"""戰鬥：一場戰鬥一個 loop。

一場戰鬥＝同一間房裡互打的一群人。每場從開打算起，每 ROUND_SECONDS 秒一回合，各跑各的節拍。
一個人同時只會在一場：兩場的人互打，就把後開的那場併進先開的那場。
每場戰鬥屬於它所在的區域物件（zone.fights），區域物件釋放時一起停。
出手（hit）現在是空的，傷害之後照設計文件做。
"""
import asyncio
import itertools
import logging

from .characters import Position, characters
from .clock import cancel, every
from .config import ROUND_SECONDS

log = logging.getLogger(__name__)

_order = itertools.count()                  # 開打的順序：合併時看誰先開


class Fight:
    """一場戰鬥。"""

    def __init__(self, zone):
        self.zone = zone                    # 在哪個區域物件（zones.Zone）
        self.members = []                   # 參戰的角色，照加入的順序出手
        self.order = next(_order)
        self.task = None                    # 這場自己的 loop

    async def run(self):
        try:
            await every(ROUND_SECONDS, self.round)
        finally:                            # 打完、出錯、被停掉（區域物件釋放）都會走到這裡
            end(self)

    def round(self):
        """一回合：照順序，每個人打自己的對手。回傳 False 代表這場結束了。"""
        try:
            for ch in list(self.members):
                if ch.fight is not self:    # 這一回合裡已經停手了
                    continue
                victim = ch.fighting
                if victim not in characters or victim.room is not ch.room:
                    stop_fighting(ch)       # 對手離開遊戲、或不在同一間房了
                    continue
                if victim.fight is not self:
                    start_fight(ch, victim) # 對手停了手又被打：拉回這一場（在別場就合併），C 版也是這樣
                hit(ch, victim)
        except Exception:
            log.exception("戰鬥出錯，結束這一場")
            return False
        return bool(self.members)


def hit(ch, victim):
    """ch 打 victim 一回合。還沒做：傷害之後照設計文件做。"""


def start_fight(ch, victim):
    """ch 開打 victim（兩個人在同一間房）。回傳他們所在的那一場。要在 asyncio 裡呼叫。

    都不在戰鬥：在 ch 所在的區域物件開一場新的。有一個人在打：另一個人加進那一場。
    兩個人在不同場：後開的那場併進先開的那場。victim 沒在打人的話，會自動還手。
    """
    fight = _together(ch.fight, victim.fight) or _new_fight(ch.room.zone)
    ch.fighting = victim
    if victim.fighting is None:
        victim.fighting = ch
    for c in (ch, victim):
        if c.fight is None:
            c.fight = fight
            fight.members.append(c)
        c.position = Position.FIGHTING
    return fight


def stop_fighting(ch):
    """ch 停手：移出那一場，姿勢回到站著。"""
    if ch.fight is not None and ch in ch.fight.members:
        ch.fight.members.remove(ch)
    ch.fight = ch.fighting = None
    if ch.position == Position.FIGHTING:
        ch.position = Position.STANDING


def end(fight):
    """結束一場戰鬥：裡面的人全部停手，停掉它的 loop。"""
    for ch in list(fight.members):
        stop_fighting(ch)
    fight.zone.fights.discard(fight)
    cancel(fight.task)


def _new_fight(zone):
    fight = Fight(zone)
    zone.fights.add(fight)
    fight.task = asyncio.create_task(fight.run(), name="戰鬥")
    return fight


def _together(a, b):
    """a、b 兩場（可能是 None）變成一場：不同場就把後開的併進先開的。回傳留下來的那場，都沒有就是 None。"""
    if a is None or b is None or a is b:
        return a or b
    keep, gone = (a, b) if a.order < b.order else (b, a)
    for c in gone.members:
        c.fight = keep
        keep.members.append(c)
    gone.members.clear()
    end(gone)
    return keep
