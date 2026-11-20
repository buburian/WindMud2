"""系統區域檔（header.type 是 system，號碼 1～99，reserved.py，使用者 2026-11-20 定的）：
真的 areas/system.json、檢查的規則、少了程式要的號碼不開機、屍體和金幣照區域檔的文字、區域資料夾沒有系統區域檔時用遊戲的那一份。
召喚物照區域檔的測試在 test_skill_summon.py。
"""
import json
from pathlib import Path

import pytest

from area_helpers import make_area, make_object, make_room, write_json
from mud import area, objects, reserved, zones
from mud.characters import characters
from mud.config import AREA_DIR, SYSTEM_AREA
from mud.npcs import Npc


@pytest.fixture
def world(tmp_path):
    """自己做的區域資料夾：一間房 101，沒有系統區域檔（zones.load 用遊戲的那一份）。"""
    write_json(tmp_path, "a.json", make_area("a.json", [make_room(101)]))
    zones.load(tmp_path)
    yield zones.world
    characters.clear()
    zones.stop()


def system_area(**change):
    """真的系統區域檔，改掉 change 裡的欄位（最上層的）。"""
    data = json.loads(Path(SYSTEM_AREA).read_text(encoding="utf-8"))
    data.update(change)
    return data


def problems_of(tmp_path, data, name="system.json"):
    data["file"] = name
    path = write_json(tmp_path, name, data)
    return area.check_files([path])[path]


def dog(room):
    npc = Npc("野狗", 0, room)
    npc.level = 3
    return npc


# ---- 真的系統區域檔 ----

def test_the_real_system_area_is_fine():
    paths = area.area_files(AREA_DIR)
    assert Path(SYSTEM_AREA) in paths and area.check_files([Path(SYSTEM_AREA)], paths)[Path(SYSTEM_AREA)] == []
    data = json.loads(Path(SYSTEM_AREA).read_text(encoding="utf-8"))
    assert data["area"]["header"]["type"] == area.AreaType.SYSTEM
    found = reserved.check({o["vnum"]: o for o in data["objects"]}, {m["vnum"]: m for m in data["mobiles"]})
    assert found == []                                               # 程式要的號碼都在、種類對


# ---- 檢查的規則 ----

@pytest.mark.parametrize("vnums, ok", [([1, 99], True), ([1, 50], True), ([1, 100], False), ([0, 99], False), ([100, 199], False)])
def test_system_numbers_are_1_to_99(tmp_path, vnums, ok):
    data = system_area()
    data["area"]["header"]["vnums"] = vnums
    found = problems_of(tmp_path, data)
    assert (found == []) == ok
    if not ok:
        assert any("系統區域檔的 area.header.vnums 要寫 [最小, 最大] 兩個整數，在 1～99 裡面" in p for p in found)


def test_system_things_must_be_in_1_to_99(tmp_path):
    data = system_area()
    data["area"]["header"]["vnums"] = [1, 99]
    data["objects"][0]["vnum"] = 150
    assert "system.json：系統區域檔的物品號碼要寫 1～99 的整數，不能是 150" in problems_of(tmp_path, data)


@pytest.mark.parametrize("key, value, label", [("rooms", [make_room(5)], "房間"),
                                               ("resets", [{"cmd": "*", "comment": "註解"}], "重置")])
def test_system_area_has_no_rooms_or_resets(tmp_path, key, value, label):
    found = problems_of(tmp_path, system_area(**{key: value}))
    assert f"system.json：系統區域檔不能有{label}（{key} 要寫 []），現在有 1 筆" in found


def test_other_areas_still_cannot_use_1_to_99(tmp_path):
    thing = make_object(5)
    data = make_area("a.json", [make_room(101)], objects=[thing])
    assert "a.json：物品號碼要寫完整的遊戲號碼（100 以上，1～99 是系統區域檔用的），不能是 5" in problems_of(tmp_path, data, "a.json")


# ---- 開機 ----

def test_missing_number_stops_the_server(tmp_path):
    data = system_area()
    data["objects"] = [o for o in data["objects"] if o["vnum"] != reserved.CORPSE]
    write_json(tmp_path, "system.json", data)                         # 資料夾裡有系統區域檔：用它，不用遊戲的那一份
    write_json(tmp_path, "a.json", make_area("a.json", [make_room(101)]))
    with pytest.raises(ValueError, match=r"^系統區域檔少了物品 10（怪物的屍體）$"):
        zones.load(tmp_path)


def test_wrong_kind_stops_the_server(tmp_path):
    data = system_area()
    next(o for o in data["objects"] if o["vnum"] == reserved.MONEY_ONE)["item_type"] = 13
    write_json(tmp_path, "system.json", data)
    with pytest.raises(ValueError, match="系統區域檔的物品 2（一枚金幣）的 item_type 要是 20（金錢），不能是 13"):
        zones.load(tmp_path)


def test_system_area_builds_no_rooms(world):
    assert all(a.name != "system.json" for a in world.areas) and "system.json" not in zones.templates
    assert "system.json" not in zones.routes
    assert reserved.CORPSE in objects.protos                          # 資料夾裡沒有：用遊戲的那一份


# ---- 屍體、金幣照區域檔 ----

def test_corpse_text_comes_from_the_system_area(world, monkeypatch):
    room = world.rooms[101]
    corpse = objects.make_corpse(dog(room))
    assert (corpse.vnum, corpse.name, corpse.long, corpse.keywords) == (reserved.CORPSE, "野狗的屍體", "野狗的屍體橫躺在地上。", ["corpse"])
    assert (corpse.level, corpse.take, room.contents[0]) == (3, False, corpse)
    monkeypatch.setitem(objects.protos, reserved.CORPSE,
                        dict(objects.protos[reserved.CORPSE], short="$n的殘骸", long="$n的殘骸倒在這裡。", keywords="remains"))
    corpse = objects.make_corpse(dog(room))                           # 改區域檔的文字，遊戲裡跟著變
    assert (corpse.name, corpse.long, corpse.keywords) == ("野狗的殘骸", "野狗的殘骸倒在這裡。", ["remains"])


@pytest.mark.parametrize("amount, vnum, name, long, keywords", [
    (1, reserved.MONEY_ONE, "一枚金幣", "一枚金幣被留在地上。", ["coin", "gold"]),
    (2, reserved.MONEY_SOME, "一些金幣", "一堆金幣被遺留在地上。", ["coins", "gold"]),
    (500, reserved.MONEY_SOME, "一些金幣", "一堆金幣被遺留在地上。", ["coins", "gold"]),
])
def test_money_comes_from_the_system_area(world, amount, vnum, name, long, keywords):
    coins = objects.money(amount)
    assert (coins.vnum, coins.name, coins.long, coins.keywords, coins.coins, coins.take) == (vnum, name, long, keywords, amount, True)
