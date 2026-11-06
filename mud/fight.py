"""戰鬥：一場戰鬥一個 loop。

一場戰鬥＝同一間房裡互打的一群人。每場從開打算起，每個 tick（TICK_SECONDS，1 秒）跑一次，各跑各的節拍。
一回合 ＝ ROUND_TICKS（2）個 tick：打一輪、停一秒。
出手照時間軸（玩家角色手冊「戰鬥的出手順序」）：每隻手記「下一次出手的時間」，
出手後加上間隔 ＝ 一回合 ÷ 這隻手每回合出手幾次。時間用 tick 算，開打那一刻是 0。
一個人同時只會在一場：兩場的人互打，就把後開的那場併進先開的那場。
每場戰鬥屬於它所在的區域物件（zone.fights），區域物件釋放時一起停。
每回合幾下照攻速（damage.attacks_per_round），一下打出去的傷害、訊息、死掉在 combat.py。
一回合的訊息先放在 messages，回合結束時每個人只送一次（一下一個 notify 會冒出好幾個 prompt）。
"""
import asyncio
import heapq
import itertools
import logging

from . import combat, damage                # 坑：combat 會 import 回來，要用「模組.名字」，不能 from .combat import hit
from .act import notify
from .characters import Position, characters
from .clock import cancel, every
from .config import ROUND_TICKS, TICK_SECONDS

log = logging.getLogger(__name__)

_order = itertools.count()                  # 開打的順序：合併時看誰先開
_joins = itertools.count()                  # 加入戰鬥的順序：同一時間出手時，先加入的先打


class Fight:
    """一場戰鬥。"""

    def __init__(self, zone):
        self.zone = zone                    # 在哪個區域物件（zones.Zone）
        self.members = []                   # 參戰的角色，照加入的順序
        self.order = next(_order)
        self.task = None                    # 這場自己的 loop
        self.ticks = 0                      # 開打後過了幾個 tick，也是時間軸的「現在」
        self.queue = []                     # 時間軸（heapq）：(下一次出手的時間, 加入的順序, 第幾隻手, 角色)
        self.joined = {}                    # 角色 → 加入的順序；停手後又加入會換新的，舊的排程就作廢
        self.armed = {}                     # 角色 → 時間軸上排了幾隻手（打架中換武器時 arm() 用）
        self.messages = {}                  # 這一回合要送的訊息：讀的人 → [句子]，回合結束時合成一段送（flush）

    async def run(self):
        try:
            await every(TICK_SECONDS, self.tick)
        finally:                            # 打完、出錯、被停掉（區域物件釋放）都會走到這裡
            end(self)

    def tick(self):
        """一個 tick：每回合的第一個 tick 打一輪，其他 tick 停（打一輪、停一秒）。回傳 False 代表這場結束了。"""
        self.ticks += 1
        if (self.ticks - 1) % ROUND_TICKS == 0:
            try:
                self.round()
            except Exception:
                log.exception("戰鬥出錯，結束這一場")
                return False
        return bool(self.members)

    def join(self, ch):
        """ch 加入這一場：每隻手的第一下排在現在（開打的兩個人都是 0）。"""
        ch.fight = self
        self.members.append(ch)
        seq = self.joined[ch] = next(_joins)
        self.armed[ch] = len(attacks(ch))
        for hand in range(self.armed[ch]):
            heapq.heappush(self.queue, (self.ticks, seq, hand, ch))

    def arm(self, ch):
        """打架中換了武器（inventory.changed）：手變多了（穿上副手武器），把多的那隻手排在「現在 ＋ 一次間隔」。

        不排在現在：不然一直換武器就能多打。手變少了不用做什麼：round() 拿到多出來的那隻手就丟掉。
        """
        if ch.fight is not self or ch not in self.joined:
            return
        hands = attacks(ch)
        for hand in range(self.armed.get(ch, 0), len(hands)):
            heapq.heappush(self.queue, (round(self.ticks + ROUND_TICKS / hands[hand], 9), self.joined[ch], hand, ch))
        self.armed[ch] = max(self.armed.get(ch, 0), len(hands))

    def round(self):
        """一輪：這一回合（從 ticks − 1 起 ROUND_TICKS 個 tick）結束前的出手，照時間依序打出來。

        同一時間：先加入的先打（開打的人比還手的人先），同一個人主手先、副手後。
        這一回合的訊息打完才送（flush），每個人只收到一段、一個 prompt。
        """
        end_time = self.ticks - 1 + ROUND_TICKS
        try:
            while self.queue and self.queue[0][0] < end_time:
                t, seq, hand, ch = heapq.heappop(self.queue)
                if ch.fight is not self or self.joined.get(ch) != seq:
                    continue                # 已經停手，或停手後又加入了：這一筆作廢
                victim = ch.fighting
                if victim not in characters or victim.room is not ch.room:
                    stop_fighting(ch)       # 對手離開遊戲（例如死了）、或不在同一間房了
                    continue
                if victim.fight is not self:
                    start_fight(ch, victim)     # 對手停了手又被打：拉回這一場（在別場就合併），C 版也是這樣
                    if ch.fight is not self:    # 這一場併進先開的那場了，剩下的由那場打
                        return
                hands = attacks(ch)
                if hand >= len(hands):          # 打架中脫掉了副手武器：這隻手不打了（要在 hit() 前面，不然會用空手多打一下）
                    self.armed[ch] = min(self.armed.get(ch, 0), hand)
                    continue
                hit(ch, victim, hand)
                # 坑：浮點數一直加會有誤差（1.6 加三次是 4.800000000000001），剛好在回合邊界的出手會排錯回合，所以取到小數 9 位
                heapq.heappush(self.queue, (round(t + ROUND_TICKS / attacks(ch)[hand], 9), seq, hand, ch))
        finally:
            self.flush()

    def tell(self, pairs):
        """把 act.compose() 算好的 [(讀的人, 文字)] 放進這一回合的訊息。"""
        for reader, text in pairs:
            self.messages.setdefault(reader, []).append(text)

    def flush(self, me=None):
        """這一回合的訊息：每個人合成一段，只 notify() 一次（只補一個 prompt）。

        me：下指令的人（技能是打指令當下就打）。他那段當作指令的回覆送，prompt 由 command() 補，不然會有兩個。
        """
        messages, self.messages = self.messages, {}
        for reader, lines in messages.items():
            if reader is me:
                reader.send("\n".join(lines) + "\n")
            else:
                notify(reader, "\n".join(lines))


def attacks(ch):
    """ch 每隻手每回合出手幾次，主手在前（都要大於 0）：照攻速（damage.attacks_per_round）。

    雙持（主手、副手都拿武器）是 [A × 0.70, A × 0.3607…]（玩家角色手冊「雙持」）；沒有屬性的角色（測試直接建的）是 1 下。
    小數不用擲骰子：間隔是一回合 ÷ 次數，自然會有些回合多打一下。
    """
    if not getattr(ch, "panel", None):
        return [1.0]
    a = damage.attacks_per_round(ch)
    if damage.dual_wielding(ch):
        return [a * damage.DUAL_WIELD_MAIN, a * damage.DUAL_OFFHAND]
    return [a]


def hit(ch, victim, hand):
    """ch 用第 hand 隻手（0 是主手）打 victim 一下：傷害、訊息、死掉在 combat.hit()。測試可以換掉這個函式。"""
    combat.hit(ch, victim, hand)


def start_fight(ch, victim):
    """ch 開打 victim（兩個人在同一間房）。回傳他們所在的那一場。要在 asyncio 裡呼叫。

    都不在戰鬥：在 ch 所在的區域物件開一場新的。有一個人在打：另一個人加進那一場。
    兩個人在不同場：後開的那場併進先開的那場。victim 沒在打人的話，會自動還手。
    """
    fight = _together(ch.fight, victim.fight) or _new_fight(ch.room.zone)
    ch.fighting = victim
    if victim.fighting is None:
        victim.fighting = ch
    for c in (ch, victim):                  # ch 先加入：同一時間出手時，先動手的人先打
        if c.fight is None:
            fight.join(c)
        c.position = Position.FIGHTING
    return fight


def stop_fighting(ch):
    """ch 停手：移出那一場，姿勢回到站著。"""
    if ch.fight is not None:
        if ch in ch.fight.members:
            ch.fight.members.remove(ch)
        ch.fight.joined.pop(ch, None)       # 時間軸上他的出手跟著作廢
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
        keep.join(c)                        # 第一下排在留下那場的「現在」
    gone.members.clear()
    end(gone)
    return keep
