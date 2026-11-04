"""裝備的點數：照 mud_design 設計文件 §3.1～§3.3（sim/balance.py）算的上限和單價。

固定裝備（物品寫了 affects）放出來時，加成的點數不能超過「放出來的等級、該部位的上限 × 顏色加成」。
這裡只放設計文件的數字和計算，不 import area（area.check_files 會呼叫這裡，避免互相 import）。
數字要跟 balance.py 一樣：tests/test_equipment.py 會直接讀 balance.py 比對，那邊改了數字，測試會提醒。
"""

G1 = 10.0                                   # G(1)
GROWTH = 1.047961370421866                  # 每升一級 G 乘上這個數（大約 4.8%）
GEAR_COEF = 6.877124803570403               # 全身裝備點數上限 ＝ GEAR_COEF × G(L)

# 部位的權重（設計文件 §3.3），部位上限 ＝ 全身上限 × 權重 ÷ 權重合計。持握、光源不占點數。
SLOT_WEIGHT = {
    "wield": 0.20, "offhand": 0.08, "body": 0.12, "head": 0.08, "legs": 0.08, "arms": 0.05, "hands": 0.05,
    "feet": 0.05, "about": 0.05, "waist": 0.04, "neck": 0.04, "wrist": 0.06, "finger": 0.06, "hold": 0.0, "light": 0.0,
}
SLOT_NAMES = {
    "wield": "主手", "offhand": "副手", "body": "身體", "head": "頭", "legs": "腿", "arms": "手臂", "hands": "手",
    "feet": "腳", "about": "披風", "waist": "腰", "neck": "頸", "wrist": "手腕", "finger": "戒指", "hold": "持握", "light": "光源",
}
PAIRED = ("finger",)                        # 一個欄位兩件：一件的上限是一半（手腕當作一雙，不算）

# 顏色（稀有度）的點數加成，代號同 area.ItemColor
COLOR_BONUS = {"gray": 0.0, "white": 1.0, "blue": 1.2, "purple": 1.3, "orange": 1.4}
COLOR_NAMES = {"gray": "灰色", "white": "白色", "blue": "藍色", "purple": "紫色", "orange": "橘色"}

# 主屬性 +1 要幾點（設計文件 §3.2、§8.1）：每個職業算「K × G(L) ÷ 這個職業 L 級的標準值」，取大的。
# 標準值 ＝ 創角的標準值 ＋ max(0, L − 1) × 每級給的點數 × 這個主屬性分到的比例。
# 標準值跟著等級長，每 1 點換到的次要屬性就變少，所以不是固定係數 × G(L)：1 級 STR +1 是 3.74 點、100 級是 138.3 點。
POINTS_PER_LEVEL = 1.0                      # 每升一級給的主屬性點數（五項合計，玩家角色手冊）
PRIMARY_PRICE = {                           # 職業 → 主屬性 → (K, 創角的標準值, 升級點數分到的比例)
    "phys": {
        "str": (4.48872677959054, 12, 0.2175679957250024),
        "int": (0.7364532005364692, 8, 0.03569578962001311),
        "wis": (2.171600611643604, 8, 0.1052571955902352),
        "con": (7.6434608355823, 16, 0.37047753985861637),
        "dex": (5.591132983358295, 16, 0.2710014792061328),
    },
    "spell": {
        "str": (0.7387267889676209, 8, 0.03580599015178046),
        "int": (4.486453191159389, 12, 0.21745779519323505),
        "wis": (2.171600611643604, 8, 0.1052571955902352),
        "con": (7.6434608355823, 16, 0.37047753985861637),
        "dex": (5.591132983358295, 16, 0.2710014792061328),
    },
}
PRIMARY_KEYS = tuple(PRIMARY_PRICE["phys"])
# 次要屬性的單價和等級無關。龍焰抗性不算裝備點數（設計文件 §5.5），所以是 0（balance.py 裡是 1）
SECONDARY_PRICE = {
    "hp": 1.0, "dmg_phys": 10.0, "dmg_spell": 10.0, "hit": 1.0, "dodge": 1.0, "crit": 1.0, "critdmg": 1.0,
    "speed": 1.0, "res_phys": 1.0, "res_spell": 1.0, "res_dragon": 0.0, "none": 0.0,
}
STAT_NAMES = {
    "none": "無", "str": "力量", "dex": "敏捷", "int": "智慧", "wis": "知識", "con": "體質", "hp": "HP",
    "dmg_phys": "物理傷害", "dmg_spell": "法術傷害", "hit": "命中", "dodge": "閃躲", "crit": "爆擊率",
    "critdmg": "爆擊傷害", "speed": "攻速", "res_phys": "物理抗性", "res_spell": "法術抗性", "res_dragon": "龍焰抗性",
}


def G(level):
    """等級成長係數：G(L) ＝ 10 × 1.048^(L − 1)。"""
    return G1 * GROWTH ** (level - 1)


def slot_cap(level, slot):
    """一件裝備在 slot 部位的點數上限（顏色加成前）。戒指一件是欄位的一半。"""
    share = SLOT_WEIGHT[slot] / sum(SLOT_WEIGHT.values())
    return GEAR_COEF * G(level) * share / (2 if slot in PAIRED else 1)


def item_cap(level, slots, two_handed=False):
    """物品的點數上限（顏色加成前）和部位的說明。

    slots 是物品的穿戴部位：雙手武器（有主手）是主手＋副手；好幾個部位用上限最大的；沒有部位是 0。
    """
    if two_handed and "wield" in slots:
        return slot_cap(level, "wield") + slot_cap(level, "offhand"), "主手＋副手（雙手）"
    if not slots:
        return 0.0, "（沒有穿戴部位）"
    best = max(slots, key=lambda s: slot_cap(level, s))
    return slot_cap(level, best), SLOT_NAMES[best]


def price(stat, level):
    """stat（屬性代號，例如 "str"、"hp"）每 +1 要幾點。"""
    if stat in PRIMARY_KEYS:
        # 低於 1 級不往下減：玩家從 1 級開始，不然很低等的怪物（大約 −42 級以下）會除以 0 或負數
        return max(k * G(level) / (std1 + max(0, level - 1) * POINTS_PER_LEVEL * share)
                   for k, std1, share in (PRIMARY_PRICE[job][stat] for job in PRIMARY_PRICE))
    return SECONDARY_PRICE[stat]
