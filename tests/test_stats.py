import random
from pathlib import Path

import pytest

from balance_loader import load_balance
from mud import equipment, stats
from mud.characters import Position
from mud.players import Player
from mud.stats import Guild, Race

MANUAL = Path(__file__).resolve().parent.parent / "docs" / "玩家角色手冊.md"
LEVELS = [1, 10, 50, 100]


@pytest.fixture(scope="module")
def balance():
    module = load_balance()
    if module is None:
        pytest.skip("找不到 mud_design/sim/balance.py")
    return module


@pytest.fixture(scope="module")
def model(balance):
    return balance.Model()


def manual_table(marker):
    """手冊裡 marker 後面的第一個表格，不含表頭。
    坑：有的表縮排在列點底下（每行開頭是空白），要先 lstrip 才認得出來。"""
    rows = []
    for line in MANUAL.read_text(encoding="utf-8").split(marker, 1)[1].splitlines():
        line = line.strip()
        if line.startswith("|"):
            rows.append([cell.strip() for cell in line.strip("|").split("|")])
        elif rows:
            break
    return rows[2:]


def test_races_match_manual():
    # 玩家角色手冊「種族」的表：種族、特色、STR、INT、WIS、CON、DEX（表裡只有中文名字，比 RACE_NAMES）
    want = [[stats.RACE_NAMES[r], stats.RACE_TRAITS[r], *(str(stats.RACE_PRIMARIES[r][p]) for p in stats.PRIMARY_KEYS)]
            for r in Race]
    assert manual_table("玩家有 6 個種族。") == want


def test_races_add_up_to_60_and_stay_in_8_to_16():
    for race, p in stats.RACE_PRIMARIES.items():
        assert sum(p.values()) == 60 and all(8 <= v <= 16 for v in p.values()), race


def test_guild_standards_match_manual():
    # 玩家角色手冊「公會」的標準主屬性表（縮排在列點底下），跟 equipment.py 主屬性單價用的創角標準一樣
    want = [[stats.GUILD_NAMES[g], *(str(equipment.PRIMARY_PRICE[g][p][1]) for p in stats.PRIMARY_KEYS)] for g in Guild]
    assert manual_table("公會的標準主屬性") == want


def test_races_match_mud_design(balance):
    names = {stats.RACE_NAMES[r]: r for r in Race}
    assert set(names) == set(balance.RACE_MODS)
    for zh, mods in balance.RACE_MODS.items():
        want = {p: balance.RACE_BASE + mods.get(p, 0) for p in balance.PRIMARY_KEYS}
        assert stats.RACE_PRIMARIES[names[zh]] == want, zh
        assert stats.RACE_TRAITS[names[zh]] == balance.RACE_TRAIT[zh]


def test_constants_match_mud_design(balance, model):
    # 參考值、切片權重（mana 我們叫 mp）、裸裝比例、MP／MV 的常數
    assert {k: model.b[k] for k in stats.REF} == pytest.approx(stats.REF)
    rename = {"mana": "mp"}
    assert {p: {rename.get(k, k): v for k, v in w.items()} for p, w in balance.SLICE_SEED.items()} == stats.SLICE_SEED
    assert 1 - model.cfg.gear_share == stats.NAKED_SHARE
    assert balance.NAKED_SHARE_OVERRIDE == {"res_dragon": 0.0}        # 龍焰抗性裸裝是 0
    assert model.cfg.resource_main_hp_ratio == stats.RESOURCE_MAIN_HP_RATIO
    assert model.cfg.resource_off_lv1_ratio == stats.RESOURCE_OFF_LV1_RATIO
    assert model.cfg.resource_off_max == stats.RESOURCE_OFF_MAX
    assert model.cfg.resource_roll == stats.RESOURCE_ROLL
    assert model.cfg.max_level == stats.MAX_LEVEL
    assert balance.PRIMARY_CAP == stats.PRIMARY_CAP                    # 角色自己的主屬性每項最高 55


def cases():
    """（等級、公會、主屬性）：人類、精靈、公會標準配點。"""
    for level in LEVELS:
        for guild in Guild:
            std = {p: equipment.standard_primary(guild, p, level) for p in stats.PRIMARY_KEYS}
            for primaries in (stats.RACE_PRIMARIES[Race.HUMAN], stats.RACE_PRIMARIES[Race.ELF], std):
                yield level, guild, primaries


@pytest.mark.parametrize("level, guild, primaries", list(cases()))
def test_naked_matches_mud_design(model, level, guild, primaries):
    # 設計文件 §8.1 末段的裸裝公式：跟 balance.py 的 naked_player 一樣
    want = model.naked_player(level, guild.value, primaries=primaries).stats
    assert stats.naked(level, primaries, guild) == pytest.approx({k: want[k] for k in stats.SECONDARY_KEYS})


@pytest.mark.parametrize("level, guild, primaries", list(cases()))
@pytest.mark.parametrize("roll", [0.95, 1.0, 1.05])
def test_resources_match_mud_design(model, level, guild, primaries, roll):
    want = model.resources(level, guild.value, primaries, roll)
    assert stats.resources(level, primaries, guild, roll) == pytest.approx({"mp": want["mana"], "mv": want["mv"]})


def test_resource_table_in_manual():
    # 玩家角色手冊 MP、MV 上限的數字表（公會標準配點、倍率 1）：等級、裸裝 HP、自己公會的資源、另一種
    for level, hp, main, off in manual_table("公會標準配點、倍率 1 時的數字"):
        level = int(level)
        std = {p: equipment.standard_primary(Guild.STAFF, p, level) for p in stats.PRIMARY_KEYS}
        got = stats.resources(level, std, Guild.STAFF, 1.0)
        assert [stats.naked(level, std, Guild.STAFF)["hp"], got["mp"], got["mv"]] == pytest.approx(
            [float(x.replace(",", "")) for x in (hp, main, off)], abs=0.5)


def test_roll_resources_is_within_5_percent():
    rng = random.Random(1)
    rolls = [stats.roll_resources(rng) for _ in range(1000)]
    assert 0.95 <= min(rolls) and max(rolls) <= 1.05


def test_recompute_fills_every_secondary_stat():
    p = Player("Vcx", None, None)
    p.race, p.guild, p.primaries, p.resource_roll = Race.ORC, Guild.SWORD, dict(stats.RACE_PRIMARIES[Race.ORC]), 1.02
    stats.recompute(p)
    assert set(p.panel) == {*stats.SECONDARY_KEYS, "mp", "mv", "ac"}
    assert p.panel["dmg_spell"] == p.panel["res_dragon"] == p.panel["ac"] == 0      # 劍之公會沒有法術傷害
    assert p.panel["mp"] > 0 and p.panel["mv"] > p.panel["mp"]                     # 兩種都有，自己公會的 MV 比較多


@pytest.mark.parametrize("position, rate", [
    (Position.STANDING, 0.10), (Position.RESTING, 0.20), (Position.SLEEPING, 0.30),
    (Position.FIGHTING, 0), (Position.STUNNED, 0),            # 戰鬥中不回；昏迷這些手冊沒寫，也不回
])
def test_regen_by_position(position, rate):
    p = Player("Vcx", None, None)
    p.race, p.guild, p.primaries = Race.HUMAN, Guild.SWORD, dict(stats.RACE_PRIMARIES[Race.HUMAN])
    stats.recompute(p)
    p.hp = p.mp = p.mv = 1.0
    p.position = position
    stats.regen(p)
    assert [p.hp, p.mp, p.mv] == pytest.approx([1 + p.panel[k] * rate for k in ("hp", "mp", "mv")])


def test_regen_stops_at_max():
    p = Player("Vcx", None, None)
    p.race, p.guild, p.primaries = Race.HUMAN, Guild.SWORD, dict(stats.RACE_PRIMARIES[Race.HUMAN])
    stats.recompute(p)
    p.hp, p.mp, p.mv = p.panel["hp"] - 1, p.panel["mp"], 0.0
    stats.regen(p)
    assert (p.hp, p.mp) == (p.panel["hp"], p.panel["mp"]) and p.mv == pytest.approx(p.panel["mv"] * 0.1)


# ---- 怪物（區域檔的生物）：跟 balance.py 的 Model.area_mob() 比對 ----

def test_mob_constants_match_mud_design(balance, model):
    assert {stats.MobTier(t).value: v["gear_fill"] for t, v in balance.MOB_TIERS.items()} == \
        {t.value: f for t, f in stats.MOB_TIER_FILL.items()}
    assert (model.cfg.mob_bonus_max, model.cfg.mob_bonus_curve, model.cfg.mob_bonus_applies_to) == \
        (stats.MOB_BONUS_MAX, stats.MOB_BONUS_CURVE, "gear")          # 進度加成只放大裝備那 25%
    assert model.base_per_G == pytest.approx(stats.BASE_PER_G)
    assert balance.ATTACK_MAIN_SHARE == stats.ATTACK_MAIN_SHARE and balance.ATTACK_TYPES == stats.ATTACK_TYPES
    assert balance.DEFENSE_RATIO == stats.DEFENSE_RATIO
    assert balance.ARCHETYPE_KEYS == stats.ARCHETYPE_KEYS and balance.ARCHETYPE_TILT == stats.ARCHETYPE_TILT
    assert {k: model.prices[k] for k in stats.PRICE if k in model.prices and k not in ("res_dragon", "none")} == \
        pytest.approx({k: v for k, v in stats.PRICE.items() if k in model.prices and k not in ("res_dragon", "none")})


ATTACKS = [None, "phys", "spell", "dragon", "dragon/phys", "phys/spell", "spell/dragon"]


@pytest.mark.parametrize("level", [1, 10, 50, 100])
@pytest.mark.parametrize("tier", ["trash", "normal", "elite", "boss"])
def test_mob_stats_match_mud_design(model, level, tier):
    # 每個等級、種類：7 種攻擊類型 × 3 種攻防傾向 × 5 種原型，全部屬性和攻擊類型比例都要一樣
    for attack in ATTACKS:
        for defense in (None, "phys", "spell"):
            for archetype in (None, "tank", "berserker", "agile", "extreme_tank"):
                want = model.area_mob(level, tier, attack, defense, archetype)
                panel, mix = stats.mob_stats(level, tier, attack, defense, archetype)
                rename = {"mana": "mp"}
                assert panel == pytest.approx({rename.get(k, k): v for k, v in want.stats.items()}), \
                    (level, tier, attack, defense, archetype)
                assert mix == pytest.approx(want.mix)

