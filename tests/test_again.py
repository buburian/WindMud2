"""「!」重複上一個指令（照 C 版 comm.c 的 inlast，使用者要的）。"""
import re

import pytest

import mud.commands as commands
from area_helpers import make_area, make_room, write_json, write_lua
from mud import save, zones
from mud.characters import Position, characters
from mud.config import ENCODING
from player_helpers import make_player_file


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


def do_many(ch, arg):
    ch.send("".join(f"第 {i} 行\n" for i in range(1, 31)))


@pytest.fixture
def ming(tmp_path, monkeypatch):
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path / "players")
    monkeypatch.setattr(commands, "COMMANDS", commands.COMMANDS + [("many", do_many, Position.DEAD)])
    rooms = [make_room(1, north=2), make_room(2, south=1)]
    rooms[1]["script"] = {"file": "r.lua", "timer": None}
    write_lua(tmp_path, "a.json", "r.lua", 'function on_command(actor, cmd, arg) room.vars.last = cmd end')
    write_json(tmp_path, "a.json", make_area("a.json", rooms, 100))
    zones.load(tmp_path)
    make_player_file("Ming")
    p = save.player_from(save.load_data("Ming"), FakeWriter())
    characters.append(p)
    yield p
    characters.clear()
    zones.stop()


def do(p, line):
    p.writer.data = b""
    commands.command(p, line)
    return re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING)).rsplit("\r\n\r\n", 1)[0]


def test_bang_before_any_command(ming):
    assert do(ming, "!") == "你還沒有打過指令。"


def test_bang_repeats_the_last_command(ming):
    assert do(ming, "look").startswith("【房間1】")
    assert do(ming, "!").startswith("【房間1】")
    do(ming, "n")
    assert ming.room.vnum == 102
    do(ming, "!")                                                       # 再一次 north：房間 2 往北沒有出口
    assert ming.room.vnum == 102 and zones.world.rooms[102].vars["last"] == "north"   # 腳本看到的是真的指令


def test_enter_and_bang_are_not_remembered(ming):
    do(ming, "look")
    do(ming, "")                                                        # 只按 Enter：不算
    do(ming, "!")
    assert ming.last_line == "look" and do(ming, "!").startswith("【房間1】")
    assert do(ming, "!xyz").startswith("【房間1】")                     # 「!」開頭的都算（照 C 版）


def test_bang_while_paging(ming):
    do(ming, "look")
    do(ming, "many")
    assert ming.pages is not None and ming.last_line == "many"
    do(ming, "c")                                                       # 翻頁的按鍵不記
    assert ming.last_line == "many"
    do(ming, "look")                                                    # 打別的：結束分頁、照常執行，也記下來
    do(ming, "many")
    out = do(ming, "!")                                                 # 分頁中打 !：結束分頁，重複上一個指令（many）
    assert out.startswith("第 1 行") and ming.pages is not None
