"""連動（設計文件 §2.6、mud_design 的 design/技能/_總覽.md，combos.py）：21 個，一個一個測。

借用 test_skills.py 的區域：房間 102 有 5 級的野狗和野貓（HP 調很多，技能打不死），101 在南邊。
亂數是 Always(0.5)：打中、不浮動、不爆擊、武器取中間值。比率的連動直接比牠少了多少 HP。
"""
import asyncio

import pytest

from mud import affects, combat, damage, fight, objects, protect, skills, stats, summons, zones
from mud.area import WeaponKind
from mud.characters import characters
from mud.config import AFFECT_PULSE_TICKS
from mud.npcs import Npc
from test_skills import fighter, mobile, prompt_of, say, text_of, world  # noqa: F401（world 是 fixture）

SWORD, STAFF = stats.Guild.SWORD, stats.Guild.STAFF
HP = 10 ** 6


@pytest.fixture(autouse=True)
def no_guards():
    protect.guards.clear()
    yield
    protect.guards.clear()


def hero(name="Shabu", guild=SWORD, learn=(), level=20):
    p = fighter(name, level=level, guild=guild)
    p.skills += list(learn)
    return p


def sturdy(*names):
    out = [mobile(n) for n in names]
    for m in out:
        m.hp = HP
    return out[0] if len(out) == 1 else out


def weapon(kind, slot="wield"):
    o = objects.Obj("武器", "", 5, ["weapon"])
    o.weapon_kind, o.base = WeaponKind(kind), {"dmg_min": 4.0, "dmg_max": 4.0}
    return o


def arm(p, main=None, off=None, shield=False):
    if main:
        p.equipment["wield"] = weapon(main)
    if off:
        p.equipment["offhand"] = weapon(off)
    if shield:
        o = objects.Obj("盾牌", "", 9, ["shield"])
        o.base = {"ac": 5.0}
        p.equipment["offhand"] = o
    stats.recompute(p)


def tag_on(ch, tag, by=None, **more):
    affects.add(ch, affects.Affect(source=f"test_{tag}", name=tag, tag=tag, duration=30, by=by, **more))


def run(body):
    """在 asyncio 裡跑 body()（會開打的要在裡面），回傳它的結果。"""
    async def main():
        return body()
    return asyncio.run(main())


def lost(m):
    return HP - m.hp


def hit(p, m, kind, ratio):
    """p 用技能打 m 一下（Always(0.5)、沒有連動）的傷害。"""
    return damage.per_hit(p, m, kind, 4.0 if damage.weapon_in(p, 0) else None) * ratio


# ---- 戰士、巨武 ----

def test_war_cry_boosts_smash(world):
    p = hero(learn=["war_cry"])
    dog = sturdy("野狗")
    say(p, "use war")
    run(lambda: say(p, "use smash dog"))
    assert lost(dog) == pytest.approx(hit(p, dog, "phys", skills.SKILLS["smash"].ratio * damage.crit_mult(p) * 1.3))   # 重擊必定爆擊


def test_war_cry_boosts_pummel_too(world):
    # Lv5 的猛擊跟重擊一樣算戰吼助威（2026-11-20）
    p = hero(learn=["war_cry", "pummel"])
    dog = sturdy("野狗")
    say(p, "use war")
    run(lambda: say(p, "use pummel dog"))
    assert lost(dog) == pytest.approx(hit(p, dog, "phys", skills.SKILLS["pummel"].ratio * damage.crit_mult(p) * 1.3))


def test_flame_arrow_burns_stack_with_fireball_and_count_for_blast(world):
    # 火焰箭的燃燒跟火球的是同一種效果：兩個各自算、疊在一起，爆炎引爆兩個都燒完
    p = hero(guild=STAFF, learn=["flame_arrow", "blast"])
    dog = sturdy("野狗")

    def body():
        say(p, "use fireball dog")
        say(p, "use flame_arrow dog")
        burns = sorted(a.source for a in dog.affects if a.tag == "燃燒")
        text = say(p, "use blast")
        return burns, text, dog.affects

    burns, text, left = run(body)
    assert burns == ["fireball", "flame_arrow"]
    assert text.count("野狗身上的【燃燒】一口氣燒完了！") == 2 and not any(a.tag == "燃燒" for a in left)


def test_berserk_adds_a_hit_to_whirlwind(world):
    p = hero(learn=["berserk", "whirlwind"])
    arm(p, main=WeaponKind.GREATSWORD)
    sturdy("野狗", "野貓")
    plain_text = run(lambda: say(p, "use whirl"))
    assert plain_text.count("你使用旋風斬攻擊野狗") == 2
    p.cooldowns = {}
    say(p, "use berserk")
    assert run(lambda: say(p, "use whirl")).count("你使用旋風斬攻擊野狗") == 3


def test_quake_staggers_and_sky_rend_hits_harder(world):
    p = hero(learn=["quake", "sky_rend"])
    arm(p, main=WeaponKind.GREATSWORD)
    dog, cat = sturdy("野狗", "野貓")
    run(lambda: say(p, "use quake"))
    assert affects.has_tag(dog, "站不穩") and affects.has_tag(cat, "站不穩")
    assert next(a for a in dog.affects if a.tag == "站不穩").duration == 6
    before = lost(dog)
    run(lambda: say(p, "use sky"))
    assert lost(dog) - before == pytest.approx(hit(p, dog, "phys", 1.8 * 0.75 * 1.5))


# ---- 盾衛 ----

def test_shield_bash_on_your_taunted_mobile_stuns_longer(world):
    p, ming = hero(learn=["taunt", "shield_bash"]), hero("Ming")
    arm(p, shield=True)
    dog = sturdy("野狗")

    def body():
        say(p, "use taunt dog")
        say(p, "use shield dog")
        return next(a for a in dog.affects if a.source == "shield_bash").duration

    assert run(body) == 6                                            # 2 回合 ＋ 1 回合
    for a in list(dog.affects):
        affects.remove(dog, a.source)
    tag_on(dog, "被挑釁", by=ming)                                    # 別人挑釁的不算
    p.cooldowns = {}
    run(lambda: say(p, "use shield dog"))
    assert next(a for a in dog.affects if a.source == "shield_bash").duration == 4


def test_bulwark_halves_what_you_take_for_others(world):
    p, ming = hero(learn=["guard", "bulwark"]), hero("Ming")
    dog = mobile("野狗")
    say(p, "use guard ming")
    say(p, "use bulwark")
    shield, hp = p.affects[0].shield, p.hp
    run(lambda: (fight.start_fight(dog, ming), combat.land(ming.fight, dog, ming, 20.0, False)))
    assert ming.hp == pytest.approx(ming.panel["hp"] - 14)           # 他照樣少受 30%
    assert (p.hp, p.affects[0].shield) == (hp, pytest.approx(shield - 3))    # 你只扣 6 的一半


# ---- 刺客、雙刃、暗殺 ----

@pytest.mark.parametrize("tag, times", [("中毒", 1.3), ("失明", 2.0)])
def test_backstab_on_poisoned_or_blind(world, tag, times):
    p = hero(learn=["backstab"])
    arm(p, main=WeaponKind.DAGGER)
    dog = mobile("野狗")
    tag_on(dog, tag)
    sturdy("野狗")                                                    # 加效果會重算屬性、HP 夾回上限：放完再調
    run(lambda: (fight.start_fight(p, dog), say(p, "use back")))    # 牠在打你：沒有背後偷襲
    assert lost(dog) == pytest.approx(hit(p, dog, "phys", 4.3 * times))


def test_backstab_from_behind(world):
    p, ming = hero(learn=["backstab"]), hero("Ming")
    arm(p, main=WeaponKind.DAGGER)
    dog = sturdy("野狗")
    run(lambda: say(p, "use back dog"))                              # 用背刺開打不算
    assert lost(dog) == pytest.approx(hit(p, dog, "phys", 4.3))
    dog.hp, p.cooldowns = HP, {}
    run(lambda: (fight.start_fight(dog, ming), say(p, "use back dog")))    # 牠在打 Ming
    assert lost(dog) == pytest.approx(hit(p, dog, "phys", 4.3 * 1.5))


def test_dual_hits_feed_the_poison(world):
    p = hero(learn=["poison_blade", "twin_slash"])
    arm(p, main=WeaponKind.LONGSWORD, off=WeaponKind.DAGGER)
    dog = sturdy("野狗")

    def body():
        say(p, "use poison dog")
        poison = next(a for a in dog.affects if a.source == "poison_blade")
        ticks = poison.ticks
        say(p, "use twin dog")
        return poison.ticks - ticks

    assert run(body) == 3 * AFFECT_PULSE_TICKS                        # 打中 3 下：多跳 3 次


def test_blade_spin_spreads_the_poison(world):
    p = hero(learn=["poison_blade", "blade_spin"])
    arm(p, main=WeaponKind.LONGSWORD, off=WeaponKind.DAGGER)
    dog, cat = sturdy("野狗", "野貓")

    def body():
        say(p, "use poison dog")
        say(p, "use blade")
        return [a.periodic for a in cat.affects if a.tag == "中毒"], [a.periodic for a in dog.affects if a.tag == "中毒"]

    theirs, mine = run(body)
    assert theirs == mine and len(theirs) == 1


def test_deathblow_on_a_stunned_mobile_in_a_fight(world):
    p = hero(learn=["deathblow"])
    arm(p, main=WeaponKind.DAGGER)
    dog = sturdy("野狗")

    def body():
        fight.start_fight(p, dog)
        refused = say(p, "use death")
        tag_on(dog, "暈")
        return refused, say(p, "use death")

    refused, used = run(body)
    assert refused.startswith("絕命刺只能在還沒開打時用。\r\n") and used.startswith("你使用絕命刺攻擊野狗")


# ---- 元素、烈焰、寒冰 ----

def test_erosion_lets_the_bolt_jump(world):
    p = hero(guild=STAFF, learn=["lightning_bolt"])
    dog, cat = sturdy("野狗", "野貓")
    run(lambda: say(p, "use light dog"))
    assert cat.hp == HP                                              # 沒有元素侵蝕不跳
    tag_on(dog, "元素侵蝕")
    p.cooldowns = {}
    foe = run(lambda: (say(p, "use light dog"), cat.fighting)[1])
    assert lost(cat) == pytest.approx(hit(p, cat, "spell", 4.25 * 0.5)) and foe is p


def test_blast_burns_out_the_fire(world):
    p = hero(guild=STAFF, learn=["blast"])
    dog = sturdy("野狗")
    mobile("野貓").room = zones.world.rooms[101]

    def body():
        say(p, "use fireball dog")
        burn = next(a for a in dog.affects if a.tag == "燃燒")
        each, left = -burn.periodic["hp"], combos_left(burn)
        before = lost(dog)
        text = say(p, "use blast")
        return lost(dog) - before, each * left, text, dog.affects

    took, burned, text, left = run(body)
    assert took == pytest.approx(hit(p, dog, "spell", 2.3) + burned) and burned > 0
    assert "野狗身上的【燃燒】一口氣燒完了！" in text and not any(a.tag == "燃燒" for a in left)


def combos_left(a):
    from mud import combos
    return combos.left_jumps(a)


def test_fire_rain_rekindles_the_fire(world):
    p = hero(guild=STAFF, learn=["fire_rain"])
    dog = sturdy("野狗")

    def body():
        say(p, "use fireball dog")
        for _ in range(4):
            affects.tick()
        burn = next(a for a in dog.affects if a.tag == "燃燒")
        worn = (burn.ticks, burn.elapsed)
        say(p, "use fire_rain")
        return worn, (burn.ticks, burn.elapsed, burn.duration)

    worn, now = run(body)
    assert worn == (5, 4) and now == (9, 0, 9)


def test_freeze_on_a_slowed_mobile_lasts_longer(world):
    p = hero(guild=STAFF, learn=["freeze"])
    dog = sturdy("野狗")
    tag_on(dog, "變慢")
    run(lambda: say(p, "use freeze dog"))
    assert next(a for a in dog.affects if a.source == "freeze").duration == 6


def test_glacier_crash_shatters_the_frozen(world):
    p = hero(guild=STAFF, learn=["glacier_crash"])
    dog = mobile("野狗")
    mobile("野貓").room = zones.world.rooms[101]
    tag_on(dog, "凍住")
    sturdy("野狗")
    run(lambda: say(p, "use glacier"))
    assert lost(dog) == pytest.approx(hit(p, dog, "spell", 2.8 * 2))


# ---- 神官、治療、詛咒 ----

def test_renew_boosts_heal(world):
    p = hero(guild=STAFF, learn=["heal", "renew"])
    say(p, "use renew")
    p.hp = 1
    say(p, "use heal")
    assert p.hp == pytest.approx(1 + p.panel["dmg_spell"] * 1.2 * 1.3)


def test_mass_heal_refreshes_renew(world):
    p = hero(guild=STAFF, learn=["renew", "mass_heal"])
    say(p, "use renew")
    renew = p.affects[0]
    for _ in range(4):
        affects.tick()
    say(p, "use mass")
    assert (renew.ticks, renew.elapsed) == (renew.duration, 0)


def test_divine_favor_strengthens_holy_shield(world):
    p = hero(guild=STAFF, learn=["divine_favor", "holy_shield"])
    say(p, "use divine")
    say(p, "use holy")
    shield = next(a for a in p.affects if a.source == "holy_shield")
    assert shield.shield == pytest.approx(p.panel["hp"] * 0.1 * 1.5)


def test_drain_life_drinks_deeper_from_the_weakened(world):
    p = hero(guild=STAFF, learn=["drain_life"])
    dog = mobile("野狗")
    for source in ("weaken", "curse", "poison_blade"):
        affects.add(dog, affects.Affect(source=source, name=source, duration=30))
    affects.add(dog, affects.Affect(source="fly", name="fly", duration=30))      # 增益不算
    sturdy("野狗")
    run(lambda: say(p, "use drain dog"))
    assert lost(dog) == pytest.approx(hit(p, dog, "spell", 2.3 * 1.25 ** 3), rel=1e-6)


@pytest.mark.parametrize("knows", [True, False])
def test_those_killed_by_corrode_rise_as_your_skeleton(world, knows):
    p = hero(guild=STAFF, learn=["corrode"] + (["raise_skeleton"] if knows else []))
    dog = mobile("野狗")
    affects.add(dog, skills.dot_affect("corrode", {"name": "腐蝕術", "jumps": 10, "hurt": "侵蝕"}, 10 ** 6, "腐蝕術", p))
    for _ in range(AFFECT_PULSE_TICKS):
        affects.tick()
    assert dog not in characters
    assert any(o.item_type == objects.CORPSE_NPC_ITEM_TYPE for o in p.room.contents)     # 照樣留屍體
    assert [s.name for s in summons.of(p)] == (["骷髏"] if knows else [])
