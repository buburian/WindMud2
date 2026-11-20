"""書商賣的地圖：程式照區域檔的房間和出口自己畫（使用者 2026-11-20 要的，規則在玩家角色手冊「地圖」）。

手畫的地圖會跟改過的區域對不上，所以地圖物品的內容由這裡畫：`look map` 時 objects.extra_descriptions() 問 text()。
哪一件物品畫哪個區域檔寫在 MAPS（不改區域檔的格式，使用者核准的計畫）；之後別的區域要賣地圖，在這裡加一行。

畫哪些房間（rooms_to_draw）：
- 只走「兩邊都通」的東南西北出口（走過去，往反方向走回得來）。迷宮（夢幻草原的迷霧）、急流、地洞這種走過去回不來的不畫，
  上樓下樓也不畫（使用者要的：迷宮跳過不畫）。
- 室內（RoomFlag.INDOORS）的房間只畫走進去的第一間，當作建築物的門口、標字母；建築物裡面不畫。
- 一個區域畫最大的那一片連在一起的室外房間。
排位置（layout）：東西相連的同一排、南北相連的同一欄，再照方向排前後（最長路徑，再往鄰居的中間拉，線越短越好）。
撞在同一格、線穿過別的房間、兩條線交叉，就多加一條「誰在誰前面」把它們推開，再排一次。
第一次有人看的時候畫，記起來；zones.load() 換了世界（重開伺服器）才重畫。
"""
import logging
from collections import defaultdict, deque

from .area import RoomFlag

log = logging.getLogger(__name__)

# 地圖物品的號碼 → 畫哪個區域檔（都是秋風城地圖店的書商賣的，areas/midgaard.json）
MAPS = {
    3391: "midgaard.json",                  # 秋風城地圖
    3394: "forest.json",                    # 城西森林地圖
    3395: "foresteast.json",                # 城東森林地圖
    3396: "north_plains.json",              # 城北平原地圖
    3397: "river.json",                     # 河流區地圖
}
KEYWORD = "地圖"                             # look 地圖：地圖物品除了自己的英文名字，打中文也看得到

REVERSE = {"north": "south", "south": "north", "east": "west", "west": "east"}   # 只畫東南西北（上面是北），上下不畫
ROOM, BLANK, ACROSS, DOWN, CROSS = "口", "　", "－", "｜", "＋"   # 全形字：Big5 都有，固定佔 2 格
LETTERS = [chr(c) for c in range(ord("Ａ"), ord("Ｚ") + 1)] + [chr(c) for c in range(ord("ａ"), ord("ｚ") + 1)]
OVERFLOW = "＊"                              # 字母用完（超過 52 個要標的地方）
WIDTH = 79                                  # 每行最多幾格（跟 score 一樣）
GAP = "　"                                   # 說明一項一項之間
TO = "往"                                    # 通到別的區域的出口：「Ａ 往秋風城」
FOOTER = "地圖的上方是北方。迷霧、樓上樓下、建築物裡面沒有畫。"
SWEEPS = 60                                 # 往鄰居中間拉幾輪
MAX_PUSHES = 500                            # 最多推開幾次（真的區域用不到這麼多；超過就照現在的樣子畫、記 log）

_world = None                               # 畫的時候的 zones.world：換了就全部重畫
_drawn = {}                                 # 區域檔名 → 畫好的地圖


def text(obj):
    """obj 是地圖就回傳畫好的地圖（文字），不是是 None。"""
    name = MAPS.get(getattr(obj, "vnum", None))
    return draw(name) if name else None


def draw(name):
    """區域檔 name（世界區域）的地圖：標題、圖、字母的說明、最後一行說明。沒載入這個區域檔是 None。"""
    global _world
    from . import zones                     # 坑：zones → resets → objects → maps，在函式裡才 import
    if zones.world is not _world:
        _world = zones.world
        _drawn.clear()
    if name not in _drawn:
        _drawn[name] = render(name, zones)
    return _drawn[name]


def render(name, zones):
    """畫 name 這個區域檔的地圖（draw() 記起來）。"""
    rooms = {v: r for v, r in (zones.world.rooms.items() if zones.world else []) if r.area.name == name}
    if not rooms:
        return None
    header = next(iter(rooms.values())).area.data["area"]["header"]
    drawn, edges, doors = rooms_to_draw(rooms)
    pos = layout(drawn, edges)
    names = labels(rooms, drawn, doors, pos, zones)
    letter = {v: (LETTERS[i] if i < len(LETTERS) else OVERFLOW) for i, v in enumerate(names)}
    from .commands.system import wrap       # 坑：commands → objects → maps，在函式裡才 import
    legend = [line.rstrip(GAP) for line in wrap([f"{letter[v]} {names[v]}" for v in names], WIDTH, sep=GAP)]
    levels = header.get("levels")
    title = header["title"] + (f"（{levels[0]}～{levels[1]} 級）" if levels else "")
    return "\n".join([title, *grid(pos, edges, letter), *(legend if names else []), FOOTER]) + "\n"


def two_way(rooms, v):
    """v 往東南西北、兩邊都通的出口：(方向, 對面)。走過去再往反方向走回得來才算（迷宮、急流這種單向的不算）。"""
    for d, t in rooms[v].exits.items():
        if d in REVERSE and t in rooms and t != v and rooms[t].exits.get(REVERSE[d]) == v:
            yield d, t


def rooms_to_draw(rooms):
    """要畫的房間、線、建築物的門口：一片室外房間（兩邊都通的出口連在一起），加上連著它們的第一間室內房間。
    畫的是從別的區域走得進來的那幾片裡最大的（迷宮那一片通常比較大，但不通到外面）；都不通外面就畫最大的。
    線只畫至少一頭在室外的（兩間店裡面相通不畫）。回傳 (房間的號碼, {(房間, 方向, 對面)}, 門口的號碼)。"""
    inside = {v for v, r in rooms.items() if RoomFlag.INDOORS in r.room_flags}
    best, best_key, seen = set(), None, set()
    for start in sorted(rooms):
        if start in inside or start in seen:
            continue
        part, todo = {start}, deque([start])
        while todo:
            v = todo.popleft()
            for _d, t in two_way(rooms, v):
                if t not in inside and t not in part:
                    part.add(t)
                    todo.append(t)
        seen |= part
        key = (any(t not in rooms for v in part for t in rooms[v].exits.values()), len(part))
        if best_key is None or key > best_key:
            best, best_key = part, key
    doors = {t for v in best for _d, t in two_way(rooms, v) if t in inside}
    drawn = best | doors
    edges = {(v, d, t) for v in drawn for d, t in two_way(rooms, v)
             if t in drawn and d in ("east", "south") and not (v in inside and t in inside)}
    return drawn, edges, doors


class Groups:
    """union-find：同一排（東西相連）、同一欄（南北相連）的房間。"""

    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def join(self, a, b):
        self.parent[self.find(a)] = self.find(b)


def axis(groups, before):
    """一個方向（橫的或直的）每一組的位置：before 是 (a, b)，a 要在 b 前面（小）。排不出來（繞成一圈）是 None。
    先最長路徑排好，再一組一組往鄰居的中間拉（不違反前後），線越短越好；最小的是 0。"""
    after, prev = defaultdict(set), defaultdict(set)
    for a, b in before:
        after[a].add(b)
        prev[b].add(a)
    waiting = {g: len(prev[g]) for g in groups}
    todo = deque(sorted(g for g in groups if waiting[g] == 0))
    order = []
    while todo:
        a = todo.popleft()
        order.append(a)
        for b in sorted(after[a]):
            waiting[b] -= 1
            if waiting[b] == 0:
                todo.append(b)
    if len(order) != len(groups):
        return None
    pos = dict.fromkeys(groups, 0)
    for a in order:
        for b in after[a]:
            pos[b] = max(pos[b], pos[a] + 1)
    for _ in range(SWEEPS):
        moved = False
        for g in order:
            want = sorted([pos[p] + 1 for p in prev[g]] + [pos[s] - 1 for s in after[g]])
            if want:
                low = max((pos[p] + 1 for p in prev[g]), default=-len(groups))
                high = min((pos[s] - 1 for s in after[g]), default=len(groups) * 2)
                new = min(max(want[len(want) // 2], low), high)
                moved = moved or new != pos[g]
                pos[g] = new
        if not moved:
            break
    least = min(pos.values(), default=0)
    return {g: p - least for g, p in pos.items()}


def layout(drawn, edges):
    """每間房在地圖上的位置 {房間: (x, y)}（一格一個地點，x 往右是東、y 往下是南）。"""
    rows, cols = Groups(), Groups()
    for v in drawn:
        rows.find(v)
        cols.find(v)
    for v, d, t in sorted(edges):
        (rows if d == "east" else cols).join(v, t)
    xs = {(cols.find(v), cols.find(t)) for v, d, t in edges if d == "east"}
    ys = {(rows.find(v), rows.find(t)) for v, d, t in edges if d == "south"}
    groups = {"x": (cols.find, xs, {cols.find(v) for v in drawn}), "y": (rows.find, ys, {rows.find(v) for v in drawn})}
    pos = place(drawn, rows, cols, groups)
    if pos is None:                         # 出口的方向互相矛盾、繞成一圈排不出前後（現在的區域沒有）：全部排成一列
        log.warning("地圖排不出前後：出口的方向互相矛盾")
        return {v: (i, 0) for i, v in enumerate(sorted(drawn))}
    given_up = set()                        # 推不開的（照樣畫：交叉畫成＋）
    for _ in range(MAX_PUSHES):
        found = clashes(pos, edges, given_up)
        if not found:
            break
        kind, key, ways = found[0]
        best = None                         # 每一種推法都試，留下推完問題最少、線最短的（一次只看眼前的會越推越亂）
        for which, a, b in ways:
            find, pairs, _ = groups[which]
            pair = (find(a), find(b))
            if pair[0] == pair[1] or pair in pairs:
                continue
            pairs.add(pair)
            tried = place(drawn, rows, cols, groups)
            pairs.discard(pair)
            if tried is not None:
                score = (len(clashes(tried, edges, given_up)), spread(tried, edges))
                if best is None or score < best[0]:
                    best = score, which, pair, tried
        if best is None:
            given_up.add(key)
            if kind != "cross":
                log.warning(f"地圖排不開：{key} 撞在一起，照現在的樣子畫")
            continue
        _score, which, pair, pos = best
        groups[which][1].add(pair)
    return pos


def place(drawn, rows, cols, groups):
    """照現在的前後排每間房的位置；繞成一圈排不出來是 None。"""
    x_at, y_at = axis(groups["x"][2], groups["x"][1]), axis(groups["y"][2], groups["y"][1])
    if x_at is None or y_at is None:
        return None
    return {v: (x_at[cols.find(v)], y_at[rows.find(v)]) for v in drawn}


def spread(pos, edges):
    """線加起來多長、地圖多寬多高：一樣沒問題的排法，挑小的。"""
    xs, ys = [x for x, _ in pos.values()], [y for _, y in pos.values()]
    return sum(abs(pos[t][0] - pos[v][0]) + abs(pos[t][1] - pos[v][1]) for v, _d, t in edges) + max(xs) + max(ys)


def clashes(pos, edges, given_up):
    """要推開的地方 [(種類, 記號, ways)]（推不開、放棄的不算）。
    種類：same 兩間撞在同一格、through 線穿過別的房間、cross 一橫一直兩條線交叉。
    ways 是可以推開它的辦法：(x 或 y, a, b) 是「a 那一欄（排）要在 b 那一欄（排）前面」。"""
    found = []
    at = {}
    for v in sorted(pos):
        u = at.get(pos[v])
        if u is not None and ("same", u, v) not in given_up:
            found.append(("same", ("same", u, v), [("x", u, v), ("x", v, u), ("y", u, v), ("y", v, u)]))
        at.setdefault(pos[v], v)
    across, down = {}, {}                   # 線經過的格子（兩間房中間的那些）→ 那條線 (起點, 終點)
    for v, d, t in sorted(edges):
        (x1, y1), (x2, y2) = pos[v], pos[t]
        east = d == "east"
        for c in ([(x, y1) for x in range(x1 + 1, x2)] if east else [(x1, y) for y in range(y1 + 1, y2)]):
            u = at.get(c)
            if u is not None and ("through", u, v) not in given_up:
                # 房間 u 擋在 v～t 的線上：u 移到線的前面或後面，或移到別排（別欄）
                along, other = ("x", "y") if east else ("y", "x")
                found.append(("through", ("through", u, v), [(along, u, v), (along, t, u), (other, u, v), (other, v, u)]))
            (across if east else down)[c] = (v, t)
    for c in sorted(across):
        if c in down and ("cross", c) not in given_up:
            (a, a2), (b, b2) = across[c], down[c]
            # 橫線 a～a2、直線 b～b2 交叉：直線移到橫線的左邊或右邊，或橫線移到直線的上面或下面
            found.append(("cross", ("cross", c), [("x", b, a), ("x", a2, b), ("y", a, b), ("y", b2, a)]))
    return found


def labels(rooms, drawn, doors, pos, zones):
    """要標字母的地方，照位置從左上到右下：{房間: 說明}。建築物的門口寫房間名稱，通到別的區域的出口寫「往」＋區域名稱。"""
    found = {}
    for v in drawn:
        if v in doors:
            found[v] = rooms[v].name
            continue
        places = []
        for t in rooms[v].exits.values():
            title = area_title(t, zones)
            if t not in rooms and title and TO + title not in places:
                places.append(TO + title)
        if places:
            found[v] = "、".join(places)
    return {v: found[v] for v in sorted(found, key=lambda v: (pos[v][1], pos[v][0]))}


def area_title(vnum, zones):
    """房間 vnum 在哪個區域檔（世界、動態區域）的 header.title；找不到是 None。"""
    room = zones.world.rooms.get(vnum)
    if room is not None:
        return room.area.data["area"]["header"]["title"]
    name = zones.dynamic_rooms.get(vnum)
    return zones.templates[name][1]["area"]["header"]["title"] if name in zones.templates else None


def grid(pos, edges, letter):
    """畫出來的每一行：房間是「口」（要標的地方是字母），中間一格放線（－、｜，交叉是＋）。行尾的空白拿掉。"""
    if not pos:
        return []
    width = max(x for x, _ in pos.values()) * 2 + 1
    height = max(y for _, y in pos.values()) * 2 + 1
    cells = [[BLANK] * width for _ in range(height)]
    for v, d, t in edges:
        (x1, y1), (x2, y2) = pos[v], pos[t]
        if d == "east":
            for x in range(x1 * 2 + 1, x2 * 2):
                cells[y1 * 2][x] = CROSS if cells[y1 * 2][x] == DOWN else ACROSS
        else:
            for y in range(y1 * 2 + 1, y2 * 2):
                cells[y][x1 * 2] = CROSS if cells[y][x1 * 2] == ACROSS else DOWN
    for v, (x, y) in pos.items():
        cells[y * 2][x * 2] = letter.get(v, ROOM)
    return ["".join(row).rstrip(BLANK) for row in cells]
