"""新區域（使用者 2026-11-20 要的）：header.opened 起 14 天內，area 的名稱後面加亮黃的「新」，登入的系統公告自動列出。

用真的 areas/：樹洞（hollow.json）寫 2026-11-20。「今天」是 zones.today（conftest 平常換成很久以後，這裡自己換）。
"""
import datetime
import re
from pathlib import Path

import pytest

import mud.commands as commands
from mud import announce, stats, zones
from mud.characters import characters
from mud.color import colorize
from mud.config import ENCODING
from mud.players import Player

AREAS = Path(__file__).resolve().parent.parent / "areas"
OPENED = datetime.date(2026, 11, 20)
ANSI = re.compile(r"\x1b\[[0-9;]*m")


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


@pytest.fixture(autouse=True)
def world(monkeypatch):
    monkeypatch.setattr(announce, "lines", [])
    monkeypatch.setattr(announce, "version", None)
    zones.load(AREAS)
    yield
    characters.clear()
    zones.stop()


def on(monkeypatch, day):
    monkeypatch.setattr(zones, "today", lambda: day)


def say(line):
    p = Player("Ming", FakeWriter(), zones.world.rooms[3001])
    p.race, p.guild = stats.Race.HUMAN, stats.Guild.SWORD
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    stats.set_level(p, 5)
    commands.command(p, line)
    return p.writer.data.decode(ENCODING).rsplit("\r\n\r\n", 1)[0]


def rows():
    return ANSI.sub("", announce.current()).split("\n")


@pytest.mark.parametrize("day, new", [
    (OPENED - datetime.timedelta(days=1), False),                    # 還沒到開放那天
    (OPENED, True),                                                  # 第 1 天
    (OPENED + datetime.timedelta(days=13), True),                    # 第 14 天
    (OPENED + datetime.timedelta(days=14), False),                   # 第 15 天起不標
])
def test_new_for_14_days(monkeypatch, day, new):
    on(monkeypatch, day)
    assert ("hollow.json" in [name for name, _header in zones.new_areas()]) == new


def test_area_marks_new_areas(monkeypatch):
    on(monkeypatch, OPENED)
    raw = say("area")
    assert colorize("樹洞{Y 新{x") in raw                                     # 亮黃，跟換區域的提示一樣
    lines = ANSI.sub("", raw).split("\r\n")
    head, row = lines[1], next(line for line in lines if line.startswith("  樹洞 新 "))
    def starts(line):
        return [len(line[:m.start()].encode(ENCODING)) for m in re.finditer(r"(?<=  )\S", line)]
    assert starts(row)[:3] == starts(head)[:3]                                  # 加了「新」照樣對齊
    assert f"副本  {zones.routes['hollow.json']}" in row
    assert not any(" 新 " in line for line in lines if not line.startswith("  樹洞"))   # 別的區域沒寫 opened


def test_area_is_plain_after_14_days(monkeypatch):
    on(monkeypatch, OPENED + datetime.timedelta(days=14))
    assert " 新" not in ANSI.sub("", say("area"))


def test_announcement_lists_new_areas(monkeypatch):
    on(monkeypatch, OPENED)
    monkeypatch.setattr(announce, "lines", ["遊戲目前是 alpha 測試版。"])
    monkeypatch.setattr(announce, "version", "abc1234")
    body = [r.strip("| ").rstrip() for r in rows()[1:-1]]
    assert body == ["【系統公告】", "遊戲目前是 alpha 測試版。",
                    f"新區域：樹洞（15～20 級，副本），入口 {zones.routes['hollow.json']}", "版本 abc1234"]
    assert ANSI.sub("", say("read announce")) == "\r\n".join(rows())            # read announce 一樣
    on(monkeypatch, OPENED + datetime.timedelta(days=14))
    assert "新區域" not in announce.current()                                     # 14 天後自己消失，不用重開


def test_new_areas_without_announce_txt(monkeypatch):
    on(monkeypatch, OPENED)
    body = [r.strip("| ").rstrip() for r in rows()[1:-1]]
    assert body[0] == "【系統公告】" and body[1].startswith("新區域：樹洞") and len(body) == 2
    on(monkeypatch, OPENED - datetime.timedelta(days=1))
    assert announce.current() == ""                                               # 沒有公告也沒有新區域：沒有框


def test_no_entrance_and_too_wide(monkeypatch):
    academy = zones.templates["academy.json"][1]["area"]["header"]
    hollow = zones.templates["hollow.json"][1]["area"]["header"]
    long_title = dict(hollow, title="很長的區域名字" * 3)                       # 名稱那段放得下，接上入口就超過 75 格
    monkeypatch.setattr(zones, "new_areas", lambda: [("academy.json", academy), ("hollow.json", long_title)])
    body = [r.strip("| ").rstrip() for r in rows()[1:]][:-1]
    assert body[1] == "新區域：教學學院（1～1 級，副本）"                           # 沒有入口（-----）：不寫入口
    assert body[2] == f"新區域：{long_title['title']}（15～20 級，副本）"            # 太寬：入口換到下一行
    assert body[3] == f"入口 {zones.routes['hollow.json']}" and f"|     入口 " in rows()[4]
    assert all(len(r.encode(ENCODING)) <= 79 for r in rows())
