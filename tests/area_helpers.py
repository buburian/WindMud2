"""測試用：做出一份完整、正確的區域資料（每個欄位都有），各測試再改其中的欄位。"""
import json


def make_exit(to_room, description=""):
    return {"description": description, "keywords": "", "locks": 0, "key": -1, "to_room": to_room}


def make_room(vnum, **exits):
    """exits 寫成 north=2 這樣：方向＝to_room。"""
    return {"vnum": vnum, "name": f"房間{vnum}", "description": "", "room_flags": 0, "sector": 0,
            "exits": {d: make_exit(to) for d, to in exits.items()}, "extra_descriptions": [], "script": None}


def make_area(filename, rooms, area_number=100):
    return {
        "schema_version": 1,
        "file": filename,
        "area": {
            "header": {"levels": [1, 5], "author": "Test", "title": "測試", "area_number": area_number},
            "recall": None, "no_teleport": None, "clan_recall": None, "gem": None,
        },
        "rooms": rooms,
    }


def write_json(folder, filename, data):
    path = folder / filename
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def write_area(folder, filename, rooms, area_number=100):
    return write_json(folder, filename, make_area(filename, rooms, area_number))
