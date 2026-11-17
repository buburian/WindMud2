"""吃喝（meals.py、commands/meals.py，設計文件 §3.9）：eat、drink、fill 的每一句、自動坐下、一口一口、坐滿 10 秒才回得快一倍、
站起來和開打就取消（同一秒 stand 又 rest 也算）、吃了又吃、劍之公會回 MV 杖之公會回 MP、buff、藥錠、很暗、存檔、區域檔檢查、液體表。
"""
import asyncio
import re
import subprocess
import sys
from pathlib import Path

import pytest

import mud.commands as commands
from area_helpers import make_area, make_mobile, make_object, make_room, write_json
from mud import affects, area, fight, meals, objects, stats, weather, zones
from mud.area import AffectFlag, RoomFlag
from mud.characters import Position, characters
from mud.commands import REFUSALS
from mud.config import ENCODING, MEAL_TICKS
from mud.npcs import Npc
from mud.players import Player

MANUAL = Path(__file__).resolve().parent.parent / "docs" / "區域製作手冊.md"


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


def item(vnum, item_type, values, keywords, wear="1"):
    o = make_object(vnum)
    o.update(short=f"物品{vnum}", keywords=keywords, item_type=item_type, wear_flags=wear, values=list(values),
             affects=[], extra_descriptions=[], script=None)
    return o


ITEMS = [item(101, 19, (2, "", 0, 0), "bread"), item(102, 19, (1, "fly", 0, 0), "cake"),
         item(103, 17, (3, 1, 0, 0), "skin"), item(104, 17, (2, 2, 1, 0), "beer"),
         item(105, 25, (0, 0, 0, 0), "fountain", wear="0"), item(106, 26, (1, "fly", "", ""), "pill"),
         item(107, 5, (2, 0, 0, 3), "sword", wear="1|8192")]
ITEMS[6]["affects"] = []


@pytest.fixture
def world(tmp_path, monkeypatch):
    """101 有噴泉 —北— 102 沒有噴泉；103 很暗、有噴泉。101 有一隻狗。"""
    monkeypatch.setattr(fight, "TICK_SECONDS", 1000)
    monkeypatch.setattr(weather, "current", weather.Weather(hour=12))
    rooms = [make_room(101, north=102), make_room(102, south=101), make_room(103)]
    rooms[2]["room_flags"] = int(RoomFlag.DARK)
    dog = make_mobile(101)
    dog.update(short="野狗", keywords="dog", act=2, position=7, drops=[], special=None, shop=None, long="", level=1)
    resets = [{"cmd": "M", "rare": 0, "mob_vnum": 101, "limit": 1, "room_vnum": 101, "comment": ""}]
    resets += [{"cmd": "O", "if_flag": 0, "obj_vnum": 105, "color": None, "level": 1, "limit": 1, "room_vnum": v, "comment": ""}
               for v in (101, 103)]
    write_json(tmp_path, "a.json", make_area("a.json", rooms, (100, 199), mobiles=[dog], objects=ITEMS, resets=resets))
    zones.load(tmp_path)
    yield zones.world
    characters.clear()
    zones.stop()


def person(name, room=101, guild=stats.Guild.SWORD):
    p = Player(name, FakeWriter(), zones.world.rooms[room])
    p.race, p.guild = stats.Race.HUMAN, guild
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.skills = []
    stats.set_level(p, 10)
    characters.append(p)
    return p


def give(p, vnum):
    obj = objects.create(vnum, 1, None)
    p.carrying.insert(0, obj)
    return obj


def plain(p):
    text = re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))
    p.writer.data = b""
    return text


def say(p, line):
    plain(p)
    commands.command(p, line)
    return plain(p).rsplit("\r\n\r\n", 1)[0]


def wait(n=MEAL_TICKS):
    for _ in range(n):
        meals.tick()


# ---- eat ----

@pytest.mark.parametrize("line, message", [("eat", "你想要吃些什麼呢？"), ("eat xyz", "你沒有這個東西。"),
                                           ("eat sword", "這個東西是不能夠吃的。")])
def test_eat_refusals(world, line, message):
    ming = person("Ming")
    give(ming, 107)
    assert say(ming, line) == message


def test_eat_sits_down_and_bites_one_at_a_time(world):
    ming, wang = person("Ming"), person("Wang")
    bread = give(ming, 101)
    assert say(ming, "eat bread") == "你坐下來休息。\r\n你吃下了【物品101/bread】。"
    assert ming.position == Position.RESTING and bread.bites == 1 and bread in ming.carrying
    assert "Ming坐下來休息。" in plain(wang) and True
    assert say(ming, "eat bread") == "你吃下了【物品101/bread】。"           # 已經在休息：不再坐一次
    assert bread not in ming.carrying


def test_no_eating_in_a_fight_or_asleep(world):
    ming = person("Ming")
    bread = give(ming, 101)
    ming.position = Position.SLEEPING
    assert say(ming, "eat bread") == REFUSALS[Position.SLEEPING]

    async def main():
        ming.position = Position.STANDING
        fight.start_fight(ming, next(c for c in characters if isinstance(c, Npc)))
        return say(ming, "eat bread")

    assert asyncio.run(main()) == "你正處於戰鬥狀態之中了!!"
    assert bread.bites == 2


# ---- 坐滿 10 秒 ----

def test_ten_seconds_then_hp_regenerates_twice_as_fast(world):
    ming = person("Ming")
    give(ming, 101)
    say(ming, "eat bread")
    wait(MEAL_TICKS - 1)
    assert ming.meal_bonus == {}
    wait(1)
    assert ming.meal_bonus == {"hp": 2}
    assert "你吃下的東西開始發揮作用，HP 恢復得比較快了。" in plain(ming)
    ming.hp = 1.0
    stats.regen(ming)
    assert ming.hp == pytest.approx(1 + ming.panel["hp"] * 0.40)


def test_standing_up_within_ten_seconds_cancels(world):
    ming = person("Ming")
    give(ming, 101)
    say(ming, "eat bread")
    wait(5)
    say(ming, "stand")
    say(ming, "rest")
    wait()
    assert ming.meal_bonus == {}


def test_stand_and_rest_in_the_same_second_still_cancels(world):
    ming = person("Ming")
    give(ming, 101)
    say(ming, "eat bread")
    say(ming, "stand")
    say(ming, "rest")                                               # 每秒的檢查看不到：要在 stand 的當下取消
    wait()
    assert ming.meal_bonus == {} and ming.meals == {}


def test_the_bonus_ends_when_you_stand_or_fight(world):
    ming = person("Ming")
    give(ming, 101)
    say(ming, "eat bread")
    wait()
    say(ming, "stand")
    assert ming.meal_bonus == {}
    say(ming, "eat bread")
    wait()
    assert ming.meal_bonus == {"hp": 2}

    async def main():
        fight.start_fight(next(c for c in characters if isinstance(c, Npc)), ming)
        return ming.meal_bonus

    assert asyncio.run(main()) == {}


def test_eating_again_keeps_the_bonus_and_does_not_stack(world):
    ming = person("Ming")
    give(ming, 101)
    say(ming, "eat bread")
    wait()
    say(ming, "eat bread")
    assert ming.meal_bonus == {"hp": 2} and ming.meals["eat"][0] == MEAL_TICKS
    wait()
    assert ming.meal_bonus == {"hp": 2}


@pytest.mark.parametrize("guild, key", [(stats.Guild.SWORD, "mv"), (stats.Guild.STAFF, "mp")])
def test_drinking_helps_the_guild_resource(world, guild, key):
    ming = person("Ming", guild=guild)
    give(ming, 104)
    give(ming, 101)
    say(ming, "drink beer")
    say(ming, "eat bread")                                          # 吃和喝各算各的
    wait()
    assert ming.meal_bonus == {"hp": 2, key: 2}


def test_sleeping_counts_too(world):
    ming = person("Ming")
    give(ming, 101)
    say(ming, "eat bread")
    say(ming, "sleep")
    wait()
    ming.hp = 1.0
    stats.regen(ming)
    assert ming.hp == pytest.approx(1 + ming.panel["hp"] * 0.60)


# ---- buff ----

def test_food_buff(world):
    ming = person("Ming")
    give(ming, 102)
    say(ming, "eat cake")
    wait()
    assert affects.has_flag(ming, AffectFlag.FLYING) and ming.meal_bonus == {}
    assert "你吃下的東西開始發揮作用：【飛翔術】。" in plain(ming)


def test_drink_buff_follows_the_liquid(world, monkeypatch):
    monkeypatch.setitem(area.LIQUIDS, 1, ("啤酒", "breathe"))
    ming = person("Ming")
    give(ming, 104)
    say(ming, "drink beer")
    wait()
    assert affects.has_flag(ming, AffectFlag.GILLS)


def test_pills_work_at_once_without_sitting(world):
    ming = person("Ming")
    pill = give(ming, 106)
    assert say(ming, "eat pill").startswith("你吃下了【物品106/pill】。")
    assert affects.has_flag(ming, AffectFlag.FLYING) and ming.position == Position.STANDING and pill not in ming.carrying


# ---- drink、fill ----

def test_drink_from_a_container(world):
    ming = person("Ming")
    beer = give(ming, 104)
    assert say(ming, "drink beer") == "你坐下來休息。\r\n你從【物品104/beer】中喝了點【啤酒】。"
    assert beer.amount == 1
    say(ming, "drink beer")
    assert say(ming, "drink beer") == "它已經空了。" and beer in ming.carrying


def test_drink_from_the_fountain(world):
    ming = person("Ming")
    ming.position = Position.RESTING
    assert say(ming, "drink") == "你從【物品105/fountain】裡喝清水，止渴了。"
    assert say(ming, "drink fountain") == "你從【物品105/fountain】裡喝清水，止渴了。"


@pytest.mark.parametrize("room, line, message", [(102, "drink", "你想喝些什麼？"), (101, "drink xyz", "你找不到它。"),
                                                 (101, "drink sword", "你沒有辦法喝它。"), (103, "drink", "你想喝些什麼？")])
def test_drink_refusals(world, room, line, message):
    ming = person("Ming", room)
    give(ming, 107)
    assert say(ming, line) == message                               # 103 很暗：看不到噴泉


def test_fill(world):
    ming = person("Ming")
    skin = give(ming, 103)
    assert say(ming, "fill skin") == "你把【物品103/skin】灌滿了清水。"
    assert (skin.amount, skin.liquid) == (3, 0)
    assert say(ming, "fill skin") == "你的容器已經裝滿了。"


@pytest.mark.parametrize("room, line, message", [(101, "fill", "你想拿什麼容器來裝水？"), (101, "fill xyz", "你沒有這樣東西。"),
                                                 (102, "fill skin", "這裡沒有泉水!!"), (101, "fill sword", "這個東西不是盛裝液體的容器。"),
                                                 (101, "fill beer", "這個容器已經裝了其他的液體。")])
def test_fill_refusals(world, room, line, message):
    ming = person("Ming", room)
    for vnum in (103, 104, 107):
        give(ming, vnum)
    assert say(ming, line) == message


# ---- 存檔、區域檔 ----

def test_bites_and_amounts_are_saved(world):
    bread, beer = objects.create(101, 1, None), objects.create(104, 1, None)
    bread.bites, beer.amount = 1, 0
    assert objects.from_data(objects.to_data(bread)).bites == 1
    assert objects.from_data(objects.to_data(beer)).amount == 0
    old = objects.to_data(bread)
    for k in objects.MEAL_FIELDS:
        del old[k]
    assert objects.from_data(old).bites == 2                          # 舊存檔：照區域檔現在的值


@pytest.mark.parametrize("item_type, values, problem", [
    (19, [0, "", 0, 0], "可以吃幾口）要是 1 以上的整數"),
    (19, [1, "smash", 0, 0], "values 第 2 個要寫增益技能的 key"),
    (17, [2, 3, 0, 0], "現在有多少）要是 0～2 的整數"),
    (17, [2, 1, 99, 0], "液體種類）要是 0～15"),
    (25, [0, 0, -1, 0], "液體種類）要是 0～15"),
])
def test_area_check(item_type, values, problem):
    problems = []
    area.check_meal_item("物品 1", item_type, values, problems)
    assert any(problem in p for p in problems)


def test_liquid_table_matches_the_manual():
    text = MANUAL.read_text(encoding="utf-8").split("### 液體種類", 1)[1].split("###", 1)[0]
    rows = re.findall(r"^\| (\d+) \| (\S+) \| ([^|]*) \|", text, re.M)
    assert {int(n): (name, buff.strip().strip("`").replace("—", "")) for n, name, buff in rows} == area.LIQUIDS


@pytest.mark.parametrize("module", ["mud.skills", "mud.meals", "mud.area"])
def test_each_module_imports_first(module):
    """坑：skills → affects → combat → death → fight → meals 繞一圈；areacheck 先 import 的順序不一樣，測試裡碰不到，要開新的 Python。"""
    subprocess.run([sys.executable, "-c", f"import {module}; import mud.area; mud.area.check_meal_item('x', 19, [1, '', 0, 0], [])"],
                   check=True, cwd=MANUAL.parent.parent)


def test_eat_and_drink_in_the_same_second_send_one_prompt(world):
    ming = person("Ming")
    give(ming, 101)
    give(ming, 104)
    say(ming, "eat bread")
    say(ming, "drink beer")
    wait()
    text = plain(ming)
    assert "HP 恢復得比較快了" in text and "MV 恢復得比較快了" in text
    assert text.count("<HP") == 1


def test_dying_cancels_at_once(world, monkeypatch):
    from mud import death
    monkeypatch.setattr(zones, "START_ROOM", 101)
    ming = person("Ming")
    give(ming, 101)
    say(ming, "eat bread")
    wait()
    say(ming, "eat bread")
    death.player_dies(ming)
    assert ming.meal_bonus == {} and ming.meals == {}


def test_the_tick_cancels_anything_that_got_up_another_way(world):
    ming = person("Ming")
    give(ming, 101)
    say(ming, "eat bread")
    wait()
    ming.position = Position.STANDING               # 不是 stand 指令（例如腳本、之後的新功能）
    wait(1)
    assert ming.meal_bonus == {}
