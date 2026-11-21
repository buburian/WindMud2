"""打架中更順（設計文件 §2.6，使用者 2026-11-21 定的，規則在玩家角色手冊「技能」）：技能排隊、破綻。

- 排隊：打架中 use 還在冷卻的技能（commands/skills.ready），記在 ch.queued（技能 id → 打了名字的那隻，沒打名字是 None；照排的順序）。
  每場戰鬥每個 tick（Fight.tick → fight_tick），冷卻好了的照順序放，跟打指令一樣檢查（commands/skills.cast）。
  暈、凍住、沉默時不放、留著；打名字的那隻死了、不在這裡就靜靜拿掉（我們定的）；其他檢查沒過說平常那句、拿掉。
- 破綻：每回合打完，每個在打的玩家擲 BREACH_CHANCE。有的話到下一回合打完以前，use 一個還在冷卻的技能可以馬上放（ready() 用掉）；
  破綻出現時有排著的，排最前面那個馬上放。生物不擲。
- 戰鬥結束（他沒在打、也沒人在打他，跟收刀一樣）settle() 清掉排隊和破綻：fight.stop_fighting() 對停手的人和他原本的對手各看一次。
自動放的時候不是他打的指令：技能送給他的字（ch.send）用 Into 轉進那一場的訊息，所以跟戰鬥訊息同一段、一個 prompt、受傷狀態在最後。
"""
import contextlib
import random

from . import act, affects
from .characters import characters
from .players import Player

rng = random                                # 破綻的亂數（測試換掉；tests/conftest.py 預設換成不會有）
BREACH_CHANCE = 0.2                         # 每回合打完，對手露出破綻的機率
BREACH = "{Y$N露出了破綻！{x"               # 只有自己看到，在受傷狀態那行前面
TAKEN = "你抓住了破綻！"                     # 用掉破綻：技能訊息前面
QUEUED = "{}還要等 {} 秒，好了就放。"        # 打架中技能還在冷卻：排起來


def add(ch, skill, chosen):
    """排 skill：chosen 是打了名字的那隻（沒打名字是 None）。已經排著就換目標、順序不變（dict 的同一個 key）。"""
    ch.queued[skill.id] = chosen


def settle(ch):
    """戰鬥結束了（ch 沒在打、也沒人在打他）就清掉排隊和破綻；打死一隻、另一隻還在打他不清。
    fight.stop_fighting() 對停手的人和他原本的對手各呼叫一次（坑：打死怪時先停玩家，那時怪還指著他，要等停怪時再看一次）。
    """
    if not isinstance(ch, Player) or ch.fighting is not None or any(c.fighting is ch for c in characters):
        return
    ch.queued.clear()
    ch.breach = False


def fight_tick(battle, round_end):
    """battle 的一個 tick（Fight.tick 在 collecting() 裡、special 後面呼叫）：每個玩家冷卻好的排隊技能照順序放；
    round_end（回合打完的那個 tick）再擲破綻。放出去的技能可能打死怪、讓這場併進別場，所以每放一個之前都再看還在不在這場。
    """
    players = [c for c in battle.members if isinstance(c, Player)]
    for ch in players:
        for sid in list(ch.queued):
            if ch.fight is not battle or affects.controlled(ch, affects.MUTED):
                break
            prune(ch)                       # 前一個放出去的可能打死了這個打名字的那隻
            if sid in ch.queued and not ch.cooldowns.get(sid):
                fire(battle, ch, sid)
    if round_end:
        for ch in players:
            roll(battle, ch)


def roll(battle, ch):
    """回合打完：ch 正在打的對手（還在同一間房）有 BREACH_CHANCE 露出破綻，沒中的話舊的過期。有排著的就馬上放排最前面那個（被暈、凍住時不放）。"""
    if ch.fight is not battle:
        return
    foe = ch.fighting
    ch.breach = foe is not None and foe in characters and foe.room is ch.room and rng.random() < BREACH_CHANCE
    if not ch.breach:
        return
    battle.tell(act.compose(BREACH, ch, foe, to=act.TO_CHAR))
    if affects.controlled(ch, affects.MUTED):
        return
    prune(ch)                               # 已經不能放的不算「排最前面的」
    if ch.queued:
        fire(battle, ch, next(iter(ch.queued)))


def prune(ch):
    """靜靜拿掉排著但已經放不了的：打名字的那隻死了、不在這裡，技能忘了（imm 的 sset off）。"""
    from . import skills                    # 坑：skills 會 import 戰鬥的模組，在函式裡才 import
    known = skills.known(ch)
    for sid, chosen in list(ch.queued.items()):
        if skills.SKILLS.get(sid) not in known or (chosen is not None and (chosen not in characters or chosen.room is not ch.room)):
            del ch.queued[sid]


def fire(battle, ch, sid):
    """放排著的 sid（從排隊拿掉，先 prune 過）：跟打指令一樣（commands/skills.cast），送給他的字進那一場的訊息。"""
    from . import skills
    from .commands import skills as command     # 坑：commands 會 import 戰鬥的模組，在函式裡才 import
    chosen = ch.queued.pop(sid)
    with into(battle, ch):
        command.cast(ch, skills.SKILLS[sid], chosen)


class Into:
    """自動放的時候當 ch.capture（Player.send 會 append）：送給他的字照順序放進那一場的訊息。"""

    def __init__(self, battle, ch):
        self.battle, self.ch = battle, ch

    def append(self, text):
        text = text.rstrip("\n")
        if text:
            self.battle.tell([(self.ch, text)])


@contextlib.contextmanager
def into(battle, ch):
    """這一段送給 ch 的字放進 battle 的訊息（回合結束時跟戰鬥訊息一起送）。"""
    old, ch.capture = ch.capture, Into(battle, ch)
    try:
        yield
    finally:
        ch.capture = old
