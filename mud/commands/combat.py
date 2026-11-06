"""戰鬥類指令：kill 開打、flee 逃跑。"""
import random

from .. import death, fight, stats
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
    if ch.fighting is not None:
        ch.send("你現在正在為自己的戰鬥努力著!!\n")
        return
    fight.start_fight(ch, victim)


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
    exits = [d for d in ch.room.exits if not (d in ch.room.doors and ch.room.doors[d].closed)]
    if not exits:
        ch.send("這裡沒有可以逃跑的出口！\n")
        return
    if rng.random() >= stats.flee_chance(ch):
        ch.send("你逃跑失敗了。\n")
        if waits is not None:
            waits["flee"] = FLEE_WAIT_TICKS
        return
    direction = rng.choice(exits)
    death.stop_all(ch)                      # 他和打他的人都停手（照 C 版 stop_fighting 的 fBoth）
    ch.send("你從戰鬥中逃跑了!!\n")
    system.move(ch, direction, leave="$n往$t邊逃竄(Flee)了!!。")
