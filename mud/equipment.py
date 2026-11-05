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
TWO_HANDED = "two_handed"                   # 雙手武器：同時佔主手和副手，上限是兩格加起來
ARMOR_SLOTS = ("offhand", "body", "head", "legs", "arms", "hands", "feet", "about", "waist", "neck", "wrist")   # 有 AC 的部位

# 裝備基本值（不算點數，設計文件 §3.3）：武器傷害照等級，護具 AC ＝ 那件的點數上限 × ARMOR_AC
WPN_PER_G = 0.5                             # 武器基本傷害 ÷ G(L)
ARMOR_AC = 1.0
TWO_HANDED_WPN_MULT = 1.1215868110020213    # 雙手武器少了副手的 AC，基本傷害乘這個補回（balance.py 解出來的）
WEAPON_SPREAD = (0.10, 0.20)                # 武器傷害範圍：下限、上限各離平均 10%～20%（做出來時骰）

# 隨機裝備（§3.3）：可以抽到的屬性和它的詞綴，順序要跟 balance.py 一樣（rng.choice 照順序挑，同一個種子才會抽到一樣的）
AFFIX_WORD = {
    "str": "蠻力", "int": "睿智", "wis": "賢者", "con": "堅毅", "dex": "靈巧",
    "hp": "活力", "dmg_phys": "鋒銳", "dmg_spell": "奧術", "hit": "精準", "dodge": "幻影",
    "crit": "致命", "critdmg": "殘暴", "speed": "疾風", "res_phys": "鐵壁", "res_spell": "抗魔",
}
AFFIX_SPLIT = (0.60, 0.20, 0.20)            # 主詞綴、次詞綴、剩下的
AFFIX_THIRD_CHANCE = 0.5                    # 剩下的有一半機率給第三條，不然給主或次詞綴

# 顏色（稀有度）的點數加成，代號同 area.ItemColor
COLOR_BONUS = {"gray": 0.0, "white": 1.0, "blue": 1.2, "purple": 1.3, "orange": 1.4}
COLOR_NAMES = {"gray": "灰色", "white": "白色", "blue": "藍色", "purple": "紫色", "orange": "橘色"}

# 主屬性 +1 要幾點（設計文件 §3.2、§8.1）：每個公會（phys 劍之公會、spell 杖之公會）算「K × G(L) ÷ 這個公會 L 級的標準值」，取大的。
# 標準值 ＝ 創角的標準值 ＋ max(0, L − 1) × 每級給的點數 × 這個主屬性分到的比例。
# 標準值跟著等級長，每 1 點換到的次要屬性就變少，所以不是固定係數 × G(L)：1 級 STR +1 是 3.74 點、100 級是 138.3 點。
POINTS_PER_LEVEL = 1.0                      # 每升一級給的主屬性點數（五項合計，玩家角色手冊）
PRIMARY_PRICE = {                           # 公會 → 主屬性 → (K, 創角的標準值, 升級點數分到的比例)
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


def best_slot(slots, two_handed=False):
    """物品算點數用哪個部位：雙手武器（有主手）是 TWO_HANDED；好幾個部位用上限最大的；沒有部位是 None。

    檢查固定裝備的上限（item_cap）和隨機抽屬性（roll_item）都用它，所以兩邊一定是同一個部位。
    """
    if two_handed and "wield" in slots:
        return TWO_HANDED
    if not slots:
        return None
    return max(slots, key=lambda s: slot_cap(1, s))     # 各部位的比例跟等級無關，用 1 級比


def cap(level, slot):
    """slot 部位一件的點數上限（顏色加成前），slot 可以是 TWO_HANDED（主手＋副手）。"""
    if slot == TWO_HANDED:
        return slot_cap(level, "wield") + slot_cap(level, "offhand")
    return slot_cap(level, slot)


def item_cap(level, slots, two_handed=False):
    """物品的點數上限（顏色加成前）和部位的說明。

    slots 是物品的穿戴部位：雙手武器（有主手）是主手＋副手；好幾個部位用上限最大的；沒有部位是 0。
    """
    slot = best_slot(slots, two_handed)
    if slot is None:
        return 0.0, "（沒有穿戴部位）"
    return cap(level, slot), "主手＋副手（雙手）" if slot == TWO_HANDED else SLOT_NAMES[slot]


def price(stat, level):
    """stat（屬性代號，例如 "str"、"hp"）每 +1 要幾點。"""
    if stat in PRIMARY_KEYS:
        return max(PRIMARY_PRICE[guild][stat][0] * G(level) / standard_primary(guild, stat, level) for guild in PRIMARY_PRICE)
    return SECONDARY_PRICE[stat]


def standard_primary(guild, stat, level):
    """公會 guild（"phys"、"spell"）在 level 級的標準主屬性 stat：創角的標準值 ＋ 升級加的（照這個主屬性分到的比例）。"""
    _, std1, share = PRIMARY_PRICE[guild][stat]
    # 低於 1 級不往下減：玩家從 1 級開始，不然很低等的怪物（大約 −42 級以下）會除以 0 或負數
    return std1 + max(0, level - 1) * POINTS_PER_LEVEL * share


def base_values(slot, level, rng, offhand_weapon=False):
    """裝備基本值（不算點數）：武器是傷害範圍 dmg_min～dmg_max（做出來時骰），護具是 AC，其他沒有。

    亂數的順序跟 balance.py 的 roll_item 一樣（先下限、再上限）。
    """
    if slot in ("wield", TWO_HANDED) or offhand_weapon:
        w = WPN_PER_G * G(level) * (TWO_HANDED_WPN_MULT if slot == TWO_HANDED else 1.0)
        lo, hi = WEAPON_SPREAD
        low = w * (1 - rng.uniform(lo, hi))
        return {"dmg_min": low, "dmg_max": w * (1 + rng.uniform(lo, hi))}
    if slot in ARMOR_SLOTS:
        return {"ac": cap(level, slot) * ARMOR_AC}
    return {}


def roll_item(slot, level, color, rng, offhand_weapon=False):
    """隨機產生一件裝備的基本值和屬性（設計文件 §3.3），照 balance.py 的 Model.roll_item 寫，同一個種子結果一樣（有測試）。

    可配點數 ＝ 上限 × 顏色加成（color 是 None 當灰色，×0）。主詞綴拿 60%、次詞綴 20%；剩下 20% 一半機率給第三條，
    不然給主或次詞綴。每條都從「分到的點數買得起 +1」的屬性裡抽、不重複，取整數；零頭補到 1 點 ＝ 1 單位的屬性。
    回傳 {"name": "[次]之[主]"（沒有屬性是空字串）, "base": 基本值, "affixes": {屬性代號: 加多少}}。
    """
    budget = cap(level, slot) * COLOR_BONUS[color or "gray"]
    base = base_values(slot, level, rng, offhand_weapon)
    prices = {k: price(k, level) for k in AFFIX_WORD}

    def pick(points, exclude):
        options = [k for k in AFFIX_WORD if prices[k] <= points and k not in exclude]
        return rng.choice(options) if options else None

    p_main, p_sub, p_rest = (budget * s for s in AFFIX_SPLIT)
    main = pick(p_main, ())
    sub = pick(p_sub, (main,)) if main else None
    third = None
    share = {}
    if main:
        share = {main: p_main, sub: p_sub} if sub else {main: p_main + p_sub}
        if rng.random() < AFFIX_THIRD_CHANCE:
            third = pick(p_rest, (main, sub))
        if third:
            share[third] = p_rest
        else:
            share[rng.choice([k for k in (main, sub) if k])] += p_rest
    affixes = {k: int(v // prices[k]) for k, v in share.items()}
    if main:                                # 零頭補到 1 點 ＝ 1 單位的屬性：優先主、次、第三條，都不是才另外抽一條
        used = sum(n * prices[k] for k, n in affixes.items())
        one = [k for k in AFFIX_WORD if k not in PRIMARY_KEYS and abs(prices[k] - 1.0) < 1e-6]
        target = next((k for k in (main, sub, third) if k in one), None) or rng.choice([k for k in one if k not in affixes])
        left = int((budget - used) // prices[target])
        if left > 0:
            affixes[target] = affixes.get(target, 0) + left
    name = f"{AFFIX_WORD[sub]}之{AFFIX_WORD[main]}" if sub else (AFFIX_WORD[main] if main else "")
    return {"name": name, "base": base, "affixes": affixes}
