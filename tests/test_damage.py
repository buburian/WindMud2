"""傷害公式、經驗值跟 mud_design 的 balance.py 比對（設計文件改了數字或公式，這裡會提醒）。"""
import itertools
import random

import pytest

from balance_loader import load_balance
from mud import damage, stats
from mud.area import MobTier
from mud.npcs import Npc
from mud.players import Player


@pytest.fixture(scope="module")
def balance():
    module = load_balance()
    if module is None:
        pytest.skip("找不到 mud_design/sim/balance.py")
    return module


@pytest.fixture(scope="module")
def model(balance):
    return balance.Model()


def player(level, race, guild):
    p = Player("玩家", None, None)
    p.race, p.guild, p.level = race, guild, level
    p.primaries = dict(stats.RACE_PRIMARIES[race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    stats.recompute(p)
    return p


def mob(level, tier="normal", attack=None, defense=None, archetype=None):
    n = Npc("怪物", 0, None)
    n.level, n.tier = level, MobTier(tier)
    n.panel, n.mix = stats.mob_stats(level, tier, attack, defense, archetype)
    return n


def entity(balance, model, ch):
    """我們的角色 → balance.py 的 Entity（同樣的屬性、等級、攻擊類型）。"""
    dtype = str(ch.guild) if isinstance(ch, Player) else "phys"
    mix = dict(ch.mix) if isinstance(ch, Npc) else None
    return balance.Entity("x", ch.level, model.G(ch.level), dtype, dict(ch.panel), mix)


def fighters():
    """各種玩家和生物：種族 × 公會 × 等級，種類 × 攻擊類型 × 攻防 × 原型 × 等級。"""
    out = [player(level, race, guild) for level in (1, 10, 50)
           for race in (stats.Race.HUMAN, stats.Race.ELF, stats.Race.ORC) for guild in stats.Guild]
    out += [mob(level, tier, attack, defense, archetype) for level, tier, attack, defense, archetype in [
        (1, "trash", None, None, None), (5, "elite", "dragon/phys", "phys", "tank"), (10, "normal", "spell", "spell", None),
        (30, "boss", "phys/spell", None, "berserker"), (50, "elite", "spell/dragon", "phys", "agile"),
        (20, "normal", None, None, "extreme_tank"), (-5, "normal", None, None, None),
    ]]
    return out


def test_numbers_match_mud_design(balance, model):
    c = model.cfg
    assert damage.HIT_K == pytest.approx(model.K)
    assert damage.CRIT_BASE == c.crit_base
    assert damage.CRIT_MULT == (c.critmult_lo, c.critmult_hi, c.critmult_base_eff)
    assert damage.SPEED == (c.speed_lo, c.speed_hi, c.speed_base_eff)
    assert damage.RESIST_BASE == c.resist_base
    assert damage.LEVEL_MOD == pytest.approx(model.level_mod, rel=1e-12)
    assert damage.DMG_VAR == c.dmg_var
    assert set(damage.TYPES) == set(balance.ATTACK_TYPES)


def test_panel_formulas_match_mud_design(balance, model):
    for ch in fighters():
        e = entity(balance, model, ch)
        assert damage.crit_chance(ch) == pytest.approx(model.crit_chance(e), rel=1e-12)
        assert damage.crit_mult(ch) == pytest.approx(model.crit_mult(e), rel=1e-12)
        assert damage.attacks_per_round(ch) == pytest.approx(model.attacks_per_round(e), rel=1e-12)


def test_hits_match_mud_design(balance, model):
    # 每一對攻守：命中率、三種類型的減傷和每一下的傷害，跟 attack_profile 一樣
    for a, d in itertools.permutations(fighters(), 2):
        ea, ed = entity(balance, model, a), entity(balance, model, d)
        profile = model.attack_profile(ea, ed)
        assert damage.hit_chance(a, d) == pytest.approx(profile["hit_chance"], rel=1e-12)
        for kind in damage.TYPES:
            assert damage.per_hit(a, d, kind) == pytest.approx(profile["per_hit_t"][kind], rel=1e-12), kind
        assert damage.attack_mix(a) == profile["mix"]


@pytest.mark.parametrize("seed", range(5))
def test_strike_matches_mud_design(balance, model, seed):
    # 同一個種子打很多下，每一下的傷害都跟 balance.py 的 _strike_once 一樣（亂數的順序一樣）
    people = fighters()
    for a, d in [(people[0], people[-1]), (people[-1], people[0]), (people[-5], people[3]), (people[-3], people[-2])]:
        p = model._combat_params(entity(balance, model, a), entity(balance, model, d))
        ours, theirs = random.Random(seed), random.Random(seed)
        for _ in range(300):
            dmg, _crit = damage.strike(a, d, ours)
            want = model._strike_once(p, p["hands"][0], theirs.random, model.cfg.dmg_var, False)
            assert dmg == pytest.approx(want, rel=1e-12)


def test_strike_reports_crits_and_misses():
    a, d = player(10, stats.Race.HUMAN, stats.Guild.SWORD), mob(10)

    class Always:
        def __init__(self, x):
            self.x = x

        def random(self):
            return self.x

    assert damage.strike(a, d, Always(0.99)) == (0.0, False)                  # 擲命中沒過
    dmg, crit = damage.strike(a, d, Always(0.0))                               # 中、浮動最低、爆擊
    assert crit and dmg == pytest.approx(damage.per_hit(a, d, "phys") * 0.8 * damage.crit_mult(a))
    assert damage.strike(a, d, Always(0.5)) == (pytest.approx(damage.per_hit(a, d, "phys")), False)


# ---- 經驗值（§4.7）----

def test_exp_numbers_match_mud_design(balance, model):
    c = model.cfg
    assert stats.EXP_NORMAL_LV1 == c.exp_normal_lv1
    assert stats.POWER_PER_LEVEL == c.power_per_level
    assert stats.EXP_ZERO_GAP == c.exp_zero_gap
    assert stats.EXP_KILLS == (c.exp_kills_first, c.exp_kills_last)
    assert (stats.EXP_EARLY_BONUS, stats.EXP_EARLY_CURVE) == (c.exp_early_bonus, c.exp_early_curve)
    assert stats.MAX_LEVEL == c.max_level
    assert {str(k): v for k, v in stats.TIER_DIFFICULTY.items()} == pytest.approx(model.tier_difficulty, rel=1e-9)
    assert {str(k): v for k, v in stats.TIER_EXP_MULT.items()} == {k: v["exp_mult"] for k, v in balance.MOB_TIERS.items()}


def test_exp_formulas_match_mud_design(model):
    for level in range(1, 100):
        assert stats.exp_to_level(level) == pytest.approx(model.exp_to_level(level), rel=1e-9), level
    for level in range(1, 101):
        assert stats.exp_early(level) == pytest.approx(model.exp_early(level), rel=1e-9, abs=1e-12), level
    for p_level, gap, tier in itertools.product((1, 10, 20, 55, 99), (-12, -10, -9, -3, 0, 2, 7), MobTier):
        for early in (True, False):
            want = model.kill_exp(p_level, p_level + gap, str(tier), early=early)
            assert stats.kill_exp(p_level, p_level + gap, tier, early) == pytest.approx(want, rel=1e-9), (p_level, gap, tier)


def test_design_doc_exp_examples():
    # 設計文件 §4.7：1 級一般怪 10（前期經驗加成 ＋50% 後是 15）、升 2 級要 100（升級需求不乘加成）；低 10 級以上是 0
    assert stats.kill_exp(1, 1, MobTier.NORMAL, early=False) == pytest.approx(10.0)
    assert stats.kill_exp(1, 1, MobTier.NORMAL) == pytest.approx(15.0)
    assert stats.exp_to_level(1) == pytest.approx(100.0)
    assert (stats.exp_early(1), stats.exp_early(99), stats.exp_early(100)) == (pytest.approx(0.5), 0.0, 0.0)
    # 玩家角色手冊的例子：20 級打同級的垃圾怪 0.8、一般怪 36.0、菁英怪 85.2、Boss 91.0
    got = [round(stats.kill_exp(20, 20, tier), 1) for tier in (MobTier.TRASH, MobTier.NORMAL, MobTier.ELITE, MobTier.BOSS)]
    assert got == [0.8, 36.0, 85.2, 91.0]
    assert stats.kill_exp(20, 10, MobTier.BOSS) == 0.0
    assert stats.kill_exp(20, 11, MobTier.BOSS) > 0
