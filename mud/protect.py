"""替人擋（保護類的守護、不倒之盾，設計文件 §2.6）：被保護的人被打時，照他的抗性、聖光算完的傷害，其中幾成改扣保護他的人。

轉過來的不再算保護的人的抗性：先扣他的護盾，再扣 HP（可以扣死）。只在同一個房間有效：任一邊離開房間、登出、死掉就停。
誰在保護誰只記在記憶體裡（guards），不存檔；時間用世界 tick 數（skills.tick 呼叫 tick()）。
扣 HP 的地方（combat.land、affects.pulse）先 split() 算好被保護的人自己受多少，自己的訊息送完再 cover() 扣保護的人。
坑：combat → death → … → affects → protect → combat 繞一圈，都用 from . import 模組。
"""
from dataclasses import dataclass

from . import affects, combat, combos, stats
from .act import TO_CHAR, TO_VICT, compose
from .characters import characters

COVERED = "{G你替$N擋下了 $t 點傷害。{x"      # 保護的人看到的
COVERED_YOU = "$n替你擋下了 $t 點傷害。"      # 被保護的人看到的


@dataclass
class Guard:
    guardian: object                        # 保護他的人
    source: str                             # 哪個技能（同一個人、同一個技能只有一份：再放是覆蓋）
    share: float                            # 幾成改扣保護的人
    ticks: int                              # 還剩幾個 tick


guards = {}                                 # 被保護的人 → [Guard]


def add(guardian, target, source, share, ticks):
    """guardian 用 source 保護 target：share 成、ticks 個 tick。同一個人用同一個技能再放是覆蓋（時間回到滿的）。"""
    kept = [g for g in guards.get(target, []) if not (g.guardian is guardian and g.source == source)]
    guards[target] = kept + [Guard(guardian, source, share, ticks)]


def active(target):
    """target 現在有效的保護：時間還沒到、保護的人還在遊戲裡、活著、跟他在同一間房；其他的拿掉。"""
    kept = [g for g in guards.get(target, []) if g.ticks > 0 and g.guardian in characters and g.guardian is not target
            and g.guardian.room is target.room and g.guardian.hp > 0]
    if kept:
        guards[target] = kept
    else:
        guards.pop(target, None)
    return kept


def split(target, dmg):
    """target 要受 dmg 點（抗性、聖光都算完了）：回傳 (他自己受的, [(保護的人, 改扣他的)])。好幾個人保護就各自照 share 分，加起來不超過全部。"""
    if dmg <= 0 or target not in guards:
        return dmg, []
    left, parts = dmg, []
    for g in active(target):
        part = min(left, dmg * g.share)
        if part > 0:
            left -= part
            parts.append((g.guardian, part))
    return left, parts


def cover(out, attacker, target, parts):
    """split() 分給保護的人的傷害：先扣他的護盾，再扣 HP，訊息放進 out（有 tell() 的：這一場、或效果那個 tick 的 Messages）。
    扣到 0 就死，算被打 target 的人（attacker）打死；attacker 是 None（沒在打架時的持續扣血）就誰都不給經驗。
    """
    for guardian, part in parts:
        if guardian not in characters:      # 前一個保護的人死掉時發生的事（腳本）
            continue
        part *= combos.guard_ratio(guardian)    # 連動「鐵壁護人」：改扣你的那一份減半
        taken, broken = affects.absorb(guardian, part)
        guardian.hp -= part - taken
        out.tell(compose(COVERED, guardian, target, t=str(stats.shown(part)), to=TO_CHAR))
        out.tell(compose(COVERED_YOU, guardian, target, t=str(stats.shown(part)), to=TO_VICT))
        out.tell(affects.broken_messages(guardian, broken))
        if guardian.hp <= 0:
            combat.slain(out, attacker, guardian)


def tick():
    """世界每個 tick：每個保護少 1 tick，時間到的拿掉（不說話，跟技能冷卻一樣）。"""
    for target in list(guards):
        for g in guards[target]:
            g.ticks -= 1
        active(target)
