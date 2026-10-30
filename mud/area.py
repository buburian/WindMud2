"""區域：檢查並載入 areas/ 裡的區域檔。

區域檔是我們自己的格式，每個欄位的意思寫在 docs/區域製作手冊.md。
規則只在 check_files() 一份：伺服器開機（load）和檢查工具（python -m mud.areacheck）都用它。

號碼規則：檔案裡的房間號碼只能是 1～99，遊戲裡的號碼是 area.header.area_number 加上它。
要指到房間或物品時（to_room、key、recall），寫 1～99 是同一個區域（一樣加上 area_number），
100 以上是完整號碼（指到別的區域）。所以遊戲號碼 1～99 是保留的：有房間用了它，
別的區域寫 1～99 就分不出是指哪一個（area_number 不能是 0）。
"""
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

DIRECTIONS = {"north": "北", "east": "東", "south": "南", "west": "西", "up": "上", "down": "下"}
REVERSE = {"north": "south", "east": "west", "south": "north", "west": "east", "up": "down", "down": "up"}

# 手冊 room_flags 表裡有的旗標（2 沒有用到）
ROOM_FLAGS = (1, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768,
              65536, 131072, 262144, 524288, 1048576, 2097152, 4194304, 8388608)
SECTOR_MAX = 10                             # sector 是 0～10
LOCKS_MAX = 8                               # locks 是 0～8

# 每一層要剛好有這些欄位
TOP_KEYS = ("schema_version", "file", "area", "rooms")
AREA_KEYS = ("header", "recall", "no_teleport", "clan_recall", "gem")
HEADER_KEYS = ("levels", "author", "title", "area_number")
ROOM_KEYS = ("vnum", "name", "description", "room_flags", "sector", "exits", "extra_descriptions", "script")
EXIT_KEYS = ("description", "keywords", "locks", "key", "to_room")
EXTRA_KEYS = ("keywords", "description")
SCRIPT_KEYS = ("trigger", "function")
TRIGGER_KEYS = ("value", "names")


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


def resolve(base, number):
    """號碼規則：1～99 是同一個區域（加上 area_number），100 以上照寫的號碼。"""
    return base + number if number <= 99 else number


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)   # JSON 的 true 在 Python 也算 int，要排除


def check_files(paths, reference=()):
    """照手冊檢查區域檔，回傳 {檔案: [問題, …]}，沒問題就是空清單。

    reference 是其他拿來對照的檔案：只查一個檔時，靠它知道別的區域有哪些房間，
    才能檢查通到別的區域的出口、跨檔案的號碼重複。它們自己的問題不會報出來。
    """
    checked = {p.resolve() for p in paths}
    problems, found = {}, {}
    for path in paths:
        problems[path] = []
        data = read_json(path, problems[path])
        if data is not None:
            found[path] = check_structure(path.name, data, problems[path])

    # 跨檔案：遊戲號碼不能重複。先登記對照用的檔案，重複時算在要檢查的檔案頭上
    owner = {}
    for path in reference:
        if path.resolve() not in checked:
            for number in room_numbers(path):
                owner.setdefault(number, path.name)
    for path, info in found.items():
        for vnum in info.vnums:
            number = info.base + vnum
            if number in owner:
                problems[path].append(f"{path.name}：房間 {number} 跟 {owner[number]} 重複")
            else:
                owner[number] = path.name

    # 出口和 recall 指到的房間要存在
    for path, info in found.items():
        for vnum, d, to in info.exits:
            if resolve(info.base, to) not in owner:
                problems[path].append(f"{path.name}：房間 {vnum} 往 {d} 的出口指到不存在的房間 {resolve(info.base, to)}")
        if info.recall is not None and resolve(info.base, info.recall) not in owner:
            problems[path].append(f"{path.name}：area.recall 指到不存在的房間 {resolve(info.base, info.recall)}")
    return problems


class Found:
    """check_structure 找到、可以拿來做跨檔案檢查的東西。area_number 不對時全部是空的。"""

    def __init__(self):
        self.base = None                    # area_number
        self.vnums = []                     # 號碼沒問題的房間（檔案號碼）
        self.exits = []                     # [(房間檔案號碼, 方向, to_room)]：格式沒問題的出口
        self.recall = None                  # 格式沒問題的 recall


def read_json(path, problems):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as e:
        problems.append(f"{Path(path).name}：讀不到，或不是正確的 JSON（{e}）")
        return None


def room_numbers(path):
    """盡量算出一個檔案有哪些遊戲號碼（給對照用，格式不對的部分就略過）。"""
    data = read_json(path, [])
    try:
        base = data["area"]["header"]["area_number"]
        room_list = data["rooms"]
    except (KeyError, TypeError):
        return []
    if not is_int(base):
        return []
    return [base + r["vnum"] for r in room_list
            if isinstance(r, dict) and is_int(r.get("vnum")) and 1 <= r["vnum"] <= 99]


def check_keys(obj, keys, where, problems):
    """obj 要是 dict，而且欄位剛好是 keys。回傳 obj 是不是 dict。"""
    if not isinstance(obj, dict):
        problems.append(f"{where}要寫成 {{…}}，不能是 {obj!r}")
        return False
    problems += [f"{where}少了欄位 {k}" for k in keys if k not in obj]
    problems += [f"{where}多了不認得的欄位 {k}" for k in obj if k not in keys]
    return True


def check_structure(name, data, problems):
    """檢查一個檔案自己的結構，問題加進 problems。回傳 Found，給跨檔案檢查用。"""
    found = Found()
    if not check_keys(data, TOP_KEYS, f"{name}：檔案最上層", problems):
        return found
    if "schema_version" in data and not (is_int(data["schema_version"]) and data["schema_version"] == 1):
        problems.append(f"{name}：schema_version 要是 1，不能是 {data['schema_version']!r}")
    if "file" in data and data["file"] != name:
        problems.append(f"{name}：file 要寫實際的檔名 {name!r}，不能是 {data['file']!r}")
    base, recall = check_area(name, data["area"], problems) if "area" in data else (None, None)

    if "rooms" not in data:
        return found
    if not isinstance(data["rooms"], list):
        problems.append(f"{name}：rooms 要寫成 […]，不能是 {data['rooms']!r}")
        return found
    vnums, exits = [], []
    for i, r in enumerate(data["rooms"]):
        vnum = r.get("vnum") if isinstance(r, dict) else None
        where = f"{name}：房間 {vnum} " if is_int(vnum) else f"{name}：第 {i + 1} 間房間 "
        if not check_keys(r, ROOM_KEYS, where, problems):
            continue
        room_exits = check_room(where, r, problems)
        if "vnum" not in r:
            continue
        if not (is_int(vnum) and 1 <= vnum <= 99):
            problems.append(f"{name}：房間號碼 {vnum!r} 不在 1～99")
        elif vnum in vnums:
            problems.append(f"{name}：房間 {vnum} 在這個檔案裡重複")
        elif base is not None and base + vnum < 100:
            problems.append(f"{where}算出來的號碼 {base + vnum} 小於 100（1～99 是保留的，area_number 不能是 0）")
        else:
            vnums.append(vnum)
            exits += [(vnum, d, to) for d, to in room_exits]
    if base is not None:                    # 沒有 area_number 就算不出遊戲號碼，跨檔案的檢查只好略過
        found.base, found.vnums, found.exits, found.recall = base, vnums, exits, recall
    return found


def check_area(name, area, problems):
    """檢查 area 區塊。回傳 (area_number, recall)，不對的就是 None。"""
    base = recall = None
    if not check_keys(area, AREA_KEYS, f"{name}：area ", problems):
        return None, None
    header = area.get("header")
    if "header" in area and check_keys(header, HEADER_KEYS, f"{name}：area.header ", problems):
        levels = header.get("levels")
        if "levels" in header and not (isinstance(levels, list) and len(levels) == 2
                                       and all(is_int(x) for x in levels) and levels[0] <= levels[1]):
            problems.append(f"{name}：area.header.levels 要寫 [最低, 最高] 兩個整數，最低不能大於最高，不能是 {levels!r}")
        for k in ("author", "title"):
            if k in header and not isinstance(header[k], str):
                problems.append(f"{name}：area.header.{k} 要是字串，不能是 {header[k]!r}")
        if "area_number" in header:
            if is_int(header["area_number"]) and header["area_number"] >= 1:
                base = header["area_number"]
            else:
                problems.append(f"{name}：area.header.area_number 要是正整數（1～99 是保留的號碼，area_number 不能是 0），"
                                f"不能是 {header['area_number']!r}")
    if "recall" in area and area["recall"] is not None:
        if is_int(area["recall"]) and area["recall"] >= 1:
            recall = area["recall"]
        else:
            problems.append(f"{name}：area.recall 要是 null 或房間號碼，不能是 {area['recall']!r}")
    if "no_teleport" in area and not (area["no_teleport"] is None or (is_int(area["no_teleport"]) and area["no_teleport"] in (0, 1))):
        problems.append(f"{name}：area.no_teleport 要是 null、0 或 1，不能是 {area['no_teleport']!r}")
    for k in ("clan_recall", "gem"):
        if k in area and not (area[k] is None or (is_int(area[k]) and area[k] >= 0)):
            problems.append(f"{name}：area.{k} 要是 null 或不小於 0 的整數，不能是 {area[k]!r}")
    return base, recall


def check_room(where, r, problems):
    """檢查一間房間（號碼以外的部分）。回傳格式沒問題的出口 [(方向, to_room)]，給跨檔案檢查用。"""
    if "name" in r and not (isinstance(r["name"], str) and r["name"].strip()):
        problems.append(f"{where}的 name 不能是空的")
    if "description" in r and not isinstance(r["description"], str):
        problems.append(f"{where}的 description 要是字串，不能是 {r['description']!r}")
    if "room_flags" in r:
        try:
            unknown = parse_flags(r["room_flags"]) & ~sum(ROOM_FLAGS)
        except ValueError as e:
            problems.append(f"{where}的 room_flags {e}")
        else:
            if unknown:
                bits = [1 << i for i in range(unknown.bit_length()) if unknown >> i & 1]
                problems.append(f"{where}的 room_flags 用了沒有的旗標 {bits}")
    if "sector" in r and not (is_int(r["sector"]) and 0 <= r["sector"] <= SECTOR_MAX):
        problems.append(f"{where}的 sector 要寫 0～{SECTOR_MAX} 的整數，不能是 {r['sector']!r}")

    exits = []
    if "exits" in r:
        if not isinstance(r["exits"], dict):
            problems.append(f"{where}的 exits 要寫成 {{…}}，不能是 {r['exits']!r}")
        else:
            for d, e in r["exits"].items():
                if d not in DIRECTIONS:
                    problems.append(f"{where}的出口方向 {d!r} 不對（只能是 {'、'.join(DIRECTIONS)}）")
                elif check_exit(f"{where}往 {d} 的出口", e, problems):
                    exits.append((d, e["to_room"]))
    if "extra_descriptions" in r:
        if not isinstance(r["extra_descriptions"], list):
            problems.append(f"{where}的 extra_descriptions 要寫成 […]，不能是 {r['extra_descriptions']!r}")
        else:
            for j, ed in enumerate(r["extra_descriptions"]):
                w = f"{where}的 extra_descriptions 第 {j + 1} 項"
                if check_keys(ed, EXTRA_KEYS, w, problems):
                    if "keywords" in ed and not (isinstance(ed["keywords"], str) and ed["keywords"].split()):
                        problems.append(f"{w}的 keywords 不能是空的")
                    if "description" in ed and not isinstance(ed["description"], str):
                        problems.append(f"{w}的 description 要是字串，不能是 {ed['description']!r}")
    if "script" in r and r["script"] is not None:
        check_script(f"{where}的 script ", r["script"], problems)
    return exits


def check_exit(where, e, problems):
    """檢查一個出口。回傳 to_room 能不能拿來做跨檔案檢查。"""
    if not check_keys(e, EXIT_KEYS, where, problems):
        return False
    for k in ("description", "keywords"):
        if k in e and not isinstance(e[k], str):
            problems.append(f"{where}的 {k} 要是字串，不能是 {e[k]!r}")
    if "locks" in e and not (is_int(e["locks"]) and 0 <= e["locks"] <= LOCKS_MAX):
        problems.append(f"{where}的 locks 要是 0～{LOCKS_MAX} 的整數，不能是 {e['locks']!r}")
    if "key" in e and not (is_int(e["key"]) and e["key"] >= -1):
        problems.append(f"{where}的 key 要是 -1、0 或物品號碼，不能是 {e['key']!r}")
    if "to_room" not in e:
        return False
    if not (is_int(e["to_room"]) and e["to_room"] >= 1):
        problems.append(f"{where}號碼 {e['to_room']!r} 不對")
        return False
    return True


def check_script(where, s, problems):
    """script 先保留，只檢查形狀：{"trigger": {"value": 整數, "names": [字串…]}, "function": 字串}。"""
    if not check_keys(s, SCRIPT_KEYS, where, problems):
        return
    if "trigger" in s and check_keys(s["trigger"], TRIGGER_KEYS, f"{where}的 trigger ", problems):
        t = s["trigger"]
        if "value" in t and not (is_int(t["value"]) and t["value"] >= 0):
            problems.append(f"{where}的 trigger.value 要是不小於 0 的整數，不能是 {t['value']!r}")
        if "names" in t and not (isinstance(t["names"], list) and all(isinstance(x, str) for x in t["names"])):
            problems.append(f"{where}的 trigger.names 要是字串的清單，不能是 {t['names']!r}")
    if "function" in s and not (isinstance(s["function"], str) and s["function"].strip()):
        problems.append(f"{where}的 function 不能是空的")


def build_room(base, r):
    """把一個（已經檢查過的）房間變成 Room。"""
    exits = {d: resolve(base, e["to_room"]) for d, e in r["exits"].items()}
    exit_descriptions = {d: e["description"] for d, e in r["exits"].items()}
    # 名字用空白隔開（例如 "牌子 sign"），存成小寫，英文比對時不分大小寫
    extra_descriptions = [([k.lower() for k in ed["keywords"].split()], ed["description"])
                          for ed in r["extra_descriptions"]]
    return Room(base + r["vnum"], r["name"], r["description"], exits, parse_flags(r["room_flags"]), r["sector"],
                exit_descriptions, extra_descriptions)


def load(directory):
    """檢查並讀 directory 裡全部的 *.json。

    有任何問題就丟 ValueError（訊息是第一個問題），原本載入的房間不動。
    """
    paths = sorted(Path(directory).glob("*.json"))
    problems = check_files(paths, paths)
    found = [p for path in paths for p in problems[path]]
    if found:
        more = f"（共 {len(found)} 個問題，用 uv run python -m mud.areacheck 看全部）" if len(found) > 1 else ""
        raise ValueError(found[0] + more)
    loaded = {}
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        base = data["area"]["header"]["area_number"]
        for r in data["rooms"]:
            room = build_room(base, r)
            loaded[room.vnum] = room
    rooms.clear()
    rooms.update(loaded)
    log.info(f"載入 {len(paths)} 個區域、{len(rooms)} 個房間")
