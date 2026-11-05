"""一下攻擊（fight.hit 呼叫）：照 damage.strike() 扣 HP、送 C 版的戰鬥訊息（fight.c 的 dam_message），打死了就處理死掉和經驗值。

訊息不直接送：放進那一場的 Fight.messages（act.compose），回合結束時每個人只收到一段（fight.Fight.flush）。
坑：fight → combat → death → fight 繞一圈，所以都用 from . import 模組。
"""
import random

from . import damage, death, stats
from .act import TO_CHAR, TO_NOTVICT, TO_ROOM, TO_VICT, compose
from .npcs import Npc
from .players import Player

rng = random                                # 亂數（測試換成固定種子的 random.Random）

BARE_HAND = "直拳"                          # 玩家還沒有武器：用 C 版人類的攻擊名稱
# 傷害佔對方 HP 上限的 %（整數）→ 程度和顏色，照 C 版 dam_message；最後一段是更大的。
# C 版 >500% 是紅底，我們的顏色代碼沒有底色，用暗紅
SEVERITY = [
    (5, "輕微的擦傷", "{c"), (10, "普通的擦傷", "{c"), (15, "淺淺的傷口", "{B"), (20, "普通的傷口", "{B"),
    (25, "很深的傷口", "{B"), (30, "*輕微的打擊*", "{b"), (35, "*輕微的傷害*", "{b"), (40, "*普通的打擊*", "{b"),
    (45, "*普通的傷害*", "{M"), (50, "*重大的打擊*", "{M"), (58, "*嚴重的傷害*", "{M"), (66, "**很嚴重的傷害**", "{m"),
    (74, "**很嚴重的創傷**", "{m"), (82, "***極為可怕的創傷***", "{m"), (90, "***近乎致命的創傷***", "{R"),
    (100, "***致-命-的-創-傷***", "{R"), (300, "****石-破-天-驚-的-創-傷****", "{r"),
    (500, "*****超-乎-想-像-的-創-傷*****", "{r"), (None, "*****鬼--哭--神--號--的--創--傷*****", "{r"),
]
MISS = "但是失手了"
CRIT = "爆擊！"
DEAD_ROOM = "$n已經斷氣，倒在地上死亡了!!"                                   # 同房間的人（照 C 版）
DEAD_SELF = "{R*********************你已經含恨死去了*********************{x"  # 死掉的玩家（照 C 版）
EXP_GAINED = "{Y你共獲得了【$t】點的經驗點數。{x"                             # 照 C 版
LEVEL_UP = "{Y【恭喜!!你提升了一級】{x現在是 $t 級，多了 $T 點主屬性點數，用 train 分配。"


def severity(dmg, top_hp):
    """傷害的程度和顏色代碼：看傷害佔 HP 上限幾 %（照 C 版 dam_message）。"""
    rate = max(int(dmg * 100 // top_hp), 0) if top_hp > 0 else 0
    for limit, words, code in SEVERITY:
        if limit is None or rate <= limit:
            return words, code


def hit(ch, victim, hand):
    """ch 打 victim 一下（hand 0 是主手；還沒有武器，兩手一樣）。有一邊沒有屬性（測試直接建的）就什麼都不做。"""
    battle = ch.fight                       # 先記住：打死生物時 die() 會把 ch.fight 清掉，後面的訊息還要放進這一場
    if battle is None or not ch.panel or not victim.panel:
        return
    dmg, crit = damage.strike(ch, victim, rng)
    land(battle, ch, victim, dmg, crit)


def land(battle, ch, victim, dmg, crit, attack=BARE_HAND):
    """打出去的一下（平砍和技能共用）：扣 HP、三句訊息放進 battle、打死了就處理死掉和經驗值。回傳 victim 死了沒。

    attack：玩家用什麼打的（訊息裡的「使用直拳」「使用重擊」）。
    """
    victim.hp -= dmg
    for to, fmt in messages(ch, victim, dmg, crit, attack):
        battle.tell(compose(fmt, ch, victim, to=to))
    if victim.hp > 0:
        return False
    battle.tell(compose(DEAD_ROOM, victim, to=TO_ROOM))
    if isinstance(victim, Npc):
        if isinstance(ch, Player):
            reward(battle, ch, victim)
        death.die(victim)
    else:
        battle.tell(compose(DEAD_SELF, victim, to=TO_CHAR))
        death.player_dies(victim)
    return True


def messages(ch, victim, dmg, crit, attack=BARE_HAND):
    """C 版的三句：[(送給誰, 句子)]。

    你使用直拳攻擊野狗，對它造成輕微的擦傷.(3)  ／  野狗攻擊你，對你造成普通的擦傷.(5)
    照 C 版：自己那句亮綠、被打那句亮青，程度照傷害佔對方 HP 上限的 % 上色，後面的「.(3)」回到一般顏色；
    同房間的人那句不上色。生物沒有武器名稱，寫「$n攻擊」；沒打中是「但是失手了」；傷害 ≤ 10 用「.」，其他「!」。
    """
    shown = stats.shown(dmg)
    words, code = severity(dmg, victim.panel["hp"]) if dmg > 0 else (MISS, "{c")
    tail = f"{'.' if shown <= 10 else '!'}({shown})"
    weapon = f"使用{attack}" if isinstance(ch, Player) else ""

    def result(whom):                       # 「爆擊！對它造成」＋程度；沒打中只有「但是失手了」
        return (CRIT if crit else "") + (f"對{whom}造成" if dmg > 0 else "")

    mine = "{G你" + weapon + "攻擊$N，" + result("$E") + code + words + "{x" + tail
    theirs = "{C$n" + weapon + "攻擊你，" + result("你") + code + words + "{x" + tail
    others = "$n" + weapon + "攻擊$N，" + result("$E") + words + tail
    return [(TO_CHAR, mine), (TO_VICT, theirs), (TO_NOTVICT, others)]


def reward(battle, player, npc):
    """打出最後一下的玩家拿經驗值（還沒有組隊，只給他）：照設計文件 §4.7，滿了升級。滿等不加、不說。"""
    if player.level >= stats.MAX_LEVEL:
        return
    amount = stats.kill_exp(player.level, npc.level, npc.tier)
    battle.tell(compose(EXP_GAINED, player, t=str(stats.shown(amount)), to=TO_CHAR))
    levels = stats.gain_exp(player, amount)
    if levels:
        battle.tell(compose(LEVEL_UP, player, t=str(player.level), T=str(levels), to=TO_CHAR))
