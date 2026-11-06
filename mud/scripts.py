"""腳本系統（區域製作手冊「腳本」）：讀好每個 .lua、觸發、wait、出錯、定時。沙箱在 lua.py，給 Lua 的名字和函式在 script_api.py。

- 主人：房間或生物（`owner.script` 是 Script，另外有 `vars`、`timer`／`timer_left`、`waiting`）。物品腳本這次不做。
- 觸發：fire() 是一間房間的（先房間、再房間裡的生物，照進房間的先後），fire_owner() 只跑一個主人。
  觸發的人（actor）就是主人時不跑（不觸發自己）；一串最多 MAX_DEPTH 層。
- 一串：最外面的一次觸發（一個指令、一個 tick 的事、wait 完接著跑）引起的全部腳本。一串裡每個主人只跑一次（使用者選的）：
  不然好幾隻生物互相觸發，每一條路都跑一次，10 隻就是 3 萬多次，整個伺服器卡好幾秒。
- on_command 有一個 `return true`（或跑到 wait）就擋住，後面的不跑。
- 出錯一律在這裡接住：停掉這一次，記一筆、提醒線上的 imm（同一個錯 REPORT_EVERY 秒內一次），不往外丟。
- wait：Lua 那邊停下來，schedule() 幾秒後接著跑；接著跑前看主人、觸發的人還在不在，不在就默默停掉。
"""
import contextlib
import logging
import math
import time

from . import act, lua
from .characters import characters

log = logging.getLogger(__name__)

MAX_DEPTH = 5                               # 腳本做的事觸發腳本，一串最多幾層（使用者定的）
MAX_WAITING = 10                            # 同一個主人同時在等的最多幾個，超過的新觸發先不跑（使用者定的）
REPORT_EVERY = 60                           # 同一個錯（同一個檔、同一行、同一個錯）幾秒內只記一筆、只提醒一次（使用者選的）


class Script:
    """一個 .lua 檔（好幾個主人可以用同一個檔，變數各自分開）。"""

    def __init__(self, area, base, file, code, functions):
        self.area = area                    # 區域檔名，不含 .json（腳本資料夾、玩家 vars 都用它）
        self.base = base                    # 那個區域檔的 area_number（號碼規則）
        self.file = file
        self.name = f"{area}/{file}"        # 錯誤訊息裡的名字
        self.code = code
        self.functions = functions          # 定義了哪些 on_ 函式


class Run:
    """一次觸發（可能 wait 好幾次才跑完）。"""

    def __init__(self, owner, event, actor):
        self.owner, self.script, self.event, self.actor = owner, owner.script, event, actor
        self.co = None                      # lupa 的 coroutine（lua.spawn），跑完、不跑了就丟掉（finish）
        self.handles = {}                   # 這次給 Lua 的 handle（同一個角色同一個 handle）

    def finish(self):
        """這一次結束了（跑完、出錯、不跑了）：放掉 Lua 的東西。

        坑：handle 裡的方法是抓著這個 Run 的 Python 函式，這個 Run 又抓著 handle（Lua 的表）：Python 和 Lua 互相抓著，
        兩邊的垃圾回收都看不到整圈，永遠收不掉（每次觸發漏約 10 KB，記憶體用完整個程式會當掉）。這裡放掉 Python 這一邊，圈就斷了。
        """
        self.co = None
        self.handles = {}


library = {}                # (區域檔名, 檔名) → Script（zones.load() 讀好）
mob_scripts = {}            # 生物的遊戲號碼 → (Script, timer)
running = []                # 現在正在跑的主人（一串觸發的堆疊，數幾層用）
chain = set()               # 這一串已經跑過的主人（包括正在跑的）
outer = 0                   # 現在疊了幾層 one_chain()；0 是下一次觸發開始新的一串
commanding = []             # 正在打指令的人（commands.command() 推進來）：給他的訊息當指令的回覆送
pending = {}                # 在等的 Run → 排好的 handle（cancel 用）
reported = {}               # (腳本名字, 錯) → 上次記的時間
clock = time.monotonic      # 測試換掉


def schedule(seconds, fn):
    """幾秒後跑 fn（wait 用）。測試換掉。"""
    import asyncio
    return asyncio.get_running_loop().call_later(seconds, fn)


def load(entries):
    """zones.load() 檢查完以後：讀好每個區域檔用到的 .lua。entries 是 [(區域檔路徑, 讀好的資料)]。"""
    library.clear()
    mob_scripts.clear()
    for path, data in entries:
        base = data["area"]["header"]["area_number"]
        for kind in ("rooms", "mobiles"):
            for x in data[kind]:
                s = x["script"]
                if s is None:
                    continue
                key = (path.stem, s["file"])
                if key not in library:
                    code = (path.parent / path.stem / s["file"]).read_text(encoding="utf-8")
                    found, _ = lua.functions(code, f"{path.stem}/{s['file']}", lua.check_env())
                    library[key] = Script(path.stem, base, s["file"], code, found)
                if kind == "mobiles":
                    mob_scripts[base + x["vnum"]] = (library[key], s["timer"])


def attach(owner, script, timer):
    owner.script, owner.timer = script, timer
    owner.timer_left = timer or 0


def attach_room(room, area_file, r):
    """建房間時（zones.add_area）：照區域檔接上腳本。area_file 是 "test.json" 這種檔名。"""
    s = r["script"]
    if s is not None:
        attach(room, library[(area_file.removesuffix(".json"), s["file"])], s["timer"])


def attach_mob(npc):
    """生物出現時（npcs.spawn）：照牠的號碼接上腳本。"""
    if npc.vnum in mob_scripts:
        attach(npc, *mob_scripts[npc.vnum])


def is_room(owner):
    return not hasattr(owner, "fighting")   # 房間沒有 fighting（角色都有）


def room_of(owner):
    return owner if is_room(owner) else owner.room


def has(owner, event):
    return getattr(owner, "script", None) is not None and event in owner.script.functions


def mobs_in(room):
    """房間裡有腳本的生物，照進房間的先後。"""
    from .npcs import Npc                   # 坑：npcs 會 import 這裡
    return sorted((c for c in characters if isinstance(c, Npc) and c.room is room and c.script is not None),
                  key=lambda c: c.arrived)


@contextlib.contextmanager
def one_chain():
    """最外面的那一次觸發開始新的一串（裡面再觸發的都算同一串）。"""
    global outer
    if outer == 0:
        chain.clear()
    outer += 1
    try:
        with act.gathering():               # 一串送給別人的訊息合成一段（不是指令引起的，例如 on_timer；指令裡的併進指令那段）
            yield
    finally:
        outer -= 1


def fire(room, event, actor=None, *args):
    """一間房間的時機 event：先房間，再房間裡的生物（照進房間的先後）。on_command 有一個擋住就停，回傳擋住了沒。"""
    if room is None:
        return False
    with one_chain():                       # 同一間房的這幾個主人算同一串
        for owner in [room, *mobs_in(room)]:
            if fire_owner(owner, event, actor, *args) and event == "on_command":
                return True
    return False


def fire_owner(owner, event, actor=None, *args):
    """只跑一個主人的 event（生物專用的時機用它）。args 是給 Lua 函式的參數（角色會換成 handle）。"""
    if owner is actor or not has(owner, event):
        return False
    with one_chain():
        return run(Run(owner, event, actor), args)


def run(r, args):
    if r.owner in chain:                    # 這一串已經跑過（包括正在跑的：A 觸發 B、B 又觸發 A）
        return False
    if len(running) >= MAX_DEPTH:
        report(r, f"一串觸發超過 {MAX_DEPTH} 層，{r.event} 不跑")
        return False
    if r.owner.waiting >= MAX_WAITING:
        return False
    chain.add(r.owner)
    from . import script_api
    try:
        env = script_api.env(r)
        values = [script_api.to_lua(r, a) for a in args]
        r.co = lua.spawn(r.script.code, r.script.name, env, r.event, *values)
    except Exception as e:                  # 不該發生（開機檢查過），出錯照樣只停這一次
        r.finish()
        report(r, str(e))
        return False
    return resume(r)


def resume(r):
    """跑一段：跑完回傳 `return true` 了沒；跑到 wait 排好接著跑、回傳 True（on_command 算擋住）；出錯記一筆、回傳 False。"""
    running.append(r.owner)
    try:
        status, value = lua.step(r.co)
    except Exception as e:                  # lupa 自己出錯（不該發生）
        status, value = "error", str(e)
    finally:
        running.pop()
    if status == "done":
        r.finish()
        return value is True
    if status == "wait":
        r.owner.waiting += 1
        pending[r] = schedule(value, lambda: later(r))
        return True
    r.finish()
    report(r, value)
    return False


def alive(owner):
    """主人還在：房間的區域物件沒釋放、生物還在遊戲裡。"""
    if is_room(owner):
        return owner.zone is not None and not owner.zone.released
    return owner in characters


def present(actor, owner):
    """觸發的人還在：在遊戲裡（沒離線），而且跟主人在同一個房間（死掉會被送走）。"""
    return actor in characters and actor.room is room_of(owner)


def later(r):
    """wait 等完了：主人或觸發的人不在了就默默停掉，不然接著跑。"""
    pending.pop(r, None)
    r.owner.waiting -= 1
    if not alive(r.owner) or (r.actor is not None and not present(r.actor, r.owner)):
        r.finish()
        return
    with one_chain():                       # wait 完接著跑：新的一串，從這個主人開始
        chain.add(r.owner)
        resume(r)


def cancel_all():
    """重新載入（zones.stop）：在等的腳本全部不跑了（世界區域不會釋放，舊房間會通過 alive() 的檢查）。"""
    for r, h in list(pending.items()):
        h.cancel()
        r.finish()
        r.owner.waiting = 0
    pending.clear()


def describe(owner):
    if is_room(owner):
        return f"房間 {owner.vnum}"
    return f"生物 {owner.vnum} {owner.name}"


def report(r, msg):
    """出錯：記一筆、提醒線上的 imm。同一個錯 REPORT_EVERY 秒內只一次。玩家看不到。"""
    from .act import notify
    from .color import colorize
    from .players import online_players
    key = (r.script.name, msg)
    now = clock()
    if now - reported.get(key, -math.inf) < REPORT_EVERY:
        return
    reported[key] = now
    text = f"{r.script.area}.json {describe(r.owner)}：{msg}"
    log.warning(f"腳本出錯：{text}")
    for p in online_players():
        if p.imm:
            notify(p, colorize("{R[腳本出錯]{x ") + text)


def tick(zone):
    """區域物件的一個 tick：數房間和生物的 timer，到了就跑 on_timer、重新數。"""
    from .npcs import Npc
    for room in zone.rooms.values():
        if room.timer:
            count_down(room)
    for c in list(characters):
        if isinstance(c, Npc) and c.timer and c.room is not None and c.room.zone is zone:
            count_down(c)


def count_down(owner):
    owner.timer_left -= 1
    if owner.timer_left <= 0:
        owner.timer_left = owner.timer
        fire_owner(owner, "on_timer")
