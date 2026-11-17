"""光源和黑暗（light.py）：很暗的四個條件、光源（身上、地上、背包裡不算、燒完的不算）、精靈和 imm 看得到、
look 的每一種、找不到人、撿不到、「某人」、走進來看不到、對面的門、燒完、燈籠放光源位置、存檔的 hours、自動拾取。

坑：日夜照現實時間算，測試都把 weather.current 換成固定的時間（白天 12 點、晚上 22 點）。
"""
import re

import pytest

import mud.commands as commands
from area_helpers import make_area, make_mobile, make_object, make_room, write_json
from mud import affects, combat, light, objects, stats, weather, zones
from mud.act import TO_ROOM, TO_VICT, act
from mud.characters import characters, find_in_room
from mud.config import ENCODING
from mud.npcs import Npc
from mud.players import Player

DAY, NIGHT = 12, 22
DARK = light.DARK_TEXT


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


def light_item(vnum, short, keywords, hours, wear="1"):
    o = make_object(vnum)
    o.update(short=short, keywords=keywords, item_type=1, wear_flags=wear, values=[0, 0, hours, 0], affects=[],
             extra_descriptions=[], script=None)
    return o


@pytest.fixture
def world(tmp_path, monkeypatch):
    """101 室內 —北— 102 原野；101 —東（木門）— 103 很暗（室內）；101 —西— 104 城市。103 有一隻狗、地上一塊麵包。"""
    monkeypatch.setattr(weather, "current", weather.Weather(hour=DAY))
    rooms = [make_room(101, north=102, east=103, west=104), make_room(102, south=101), make_room(103, west=101),
             make_room(104, east=101)]
    rooms[1]["sector"], rooms[2]["room_flags"], rooms[3]["sector"] = 2, 1, 1
    for r, d in ((rooms[0], "east"), (rooms[2], "west")):
        r["exits"][d].update(locks=1, keywords="木門 door")
    dog = make_mobile(101)
    dog.update(short="野狗", keywords="dog", act=2, position=7, drops=[], special=None, shop=None, long="")
    bread = make_object(103)
    bread.update(short="麵包", keywords="bread", item_type=19, wear_flags="1", values=[1, "", 0, 0], affects=[],
                 extra_descriptions=[], script=None)
    objs = [light_item(101, "火把", "torch", 2), light_item(102, "燈籠", "lantern", -1, wear="1|16384"), bread]
    resets = [{"cmd": "M", "rare": 0, "mob_vnum": 101, "limit": 1, "room_vnum": 103, "comment": ""},
              {"cmd": "O", "obj_vnum": 103, "limit": 1, "room_vnum": 103, "color": None, "level": 1,
               "if_flag": 0, "comment": ""}]
    write_json(tmp_path, "a.json", make_area("a.json", rooms, (100, 199), mobiles=[dog], objects=objs, resets=resets))
    zones.load(tmp_path)
    yield zones.world
    characters.clear()
    zones.stop()


def at(hour, monkeypatch):
    monkeypatch.setattr(weather, "current", weather.Weather(hour=hour))


def person(name, room=101, race=stats.Race.HUMAN, imm=False):
    p = Player(name, FakeWriter(), zones.world.rooms[room])
    p.race, p.guild, p.imm = race, stats.Guild.SWORD, imm
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.skills = []
    stats.set_level(p, 1)
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


def wear_torch(p, vnum=101):
    torch = objects.create(vnum, 1, None)
    p.equipment["light"] = torch
    return torch


def room(vnum):
    return zones.world.rooms[vnum]


# ---- 什麼時候很暗 ----

@pytest.mark.parametrize("vnum, hour, dark", [
    (101, NIGHT, False), (104, NIGHT, False),                         # 室內、城市晚上也不暗
    (102, DAY, False), (102, 6, False), (102, 18, False),             # 原野：白天、日出不暗
    (102, 19, True), (102, NIGHT, True), (102, 0, True), (102, 5, True),   # 日落、晚上暗
    (103, DAY, True), (103, NIGHT, True),                             # 很暗的旗標：白天也暗
])
def test_when_a_room_is_dark(world, monkeypatch, vnum, hour, dark):
    at(hour, monkeypatch)
    assert light.dark(room(vnum)) is dark


def test_a_worn_light_lights_the_room(world):
    ming = person("Ming", 103)
    assert light.dark(room(103))
    wear_torch(ming)
    assert not light.dark(room(103))


def test_a_light_in_the_backpack_does_not_count(world):
    ming = person("Ming", 103)
    ming.carrying.append(objects.create(101, 1, None))
    assert light.dark(room(103))


def test_a_light_on_the_floor_lights_the_room(world):
    room(103).contents.insert(0, objects.create(101, 1, None))
    assert not light.dark(room(103))


def test_a_burnt_out_light_does_not_count(world):
    ming = person("Ming", 103)
    wear_torch(ming).hours = 0
    assert light.dark(room(103))


def test_someone_elses_light_in_another_room_does_not_count(world):
    wear_torch(person("Ming", 101))
    assert light.dark(room(103))


# ---- 誰看得到 ----

@pytest.mark.parametrize("race, imm, sees", [(stats.Race.HUMAN, False, False), (stats.Race.ELF, False, True),
                                             (stats.Race.HUMAN, True, True)])
def test_elves_and_imms_see_in_the_dark(world, race, imm, sees):
    assert light.can_see_room(person("Ming", 103, race, imm)) is sees


def test_creatures_see_in_the_dark(world):
    dog = next(c for c in characters if isinstance(c, Npc))
    ming = person("Ming", 103)
    assert light.can_see_room(dog) and find_in_room(dog, "ming") is ming


# ---- look ----

@pytest.mark.parametrize("line", ["look", "l", "look dog", "look w", "look in bread", "look ming", "look xyz"])
def test_look_in_the_dark_shows_one_line(world, line):
    assert say(person("Ming", 103), line) == DARK


def test_look_with_a_light(world):
    ming = person("Ming", 103)
    wear_torch(ming)
    text = say(ming, "look")
    assert "【房間103】" in text and "野狗" in text and "/bread" in text           # 麵包的 long 是空的，只看到英文名字


def test_the_screen_after_walking_into_the_dark(world):
    ming = person("Ming", 101)
    assert say(ming, "e") == DARK


def test_glowing_eyes_of_an_elf(world):
    ming = person("Ming", 103)
    person("Legolas", 103, stats.Race.ELF)
    assert say(ming, "look") == DARK + "\r\n" + light.EYES_TEXT


def test_an_elf_sees_the_room(world):
    assert "【房間103】" in say(person("Legolas", 103, stats.Race.ELF), "look")


# ---- 找人、撿東西 ----

def test_cannot_find_others_in_the_dark(world):
    ming = person("Ming", 103)
    assert find_in_room(ming, "dog") is None
    assert find_in_room(ming, "ming") is ming                         # 自己找得到
    assert say(ming, "kill dog") == "找不到你想攻擊的人。"


def test_cannot_get_from_the_floor_in_the_dark(world):
    ming = person("Ming", 103)
    assert say(ming, "get bread") == "這裡找不到【bread】。"
    assert say(ming, "get all") == "我沒看到任何的東西。"
    wear_torch(ming)
    say(ming, "get bread")
    assert [o.name for o in ming.carrying] == ["麵包"]


def test_own_backpack_is_still_seen(world):
    ming = person("Ming", 103)
    ming.carrying.append(objects.create(103, 1, None))
    assert "麵包" in say(ming, "inventory")


# ---- 某人、走進來 ----

def test_names_become_someone_in_the_same_dark_room(world):
    ming, wang = person("Ming", 103), person("Wang", 103)
    act("$n笑了。", wang, to=TO_ROOM)
    assert "某人笑了。" in plain(ming)


def test_tell_from_another_room_keeps_the_name(world):
    ming, wang = person("Ming", 103), person("Wang", 101)
    act("$n告訴你：『嗨』", wang, ming, to=TO_VICT)
    assert "Wang告訴你" in plain(ming)


def test_walking_in_and_out_of_the_dark(world):
    ming, wang = person("Ming", 103), person("Wang", 101)
    say(wang, "e")
    assert "走了過來" not in plain(ming)                               # 看不到誰走進來
    say(wang, "w")
    assert "某人朝西離開。" in plain(ming)


def test_a_light_coming_in_is_seen(world):
    ming, wang = person("Ming", 103), person("Wang", 101)
    wear_torch(wang)
    say(wang, "e")
    assert "Wang從西邊走了過來。" in plain(ming)


@pytest.mark.parametrize("race, told", [(stats.Race.HUMAN, False), (stats.Race.ELF, True)])
def test_door_opened_from_the_other_side(world, race, told):
    ming = person("Ming", 103, race)
    room(101).doors["east"].set(1)                                    # 關上（area.DoorState.CLOSED）
    room(103).doors["west"].set(1)
    say(person("Wang", 101), "open east")
    assert ("西方的木門被打開了。" in plain(ming)) is told


# ---- 照明用具 ----

def test_lights_always_go_to_the_light_slot(world):
    assert objects.create(102, 1, None).slot == "light"               # 燈籠寫了 hold 也一樣
    ming = person("Ming", 101)
    ming.carrying.append(objects.create(102, 1, None))
    say(ming, "wear lantern")
    assert ming.equipment["light"].name == "燈籠"


def test_a_coloured_light_gets_no_affixes(world):
    torch = objects.create(101, 30, "orange")
    assert torch.name == "火把" and torch.affects == [] and torch.hours == 2


def test_hours_are_saved(world):
    torch = objects.create(101, 1, None)
    torch.hours = 1
    assert objects.from_data(objects.to_data(torch)).hours == 1
    old = objects.to_data(torch)
    del old["hours"]                                                  # 舊存檔：照區域檔現在的值
    assert objects.from_data(old).hours == 2


def test_lights_burn_out(world):
    ming, wang = person("Ming", 101), person("Wang", 101)
    torch = wear_torch(ming)
    light.burn()
    assert torch.hours == 1 and "light" in ming.equipment
    plain(ming)
    light.burn()
    assert "light" not in ming.equipment and torch not in ming.carrying
    assert "【火把/torch】燃燒殆盡了。" in plain(ming)
    assert "【火把/torch】燃燒殆盡了。" in plain(wang)


def test_what_does_not_burn(world):
    imm = person("Boss", 101, imm=True)
    imm_torch = wear_torch(imm)
    lantern = wear_torch(person("Ming", 101), 102)
    floor = objects.create(101, 1, None)
    room(101).contents.insert(0, floor)
    light.burn()
    assert (imm_torch.hours, lantern.hours, floor.hours) == (2, -1, 2)


# ---- 自動拾取 ----

def test_no_autoloot_in_the_dark(world):
    ming = person("Ming", 103)
    ming.autoloot = True
    dog = next(c for c in characters if isinstance(c, Npc))
    dog.carrying.append(objects.create(103, 1, None))
    out = affects.Messages()
    combat.slain(out, ming, dog)
    assert ming.carrying == []
    assert not any("裝著" in text for text in out.by.get(ming, []))
