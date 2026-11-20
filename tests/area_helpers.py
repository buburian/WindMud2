"""測試用：做出一份完整、正確的區域資料（每個欄位都有），各測試再改其中的欄位。"""
import json


def make_exit(to_room, description=""):
    return {"description": description, "keywords": "", "locks": 0, "key": -1, "to_room": to_room}


def make_room(vnum, **exits):
    """exits 寫成 north=102 這樣：方向＝to_room（號碼一律寫完整的遊戲號碼）。"""
    return {"vnum": vnum, "name": f"房間{vnum}", "description": "", "room_flags": 0, "sector": 0,
            "exits": {d: make_exit(to) for d, to in exits.items()}, "extra_descriptions": [], "script": None}


def make_mobile(vnum):
    """每個欄位都有值的生物（巢狀的也是），各測試再改其中的欄位。"""
    return {
        "vnum": vnum, "keywords": f"mob{vnum}", "short": f"生物{vnum}", "long": "", "description": "",
        "level": 1, "tier": "normal", "tier_roll": {"elite": 2000, "boss": 100}, "attack": "dragon/phys", "defense": "phys", "archetype": "tank", "act": 0, "affected_by": 0, "alignment": 0, "race": "human", "sex": 0, "position": 0,
        "drops": [{"obj_vnum": 101, "color": "orange", "chance": 100, "tiers": ["boss"]}],
        "script": None,                     # 腳本要另外寫 .lua 檔（write_lua），所以預設沒有
        "shop": {"buy_types": [8], "profit_buy": 100, "profit_sell": 100, "open_hour": 0, "close_hour": 23},
        "special": "spec_guard", "special_ratio": 2.5, "poison_ratio": 0.4,
    }


def make_object(vnum):
    """每個欄位都有值的物品（巢狀的也是），各測試再改其中的欄位。"""
    return {
        "vnum": vnum, "keywords": f"obj{vnum}", "short": f"物品{vnum}", "long": "",
        "item_type": 5, "extra_flags": 0, "wear_flags": "1|8192", "values": [2, 1, 4, 3], "weight": 1, "cost": 0,
        "affects": [{"location": 1, "modifier": 1}], "main_affix": None,
        "extra_descriptions": [{"keywords": "劍 sword", "description": ""}],
        "script": {"trigger": {"value": 64, "names": ["say"]}, "function": "os_test"},
    }


def make_resets():
    """每種重置指令各一筆，都寫對（號碼只看寫法，指到的東西不必存在）。"""
    return [
        {"cmd": "M", "rare": 0, "mob_vnum": 101, "limit": 1, "room_vnum": 101, "comment": ""},
        {"cmd": "G", "rare": 0, "obj_vnum": 101, "color": "white", "level": None, "limit": 0, "comment": ""},
        {"cmd": "O", "if_flag": 0, "obj_vnum": 103, "color": None, "level": 1, "limit": 0, "room_vnum": 102, "comment": ""},
        {"cmd": "P", "if_flag": 0, "obj_vnum": 104, "color": "orange", "level": 10, "limit": 0, "container_vnum": 103, "comment": ""},
        {"cmd": "D", "if_flag": 0, "room_vnum": 101, "direction": "north", "state": 0, "comment": ""},
        {"cmd": "R", "if_flag": 0, "room_vnum": 102, "exit_count": 4, "comment": ""},
        {"cmd": "*", "comment": "註解"},
    ]


def make_area(filename, rooms, vnums=(100, 199), mobiles=(), resets=(), objects=(), kind="world"):
    """vnums 是 header.vnums（這個檔的號碼範圍）；kind 是 header.type：world、dynamic、instance。"""
    return {
        "schema_version": 1,
        "file": filename,
        "area": {
            "header": {"levels": [1, 5], "author": "Test", "title": "測試", "vnums": list(vnums), "type": kind,
                       "reset_empty": None, "reset_players": None, "opened": None},
            "recall": None, "no_teleport": None, "clan_recall": None, "gem": None,
        },
        "rooms": rooms,
        "mobiles": list(mobiles),
        "objects": list(objects),
        "resets": list(resets),
    }


def write_json(folder, filename, data):
    path = folder / filename
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def write_area(folder, filename, rooms, vnums=(100, 199), mobiles=(), objects=(), kind="world"):
    return write_json(folder, filename, make_area(filename, rooms, vnums, mobiles, objects=objects, kind=kind))


def write_lua(folder, area_file, file, code):
    """寫一個腳本檔：區域檔 area_file（例如 "a.json"）的腳本放在同名的資料夾（folder/a/file）。"""
    target = folder / area_file.removesuffix(".json") / file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(code, encoding="utf-8")
    return target
