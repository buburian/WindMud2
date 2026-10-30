"""區域：開機時從 areas/ 載入房間。

區域檔是我們自己的格式（目前以 area2json 的輸出打底），只取用得到的欄位，其他欄位不管。
"""
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

DIRECTIONS = {"north": "北", "east": "東", "south": "南", "west": "西", "up": "上", "down": "下"}
REVERSE = {"north": "south", "east": "west", "south": "north", "west": "east", "up": "down", "down": "up"}


class Room:
    """一個房間。"""

    def __init__(self, vnum, name, description, exits):
        self.vnum = vnum
        self.name = name
        self.description = description
        self.exits = exits                  # 方向 → 房間 vnum


rooms = {}  # vnum → Room


def load(directory):
    """讀 directory 裡全部的 *.json。

    重複的 vnum、出口指到不存在的房間都算錯：丟 ValueError，原本載入的房間不動。
    """
    files = sorted(Path(directory).glob("*.json"))
    loaded = {}
    where = {}                              # vnum → 檔名，報錯用
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        for r in data.get("rooms", []):
            vnum = r["vnum"]
            if vnum in loaded:
                raise ValueError(f"{path.name}：房間 {vnum} 跟 {where[vnum]} 重複")
            exits = {d: e["to_room"] for d, e in r.get("exits", {}).items()}
            loaded[vnum] = Room(vnum, r["name"], r["description"], exits)
            where[vnum] = path.name
    for room in loaded.values():
        for d, to in room.exits.items():
            if to not in loaded:
                raise ValueError(f"{where[room.vnum]}：房間 {room.vnum} 往 {d} 的出口指到不存在的房間 {to}")
    rooms.clear()
    rooms.update(loaded)
    log.info(f"載入 {len(files)} 個區域、{len(rooms)} 個房間")
