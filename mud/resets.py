"""重置：照區域檔的 resets 把生物放進房間，照 C 版（db.c 的 area_update、reset_area）定時再做一次。

現在做 M（把生物放進房間）和 D（門的狀態）；G、O、P（物品）、R（打亂出口）等物品做了再做。
每個區域物件記住它有哪些區域檔（世界有很多個），每個區域檔各自算時間：
建立區域物件時重置一次；之後每 AREA_TICKS 個 tick 呼叫 update()：
沒有玩家時大約 3 分鐘重置一次，有玩家時大約 15 分鐘，重置前 1 分鐘醒著的玩家會聽到腳步聲。
"""
import logging
import random

from . import doors
from .act import notify
from .area import CHANCE_MAX, ActFlag, DoorState, parse_flags, resolve
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
    """照順序做區域檔的 resets。現在只做 M、D，其他指令先跳過。protos 是 mobiles 這種表：遊戲號碼 → (area_number, 區域檔的生物)。"""
    for r in area.data["resets"]:
        if r["cmd"] == "M":
            reset_mobile(zone, area, r, protos, rng)
        elif r["cmd"] == "D":
            reset_door(zone, area, r)


def reset_mobile(zone, area, r, protos, rng):
    """M：生物放進房間。出現機率沒骰到、或已經有 limit 隻就不放。回傳放出來的生物（之後的 G 用），沒放是 None。"""
    vnum, room_vnum = resolve(area.base, r["mob_vnum"]), resolve(area.base, r["room_vnum"])
    base, proto = protos.get(vnum, (None, None))
    room = zone.rooms.get(room_vnum)
    if proto is None or room is None:       # 號碼存不存在還沒檢查：先記 log 跳過
        log.warning(f"{area.name} 的 M 放不了：生物 {vnum} 或房間 {room_vnum} 不在{zone.name}裡")
        return None
    if r["rare"] > SURE_RARE and rng.randrange(CHANCE_MAX) >= r["rare"] - SURE_RARE:
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
