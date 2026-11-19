"""戰鬥類指令：kill 開打、flee 逃跑。"""
import random

from .. import damage, death, fight, stats, terrain
from ..act import TO_CHAR, act
from ..area import RoomFlag
from ..characters import find_in_room
from ..config import TICK_SECONDS
from ..npcs import Npc
from . import system

rng = random                                # flee 的亂數（測試換掉）
FLEE_WAIT_TICKS = 2                         # flee 失敗後要等幾個 tick 才能再逃（使用者定的；世界 tick 減，實際等 1～2 秒）


def do_kill(ch, arg):
    """kill <名字>：開打同房間的生物，牠會自動還手（照 C 版）。不可以打玩家（使用者要的），自己也不行。

    下一個回合開始出手（一秒以內），每一下的傷害、訊息在 combat.py。訊息照 C 版 do_kill。
    """
    words = arg.split()
    if not words:
        ch.send("你想要攻擊誰？如果苗頭不對，要記得逃跑(Flee)喔!!\n")
        return
    victim = find_in_room(ch, words[0])
    if victim is None:
        ch.send("找不到你想攻擊的人。\n")
        return
    if not isinstance(victim, Npc):
        ch.send("你不可以攻擊玩家。\n")
        return
    if protected(ch, victim):
        return
    if ch.fighting is not None:
        ch.send("你現在正在為自己的戰鬥努力著!!\n")
        return
    fight.start_fight(ch, victim)


CONSIDER_WHO = "你想考慮要殺誰啊？"        # 照 C 版 do_consider
# 對方比你強幾級（damage.power_gap，戰力換算）小於這個數 → 說這句；都不是就是最後一句。
# 句子照 C 版 do_consider，分段改照戰力（使用者 2026-11-19 定的：C 版看等級差，我們差 1 級勝率就從 95% 掉到 5%，設計文件 §4.4）
CONSIDER = [
    (-5.0, "你可以毫不費力的對付$N。"),
    (-2.0, "$N根本不是你的對手。"),
    (-0.5, "$N看起來滿容易對付的。"),
    (0.5, "$N是一個好對手!"),
    (1.5, "$N說，除非你有點運氣。"),
    (3.0, "$N大笑，不把你放在眼裡。"),
]
CONSIDER_DEAD = "你將會受到死神的眷顧。"


def do_consider(ch, arg):
    """consider <名字>：跟同房間的生物比戰力，用一句話說打不打得過（照 C 版的句子，使用者 2026-11-19 要的，規則在玩家角色手冊「戰鬥」）。

    只是看：不開打、不改任何人，安全區、打架中都能用。找人的檢查跟 kill 一樣。
    """
    words = arg.split()
    if not words:
        ch.send(CONSIDER_WHO + "\n")
        return
    victim = find_in_room(ch, words[0])
    if victim is None:
        ch.send("找不到你想攻擊的人。\n")
        return
    if not isinstance(victim, Npc):
        ch.send("你不可以攻擊玩家。\n")
        return
    act(consider_text(damage.power_gap(ch, victim)), ch, victim, to=TO_CHAR)


def consider_text(gap):
    """對方比你強 gap 級（可以是 ±inf）：consider 說的那句。"""
    return next((text for bound, text in CONSIDER if gap < bound), CONSIDER_DEAD)


def protected(ch, victim):
    """victim 在安全區（RoomFlag.SAFE）：不能對牠開打，送 C 版那句、回傳 True。kill 和 use 的傷害技能用（使用者要的）。

    開打的地方只有 kill、use、主動攻擊（behavior.aggress 自己看 SAFE），都擋掉了，所以安全區裡不會有戰鬥。
    """
    if RoomFlag.SAFE not in victim.room.room_flags:
        return False
    act("$N正在受到神力所保護的房間內。", ch, victim, to=TO_CHAR)
    return True


def do_flee(ch, arg):
    """flee：從戰鬥中逃跑（戰鬥中不能用走的）。機率照 DEX（stats.flee_chance），成功往隨機一個開著的出口跑掉。

    照 C 版 do_flee 的訊息；C 版的扣經驗、職業、等級差、試 6 次不做。失敗要等 FLEE_WAIT_TICKS 才能再逃（使用者定的）。
    """
    if ch.fighting is None:
        ch.send("你在害怕什麼呢？你沒有在跟任何一個人戰鬥啊。\n")
        return
    waits = getattr(ch, "cooldowns", None)  # 生物沒有冷卻：不用等
    if waits and waits.get("flee"):
        ch.send(f"你還要等 {waits['flee'] * TICK_SECONDS:g} 秒才能再逃跑。\n")
        return
    exits = [d for d in ch.room.exits if not (d in ch.room.doors and ch.room.doors[d].closed)
             and terrain.can_go(ch, ch.room, d)]            # 走不過去的地形（要飛、要船…）不挑
    if not exits:
        ch.send("這裡沒有可以逃跑的出口！\n")
        return
    if rng.random() >= stats.flee_chance(ch):
        ch.send("你逃跑失敗了。\n")
        if waits is not None:
            waits["flee"] = FLEE_WAIT_TICKS
        return
    escape(ch, rng.choice(exits))


def escape(ch, direction):
    """逃跑成功（玩家的 flee、wimpy 的生物，behavior.wimpy）：他和打他的人都停手（照 C 版 stop_fighting 的 fBoth），往 direction 跑掉。"""
    death.stop_all(ch)
    ch.send("你從戰鬥中逃跑了!!\n")
    system.move(ch, direction, leave="$n往$t邊逃竄(Flee)了!!。")
