"""連動（設計文件 §2.6，清單在 mud_design 的 design/技能/_總覽.md、sim/skill_tree.py 的 COMBOS）：技能碰到某些條件會變強。

- 條件是自己身上有什麼，或目標身上有什麼（效果，或牠正在打誰）。看效果的種類（affects.has_tag），不看是哪個技能放的；誰放的都算
  （「被你挑釁」這種寫明是你的才看 Affect.by）。
- 放技能的那一刻看一次：打很多下的技能不會每下重看（skills.strike 開打前算好）。
- 好幾個連動同時成立，全部乘起來。
skills.py 在對的地方呼叫這裡；每個函式的註解寫它管哪幾個連動。
坑：skills 會 import 這個模組，用到 skills 的在函式裡才 import。
"""
from . import affects
from .config import AFFECT_PULSE_TICKS, ROUND_TICKS

RATIOS = {                                  # 比率的連動：技能 id → [(條件, 倍數)]，條件是 (ch, 目標) → 成立沒
    "smash": [(lambda ch, v: affects.has_tag(ch, "戰吼"), 1.3)],            # 戰吼助威
    "pummel": [(lambda ch, v: affects.has_tag(ch, "戰吼"), 1.3)],           # 戰吼助威（Lv5 的猛擊也算）
    "power_slash": [(lambda ch, v: affects.has_tag(ch, "戰吼"), 1.3)],      # 戰吼助威
    "sky_rend": [(lambda ch, v: affects.has_tag(v, "站不穩"), 1.5)],        # 震地破綻
    "backstab": [(lambda ch, v: affects.has_tag(v, "中毒"), 1.3),            # 毒上加刺
                 (lambda ch, v: affects.has_tag(v, "失明"), 2.0),            # 煙中背刺
                 (lambda ch, v: v.fighting is not None and v.fighting is not ch, 1.5)],   # 背後偷襲：用背刺開打不算
    "glacier_crash": [(lambda ch, v: affects.has_tag(v, "凍住"), 2.0)],     # 碎冰
}
WEAKEN_STEP = 1.25                          # 越弱越吸：目標身上每有一個減弱類技能放的效果，吸取生命的比率 ×1.25
POISON_FEEDERS = ("twin_slash", "flurry", "hundred_cuts", "blade_dance")   # 多刀催毒：每打中一下，目標的中毒多跳 1 次
STAGGER_TICKS = 6                           # 震地破綻：震地打中的怪 6 秒內站不穩
REFRESHED_HEALS = ("回春術", "生命之泉")     # 群體回春：群體治療讓這兩種的時間重新算


def ratio(ch, skill, victim):
    """傷害技能打 victim 的比率要乘多少（戰吼助威、震地破綻、毒上加刺、煙中背刺、背後偷襲、碎冰、越弱越吸）。"""
    x = 1.0
    for ok, times in RATIOS.get(skill.id, []):
        if ok(ch, victim):
            x *= times
    if skill.id == "drain_life":
        x *= WEAKEN_STEP ** weakened(victim)
    return x


def weakened(victim):
    """victim 身上有幾個減弱類技能放的效果（越弱越吸）：同一個技能只算一個，別人放的也算。"""
    from .skills import SKILLS
    return len({a.source for a in victim.affects if a.source in SKILLS and SKILLS[a.source].kind == "debuff"})


def extra_hits(ch, skill):
    """狂暴連斬：身上有狂暴時，旋風斬、天崩地裂每隻多打 1 次。"""
    return 1 if skill.id in ("whirlwind", "cataclysm") and affects.has_tag(ch, "狂暴") else 0


def opener_ok(victim):
    """趁暈絕命：目標暈著時，打架中也能用絕命刺。"""
    return affects.has_tag(victim, "暈")


def control_ticks(ch, skill, victim):
    """控制要多幾個 tick（多 1 回合）：挑釁盾擊（盾擊打被你挑釁的怪）、慢了就凍（冰凍術打變慢的怪）。"""
    if skill.id == "shield_bash" and any(a.tag == "被挑釁" and a.by is ch for a in victim.affects):
        return ROUND_TICKS
    if skill.id == "freeze" and affects.has_tag(victim, "變慢"):
        return ROUND_TICKS
    return 0


def on_hit(ch, skill, victim):
    """打中一下、目標沒死：多刀催毒（毒刃多跳 1 次）、震地破綻（站不穩 6 秒）。"""
    if skill.id in POISON_FEEDERS:
        for a in victim.affects:
            if a.tag == "中毒" and a.periodic:
                a.ticks += AFFECT_PULSE_TICKS
                a.duration += AFFECT_PULSE_TICKS
    if skill.id == "quake":
        affects.add(victim, affects.Affect(source="quake_stagger", name="站不穩", tag="站不穩", duration=STAGGER_TICKS, by=ch))


def burns(victim):
    """victim 身上的燃燒（燃燒種類的持續扣血）。"""
    return [a for a in victim.affects if a.tag == "燃燒" and a.periodic.get("hp", 0) < 0]


def left_jumps(a):
    """持續扣血的效果還會跳幾次。"""
    return (a.elapsed + a.ticks) // AFFECT_PULSE_TICKS - a.elapsed // AFFECT_PULSE_TICKS


DETONATED = "$n身上的【$t】一口氣燒完了！"


def after_hits(battle, ch, skill, victim, burning):
    """一隻打完、牠還活著、打中過（burning 是放技能那一刻牠在不在燒）：爆炎引爆（剩下的燃燒一次跳完）、火雨添柴（燃燒的時間重新算）。
    回傳牠死了沒。
    """
    from . import combat
    if not burning:
        return False
    if skill.id == "fire_rain":
        for a in burns(victim):
            a.ticks, a.elapsed = a.duration, 0
    if skill.id == "blast":
        for a in burns(victim):
            dmg = -a.periodic["hp"] * left_jumps(a)
            victim.affects.remove(a)
            affects.changed(victim)
            if dmg <= 0:
                continue
            if combat.burn_all(battle, ch, victim, a, dmg, DETONATED):
                return True
    return False


def spread_poison(victims):
    """毒刃擴散：迴旋刃打中的怪裡有一隻中毒，其他被打中、還沒中毒的也中同樣的毒（同樣的每跳、剩下的時間）。"""
    import copy
    poison = next((a for v in victims for a in v.affects if a.tag == "中毒" and a.periodic), None)
    if poison is None:
        return
    for v in victims:
        if not any(a.tag == "中毒" for a in v.affects):
            same = copy.copy(poison)
            same.periodic = dict(poison.periodic)
            affects.add(v, same)


def heal_ratio(skill, target):
    """回春加護：目標身上有回春術時，治療術補的量 ×1.3。"""
    return 1.3 if skill.id == "heal" and affects.has_tag(target, "回春術") else 1.0


def after_heal(skill, target):
    """群體回春：群體治療讓目標身上的回春術、生命之泉時間重新算。"""
    if skill.id == "mass_heal":
        for a in target.affects:
            if (a.tag or a.name) in REFRESHED_HEALS:
                a.ticks, a.elapsed = a.duration, 0


def shield_ratio(skill, target):
    """神佑護盾：身上有神佑的人，神聖護盾 ×1.5。"""
    return 1.5 if skill.id == "holy_shield" and affects.has_tag(target, "神佑") else 1.0


def guard_ratio(guardian):
    """鐵壁護人：保護的人身上有鐵壁時，改扣他的那一份減半（另一半不見）。"""
    return 0.5 if affects.has_tag(guardian, "鐵壁") else 1.0


def undead(a, victim):
    """死者為僕：被腐蝕術、瘟疫扣死的怪照樣留屍體和掉落，另外叫出放的人的骷髏（要學會喚骨術，跟喚骨術一樣換掉舊的）。"""
    from . import summons
    from .characters import characters
    from .skills import SKILLS
    owner = a.by
    if a.source in ("corrode", "plague") and owner in characters and "raise_skeleton" in getattr(owner, "skills", []):
        summons.summon(owner, SKILLS["raise_skeleton"])
