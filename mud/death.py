"""死掉（照 C 版 fight.c 的 raw_kill）：生物死了留下屍體，從遊戲裡拿掉；玩家死了回起始房間。

生物：imm 的 slay、戰鬥打到 HP 0（combat.py）都呼叫 die()。
玩家：戰鬥打到 HP 0 呼叫 player_dies()（使用者選的簡單做法：回起始房間、HP 剩 1，不掉東西、不留屍體，之後設計死亡再改）。
死亡慘叫（C 版 death_cry：隨機訊息、斷頭這類物品、隔壁聽到）還沒做。訊息由呼叫的人送。
"""
import random

from . import affects, fight, objects, zones   # 坑：fight → combat → death → fight 繞一圈，所以用 fight.stop_fighting，不 from import
from .characters import Position, characters


def stop_all(ch):
    """打 ch 的人和 ch 自己都停手（照 C 版 stop_fighting 的 fBoth）。"""
    for c in characters:
        if c.fighting is ch:
            fight.stop_fighting(c)
    fight.stop_fighting(ch)


def die(npc, rng=random):
    """npc 死掉：打牠的人和牠自己停手，原地留下屍體（掉落表骰到的物品放在裡面），從遊戲裡拿掉。

    拿掉以後重置的 limit 數不到牠，下次重置會再放一隻（照 C 版）。
    """
    stop_all(npc)
    objects.make_corpse(npc, rng)
    characters.remove(npc)


def player_dies(player):
    """玩家死掉：打他的人和他停手，「死掉後不在」的效果拿掉，回到起始房間，HP 剩 1、站著（使用者選的）。"""
    stop_all(player)
    affects.on_death(player)
    player.room = zones.start_room()
    player.hp = 1.0
    player.position = Position.STANDING
