import asyncio
import logging
import re

import pytest

from area_helpers import make_area, make_mobile, make_room, write_json
from mud import resets, stats, zones
from mud.area import MobTier
from mud.characters import Position, characters
from mud.color import colorize
from mud.commands import command
from mud.config import ENCODING
from mud.npcs import Npc, roll_tier
from mud.players import Player


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


class FixedRng:
    """假的亂數：randrange 一律回傳 n，randint 一律回傳最小值。"""

    def __init__(self, n=0):
        self.n = n

    def randrange(self, _):
        return self.n

    def randint(self, a, _):
        return a


@pytest.fixture
def folder(tmp_path):
    yield tmp_path
    characters.clear()
    zones.stop()


def mob(vnum, **fields):
    """站著、不會骰種類、沒有旗標的生物。"""
    m = make_mobile(vnum)
    m.update(position=7, tier_roll=None, act=0, long=f"生物{vnum}在這裡晃來晃去。\n")
    m.update(fields)
    return m


def M(mob_vnum, room_vnum, limit=1, rare=0):
    return {"cmd": "M", "rare": rare, "mob_vnum": mob_vnum, "limit": limit, "room_vnum": room_vnum, "comment": ""}


def load(folder, mobiles, reset_list, rooms=(1, 2), area_number=100, name="a.json", kind="world"):
    rs = [make_room(v) for v in rooms]
    write_json(folder, name, make_area(name, rs, area_number, mobiles=mobiles, resets=reset_list, kind=kind))


def npcs():
    return [c for c in characters if isinstance(c, Npc)]


def player(name, room, position=Position.STANDING):
    p = Player(name, FakeWriter(), room)
    p.position = position
    characters.append(p)
    return p


# ---- M 把生物放進房間 ----

def test_load_puts_mobiles_in_rooms(folder):
    load(folder, [mob(1, short="野狗", keywords="dog 野狗", level=7, tier="elite", position=4, sex=2)], [M(1, 2)])
    zones.load(folder)
    [dog] = npcs()
    assert (dog.name, dog.vnum, dog.level, dog.tier, dog.position, dog.sex) == ("野狗", 101, 7, MobTier.ELITE, Position.SLEEPING, 2)
    assert dog.room is zones.world.rooms[102] and dog.room.area.name == "a.json"
    assert dog.keywords == ["dog", "野狗"]


def test_limit_counts_the_whole_zone(folder):
    load(folder, [mob(1)], [M(1, 1, limit=2), M(1, 1, limit=2), M(1, 2, limit=2)])
    zones.load(folder)
    assert len(npcs()) == 2


def test_sentinel_limit_counts_the_room(folder):
    # 待在原地的（act 2 sentinel）：每間房各自算
    load(folder, [mob(1, act=2)], [M(1, 1), M(1, 1), M(1, 2)])
    zones.load(folder)
    assert sorted(c.room.vnum for c in npcs()) == [101, 102]


def test_limit_zero_puts_nothing(folder):
    load(folder, [mob(1)], [M(1, 1, limit=0)])
    zones.load(folder)
    assert npcs() == []


@pytest.mark.parametrize("roll, appears", [(4999, True), (5000, False)])
def test_rare(folder, roll, appears):
    # rare 5010：骰 0～9999，小於 5000 才出現
    load(folder, [mob(1)], [])
    zones.load(folder)
    zones.world.areas[0].data["resets"] = [M(1, 1, rare=5010)]
    resets.reset_area(zones.world, zones.world.areas[0], resets.mobiles, FixedRng(roll))
    assert len(npcs()) == (1 if appears else 0)


@pytest.mark.parametrize("roll, tier", [(0, MobTier.ELITE), (1999, MobTier.ELITE), (2000, MobTier.BOSS),
                                        (2099, MobTier.BOSS), (2100, MobTier.NORMAL), (9999, MobTier.NORMAL)])
def test_tier_roll(roll, tier):
    # {"elite": 2000, "boss": 100}：照順序累加，0～1999 菁英、2000～2099 Boss，其他是原本的 normal
    assert roll_tier(make_mobile(1), FixedRng(roll)) == tier


def test_mobile_from_another_file(folder):
    # M 用完整號碼放別的區域檔的生物
    load(folder, [mob(1, short="野狗")], [], name="a.json", area_number=100)
    load(folder, [], [M(101, 1)], name="b.json", area_number=200)
    zones.load(folder)
    [dog] = npcs()
    assert dog.name == "野狗" and dog.room.vnum == 201 and dog.room.area.name == "b.json"


def test_room_not_in_this_zone_is_skipped(folder, caplog):
    load(folder, [mob(1)], [M(1, 50)])
    with caplog.at_level(logging.WARNING):
        zones.load(folder)
    assert npcs() == [] and "a.json 的 M 放不了：生物 101 或房間 150 不在世界裡" in caplog.text


def test_dynamic_area_and_instances_get_their_own_mobiles(folder):
    write_json(folder, "world.json", make_area("world.json", [make_room(1, north=201)], 100))
    load(folder, [mob(1)], [M(1, 1)], rooms=(1,), name="dyn.json", area_number=200, kind="dynamic")
    load(folder, [mob(1)], [M(1, 1)], rooms=(1,), name="inst.json", area_number=300, kind="instance")
    zones.load(folder)
    assert npcs() == []                     # 世界沒有生物，動態區域、副本還沒建立

    async def main():
        dyn = zones.room_at(zones.world.rooms[101], 201).zone
        a, b = zones.instance("inst.json", "小明"), zones.instance("inst.json", "阿華")
        return dyn, a, b

    dyn, a, b = asyncio.run(main())
    assert sorted(c.room.zone.name for c in npcs()) == ["dyn.json", "inst.json", "inst.json"]
    assert {c.room.zone for c in npcs()} == {dyn, a, b}         # 每份副本各自一隻


def test_reload_replaces_the_mobiles(folder):
    load(folder, [mob(1)], [M(1, 1)])
    zones.load(folder)
    zones.load(folder)
    [dog] = npcs()                          # 舊的拿掉，新的放好
    assert dog.room is zones.world.rooms[101]


# ---- 重置的時機（照 C 版的 area_update） ----

def test_reset_after_3_updates_without_players(folder):
    load(folder, [mob(1)], [M(1, 1)])
    zones.load(folder)
    characters.remove(npcs()[0])            # 被打死了
    area = zones.world.areas[0]
    for _ in range(2):
        resets.update(zones.world, FixedRng())
    assert npcs() == []
    resets.update(zones.world, FixedRng())  # 第 3 次：沒有玩家就重置
    assert len(npcs()) == 1 and area.age == 0


def test_with_players_footsteps_at_14_and_reset_at_15(folder):
    load(folder, [mob(1)], [M(1, 1)])
    zones.load(folder)
    characters.remove(npcs()[0])
    awake = player("Ming", zones.world.rooms[102])
    asleep = player("Hua", zones.world.rooms[102], Position.SLEEPING)
    for _ in range(13):
        resets.update(zones.world, FixedRng())
    assert npcs() == [] and awake.writer.data == b""
    resets.update(zones.world, FixedRng())  # 第 14 次：醒著的玩家聽到腳步聲，睡著的聽不到
    assert awake.writer.data == "\r\n你聽到一陣腳步聲。\r\n\r\n> ".encode(ENCODING)
    assert asleep.writer.data == b"" and npcs() == []
    resets.update(zones.world, FixedRng())  # 第 15 次：有玩家也重置
    assert len(npcs()) == 1 and zones.world.areas[0].age == 0


def test_zone_tick_updates_every_area_ticks(folder, monkeypatch):
    monkeypatch.setattr(zones, "AREA_TICKS", 2)
    load(folder, [], [])
    zones.load(folder)
    for _ in range(4):
        zones.world.tick()
    assert zones.world.areas[0].age == 2


# ---- look ----

def test_look_shows_mobiles_before_players(folder):
    load(folder, [mob(1, short="野狗"), mob(2, short="老鼠", position=4)], [M(1, 1), M(2, 1)])
    zones.load(folder)
    ming = player("Ming", zones.world.rooms[101])
    player("Hua", zones.world.rooms[101])
    command(ming, "look")
    text = re.sub(r"\x1b\[[0-9;]*m", "", ming.writer.data.decode(ENCODING))
    # 站著的生物顯示 long；睡著的照姿勢寫；生物在玩家前面
    assert text.endswith("\r\n生物1在這裡晃來晃去。\r\n老鼠躺在這裡睡覺。\r\nHua站在這裡。\r\n\r\n> ")



def test_look_tags_elite_and_boss(folder):
    # 名字前面的標記（使用者要的）：菁英亮綠、首領亮紅；一般、雜魚沒有。站著顯示 long、睡著照姿勢寫都一樣加
    load(folder, [mob(1, short="狼王", tier="elite"), mob(2, short="龍", tier="boss", position=4),
                  mob(3, short="野狗", tier="normal"), mob(4, short="老鼠", tier="trash")], [M(1, 1), M(2, 1), M(3, 1), M(4, 1)])
    zones.load(folder)
    ming = player("Ming", zones.world.rooms[101])
    command(ming, "look")
    raw = ming.writer.data.decode(ENCODING)
    green, red, white, reset = colorize("{G"), colorize("{R"), colorize("{W"), colorize("{x")
    assert f"{green}(菁英){white}生物1在這裡晃來晃去。{reset}" in raw
    assert f"{red}(首領){white}龍躺在這裡睡覺。{reset}" in raw
    text = re.sub(r"\x1b\[[0-9;]*m", "", raw)
    assert "\r\n生物3在這裡晃來晃去。\r\n生物4在這裡晃來晃去。\r\n" in text          # 一般、雜魚沒有標記

def test_spawned_mobile_has_its_stats(folder):
    # 出現時就照等級、骰過的種類、攻擊類型、攻防傾向、原型算好全部屬性，HP 補滿
    load(folder, [mob(1, level=10, tier="normal", tier_roll={"boss": 10000}, attack="dragon/phys",
                      defense="phys", archetype="tank")], [M(1, 1)])
    zones.load(folder)
    [dragon] = npcs()
    panel, mix = stats.mob_stats(10, "boss", "dragon/phys", "phys", "tank")
    assert dragon.tier == MobTier.BOSS
    assert (dragon.panel, dragon.mix) == (panel, mix)
    assert dragon.hp == panel["hp"] and dragon.mp == dragon.mv == 0
