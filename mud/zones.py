"""區域物件：開機後真的在跑的世界區域、動態區域、副本區域，以及它們的 tick loop。

area.py 管區域檔的格式和檢查；這裡管執行中的區域。
- 世界區域：開機時把 type 是 world 的檔全部建進一個區域物件 world，永遠不釋放。
- 動態區域：有人走進去才建立（room_at），大家共用一份；連續 RELEASE_TICKS 個 tick 沒有玩家就釋放，
  下一個人走進去會重新建立，裡面全部重來。
- 副本區域：instance() 建立，一個擁有者一份；連續 RELEASE_TICKS 個 tick 沒有玩家就釋放。

tick loop：世界和全部的動態區域共用一個（世界 tick），副本每份自己一個，各跑各的節拍，每 TICK_SECONDS（1 秒）一次。
定時做的事都用「每幾個 tick」定義，寫在 Zone.tick()。
區域檔在開機時就讀好、檢查好放在記憶體，建立動態區域和副本時不讀檔。
"""
import asyncio
import json
import logging
from collections import deque
from pathlib import Path

from . import affects, area, behavior, fight, light, meals, objects, reserved, resets, scripts, skills, stats, terrain, weather
from .area import AreaType
from .characters import characters
from .clock import cancel, every
from .config import (ACADEMY_FILE, ACADEMY_START, ACADEMY_STUDENT, AREA_TICKS, CHOKE_TICKS, HOUR_TICKS, OBJ_TICKS,
                     REGEN_TICKS, RELEASE_TICKS, START_ROOM, SYSTEM_AREA, TICK_SECONDS)
from .npcs import Npc
from .players import online_players

log = logging.getLogger(__name__)


class Zone:
    """區域物件：一份正在跑的區域（世界、一個動態區域或一份副本）。"""

    def __init__(self, kind, name):
        self.kind = kind                    # AreaType
        self.name = name                    # 給 log 看的名字：世界是「世界」，其他是檔名
        self.rooms = {}                     # 遊戲號碼 → Room（room.zone 指回這裡）
        self.areas = []                     # 這裡有哪些區域檔（resets.AreaReset，各自算重置的時間）；room.area 指到其中一個
        self.fights = set()                 # 這裡正在跑的戰鬥（fight.Fight）
        self.task = None                    # 自己的 tick loop：只有副本有，世界和動態區域由世界 tick 來做
        self.key = None                     # 副本在 instances 裡的 (檔名, 擁有者)
        self.ticks = 0                      # 跑了幾個 tick
        self.empty_ticks = 0                # 連續幾個 tick 沒有玩家
        self.released = False

    def add_area(self, name, data):
        """把一個區域檔（已經檢查過）建進這個區域物件：房間，和重置要用的資料。"""
        reset = resets.AreaReset(name, data)
        self.areas.append(reset)
        for r in data["rooms"]:
            room = area.build_room(r)
            room.zone, room.area = self, reset
            scripts.attach_room(room, name, r)
            self.rooms[room.vnum] = room

    def tick(self):
        """這個區域物件一次 tick 要做的事。都要做：重置、地上物品的 timer。世界：每個 tick 數技能冷卻、走身上的效果、生物的行為，
        每 HOUR_TICKS 走一次天氣，每 REGEN_TICKS 回復；動態區域、副本：沒有玩家太久就釋放。
        世界也每 HOUR_TICKS 燒一次照明用具、每 CHOKE_TICKS 水底的玩家窒息一次。
        世界的變換之後加在這裡，用「每幾個 tick 做一次」（self.ticks % N == 0）。"""
        self.ticks += 1
        scripts.tick(self)                  # 腳本的 on_timer（坑：跟 objects.update 一樣要在下面兩個 return 前面）
        if self.ticks % AREA_TICKS == 0:
            resets.update(self)             # 照 C 版：沒有玩家、有玩家各自幾分鐘重置一次（區域檔的 header 可以改）
        if self.ticks % OBJ_TICKS == 0:
            # 坑：要放在下面兩個 return 前面，不然世界的屍體、有人站著的副本裡的屍體永遠不會爛
            objects.update(self)            # 地上有 timer 的物品（屍體）減 1，到了就消失
        if self.kind == AreaType.WORLD:
            skills.tick()                   # 技能的冷卻：掛在角色身上，跟回復一樣所有在線玩家一起數
            affects.tick()                  # 身上的效果：全部角色（玩家和生物，副本裡的也是）一起走
            meals.tick()                    # 吃喝之後坐滿 10 秒的效果（設計文件 §3.9）
            behavior.tick(self.ticks)       # 生物的行為：走動、撿東西、主動攻擊（副本裡的也是，設計文件 §4.11）
            if self.ticks % HOUR_TICKS == 0:
                weather.tick()              # 全遊戲一個天氣，只由世界 tick 走時間
                light.burn()                # 玩家身上的照明用具少 1 小時（照 C 版，遊戲裡每小時）
            if self.ticks % CHOKE_TICKS == 0:
                terrain.choke()             # 水底沒有水中呼吸的玩家窒息（副本裡的也是：掛在角色身上的事放世界 tick）
            if self.ticks % REGEN_TICKS == 0:
                # 回復掛在角色身上，在線玩家和全部生物一起回（副本裡的也是）：放在各區域的 tick 會因為節拍不同步，走來走去多回或少回
                for c in list(characters):
                    if getattr(c, "panel", None):
                        stats.regen(c)
            return
        if any(p.room.zone is self for p in online_players()):
            self.empty_ticks = 0
            return
        self.empty_ticks += 1
        if self.empty_ticks >= RELEASE_TICKS:
            release(self)


world = None                # 世界區域（Zone）
dynamic = {}                # 動態區域的檔名 → 現在有建立的那一份（Zone）
instances = {}              # (副本的檔名, 擁有者) → 那一份副本（Zone）
templates = {}              # 動態區域、副本的檔名 → (AreaType, 讀好的區域檔)
routes = {}                 # 檔名 → 從起始房間怎麼走到那個區域（"3s4wn"，"" 是就在這裡，None 是走不到）：area 指令用，load() 算；副本不在裡面
dynamic_rooms = {}          # 動態區域的房間遊戲號碼 → 檔名：走到這些號碼時要找到（或建立）那個動態區域
world_task = None           # 世界 tick


def load(directory):
    """檢查 directory 裡全部的區域檔，建好世界區域。動態區域、副本先讀好放著，要用時才建立。

    有任何問題就丟 ValueError（訊息是第一個問題），原本的區域物件不動。
    沒問題才停掉舊的區域物件（和它們的 loop），換成新的。世界 tick 要另外呼叫 start()。
    """
    global world, templates, dynamic_rooms, routes
    paths = sorted(Path(directory).glob("*.json"))
    if not any(area.area_kind(p) == AreaType.SYSTEM for p in paths):
        # 屍體、金幣、召喚物的文字在系統區域檔（reserved.py）：資料夾裡沒有（測試自己做的區域資料夾）就用遊戲的那一份
        paths.append(Path(SYSTEM_AREA))
    problems = area.check_files(paths, paths)
    found = [p for path in paths for p in problems[path]]
    if found:
        more = f"（共 {len(found)} 個問題，用 uv run python -m mud.areacheck 看全部）" if len(found) > 1 else ""
        raise ValueError(found[0] + more)
    new_world = Zone(AreaType.WORLD, "世界")
    new_templates, new_dynamic_rooms, new_mobiles, new_objects = {}, {}, {}, {}
    entries = [(path, json.loads(path.read_text(encoding="utf-8"))) for path in paths]
    scripts.load(entries)                   # 建房間之前先讀好腳本（建房間、放生物時要接上）
    for path, data in entries:
        kind = AreaType(data["area"]["header"]["type"])
        for m in data["mobiles"]:           # 生物用遊戲號碼收成一張表：M 可以放別的區域檔的生物
            new_mobiles[m["vnum"]] = m
        for o in data["objects"]:           # 物品也是：掉落表可以掉別的區域檔的物品
            new_objects[o["vnum"]] = o
        if kind == AreaType.SYSTEM:         # 系統區域檔只有程式要用的生物、物品：不建房間
            continue
        if kind == AreaType.WORLD:
            new_world.add_area(path.name, data)
            continue
        new_templates[path.name] = (kind, data)
        if kind == AreaType.DYNAMIC:
            for r in data["rooms"]:
                new_dynamic_rooms[r["vnum"]] = path.name
    missing = reserved.check(new_objects, new_mobiles)
    if missing:                             # 程式要的屍體、金幣、召喚物少了：跟區域檔有錯一樣停止開機
        raise ValueError(missing[0] + (f"（共 {len(missing)} 個問題）" if len(missing) > 1 else ""))
    stop()
    world, templates, dynamic_rooms = new_world, new_templates, new_dynamic_rooms
    routes = find_routes(entries, START_ROOM)
    resets.mobiles, objects.protos = new_mobiles, new_objects
    resets.reset_zone(world)                # 世界一開機就放好生物
    counts = {k: sum(1 for t in templates.values() if t[0] == k) for k in (AreaType.DYNAMIC, AreaType.INSTANCE)}
    log.info(f"載入 {len(paths)} 個區域檔：世界 {len(world.rooms)} 間房；"
             f"動態區域 {counts[AreaType.DYNAMIC]} 個、副本區域 {counts[AreaType.INSTANCE]} 個，要用時才建立")


def find_routes(entries, start):
    """每個區域檔從 start（神殿大廳）怎麼走過去（使用者 2026-11-20 要的：文字遊戲沒有地圖，area 告訴玩家怎麼去）。

    從 start 一間一間往外找（照出口，門照樣走；方向照 DIRECTIONS 的順序，結果才固定），每個區域檔取走得最近的那一間。
    只算世界、動態區域：副本的入口（enter 的地方）還沒做，入口跟副本的 recall 點是不同的（使用者說的），所以副本不算。
    回傳 {檔名: 路徑}：路徑寫成 "3s4wn"（同一個方向連走好幾步寫次數），"" 是起點就在這個區域裡，None 是走不到。
    區域檔開機時讀好就不會變，所以 load() 算一次就好。
    """
    owner, exits = {}, {}
    for path, data in entries:
        for r in data["rooms"]:
            owner[r["vnum"]] = path.name
            exits[r["vnum"]] = [(d, r["exits"][d]["to_room"]) for d in area.DIRECTIONS if d in r["exits"]]
    came = {start: None} if start in exits else {}
    todo = deque(came)
    while todo:
        room = todo.popleft()
        for d, to in exits[room]:
            if to in exits and to not in came:
                came[to] = (room, d)
                todo.append(to)
    order = {room: i for i, room in enumerate(came)}    # 找到的順序：越前面越近
    out = {}
    for path, data in entries:
        if AreaType(data["area"]["header"]["type"]) in (AreaType.INSTANCE, AreaType.SYSTEM):
            continue
        reached = [r["vnum"] for r in data["rooms"] if r["vnum"] in order]
        out[path.name] = walk(came, min(reached, key=order.get)) if reached else None
    return out


def walk(came, room):
    """從起點走到 room 的方向，壓成 "3s4wn"。"""
    steps = []
    while came[room] is not None:
        room, d = came[room]
        steps.append(d[0])
    steps.reverse()
    out, i = "", 0
    while i < len(steps):
        j = i
        while j < len(steps) and steps[j] == steps[i]:
            j += 1
        out += (str(j - i) if j - i > 1 else "") + steps[i]
        i = j
    return out


def stop():
    """停掉全部的區域物件：世界 tick、副本的 tick、所有戰鬥，清空名單，拿掉所有生物（重新載入時重新放）。"""
    global world_task
    cancel(world_task)
    world_task = None
    scripts.cancel_all()
    for zone in [world, *dynamic.values(), *instances.values()]:
        if zone is not None:
            for f in list(zone.fights):
                fight.end(f)
            cancel(zone.task)
    dynamic.clear()
    instances.clear()
    characters[:] = [c for c in characters if not isinstance(c, Npc)]


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


ACADEMY_AREA = ACADEMY_FILE.removesuffix(".json")   # 腳本變數用的區域名（區域檔名去掉 .json）


def enroll(player):
    """新角色：有學院的區域檔就記成學生（使用者要的：建立角色後先進學院）。"""
    if ACADEMY_FILE in templates:
        player.vars.setdefault(ACADEMY_AREA, {})[ACADEMY_STUDENT] = True


def is_student(player):
    """還沒從教學學院畢業：有學院的區域檔，而且他的腳本變數有 student（enroll() 設、院長的腳本拿掉）。"""
    return ACADEMY_FILE in templates and bool(player.vars.get(ACADEMY_AREA, {}).get(ACADEMY_STUDENT))


def recall_room(ch):
    """recall 會送到哪間房（使用者定的）：所在的區域檔有寫 recall 就用區域的（通常是副本：副本裡的 recall 點，人還在副本裡），
    沒寫就用玩家自己的返回點（player.recall，沒設定是起始房間 START_ROOM）。找不到是 None。

    副本的入口不是 recall 點：入口是世界裡放傳送門的那間，離開副本要用副本裡的傳送門（使用者 2026-11-20 定的，enter 還沒做）。
    """
    area = getattr(ch.room, "area", None)
    vnum = area.data["area"]["recall"] if area is not None else None
    if vnum is None:
        vnum = getattr(ch, "recall", None) or START_ROOM
    return room_at(ch.room, vnum)


def home(player):
    """玩家的「家」：建立角色、副本裡離線再登入、死掉都回這裡。學生是自己那一份學院的第一間，其他人是起始房間。要在 asyncio 裡呼叫。"""
    if is_student(player):
        return instance(ACADEMY_FILE, player.name).rooms[ACADEMY_START]
    return start_room()


def room_at(from_room, vnum):
    """從 from_room 走到遊戲號碼 vnum 的房間；走不到（例如那是副本）就是 None。

    先找自己所在的區域物件，所以在副本、動態區域裡走，會留在同一份。
    再找世界，最後看是不是動態區域的房間：那個動態區域還沒建立就建立一份。
    """
    room = find_room(from_room, vnum)
    name = dynamic_rooms.get(vnum)
    if room is None and name is not None:
        dynamic[name] = _build(name)
        resets.reset_zone(dynamic[name])
        log.info(f"建立動態區域 {name}")
        room = dynamic[name].rooms[vnum]
    return room


def find_room(from_room, vnum):
    """跟 room_at() 一樣的順序找房間，但不會建立動態區域：還沒建立就是 None（例如門的對面還沒有人去過）。"""
    if vnum in from_room.zone.rooms:
        return from_room.zone.rooms[vnum]
    if vnum in world.rooms:
        return world.rooms[vnum]
    name = dynamic_rooms.get(vnum)
    return dynamic[name].rooms[vnum] if name in dynamic else None


def instance(name, owner):
    """擁有者 owner（名字；之後做組隊時是隊長的名字）的那一份副本 name，沒有就建立一份。要在 asyncio 裡呼叫。"""
    key = (name, owner)
    if key in instances:
        return instances[key]
    if name not in templates or templates[name][0] != AreaType.INSTANCE:
        raise ValueError(f"{name} 不是副本區域")
    zone = instances[key] = _build(name)
    zone.key = key
    resets.reset_zone(zone)
    zone.task = asyncio.create_task(every(TICK_SECONDS, lambda: _instance_tick(zone)), name=f"副本 {name} 的 tick")
    log.info(f"建立副本 {name}（擁有者 {owner}）")
    return zone


def _instance_tick(zone):
    safe_tick(zone)
    return not zone.released                # 釋放了就結束自己的 tick loop


def release(zone):
    """釋放一個動態區域或副本：停掉裡面的戰鬥、移走留在裡面的角色（之後的 NPC），從名單拿掉。

    地上的物品（屍體）放在房間裡，房間不要了就跟著不見，不用另外清。
    """
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
    kind, data = templates[name]
    zone = Zone(kind, name)
    zone.add_area(name, data)
    return zone
