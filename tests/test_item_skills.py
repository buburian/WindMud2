"""會放技能的物品（commands/item_skills.py，設計文件 §3.8）：quaff、recite、zap、brandish 的每一句、等級不夠和對象不對都不用掉、
沒寫對象看技能種類、不扣消耗不設冷卻、次數和碎掉、brandish 放給每個人（很暗看不到的不算）、安全區、存檔、區域檔檢查。
"""
import asyncio
import re

import pytest

import mud.commands as commands
from area_helpers import make_area, make_mobile, make_object, make_room, write_json
from mud import affects, area, combat, fight, objects, stats, weather, zones
from mud.area import AffectFlag, RoomFlag
from mud.characters import characters
from mud.config import ENCODING
from mud.npcs import Npc
from mud.players import Player


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


class Always:
    def __init__(self, x):
        self.x = x

    def random(self):
        return self.x


def item(vnum, item_type, values, wear="1"):
    o = make_object(vnum)
    o.update(short=f"物品{vnum}", keywords=f"thing{vnum}", item_type=item_type, wear_flags=wear, values=list(values),
             affects=[], extra_descriptions=[], script=None)
    return o


HOLD = "1|16384"
ITEMS = {
    "fly_potion": item(101, 10, (1, "fly", "", "")),
    "smash_potion": item(102, 10, (1, "smash", "", "")),
    "buff_scroll": item(103, 2, (1, "fly", "breathe", "")),
    "smash_scroll": item(104, 2, (1, "smash", "", "")),
    "breathe_wand": item(105, 3, (0, 2, 2, "breathe"), HOLD),
    "smash_wand": item(106, 3, (0, 1, 1, "smash"), HOLD),
    "fly_staff": item(107, 4, (0, 1, 1, "fly"), HOLD),
    "smash_staff": item(108, 4, (0, 2, 2, "smash"), HOLD),
    "empty_wand": item(109, 3, (0, 3, 0, "fly"), HOLD),
}
VNUM = {k: o["vnum"] for k, o in ITEMS.items()}


@pytest.fixture
def world(tmp_path, monkeypatch):
    """101（有兩隻狗）—北— 102 安全區（一隻狗）；103 很暗（一隻狗）。"""
    monkeypatch.setattr(fight, "TICK_SECONDS", 1000)
    monkeypatch.setattr(combat, "rng", Always(0.5))
    monkeypatch.setattr(weather, "current", weather.Weather(hour=12))
    rooms = [make_room(101, north=102), make_room(102, south=101), make_room(103)]
    rooms[1]["room_flags"], rooms[2]["room_flags"] = int(RoomFlag.SAFE), int(RoomFlag.DARK)
    dog = make_mobile(101)
    dog.update(short="野狗", keywords="dog", act=2, position=7, drops=[], special=None, shop=None, long="", level=1)
    resets = [{"cmd": "M", "rare": 0, "mob_vnum": 101, "limit": 9, "room_vnum": v, "comment": ""} for v in (101, 101, 102, 103)]
    write_json(tmp_path, "a.json", make_area("a.json", rooms, (100, 199), mobiles=[dog], objects=list(ITEMS.values()),
                                             resets=resets))
    zones.load(tmp_path)
    yield zones.world
    characters.clear()
    zones.stop()


def person(name, room=101, level=10):
    p = Player(name, FakeWriter(), zones.world.rooms[room])
    p.race, p.guild = stats.Race.HUMAN, stats.Guild.SWORD
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.skills = []
    stats.set_level(p, level)
    p.hp, p.mp, p.mv = p.panel["hp"], p.panel["mp"], p.panel["mv"]
    characters.append(p)
    return p


def give(p, key, level=1):
    obj = objects.create(VNUM[key], level, None)
    p.carrying.insert(0, obj)
    return obj


def hold(p, key, level=1):
    obj = objects.create(VNUM[key], level, None)
    p.equipment["hold"] = obj
    return obj


def plain(p):
    text = re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))
    p.writer.data = b""
    return text


def say(p, line):
    plain(p)
    commands.command(p, line)
    return plain(p).rsplit("\r\n\r\n", 1)[0]


def dogs(room=101):
    return [c for c in characters if isinstance(c, Npc) and c.room.vnum == room]


def flying(p):
    return affects.has_flag(p, AffectFlag.FLYING)


# ---- quaff ----

@pytest.mark.parametrize("line, message", [("quaff", "你想要服下什麼樣的藥水？"), ("quaff xyz", "你沒有這種藥水。"),
                                           ("quaff thing103", "你只能服下藥水。")])
def test_quaff_refusals(world, line, message):
    ming = person("Ming")
    give(ming, "buff_scroll")
    assert say(ming, line) == message


def test_quaff(world):
    ming, wang = person("Ming"), person("Wang")
    potion = give(ming, "fly_potion")
    text = say(ming, "quaff thing101")
    assert text.startswith("你服下了【物品101/thing101】。") and "你對自己施展了【飛翔術】。" in text
    assert "Ming服下(Quaff)了【物品101/thing101】。" in plain(wang)
    assert flying(ming) and potion not in ming.carrying


def test_too_low_is_not_used(world):
    ming = person("Ming", level=10)
    potion = give(ming, "fly_potion", level=20)
    assert say(ming, "quaff thing101") == "你至少等級(Level)要達到【20】級以上才能使用這項物品。"
    assert potion in ming.carrying and not flying(ming)


def test_a_damage_potion_is_refused(world):
    ming = person("Ming")
    potion = give(ming, "smash_potion")
    assert say(ming, "quaff thing102") == "你不可以攻擊玩家。"
    assert potion in ming.carrying


# ---- recite ----

@pytest.mark.parametrize("line, message", [("recite", "你沒有這種卷軸。"), ("recite thing101", "你只能朗讀卷軸(Scroll)。"),
                                           ("recite thing103 nobody", "你找不到你想要閱讀的捲軸。")])
def test_recite_refusals(world, line, message):
    ming = person("Ming")
    give(ming, "fly_potion")
    give(ming, "buff_scroll")
    assert say(ming, line) == message


def test_recite_buffs_on_yourself_by_default(world):
    ming = person("Ming")
    scroll = give(ming, "buff_scroll")
    assert say(ming, "recite thing103").startswith("你朗讀著【物品103/thing103】。")
    assert flying(ming) and affects.has_flag(ming, AffectFlag.GILLS) and scroll not in ming.carrying


def test_recite_on_another_player(world):
    ming, wang = person("Ming"), person("Wang")
    give(ming, "buff_scroll")
    say(ming, "recite thing103 wang")
    assert flying(wang) and not flying(ming)


def test_a_buff_on_a_creature_is_refused_and_kept(world):
    ming = person("Ming")
    scroll = give(ming, "buff_scroll")
    assert say(ming, "recite thing103 dog") == "飛翔術只能放在玩家身上。"
    assert scroll in ming.carrying


def test_a_damage_scroll_needs_a_target(world):
    ming = person("Ming")
    scroll = give(ming, "smash_scroll")
    assert say(ming, "recite thing104") == "你想要攻擊誰？"
    assert scroll in ming.carrying


def test_a_damage_scroll_starts_a_fight_and_costs_nothing(world):
    ming = person("Ming")
    give(ming, "smash_scroll")
    mv = ming.mv

    async def main():
        text = say(ming, "recite thing104 dog")
        return text, ming.fighting

    text, fighting = asyncio.run(main())
    assert "你朗讀著【物品104/thing104】。" in text and "重擊" in text
    assert isinstance(fighting, Npc)
    assert ming.mv == mv and ming.cooldowns == {}               # 不扣消耗、沒有冷卻


def test_safe_room_keeps_the_scroll(world):
    ming = person("Ming", 102)
    scroll = give(ming, "smash_scroll")
    assert say(ming, "recite thing104 dog") == "野狗正在受到神力所保護的房間內。"
    assert scroll in ming.carrying


# ---- zap ----

def test_zap_needs_a_wand_in_hand(world):
    ming = person("Ming")
    assert say(ming, "zap") == "你手上沒有握著任何東西可以拿來甩動。"
    hold(ming, "fly_staff")
    assert say(ming, "zap") == "你只能夠甩動著魔杖(Wand)。"
    hold(ming, "breathe_wand")
    assert say(ming, "zap nobody") == "你找不到你想甩動的魔杖(Wand)。"


def test_zap_a_buff_on_yourself_until_it_breaks(world):
    ming, wang = person("Ming"), person("Wang")
    wand = hold(ming, "breathe_wand")
    assert say(ming, "zap").startswith("你對著你自己甩動(Zap)【物品105/thing105】。")
    assert "Ming對著他自己甩動(Zap)【物品105/thing105】。" in plain(wang)
    assert affects.has_flag(ming, AffectFlag.GILLS) and wand.charges == 1
    assert "你的【物品105/thing105】爆炸成了一堆的碎片。" in say(ming, "zap")
    assert "hold" not in ming.equipment


def test_an_empty_wand_just_breaks(world):
    ming = person("Ming")
    hold(ming, "empty_wand")
    assert say(ming, "zap") == "你的【物品109/thing109】爆炸成了一堆的碎片。"
    assert not flying(ming) and "hold" not in ming.equipment


def test_a_damage_wand_asks_out_of_a_fight_and_hits_the_opponent_in_one(world):
    ming = person("Ming")
    wand = hold(ming, "smash_wand")
    assert say(ming, "zap") == "你想要甩動些什麼？"
    assert wand.charges == 1

    async def main():
        fight.start_fight(ming, dogs()[0])
        return say(ming, "zap")

    text = asyncio.run(main())
    assert "你對著野狗甩動(Zap)" in text and "爆炸成了一堆的碎片" in text


def test_too_low_keeps_the_charge(world):
    ming = person("Ming", level=5)
    wand = hold(ming, "breathe_wand", level=9)
    assert say(ming, "zap") == "你至少等級(Level)要達到【9】級以上才能使用這項物品。"
    assert wand.charges == 2


# ---- brandish ----

def test_brandish_buffs_every_visible_player(world):
    ming, wang = person("Ming"), person("Wang")
    hold(ming, "fly_staff")
    text = say(ming, "brandish")
    assert text.startswith("你揮舞著【物品107/thing107】。")
    assert "【物品107/thing107】燃燒起來射出陣陣光芒後消失不見了。" in text
    assert flying(ming) and flying(wang)


def test_brandish_in_the_dark_reaches_only_yourself(world):
    ming, wang = person("Ming", 103), person("Wang", 103)
    hold(ming, "fly_staff")
    say(ming, "brandish")
    assert flying(ming) and not flying(wang)


def test_brandish_hits_every_creature(world):
    ming = person("Ming")
    staff = hold(ming, "smash_staff")

    async def main():
        say(ming, "brandish")
        return [d.fighting for d in dogs()]

    assert all(f is ming for f in asyncio.run(main()))
    assert staff.charges == 1


def test_brandish_damage_in_a_safe_room_keeps_the_charge(world):
    ming = person("Ming", 102)
    staff = hold(ming, "smash_staff")
    assert say(ming, "brandish") == "野狗正在受到神力所保護的房間內。"
    assert staff.charges == 2


def test_brandish_needs_a_staff(world):
    ming = person("Ming")
    assert say(ming, "brandish") == "你手上沒有握著任何東西可以拿來揮舞。"
    hold(ming, "breathe_wand")
    assert say(ming, "b") == "你只能拿魔棒(Staff)來揮舞。"


# ---- 物品本身 ----

def test_wands_are_held_and_take_no_affixes(world):
    wand = objects.create(VNUM["breathe_wand"], 30, "orange")
    assert wand.slot == "hold" and wand.affects == [] and wand.name == "物品105"
    assert (wand.skills, wand.charges) == (["breathe"], 2)


def test_skills_and_charges_are_saved(world):
    wand = objects.create(VNUM["breathe_wand"], 1, None)
    wand.charges = 1
    assert (objects.from_data(objects.to_data(wand)).charges) == 1
    old = objects.to_data(wand)
    del old["skills"], old["charges"]                                 # 舊存檔：照區域檔現在的值
    assert (objects.from_data(old).skills, objects.from_data(old).charges) == (["breathe"], 2)
    old["vnum"] = 199                                                 # 區域檔沒有這件了
    assert (objects.from_data(old).skills, objects.from_data(old).charges) == ([], 0)


@pytest.mark.parametrize("item_type, values, problem", [
    (10, [1, "cure light", "", ""], "values 第 2 個要寫技能的 key"),
    (2, [1, "", "", ""], "沒有寫技能（values 第 2～4 個）"),
    (3, [0, 1, 1, ""], "沒有寫技能（values 第 4 個）"),
    (4, [0, -1, 1, "fly"], "values 第 2 個（最多幾次）要是 0 以上的整數"),
    (3, [0, 1, "x", "fly"], "values 第 3 個（剩幾次）要是 0 以上的整數"),
])
def test_area_check(item_type, values, problem):
    problems = []
    area.check_skill_item("物品 1", item_type, values, problems)
    assert any(problem in p for p in problems)


def test_area_check_passes_good_items():
    problems = []
    for o in ITEMS.values():
        area.check_skill_item("物品", o["item_type"], o["values"], problems)
    assert problems == []
