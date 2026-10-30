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

    def __init__(self, vnum, name, description, exits, room_flags, sector, exit_descriptions, extra_descriptions):
        self.vnum = vnum
        self.name = name
        self.description = description
        self.exits = exits                  # 方向 → 房間 vnum
        self.room_flags = room_flags        # 房間旗標（數字，用 | 合起來的）
        self.sector = sector                # 地形代號
        self.exit_descriptions = exit_descriptions    # 方向 → 往那個方向看到的樣子（look 方向）
        self.extra_descriptions = extra_descriptions  # [(小寫的名字們, 描述)]：可以細看的東西（look 牌子）


rooms = {}  # vnum → Room


def parse_flags(value):
    """room_flags 的寫法：數字（0、5），或字串（"0"、"5"、"1|4"，用 | 把幾個數字合起來）。

    "1|4" 跟 5 一樣。格式不對就丟 ValueError。
    """
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"要寫數字或字串，不能是 {value!r}")
    parts = [value] if isinstance(value, int) else [p.strip() for p in value.split("|")]
    result = 0
    for p in parts:
        if isinstance(p, str):
            if not (p.isascii() and p.isdigit()):
                raise ValueError(f"看不懂 {value!r}")
            p = int(p)
        if p < 0:
            raise ValueError(f"不能是負數：{value!r}")
        result |= p
    return result


def parse_room(filename, base, r):
    """把區域檔裡的一個房間變成 Room。格式不對丟 ValueError；少了欄位會丟 KeyError，由 load() 轉成 ValueError。"""
    if not 1 <= r["vnum"] <= 99:
        raise ValueError(f"{filename}：房間號碼 {r['vnum']} 不在 1～99")
    vnum = base + r["vnum"]
    if vnum < 100:
        raise ValueError(f"{filename}：房間 {r['vnum']} 算出來的號碼 {vnum} 小於 100"
                         "（1～99 是保留的，area_number 不能是 0）")
    exits, exit_descriptions = {}, {}
    for d, e in r.get("exits", {}).items():
        to = e["to_room"]
        if to < 1:
            raise ValueError(f"{filename}：房間 {r['vnum']} 往 {d} 的出口號碼 {to} 不對")
        exits[d] = base + to if to <= 99 else to
        exit_descriptions[d] = e["description"]
    # 名字用空白隔開（例如 "牌子 sign"），存成小寫，英文比對時不分大小寫
    extra_descriptions = [([k.lower() for k in ed["keywords"].split()], ed["description"])
                          for ed in r["extra_descriptions"]]
    try:
        room_flags = parse_flags(r["room_flags"])
    except ValueError as e:
        raise ValueError(f"{filename}：房間 {r['vnum']} 的 room_flags {e}") from None
    sector = r["sector"]                    # 地形一間房只有一種：只能寫一個整數
    if isinstance(sector, bool) or not isinstance(sector, int) or sector < 0:
        raise ValueError(f"{filename}：房間 {r['vnum']} 的 sector 要寫一個整數，不能是 {sector!r}")
    return Room(vnum, r["name"], r["description"], exits, room_flags, sector,
                exit_descriptions, extra_descriptions)


def load(directory):
    """讀 directory 裡全部的 *.json。

    號碼規則：檔案裡的房間號碼只能是 1～99，遊戲裡的號碼是 area.header.area_number 加上它。
    出口的 to_room 寫 1～99 是同一個區域（一樣加上 area_number），100 以上是完整號碼（通到別的區域）。
    所以遊戲號碼 1～99 是保留的：有房間用了它，別的區域寫 to_room 就分不出是哪一個（area_number 不能是 0）。

    格式不對、遊戲號碼重複、出口通到不存在的房間都算錯：丟 ValueError，原本載入的房間不動。
    """
    files = sorted(Path(directory).glob("*.json"))
    loaded = {}
    where = {}                              # 遊戲號碼 → 檔名，報錯用
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        try:
            base = data["area"]["header"]["area_number"]
        except (KeyError, TypeError):
            raise ValueError(f"{path.name}：area.header 裡沒有 area_number") from None
        for r in data.get("rooms", []):
            try:
                room = parse_room(path.name, base, r)
            except KeyError as e:
                raise ValueError(f"{path.name}：房間 {r.get('vnum', '?')} 少了欄位 {e.args[0]}") from None
            if room.vnum in loaded:
                raise ValueError(f"{path.name}：房間 {room.vnum} 跟 {where[room.vnum]} 重複")
            loaded[room.vnum] = room
            where[room.vnum] = path.name
    for room in loaded.values():
        for d, to in room.exits.items():
            if to not in loaded:
                raise ValueError(f"{where[room.vnum]}：房間 {room.vnum} 往 {d} 的出口指到不存在的房間 {to}")
    rooms.clear()
    rooms.update(loaded)
    log.info(f"載入 {len(files)} 個區域、{len(rooms)} 個房間")
