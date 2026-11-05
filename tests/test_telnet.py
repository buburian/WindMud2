from mud.config import ENCODING, MAX_LINE
from mud.telnet import BINARY, DO, DONT, ECHO, IAC, SB, SE, START, WILL, WONT, Telnet, encode


def test_newlines_each_count_once():
    # \r\n、\r\0、\n、單獨的 \r 都只算一次換行
    tn = Telnet()
    assert tn.feed(b"a\r\nb\r\0c\nd\re\r\n") == ["a", "b", "c", "d", "e"]


def test_crlf_split_across_reads():
    tn = Telnet()
    assert tn.feed(b"a\r") == ["a"]
    assert tn.feed(b"\nb\r\n") == ["b"]


def test_big5_char_split_across_reads():
    tn = Telnet()
    data = "小明".encode(ENCODING)
    assert tn.feed(data[:1]) == []
    assert tn.feed(data[1:] + b"\r\n") == ["小明"]


def test_iac_split_across_reads():
    tn = Telnet()
    assert tn.feed(bytes([IAC])) == []
    assert tn.feed(bytes([WILL])) == []
    assert tn.feed(bytes([1]) + b"hi\r\n") == ["hi"]
    assert tn.replies == bytes([IAC, DONT, 1])


def test_refuse_once_and_ignore_wont_dont():
    tn = Telnet()
    tn.feed(bytes([IAC, WILL, 1, IAC, WILL, 1, IAC, DO, 3, IAC, WONT, 5, IAC, DONT, 6]))
    assert tn.replies == bytes([IAC, DONT, 1, IAC, WONT, 3])


def test_start_asks_for_binary_and_accepts_will():
    # 一連上請對方用 8-bit 傳；對方回 WILL BINARY 是答應，不能再回 DONT
    assert START == bytes([IAC, DO, BINARY])
    tn = Telnet()
    tn.feed(bytes([IAC, WILL, BINARY]))
    assert tn.replies == b""
    tn.feed(bytes([IAC, DO, BINARY]))
    assert tn.replies == bytes([IAC, WONT, BINARY])


def test_echo_off_accepts_do_echo():
    # 打密碼：我們說 WILL ECHO，對方回 DO ECHO 是答應，不能再回 WONT（那樣又把回顯打開了）
    tn = Telnet()
    assert tn.echo_off() == bytes([IAC, WILL, ECHO])
    assert tn.feed(bytes([IAC, DO, ECHO]) + b"secret\r\n") == ["secret"]
    assert tn.replies == b""
    assert tn.echo_on() == bytes([IAC, WONT, ECHO])
    tn.feed(bytes([IAC, DONT, ECHO]))       # 對方答應恢復回顯，不用回
    assert tn.replies == b""


def test_do_echo_without_asking_is_refused():
    tn = Telnet()
    tn.feed(bytes([IAC, DO, ECHO]))
    assert tn.replies == bytes([IAC, WONT, ECHO])


def test_subnegotiation_dropped():
    tn = Telnet()
    assert tn.feed(b"a" + bytes([IAC, SB, 24, 1, IAC, SE]) + b"b\r\n") == ["ab"]


def test_iac_iac_is_one_0xff_byte():
    tn = Telnet()
    tn.feed(b"a" + bytes([IAC, IAC]) + b"b")
    assert tn.line == b"a\xffb"


def test_backspace_removes_whole_big5_char():
    tn = Telnet()
    # 「小」的第二碼是 0x70（'p'），退格不能只退半個字
    assert tn.feed("小a".encode(ENCODING) + b"\x08\r\n") == ["小"]
    assert tn.feed("小明".encode(ENCODING) + b"\x7f\r\n") == ["小"]


def test_line_longer_than_max_is_truncated():
    tn = Telnet()
    assert tn.feed(b"A" * (MAX_LINE + 500) + b"\r\n") == ["A" * MAX_LINE]


def test_encode():
    assert encode("你好\n") == "你好".encode(ENCODING) + b"\r\n"
