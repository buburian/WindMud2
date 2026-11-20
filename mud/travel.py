"""旅具（設計文件 §3.12，使用者 2026-11-20 定的；規則在玩家角色手冊「旅具」、區域製作手冊「travel_effect」）。

光源、持握的物品寫了 travel_effect（area.TravelEffect），放出來的顏色不是灰色、null，就是旅具：穿在身上帶一種跟打架無關的續航效果。
- 量照物品等級 L 的標準數字（公會標準配點）：裸裝 HP(L)、自己公會的資源(L)（劍之公會 MV、杖之公會 MP，stats.resource_standard），
  乘比例、再乘顏色加成，四捨五入、最少 1。早點解毒不看等級、顏色。
- 打架中沒有作用（背得多除外）。光源、持握各穿一件，效果一樣就加起來。
- 不是 affect：不存在 ch.affects，死掉、清除效果都不影響；穿脫就有、就沒有。
用到的地方：world tick 每 TRAVEL_TICKS（tick()，回資源）、stats.regen（休息睡覺、吃喝多回）、stats.carry_limit（背得多）、
affects.step（早點解毒）、death.player_dies（死後不虛弱）、light.burn（旅具不燒完）、objects.base_price（價錢照戒指）、
examine 的詩（items.identify）、score 的「旅具效果」（system.travel_lines）。
"""
from . import equipment, stats
from .area import ItemColor, TravelEffect
from .players import online_players

SLOTS = (("light", "照明用具"), ("hold", "手中握著"))     # 旅具穿的位置和 equipment 的格子名稱（inventory.SLOTS 那兩格）
HP_STANDARD = stats.NAKED_SHARE * stats.REF["hp"]        # 裸裝 HP(L) ＝ 這個 × G(L)（公會標準配點：主屬性 ÷ 標準 ＝ 1）
PRICE_SLOT = "finger"                       # 基本價格當作同等級、同顏色的戒指算（設計文件 §3.7，mud_design 2026-11-20 定的）

# 每種效果：(比例, 量照什麼：hp 裸裝 HP、res 自己公會的資源、level 物品等級, score 的名字, score 的「什麼時候」, examine 的詩)
# 名字裡的 {res} 換成自己公會的資源（MP 或 MV，使用者 2026-11-20 選的：畫面不寫「資源」）。詩是使用者 2026-11-20 定的
EFFECTS = {
    TravelEffect.REGEN: (0.02, "res", "回 {res}", "沒在打架時每 10 秒", "步履雖勞心未倦，一身氣力自綿長。"),
    TravelEffect.REST_HP: (0.10, "hp", "多回 HP", "休息、睡覺時每 30 秒", "一枕安眠天未曉，醒來傷處已無痕。"),
    TravelEffect.REST_RES: (0.10, "res", "多回 {res}", "休息、睡覺時每 30 秒", "靜坐閉目聽夜雨，一宵養足滿懷神。"),
    TravelEffect.MEAL: (0.15, None, "吃喝更有效", "吃喝後回得快時每 30 秒", "粗茶淡飯皆滋味，一飽能抵十日勞。"),
    TravelEffect.CARRY: (2, "level", "背得多", "負重上限", "行囊再重何須懼，肩上猶能擔一山。"),
    TravelEffect.CURE: (None, None, "早點解毒", "沒在打架時，中毒、燃燒這類效果過得快一倍", "毒侵火灼皆過客，不待天明早離身。"),
    TravelEffect.REVIVE: (0.50, "hp", "死後不虛弱", "死掉回去時 HP 回到", "魂歸神殿身未冷，一口長氣再登程。"),
}


def effect_of(obj):
    """obj 的旅具效果（TravelEffect）：寫了 travel_effect、顏色不是灰色和 null 才有；沒有是 None（普通的光源、持握）。"""
    if getattr(obj, "travel_effect", None) is None or obj.color in (None, ItemColor.GRAY):
        return None
    return TravelEffect(obj.travel_effect)


def worn(ch):
    """ch 穿著的旅具：[(格子名稱, 物品, 效果)]，照光源、持握的順序。生物不穿裝備，是空的。"""
    found = []
    for pos, label in SLOTS:
        obj = ch.equipment.get(pos)
        effect = effect_of(obj) if obj is not None else None
        if effect is not None:
            found.append((label, obj, effect))
    return found


def resource_key(ch):
    """自己公會的資源：劍之公會 "mv"、杖之公會 "mp"。"""
    return stats.GUILD_RESOURCE[ch.guild]


def standard(ch, base, level):
    """level 級的標準數字：hp 是裸裝 HP，res 是 ch 公會的資源，level 是等級本身。"""
    if base == "hp":
        return HP_STANDARD * equipment.G(level)
    if base == "res":
        return stats.resource_standard(level, ch.guild, resource_key(ch))
    return level


def amount(ch, obj, effect, base=None):
    """一件旅具的量（整數）：標準數字 × 比例 × 顏色加成，四捨五入、最少 1。吃喝更有效要給 base（吃的 "hp"、喝的 "res"）。"""
    ratio, own_base = EFFECTS[effect][:2]
    raw = standard(ch, base or own_base, obj.level) * ratio * equipment.COLOR_BONUS[obj.color]
    return max(1, stats.shown(raw))


def total(ch, effect, base=None):
    """ch 穿著的旅具裡，effect 這種的量加起來（光源、持握各一件，一樣就加起來）；沒有是 0。"""
    return sum(amount(ch, obj, e, base) for _, obj, e in worn(ch) if e == effect)


def count(ch, effect):
    """ch 穿著幾件 effect 這種旅具（早點解毒用：不看等級、顏色，一件多減 1）。"""
    return sum(1 for _, _, e in worn(ch) if e == effect)


def fighting(ch):
    return ch.fighting is not None


def tick():
    """世界每 TRAVEL_TICKS（10 秒）：沒在打架的在線玩家，回資源（regen）的旅具回自己公會的資源，不超過上限。不說話。"""
    for p in online_players():
        if fighting(p) or not getattr(p, "panel", None):
            continue
        n = total(p, TravelEffect.REGEN)
        if n:
            key = resource_key(p)
            setattr(p, key, min(p.panel[key], getattr(p, key) + n))


def rest_bonus(ch):
    """stats.regen（每 30 秒，休息、睡覺時）跟著多回的：{"hp" 等: 加多少}。多回 HP、多回資源；
    吃喝更有效：吃的回得快（meal_bonus 有 hp）多回 HP、喝的回得快（有公會的資源）多回資源，兩個都有就都回。"""
    if fighting(ch) or not worn(ch):
        return {}
    res = resource_key(ch)
    extra = {"hp": total(ch, TravelEffect.REST_HP), res: total(ch, TravelEffect.REST_RES)}
    bonus = getattr(ch, "meal_bonus", {})
    if "hp" in bonus:
        extra["hp"] += total(ch, TravelEffect.MEAL, "hp")
    if res in bonus:
        extra[res] += total(ch, TravelEffect.MEAL, "res")
    return extra


def carry(ch):
    """負重上限多加的（背得多）：一直都有，打架中也是。"""
    return total(ch, TravelEffect.CARRY)


def cure_step(ch):
    """持續扣 HP 的效果每 tick 多減幾（早點解毒）：沒在打架時，一件多減 1。"""
    return 0 if fighting(ch) else count(ch, TravelEffect.CURE)


def revive_hp(ch):
    """死掉回去時 HP 回到多少（死後不虛弱）：不超過自己的上限；沒有這種旅具是 None。"""
    n = total(ch, TravelEffect.REVIVE)
    return min(ch.panel["hp"], n) if n else None


def score_line(ch, label, obj, effect):
    """score「旅具效果」那段的一行：「【照明用具】多回 MV：休息、睡覺時每 30 秒 +5」。"""
    _, _, name, when, _ = EFFECTS[effect]
    res = stats.STAT_NAMES[resource_key(ch)]
    head = f"【{label}】" + name.format(res=res) + "："
    if effect == TravelEffect.CURE:
        return head + when
    if effect == TravelEffect.MEAL:
        return head + f"{when} HP +{amount(ch, obj, effect, 'hp')}、{res} +{amount(ch, obj, effect, 'res')}"
    if effect == TravelEffect.REVIVE:
        return head + f"{when} {amount(ch, obj, effect)}"
    return head + f"{when} +{amount(ch, obj, effect)}"


def poem(obj):
    """examine 那句詩（不寫數字，使用者 2026-11-20 定的）；不是旅具是 None。"""
    effect = effect_of(obj)
    return None if effect is None else EFFECTS[effect][4]
