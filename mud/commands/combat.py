"""戰鬥類指令。現在只有 kill；flee 還沒做（戰鬥中還是可以用走的離開）。"""
from .. import fight
from ..characters import find_in_room
from ..npcs import Npc


def do_kill(ch, arg):
    """kill <名字>：開打同房間的生物，牠會自動還手（照 C 版）。不可以打玩家（使用者要的），自己也不行。

    下一個回合開始出手（一秒以內），每一下的傷害、訊息在 combat.py。訊息照 C 版 do_kill（C 版教人 flee 的那句拿掉，還沒有 flee）。
    """
    words = arg.split()
    if not words:
        ch.send("你想要攻擊誰？\n")
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
