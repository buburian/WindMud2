"""put（玩家角色手冊「物品和裝備」，照 C 版 do_put）：每一句和檢查的順序、put all、地上和背包的容器、很暗、容量、綁定、存檔；
件數照舊版（容器本身不算、裡面的算，使用者 2026-11-17 選的）：撿、give、buy 的上限，從自己的袋子拿不擋，inventory 那一行；容量的存檔。
"""
import re

import pytest

import mud.commands as commands
from area_helpers import make_area, make_mobile, make_object, make_room, write_json
from mud import death, objects, save, stats, weather, zones
from mud.area import ExtraFlag, RoomFlag
from mud.characters import Position, characters
from mud.commands import REFUSALS
from mud.config import ENCODING
from mud.players import Player

SHOP = {"buy_types": [], "profit_buy": 100, "profit_sell": 100, "open_hour": 0, "close_hour": 23}


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


def mob(vnum, short, keywords, shop=None):
    m = make_mobile(vnum)
    m.update(short=short, keywords=keywords, shop=shop, level=10, act=2, position=7, tier_roll=None, drops=[],
             special=None, long="")
    return m


def item(vnum, short, keywords, item_type, wear="1", values=(0, 0, 0, 0), weight=1, extra=0):
    o = make_object(vnum)
    o.update(short=short, keywords=keywords, item_type=item_type, wear_flags=wear, values=list(values), weight=weight,
             extra_flags=extra, cost=1, affects=[], extra_descriptions=[], script=None)
    return o


@pytest.fixture
def world(tmp_path, monkeypatch):
    """101：店主（賣石頭）、野狗；102：很暗。物品 120 石頭（重 1）、121 袋子（容量 3）、122 箱子（地上的，容量 100，可以關）、
    123 拾取後綁定的戒指。"""
    monkeypatch.setattr(weather, "current", weather.Weather(hour=12))
    saved = []
    monkeypatch.setattr(save, "save_player", saved.append)
    rooms = [make_room(101), make_room(102)]
    rooms[1]["room_flags"] = int(RoomFlag.DARK)
    objs = [item(120, "石頭", "stone", 13), item(121, "袋子", "bag", 15, values=(3, 0, 0, 0)),
            item(122, "箱子", "box", 15, wear="0", values=(100, 1, -1, 0), weight=50),
            item(123, "金戒", "gold", 9, wear="1|2", extra=int(ExtraFlag.BIND_PICKUP))]
    resets = [{"cmd": "M", "rare": 0, "mob_vnum": 101, "limit": 1, "room_vnum": 101, "comment": ""},
              {"cmd": "G", "rare": 0, "obj_vnum": 120, "color": None, "level": 1, "limit": 0, "comment": ""},
              {"cmd": "M", "rare": 0, "mob_vnum": 102, "limit": 1, "room_vnum": 101, "comment": ""}]
    write_json(tmp_path, "a.json", make_area("a.json", rooms, (100, 199), objects=objs, resets=resets,
                                             mobiles=[mob(101, "店主", "keeper", SHOP), mob(102, "野狗", "dog")]))
    zones.load(tmp_path)
    yield saved
    characters.clear()
    zones.stop()


def person(name, room=101, race=stats.Race.ELF):
    p = Player(name, FakeWriter(), zones.world.rooms[room])
    p.race, p.guild = race, stats.Guild.SWORD
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.skills = []
    stats.set_level(p, 10)
    p.gold = 1000
    p.page_lines = 60                       # 35 件的 inventory 不要分頁
    characters.append(p)
    return p


def plain(p):
    text = re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))
    p.writer.data = b""
    return text


def say(p, line):
    plain(p)
    commands.command(p, line)
    return plain(p).rsplit("\r\n\r\n", 1)[0]


def carry(p, vnum, n=1):
    made = [objects.create(vnum, 1, None) for _ in range(n)]
    p.carrying[:0] = made
    return made[0]


def on_floor(vnum, room=101):
    obj = objects.create(vnum, 1, None)
    zones.world.rooms[room].contents.insert(0, obj)
    return obj


# ---- put ----

def test_put_into_a_bag(world):
    ming, hua = person("Ming"), person("Hua")
    bag = carry(ming, 121)
    stone = carry(ming, 120)
    plain(hua)
    assert say(ming, "put stone bag") == "你把【石頭/stone】放進【袋子/bag】裡面。"
    assert "Ming把【石頭/stone】放進【袋子/bag】裡面。" in plain(hua)
    assert bag.contains == [stone] and ming.carrying == [bag]
    assert world == [ming]                                             # 放完存檔（照 C 版）


def test_put_into_a_box_on_the_floor(world):
    ming, hua = person("Ming"), person("Hua")
    box = on_floor(122)
    carry(ming, 120)
    say(ming, "put stone box")
    assert ming.carrying == [] and [o.vnum for o in box.contains] == [120]
    assert "石頭/stone" in say(hua, "look in box")
    assert say(hua, "get stone box") == "你把【石頭/stone】從【箱子/box】拿出來。"


@pytest.mark.parametrize("line, want", [
    ("put", "你想把什麼東西放進容器裡？"),
    ("put stone", "你想把什麼東西放進容器裡？"),
    ("put stone all", "你不能這樣作。"),
    ("put stone chest", "這兒沒有【chest】。"),
    ("put bag stone", "那不是個容器。"),
    ("put sword bag", "你沒有這個物品。"),
    ("put bag bag", "你不能把物品塞進它自己裡面。"),
])
def test_mistakes(world, line, want):
    ming = person("Ming")
    carry(ming, 121)
    carry(ming, 120)
    assert say(ming, line) == want
    assert world == []                                                 # 沒放就不存檔


def test_corpses_are_not_containers(world):
    ming = person("Ming")
    carry(ming, 120)
    death.die(next(c for c in characters if getattr(c, "vnum", None) == 102))
    assert say(ming, "put stone corpse") == "那不是個容器。"


def test_closed(world):
    ming = person("Ming")
    on_floor(122)
    carry(ming, 120)
    say(ming, "close box")
    assert say(ming, "put stone box") == "【箱子/box】關起來了。"


def test_dark_floor(world):
    ming = person("Wang", 102, race=stats.Race.HUMAN)                  # 精靈有夜視，看得到
    on_floor(122, 102)
    carry(ming, 120)
    assert say(ming, "put stone box") == "這兒沒有【box】。"
    carry(ming, 121)
    assert say(ming, "put stone bag") == "你把【石頭/stone】放進【袋子/bag】裡面。"     # 背包裡的照樣找得到


def test_capacity(world):
    ming = person("Ming")
    bag = carry(ming, 121)                                             # 容量 3
    carry(ming, 120, 4)
    for _ in range(3):
        say(ming, "put stone bag")
    assert len(bag.contains) == 3                                      # 剛好 3 放得進去
    assert say(ming, "put stone bag") == "它塞不進去。"


def test_bound_things_stay_out(world):
    ming = person("Ming")
    on_floor(122)
    carry(ming, 123)
    assert say(ming, "put gold box") == "你無法把它放進去。"
    bag = carry(ming, 121)
    bag.contains.append(objects.create(123, 1, None))
    assert say(ming, "put bag box") == "你無法把它放進去。"            # 裝著綁住的東西的容器也不行


def test_put_all(world):
    ming = person("Ming")
    bag = carry(ming, 121)
    carry(ming, 123)
    carry(ming, 120, 4)
    assert say(ming, "put all bag") == "\r\n".join(["你把【石頭/stone】放進【袋子/bag】裡面。"] * 3)
    assert len(bag.contains) == 3 and sorted(o.vnum for o in ming.carrying) == [120, 121, 123]
    assert say(ming, "put all bag") == "你沒有可以放進去的東西。"     # 第 4 顆塞不進去、戒指綁住、袋子自己：靜靜跳過
    assert world == [ming]


def test_needs_to_be_awake(world):
    ming = person("Ming")
    ming.position = Position.SLEEPING
    assert say(ming, "put stone bag") == REFUSALS[Position.SLEEPING]


# ---- 件數（照舊版）----

def test_count(world):
    bag = objects.create(121, 1, None)
    assert objects.count(bag) == 0 and objects.count(objects.create(120, 1, None)) == 1
    bag.contains = [objects.create(120, 1, None) for _ in range(3)]
    inner = objects.create(121, 1, None)
    inner.contains = [objects.create(120, 1, None)]
    bag.contains.append(inner)
    assert objects.count(bag) == 4                                     # 袋子裡的袋子也一樣：本身不算，裡面的算


def full(p):
    """p 剛好 35 件：袋子裡 2 顆、外面 33 顆。"""
    bag = carry(p, 121)
    bag.contains = [objects.create(120, 1, None) for _ in range(2)]
    carry(p, 120, 33)
    return bag


def test_inventory_counts_inside(world):
    ming = person("Ming")
    full(ming)
    assert "（35/35 件，" in say(ming, "inventory")


def test_full_means_full(world):
    ming, hua = person("Ming"), person("Hua")
    full(ming)
    on_floor(120)
    assert say(ming, "get stone") == "【石頭/stone】你不能攜帶這麼多的物品。"
    carry(hua, 120)
    assert say(hua, "give stone ming") == "Ming沒辦法攜帶這麼多的物品。"
    assert say(ming, "buy stone") == "你沒有辦法攜帶這麼多的物品。"
    on_floor(121)
    assert say(ming, "get bag") == "你拿起了【袋子/bag】。"            # 空袋子是 0 件


def test_taking_out_of_your_own_bag_is_never_too_much(world):
    ming = person("Ming")
    full(ming)
    assert say(ming, "get stone bag") == "你把【石頭/stone】從【袋子/bag】拿出來。"   # 件數、負重都沒變（C 版會擋）
    assert say(ming, "get all bag") == "你把【石頭/stone】從【袋子/bag】拿出來。"
    assert "（35/35 件，" in say(ming, "inventory")


# ---- 存檔 ----

def test_holds_is_saved(world):
    bag = objects.create(121, 1, None)
    bag.holds = 7
    assert objects.from_data(objects.to_data(bag)).holds == 7


def test_old_saves(world):
    data = objects.to_data(objects.create(121, 1, None))
    del data["holds"]
    assert objects.from_data(data).holds == 3                          # 照區域檔現在的值
    del objects.protos[121]
    assert objects.from_data(data).holds == 0                          # 區域檔沒有這件了：放不進東西
    stone = objects.to_data(objects.create(120, 1, None))
    del stone["holds"]
    assert objects.from_data(stone).holds is None                      # 不是容器
