import pytest

import mud.commands as commands
from mud.commands import system
from mud.config import ENCODING
from mud.players import Player, players


class FakeWriter:
    """假的連線：只把送出的 bytes 收起來。"""

    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


def cast(writer, name, arg):
    pass


def channel(writer, name, arg):
    pass


def chat(writer, name, arg):
    pass


def test_first_command_starting_with_input_wins(monkeypatch):
    monkeypatch.setattr(commands, "COMMANDS", [("cast", cast), ("channel", channel), ("chat", chat)])
    assert commands.find("c") is cast
    assert commands.find("ch") is channel
    assert commands.find("cha") is channel
    assert commands.find("chat") is chat
    assert commands.find("x") is None


def test_order_decides_priority(monkeypatch):
    monkeypatch.setattr(commands, "COMMANDS", [("chat", chat), ("channel", channel)])
    assert commands.find("ch") is chat
    assert commands.find("chan") is channel


def test_real_table():
    assert commands.find("c") is system.do_chat
    assert commands.find("t") is system.do_tell
    assert commands.find("r") is system.do_reply
    assert commands.find("q") is system.do_quit


def test_quit_abbreviation_saves_and_disconnects(monkeypatch):
    saved = []
    monkeypatch.setattr(system, "save_player", saved.append)
    w = FakeWriter()
    assert commands.command(w, "小明", "q") is False
    assert saved == ["小明"]
    assert w.data == "再見。\r\n".encode(ENCODING)


def test_unknown_command():
    w = FakeWriter()
    assert commands.command(w, "小明", "xyz") is True
    assert w.data == "什麼？\r\nHP100> ".encode(ENCODING)


@pytest.fixture
def online():
    # 小明、阿華、Bob 都在線
    ws = {}
    for name in ("小明", "阿華", "Bob"):
        ws[name] = FakeWriter()
        players[ws[name]] = Player(name)
    yield ws
    players.clear()


def test_tell_reaches_only_target_in_green(online):
    ming, hua, bob = online["小明"], online["阿華"], online["Bob"]
    commands.command(ming, "小明", "tell 阿華 晚點見")
    assert ming.data == "\x1b[32;1m你告訴阿華：晚點見\x1b[0m\r\nHP100> ".encode(ENCODING)
    assert hua.data == "\r\n\x1b[32;1m小明告訴你：晚點見\x1b[0m\r\nHP100> ".encode(ENCODING)
    assert bob.data == b""


def test_tell_english_name_ignores_case(online):
    commands.command(online["小明"], "小明", "t bob hi")
    assert "小明告訴你：hi".encode(ENCODING) in online["Bob"].data


def test_tell_unknown_target(online):
    ming = online["小明"]
    commands.command(ming, "小明", "tell 小美 你好")
    assert ming.data == "沒有找到你想說話的對象。\r\nHP100> ".encode(ENCODING)


def test_reply_goes_back_to_last_teller(online):
    ming, hua = online["小明"], online["阿華"]
    commands.command(ming, "小明", "tell 阿華 晚點見")
    ming.data = hua.data = b""
    commands.command(hua, "阿華", "r 好啊")
    assert hua.data == "\x1b[32;1m你告訴小明：好啊\x1b[0m\r\nHP100> ".encode(ENCODING)
    assert ming.data == "\r\n\x1b[32;1m阿華告訴你：好啊\x1b[0m\r\nHP100> ".encode(ENCODING)


def test_reply_without_teller_or_after_teller_left(online):
    ming, hua = online["小明"], online["阿華"]
    commands.command(hua, "阿華", "reply 嗨")
    assert hua.data == "找不到你想回答的對象。\r\nHP100> ".encode(ENCODING)
    commands.command(ming, "小明", "tell 阿華 晚點見")
    del players[ming]                            # 小明離線了
    hua.data = b""
    commands.command(hua, "阿華", "reply 嗨")
    assert hua.data == "找不到你想回答的對象。\r\nHP100> ".encode(ENCODING)


def test_reply_missing_message(online):
    ming, hua = online["小明"], online["阿華"]
    commands.command(ming, "小明", "tell 阿華 晚點見")
    hua.data = b""
    commands.command(hua, "阿華", "reply")
    assert hua.data == "你想回答些什麼呢？\r\nHP100> ".encode(ENCODING)


def test_tell_missing_message(online):
    ming = online["小明"]
    for line in ("tell", "tell 阿華"):
        ming.data = b""
        commands.command(ming, "小明", line)
        assert ming.data == "你想要告訴誰些什麼呢？\r\nHP100> ".encode(ENCODING)
