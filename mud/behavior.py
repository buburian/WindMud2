"""生物平常的行為（設計文件 §4.11，規則在區域製作手冊 act）：走動、scavenger 撿東西、主動攻擊，還有回合結束時 wimpy 的逃跑。

掛在角色身上的定時事情放世界 tick（zones.Zone.tick 呼叫 tick()）：副本裡的生物也在這裡做，大家的節拍一樣。
生物的回血跟玩家一起在 zones.py（stats.regen）；打架用的 special、janitor、fido 在 specials.py。
坑：fight → behavior → fight 繞一圈，這裡用 from . import 模組；commands 會 import 戰鬥的模組，在函式裡才 import。
"""
import random

from . import fight, objects, specials, stats
from .act import TO_ROOM, act, gathering
from .area import DIRECTIONS, ActFlag, RoomFlag
from .characters import Position, characters
from .config import MOBILE_TICKS
from .npcs import Npc
from .players import online_players

rng = random                                # 測試換掉
WANDER_CHANCE = 0.20                        # 走動：每 MOBILE_TICKS 骰一次，20% 走一步
SCAVENGE_CHANCE = 0.25                      # scavenger：每 MOBILE_TICKS 骰一次，25% 撿地上最值錢的一件
WIMPY_CHANCE = 0.25                         # wimpy：每回合結束 HP 低於上限的一半就骰，25% 逃掉（跟 DEX 12 的玩家一樣）
UNNOTICED_CHANCE = 0.5                      # 半身人的「不起眼」：會主動攻擊的生物第一次要打他時，一半不打


def tick(ticks):
    """世界每個 tick：每 MOBILE_TICKS 站著的生物做平常的事，然後主動攻擊。這一個 tick 生物做的事，旁邊的人一起收、一個 prompt。"""
    with gathering():
        if ticks % MOBILE_TICKS == 0:
            for npc in [c for c in characters if isinstance(c, Npc)]:
                if npc in characters:       # 前面的生物做的事（走進房間的腳本）可能讓牠不在了
                    idle(npc)
        aggress()


def idle(npc):
    """每 MOBILE_TICKS：站著的生物（睡覺、休息、打架中都不做）照順序：平常的 special → scavenger 撿東西 → 走動。"""
    if npc.position != Position.STANDING:
        return
    specials.idle(npc)
    if ActFlag.SCAVENGER in npc.act and rng.random() < SCAVENGE_CHANCE:
        scavenge(npc)
    if ActFlag.SENTINEL not in npc.act and rng.random() < WANDER_CHANCE:
        ways = exits(npc)
        if ways:
            from .commands import system
            system.move(npc, rng.choice(ways))     # 離開、走過來的訊息跟玩家一樣


def exits(ch):
    """生物走得過去的方向（走動、wimpy 逃跑共用，照 DIRECTIONS 的順序）：門沒關、不是 no_mob 房間、
    在同一份區域物件、同一個區域檔裡（使用者選的：世界的生物也不走進別的區域檔；所以也不會建出還沒建立的動態區域）。
    """
    room = ch.room
    ways = []
    for d in DIRECTIONS:
        if d not in room.exits:
            continue
        door = room.doors.get(d)
        to = room.zone.rooms.get(room.exits[d])
        if ((door is None or not door.closed) and to is not None and to.area is room.area
                and RoomFlag.NO_MOB not in to.room_flags):
            ways.append(d)
    return ways


def scavenge(npc):
    """scavenger：撿地上最值錢（商店的基本價格）、拿得起來的一件（屍體拿不起來、封印的不撿），一樣貴撿前面的（新的）。訊息照 C 版。"""
    from .commands import items
    things = [o for o in npc.room.contents if o.take and not items.sealed(o)]
    if not things:
        return
    best = max(things, key=objects.base_price)
    npc.room.contents.remove(best)
    npc.carrying.insert(0, best)
    act("$n撿起了【$t】。", npc, t=objects.short(best), to=TO_ROOM)


def aggress():
    """主動攻擊（每個 tick）：aggressive、站著（沒在打架）、不在安全區的生物，從同一間房的玩家隨機挑一個開打，
    跟玩家用 kill 開打一樣（沒有另外的訊息）。不挑 imm、正在打架的人（不然等於兩隻一起打）；睡著的照打，不看等級差。
    先從在線的玩家整理每間房可以打的人（玩家少，比較快：loop 裡不能卡住）。
    """
    targets = {}
    for p in online_players():
        if not p.imm and p.fighting is None:
            targets.setdefault(p.room, []).append(p)
    if not targets:
        return
    for npc in [c for c in characters if isinstance(c, Npc)]:
        room = npc.room
        if (room not in targets or ActFlag.AGGRESSIVE not in npc.act or npc.position != Position.STANDING
                or RoomFlag.SAFE in room.room_flags):
            continue
        choices = [p for p in targets[room] if p.fighting is None and not spared(npc, p)]
        if not choices:
            continue
        victim = rng.choice(choices)
        if unnoticed(npc, victim):
            continue
        fight.start_fight(npc, victim)


def spared(npc, p):
    """npc 骰過「不起眼」、決定不打 p，而且 p 還沒離開那間房（arrived 沒變）。"""
    seen = npc.unnoticed.get(p)
    return seen is not None and seen == (p.arrived, True)


def unnoticed(npc, p):
    """半身人的「不起眼」（玩家角色手冊的種族）：npc 第一次要打他時骰一次，一半機率不打，到他離開這間房以前都照這次的結果。
    回傳這次不打。不是半身人一律打。
    """
    if getattr(p, "race", None) != stats.Race.HALFLING:
        return False
    seen = npc.unnoticed.get(p)
    if seen is None or seen[0] != p.arrived:
        seen = npc.unnoticed[p] = (p.arrived, rng.random() < UNNOTICED_CHANCE)
    return seen[1]


def wimpy(battle):
    """回合結束（Fight.tick）：wimpy 的生物 HP 低於上限的一半就骰一次，WIMPY_CHANCE 逃掉。
    能往哪裡逃跟走動一樣（exits），沒有路就不逃；逃掉跟玩家的 flee 一樣，雙方停手（commands.combat.escape）。
    """
    from .commands import combat as combat_commands
    for npc in list(battle.members):
        if (not isinstance(npc, Npc) or ActFlag.WIMPY not in npc.act or npc.fight is not battle or not npc.panel
                or npc.hp >= npc.panel["hp"] / 2 or rng.random() >= WIMPY_CHANCE):
            continue
        ways = exits(npc)
        if ways:
            combat_commands.escape(npc, rng.choice(ways))
