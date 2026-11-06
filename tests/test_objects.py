"""物品：做出物品（固定、隨機裝備）、掉落表、屍體、slay、look 看屍體、屍體消失、區域物件釋放。"""
import asyncio
import logging
import random
import re

import pytest

import mud.commands as commands
from area_helpers import make_area, make_mobile, make_object, make_room, write_json
from mud import death, equipment, fight, objects, resets, zones
from mud.area import CORPSE_NPC_ITEM_TYPE, Apply, MobTier
from mud.characters import Position, characters
from mud.color import colorize
from mud.commands import imm, system
from mud.config import ENCODING
from mud.npcs import Npc
from mud.players import Player


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


class FixedRng:
    """假的亂數：randrange 一律回傳 n，randint 一律回傳最小值；記住 randrange 被叫了幾次。其他（隨機裝備用的）照真的亂數。"""

    def __init__(self, n=0):
        self.n, self.calls = n, 0
        self.real = random.Random(0)

    def __getattr__(self, name):
        return getattr(self.real, name)

    def randrange(self, _):
        self.calls += 1
        return self.n

    def randint(self, a, _):
        return a


@pytest.fixture
def folder(tmp_path):
    yield tmp_path
    characters.clear()
    zones.stop()


def mob(vnum, drops=(), **fields):
    """站著、不會骰種類、沒有旗標的生物。"""
    m = make_mobile(vnum)
    m.update(position=7, tier_roll=None, act=0, long="", sex=1, drops=list(drops))
    m.update(fields)
    return m


def potion(vnum):
    """不是裝備的物品（藥水，只能拿起來）。"""
    o = make_object(vnum)
    o.update(short="治療藥水", keywords="potion 藥水", item_type=10, wear_flags="1", values=[5, "cure light", "", ""],
             affects=[], extra_descriptions=[], script=None)
    return o


def sword(vnum, affects=()):
    """單手長劍。affects 是空的就是隨機裝備。"""
    o = make_object(vnum)
    o.update(short="長劍", keywords="sword 長劍", affects=list(affects), extra_descriptions=[], script=None)
    return o


def drop(obj_vnum, chance=10000, color=None, tiers=None):
    return {"obj_vnum": obj_vnum, "color": color, "chance": chance, "tiers": tiers}


def M(mob_vnum, room_vnum, limit=1):
    return {"cmd": "M", "rare": 0, "mob_vnum": mob_vnum, "limit": limit, "room_vnum": room_vnum, "comment": ""}


def load(folder, mobiles=(), objects_=(), reset_list=(), name="a.json", area_number=100, kind="world", rooms=(1, 2)):
    rs = [make_room(v) for v in rooms]
    write_json(folder, name, make_area(name, rs, area_number, mobiles=mobiles, resets=reset_list,
                                       objects=objects_, kind=kind))


def world_with_dog(folder, drops=(), objs=()):
    """世界：房間 101 有一隻野狗（生物 101）。"""
    load(folder, [mob(1, drops, short="野狗", keywords="dog 野狗", level=5)], objs, [M(1, 1)])
    zones.load(folder)
    return next(c for c in characters if isinstance(c, Npc))


def player(name, room, position=Position.STANDING, is_imm=False):
    p = Player(name, FakeWriter(), room)
    p.position, p.imm = position, is_imm
    characters.append(p)
    return p


def raw(p):
    """收到的字（留著顏色），看完就清掉。"""
    text = p.writer.data.decode(ENCODING)
    p.writer.data = b""
    return text


def text_of(p):
    """收到的字（拿掉顏色），看完就清掉。"""
    return re.sub(r"\x1b\[[0-9;]*m", "", raw(p))


def corpse_in(room):
    [corpse] = [o for o in room.contents if o.item_type == CORPSE_NPC_ITEM_TYPE]
    return corpse


# ---- 做出物品 ----

def test_fixed_equipment_uses_written_affects(monkeypatch):
    monkeypatch.setattr(objects, "protos", {101: sword(1, [{"location": 1, "modifier": 2}, {"location": 9, "modifier": 3}])})
    o = objects.create(101, 10, "orange", random.Random(1))
    assert (o.vnum, o.name, o.keywords, o.level, o.color) == (101, "長劍", ["sword", "長劍"], 10, "orange")
    assert o.affects == [(Apply.STR, 2), (Apply.HIT, 3)]
    assert o.base == equipment.base_values("wield", 10, random.Random(1))     # 基本值照等級算


@pytest.mark.parametrize("seed", range(5))
def test_random_equipment_rolls_and_puts_the_name_in_front(monkeypatch, seed):
    monkeypatch.setattr(objects, "protos", {101: sword(1)})
    o = objects.create(101, 10, "orange", random.Random(seed))
    rolled = equipment.roll_item("wield", 10, "orange", random.Random(seed))
    assert rolled["name"] and o.name == rolled["name"] + "長劍"        # 疾風之蠻力長劍
    assert o.affects == [(Apply[k.upper()], n) for k, n in rolled["affixes"].items()]
    assert o.base == rolled["base"]


@pytest.mark.parametrize("color", ["gray", None])
def test_gray_or_no_color_has_no_random_affects(monkeypatch, color):
    monkeypatch.setattr(objects, "protos", {101: sword(1)})
    o = objects.create(101, 10, color, random.Random(1))
    assert (o.name, o.affects) == ("長劍", [])
    assert set(o.base) == {"dmg_min", "dmg_max"}


def test_not_equipment_has_no_affects(monkeypatch):
    monkeypatch.setattr(objects, "protos", {101: potion(1)})
    o = objects.create(101, 10, None)
    assert (o.name, o.affects, o.base) == ("治療藥水", [], {})


def test_slots_for_two_handed_offhand_weapon_and_shield(monkeypatch):
    great = sword(1)
    great.update(extra_flags=512, values=[8, 0, 0, 3])              # 大劍：雙手
    offhand = sword(2)
    offhand.update(wear_flags="1|512")                              # 副手武器（雙持）
    shield = sword(3)
    shield.update(item_type=9, wear_flags="1|512", values=[0, 0, 0, 0])
    monkeypatch.setattr(objects, "protos", {101: great, 102: offhand, 103: shield})
    for vnum, slot, offhand_weapon in ((101, "two_handed", False), (102, "offhand", True), (103, "offhand", False)):
        o = objects.create(vnum, 20, "blue", random.Random(7))
        want = equipment.roll_item(slot, 20, "blue", random.Random(7), offhand_weapon)
        assert o.base == want["base"] and o.affects == [(Apply[k.upper()], n) for k, n in want["affixes"].items()], vnum
    assert "ac" in objects.create(103, 20, "blue").base and "dmg_min" in objects.create(102, 20, "blue").base


def test_unknown_object_is_logged(monkeypatch, caplog):
    monkeypatch.setattr(objects, "protos", {})
    with caplog.at_level(logging.WARNING):
        assert objects.create(999, 1, None) is None
    assert "做不出物品 999：沒有這個號碼的物品" in caplog.text


# ---- 掉落表 ----

def test_drops_use_the_mobile_level_and_the_line_color(folder):
    dog = world_with_dog(folder, [drop(1, color="white")], [sword(1)])
    [o] = objects.roll_drops(dog)
    assert (o.vnum, o.level, o.color) == (101, 5, "white")


def test_each_line_rolls_on_its_own(folder):
    dog = world_with_dog(folder, [drop(1), drop(2, chance=5000), drop(1, color="blue")], [sword(1), potion(2)])
    found = objects.roll_drops(dog, FixedRng(5000))                 # 中間那行沒骰到，不影響後面那行
    assert [(o.vnum, o.color) for o in found] == [(101, None), (101, "blue")]     # 照掉落表的順序


@pytest.mark.parametrize("roll, dropped", [(4999, True), (5000, False)])
def test_chance_is_out_of_ten_thousand(folder, roll, dropped):
    dog = world_with_dog(folder, [drop(2, chance=5000)], [potion(2)])
    assert len(objects.roll_drops(dog, FixedRng(roll))) == (1 if dropped else 0)


def test_tiers_limit_who_drops(folder):
    dog = world_with_dog(folder, [drop(2, tiers=["boss"])], [potion(2)])
    rng = FixedRng(0)
    assert objects.roll_drops(dog, rng) == [] and rng.calls == 0    # 種類對不上：不骰
    dog.tier = MobTier.BOSS
    assert len(objects.roll_drops(dog, rng)) == 1


def test_drops_use_the_mobile_file_numbers(folder):
    # a.json 的 M 放 b.json 的生物：掉落表的 obj_vnum 照 b.json 的 area_number 換算
    load(folder, reset_list=[M(201, 1)])
    load(folder, [mob(1, [drop(2), drop(150)])], [potion(2)], name="b.json", area_number=200)
    zones.load(folder)
    [npc] = [c for c in characters if isinstance(c, Npc)]
    assert [line["obj_vnum"] for line in npc.drops] == [202, 150]


def test_drop_of_missing_object_is_skipped(folder, caplog):
    dog = world_with_dog(folder, [drop(9)])
    with caplog.at_level(logging.WARNING):
        assert objects.roll_drops(dog) == []
    assert "做不出物品 109" in caplog.text


# ---- 屍體 ----

def test_corpse_holds_the_drops(folder):
    dog = world_with_dog(folder, [drop(2)], [potion(2)])
    room = dog.room
    room.contents.append(objects.Obj("石頭", "一顆石頭在這裡。", 13, ["stone"]))
    corpse = objects.make_corpse(dog, FixedRng(0))
    assert room.contents[0] is corpse                               # 新的在前面（照 C 版）
    assert (corpse.name, corpse.long, corpse.keywords) == ("野狗的屍體", "野狗的屍體橫躺在地上。", ["corpse", "屍體"])
    assert (corpse.item_type, corpse.level, corpse.timer) == (CORPSE_NPC_ITEM_TYPE, 5, 10)
    assert [o.name for o in corpse.contains] == ["治療藥水"]


def test_corpse_timer_is_ten_to_fourteen(folder):
    dog = world_with_dog(folder)
    timers = {objects.make_corpse(dog, random.Random(seed)).timer for seed in range(200)}
    assert timers == set(range(10, 15))


# ---- slay ----

def test_slay_is_an_imm_command():
    assert commands.find("slay") is None
    assert commands.find("sla", is_imm=True) is imm.do_slay
    assert commands.find("sl", is_imm=True) is system.do_sleep      # 原本的縮寫不變
    assert commands.find("s", is_imm=True) is system.do_south


def test_slay_leaves_a_corpse(folder):
    dog = world_with_dog(folder, [drop(2)], [potion(2)])
    room = dog.room
    shabu, ming = player("Shabu", room, is_imm=True), player("Ming", room)
    commands.command(shabu, "slay dog")
    assert text_of(shabu) == "你相當殘酷地屠殺(Slay)野狗，他變成一堆的肉塊與血水!!\r\n\r\n> "
    assert text_of(ming) == "\r\nShabu相當殘酷地屠殺(Slay)野狗，他變成一堆的肉塊與血水!!\r\n\r\n> "
    assert dog not in characters
    assert [o.name for o in corpse_in(room).contains] == ["治療藥水"]


def test_slay_by_chinese_name(folder):
    dog = world_with_dog(folder)
    shabu = player("Shabu", dog.room, is_imm=True)
    commands.command(shabu, "slay 野狗")
    assert dog not in characters


@pytest.mark.parametrize("arg, want", [
    ("", "你想要屠殺(Slay)誰？"),
    ("cat", "找不到你想要屠殺的人。"),
    ("shabu", "屠殺(Slay)無法對自己使用。"),
    ("ming", "玩家的死亡還沒做，現在只能屠殺生物。"),
])
def test_slay_mistakes(folder, arg, want):
    dog = world_with_dog(folder)
    shabu = player("Shabu", dog.room, is_imm=True)
    player("Ming", dog.room)
    commands.command(shabu, f"slay {arg}".strip())
    assert text_of(shabu) == f"{want}\r\n\r\n> "
    assert dog in characters and dog.room.contents == []


def test_slay_needs_the_same_room(folder):
    dog = world_with_dog(folder)
    shabu = player("Shabu", zones.world.rooms[102], is_imm=True)
    commands.command(shabu, "slay dog")
    assert text_of(shabu) == "找不到你想要屠殺的人。\r\n\r\n> "


def test_not_imm_typing_slay_is_unknown(folder):
    dog = world_with_dog(folder)
    ming = player("Ming", dog.room)
    commands.command(ming, "slay dog")
    assert text_of(ming) == "什麼？\r\n\r\n> "
    assert dog in characters


def test_death_stops_the_fight(folder):
    dog = world_with_dog(folder)
    shabu, ming = player("Shabu", dog.room, is_imm=True), player("Ming", dog.room)

    async def main():
        fight.start_fight(ming, dog)
        commands.command(shabu, "slay dog")
        # loop 結束時戰鬥本來就會被停掉，所以要在 loop 還在的時候看
        return ming.fighting, ming.fight, ming.position

    assert asyncio.run(main()) == (None, None, Position.STANDING)


def test_slain_mobile_comes_back_at_the_next_reset(folder):
    dog = world_with_dog(folder)
    death.die(dog)
    resets.reset_area(zones.world, zones.world.areas[0], resets.mobiles)
    [again] = [c for c in characters if isinstance(c, Npc)]
    assert again is not dog and again.room is dog.room


# ---- look ----

def test_look_shows_the_corpse_after_players(folder):
    dog = world_with_dog(folder)
    shabu, ming = player("Shabu", dog.room, is_imm=True), player("Ming", dog.room)
    death.die(dog)
    assert system.look(shabu).endswith(
        "\n\n" + colorize("{W") + "Ming站在這裡。" + colorize("{x") + "\n"
        + colorize("{W") + "野狗的屍體橫躺在地上。/" + colorize("{C") + "corpse" + colorize("{x") + "\n")   # 描述亮白，英文名字亮青
    characters.remove(ming)
    assert re.sub(r"\x1b\[[0-9;]*m", "", system.look(shabu)).endswith("\n\n野狗的屍體橫躺在地上。/corpse\n")   # 只有屍體也空一行


def test_look_in_corpse(folder):
    dog = world_with_dog(folder, [drop(2), drop(1, color="orange")], [potion(2), sword(1)])
    shabu = player("Shabu", dog.room)
    death.die(dog, random.Random(3))
    commands.command(shabu, "look in 屍體")
    text = raw(shabu)
    name = corpse_in(dog.room).contains[1].name
    assert name.endswith("長劍") and name != "長劍"                  # 隨機裝備：名稱接在前面
    assert text == ("野狗的屍體裝著：\r\n     " + colorize("{G") + "治療藥水/" + colorize("{C") + "potion" + colorize("{x") + "\r\n"
                    "     " + colorize("{y") + name + "/" + colorize("{C") + "sword" + colorize("{x") + "\r\n\r\n> ")


def test_look_in_empty_corpse(folder):
    dog = world_with_dog(folder)
    shabu = player("Shabu", dog.room)
    death.die(dog)
    commands.command(shabu, "look i corpse")                        # i、in 都算
    assert text_of(shabu) == "野狗的屍體裝著：\r\n     空無一物。\r\n\r\n> "


@pytest.mark.parametrize("line, want", [
    ("look in", "你想看些什麼東西？"),
    ("look in 箱子", "這裡沒有你想看的東西。"),
    ("look in stone", "這不是一個容器。"),
])
def test_look_in_mistakes(folder, line, want):
    dog = world_with_dog(folder)
    dog.room.contents.append(objects.Obj("石頭", "一顆石頭在這裡。", 13, ["stone"]))
    shabu = player("Shabu", dog.room)
    commands.command(shabu, line)
    assert text_of(shabu) == f"{want}\r\n\r\n> "


@pytest.mark.parametrize("color, code", [("gray", "{D"), ("white", "{W"), ("blue", "{B"), ("purple", "{M"),
                                         ("orange", "{y"), (None, "{G")])
def test_name_colors(color, code):
    o = objects.Obj("長劍", "", 5, ["long", "sword", "長劍"])
    o.color = color
    # 名字照顏色，後面接 keywords 裡的英文字（亮青，照 C 版）
    assert objects.short(o) == colorize(code) + "長劍/" + colorize("{C") + "long sword" + colorize("{x")


def test_name_without_english_keywords():
    assert objects.short(objects.Obj("長劍", "", 5, ["長劍"])) == colorize("{G") + "長劍" + colorize("{x")


# ---- 屍體消失 ----

def test_corpse_rots_away_with_everything_inside(folder, monkeypatch):
    monkeypatch.setattr(zones, "OBJ_TICKS", 1)
    dog = world_with_dog(folder, [drop(2)], [potion(2)])
    room = dog.room
    awake, asleep = player("Ming", room), player("Hua", room, Position.SLEEPING)
    death.die(dog, FixedRng(0))
    corpse_in(room).timer = 2
    zones.world.tick()                                              # 世界的屍體也會爛（在天氣、回復的 return 前面）
    assert corpse_in(room).timer == 1 and text_of(awake) == ""
    zones.world.tick()
    assert room.contents == []
    assert text_of(awake) == "\r\n野狗的屍體腐爛變成了灰塵。\r\n\r\n> "
    assert text_of(asleep) == ""


def test_two_corpses_rot_in_one_message(folder, monkeypatch):
    monkeypatch.setattr(zones, "OBJ_TICKS", 1)
    load(folder, [mob(1, short="野狗", keywords="dog"), mob(2, short="野貓", keywords="cat")], [], [M(1, 1), M(2, 1)])
    zones.load(folder)
    room = zones.world.rooms[101]
    ming = player("Ming", room)
    for npc in [c for c in characters if isinstance(c, Npc)]:
        death.die(npc, FixedRng(0))
    for corpse in room.contents:
        corpse.timer = 1
    zones.world.tick()
    # 新的在前面：野貓後死，先說；只有一個 prompt
    assert text_of(ming) == "\r\n野貓的屍體腐爛變成了灰塵。\r\n野狗的屍體腐爛變成了灰塵。\r\n\r\n> "


def test_corpse_rots_in_an_instance_with_a_player_inside(folder, monkeypatch):
    # 副本裡有人站著時 tick 會提早 return：屍體還是要爛
    monkeypatch.setattr(zones, "OBJ_TICKS", 1)
    write_json(folder, "world.json", make_area("world.json", [make_room(1)], 100))
    load(folder, [mob(1, short="野狗", keywords="dog")], [], [M(1, 1)], name="inst.json", area_number=300, kind="instance")
    zones.load(folder)

    async def main():
        return zones.instance("inst.json", "Ming")

    zone = asyncio.run(main())
    room = zone.rooms[301]
    ming = player("Ming", room)
    [dog] = [c for c in characters if isinstance(c, Npc)]
    death.die(dog, FixedRng(0))
    corpse_in(room).timer = 1
    zone.tick()
    assert room.contents == [] and "野狗的屍體腐爛變成了灰塵。" in text_of(ming)


# ---- 區域物件 ----

def test_corpse_goes_away_with_a_released_dynamic_area(folder):
    w = make_room(1)
    w["exits"]["north"] = {"description": "", "keywords": "", "locks": 0, "key": -1, "to_room": 201}
    write_json(folder, "world.json", make_area("world.json", [w], 100))
    load(folder, [mob(1, short="野狗", keywords="dog")], [], [M(1, 1)], name="dyn.json", area_number=200, kind="dynamic")
    zones.load(folder)
    room = zones.room_at(zones.world.rooms[101], 201)               # 走進去才建立
    [dog] = [c for c in characters if isinstance(c, Npc)]
    death.die(dog)
    assert room.contents
    zones.release(room.zone)
    again = zones.room_at(zones.world.rooms[101], 201)
    assert again is not room and again.contents == []


def test_instances_have_their_own_corpses(folder):
    write_json(folder, "world.json", make_area("world.json", [make_room(1)], 100))
    load(folder, [mob(1, short="野狗", keywords="dog")], [], [M(1, 1)], name="inst.json", area_number=300, kind="instance")
    zones.load(folder)

    async def main():
        return zones.instance("inst.json", "小明"), zones.instance("inst.json", "阿華")

    a, b = asyncio.run(main())
    dog_a = next(c for c in characters if isinstance(c, Npc) and c.room is a.rooms[301])
    death.die(dog_a)
    assert a.rooms[301].contents and b.rooms[301].contents == []


def test_reload_clears_corpses(folder):
    dog = world_with_dog(folder)
    death.die(dog)
    zones.load(folder)
    assert zones.world.rooms[101].contents == []
