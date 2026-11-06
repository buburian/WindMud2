"""裝備跟屬性、戰鬥、技能的關係：跟 balance.py 比對（primary_bundle、apply_points、雙持的比例），也比對手冊的表（負重、武器重量、攻擊方式）。

物品指令本身在 tests/test_items.py（這裡借用它的區域和輔助函式）。
"""
import asyncio
import dataclasses
import re
from pathlib import Path

import pytest

from balance_loader import load_balance
from mud import combat, damage, fight, skills, stats
from mud.area import ATTACK_NAMES, Attack, WeaponKind
from mud.players import Player
from test_items import give, make, person, plain, say, the_dog, world  # noqa: F401（world 是 fixture）

MANUAL = Path(__file__).resolve().parent.parent / "docs" / "玩家角色手冊.md"
AREA_MANUAL = Path(__file__).resolve().parent.parent / "docs" / "區域製作手冊.md"


class Always:
    """假的亂數：random() 一律回傳 x。"""

    def __init__(self, x):
        self.x = x

    def random(self):
        return self.x


class Counting:
    def __init__(self):
        self.calls = 0

    def random(self):
        self.calls += 1
        return 0.5


@pytest.fixture(scope="module")
def balance():
    module = load_balance()
    if module is None:
        pytest.skip("找不到 mud_design/sim/balance.py")
    return module


@pytest.fixture(scope="module")
def model(balance):
    return balance.Model()


def section(text, title):
    """手冊裡 title 這一節：到下一個同一層（或更上層）的標題為止。"""
    start = text.index(title)
    level = len(title) - len(title.lstrip("#"))
    end = re.compile(rf"\n#{{1,{level}}} ").search(text, start + len(title))
    return text[start:end.start() if end else None]


# ---- 手冊的表 ----

def test_carry_table_matches_the_manual():
    part = section(MANUAL.read_text(encoding="utf-8"), "## 負重")
    pairs = {int(s): int(w) for s, w in re.findall(r"\| (\d+)(?: 以上)? \| (\d+) ", part)}
    assert pairs == stats.CARRY_BY_STR
    assert "×1.25" in part and stats.ORC_CARRY == 1.25
    assert "背包最多 35 件" in part and stats.CARRY_COUNT == 35


def test_wield_table_matches_the_manual():
    part = section(MANUAL.read_text(encoding="utf-8"), "## 武器重量限制")
    pairs = {int(s): int(w) for s, w in re.findall(r"\| (\d+)(?: 以上)? \| (\d+) ", part)}
    assert pairs == stats.WIELD_BY_STR
    assert "STR 8～16：就等於 STR" in part
    p = Player("p", None, None)
    for s, want in [(8, 8), (12, 12), (16, 16), (17, 22), (30, 85), (40, 85)]:
        p.primaries = {"str": s}
        assert stats.wield_limit(p) == want


def test_attack_names_match_the_manual():
    part = section(AREA_MANUAL.read_text(encoding="utf-8"), "### 武器的攻擊方式")
    pairs = {int(n): name for n, name in re.findall(r"\| (\d+) \| (\S+) ", part)}
    assert pairs == {int(a): name for a, name in ATTACK_NAMES.items()}
    assert set(ATTACK_NAMES) == set(Attack)


# ---- 屬性 ----

def test_primary_bundle_matches_mud_design(model):
    for guild in stats.Guild:
        for p in stats.PRIMARY_KEYS:
            for level in (1, 10, 50, 100):
                want = model.primary_bundle(str(guild), p, level)
                assert stats.primary_bundle(guild, p, level) == pytest.approx(want, rel=1e-9), (guild, p, level)


def test_gear_matches_apply_points(world, balance, model):
    # 主屬性用**裝備等級**換算：長劍（力量 +2）5 級、戒指（HP +5）8 級、皮甲（物理抗性 +3）10 級
    p = person(level=10)
    bare = dict(p.panel)
    e = balance.Entity("x", p.level, model.G(p.level), "phys", dict(bare), None)
    p.equipment = {"wield": make(2, 5), "finger_l": make(6, 8), "body": make(7, 10)}
    stats.recompute(p)
    for obj in p.equipment.values():
        for apply, n in obj.affects:
            key = apply.name.lower()
            price = model.primary_price(obj.level, key) if key in stats.PRIMARY_KEYS else model.prices[key]
            e = model.apply_points(e, {key: n * price}, obj.level)
    for key in stats.SECONDARY_KEYS:
        assert p.panel[key] == pytest.approx(e.stats[key], rel=1e-9), key
    assert p.panel["ac"] == pytest.approx(p.equipment["body"].base["ac"])      # AC 只有護具（戒指沒有基本值）
    assert (p.panel["mp"], p.panel["mv"]) == (bare["mp"], bare["mv"])             # MP、MV 只看角色自己的主屬性


def test_shield_and_armor_ac_add_up(world):
    p = person(level=5)
    give(p, 3, 7)
    say(p, "wear all")
    assert p.panel["ac"] == pytest.approx(p.equipment["offhand"].base["ac"] + p.equipment["body"].base["ac"])


def test_taking_gear_off_lowers_hp(world):
    p = person()
    give(p, 6)
    say(p, "wear ring")
    assert p.panel["hp"] == pytest.approx(person("Other").panel["hp"] + 5)
    p.hp = p.panel["hp"]
    say(p, "remove ring")
    assert p.hp == pytest.approx(p.panel["hp"])                                   # 夾在新上限，不會超過


def test_score_shows_primaries_with_gear(world):
    p = person()
    give(p, 2)
    say(p, "wear sword")
    assert "力量  14" in say(p, "score")                                            # 12 ＋ 長劍的 2
    assert p.primaries["str"] == 12 and stats.carry_limit(p) == 140                # 負重照舊看自己的


# ---- 戰鬥 ----

def wielding(*numbers, level=10):
    p = person(level=level)
    give(p, *numbers)
    say(p, "wear all")
    return p


def test_weapon_damage(world):
    # 拿武器：（傷害點數 ＋ 下限 ＋ (上限 − 下限) × 亂數）× 減傷 × 等級差，不再 ±20%
    p, dog = wielding(2), the_dog()
    sword = p.equipment["wield"]
    low, high = sword.base["dmg_min"], sword.base["dmg_max"]
    dmg, crit = damage.strike(p, dog, Always(0.5))
    assert not crit and dmg == pytest.approx(damage.per_hit(p, dog, "phys", low + (high - low) * 0.5))
    dmg, crit = damage.strike(p, dog, Always(0.0))                                 # 下限、爆擊
    assert crit and dmg == pytest.approx(damage.per_hit(p, dog, "phys", low) * damage.crit_mult(p))


def test_weapon_roll_takes_the_same_random_numbers(world):
    p, bare, dog = wielding(2), person("Bare", level=10), the_dog()
    armed, unarmed = Counting(), Counting()
    damage.strike(p, dog, armed)
    damage.strike(bare, dog, unarmed)
    assert armed.calls == unarmed.calls == 3                                       # 命中、武器值（或 ±20%）、爆擊


def test_dual_wield_attacks(world, balance, model):
    assert damage.DUAL_WIELD_MAIN == balance.DUAL_WIELD_MAIN
    assert damage.DUAL_OFFHAND == pytest.approx(model.dual_offhand_share, rel=1e-12)
    p = wielding(4, 2)
    a = damage.attacks_per_round(p)
    assert fight.attacks(p) == pytest.approx([a * 0.70, a * damage.DUAL_OFFHAND])
    assert fight.attacks(wielding(2)) == [damage.attacks_per_round(p)]             # 只有主手


def test_attack_messages_use_the_weapon(world, monkeypatch):
    monkeypatch.setattr(combat, "rng", Always(0.5))
    p, dog = wielding(4, 2), the_dog()

    async def main():
        f = fight.start_fight(p, dog)
        for _ in range(6):
            f.tick()
        return plain(p)

    text = asyncio.run(main())
    assert "你使用重砍攻擊野狗" in text and "你使用戳刺攻擊野狗" in text and "直拳" not in text


def entries(f, ch):
    return sorted((hand, t) for t, _seq, hand, c in f.queue if c is ch and f.joined.get(ch) == _seq)


def test_switching_weapons_mid_fight(world, monkeypatch):
    monkeypatch.setattr(combat, "rng", Always(0.99))                               # 都打不中：不會打死誰
    p, dog = wielding(2), the_dog()
    give(p, 4)

    async def main():
        f = fight.start_fight(p, dog)
        before = entries(f, p)
        say(p, "wear dagger")                                                      # 穿上副手武器：副手排在一次間隔之後
        after = entries(f, p)
        second = round(f.ticks + fight.ROUND_TICKS / fight.attacks(p)[1], 9)
        say(p, "remove dagger")                                                    # 再脫掉：那一下拿出來時丟掉，不會用空手多打
        for _ in range(12):
            f.tick()
        text = plain(p)
        return before, after, second, entries(f, p), f.armed[p], text

    before, after, second, end, armed, text = asyncio.run(main())
    assert before == [(0, 0)]
    assert after == [(0, 0), (1, second)]
    assert {hand for hand, _ in end} == {0} and armed == 1
    assert "你使用重砍攻擊野狗" in text and "戳刺" not in text and "直拳" not in text


# ---- 技能 ----

def test_skill_range_with_a_weapon(world):
    p = wielding(2)
    sword = p.equipment["wield"]
    dmg = p.panel["dmg_phys"]
    want = (stats.shown((dmg + sword.base["dmg_min"]) * 1.2), stats.shown((dmg + sword.base["dmg_max"]) * 1.2))
    assert skills.display_range(p, skills.SKILLS["smash"]) == want


@pytest.mark.parametrize("kinds, ok", [((WeaponKind.LONGSWORD,), True), ((WeaponKind.DAGGER,), False)])
def test_weapon_kinds_with_a_weapon(world, monkeypatch, kinds, ok):
    monkeypatch.setitem(skills.SKILLS, "smash", dataclasses.replace(skills.SKILLS["smash"], weapon_kinds=kinds))
    p = wielding(2)
    assert skills.weapon_ok(p, skills.SKILLS["smash"]) is ok
    bare = person("Bare")
    assert skills.weapon_ok(bare, skills.SKILLS["smash"]) is False                 # 空手不行
