"""給 Lua 腳本的名字和函式（區域製作手冊「腳本」的「能用的函式」「變數」）。

- me、room、actor 是 Lua 的表（handle）。方法都是綁好那個角色或房間的 Python 函式（腳本假造不了）；
  `actor:tell(x)`、`actor.tell(x)` 兩種寫法都可以。要把 handle 換回角色時用 lua.obj_of()。
- 「算腳本出錯」的地方丟 ScriptError：lua.wrap() 會加上腳本的行號，這一次停掉（pcall 接不住）。
- 號碼照號碼規則：1～99 是這個腳本所在的區域檔，100 以上是完整號碼；給腳本的號碼也換回這種寫法。
"""
import math
import random

from . import lua
from .area import DoorState, ItemColor, check_fixed_item, resolve
from .config import ENCODING

rng = random                                # 測試換掉
MAX_LOADED_MOBS = 50                        # load_mob：同一個區域物件裡、同號碼的生物最多幾隻（使用者定的安全上限）
DOOR_ACTIONS = {"open": DoorState.OPEN, "close": DoorState.CLOSED, "lock": DoorState.LOCKED, "unlock": DoorState.CLOSED}


class ScriptError(Exception):
    """算腳本出錯：訊息就是給區域作者看的話。"""


class Vnum(int):
    """觸發時給腳本的物品號碼（遊戲號碼）：to_lua() 換成這個腳本的寫法。"""


def env(r):
    """這次觸發的環境：Lua 本來就有的安全函式、wait、me、room、random、hour。"""
    from . import scripts
    e = lua.base_env()
    e["me"] = handle_of(r, r.owner)
    room = scripts.room_of(r.owner)
    e["room"] = e["me"] if room is r.owner else handle_of(r, room)
    e["random"] = lua.wrap(lambda a, b: roll(a, b))
    e["hour"] = lua.wrap(game_hour)
    return e


def to_lua(r, value):
    """給 Lua 函式的參數：角色、房間換成 handle，物品號碼換成這個腳本的寫法，其他照原樣。"""
    from .characters import Character
    if isinstance(value, Character):
        return handle_of(r, value)
    if isinstance(value, Vnum):
        return script_number(r.script.base, int(value))
    return value


def script_number(base, vnum):
    """遊戲號碼 → 腳本的寫法：自己區域的是 1～99，別的區域是完整號碼。"""
    return vnum - base if base < vnum <= base + 99 else vnum


def number(r, n, what="號碼"):
    """腳本寫的號碼 → 遊戲號碼（號碼規則）。"""
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ScriptError(f"{what}要是 1 以上的整數，不能是 {lua_repr(n)}")
    return resolve(r.script.base, n)


def lua_repr(v):
    return "nil" if v is None else repr(v)


def text_of(t):
    """要送出去的字：要是字串、轉得成 Big5（程式串出來的字開機查不到）。"""
    if not isinstance(t, str):
        raise ScriptError(f"要給文字，不能是 {lua_repr(t)}")
    try:
        t.encode(ENCODING)
    except UnicodeEncodeError as e:
        raise ScriptError(f"有轉不成 Big5 的字 {t[e.start]!r}") from None
    return t


def deliver(ch, text, apart=False):
    """送給 ch（notify：他自己的指令還沒跑完就當作那個指令的回覆，不然補 prompt）。apart 見 notify()。"""
    from .act import notify
    notify(ch, text.rstrip("\n"), apart)


def method(obj, fn):
    """綁好 obj 的方法。`actor:tell(x)` 第一個參數是 handle 自己，丟掉；`actor.tell(x)` 也可以。"""
    def call(*args):
        if args and lua.obj_of(args[0]) is obj:
            args = args[1:]
        return fn(*args)
    return lua.wrap(call)


def handle_of(r, obj):
    if id(obj) not in r.handles:
        from . import scripts
        fields = room_fields(r, obj) if scripts.is_room(obj) else character_fields(r, obj)
        r.handles[id(obj)] = lua.handle(obj, fields)
    return r.handles[id(obj)]


# ---- 變數 ----

def check_value(v):
    if v is None or isinstance(v, (bool, str)) or (isinstance(v, (int, float)) and math.isfinite(v)):
        return v
    raise ScriptError("變數只能存 nil、true／false、數字、字串")


def vars_of(store):
    """store 是 dict：讀寫 store[名字]，寫 nil 是拿掉。"""
    def get(name):
        return store.get(str(name))

    def set_(name, value):
        if not isinstance(name, (str, int)) or isinstance(name, bool):
            raise ScriptError(f"變數的名字要是字串，不能是 {lua_repr(name)}")
        if check_value(value) is None:
            store.pop(str(name), None)
        else:
            store[str(name)] = value
    return lua.vars_table(get, set_)


# ---- 角色（me、actor） ----

def character_fields(r, ch):
    from .npcs import Npc
    from .players import Player
    player = isinstance(ch, Player)
    store = ch.vars.setdefault(r.script.area, {}) if player else ch.vars
    fields = {
        "name": ch.name, "level": getattr(ch, "level", 1),
        "guild": str(ch.guild) if player and ch.guild else None,
        "race": str(ch.race) if player and ch.race else None,
        "vars": vars_of(store),
        "is_player": method(ch, lambda: player),
        "has_item": method(ch, lambda n: any(o.vnum == number(r, n) for o in ch.carrying)),
        "wears_item": method(ch, lambda n: any(o.vnum == number(r, n) for o in ch.equipment.values())),
        "tell": method(ch, lambda t: deliver(ch, colorize_text(t))),
        "transfer": method(ch, lambda n: transfer(r, ch, n)),
        "give_item": method(ch, lambda n, level=None, color=None: give_item(r, ch, n, level, color)),
        "take_item": method(ch, lambda n: take_item(r, ch, n)),
        "read_var": method(ch, lambda area, name: read_var(ch, area, name)),
    }
    if isinstance(ch, Npc):
        fields.update({
            "command": method(ch, lambda line: mob_command(ch, line)),
            "use": method(ch, lambda skill, target: mob_use(ch, skill, target)),
            "destroy": method(ch, lambda: destroy(ch)),
        })
    return fields


def colorize_text(t):
    from .color import colorize
    return colorize(text_of(t))


def read_var(ch, area, name):
    """別的區域檔的玩家變數：只能看。觸發的人是生物時沒有（nil）。"""
    from .players import Player
    if not isinstance(ch, Player):
        return None
    return ch.vars.get(str(area), {}).get(str(name))


def transfer(r, ch, n):
    """送到那間房：不能送進副本（找不到就算出錯）。先停手，給他看新房間，觸發那邊的 on_enter(actor, nil)。"""
    from . import death, scripts, zones
    from .commands.system import look
    vnum = number(r, n, "房號")
    target = zones.room_at(ch.room, vnum)
    if target is None:
        raise ScriptError(f"沒有房間 {vnum}，或那是副本（不能送進副本）")
    death.stop_all(ch)
    ch.room = target
    arrive(ch)
    deliver(ch, look(ch), apart=True)       # 新房間的畫面：前面空一行
    scripts.fire(target, "on_enter", ch, ch, None)


def arrive(ch):
    """記下進房間的先後（好幾個生物的腳本照這個順序跑）。"""
    from . import characters
    characters.arrive(ch)


def make_item(r, n, level, color):
    """跟 oload 一樣：號碼、等級（一定要寫）、品質（顏色，不寫沒有隨機屬性）。固定裝備當下檢查點數上限。"""
    from . import objects
    vnum = number(r, n)
    if isinstance(level, bool) or not isinstance(level, int) or level < 1:
        raise ScriptError(f"等級一定要寫，要是 1 以上的整數，不能是 {lua_repr(level)}")
    if color is not None and color not in {c.value for c in ItemColor}:
        raise ScriptError(f"顏色要是 {'、'.join(c.value for c in ItemColor)} 或不寫，不能是 {lua_repr(color)}")
    if vnum not in objects.protos:
        raise ScriptError(f"沒有物品 {vnum}")
    problems = []
    check_fixed_item(f"放出物品 {vnum}", vnum, objects.protos, level, color, problems)
    if problems:
        raise ScriptError(problems[0])
    return objects.create(vnum, level, color, rng)


def give_item(r, ch, n, level, color):
    ch.carrying.insert(0, make_item(r, n, level, color))


def take_item(r, ch, n):
    vnum = number(r, n)
    obj = next((o for o in ch.carrying if o.vnum == vnum), None)
    if obj is None:
        return False
    ch.carrying.remove(obj)
    return True


def mob_command(npc, line):
    from . import commands
    commands.command(npc, text_of(line))


def mob_use(npc, skill_id, target):
    """生物對某人放技能（使用者同意加的）：只能放增益技能，傷害技能等設計怪物技能時再開（使用者定的）。"""
    from . import skills
    from .players import Player
    skill = skills.SKILLS.get(skill_id) if isinstance(skill_id, str) else None
    if skill is None:
        raise ScriptError(f"沒有技能 {lua_repr(skill_id)}")
    if skill.kind != "buff":
        raise ScriptError(f"{skill.name}是傷害技能：mob:use 只能放增益技能")
    victim = lua.obj_of(target)
    if not isinstance(victim, Player) or victim.room is not npc.room:
        raise ScriptError("mob:use 的對象要是同一個房間的玩家")
    skills.use(npc, skill, victim)


def destroy(npc):
    """讓生物消失，不留屍體（身上的東西一起不見）。"""
    from . import death
    from .characters import characters
    if npc in characters:
        death.stop_all(npc)
        characters.remove(npc)
        npc.carrying.clear()


# ---- 房間（room） ----

def room_fields(r, room):
    return {
        "vars": vars_of(room.vars),
        "has_item": method(room, lambda n: any(o.vnum == number(r, n) for o in room.contents)),
        "echo": method(room, lambda t: echo(room, colorize_text(t))),
        "echo_except": method(room, lambda who, t: echo(room, colorize_text(t), lua.obj_of(who))),
        "load_item": method(room, lambda n, level=None, color=None: room.contents.insert(0, make_item(r, n, level, color))),
        "load_mob": method(room, lambda n: load_mob(r, room, n)),
        "door": method(room, lambda direction, action: door(room, direction, action)),
    }


def echo(room, text, skip=None):
    """房間裡醒著的玩家看（睡著的看不到，照 act()）。"""
    from .characters import Position, characters
    from .players import Player
    for c in list(characters):
        if isinstance(c, Player) and c.room is room and c is not skip and c.position > Position.SLEEPING:
            deliver(c, text)


def load_mob(r, room, n):
    """放一隻生物（跟重置的 M 一樣骰 tier_roll，牠的 on_born 會跑）。不管 M 的 limit，但同一個區域物件、同號碼最多 MAX_LOADED_MOBS 隻。"""
    from . import npcs, resets
    from .characters import characters
    vnum = number(r, n)
    if vnum not in resets.mobiles:
        raise ScriptError(f"沒有生物 {vnum}")
    here = sum(1 for c in characters if isinstance(c, npcs.Npc) and c.vnum == vnum and c.room is not None and c.room.zone is room.zone)
    if here >= MAX_LOADED_MOBS:
        raise ScriptError(f"生物 {vnum} 已經有 {here} 隻了（同號碼最多 {MAX_LOADED_MOBS} 隻）")
    base, proto = resets.mobiles[vnum]
    npcs.spawn(vnum, proto, room, rng, base)


def door(room, direction, action):
    """開、關、鎖、開鎖門，兩邊一起變，不用鑰匙。"""
    from . import doors
    if direction not in room.doors:
        raise ScriptError(f"往 {lua_repr(direction)} 沒有門")
    if action not in DOOR_ACTIONS:
        raise ScriptError(f"門要 open、close、lock 或 unlock，不能是 {lua_repr(action)}")
    doors.set_state(room, direction, DOOR_ACTIONS[action])


# ---- 其他 ----

def roll(a, b):
    if any(isinstance(x, bool) or not isinstance(x, int) for x in (a, b)) or a > b:
        raise ScriptError(f"random 要給兩個整數（小的在前），不能是 {lua_repr(a)}、{lua_repr(b)}")
    return rng.randint(a, b)


def game_hour():
    from . import weather
    return weather.current.hour if weather.current is not None else 0
