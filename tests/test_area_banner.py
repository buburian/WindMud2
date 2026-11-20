"""換區域的提示（system.area_banner，使用者 2026-11-20 要的）：從一個區域檔走進另一個，新房間的畫面前面先是有外框的區域名稱。
走路、逃跑、回城都算（goto 在 test_imm.py、腳本的 transfer 在 test_academy.py）；同一個區域檔裡走、生物、睡著不出現；很暗照樣出現。
"""
import asyncio
import re

import pytest

import mud.commands as commands
from area_helpers import make_area, make_mobile, make_room, write_json
from mud import fight, stats, weather, zones
from mud.area import RoomFlag
from mud.characters import Position, characters
from mud.color import colorize
from mud.commands import combat as combat_commands
from mud.commands.system import area_banner, width
from mud.config import ENCODING
from mud.npcs import Npc
from mud.players import Player


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


@pytest.fixture
def world(tmp_path, monkeypatch):
    """a.json「測試」1～5 級：101 —北— 102；b.json「隔壁的林子」10～20 級：201（102 往東）、202 很暗（201 往東，有一隻狗）。"""
    monkeypatch.setattr(zones, "START_ROOM", 101)
    monkeypatch.setattr(fight, "TICK_SECONDS", 1000)
    monkeypatch.setattr(weather, "current", weather.Weather(hour=12))
    write_json(tmp_path, "a.json", make_area("a.json", [make_room(101, north=102), make_room(102, south=101, east=201)]))
    dark = make_room(202, west=201)
    dark["room_flags"] = int(RoomFlag.DARK)
    dog = make_mobile(201)
    dog.update(short="野狗", keywords="dog", act=2, position=7, drops=[], special=None, shop=None, long="", tier_roll=None)
    other = make_area("b.json", [make_room(201, west=102, east=202), dark], (200, 299), mobiles=[dog],
                      resets=[{"cmd": "M", "rare": 0, "mob_vnum": 201, "limit": 1, "room_vnum": 201, "comment": ""}])
    other["area"]["header"].update(title="隔壁的林子", levels=[10, 20])
    write_json(tmp_path, "b.json", other)
    zones.load(tmp_path)
    yield zones.world
    characters.clear()
    zones.stop()


def person(room):
    p = Player("Ming", FakeWriter(), zones.world.rooms[room])
    p.race, p.guild = stats.Race.HUMAN, stats.Guild.SWORD
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.skills = []
    stats.set_level(p, 1)
    characters.append(p)
    return p


def raw(p):
    text = p.writer.data.decode(ENCODING)
    p.writer.data = b""
    return text


def say(p, line):
    raw(p)
    commands.command(p, line)
    return re.sub(r"\x1b\[[0-9;]*m", "", raw(p))


def frame(text):
    edge = "+" + "-" * (width(text) + 2) + "+"
    return f"{edge}\r\n| {text} |\r\n{edge}\r\n"


NEXT_DOOR = frame("*** 隔壁的林子（10～20 級） ***")
HOME = frame("*** 測試（1～5 級） ***")


def test_walking_into_another_area_file(world):
    ming = person(102)
    assert say(ming, "e").startswith("\r\n" + NEXT_DOOR + "\r\n【房間201】")    # 空一行、外框、空一行、房間
    assert say(ming, "w").startswith("\r\n" + HOME + "\r\n【房間102】")


def test_the_frame_fits_the_name():
    # 外框用半形的 + - |；中文算兩格：「*** 隔壁的林子（10～20 級） ***」31 格，左右各多一格空白
    assert NEXT_DOOR.split("\r\n")[0] == "+" + "-" * 33 + "+" and len(NEXT_DOOR.split("\r\n")[1].encode(ENCODING)) == 35


def test_bright_yellow(world):
    ming = person(102)
    raw(ming)
    commands.command(ming, "e")
    assert raw(ming).startswith("\r\n" + colorize("{Y" + NEXT_DOOR.rstrip("\r\n") + "{x"))


def test_not_inside_the_same_area_file(world):
    ming = person(101)
    assert say(ming, "n").startswith("【房間102】")


def test_dark_rooms_still_show_it(world):
    ming = person(201)
    assert say(ming, "e").startswith("這裡黑漆漆的一片")                       # 同一個檔、很暗：沒有外框
    ming.room = zones.world.rooms[102]
    zones.world.rooms[201].room_flags |= RoomFlag.DARK
    out = say(ming, "e")
    assert out.startswith("\r\n" + NEXT_DOOR + "\r\n") and "黑漆漆" in out      # 很暗也出現（走過來就知道到了哪裡）


def test_only_awake_players(world):
    ming, dog = person(201), next(c for c in characters if isinstance(c, Npc))
    before = zones.world.rooms[102]
    assert area_banner(ming, before) == colorize("{Y" + NEXT_DOOR.rstrip("\r\n") + "{x").replace("\r\n", "\n") + "\n\n"
    ming.position = Position.SLEEPING
    assert area_banner(ming, before) == ""                                    # 睡著看不到房間
    assert area_banner(dog, before) == ""                                     # 生物不用


def test_fleeing_and_recall_count(world):
    ming = person(201)
    dog = next(c for c in characters if isinstance(c, Npc))

    async def main():
        fight.start_fight(ming, dog)
        raw(ming)
        combat_commands.escape(ming, "west")
        return re.sub(r"\x1b\[[0-9;]*m", "", raw(ming))

    assert asyncio.run(main()).startswith("你從戰鬥中逃跑了!!\r\n\r\n" + HOME + "\r\n【房間102】")
    ming.room = zones.world.rooms[201]
    assert HOME + "\r\n【房間101】" in say(ming, "recall")                     # 回城回到 a.json 的 101
