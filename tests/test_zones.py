import asyncio
import logging

import pytest

from area_helpers import make_room, write_area
from mud import fight, zones
from mud.act import TO_ROOM, act
from mud.area import AreaType
from mud.characters import Position, characters
from mud.commands import command
from mud.commands.system import look
from mud.config import ENCODING
from mud.players import Player


class FakeWriter:
    """假的連線：只把送出的 bytes 收起來。"""

    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


@pytest.fixture
def folder(tmp_path):
    # 世界：101 往北是動態區域的 201。動態區域：201 往南回 101、往北 202。副本：301、302 南北相連。
    write_area(tmp_path, "world.json", [make_room(1, north=201)], area_number=100)
    write_area(tmp_path, "dyn.json", [make_room(1, south=101, north=2), make_room(2, south=1)],
               area_number=200, kind="dynamic")
    write_area(tmp_path, "inst.json", [make_room(1, north=2), make_room(2, south=1)],
               area_number=300, kind="instance")
    zones.load(tmp_path)
    yield tmp_path
    characters.clear()
    zones.stop()


@pytest.fixture
def fast(monkeypatch):
    # tick 0.01 秒一次，沒有玩家 0.05 秒就釋放
    monkeypatch.setattr(zones, "TICK_SECONDS", 0.01)
    monkeypatch.setattr(zones, "RELEASE_SECONDS", 0.05)


def player(name, room):
    p = Player(name, FakeWriter(), room)
    characters.append(p)
    return p


async def until(cond, timeout=2):
    """等到 cond() 成立；等太久就算失敗。"""
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not cond():
        assert loop.time() < end, "等太久"
        await asyncio.sleep(0.005)


def test_load_builds_only_the_world(folder):
    assert set(zones.world.rooms) == {101}
    assert zones.world.rooms[101].zone is zones.world
    assert zones.dynamic == {} and zones.instances == {}
    assert {name: t[0] for name, t in zones.templates.items()} == {
        "dyn.json": AreaType.DYNAMIC, "inst.json": AreaType.INSTANCE}


def test_walking_in_builds_the_dynamic_area_once(folder):
    ming = player("小明", zones.start_room())
    hua = player("阿華", zones.start_room())
    command(ming, "n")
    assert ming.room.vnum == 201 and ming.room.zone.kind == AreaType.DYNAMIC
    assert zones.dynamic["dyn.json"] is ming.room.zone
    command(hua, "n")                       # 第二個人走進去：同一份
    assert hua.room is ming.room
    command(ming, "n")                      # 在動態區域裡走，留在同一份
    assert ming.room is zones.dynamic["dyn.json"].rooms[202]
    command(hua, "s")                       # 走回世界
    assert hua.room is zones.world.rooms[101]


def test_dynamic_area_is_released_when_no_player_is_inside(folder, fast):
    async def main():
        ming = player("小明", zones.start_room())
        command(ming, "n")
        first = ming.room
        command(ming, "s")
        zones.start()
        await until(lambda: "dyn.json" not in zones.dynamic)
        command(ming, "n")                  # 再走進去：重新建立，是新的一份
        assert ming.room.vnum == 201 and ming.room is not first

    asyncio.run(main())


def test_dynamic_area_stays_while_a_player_is_inside(folder, fast):
    async def main():
        ming = player("小明", zones.start_room())
        command(ming, "n")
        zone = ming.room.zone
        zones.start()
        await asyncio.sleep(0.2)            # 比釋放時間久很多
        assert zones.dynamic["dyn.json"] is zone

    asyncio.run(main())


def test_world_tick_ticks_world_and_every_dynamic_area(folder, fast, monkeypatch):
    ticked = []
    monkeypatch.setattr(zones.Zone, "tick", lambda self: ticked.append(self.name))

    async def main():
        command(player("小明", zones.start_room()), "n")
        zones.start()
        await until(lambda: ticked.count("dyn.json") >= 3)

    asyncio.run(main())
    assert ticked[:2] == ["世界", "dyn.json"]   # 每次先做世界，再做動態區域


def test_tick_error_only_affects_that_zone(folder, fast, monkeypatch, caplog):
    ticked = []

    def tick(self):
        if self.name == "dyn.json":
            raise RuntimeError("壞掉了")
        ticked.append(self.name)

    monkeypatch.setattr(zones.Zone, "tick", tick)

    async def main():
        command(player("小明", zones.start_room()), "n")
        zones.start()
        await until(lambda: ticked.count("世界") >= 3)   # 動態區域每次都出錯，世界照樣一直 tick

    with caplog.at_level(logging.ERROR):
        asyncio.run(main())
    assert "dyn.json 的 tick 出錯" in caplog.text


def test_instance_one_copy_per_owner(folder):
    async def main():
        a = zones.instance("inst.json", "小明")
        assert zones.instance("inst.json", "小明") is a
        b = zones.instance("inst.json", "阿華")
        assert b is not a and b.rooms[301] is not a.rooms[301]
        assert a.task is not b.task and not a.task.done() and not b.task.done()   # 每份副本自己一個 tick loop

    asyncio.run(main())


def test_instance_only_for_instance_files(folder):
    async def main():
        with pytest.raises(ValueError, match="不是副本區域"):
            zones.instance("dyn.json", "小明")

    asyncio.run(main())


def test_two_copies_do_not_see_each_other(folder):
    async def main():
        a, b = zones.instance("inst.json", "小明"), zones.instance("inst.json", "阿華")
        ming = player("小明", a.rooms[301])
        bob = player("Bob", a.rooms[301])
        hua = player("阿華", b.rooms[301])  # 號碼一樣，但在另一份
        assert "Bob站在這裡" in look(ming) and "阿華" not in look(ming)
        act("$n揮揮手。", ming, to=TO_ROOM)
        assert "小明揮揮手".encode(ENCODING) in bob.writer.data
        assert hua.writer.data == b""
        command(ming, "n")                  # 在副本裡走，留在同一份
        assert ming.room is a.rooms[302]

    asyncio.run(main())


def test_instance_is_released_when_empty(folder, fast):
    async def main():
        zone = zones.instance("inst.json", "小明")
        await until(lambda: zone.released)
        assert zones.instances == {}
        await until(lambda: zone.task.done())   # 自己的 tick loop 也結束了
        assert zones.instance("inst.json", "小明") is not zone

    asyncio.run(main())


def test_release_stops_fights_and_removes_leftovers(folder, fast, monkeypatch):
    monkeypatch.setattr(fight, "ROUND_SECONDS", 0.01)

    async def main():
        zone = zones.instance("inst.json", "小明")
        ming = player("小明", zone.rooms[301])
        hua = player("阿華", zone.rooms[301])
        f = fight.start_fight(ming, hua)
        characters.remove(ming)             # 小明離線；阿華（當成之後的 NPC）還在裡面打
        fight.stop_fighting(ming)
        zones.release(zone)
        assert zone.fights == set() and hua.fight is None and hua.position == Position.STANDING
        assert hua not in characters        # 留在裡面的角色一起移走
        await until(lambda: f.task.done())

    asyncio.run(main())


def test_reload_stops_old_loops(folder):
    async def main():
        zones.start()
        old_tick = zones.world_task
        inst = zones.instance("inst.json", "小明")
        zones.load(folder)
        await until(lambda: old_tick.done() and inst.task.done())
        assert zones.instances == {}

    asyncio.run(main())
