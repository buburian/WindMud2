"""死掉（照 C 版 fight.c 的 raw_kill）：生物死了留下屍體，從遊戲裡拿掉；玩家死了回起始房間。

生物：imm 的 slay、戰鬥打到 HP 0（combat.py）都呼叫 die()。
玩家：戰鬥打到 HP 0 呼叫 player_dies()（使用者選的簡單做法：回起始房間、HP 剩 1，不掉東西、不留屍體，之後設計死亡再改）。
死亡慘叫（C 版 death_cry：隨機訊息、斷頭這類物品、隔壁聽到）還沒做。訊息由呼叫的人送。
"""
import random

from . import affects, fight, meals, objects, scripts, summons, travel, zones   # 坑：fight → combat → death → fight 繞一圈，所以用 fight.stop_fighting，不 from import
from .characters import Position, characters


def stop_all(ch):
    """打 ch 的人和 ch 自己都停手（照 C 版 stop_fighting 的 fBoth）。"""
    for c in characters:
        if c.fighting is ch:
            fight.stop_fighting(c)
    fight.stop_fighting(ch)


def die(npc, rng=random, killer=None):
    """npc 死掉：打牠的人和牠自己停手，原地留下屍體（掉落表骰到的物品放在裡面），從遊戲裡拿掉。回傳屍體（自動拾取用）。

    拿掉以後重置的 limit 數不到牠，下次重置會再放一隻（照 C 版）。
    倒下之前先跑牠腳本的 on_death(killer)（使用者定的：還在房間裡，留遺言做得到）；腳本讓牠消失了（destroy）就不留屍體、回傳 None。
    召喚物（summons.py）被打死不留屍體、不掉東西，回傳 None。
    """
    if npc.master is not None:
        stop_all(npc)
        characters.remove(npc)
        return None
    scripts.fire_owner(npc, "on_death", None, killer)
    if npc not in characters:
        return None
    # 跟牠打的人：在打牠的，和牠在打的（他還沒來得及還手，牠就被別人打死了）
    foes = [c for c in characters if c.fighting is npc or c is npc.fighting]
    stop_all(npc)
    corpse = objects.make_corpse(npc, rng)
    characters.remove(npc)
    from . import skills                    # 坑：skills → affects → combat → death 繞一圈，在函式裡才 import
    for c in foes:                          # 收刀、回神：在打的最後一隻死了、身邊也沒有別的生物在打他，整場戰鬥才算結束
        if c.fighting is None and not any(o.fighting is c for o in characters):
            skills.fight_ended(c)
    return corpse


def player_dies(player):
    """玩家死掉：打他的人和他停手，「死掉後不在」的效果拿掉，回「家」（zones.home：起始房間，學生是學院的第一間），HP 剩 1、站著（使用者選的）。
    穿著死後不虛弱的旅具：HP 回到它的量（不超過上限，設計文件 §3.12）。"""
    stop_all(player)
    affects.on_death(player)
    summons.release(player)                 # 主人死掉：召喚物消失
    player.room = zones.home(player)
    player.hp = float(travel.revive_hp(player) or 1)
    player.position = Position.STANDING
    meals.cancel(player)
