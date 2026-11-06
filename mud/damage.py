"""傷害公式（mud_design 設計文件 §2.3～§2.5、§8.1）：照 sim/balance.py 寫，只放算式和常數。

一下攻擊：擲命中 → (傷害點數 ＋ 武器基本傷害) × (1 − 減傷) × 等級差修正 → ±20% 浮動 → 擲爆擊。
玩家拿武器時，那隻手的武器在 dmg_min～dmg_max 取一個值代替 ±20%（mud_design 確認的，§2.5「帶入公式前就決定好」）。
參考值都用持有者自己的等級（角色面板上的百分比不隨對手變）。數字要跟 balance.py 一樣：tests/test_damage.py 直接比對。
訊息、扣 HP、死掉在 combat.py；這裡不改任何角色。
"""
from .equipment import G
from .stats import REF

HIT_K = 4.0                                 # 命中 ＝ 4 × 命中 ÷ (4 × 命中 ＋ 閃躲)：同級參考值互打 80%
CRIT_BASE = 0.20                            # 爆擊點數 ＝ 參考值時的爆擊率
CRIT_MULT = (1.5, 3.0, 0.20)                # 爆擊倍率：最低、最高（漸近）、參考值時的進度（1.5 ＋ 1.5 × 0.2 ＝ 1.8 倍）
SPEED = (1.0, 6.0, 0.20)                    # 每回合攻擊次數：最少、最多（漸近）、參考值時的進度（2 次）
RESIST_BASE = 0.30                          # 抗性 ＝ 參考值時的減傷
LEVEL_MOD = 1.077845797828398               # 等級差傷害修正：攻方每高 1 級 × 這個（balance.py 解出來的）
DMG_VAR = 0.20                              # 每一下 ±20% 浮動（照 balance.py 的模擬）：空手的玩家和生物；拿武器改成武器的最小～最大
DUAL_WIELD_MAIN = 0.70                      # 雙持：主手出手 攻擊次數 × 這個（使用者定的，balance.py 的 DUAL_WIELD_MAIN）
DUAL_OFFHAND = 0.3607934055010107           # 雙持：副手出手 攻擊次數 × 這個（balance.py 的 Model.dual_offhand_share 解出來的）
TYPES = ("phys", "spell", "dragon")         # 傷害類型：物理、法術、龍焰（龍焰只有怪物有）


def eff(x, ref, base):
    """飽和轉換：x ＝ ref 時是 base，x 越大越接近 1，x ≤ 0 是 0（設計文件 §2.3）。"""
    if x <= 0:
        return 0.0
    return x / (x + ref * (1.0 - base) / base)


def _ref(ch, key):
    return REF[key] * G(ch.level)


def crit_chance(ch):
    return eff(ch.panel.get("crit", 0.0), _ref(ch, "crit"), CRIT_BASE)


def crit_mult(ch):
    lo, hi, base = CRIT_MULT
    return lo + (hi - lo) * eff(ch.panel.get("critdmg", 0.0), _ref(ch, "critdmg"), base)


def attacks_per_round(ch):
    lo, hi, base = SPEED
    return lo + (hi - lo) * eff(ch.panel.get("speed", 0.0), _ref(ch, "speed"), base)


def hit_chance(a, d):
    hit = a.panel.get("hit", 0.0)
    if hit <= 0:
        return 0.0
    return HIT_K * hit / (HIT_K * hit + d.panel.get("dodge", 0.0))


def reduction(d, kind):
    """守方 d 對 kind 類型的減傷：物理、法術是抗性 ＋ AC，龍焰只看龍焰抗性（AC 不擋龍焰）。"""
    res = d.panel.get(f"res_{kind}", 0.0) + (0.0 if kind == "dragon" else d.panel.get("ac", 0.0))
    return eff(res, _ref(d, f"res_{kind}"), RESIST_BASE)


def per_hit(a, d, kind, weapon_value=None):
    """a 打 d 一下 kind 類型、打中、還沒浮動和爆擊的傷害。

    武器基本傷害：weapon_value 是玩家這一下的武器值（拿武器時）；沒給就是 panel 的 wpn（生物的武器基本傷害，玩家沒有是 0）。
    """
    wpn = a.panel.get("wpn", 0.0) if weapon_value is None else weapon_value
    points = a.panel.get(f"dmg_{kind}", 0.0) + wpn
    return points * (1.0 - reduction(d, kind)) * LEVEL_MOD ** (a.level - d.level)


def attack_mix(ch):
    """每一下是哪種類型的機率：生物照區域檔的 attack（npc.mix），玩家是自己公會那一種（劍之公會物理、杖之公會法術）。"""
    mix = getattr(ch, "mix", None)
    return mix if mix else {str(ch.guild): 1.0}


def strike(a, d, rng, kind=None, hand=0):
    """a 打 d 一下：回傳 (傷害, 有沒有爆擊)，沒打中是 (0.0, False)。

    亂數的順序跟 balance.py 的 _strike_once 一樣（同一個種子結果一樣，有測試）：
    混合型先骰類型（沒打中也骰）→ 命中 → ±20% 浮動 → 爆擊。
    kind：技能用，這一下一定是這個類型（技能的公會），不骰類型；平砍不給。
    hand：哪隻手（0 主手、1 副手）。那隻手拿武器：武器值 ＝ 下限 ＋ (上限 − 下限) × 亂數，放在 ±20% 那一格（亂數次數不變）。
    """
    mix = {kind: 1.0} if kind else attack_mix(a)
    kinds = list(mix)
    kind = kinds[-1]
    if len(kinds) > 1:
        roll, total = rng.random(), 0.0
        for k in kinds:
            total += mix[k]
            if roll < total:
                kind = k
                break
    else:
        kind = kinds[0]
    if rng.random() >= hit_chance(a, d):
        return 0.0, False
    weapon = weapon_in(a, hand)
    if weapon is not None:
        low, high = weapon.base["dmg_min"], weapon.base["dmg_max"]
        dmg = per_hit(a, d, kind, low + (high - low) * rng.random())
    else:
        dmg = per_hit(a, d, kind) * (1.0 + DMG_VAR * (2.0 * rng.random() - 1.0))
    crit = rng.random() < crit_chance(a)
    if crit:
        dmg *= crit_mult(a)
    return dmg, crit


def weapon_in(ch, hand):
    """ch 第 hand 隻手（0 主手、1 副手）拿的武器（objects.Obj）；空手、生物（不穿裝備）是 None。"""
    obj = getattr(ch, "equipment", {}).get("wield" if hand == 0 else "offhand")
    return obj if obj is not None and obj.is_weapon() else None


def dual_wielding(ch):
    """雙持：主手、副手都拿武器（副手武器要主手有武器才穿得上，見 inventory.wear）。"""
    return weapon_in(ch, 0) is not None and weapon_in(ch, 1) is not None
