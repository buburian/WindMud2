"""身上的效果（buff／debuff，玩家角色手冊「身上的效果」，設計文件 §2.6）：玩家和生物都可以有。

一個效果（Affect）可以同時有三種作用：
- 暫時加減屬性（applies）：次要屬性加減，跟裝備一樣算進 panel（stats.recompute、npcs.recompute），打架就用得到。
  主屬性照被放的人自己的等級換成次要屬性（使用者定的，stats.add_affects）；生物沒有公會，不算。
- 持續加減 HP／MP／MV（periodic 固定量、periodic_pct 上限的幾成）：每 AFFECT_PULSE_TICKS（3）tick 跳一次，從放下去開始數，放下去那一刻不跳。
  HP 扣到 0 就死（使用者定的），跟被打死同一套（combat.slain）。
- 旗標（flags，area.AffectFlag）：現在只是記號。
- 護盾（shield_pct，使用者 2026-11-06 定的）：放下去時用 HP 上限 × shield_pct 算出幾點（shield）。受到的傷害（攻擊、技能、持續扣血全部）
  先扣護盾、扣完才扣 HP（absorb()）；好幾個護盾先放的先扣；扣光的就破了、拿掉。再放一次（覆蓋）回到滿的。
同一個來源（哪個技能放的）只有一份：再放一次是覆蓋；不同來源就疊。
離線的玩家不在 characters 裡，所以時間停住（存檔存剩下的時間，登入後接著跑）。
坑：combat → death → zones → affects → combat 繞一圈，所以 combat 用 from . import。
"""
import math
from dataclasses import asdict, dataclass, field

from . import act, combat, npcs, stats
from .act import TO_CHAR, TO_ROOM, compose, notify
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
    applies: dict = field(default_factory=dict)     # 屬性的代號（主屬性 stats.PRIMARY_KEYS 或次要屬性 SECONDARY_KEYS）→ 加減多少
    periodic: dict = field(default_factory=dict)    # "hp"、"mp"、"mv" → 每 AFFECT_PULSE_TICKS 加減多少（負的是扣）
    periodic_pct: dict = field(default_factory=dict)    # "hp"、"mp"、"mv" → 每跳一次加減當時上限的幾成（0.10 是 10%）
    flags: AffectFlag = AffectFlag(0)
    keep_on_death: bool = False             # 死掉後還在不在（每個效果自己設定，使用者定的）
    off_message: str = ""                   # 時間到、效果消失時告訴他的話（可以用顏色代碼）；沒寫就用共用的（off_message()）
    shield_pct: float = 0.0                 # 護盾：HP 上限的幾倍（1.2 是 120%）；0 是沒有護盾
    shield: float = 0.0                     # 護盾還剩幾點：add() 放下去時算，被打就扣（absorb）
    hurt: str = ""                          # 持續扣 HP 跳的時候的訊息動詞（「燒傷」：你被【燃燒】燒傷了.(6)）；空的不說
    ticks: int = None                       # 還剩幾個 tick
    elapsed: int = 0                        # 放下去以後過了幾個 tick：決定什麼時候跳（不用剩下的 tick，矮人才不會亂）

    def __post_init__(self):
        if self.ticks is None:
            self.ticks = self.duration


def add(ch, affect):
    """把新做的效果放到 ch 身上：同一個來源已經有就整個換掉（覆蓋：時間回到滿的、跳的時間從頭數），不同來源就疊。

    護盾用 ch 這時候的 HP 上限算幾點（之後上限變了不改）；覆蓋就是回到滿的。
    """
    if affect.shield_pct and ch.panel:
        affect.shield = ch.panel["hp"] * affect.shield_pct
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


PULSE_KEYS = ("hp", "mp", "mv")             # 持續加減的資源，跳的順序
SHIELD_BROKEN = "你的【$t】被打破了。"       # 護盾扣光了（使用者選的：破了就消失）


def absorb(ch, dmg):
    """ch 受到 dmg 點傷害，先扣護盾（先放的先扣）：回傳（護盾吸收了幾點, 被打破的效果）。扣光的護盾拿掉。

    剩下的（dmg − 吸收）才扣 HP，由呼叫的人扣：攻擊、技能（combat.land）、持續扣血（pulse）。
    """
    taken, broken = 0.0, []
    for a in list(ch.affects):
        if taken >= dmg:
            break
        if a.shield <= 0:
            continue
        use = min(a.shield, dmg - taken)
        a.shield -= use
        taken += use
        if a.shield <= 0:
            ch.affects.remove(a)
            broken.append(a)
    if broken:
        changed(ch)
    return taken, broken


def broken_messages(ch, broken):
    """被打破的護盾，每個一句給 ch：[(讀的人, 文字)]，放進那一段訊息（戰鬥的 Fight.tell、tick 的 Messages.tell）。"""
    return [pair for a in broken for pair in compose(SHIELD_BROKEN, ch, t=a.name, to=TO_CHAR)]


def drains_hp(a):
    """持續扣 HP 的效果（固定量或上限的幾成）：矮人的堅韌、扣死都看它。"""
    return a.periodic.get("hp", 0) < 0 or a.periodic_pct.get("hp", 0) < 0


def step(ch, a):
    """這個效果每 tick 減幾：矮人身上持續扣 HP 的減 TOUGH_STEP，其他減 1。"""
    return TOUGH_STEP if getattr(ch, "race", None) == stats.Race.DWARF and drains_hp(a) else 1


WORN_OFF = "你身上的【{}】消失了。"          # 效果消失時共用的那句（使用者要的）


def off_message(a):
    """效果時間到、消失時告訴他的話：有寫 off_message 才用它，沒寫就是共用的「你身上的【名字】消失了。」（使用者要的）。"""
    return a.off_message or WORN_OFF.format(a.name)


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
    act.blocks.append(out)                  # 這個 tick 裡腳本說的話（被扣死時的 on_death）也收進來，一起送
    try:
        for ch in list(characters):         # 會有生物被扣死、移出 characters
            if ch.affects:
                tick_one(ch, out)
    finally:
        act.blocks.remove(out)
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
            out.tell(compose(off_message(a), ch, to=TO_CHAR))


def pulse(ch, a, out):
    """跳一次：HP、MP、MV 照 periodic（固定量）＋ periodic_pct（當時上限的幾成）加減，加不超過上限、MP／MV 扣到 0 為止。
    HP 扣到 0 就死，回傳 True。

    打架中被扣死：算被他正在打的對手打死（照常給經驗）；沒在打架誰都不給經驗（使用者定的）。
    """
    if not ch.panel:
        return False
    for key in PULSE_KEYS:
        if key not in a.periodic and key not in a.periodic_pct:
            continue
        now = getattr(ch, key)
        n = a.periodic.get(key, 0.0) + ch.panel[key] * a.periodic_pct.get(key, 0.0)
        if n >= 0:
            setattr(ch, key, max(now, min(ch.panel[key], now + n)))
        elif key == "hp":
            taken, broken = absorb(ch, -n)  # 持續扣血也先扣護盾（使用者選的：全部傷害）
            ch.hp = now + n + taken
            if a.hurt:                      # 跳的訊息（燃燒）：被燒的亮青、同房間的人不上色，跟戰鬥訊息一樣
                tail = combat.damage_tail(-n, taken)
                out.tell(compose("{C你被【$t】" + a.hurt + "了{x" + tail, ch, t=a.name, to=TO_CHAR))
                out.tell(compose("$n被【$t】" + a.hurt + "了" + tail, ch, t=a.name, to=TO_ROOM))
            out.tell(broken_messages(ch, broken))
        else:
            setattr(ch, key, min(now, max(0.0, now + n)))
    if drains_hp(a) and ch.hp <= 0:
        combat.slain(out, ch.fighting, ch)
        return True
    return False


def parts(a, listing=False):
    """這個效果做什麼，一樣一句：持續加減（「每 3 秒 HP -10」「每 3 秒 HP +上限的 10%」）、加減屬性（「命中 +10」）、旗標（「失明」）、護盾。

    護盾：身上的寫還剩幾點（score、mstat）；listing（skills 列技能，還沒放到誰身上）寫「護盾 HP 上限的 120%」。
    """
    every = AFFECT_PULSE_TICKS * TICK_SECONDS
    return ([f"每 {every:g} 秒 {stats.STAT_NAMES[k]} {n:+g}" for k, n in a.periodic.items()]
            + [f"每 {every:g} 秒 {stats.STAT_NAMES[k]} {'+' if f >= 0 else '-'}上限的 {abs(f) * 100:g}%" for k, f in a.periodic_pct.items()]
            + [f"{stats.STAT_NAMES[k]} {n:+g}" for k, n in a.applies.items()]
            + [AFFECT_FLAG_NAMES[f] for f in AffectFlag if f in a.flags]
            + ([f"護盾 HP 上限的 {a.shield_pct * 100:g}%" if listing else f"護盾還剩 {stats.shown(a.shield)} 點"]
               if a.shield_pct else []))


def describe(ch, a):
    """mstat 的一段：「測試毒：還有 25 秒，每 3 秒 HP -10」（score 最下面的那段另外排）。"""
    return f"{a.name}：" + "，".join([f"還有 {seconds_left(ch, a):g} 秒", *parts(a)])


def to_data(a):
    """存檔用：剩下的時間、跳到哪裡都存，登入後接著跑。"""
    return {**asdict(a), "flags": int(a.flags)}


def from_data(d):
    return Affect(**{**d, "flags": AffectFlag(d["flags"])})
