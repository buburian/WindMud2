"""系統公告（announce.py，使用者 2026-11-20 要的）：舊角色登入時「歡迎回來」和房間之間，前後空一行、有外框；平常打 read announce 看；
檔案空的、沒有就不顯示；太寬、太長、轉不成 Big5 不開機（原本的不動）。"""
import re
from pathlib import Path

import pytest

from mud import announce, commands
from mud.config import ANNOUNCE_FILE, ENCODING
from player_helpers import PASSWORD, make_player_file
from test_login import NORTH, folder, run, text  # noqa: F401（folder 是 fixture）

ANSI = re.compile(r"\x1b\[[0-9;]*m")


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setattr(announce, "text", "")


def write(tmp_path, text):
    path = tmp_path / "announce.txt"
    path.write_text(text, encoding="utf-8")
    return path


def box(text):
    return ANSI.sub("", text).split("\n")


def test_the_real_file_loads():
    announce.load(ANNOUNCE_FILE)                         # 空的也行：就是沒有公告


@pytest.mark.parametrize("text", ["", "\n\n", "   \n"])
def test_empty_means_no_announcement(tmp_path, text):
    announce.load(write(tmp_path, text))
    assert announce.text == ""


def test_missing_file_means_no_announcement(tmp_path):
    announce.load(tmp_path / "nothing.txt")
    assert announce.text == ""


def test_the_box(tmp_path):
    announce.load(write(tmp_path, "邪龍教派開放了。\n打 area 看怎麼走。\n\n"))   # 最後的空行不算
    assert box(announce.text) == ["+--------------------+",          # 照最寬的那一行（18 格）
                                       "| 【系統公告】       |",
                                       "| 邪龍教派開放了。   |",
                                       "| 打 area 看怎麼走。 |",
                                       "+--------------------+"]
    assert announce.text.startswith("\x1b[33;1m+")             # 外框亮黃


def test_colour_codes_do_not_count(tmp_path):
    announce.load(write(tmp_path, "{R注意{x：明天維修"))
    rows = box(announce.text)
    assert rows[2] == "| 注意：明天維修 |" and len({len(r.encode(ENCODING)) for r in rows}) == 1


@pytest.mark.parametrize("text, problem", [
    ("字" * 38, "第 1 行太寬了：76 格，最多 75 格（外框佔 4 格）"),
    ("\n".join(["一行"] * 11), "太長了：11 行，最多 10 行"),
    ("龍🐉", "第 1 行有轉不成 Big5 的字 '🐉'"),
])
def test_rules(tmp_path, text, problem):
    announce.load(write(tmp_path, "原本的"))
    with pytest.raises(ValueError, match=re.escape(problem)):
        announce.load(write(tmp_path, text))
    assert "原本的" in announce.text                            # 有問題：原本的不動


def test_widest_line_that_fits(tmp_path):
    announce.load(write(tmp_path, "字" * 37 + "a"))        # 75 格剛好放得下，整個框 79 格
    assert {len(r.encode(ENCODING)) for r in box(announce.text)} == {79}


def test_shown_between_welcome_and_the_room(folder, tmp_path):
    announce.load(write(tmp_path, "邪龍教派開放了。"))
    make_player_file("Ming", room=102)

    async def main(connect):
        c = await connect()
        await c.until("請輸入你的英文名字：")
        c.say("Ming")
        await c.until("請輸入密碼：")
        c.say(PASSWORD)
        got = ANSI.sub("", text(await c.until("> ")))
        assert re.search(r"歡迎回來，Ming。\r\n\r\n\+-+\+\r\n\| 【系統公告】 +\|\r\n\| 邪龍教派開放了。 +\|\r\n\+-+\+\r\n\r\n【", got)
        assert NORTH in got

    run(main)


# ---- read ----

class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


def read(line):
    from mud.characters import Position
    from mud.players import Player
    p = Player("Ming", FakeWriter(), None)
    p.position = Position.SLEEPING                                   # 睡著也能讀
    commands.command(p, line)
    return ANSI.sub("", p.writer.data.decode(ENCODING)).rsplit("\r\n\r\n", 1)[0]


def test_read_announce(tmp_path):
    announce.load(write(tmp_path, "邪龍教派開放了。"))
    assert read("read announce") == "\r\n".join(box(announce.text))
    assert read("rea ann") == read("read announce")                  # 指令、名字都可以縮寫


def test_read_without_an_announcement():
    assert read("read announce") == "現在沒有系統公告。"


@pytest.mark.parametrize("line", ["read", "read mail"])
def test_read_lists_what_can_be_read(line):
    assert read(line) == "要讀什麼？可以讀的：\r\n  announce：系統公告"


def test_read_keeps_the_old_abbreviations():
    assert commands.find("r") is commands.find("reply") and commands.find("rea") is commands.find("read")
