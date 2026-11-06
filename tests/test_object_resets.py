"""重置 G、O、P、R（區域製作手冊 resets 那章，照 C 版 db.c），生物身上的東西進屍體（店主的消失），test.json 載入後的樣子。"""
import logging
from pathlib import Path

import pytest

from area_helpers import make_area, make_mobile, make_object, make_room, write_json
from mud import death, objects, resets, zones
from mud.characters import Position, characters
from mud.npcs import Npc
from mud.players import Player

AREAS = Path(__file__).resolve().parent.parent / "areas"


class FixedRng:
    """假的亂數：randrange 一律回傳 n；randint 一律回傳 high 是 True 時的最大值、不然最小值；隨機裝備用 0.5。"""

    def __init__(self, n=0, high=False):
        self.n, self.high = n, high

    def randrange(self, _):
        return self.n

    def randint(self, a, b):
        return b if self.high else a

    def uniform(self, a, b):
        return (a + b) / 2

    def random(self):
        return 0.5

    def choice(self, seq):
        return seq[0]


@pytest.fixture
def folder(tmp_path):
    yield tmp_path
    characters.clear()
    zones.stop()


def mob(vnum, shop=None, **fields):
    m = make_mobile(vnum)
    m.update(position=7, tier_roll=None, act=0, drops=[], shop=shop, long=f"生物{vnum}在這裡晃來晃去。\n")
    m.update(fields)
    return m


def obj(vnum, short, keywords, item_type, values, wear="1"):
    o = make_object(vnum)
    o.update(short=short, keywords=keywords, item_type=item_type, values=values, wear_flags=wear, affects=[], weight=1)
    return o


OBJECTS = [obj(1, "藥水", "potion", 10, [5, "cure light", "", ""]), obj(2, "箱子", "box", 15, [50, 1, -1, 0]),
           obj(3, "麵包", "bread", 19, [10, 0, 0, 0]), obj(4, "長劍", "sword", 5, [2, 0, 0, 3], "1|8192")]


def M(mob_vnum, room_vnum, limit=1, rare=0):
    return {"cmd": "M", "rare": rare, "mob_vnum": mob_vnum, "limit": limit, "room_vnum": room_vnum, "comment": ""}


def G(obj_vnum, level=None, color=None, rare=0):
    return {"cmd": "G", "rare": rare, "obj_vnum": obj_vnum, "color": color, "level": level, "limit": 0, "comment": ""}


def O(obj_vnum, room_vnum, level=1):
    return {"cmd": "O", "if_flag": 0, "obj_vnum": obj_vnum, "color": None, "level": level, "limit": 0, "room_vnum": room_vnum, "comment": ""}


def P(obj_vnum, container_vnum, level=1):
    return {"cmd": "P", "if_flag": 0, "obj_vnum": obj_vnum, "color": None, "level": level, "limit": 0,
            "container_vnum": container_vnum, "comment": ""}


def load(folder, reset_list, mobiles=(), rooms=None, rng=None):
    rooms = rooms or [make_room(1, north=2), make_room(2, south=1)]
    write_json(folder, "a.json", make_area("a.json", rooms, 100, mobiles=list(mobiles), resets=reset_list, objects=OBJECTS))
    zones.load(folder)
    return zones.world.areas[0]


def again(area, rng=None):
    resets.reset_area(zones.world, area, resets.mobiles, rng or FixedRng())


def npcs():
    return [c for c in characters if isinstance(c, Npc)]


def names(objs):
    return [o.name for o in objs]


# ---- G ----

def test_give_to_the_mobile_just_placed(folder):
    load(folder, [M(1, 1), G(1), G(4, level=7, color="white")], [mob(1, level=5)])
    [m] = npcs()
    potion, sword = m.carrying[1], m.carrying[0]
    assert (potion.name, potion.level) == ("藥水", 5)                     # level 是 null：生物的等級
    assert (sword.name.endswith("長劍"), sword.level, sword.color) == (True, 7, "white")


def test_give_only_when_the_mobile_was_placed(folder):
    # 第二次重置：生物已經滿了（limit 1），M 沒放出來，後面的 G 也不做
    area = load(folder, [M(1, 1), G(1)], [mob(1)])
    again(area)
    [m] = npcs()
    assert names(m.carrying) == ["藥水"]


@pytest.mark.parametrize("roll, given", [(0, True), (4999, True), (5000, False)])
def test_give_rare(folder, roll, given):
    area = load(folder, [M(1, 1), G(1, rare=5010)], [mob(1)])         # 大約 50%
    for m in npcs():
        characters.remove(m)
    again(area, FixedRng(roll))
    [m] = npcs()
    assert (m.carrying != []) is given


# ---- O ----

def test_object_on_the_floor_once(folder):
    area = load(folder, [O(2, 2)])
    room = zones.world.rooms[102]
    assert names(room.contents) == ["箱子"]
    again(area)
    assert names(room.contents) == ["箱子"]                               # 已經有了不再放


def test_object_waits_until_nobody_is_around(folder):
    area = load(folder, [O(2, 2)])
    room = zones.world.rooms[102]
    room.contents.clear()
    p = Player("Ming", None, zones.world.rooms[101])                       # 區域檔的房間裡有玩家：不放
    characters.append(p)
    again(area)
    assert room.contents == []
    characters.remove(p)
    again(area)
    assert names(room.contents) == ["箱子"]


# ---- P ----

def test_put_into_the_container(folder):
    area = load(folder, [O(2, 2), P(3, 2)])
    [box] = zones.world.rooms[102].contents
    assert names(box.contains) == ["麵包"]
    again(area)
    assert names(box.contains) == ["麵包"]                                # 已經有了不再放
    box.contains.clear()
    p = Player("Ming", None, zones.world.rooms[102])                       # 有玩家也放（照 WindSrc）
    characters.append(p)
    again(area)
    assert names(box.contains) == ["麵包"]


def test_put_into_a_container_a_mobile_carries(folder):
    load(folder, [M(1, 1), G(2), P(3, 2)], [mob(1)])
    [m] = npcs()
    assert names(m.carrying[0].contains) == ["麵包"]


def test_put_without_a_container(folder, caplog):
    with caplog.at_level(logging.WARNING):
        load(folder, [P(3, 2)])
    assert "沒有容器 102" in caplog.text


# ---- R ----

def test_randomize_exits(folder):
    rooms = [make_room(1, north=2, east=3), make_room(2, south=1), make_room(3, west=1)]
    rooms[0]["exits"]["north"].update(description="往北看。", locks=1, keywords="木門 door")
    rooms[1]["exits"]["south"].update(locks=1, keywords="木門 door")
    r = {"cmd": "R", "if_flag": 0, "room_vnum": 1, "exit_count": 2, "comment": ""}
    area = load(folder, [], rooms=rooms)
    room = zones.world.rooms[101]
    again(area, FixedRng())                                               # 亂數取最小：自己跟自己換，不變
    area.data["resets"] = [r]
    again(area, FixedRng())
    assert room.exits == {"north": 102, "east": 103}
    again(area, FixedRng(high=True))                                      # 亂數取最大：北、東對調
    assert room.exits == {"north": 103, "east": 102}
    assert set(room.doors) == {"east"} and room.exit_descriptions.get("east") == "往北看。"
    assert "north" not in room.exit_descriptions or room.exit_descriptions["north"] == ""


# ---- 生物身上的東西、死掉 ----

def test_carried_things_go_into_the_corpse(folder):
    load(folder, [M(1, 1), G(1)], [mob(1)])
    [m] = npcs()
    death.die(m)
    [corpse] = zones.world.rooms[101].contents
    assert names(corpse.contains) == ["藥水"]


def test_shopkeepers_things_are_gone(folder):
    # 照 C 版：店主身上的東西不放進屍體（防止殺店主複製東西，使用者選的）
    shop = make_mobile(1)["shop"]
    load(folder, [M(1, 1), G(1)], [mob(1, shop=shop)])
    [m] = npcs()
    assert m.shopkeeper and names(m.carrying) == ["藥水"]
    death.die(m)
    [corpse] = zones.world.rooms[101].contents
    assert corpse.contains == []


# ---- test.json ----

def test_the_test_area(folder):
    zones.load(AREAS)
    merchant = next(c for c in npcs() if c.name == "測試商人")
    assert sorted(names(merchant.carrying)) == ["測試藥水", "測試長劍"]       # G
    [box] = [o for o in zones.world.rooms[102].contents if o.vnum == 103]  # O
    assert names(box.contains) == ["測試麵包"]                                # P
    assert merchant.position == Position.STANDING


def test_give_follows_the_nearest_m(folder):
    # 第二筆 M 沒放出來（已經 1 隻了），後面的 G 是跟著它的：不做，也不能給到第一筆 M 的那隻
    load(folder, [M(1, 1), M(1, 1), G(1)], [mob(1)])
    [m] = npcs()
    assert m.carrying == []
