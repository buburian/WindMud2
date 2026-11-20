"""淬火石（設計文件 §3.11，使用者 2026-11-20 核准）：像金幣一樣記在玩家身上（Player.temper_stones，存檔），不是物品，
所以不能給、丟、賣，死掉也不會掉。用一顆把身上穿著的一件裝備變成玩家現在等級的橘色，屬性組合不變、點數用滿
（算法在 equipment.temper，照 balance.py 的 Model.temper_item）。指令在 commands/temper.py（use 淬火石／use temper）。

怎麼拿到（全世界一樣，區域檔不用寫）：打死 MIN_LEVEL 級以上的怪，照牠出現時骰到的種類 CHANCE 掉一顆給打死牠的玩家；
垃圾怪不掉；比玩家低 stats.EXP_ZERO_GAP 級以上（含）不掉（跟經驗一樣）。
"""
import random

from . import equipment
from .act import TO_CHAR, compose
from .area import Apply, ExtraFlag, MobTier

MIN_LEVEL = 15                              # 這個等級以上的怪才掉（balance.py 的 TEMPER_MIN_LEVEL）
CHANCE = {MobTier.NORMAL: 0.005, MobTier.ELITE: 0.02, MobTier.BOSS: 0.05}   # 種類 → 機率（TEMPER_CHANCE，垃圾怪不掉）
NAME = "淬火石"
WORDS = ("淬火石", "temper")                # use 後面打這兩個才是淬火石（要打完整：不然 use t 這類會搶走技能的縮寫）
GOT = "{Y你得到了一顆【淬火石】！{x"

rng = random                                # 掉落的亂數（測試換掉）：不用 combat.rng，原本戰鬥的亂數順序才不會變


def drop(out, player, npc):
    """player 打死了 npc（combat.slain）：照種類骰一次，掉了就加一顆、訊息放進 out（接在經驗後面）。"""
    from . import stats                     # 坑：stats → … → combat → temper，在函式裡才 import
    chance = CHANCE.get(getattr(npc, "tier", None), 0.0)
    if not chance or npc.level < MIN_LEVEL or player.level - npc.level >= stats.EXP_ZERO_GAP:
        return
    if rng.random() < chance:
        player.temper_stones += 1
        out.tell(compose(GOT, player, to=TO_CHAR))


def stats_of(obj):
    """物品的屬性寫成 equipment 用的 [(屬性代號, 數值)]（照存的順序）。"""
    return [(apply.name.lower(), n) for apply, n in obj.affects]


def result(obj, level):
    """obj 淬火到 level 級會變成什麼：(新的 affects, 新的 base)；不能淬火就 ValueError（equipment.temper）。"""
    affixes, base = equipment.temper(stats_of(obj), obj.base, obj.slot, obj.level, obj.color, level, obj.main_affix)
    return [(Apply[k.upper()], n) for k, n in affixes], base


def apply(obj, level):
    """真的淬火：等級、顏色、屬性、武器傷害或 AC 一起換，綁住（跟拾取後綁定一樣）。名稱、主詞綴不變。"""
    obj.affects, obj.base = result(obj, level)
    obj.level, obj.color = level, equipment.TEMPER_COLOR
    obj.bind = ExtraFlag.BIND_PICKUP
