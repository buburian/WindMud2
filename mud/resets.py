"""重置：照區域檔的 resets 把生物放進房間，照 C 版（db.c 的 area_update、reset_area）定時再做一次。

M（把生物放進房間）、G（給生物物品）、O（物品放進房間）、P（物品放進容器）、D（門的狀態）、R（打亂出口）都照手冊 resets 那章做。
每個區域物件記住它有哪些區域檔（世界有很多個），每個區域檔各自算時間：
建立區域物件時重置一次；之後每 AREA_TICKS 個 tick 呼叫 update()：
沒有玩家時大約 3 分鐘重置一次，有玩家時大約 15 分鐘，重置前 1 分鐘醒著的玩家會聽到腳步聲。
"""
import logging
import random

from . import doors, objects
from .act import notify
from .area import CHANCE_MAX, DIRECTIONS, ActFlag, DoorState, parse_flags, resolve
from .characters import Position, characters
from .npcs import Npc, spawn
from .players import online_players

log = logging.getLogger(__name__)

RESET_MIN_AGE = 3                           # age 到這個數字以後，沒有玩家就重置（約 3 分鐘）
RESET_AGE = 15                              # 有玩家時 age 到這個數字才重置（約 15 分鐘）
FOOTSTEPS = "你聽到一陣腳步聲。"              # 有玩家時，重置前 1 分鐘（age 14）送給區域裡醒著的玩家
SURE_RARE = 10                              # 出現機率 rare 0～10 一定出現；大於 10 是 (rare − 10) ÷ 10000

mobiles = {}                                # 遊戲號碼 → (那個區域檔的 area_number, 區域檔的生物)（zones.load 填，跨檔案也找得到）


class AreaReset:
    """一個區域檔在一個區域物件裡：重置要用的資料，和它自己的時間（age）。房間的 room.area 指到這裡。"""

    def __init__(self, name, base, data):
        self.name = name                    # 檔名
        self.base = base                    # area_number
        self.data = data                    # 讀好、檢查過的區域檔
        self.age = 0                        # 上次重置後過了幾次 update（C 版的 pArea->age）


def update(zone, rng=random):
    """照 C 版的 area_update：zone 裡每個區域檔 age 加 1，該重置的就重置。"""
    for area in zone.areas:
        area.age += 1
        if area.age < RESET_MIN_AGE:
            continue
        players = [p for p in online_players() if p.room.zone is zone and p.room.area is area]
        if players and area.age == RESET_AGE - 1:
            for p in players:
                if p.position > Position.SLEEPING:
                    notify(p, FOOTSTEPS)
        if not players or area.age >= RESET_AGE:
            reset_area(zone, area, mobiles, rng)
            area.age = rng.randint(0, RESET_MIN_AGE)


def reset_zone(zone, rng=random):
    """建立區域物件時：每個區域檔都重置一次。"""
    for area in zone.areas:
        reset_area(zone, area, mobiles, rng)


def reset_area(zone, area, protos, rng=random):
    """照順序做區域檔的 resets（照 C 版 reset_area）。protos 是 mobiles 這種表：遊戲號碼 → (area_number, 區域檔的生物)。

    G 對「前面最近的那一筆 M 這一次放出來的生物」做事：那筆 M 沒放出生物，後面的 G 也不做。
    """
    last_mob = None
    for r in area.data["resets"]:
        cmd = r["cmd"]
        if cmd == "M":
            last_mob = reset_mobile(zone, area, r, protos, rng)
        elif cmd == "G":
            reset_give(area, r, last_mob, rng)
        elif cmd == "O":
            reset_object(zone, area, r, rng)
        elif cmd == "P":
            reset_put(zone, area, r, rng)
        elif cmd == "D":
            reset_door(zone, area, r)
        elif cmd == "R":
            reset_exits(zone, area, r, rng)


def appears(r, rng):
    """出現機率 rare（M、G）：0～10 一定出現；大於 10 是 (rare − 10) ÷ 10000。"""
    return r["rare"] <= SURE_RARE or rng.randrange(CHANCE_MAX) < r["rare"] - SURE_RARE


def reset_mobile(zone, area, r, protos, rng):
    """M：生物放進房間。出現機率沒骰到、或已經有 limit 隻就不放。回傳放出來的生物（之後的 G 用），沒放是 None。"""
    vnum, room_vnum = resolve(area.base, r["mob_vnum"]), resolve(area.base, r["room_vnum"])
    base, proto = protos.get(vnum, (None, None))
    room = zone.rooms.get(room_vnum)
    if proto is None or room is None:       # 號碼存不存在還沒檢查：先記 log 跳過
        log.warning(f"{area.name} 的 M 放不了：生物 {vnum} 或房間 {room_vnum} 不在{zone.name}裡")
        return None
    if not appears(r, rng):
        return None
    # limit：待在原地的（sentinel）數這個房間；其他數同一個區域物件（每份副本各自算，手冊寫的「整個遊戲」改成這樣）
    sentinel = ActFlag.SENTINEL in ActFlag(parse_flags(proto["act"]))
    count = sum(1 for c in characters if isinstance(c, Npc) and c.vnum == vnum
                and (c.room is room if sentinel else c.room.zone is zone))
    if count >= r["limit"]:
        return None
    return spawn(vnum, proto, room, rng, base)


def reset_door(zone, area, r):
    """D：設定門的狀態，這一邊和對面那一邊一起設（一筆就夠，C 版一筆只設一邊）。

    房間不在這個區域物件、或那個方向沒有門：還沒檢查，先記 log 跳過。
    """
    room_vnum = resolve(area.base, r["room_vnum"])
    room = zone.rooms.get(room_vnum)
    if room is None or r["direction"] not in room.doors:
        log.warning(f"{area.name} 的 D 設不了：房間 {room_vnum} 不在{zone.name}裡，或往 {r['direction']} 沒有門")
        return
    doors.set_state(room, r["direction"], DoorState(r["state"]))


def reset_give(area, r, mob, rng):
    """G：給前面那筆 M 這一次放出來的生物一件物品，放進牠的背包。level 是 null 就用那隻生物的等級。limit 不用（C 版沒用到）。"""
    if mob is None or not appears(r, rng):
        return
    level = mob.level if r["level"] is None else r["level"]
    obj = objects.create(resolve(area.base, r["obj_vnum"]), level, r["color"], rng)
    if obj is not None:
        mob.carrying.insert(0, obj)


def players_in(zone, area):
    """這個區域檔在 zone 裡的房間有沒有玩家（C 版的 pArea->nplayer）。"""
    return any(p.room is not None and p.room.zone is zone and p.room.area is area for p in online_players())


def reset_object(zone, area, r, rng):
    """O：物品放進房間地上。區域檔的房間裡沒有玩家、房間地上也還沒有這件物品（同號碼）時才放（照 C 版）。"""
    vnum, room_vnum = resolve(area.base, r["obj_vnum"]), resolve(area.base, r["room_vnum"])
    room = zone.rooms.get(room_vnum)
    if room is None:
        log.warning(f"{area.name} 的 O 放不了：房間 {room_vnum} 不在{zone.name}裡")
        return
    if players_in(zone, area) or any(o.vnum == vnum for o in room.contents):
        return
    obj = objects.create(vnum, r["level"], r["color"], rng)
    if obj is not None:
        room.contents.insert(0, obj)


def objects_in(zone):
    """zone 裡的物品：每間房地上的，和生物背包裡的（P 找容器用）。"""
    for room in zone.rooms.values():
        yield from room.contents
    for c in characters:
        if isinstance(c, Npc) and c.room is not None and c.room.zone is zone:
            yield from c.carrying


def reset_put(zone, area, r, rng):
    """P：物品放進容器（zone 裡第一件 container_vnum 的物品）。容器裡還沒有這件物品時才放（照 WindSrc：有玩家也放）。"""
    vnum, container_vnum = resolve(area.base, r["obj_vnum"]), resolve(area.base, r["container_vnum"])
    container = next((o for o in objects_in(zone) if o.vnum == container_vnum), None)
    if container is None:
        log.warning(f"{area.name} 的 P 放不了：{zone.name}裡沒有容器 {container_vnum}")
        return
    if any(o.vnum == vnum for o in container.contains):
        return
    obj = objects.create(vnum, r["level"], r["color"], rng)
    if obj is not None:
        container.contains.insert(0, obj)


def reset_exits(zone, area, r, rng):
    """R：房間前 exit_count 個方向（北、東、南、西、上、下）的出口隨機對調（照 C 版：d0 跟 d0～最後一個裡隨機一個換）。

    出口、出口的描述、門一起換。對面的房間不動，所以走過去再走回來不一定回得來（舊版做迷宮用的）。
    """
    room = zone.rooms.get(resolve(area.base, r["room_vnum"]))
    if room is None:
        log.warning(f"{area.name} 的 R 做不了：房間 {r['room_vnum']} 不在{zone.name}裡")
        return
    dirs = list(DIRECTIONS)[:r["exit_count"]]
    for d0 in range(len(dirs) - 1):
        swap_exits(room, dirs[d0], dirs[rng.randint(d0, len(dirs) - 1)])


def swap_exits(room, a, b):
    """room 往 a、往 b 的出口對調（沒有的那一邊就變成沒有）。"""
    for table in (room.exits, room.exit_descriptions, room.doors):
        here, there = table.pop(a, None), table.pop(b, None)
        if there is not None:
            table[a] = there
        if here is not None:
            table[b] = here
