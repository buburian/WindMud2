"""角色的屬性：種族、公會、裸裝的次要屬性、MP／MV 上限（玩家角色手冊；設計文件 §2.6、§3.6、§8）。

這裡只放設計文件的定義和算式。數字要跟 mud_design 的 sim/balance.py 一樣：tests/test_stats.py 會直接讀它比對，
那邊改了數字，測試會提醒。次要屬性一律從頭算（設計文件 §8.2），不要加加減減。
"""
import enum
import math
import random

from .area import MobTier
from .characters import Position
from .equipment import G, PRIMARY_KEYS, SECONDARY_PRICE, STAT_NAMES as EQUIPMENT_STAT_NAMES, standard_primary


class Race(enum.StrEnum):
    """玩家的種族（玩家角色手冊「種族」），存檔寫代號。跟區域檔生物的 race 不是同一套。"""
    HUMAN = "human"                         # 人類
    ELF = "elf"                             # 精靈
    DWARF = "dwarf"                         # 矮人
    ORC = "orc"                             # 獸人
    HALFLING = "halfling"                   # 半身人
    SPIRIT = "spirit"                       # 靈族


RACE_NAMES = {Race.HUMAN: "人類", Race.ELF: "精靈", Race.DWARF: "矮人", Race.ORC: "獸人",
              Race.HALFLING: "半身人", Race.SPIRIT: "靈族"}
RACE_TRAITS = {Race.HUMAN: "平均，沒有弱點", Race.ELF: "聰明、靈巧、體弱", Race.DWARF: "耐打、動作慢",
               Race.ORC: "力氣大、不愛動腦", Race.HALFLING: "身手敏捷、個子小", Race.SPIRIT: "精神力強、MP 多、體弱"}
# 每個種族的主屬性：人類全 12 為基準加減，加減合計 0（五項都是 60），每項 8～16
RACE_PRIMARIES = {
    Race.HUMAN: {"str": 12, "int": 12, "wis": 12, "con": 12, "dex": 12},
    Race.ELF: {"str": 10, "int": 14, "wis": 12, "con": 11, "dex": 13},
    Race.DWARF: {"str": 13, "int": 11, "wis": 12, "con": 14, "dex": 10},
    Race.ORC: {"str": 14, "int": 11, "wis": 11, "con": 12, "dex": 12},
    Race.HALFLING: {"str": 11, "int": 12, "wis": 12, "con": 11, "dex": 14},
    Race.SPIRIT: {"str": 11, "int": 12, "wis": 14, "con": 11, "dex": 12},
}


class Guild(enum.StrEnum):
    """公會（玩家角色手冊「公會」），遊戲沒有職業。代號跟設計文件、balance.py 一樣。"""
    SWORD = "phys"                          # 劍之公會：物理傷害、物理技能耗 MV、攻擊被物理抗性擋
    STAFF = "spell"                         # 杖之公會：法術傷害、法術耗 MP、攻擊被法術抗性擋


GUILD_NAMES = {Guild.SWORD: "劍之公會", Guild.STAFF: "杖之公會"}
GUILD_DAMAGE = {Guild.SWORD: "dmg_phys", Guild.STAFF: "dmg_spell"}     # 公會用的傷害；另一種的裸裝是 0
GUILD_RESOURCE = {Guild.SWORD: "mv", Guild.STAFF: "mp"}               # 公會自己用的資源

# 次要屬性（玩家角色手冊「名詞」）。AC 來自裝備；MP、MV 另外用 resources() 算
SECONDARY_KEYS = ("hp", "dmg_phys", "dmg_spell", "hit", "dodge", "crit", "critdmg", "speed",
                  "res_phys", "res_spell", "res_dragon")
STAT_NAMES = {**EQUIPMENT_STAT_NAMES, "mp": "MP", "mv": "MV", "ac": "AC"}

NAKED_SHARE = 0.75                          # 裸裝是參考值的 75%，其他靠裝備（龍焰抗性裸裝是 0，區域檔另外給）
REF = {                                     # 參考值 ÷ G(L)（設計文件 §2.2，balance.py 的 Model().b）
    "hp": 10.0, "dmg_phys": 0.5, "dmg_spell": 0.5, "dmg_dragon": 0.5, "hit": 1.9999999968133229, "dodge": 1.9999999808124505,
    "crit": 1.1034482729119763, "critdmg": 0.41379310227256505, "speed": 3.999999993608712,
    "res_phys": 1.4956289410451793, "res_spell": 1.4956289410451793, "res_dragon": 1.4956289410451793,
}
# 主屬性 → 次要屬性的權重（設計文件 §3.2，balance.py 的 SLICE_SEED；mana 在這裡叫 mp）。
# 每個次要屬性照權重分給各主屬性，分完是 100%（SLICE）。兩個公會都相同
SLICE_SEED = {
    "str": {"dmg_phys": 1.0, "critdmg": 1.0, "hit": 0.5, "mv": 0.7},
    "int": {"dmg_spell": 1.0, "crit": 0.4, "hit": 0.5, "mp": 0.3, "res_dragon": 0.6},
    "dex": {"dodge": 1.0, "speed": 1.0, "crit": 1.0, "hit": 0.5},
    "con": {"hp": 1.0, "res_phys": 1.0, "mv": 0.3},
    "wis": {"res_spell": 1.0, "critdmg": 0.3, "mp": 0.7, "hp": 0.15, "res_dragon": 0.8},
}


def _slice(stat):
    total = sum(SLICE_SEED[p].get(stat, 0.0) for p in PRIMARY_KEYS)
    return {p: SLICE_SEED[p].get(stat, 0.0) / total for p in PRIMARY_KEYS}


SLICE = {stat: _slice(stat) for stat in (*SECONDARY_KEYS, "mp", "mv")}

# MP、MV 上限（設計文件 §2.6，2026-11-04 使用者定的）
MAX_LEVEL = 100                             # 滿等
PRIMARY_CAP = 55                            # 角色自己的主屬性每項最高 55（玩家角色手冊「升級」）；裝備、buff 加的不受限
RESOURCE_MAIN_HP_RATIO = 0.5                # 自己公會用的資源 ＝ 裸裝 HP × 這個
RESOURCE_OFF_LV1_RATIO = 0.5                # 另一種資源 1 級 ＝ 自己公會那種 × 這個，之後每級乘固定倍率
RESOURCE_OFF_MAX = 500.0                    # 另一種資源在滿等時的量
RESOURCE_ROLL = 0.05                        # 創角時骰一次 1 ± 這個，MP、MV 一直乘它（兩種用同一個，使用者確認）


def _ratio(primaries, guild, level, stat):
    """Σ（角色自己的主屬性 ÷ 公會標準）× 這個主屬性負責 stat 的比例。公會標準配點時是 1。"""
    return sum(primaries[p] / standard_primary(guild, p, level) * SLICE[stat][p] for p in PRIMARY_KEYS)


def naked(level, primaries, guild):
    """裸裝的次要屬性（設計文件 §8.1 末段）：0.75 × 參考值 × G(L) × Σ（主屬性 ÷ 公會標準）× 切片。

    公會用不到的傷害、龍焰抗性是 0。primaries 是角色自己的主屬性（裝備加的另外算）。
    """
    unused = GUILD_DAMAGE[Guild.STAFF if guild == Guild.SWORD else Guild.SWORD]
    return {s: 0.0 if s in (unused, "res_dragon") else NAKED_SHARE * REF[s] * G(level) * _ratio(primaries, guild, level, s)
            for s in SECONDARY_KEYS}


def resource_standard(level, guild, stat):
    """公會標準配點時的 MP（stat 是 "mp"）或 MV（"mv"）上限。"""
    def main(lv):
        return RESOURCE_MAIN_HP_RATIO * NAKED_SHARE * REF["hp"] * G(lv)
    if stat == GUILD_RESOURCE[guild]:
        return main(level)
    first = main(1) * RESOURCE_OFF_LV1_RATIO
    growth = (RESOURCE_OFF_MAX / first) ** (1 / (MAX_LEVEL - 1))      # 每級大約 1.034，滿等剛好 RESOURCE_OFF_MAX
    return first * growth ** (level - 1)


def resources(level, primaries, guild, roll):
    """MP、MV 上限 ＝ 標準 × Σ（角色自己的主屬性 ÷ 公會標準）× 負責比例 × 創角時骰的倍率。"""
    return {s: resource_standard(level, guild, s) * _ratio(primaries, guild, level, s) * roll for s in ("mp", "mv")}


def shown(x):
    """顯示用的整數：四捨五入（設計文件 §8.2：內部存小數，只有顯示時取整）。Python 的 round() 是取偶數，不能用。"""
    return math.floor(x + 0.5)


def roll_resources(rng=random):
    """創角時骰一次 MP、MV 的倍率（0.95～1.05）。"""
    return rng.uniform(1 - RESOURCE_ROLL, 1 + RESOURCE_ROLL)


def set_level(player, level, rng=random):
    """把玩家改成 level 級（imm 的 advance 用）。回傳扣回的主屬性（照順序，可能重複）。

    每一級 1 點主屬性點數，永遠成立：還沒分配的 points ＋ Σ trained ＝ 等級 − 1。
    升級：多的級數加到 points。降級：要扣的先從 points 扣；不夠的一點一點隨機挑加過點的屬性扣 1（使用者選的）。
    改完從頭算屬性，HP、MP、MV 補滿（照 C 版 advance）。
    """
    taken = []
    owe = player.level - level
    if owe <= 0:
        player.points -= owe
    else:
        use = min(owe, player.points)
        player.points -= use
        for _ in range(owe - use):
            key = rng.choice([k for k in PRIMARY_KEYS if player.trained[k] > 0])
            player.trained[key] -= 1
            player.primaries[key] -= 1
            taken.append(key)
    player.level = level
    recompute(player)
    player.hp, player.mp, player.mv = player.panel["hp"], player.panel["mp"], player.panel["mv"]
    return taken


def train(player, key, n):
    """把 n 點還沒分配的點數加到主屬性 key（train 指令先檢查過點數和上限）。現在的 HP、MP、MV 不補。"""
    player.points -= n
    player.trained[key] += n
    player.primaries[key] += n
    recompute(player)


# 每次回復上限的幾成（玩家角色手冊「回復」）：跟屬性無關，屬性已經透過上限影響回復量。
# 戰鬥中不回（戰鬥公式的 1:1 沒有算回血）；昏迷、快死了這些手冊沒寫，也不回
REGEN_RATE = {Position.STANDING: 0.10, Position.RESTING: 0.20, Position.SLEEPING: 0.30}


def regen(player):
    """回復一次（世界 tick 每 REGEN_TICKS 呼叫）：HP、MP、MV 各回上限的固定比例，不超過上限。"""
    rate = REGEN_RATE.get(player.position, 0)
    for key in ("hp", "mp", "mv"):
        setattr(player, key, min(player.panel[key], getattr(player, key) + player.panel[key] * rate))


def recompute(player):
    """從頭算玩家的全部次要屬性（player.panel）：裸裝 ＋ MP、MV 上限；AC 來自裝備，裝備還沒做是 0。

    設計文件 §8.2：升級、改主屬性、穿脫裝備時都從頭算一次，戰鬥只讀這份快取。
    """
    panel = naked(player.level, player.primaries, player.guild)
    panel.update(resources(player.level, player.primaries, player.guild, player.resource_roll))
    panel["ac"] = 0.0
    player.panel = panel


# ---- 怪物（區域檔的生物）：設計文件 §4.1～§4.3、§4.6，balance.py 的 Model.area_mob() ----
# 順序：等級 ＋ 種類（裝備完整度、進度加成）→ 攻擊類型 → 原型 → 攻防傾向。MP、MV 是 0（怪物放技能不耗資源，技能系統再定）

MOB_TIER_FILL = {                           # 種類 → 裝備完整度（怪物裝備那 25% ＝ 滿裝 × 這個；§4.3）
    MobTier.TRASH: 0.0, MobTier.NORMAL: 0.5, MobTier.ELITE: 1.0, MobTier.BOSS: 1.1,
}
MOB_BONUS_MAX = 0.20                        # 進度加成（§4.6）：滿等的怪物裝備那 25% 再多 20%
MOB_BONUS_CURVE = 3.0                       # 曲線陡度：前期慢、後期快
GEAR_SHARE = 1 - NAKED_SHARE                # 裝備負責的比例（25%）
BASE_PER_G = {"wpn": 0.5, "ac": 5.014570169544317}   # 武器基本傷害、全身 AC ÷ G(L)（不算點數，也乘裝備完整度）
ATTACK_MAIN_SHARE = 0.70                    # 主／次攻擊類型：主 70%、次 30%（§4.1）
ATTACK_TYPES = ("phys", "spell", "dragon")
DEFENSE_RATIO = (2.0, 0.5)                  # 攻防傾向：擅長的抗性 : 不擅長的，換算回原本合計（§4.2）
ARCHETYPE_KEYS = ("hp", "dmg", "hit", "dodge", "crit", "critdmg", "speed", "res_phys", "res_spell")
ARCHETYPE_TILT = {                          # 原型的傾向係數（§4.2）："dmg" 是這隻怪有的每一種傷害，正規化時只算一次
    "tank": {"hp": 2.0, "dmg": 0.5, "hit": 0.5, "dodge": 2.0, "crit": 0.5, "critdmg": 0.5, "speed": 0.5, "res_phys": 2.0, "res_spell": 2.0},
    "berserker": {"hp": 0.5, "dmg": 2.0, "hit": 1.0, "dodge": 0.5, "crit": 2.0, "critdmg": 2.0, "speed": 2.0, "res_phys": 0.5, "res_spell": 0.5},
    "agile": {"hp": 0.5, "dmg": 1.0, "hit": 2.0, "dodge": 2.0, "crit": 1.0, "critdmg": 1.0, "speed": 2.0, "res_phys": 0.5, "res_spell": 0.5},
    "extreme_tank": {"hp": 1.0, "dmg": 0.0, "hit": 0.0, "dodge": 0.0, "crit": 0.0, "critdmg": 0.0, "speed": 0.0, "res_phys": 0.0, "res_spell": 0.0},
}
PRICE = {**SECONDARY_PRICE, "dmg_dragon": SECONDARY_PRICE["dmg_phys"]}   # 原型換算點數用（龍焰傷害跟物理傷害一樣）


def mob_bonus(level):
    """進度加成 factor(L)：0 → MOB_BONUS_MAX，正規化指數曲線，t ＝ (L − 1) ÷ (滿等 − 1)。"""
    t = min(max((level - 1) / (MAX_LEVEL - 1), 0.0), 1.0)
    return MOB_BONUS_MAX * (math.exp(MOB_BONUS_CURVE * t) - 1) / (math.exp(MOB_BONUS_CURVE) - 1)


def mob_multiplier(level, gear_part, fill):
    """怪物屬性 ÷ 參考值：固定基礎（1 − gear_part）＋ 裝備部分 × 裝備完整度 × (1 ＋ 進度加成)。"""
    return 1 - gear_part + gear_part * fill * (1 + mob_bonus(level))


def parse_attack(attack):
    """區域檔的 attack → 攻擊類型比例（主在前）：None 是純物理，"spell" 只用一種，"dragon/phys" 主 70%、次 30%。"""
    if attack is None:
        return {"phys": 1.0}
    main, _, sub = attack.partition("/")
    return {main: 1.0} if not sub else {main: ATTACK_MAIN_SHARE, sub: 1 - ATTACK_MAIN_SHARE}


def mob_stats(level, tier, attack, defense, archetype):
    """區域檔的生物的全部屬性和攻擊類型比例：(panel, mix)。區域檔檢查過，代號都是對的。

    panel 的鍵：SECONDARY_KEYS、dmg_dragon、mp、mv、wpn（武器基本傷害）、ac。
    """
    g, fill, mix = G(level), MOB_TIER_FILL[MobTier(tier)], parse_attack(attack)
    general = mob_multiplier(level, GEAR_SHARE, fill)
    panel = {}
    for key in SECONDARY_KEYS:
        if key.startswith("dmg_"):
            continue
        gear_part = 1.0 if key == "res_dragon" else GEAR_SHARE    # 龍焰抗性沒有固定基礎，全部算裝備部分
        panel[key] = REF[key] * g * mob_multiplier(level, gear_part, fill)
    for t in ATTACK_TYPES:                  # 有的攻擊類型，傷害都是參考值（每一擊只用一種，戰力不變）
        panel[f"dmg_{t}"] = REF[f"dmg_{t}"] * g * general if t in mix else 0.0
    panel["mp"] = panel["mv"] = 0.0
    panel["wpn"], panel["ac"] = BASE_PER_G["wpn"] * g * fill, BASE_PER_G["ac"] * g * fill
    if archetype is not None:
        _tilt(panel, level, g, mix, ARCHETYPE_TILT[archetype])
    if defense is not None:
        good, bad = ("res_phys", "res_spell") if defense == "phys" else ("res_spell", "res_phys")
        total, (hi, lo) = panel[good] + panel[bad], DEFENSE_RATIO
        panel[good], panel[bad] = total * hi / (hi + lo), total * lo / (hi + lo)
    return panel, mix


def _tilt(panel, level, g, mix, tilt):
    """原型：只動可調的部分（含進度加成），固定基礎不動，總點數不變。龍抗、MP、MV、武器基本傷害、AC 不動。"""
    dmg_keys = [f"dmg_{t}" for t in mix]
    stat_key = {k: dmg_keys[0] if k == "dmg" else k for k in ARCHETYPE_KEYS}
    fixed = {k: REF[sk] * g * mob_multiplier(level, GEAR_SHARE, 0.0) for k, sk in stat_key.items()}
    points = {k: (panel[sk] - fixed[k]) * PRICE[sk] for k, sk in stat_key.items()}
    total = sum(points.values())
    if total <= 0:                          # 垃圾怪沒有可調的點數，原型沒有作用
        return
    tilted = {k: v * tilt[k] for k, v in points.items()}
    scale = total / sum(tilted.values())
    for k, sk in stat_key.items():
        value = fixed[k] + tilted[k] * scale / PRICE[sk]
        for key in dmg_keys if k == "dmg" else [sk]:
            panel[key] = value

