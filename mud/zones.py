"""區域物件：開機後真的在跑的世界區域、動態區域、副本區域，以及它們的 tick loop。

area.py 管區域檔的格式和檢查；這裡管執行中的區域。
- 世界區域：開機時把 type 是 world 的檔全部建進一個區域物件 world，永遠不釋放。
- 動態區域：有人走進去才建立（room_at），大家共用一份；沒有玩家超過 RELEASE_SECONDS 就釋放，
  下一個人走進去會重新建立，裡面全部重來。
- 副本區域：instance() 建立，一個擁有者一份；沒有玩家超過 RELEASE_SECONDS 就釋放。

tick loop：世界和全部的動態區域共用一個（世界 tick），副本每份自己一個，各跑各的節拍。
區域檔在開機時就讀好、檢查好放在記憶體，建立動態區域和副本時不讀檔。
"""
import asyncio
import json
import logging
from pathlib import Path

from . import area, fight, weather
from .area import AreaType
from .characters import characters
from .clock import cancel, every
from .config import RELEASE_SECONDS, START_ROOM, TICK_SECONDS
from .players import online_players

log = logging.getLogger(__name__)


class Zone:
    """區域物件：一份正在跑的區域（世界、一個動態區域或一份副本）。"""

    def __init__(self, kind, name):
        self.kind = kind                    # AreaType
        self.name = name                    # 給 log 看的名字：世界是「世界」，其他是檔名
        self.rooms = {}                     # 遊戲號碼 → Room（room.zone 指回這裡）
        self.fights = set()                 # 這裡正在跑的戰鬥（fight.Fight）
        self.task = None                    # 自己的 tick loop：只有副本有，世界和動態區域由世界 tick 來做
        self.key = None                     # 副本在 instances 裡的 (檔名, 擁有者)
        self.empty_since = None             # 從什麼時候開始沒有玩家（loop.time()）；有玩家時是 None
        self.released = False

    def add_rooms(self, base, data):
        """把一個區域檔（已經檢查過）的房間建進這個區域物件。"""
        for r in data["rooms"]:
            room = area.build_room(base, r)
            room.zone = self
            self.rooms[room.vnum] = room

    def tick(self):
        """這個區域物件一次 tick 要做的事。世界：天氣；動態區域、副本：沒有玩家太久就釋放。世界的變換之後加在這裡。"""
        if self.kind == AreaType.WORLD:
            weather.tick()                  # 全遊戲一個天氣，只由世界 tick 走時間
            return
        now = asyncio.get_running_loop().time()
        if any(p.room.zone is self for p in online_players()):
            self.empty_since = None
        elif self.empty_since is None:
            self.empty_since = now
        elif now - self.empty_since >= RELEASE_SECONDS:
            release(self)


world = None                # 世界區域（Zone）
dynamic = {}                # 動態區域的檔名 → 現在有建立的那一份（Zone）
instances = {}              # (副本的檔名, 擁有者) → 那一份副本（Zone）
templates = {}              # 動態區域、副本的檔名 → (AreaType, area_number, 讀好的區域檔)
dynamic_rooms = {}          # 動態區域的房間遊戲號碼 → 檔名：走到這些號碼時要找到（或建立）那個動態區域
world_task = None           # 世界 tick


def load(directory):
    """檢查 directory 裡全部的區域檔，建好世界區域。動態區域、副本先讀好放著，要用時才建立。

    有任何問題就丟 ValueError（訊息是第一個問題），原本的區域物件不動。
    沒問題才停掉舊的區域物件（和它們的 loop），換成新的。世界 tick 要另外呼叫 start()。
    """
    global world, templates, dynamic_rooms
    paths = sorted(Path(directory).glob("*.json"))
    problems = area.check_files(paths, paths)
    found = [p for path in paths for p in problems[path]]
    if found:
        more = f"（共 {len(found)} 個問題，用 uv run python -m mud.areacheck 看全部）" if len(found) > 1 else ""
        raise ValueError(found[0] + more)
    new_world = Zone(AreaType.WORLD, "世界")
    new_templates, new_dynamic_rooms = {}, {}
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        header = data["area"]["header"]
        kind, base = AreaType(header["type"]), header["area_number"]
        if kind == AreaType.WORLD:
            new_world.add_rooms(base, data)
            continue
        new_templates[path.name] = (kind, base, data)
        if kind == AreaType.DYNAMIC:
            for r in data["rooms"]:
                new_dynamic_rooms[base + r["vnum"]] = path.name
    stop()
    world, templates, dynamic_rooms = new_world, new_templates, new_dynamic_rooms
    counts = {k: sum(1 for t in templates.values() if t[0] == k) for k in (AreaType.DYNAMIC, AreaType.INSTANCE)}
    log.info(f"載入 {len(paths)} 個區域檔：世界 {len(world.rooms)} 間房；"
             f"動態區域 {counts[AreaType.DYNAMIC]} 個、副本區域 {counts[AreaType.INSTANCE]} 個，要用時才建立")


def stop():
    """停掉全部的區域物件：世界 tick、副本的 tick、所有戰鬥，清空名單。"""
    global world_task
    cancel(world_task)
    world_task = None
    for zone in [world, *dynamic.values(), *instances.values()]:
        if zone is not None:
            for f in list(zone.fights):
                fight.end(f)
            cancel(zone.task)
    dynamic.clear()
    instances.clear()


def start():
    """開始世界 tick（世界和全部動態區域共用）。要在 asyncio 裡呼叫。"""
    global world_task
    world_task = asyncio.create_task(every(TICK_SECONDS, world_tick), name="世界 tick")


def world_tick():
    """世界 tick 的一次：先做世界，再做每個動態區域。"""
    safe_tick(world)
    for zone in list(dynamic.values()):     # 用複本：tick 裡可能會釋放、拿掉動態區域
        safe_tick(zone)


def safe_tick(zone):
    """做一個區域物件的 tick。出錯只記 log，不影響別的區域物件，下一個 tick 照跑。"""
    try:
        zone.tick()
    except Exception:
        log.exception(f"{zone.name} 的 tick 出錯")


def start_room():
    """登入後站的房間（世界區域的 START_ROOM）。"""
    return world.rooms[START_ROOM]


def room_at(from_room, vnum):
    """從 from_room 走到遊戲號碼 vnum 的房間；走不到（例如那是副本）就是 None。

    先找自己所在的區域物件，所以在副本、動態區域裡走，會留在同一份。
    再找世界，最後看是不是動態區域的房間：那個動態區域還沒建立就建立一份。
    """
    if vnum in from_room.zone.rooms:
        return from_room.zone.rooms[vnum]
    if vnum in world.rooms:
        return world.rooms[vnum]
    name = dynamic_rooms.get(vnum)
    if name is None:
        return None
    if name not in dynamic:
        dynamic[name] = _build(name)
        log.info(f"建立動態區域 {name}")
    return dynamic[name].rooms[vnum]


def instance(name, owner):
    """擁有者 owner（名字；之後做組隊時是隊長的名字）的那一份副本 name，沒有就建立一份。要在 asyncio 裡呼叫。"""
    key = (name, owner)
    if key in instances:
        return instances[key]
    if name not in templates or templates[name][0] != AreaType.INSTANCE:
        raise ValueError(f"{name} 不是副本區域")
    zone = instances[key] = _build(name)
    zone.key = key
    zone.task = asyncio.create_task(every(TICK_SECONDS, lambda: _instance_tick(zone)), name=f"副本 {name} 的 tick")
    log.info(f"建立副本 {name}（擁有者 {owner}）")
    return zone


def _instance_tick(zone):
    safe_tick(zone)
    return not zone.released                # 釋放了就結束自己的 tick loop


def release(zone):
    """釋放一個動態區域或副本：停掉裡面的戰鬥、移走留在裡面的角色（之後的 NPC），從名單拿掉。"""
    for f in list(zone.fights):
        fight.end(f)
    characters[:] = [c for c in characters if c.room.zone is not zone]
    zone.released = True
    if zone.kind == AreaType.DYNAMIC:
        dynamic.pop(zone.name, None)
        log.info(f"釋放動態區域 {zone.name}")
    else:
        instances.pop(zone.key, None)
        log.info(f"釋放副本 {zone.name}（擁有者 {zone.key[1]}）")
    cancel(zone.task)                       # 在自己的 tick 裡釋放時不會停到自己，由 _instance_tick 回傳 False 結束


def _build(name):
    kind, base, data = templates[name]
    zone = Zone(kind, name)
    zone.add_rooms(base, data)
    return zone
