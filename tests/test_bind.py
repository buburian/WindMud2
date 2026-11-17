"""綁定（設計文件 §3.10，玩家角色手冊「綁定」）：拾取後綁定、裝備後綁定，綁住的不能 drop、不能 give，
容器裡有綁住的也不行，imm 和生物不擋，可以賣，inventory、equipment 的（綁定），examine、ostat 那一行，存檔，區域檔檢查。
"""
import re
from types import SimpleNamespace

import pytest

import mud.commands as commands
from area_helpers import make_area, make_mobile, make_object, make_room, write_json
from mud import affects, area, combat, death, objects, save, script_api, stats, weather, zones
from mud.area import ExtraFlag
from mud.characters import characters
from mud.commands.imm import obj_text
from mud.config import ENCODING
from mud.players import Player

PICKUP, EQUIP = int(ExtraFlag.BIND_PICKUP), int(ExtraFlag.BIND_EQUIP)
SHOP = {"buy_types": [9, 15], "profit_buy": 100, "profit_sell": 50, "open_hour": 0, "close_hour": 23}


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


def item(vnum, short, keywords, extra=0, item_type=9, wear="1|2", values=(0, 0, 0, 0)):
    o = make_object(vnum)
    o.update(short=short, keywords=keywords, item_type=item_type, extra_flags=extra, wear_flags=wear, values=list(values),
             cost=100, affects=[], extra_descriptions=[], script=None)
    return o


@pytest.fixture
def world(tmp_path, monkeypatch):
    """101：店主（賣拾取後綁定的戒指，收護具和容器）、野狗。物品 110 拾取後綁定戒指、111 裝備後綁定戒指、112 袋子、113 戒指（不綁）。"""
    monkeypatch.setattr(weather, "current", weather.Weather(hour=12))
    monkeypatch.setattr(save, "save_player", lambda p: None)
    objs = [item(110, "金戒", "gold", PICKUP), item(111, "銀戒", "silver", EQUIP),
            item(112, "袋子", "bag", item_type=15, wear="1", values=(50, 0, 0, 0)), item(113, "銅戒", "copper")]
    resets = [{"cmd": "M", "rare": 0, "mob_vnum": 101, "limit": 1, "room_vnum": 101, "comment": ""},
              {"cmd": "G", "rare": 0, "obj_vnum": 110, "color": None, "level": 1, "limit": 0, "comment": ""},
              {"cmd": "M", "rare": 0, "mob_vnum": 102, "limit": 1, "room_vnum": 101, "comment": ""}]
    write_json(tmp_path, "a.json", make_area("a.json", [make_room(101)], (100, 199),
                                             mobiles=[mob(101, "店主", "keeper", SHOP), mob(102, "野狗", "dog")],
                                             objects=objs, resets=resets))
    zones.load(tmp_path)
    yield
    characters.clear()
    zones.stop()


def person(name, imm=False):
    p = Player(name, FakeWriter(), zones.world.rooms[101])
    p.race, p.guild, p.imm = stats.Race.ELF, stats.Guild.SWORD, imm
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.skills = []
    stats.set_level(p, 10)
    characters.append(p)
    return p


def npc(vnum):
    return next(c for c in characters if getattr(c, "vnum", None) == vnum)


def plain(p):
    text = re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))
    p.writer.data = b""
    return text


def say(p, line):
    plain(p)
    commands.command(p, line)
    return plain(p).rsplit("\r\n\r\n", 1)[0]


def give_to(p, vnum, level=1):
    obj = objects.create(vnum, level, None)
    p.carrying.insert(0, obj)
    return obj


def floor():
    return zones.world.rooms[101].contents


# ---- 區域檔 ----

def test_create_reads_the_flags(world):
    gold, silver, copper = (objects.create(v, 1, None) for v in (110, 111, 113))
    assert (gold.bind, silver.bind, copper.bind) == (ExtraFlag.BIND_PICKUP, ExtraFlag.BIND_EQUIP, None)
    assert [objects.bound(o) for o in (gold, silver, copper)] == [True, False, False]


def test_area_check_allows_only_one():
    problems = []
    area.check_object("物品 110", item(110, "金戒", "gold", f"{PICKUP}|{EQUIP}"), problems)
    assert problems == ["物品 110的 extra_flags '1024|2048' 同時有 1024 拾取後綁定和 2048 裝備後綁定：只能寫一個"]
    for extra in (PICKUP, EQUIP):
        problems = []
        area.check_object("物品 110", item(110, "金戒", "gold", extra), problems)
        assert problems == []


# ---- 拿到就綁：每一條路 ----

def test_picked_up_from_the_floor(world):
    ming = person("Ming")
    floor().insert(0, objects.create(110, 1, None))
    assert say(ming, "get gold") == "你拿起了【金戒/gold】。"
    assert say(ming, "drop gold") == "你無法丟掉這樣東西。"
    assert [o.vnum for o in ming.carrying] == [110] and floor() == []


def test_taken_from_a_corpse(world):
    ming = person("Ming")
    dog = npc(102)
    dog.carrying.insert(0, objects.create(110, 1, None))
    death.die(dog)
    assert say(ming, "get gold corpse") == "你把【金戒/gold】從【野狗的屍體/corpse】拿出來。"
    assert say(ming, "drop gold") == "你無法丟掉這樣東西。"


def test_autoloot(world):
    ming = person("Ming")
    ming.autoloot = True
    dog = npc(102)
    dog.carrying.insert(0, objects.create(110, 1, None))
    combat.slain(affects.Messages(), ming, dog)
    assert [o.vnum for o in ming.carrying] == [110]
    assert say(ming, "drop gold") == "你無法丟掉這樣東西。"


def test_bought(world):
    ming = person("Ming")
    ming.gold = 1000
    assert say(ming, "buy gold") == "你買下了【金戒/gold】。"
    assert say(ming, "drop gold") == "你無法丟掉這樣東西。"
    assert [o.vnum for o in npc(101).carrying if o.for_sale] == [110]   # 店裡那件照舊在賣


def test_given_by_a_creature(world):
    ming = person("Ming")
    dog = npc(102)
    dog.carrying.insert(0, objects.create(110, 1, None))
    commands.command(dog, "give gold ming")                           # 生物不擋
    assert [o.vnum for o in ming.carrying] == [110] and dog.carrying == []
    assert say(ming, "give gold dog") == "你無法讓它離開你。"


def test_given_by_a_script(world):
    ming = person("Ming")
    script_api.give_item(SimpleNamespace(owner=None), ming, 110, 1, None)
    assert say(ming, "drop gold") == "你無法丟掉這樣東西。"


def test_oload(world):
    boss, ming = person("Boss", imm=True), person("Ming")
    say(boss, "oload 110 1")
    [ring] = boss.carrying
    assert objects.bound(ring)
    assert say(boss, "give gold ming") == "你把【金戒/gold】拿給Ming。"         # imm 不擋
    assert say(ming, "drop gold") == "你無法丟掉這樣東西。"


# ---- 不能丟、不能給 ----

def test_drop_all_skips_bound(world):
    ming = person("Ming")
    give_to(ming, 113)
    give_to(ming, 110)
    assert say(ming, "drop all") == "你丟下了【銅戒/copper】。"
    assert [o.vnum for o in ming.carrying] == [110]
    assert say(ming, "drop all") == "你沒有攜帶任何東西。"


def test_give_checks_in_order(world):
    ming, hua = person("Ming"), person("Hua")
    give_to(ming, 110)
    assert say(ming, "give gold nobody") == "他們不在這裡。"              # 先找人（照 C 版）
    assert say(ming, "give gold hua") == "你無法讓它離開你。"
    assert say(ming, "give gold dog") == "你無法讓它離開你。"             # 生物也不行
    assert say(ming, "give gold keeper") == "你無法讓它離開你。"          # 在店主拒絕之前
    assert [o.vnum for o in ming.carrying] == [110] and hua.carrying == []


def test_container_with_bound_inside(world):
    ming, hua = person("Ming"), person("Hua")
    bag = give_to(ming, 112)
    bag.contains.append(objects.create(110, 1, None))
    assert say(ming, "drop bag") == "你無法丟掉這樣東西。"
    assert say(ming, "give bag hua") == "你無法讓它離開你。"
    assert say(ming, "drop all") == "你沒有攜帶任何東西。"
    bag.contains.clear()
    assert say(ming, "give bag hua") == "你把【袋子/bag】拿給Hua。"


def test_imm_is_not_stopped(world):
    boss = person("Boss", imm=True)
    give_to(boss, 110)
    assert say(boss, "drop gold") == "你丟下了【金戒/gold】。"


def test_bound_can_be_sold(world):
    ming = person("Ming")
    give_to(ming, 110)
    assert say(ming, "sell gold") == "你賣掉【金戒/gold】，老闆給了你【50】枚金幣。"
    assert ming.carrying == [] and ming.gold == 50


# ---- 裝備後綁定 ----

def test_bind_on_equip(world):
    ming, hua = person("Ming"), person("Hua")
    silver = give_to(ming, 111)
    assert say(ming, "give silver hua") == "你把【銀戒/silver】拿給Hua。"   # 還沒穿過：可以給、可以丟
    assert say(hua, "drop silver") == "你丟下了【銀戒/silver】。"
    say(hua, "get silver")
    say(hua, "wear silver")
    assert silver.bound and objects.bound(silver)
    assert say(hua, "remove silver") == "你卸下了【銀戒/silver】。"
    assert say(hua, "drop silver") == "你無法丟掉這樣東西。"              # 脫下來還是綁著
    say(hua, "wear silver")
    assert "銀戒/silver" in say(hua, "equipment")


def test_failed_wear_does_not_bind(world):
    ming = person("Ming")
    silver = give_to(ming, 111, level=50)
    assert say(ming, "wear silver").startswith("你至少等級(Level)要達到【50】級")
    assert not silver.bound
    assert say(ming, "drop silver") == "你丟下了【銀戒/silver】。"


# ---- 看得出來 ----

def test_inventory_and_equipment(world):
    ming = person("Ming")
    give_to(ming, 111)
    give_to(ming, 110)
    give_to(ming, 113)
    lines = say(ming, "inventory").split("\r\n")
    assert lines[1:4] == ["     銅戒/copper", "     金戒/gold（綁定）", "     銀戒/silver"]
    say(ming, "wear silver")
    assert "銀戒/silver（綁定）" in say(ming, "equipment")
    assert "（綁定）" not in say(ming, "look")                            # 別的地方的名字不加


def test_examine(world):
    ming = person("Ming")
    give_to(ming, 113)
    give_to(ming, 110)
    give_to(ming, 111)
    assert say(ming, "examine silver").split("\r\n")[-1] == "綁定：【裝備後綁定】，還沒綁住。"
    say(ming, "wear silver")
    assert say(ming, "examine silver").split("\r\n")[-1] == "綁定：【裝備後綁定】，已經綁住了。"
    assert say(ming, "examine gold").split("\r\n")[-1] == "綁定：【拾取後綁定】，已經綁住了。"
    assert "綁定" not in say(ming, "examine copper")


def test_ostat(world):
    assert "綁定 裝備後綁定（還沒綁）" in obj_text(objects.create(111, 1, None))
    assert "綁定 拾取後綁定（綁住了）" in obj_text(objects.create(110, 1, None))
    assert "綁定 無" in obj_text(objects.create(113, 1, None))


# ---- 存檔 ----

def test_saved(world):
    silver = objects.create(111, 1, None)
    silver.bound = True
    back = objects.from_data(objects.to_data(silver))
    assert (back.bind, back.bound) == (ExtraFlag.BIND_EQUIP, True)
    gold = objects.from_data(objects.to_data(objects.create(110, 1, None)))
    assert gold.bind == ExtraFlag.BIND_PICKUP and objects.bound(gold)


def test_old_saves_are_not_bound(world):
    data = objects.to_data(objects.create(110, 1, None))
    del data["bind"], data["bound"]
    old = objects.from_data(data)
    assert (old.bind, old.bound, objects.bound(old)) == (None, False, False)
