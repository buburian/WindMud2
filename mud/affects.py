"""身上的效果（buff／debuff，玩家角色手冊「身上的效果」，設計文件 §2.6）：玩家和生物都可以有。

一個效果（Affect）可以同時有三種作用：
- 暫時加減屬性（applies）：次要屬性加減，跟裝備一樣算進 panel（stats.recompute、npcs.recompute），打架就用得到。
  主屬性下一步才加（使用者定的：可以加減，換算用哪個等級還沒定）。
- 持續加減 HP／MP／MV（periodic）：每 AFFECT_PULSE_TICKS（3）tick 跳一次，從放下去開始數，放下去那一刻不跳。
  HP 扣到 0 就死（使用者定的），跟被打死同一套（combat.slain）。
- 旗標（flags，area.AffectFlag）：現在只是記號。
同一個來源（哪個技能放的）只有一份：再放一次是覆蓋；不同來源就疊。
離線的玩家不在 characters 裡，所以時間停住（存檔存剩下的時間，登入後接著跑）。
坑：combat → death → zones → affects → combat 繞一圈，所以 combat 用 from . import。
"""
import math
from dataclasses import asdict, dataclass, field

from . import combat, npcs, stats
from .act import TO_CHAR, compose, notify
from .area import AFFECT_FLAG_NAMES, AffectFlag
from .characters import characters
from .config import AFFECT_PULSE_TICKS, TICK_SECONDS

TOUGH_STEP = 2                              # 矮人的堅韌：持續扣 HP 的效果每 tick 減 2（跳的時間點照樣從放下去開始數，所以只跳一半）


@dataclass
class Affect:
    """身上的一個效果。ticks、elapsed 不用給：新做的從 duration、0 開始（讀存檔時才給）。"""
    source: str                             # 哪個技能放的（技能 id；imm 的測試效果是 test_…）：同一個來源只有一份
    name: str                               # 顯示的名字
    duration: int                           # 總共幾個 tick（覆蓋時回到這麼多）
    applies: dict = field(default_factory=dict)     # 次要屬性的代號（stats.SECONDARY_KEYS）→ 加減多少
    periodic: dict = field(default_factory=dict)    # "hp"、"mp"、"mv" → 每 AFFECT_PULSE_TICKS 加減多少（負的是扣）
    flags: AffectFlag = AffectFlag(0)
    keep_on_death: bool = False             # 死掉後還在不在（每個效果自己設定，使用者定的）
    off_message: str = ""                   # 時間到、效果消失時告訴他的話（可以用顏色代碼）；空的就不說
    ticks: int = None                       # 還剩幾個 tick
    elapsed: int = 0                        # 放下去以後過了幾個 tick：決定什麼時候跳（不用剩下的 tick，矮人才不會亂）

    def __post_init__(self):
        if self.ticks is None:
            self.ticks = self.duration


def add(ch, affect):
    """把新做的效果放到 ch 身上：同一個來源已經有就整個換掉（覆蓋：時間回到滿的、跳的時間從頭數），不同來源就疊。"""
    ch.affects[:] = [a for a in ch.affects if a.source != affect.source] + [affect]
    changed(ch)


def remove(ch, source):
    """拿掉 source 放的效果（沒有就什麼都不做）。"""
    ch.affects[:] = [a for a in ch.affects if a.source != source]
    changed(ch)


def clear(ch):
    """拿掉全部的效果。"""
    ch.affects.clear()
    changed(ch)


def has_flag(ch, flag):
    """ch 身上有沒有帶著 flag（AffectFlag）的效果。"""
    return any(flag in a.flags for a in ch.affects)


def changed(ch):
    """效果變了：從頭算屬性（玩家、生物的 recompute 都會加上效果），HP、MP、MV 夾在新上限（跟脫裝備一樣，上限變高不補）。"""
    if not ch.panel:                        # 沒有屬性（測試直接建的角色）
        return
    (npcs.recompute if isinstance(ch, npcs.Npc) else stats.recompute)(ch)
    stats.clamp(ch)


def on_death(ch):
    """死掉：拿掉「死掉後不在」的效果（keep_on_death 是 False 的）。"""
    ch.affects[:] = [a for a in ch.affects if a.keep_on_death]
    changed(ch)


def step(ch, a):
    """這個效果每 tick 減幾：矮人身上持續扣 HP 的減 TOUGH_STEP，其他減 1。"""
    return TOUGH_STEP if getattr(ch, "race", None) == stats.Race.DWARF and a.periodic.get("hp", 0) < 0 else 1


def seconds_left(ch, a):
    """還有幾秒：剩下的 tick ÷ 每 tick 減幾（矮人的毒走得快），進位。"""
    return math.ceil(a.ticks / step(ch, a)) * TICK_SECONDS


class Messages:
    """一個 tick 的訊息先收起來，最後每個人只 notify 一次（只補一個 prompt）。"""

    def __init__(self):
        self.by = {}

    def tell(self, pairs):                  # 跟 fight.Fight.tell 一樣收 act.compose() 算好的 [(讀的人, 文字)]：combat.slain 也用它
        for reader, text in pairs:
            self.by.setdefault(reader, []).append(text)

    def flush(self):
        for reader, lines in self.by.items():
            notify(reader, "\n".join(lines))


def tick():
    """世界每個 tick：全部角色（玩家和生物，副本裡的也是）身上的效果走 1 tick（掛在角色身上的定時事情放世界 tick）。"""
    out = Messages()
    for ch in list(characters):             # 會有生物被扣死、移出 characters
        if ch.affects:
            tick_one(ch, out)
    out.flush()


def tick_one(ch, out):
    """ch 身上的每個效果：elapsed ＋1、剩下的減 1（矮人的毒減 2）；elapsed 是 3 的倍數就跳；剩下 ≤ 0 就拿掉（跳完才拿掉）。"""
    gone = []
    for a in list(ch.affects):
        a.elapsed += 1
        a.ticks -= step(ch, a)
        if a.elapsed % AFFECT_PULSE_TICKS == 0 and pulse(ch, a, out):
            break                           # 扣死了：死掉時已經處理過身上的效果（玩家 on_death，生物移出遊戲）
        if a.ticks <= 0:
            ch.affects.remove(a)
            gone.append(a)
    if gone:
        changed(ch)
        for a in gone:
            if a.off_message:
                out.tell(compose(a.off_message, ch, to=TO_CHAR))


def pulse(ch, a, out):
    """跳一次：HP、MP、MV 照 periodic 加減，加不超過上限、MP／MV 扣到 0 為止。HP 扣到 0 就死，回傳 True。

    打架中被扣死：算被他正在打的對手打死（照常給經驗）；沒在打架誰都不給經驗（使用者定的）。
    """
    if not ch.panel:
        return False
    for key, n in a.periodic.items():
        now = getattr(ch, key)
        if n >= 0:
            setattr(ch, key, max(now, min(ch.panel[key], now + n)))
        elif key == "hp":
            ch.hp = now + n
        else:
            setattr(ch, key, min(now, max(0.0, now + n)))
    if a.periodic.get("hp", 0) < 0 and ch.hp <= 0:
        combat.slain(out, ch.fighting, ch)
        return True
    return False


def describe(ch, a):
    """affects、mstat 的一行：「測試毒：還有 25 秒，每 3 秒 HP -10」。"""
    parts = [f"還有 {seconds_left(ch, a):g} 秒"]
    every = AFFECT_PULSE_TICKS * TICK_SECONDS
    parts += [f"每 {every:g} 秒 {stats.STAT_NAMES[k]} {n:+g}" for k, n in a.periodic.items()]
    parts += [f"{stats.STAT_NAMES[k]} {n:+g}" for k, n in a.applies.items()]
    parts += [AFFECT_FLAG_NAMES[f] for f in AffectFlag if f in a.flags]
    return f"{a.name}：" + "，".join(parts)


def to_data(a):
    """存檔用：剩下的時間、跳到哪裡都存，登入後接著跑。"""
    return {**asdict(a), "flags": int(a.flags)}


def from_data(d):
    return Affect(**{**d, "flags": AffectFlag(d["flags"])})
