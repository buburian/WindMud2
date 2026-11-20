"""舊區域轉成我們的區域檔（mud/areaconvert.py）：每條轉換規則、報告、轉出來的檔檢查沒問題、真的秋風城。

舊檔是 area2json 的格式（mud_design/tools/area_convert/README.md）：旗標是 {"value", "names"}、代號是 {"value", "name"}。
"""
import json
from pathlib import Path

import pytest

from mud import area, areaconvert

MIDGAARD = Path(__file__).resolve().parents[2] / "mud_design" / "tools" / "area_convert" / "out" / "midgaard1.json"


def flags(*names):
    return {"value": 0, "names": list(names)}           # value 轉的時候不看（只照名字）


def code(value, name):
    return {"value": value, "name": name}


def old_exit(to, locks=0, key=-1, keywords=""):
    return {"description": "", "keywords": keywords, "locks": locks, "door_flags": [], "key": key, "to_room": to}


def old_room(vnum, room_flags=(), **exits):
    return {"vnum": vnum, "name": f"房間{vnum}", "description": "描述\n", "area_number": 0, "room_flags": flags(*room_flags),
            "sector": code(1, "city"), "exits": exits, "extra_descriptions": [], "script": None}


def old_mob(vnum, level=5, act=(), affected=(), race="human", position=8, **extra):
    m = {"vnum": vnum, "keywords": f"mob{vnum}", "short": f"生物{vnum}", "long": "站著。\n", "description": "",
         "level": level, "act": flags(*act), "affected_by": flags(*affected), "alignment": 0, "race": race,
         "sex": code(1, "male"), "hitroll": 0, "ac": 0, "hit_dice": {}, "damage_dice": {}, "gold": 0, "exp": 0,
         "position": position, "custom": None, "random_drop": None, "script": None, "actions": [], "fight_actions": []}
    m.update(extra)
    return m


def old_obj(vnum, item_type=(9, "armor"), wear=("take", "body"), extra=(), values=(5, 0, 5, 0), keywords=None, affects=()):
    return {"vnum": vnum, "keywords": keywords or f"obj{vnum}", "short": f"物品{vnum}", "long": "", "action_description": "",
            "item_type": code(*item_type), "extra_flags": flags(*extra), "wear_flags": flags(*wear), "values": list(values),
            "values_raw": [], "weight": 1, "cost": 10, "cost_per_day": 0, "affects": list(affects),
            "extra_descriptions": [], "script": None}


def M(mob, room, rare=0):
    return {"cmd": "M", "rare": rare, "mob_vnum": mob, "limit": 1, "room_vnum": room, "comment": ""}


def E(obj, rare=1):
    return {"cmd": "E", "rare": rare, "obj_vnum": obj, "limit": 100, "wear_loc": code(5, "body"), "comment": ""}


def old_area(rooms, mobiles=(), objects=(), resets=(), shops=(), specials=(), levels=(None, None), recall=None):
    return {"schema_version": 1, "file": "old.are",
            "area": {"name": "{ All } x 舊城", "header": {"levels": "All", "level_min": levels[0], "level_max": levels[1],
                                                         "author": "*Diku", "title": "舊城"},
                     "recall": recall, "no_teleport": None, "clan_recall": None, "gem": None},
            "helps": [], "mobiles": list(mobiles), "objects": list(objects), "rooms": list(rooms), "resets": list(resets),
            "shops": list(shops), "specials": list(specials), "messages": [], "decode_failures": 0}


def two_rooms():
    return [old_room(3001, north=old_exit(3002)), old_room(3002, south=old_exit(3001))]


def problems_of(tmp_path, data):
    path = tmp_path / data["file"]
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return area.check_files([path], [path])[path]


def test_header_and_range(tmp_path):
    data, _ = areaconvert.convert(old_area(two_rooms()), "new.json")
    assert data["file"] == "new.json"
    assert data["area"]["header"] == {"levels": [1, 100], "author": "*Diku", "title": "舊城", "vnums": [3001, 3002],
                                      "type": "world", "reset_empty": None, "reset_players": None}   # 舊的寫 All：1～100；範圍是最小、最大的號碼；重生用預設
    data, _ = areaconvert.convert(old_area(two_rooms(), levels=(5, 25)), "new.json", [3000, 3399])
    assert data["area"]["header"]["levels"] == [5, 25] and data["area"]["header"]["vnums"] == [3000, 3399]
    assert problems_of(tmp_path, data) == []


def test_flags_go_by_name_and_unknown_ones_are_reported():
    rooms = [old_room(3001, room_flags=("safe", "indoors"))]
    mobs = [old_mob(3001, act=("is_npc", "sentinel", "hate"), affected=("detect_invis", "flaming"))]
    objs = [old_obj(3001, extra=("bless", "anti_evil"), wear=("take", "body", "shoulder"))]
    data, report = areaconvert.convert(old_area(rooms, mobs, objs), "new.json")
    assert data["rooms"][0]["room_flags"] == area.RoomFlag.SAFE | area.RoomFlag.INDOORS
    assert data["mobiles"][0]["act"] == area.ActFlag.SENTINEL
    assert data["mobiles"][0]["affected_by"] == area.AffectFlag.DETECT_INVIS
    assert data["objects"][0]["extra_flags"] == area.ExtraFlag.BLESS == 256          # 我們的數字，不是舊的
    assert data["objects"][0]["wear_flags"] == area.WearFlag.TAKE | area.WearFlag.BODY
    assert report.dropped == ["生物 3001 生物3001的 act hate", "生物 3001 生物3001的 affected_by flaming",
                              "物品 3001 物品3001的 extra_flags anti_evil", "物品 3001 物品3001的 wear_flags shoulder"]
    assert "房間 3001 房間3001的旗標" not in " ".join(report.kept)                # safe、indoors 有作用


def test_room_flags_without_effect_are_listed():
    _, report = areaconvert.convert(old_area([old_room(3001, room_flags=("no_summon", "safe"))]), "new.json")
    assert report.kept == ["房間 3001 房間3001的旗標 no_summon"]


def test_exits_to_other_areas_are_dropped():
    # 101 剛好是 test.json 的房間：不在這個檔的一律拿掉，不靠檢查
    rooms = [old_room(3001, north=old_exit(3002), east=old_exit(101), up=old_exit(3700, locks=1)), old_room(3002, south=old_exit(3001))]
    resets = [{"cmd": "D", "if_flag": 0, "room_vnum": 3001, "direction": code(4, "up"), "state": code(1, "closed"), "comment": ""}]
    data, report = areaconvert.convert(old_area(rooms, resets=resets), "new.json")
    assert list(data["rooms"][0]["exits"]) == ["north"]
    assert data["resets"] == []                                         # 那扇門的 D 也拿掉
    assert report.dropped == ["房間 3001 房間3001往 east 通到別的區域的出口 101", "房間 3001 房間3001往 up 通到別的區域的出口 3700",
                              "重置 D：房間 3001 往 up 沒有門（出口拿掉了，或沒寫門）"]


def test_one_sided_doors_are_filled():
    rooms = [old_room(3001, north=old_exit(3002, locks=2, key=3005, keywords="鐵門 door")), old_room(3002, south=old_exit(3001))]
    resets = [{"cmd": "D", "if_flag": 0, "room_vnum": 3001, "direction": code(0, "north"), "state": code(2, "locked"), "comment": "鎖"}]
    data, report = areaconvert.convert(old_area(rooms, resets=resets), "new.json")
    assert data["rooms"][1]["exits"]["south"] == {"description": "", "keywords": "鐵門 door", "locks": 2, "key": 3005, "to_room": 3001}
    assert data["resets"] == [{"cmd": "D", "if_flag": 0, "room_vnum": 3001, "direction": "north", "state": 2, "comment": "鎖"}]
    assert report.changed == ["房間 3002 往 south 的門照房間 3001 那邊補上（門兩邊都要寫）"]


def test_one_way_exit_gets_no_door():
    rooms = [old_room(3001, north=old_exit(3002, locks=1)), old_room(3002, south=old_exit(3003)), old_room(3003)]
    data, _ = areaconvert.convert(old_area(rooms), "new.json")
    assert data["rooms"][1]["exits"]["south"]["locks"] == 0             # 往回的出口沒指回來：不是同一扇門


def test_worn_equipment_becomes_a_white_drop(tmp_path):
    # 使用者要的：穿上的裝備變成 100% 掉落的白色裝備；同一隻被好幾筆 M 放只加一次；不是裝備不寫顏色；不一定出現的照 rare
    objs = [old_obj(3001), old_obj(3002, item_type=(18, "key"), wear=("take",), values=(0, 0, 0, 0)), old_obj(3003)]
    resets = [M(3001, 3001), E(3001), E(3002), M(3001, 3002), E(3001), E(3003, rare=2510)]
    data, _ = areaconvert.convert(old_area(two_rooms(), [old_mob(3001)], objs, resets), "new.json")
    assert data["mobiles"][0]["drops"] == [
        {"obj_vnum": 3001, "color": "white", "chance": 10000, "tiers": None},
        {"obj_vnum": 3002, "color": None, "chance": 10000, "tiers": None},
        {"obj_vnum": 3003, "color": "white", "chance": 2500, "tiers": None}]
    assert [r["cmd"] for r in data["resets"]] == ["M", "M"]             # E 拿掉了
    assert problems_of(tmp_path, data) == []


def test_mobiles():
    mobs = [old_mob(3001, level=0, race="element", position=0), old_mob(3002, level=150, race="Hobbit")]
    data, report = areaconvert.convert(old_area(two_rooms(), mobs), "new.json")
    m1, m2 = data["mobiles"]
    assert (m1["level"], m1["race"], m1["position"], m1["tier"]) == (1, "elemental", 7, "normal")   # 舊的 0 會變成死的
    assert (m2["level"], m2["race"], m2["position"]) == (150, "hobbit", 7)
    assert m1["long"] == "站著。\n" and m1["sex"] == 1
    assert report.changed == ["生物 3001 生物3001的種族 element 照開頭比對成 elemental", "生物 3001 生物3001的等級 0 改成 1",
                              "生物 3002 生物3002的種族 Hobbit 照開頭比對成 hobbit"]


def test_things_that_are_not_converted_are_reported():
    mob = old_mob(3001, custom={"attacks": 10}, script={"trigger": flags("say"), "function": "ms_x"},
                  actions=[{"when": code(1, "enter"), "mode": code(0, "interp"), "text": "say 你好"}],
                  fight_actions=[{"rate": 10, "message": "", "command": "mobdam all 1 2"}])
    room = old_room(3001)
    room["script"] = {"trigger": flags("command"), "function": "rs_chess"}
    obj = old_obj(3001, affects=[{"location": code(18, "hitroll"), "modifier": 2}])
    data, report = areaconvert.convert(old_area([room], [mob], [obj]), "new.json")
    assert data["mobiles"][0]["script"] is None and data["rooms"][0]["script"] is None and data["objects"][0]["affects"] == []
    assert report.dropped == [
        "房間 3001 房間3001的 C 版腳本 rs_chess（觸發 command）",
        "生物 3001 生物3001的 K 行 {'attacks': 10}",
        "生物 3001 生物3001的 C 版腳本 ms_x（觸發 say）",
        "生物 3001 生物3001的平常動作（enter）say 你好",
        "生物 3001 生物3001的戰鬥動作 10% mobdam all 1 2",
        "物品 3001 物品3001的加成 hitroll +2（舊的屬性代號，改成照等級和顏色抽）"]


@pytest.mark.parametrize("keywords, values, extra, want", [
    ("axe blade", [0, 5, 6, 1], (), ([4, 0, 0, 1], 0)),                # 單手斧，攻擊方式照舊
    ("dagger", [0, 2, 4, 11], (), ([1, 0, 0, 11], 0)),
    ("standard mace", [0, 4, 4, 7], ("magic",), ([5, 0, 0, 7], 64)),
    ("bardiche", [0, 3, 4, 3], (), ([9, 0, 0, 3], 512)),               # 戰斧是雙手：加 512
    ("sword long", [0, 2, 6, 10], (), ([2, 0, 0, 1], 0)),              # 利牙是怪物專用：用長劍預設的橫切
    ("icekingdom news", [0, 0, 0, 7], (), ([2, 0, 0, 7], 0)),          # 看不出來：長劍
])
def test_weapons(tmp_path, keywords, values, extra, want):
    obj = old_obj(3001, item_type=(5, "weapon"), wear=("take", "wield"), extra=extra, values=values, keywords=keywords)
    data, _ = areaconvert.convert(old_area(two_rooms(), objects=[obj]), "new.json")
    assert (data["objects"][0]["values"], data["objects"][0]["extra_flags"]) == want
    assert problems_of(tmp_path, data) == []


def test_armor_values_are_left_to_the_level():
    data, _ = areaconvert.convert(old_area(two_rooms(), objects=[old_obj(3001, values=(5, 7, 5, 1))]), "new.json")
    assert data["objects"][0]["values"] == [0, 7, 0, 1]                 # 防護力由裝備等級算


def test_shops_and_specials():
    mobs = [old_mob(3001), old_mob(3002), old_mob(3003)]
    shops = [{"keeper_vnum": 3001, "buy_types": [2, 10, 0, 0, 0], "buy_type_names": [], "profit_buy": 120, "profit_sell": 80,
              "open_hour": 6, "close_hour": 22, "comment": ""}]
    specials = [{"cmd": "M", "mob_vnum": 3001, "function": "spec_cast_mage", "comment": ""},
                {"cmd": "M", "mob_vnum": 3002, "function": "spec_guard", "comment": ""},
                {"cmd": "M", "mob_vnum": 3003, "function": "spec_unknown", "comment": ""},
                {"cmd": "*", "comment": "註解"}]
    data, report = areaconvert.convert(old_area(two_rooms(), mobs, shops=shops, specials=specials), "new.json")
    assert data["mobiles"][0]["shop"] == {"buy_types": [2, 10], "profit_buy": 120, "profit_sell": 80, "open_hour": 6, "close_hour": 22}
    assert [m["special"] for m in data["mobiles"]] == ["spec_cast_mage", "spec_guard", None]
    assert "生物 3003 的 special spec_unknown" in report.dropped
    assert report.kept == ["生物 3001 生物3001的商店（商店還沒做）", "生物 3002 生物3002的 special spec_guard（先不做）"]


def test_other_resets(tmp_path):
    objs = [old_obj(3001), old_obj(3002, item_type=(15, "container"), wear=("take",), values=(10, 0, 0, 0))]
    resets = [{"cmd": "*", "comment": "註解"}, M(3001, 3001),
              {"cmd": "G", "rare": 110, "obj_vnum": 3001, "limit": 0, "comment": "賣的"},
              {"cmd": "O", "if_flag": 0, "obj_vnum": 3002, "limit": 1, "room_vnum": 3002, "comment": ""},
              {"cmd": "P", "if_flag": 0, "obj_vnum": 3001, "limit": 1, "container_vnum": 3002, "comment": ""}]
    data, _ = areaconvert.convert(old_area(two_rooms(), [old_mob(3001)], objs, resets), "new.json")
    assert data["resets"] == [
        {"cmd": "*", "comment": "註解"},
        {"cmd": "M", "rare": 0, "mob_vnum": 3001, "limit": 1, "room_vnum": 3001, "comment": ""},
        {"cmd": "G", "rare": 110, "obj_vnum": 3001, "color": None, "level": None, "limit": 0, "comment": "賣的"},
        {"cmd": "O", "if_flag": 0, "obj_vnum": 3002, "color": None, "level": 1, "limit": 1, "room_vnum": 3002, "comment": ""},
        {"cmd": "P", "if_flag": 0, "obj_vnum": 3001, "color": None, "level": 1, "limit": 1, "container_vnum": 3002, "comment": ""}]
    assert problems_of(tmp_path, data) == []


def test_cli_refuses_to_overwrite(tmp_path, capsys):
    old = tmp_path / "old.json"
    old.write_text(json.dumps(old_area(two_rooms()), ensure_ascii=False), encoding="utf-8")
    new = tmp_path / "new.json"
    assert areaconvert.main([str(old), str(new)]) == 0
    out = capsys.readouterr().out
    assert "房間 2、生物 0、物品 0、重置 0" in out and "0 個問題" in out
    new.write_text("改過了", encoding="utf-8")
    assert areaconvert.main([str(old), str(new)]) == 1                  # 在編輯器改過的不能蓋掉
    assert new.read_text(encoding="utf-8") == "改過了"
    assert areaconvert.main([str(old), str(new), "--force", "--vnums", "3000", "3399"]) == 0
    assert json.loads(new.read_text(encoding="utf-8"))["area"]["header"]["vnums"] == [3000, 3399]


@pytest.mark.skipif(not MIDGAARD.exists(), reason="找不到 mud_design 的 area2json 輸出")
def test_midgaard_converts_without_problems(tmp_path):
    data, report = areaconvert.convert(json.loads(MIDGAARD.read_text(encoding="utf-8")), "midgaard.json")
    assert (len(data["rooms"]), len(data["mobiles"]), len(data["objects"])) == (179, 89, 120)    # 12 件法術還沒有技能（含 3 個藥錠）
    assert data["area"]["header"]["vnums"] == [3000, 3399]
    assert not any(r["cmd"] == "E" for r in data["resets"])
    assert all(e["to_room"] // 100 in (30, 31, 32) for r in data["rooms"] for e in r["exits"].values())
    assert problems_of(tmp_path, data) == []


# ---- 會放技能的物品（設計文件 §3.8）----

def test_spells_become_skills(tmp_path):
    objs = [old_obj(3001, item_type=(10, "potion"), wear=("take",), values=(12, "fly", "", "")),
            old_obj(3002, item_type=(3, "wand"), wear=("take", "hold"), values=(0, 10, 10, "breathe water"))]
    data, report = areaconvert.convert(old_area(two_rooms(), objects=objs), "new.json")
    assert [o["values"] for o in data["objects"]] == [[12, "fly", "", ""], [0, 10, 10, "breathe"]]
    assert "物品 3002 物品3002的法術 breathe water 換成技能 breathe" in report.changed
    assert problems_of(tmp_path, data) == []


@pytest.mark.parametrize("values, why", [((12, "fly", "identify", ""), "法術 identify 還沒有對應的技能"),
                                         ((12, "", "", ""), "沒有寫法術")])
def test_items_without_skills_are_dropped_with_their_resets(tmp_path, values, why):
    mob = old_mob(3001)
    objs = [old_obj(3001, item_type=(2, "scroll"), wear=("take",), values=values), old_obj(3002)]
    resets = [M(3001, 3001), {"cmd": "G", "rare": 0, "obj_vnum": 3001, "limit": 1, "comment": ""}, E(3001),
              {"cmd": "O", "if_flag": 0, "obj_vnum": 3001, "limit": 1, "room_vnum": 3001, "comment": ""},
              {"cmd": "P", "if_flag": 0, "obj_vnum": 3002, "limit": 1, "container_vnum": 3001, "comment": ""}]
    data, report = areaconvert.convert(old_area(two_rooms(), mobiles=[mob], objects=objs, resets=resets), "new.json")
    assert [o["vnum"] for o in data["objects"]] == [3002]
    assert [r["cmd"] for r in data["resets"]] == ["M"]                 # G、E、O 和放進它的 P 都拿掉
    assert data["mobiles"][0]["drops"] == []
    assert f"物品 3001 物品3001（{why}，整件拿掉，連同放它的重置）" in report.dropped
    assert problems_of(tmp_path, data) == []


def test_food_becomes_one_bite(tmp_path):
    food = old_obj(3001, item_type=(19, "food"), wear=("take",), values=(40, 0, 0, 1))
    data, _ = areaconvert.convert(old_area(two_rooms(), objects=[food]), "new.json")
    assert data["objects"][0]["values"] == [1, "", 0, 1]              # 毒（第 4 個）不做，照留
    assert problems_of(tmp_path, data) == []
