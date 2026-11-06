"""分頁（mud/pager.py，玩家角色手冊「設定」）：指令的回覆超過每頁幾行先送一頁，停下來等按鍵。

用 monkeypatch 在指令表放一個會送很多行的假指令 many（many 45：送「第 1 行」～「第 45 行」）。
"""
import re

import pytest

import mud.commands as commands
from area_helpers import make_area, make_room, write_json
from mud import pager, save, zones
from mud.characters import Position, characters
from mud.config import ENCODING
from mud.players import Player
from player_helpers import make_player_file


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


def do_many(ch, arg):
    ch.send("".join(f"第 {i} 行\n" for i in range(1, int(arg) + 1)))


def do_boom(ch, arg):
    ch.send("先送出去的字\n")
    raise RuntimeError("壞了")


@pytest.fixture
def ming(tmp_path, monkeypatch):
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path / "players")
    monkeypatch.setattr(commands, "COMMANDS", commands.COMMANDS + [("many", do_many, Position.DEAD),
                                                                   ("boom", do_boom, Position.DEAD)])
    write_json(tmp_path, "a.json", make_area("a.json", [make_room(1)], 100))
    zones.load(tmp_path)
    make_player_file("Ming")
    p = save.player_from(save.load_data("Ming"), FakeWriter())
    characters.append(p)
    yield p
    characters.clear()
    zones.stop()


def plain(p):
    text = re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))
    p.writer.data = b""
    return text


def do(p, line):
    plain(p)
    commands.command(p, line)
    return plain(p)


def lines(a, b):
    return "".join(f"第 {i} 行\r\n" for i in range(a, b + 1))


def normal_prompt(p):
    return re.sub(r"\x1b\[[0-9;]*m", "", p.prompt())


def test_short_replies_are_not_paged(ming):
    assert do(ming, "many 20") == lines(1, 20) + "\r\n" + normal_prompt(ming)     # 剛好 20 行：不分頁
    assert ming.pages is None


def test_long_replies_stop_after_a_page(ming):
    assert do(ming, "many 45") == lines(1, 20) + "\r\n" + pager.PROMPT
    assert ming.prompt() == pager.PROMPT
    assert do(ming, "") == lines(21, 40) + "\r\n" + pager.PROMPT                  # Enter：下一頁
    assert do(ming, "") == lines(41, 45) + "\r\n" + normal_prompt(ming)          # 最後一頁：一般的 prompt
    assert ming.pages is None
    assert do(ming, "") == normal_prompt(ming)                                    # 不在分頁：Enter 照舊只補 prompt


def test_page_keys(ming):
    do(ming, "many 65")
    assert do(ming, "C") == lines(21, 40) + "\r\n" + pager.PROMPT                 # c 也是下一頁（不分大小寫）
    assert do(ming, "r") == lines(21, 40) + "\r\n" + pager.PROMPT                 # 重印這一頁
    assert do(ming, "b") == lines(1, 20) + "\r\n" + pager.PROMPT                  # 上一頁
    assert do(ming, "b") == lines(1, 20) + "\r\n" + pager.PROMPT                  # 已經是第一頁
    do(ming, "c")
    do(ming, "c")
    assert do(ming, "c") == lines(61, 65) + "\r\n" + normal_prompt(ming)


def test_q_stops_paging(ming):
    do(ming, "many 45")
    assert do(ming, "q") == normal_prompt(ming) and ming.pages is None


def test_typing_a_command_stops_paging_and_runs_it(ming):
    do(ming, "many 45")
    out = do(ming, "look")                                                        # 使用者選的：結束分頁，照常執行
    assert out.startswith("【房間1】") and out.endswith(normal_prompt(ming)) and ming.pages is None


def test_page_size_is_the_players_setting(ming):
    do(ming, "config lines 30")
    assert do(ming, "many 45") == lines(1, 30) + "\r\n" + pager.PROMPT
    assert do(ming, "") == lines(31, 45) + "\r\n" + normal_prompt(ming)


def test_other_messages_while_paging_end_with_the_page_prompt(ming):
    hua = Player("Hua", FakeWriter(), ming.room)
    characters.append(hua)
    do(ming, "many 45")
    commands.command(hua, "chat 嗨")                                              # 別人的訊息照樣馬上送進來（照 C 版）
    assert plain(ming) == "\r\nHua 聊天：嗨\r\n\r\n" + pager.PROMPT
    assert do(ming, "") == lines(21, 40) + "\r\n" + pager.PROMPT


def test_quit_still_says_goodbye(ming):
    assert commands.command(ming, "quit") is False and "再見。" in plain(ming)


def test_an_error_does_not_swallow_what_was_sent(ming):
    with pytest.raises(RuntimeError):
        commands.command(ming, "boom")
    assert plain(ming) == "先送出去的字\r\n" and ming.capture is None
