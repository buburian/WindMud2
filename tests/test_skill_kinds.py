"""第 1 批路線技能的機制（設計文件 §2.6，mud_design 的技能草案）：被動、限定武器和副手、只能開打前用、
減弱（倍率一定放得上去、持續扣血要擲命中）、補血（一次、持續）、吸血、打中後的減弱、增強的倍率、效果種類、存檔。

資料跟 mud_design 比對在 test_skill_tree.py。借用 test_items.py 的區域（房間 102 有一隻 5 級的野狗，物品 101～110）。
亂數換成 Always：0.5 是打中、不浮動、不爆擊（武器取中間值）；0.99 是打不中；0.0 是打中、爆擊。
"""
import asyncio
import re

import pytest

import mud.commands as commands
from mud import affects, area, combat, damage, fight, skills, stats, zones
from mud.characters import characters
from mud.commands import skills as skill_commands
from mud.config import ENCODING, TICK_SECONDS
from mud.players import Player
from test_items import FakeWriter, make, prompt_of, reply, the_dog, world  # noqa: F401（world 是 fixture）

SWORD, STAFF = stats.Guild.SWORD, stats.Guild.STAFF
LONGSWORD, SHIELD, DAGGER, GREATSWORD = 2, 3, 4, 5      # test_items.py 的物品（號碼 − 100）


class Always:
    """假的亂數：random() 一律回傳 x。"""

    def __init__(self, x):
        self.x = x

    def random(self):
        return self.x


@pytest.fixture(autouse=True)
def steady(monkeypatch):
    monkeypatch.setattr(combat, "rng", Always(0.5))


def hero(name="Shabu", guild=SWORD, level=10, learn=()):
    """在線上、有屬性的人類玩家，站在房間 102，會 learn 這幾個技能（學會才算屬性：被動技能要有效）。"""
    p = Player(name, FakeWriter(), zones.world.rooms[102])
    p.race, p.guild = stats.Race.HUMAN, guild
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.skills = list(learn)
    stats.set_level(p, level)
    characters.append(p)
    return p


def plain(p):
    text = re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))
    p.writer.data = b""
    return text


def say(p, line):
    plain(p)
    commands.command(p, line)
    return plain(p)


def in_fight(starts, body):
    """在 asyncio 裡開打（starts 是 [(打的人, 被打的人)]），再跑 body()，回傳它的結果。"""
    async def main():
        for ch, victim in starts:
            fight.start_fight(ch, victim)
        return body()

    return asyncio.run(main())


def sturdy_dog():
    """野狗，HP 很多（技能打不死，才看得到打中後的效果）。"""
    dog = the_dog()
    dog.hp = 10 ** 6
    return dog


def wield(p, n, slot="wield"):
    p.equipment[slot] = make(n, 1)
    stats.recompute(p)


# ---- 被動 ----

def test_passives_cannot_be_used(world):
    p = hero(learn=["iron_body"])
    assert say(p, "use iron") == reply(p, "鋼鐵之軀是被動技能，學會就一直有效，不用放。")


def test_passives_multiply_the_final_value_when_learned(world):
    p = hero()
    hp, dodge, now = p.panel["hp"], p.panel["dodge"], p.hp
    skills.learn(p, skills.SKILLS["iron_body"])
    skills.learn(p, skills.SKILLS["light_step"])
    assert (p.panel["hp"], p.panel["dodge"]) == (pytest.approx(hp * 1.05), pytest.approx(dodge * 1.05))
    assert p.hp == now                                               # 上限變高，現在的不補（跟穿裝備一樣）
    skills.forget(p, skills.SKILLS["iron_body"])
    assert p.panel["hp"] == pytest.approx(hp)


def test_heavy_mastery_needs_a_two_handed_weapon(world):
    p = hero(learn=["heavy_mastery"])
    dog = the_dog()
    assert p.final == {}
    wield(p, LONGSWORD)
    assert p.final == {}                                             # 單手武器：沒有效果
    wield(p, GREATSWORD)
    assert p.final == {"dmg_out": 1.05}
    with_it = damage.per_hit(p, dog, "phys", 10)
    p.skills = []
    stats.recompute(p)
    assert with_it == pytest.approx(damage.per_hit(p, dog, "phys", 10) * 1.05)    # 平砍（技能也是平砍 × 比率）×1.05


def test_wearing_and_removing_turns_a_passive_on_and_off(world):
    p = hero(learn=["heavy_mastery"])
    p.carrying.insert(0, make(GREATSWORD, 1))
    say(p, "wear greatsword")
    assert p.final == {"dmg_out": 1.05}
    say(p, "remove greatsword")
    assert p.final == {}


def test_shield_mastery_multiplies_the_shields_ac(world):
    p = hero(learn=["shield_mastery"])
    wield(p, SHIELD, "offhand")
    shield_ac = p.equipment["offhand"].base["ac"]
    assert p.panel["ac"] == pytest.approx(shield_ac * 1.05)


def test_dual_passives_need_two_weapons(world):
    p = hero()
    wield(p, LONGSWORD)
    wield(p, DAGGER, "offhand")
    hands, crit = damage.hands(p), p.panel["crit"]
    skills.learn(p, skills.SKILLS["dual_mastery"])
    skills.learn(p, skills.SKILLS["lethal_rhythm"])
    assert damage.hands(p) == [pytest.approx(hands[0]), pytest.approx(hands[1] * 1.05)]   # 只有副手
    assert p.panel["crit"] == pytest.approx(crit * 1.05)
    del p.equipment["offhand"]
    stats.recompute(p)
    assert p.final == {} and p.panel["crit"] == pytest.approx(crit)


# ---- 限定武器、副手、只能開打前用 ----

def test_offhand_and_weapon_conditions(world):
    p = hero(learn=["twin_slash", "backstab", "shield_mastery"])
    mv = p.mv
    assert say(p, "use twin dog") == reply(p, "你要兩手各拿一把武器才能用雙刃斬。")
    assert say(p, "use back dog") == reply(p, "你手上的武器不能用背刺。")
    assert (p.fighting, p.mv, p.cooldowns) == (None, mv, {})       # 沒過就不開打、不扣、不冷卻
    wield(p, DAGGER)                                                 # 主手拿匕首
    assert in_fight([], lambda: say(p, "use back dog")).startswith("你使用背刺攻擊野狗，")


def test_deathblow_only_before_the_fight(world):
    p = hero(learn=["deathblow"])
    wield(p, DAGGER)
    dog = the_dog()
    ming = hero("Ming")
    assert in_fight([(ming, dog)], lambda: say(p, "use death dog")) == reply(p, "絕命刺只能在還沒開打時用。")
    assert in_fight([(p, dog)], lambda: say(p, "use death dog")) == reply(p, "絕命刺只能在還沒開打時用。")


def test_deathblow_opens_a_fight(world):
    p = hero(learn=["deathblow"])
    wield(p, DAGGER)
    got = in_fight([], lambda: (say(p, "use death dog"), p.fighting))
    assert got[0].startswith("你使用絕命刺攻擊野狗，") and got[1] is the_dog()


# ---- 減弱 ----

@pytest.mark.parametrize("skill, keys", [("expose_weakness", {"ac": 0.5}), ("cripple", {"hit": 0.5, "dodge": 0.5}),
                                         ("erosion", {"res_spell": 0.65}), ("chill", {"dodge": 0.5}),
                                         ("curse", {"res_phys": 0.9, "res_spell": 0.9})])
def test_debuffs_that_only_change_stats_always_land(world, monkeypatch, skill, keys):
    monkeypatch.setattr(combat, "rng", Always(0.99))                # 平砍、技能都打不中
    s = skills.SKILLS[skill]
    p = hero(guild=s.guild, learn=[skill])
    dog = the_dog()
    before = dict(dog.panel)
    got, foe = in_fight([], lambda: (say(p, f"use {skill} dog"), p.fighting))
    assert got.startswith(f"你對野狗施展了【{s.name}】。")
    for key, x in keys.items():
        assert dog.panel[key] == pytest.approx(before[key] * x), key
    assert foe is dog                                                # 放減益會開打（asyncio.run 結束時戰鬥會被收掉，所以在裡面看）


def test_weaken_lowers_every_damage_point(world):
    p = hero(guild=STAFF, learn=["weaken"])
    dog = the_dog()
    before = {k: dog.panel.get(k) for k in stats.DMG_POINT_KEYS}
    in_fight([], lambda: say(p, "use weaken dog"))
    for key, n in before.items():
        if n is not None:
            assert dog.panel[key] == pytest.approx(n * 0.9), key


def test_poison_blade_hits_then_poisons(world):
    p = hero(learn=["poison_blade"])
    dog = the_dog()
    got = in_fight([], lambda: say(p, "use poison dog"))
    assert got.startswith("你對野狗施展了【毒刃】。")
    poison = next(a for a in dog.affects if a.source == "poison_blade")
    each = damage.per_hit(p, dog, "phys") * 0.3                     # 這一下 × 30%，放的時候算好
    assert (poison.name, poison.tag, poison.hurt) == ("中毒", "中毒", "毒傷")
    assert poison.periodic == {"hp": pytest.approx(-max(1, each))}
    assert poison.duration * TICK_SECONDS == 30


def test_poison_blade_can_miss(world, monkeypatch):
    monkeypatch.setattr(combat, "rng", Always(0.99))
    p = hero(learn=["poison_blade"])
    dog = the_dog()
    ming = hero("Ming")
    plain(ming)
    got, seen, foe = in_fight([], lambda: (say(p, "use poison dog"), plain(ming), p.fighting))
    assert got == reply(p, "你對野狗施展【毒刃】，但是失手了。")
    assert seen == f"\r\nShabu對野狗施展【毒刃】，但是失手了。\r\n\r\n{prompt_of(ming)}"
    assert dog.affects == [] and foe is dog                          # 沒放上去，還是開打了


# ---- 補血 ----

def test_heal_yourself(world):
    p = hero(guild=STAFF, learn=["heal"])
    p.hp = 1
    amount = p.panel["dmg_spell"] * 1.2                              # 空手：法術傷害點數 × 比率，不浮動
    assert say(p, "use heal") == reply(p, f"你對自己施展了【治療術】，恢復了 {stats.shown(amount)} 點 HP。")
    assert p.hp == pytest.approx(1 + amount) and p.fighting is None


def test_heal_stops_at_the_top_and_can_crit(world, monkeypatch):
    p = hero(guild=STAFF, learn=["heal"])
    p.hp = p.panel["hp"] - 1
    assert say(p, "use heal") == reply(p, "你對自己施展了【治療術】，恢復了 1 點 HP。")
    monkeypatch.setattr(combat, "rng", Always(0.0))
    p.hp, p.cooldowns = 1, {}
    amount = p.panel["dmg_spell"] * 1.2 * damage.crit_mult(p)
    assert say(p, "use heal") == reply(p, f"你對自己施展了【治療術】，爆擊！恢復了 {stats.shown(amount)} 點 HP。")


def test_heal_counts_the_main_hand_weapon(world):
    p = hero(guild=STAFF, learn=["heal"])
    wield(p, LONGSWORD)
    sword = p.equipment["wield"]
    p.hp = 1
    say(p, "use heal")
    middle = (sword.base["dmg_min"] + sword.base["dmg_max"]) / 2    # Always(0.5)：武器取中間值
    assert p.hp == pytest.approx(1 + (p.panel["dmg_spell"] + middle) * 1.2)


def test_heal_others_but_not_mobiles(world):
    p = hero(guild=STAFF, learn=["heal"])
    ming = hero("Ming")
    ming.hp = 1
    amount = stats.shown(p.panel["dmg_spell"] * 1.2)
    plain(ming)
    assert "恢復了" in say(p, "use heal ming")
    assert plain(ming) == f"\r\nShabu對你施展了【治療術】，你恢復了 {amount} 點 HP。\r\n\r\n{prompt_of(ming)}"
    assert say(p, "use heal dog") == reply(p, "治療術只能放在玩家身上。")


def test_renew_heals_every_3_seconds(world):
    p = hero(guild=STAFF, learn=["renew"])
    p.hp = 1
    assert say(p, "use renew") == reply(p, "你對自己施展了【回春術】。")
    renew = next(a for a in p.affects if a.source == "renew")
    each = p.panel["dmg_spell"] * 0.1
    assert renew.periodic == {"hp": pytest.approx(each)} and renew.duration * TICK_SECONDS == 30
    assert affects.parts(renew) == [f"每 3 秒 HP {stats.shown(each):+d}"]      # 放的時候算好的有小數：score 寫整數
    for _ in range(3):
        affects.tick()
    assert p.hp == pytest.approx(1 + each)


# ---- 傷害技能的吸血、打中後的減弱 ----

def test_drain_life_heals_you(world):
    p = hero(guild=STAFF, learn=["drain_life"])
    p.hp = 1
    dog = sturdy_dog()
    got = in_fight([(p, dog)], lambda: say(p, "use drain dog"))
    dmg = damage.per_hit(p, dog, "spell") * 2.3
    assert f"你吸取了 {stats.shown(dmg * 0.5)} 點 HP。" in got
    assert p.hp == pytest.approx(1 + dmg * 0.5)


def test_ice_shard_slows_on_hit(world):
    p = hero(guild=STAFF, learn=["ice_shard"])
    dog = sturdy_dog()
    hands = damage.hands(dog)
    in_fight([(p, dog)], lambda: say(p, "use ice dog"))
    slow = next(a for a in dog.affects if a.source == "ice_shard")
    assert (slow.mult, slow.tag, slow.duration * TICK_SECONDS) == ({"aspd": 0.9}, "變慢", 6)
    assert damage.hands(dog) == [pytest.approx(hands[0] * 0.9)]


def test_ice_shard_misses_without_slowing(world, monkeypatch):
    monkeypatch.setattr(combat, "rng", Always(0.99))
    p = hero(guild=STAFF, learn=["ice_shard"])
    dog = sturdy_dog()
    in_fight([(p, dog)], lambda: say(p, "use ice dog"))
    assert dog.affects == []


def test_hit_multiplier_and_attack_speed(world):
    p, dog = hero(), the_dog()
    chance, hands = damage.hit_chance(dog, p), damage.hands(dog)
    affects.add(dog, affects.Affect(source="x", name="x", duration=10, mult={"hit_mult": 0.5, "aspd": 0.5}))
    assert damage.hit_chance(dog, p) == pytest.approx(chance * 0.5)       # 失明：命中率最後再乘
    assert damage.hands(dog) == [pytest.approx(hands[0] * 0.5)]


# ---- 增強 ----

def test_buffs_with_multipliers(world):
    p = hero(guild=STAFF, learn=["bless", "divine_favor"])
    before, now = dict(p.panel), p.hp
    say(p, "use bless")
    say(p, "use divine")
    assert p.panel["res_phys"] == pytest.approx(before["res_phys"] * 1.1)
    assert p.panel["res_spell"] == pytest.approx(before["res_spell"] * 1.1)
    assert p.panel["hp"] == pytest.approx(before["hp"] * 1.1) and p.hp == now


def test_berserk_is_only_for_yourself(world):
    p = hero(learn=["berserk", "war_cry"])
    ming = hero("Ming")
    assert say(p, "use berserk ming") == reply(p, skills.SELF_ONLY)
    ac, mv = p.panel["ac"], p.mv
    assert say(p, "use berserk") == reply(p, "你對自己施展了【狂暴】。")
    assert p.panel["ac"] == pytest.approx(ac * 0.92) and p.mv < mv
    assert say(p, "use war ming").startswith("你對Ming施展了【戰吼】。")
    assert [a.source for a in ming.affects] == ["war_cry"]


def test_shield_buffs(world):
    p = hero(learn=["bulwark"])
    say(p, "use bulwark")
    assert p.affects[0].shield == pytest.approx(p.panel["hp"] * 0.1)


# ---- 效果種類、存檔、說明、區域檔 ----

def test_effects_carry_their_tag(world):
    p = hero(guild=STAFF, learn=["fireball", "corrode"])
    dog = sturdy_dog()
    in_fight([], lambda: say(p, "use fireball dog"))
    assert affects.has_tag(dog, "燃燒")                               # 火球的燃燒（技能寫的 tag）
    in_fight([], lambda: say(p, "use corrode dog"))
    assert affects.has_tag(dog, "腐蝕術")                             # 沒寫 tag：技能名稱
    assert not affects.has_tag(dog, "中毒")


def test_multipliers_are_saved():
    a = affects.Affect(source="cripple", name="致殘", duration=30, mult={"hit": 0.5}, tag="致殘")
    data = affects.to_data(a)
    assert affects.from_data(data) == a
    old = {k: v for k, v in data.items() if k not in ("mult", "tag")}     # 舊存檔沒有這兩個
    assert (affects.from_data(old).mult, affects.from_data(old).tag) == ({}, "")


def test_parts_shows_multipliers():
    a = affects.Affect(source="x", name="x", duration=10, mult={"ac": 0.92, "aspd": 0.85, "res_phys": 1.1})
    assert affects.parts(a) == ["AC -8%", "攻速 -15%", "物理抗性 +10%"]


@pytest.mark.parametrize("guild", [SWORD, STAFF])
def test_skills_listing_stays_within_79(world, guild):
    p = hero(guild=guild, level=50, learn=[s.id for s in skills.SKILLS.values() if not s.imm_only])
    wield(p, LONGSWORD)
    skill_commands.do_skills(p, "")                                  # 直接呼叫：太長了，打指令會分頁
    lines = plain(p).split("\r\n")
    assert all(len(line.encode("cp950")) <= 79 for line in lines)
    text = "\n".join(lines)
    assert re.search(r"鋼鐵之軀 iron_body +被動\n +HP \+5%\n", text)
    assert re.search(r"雙刃斬 twin_slash +傷害 .*\n +打 3 次、要雙持\n", text)
    assert "絕命刺 deathblow" in text and "要拿匕首、只能在還沒開打時用" in text
    assert re.search(r"重武精通 heavy_mastery +被動\n +平砍傷害 \+5%、要拿雙手武器\n", text)
    assert "冰錐 ice_shard" in text and "打中後：攻速 -10%、變慢，6 秒" in text
    assert "吸血 50%" in text
    assert re.search(r"治療術 heal +補血 \d+(~\d+)? +\d+ MP +6 秒", text)
    assert re.search(r"回春術 renew +持續 30 秒 .*\n +每 3 秒補 \d+(~\d+)? HP，10 次", text)
    assert re.search(r"毒刃 poison_blade +持續 30 秒 .*\n +中毒：每 3 秒傷害 \d+(~\d+)?，10 次", text)


def test_route_skills_cost():
    power = skills.SKILLS["power_slash"]
    for level in (1, 10, 50, 100):
        want = max(1, stats.shown(stats.resource_standard(level, SWORD, "mv") * 0.19))
        assert skills.cost(power, level) == want
    assert skills.cost(skills.SKILLS["iron_body"], 50) == 0


def test_items_cannot_hold_passives():
    problems = []
    area.check_skill_item("物品 101", 10, [5, "iron_body", "", ""], problems)
    assert len(problems) == 1 and "不能是 'iron_body'" in problems[0]
