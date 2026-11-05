import random

import pytest

from balance_loader import load_balance
from mud import equipment

# balance.py 的部位名稱 → 我們的部位代號
SLOT_KEYS = {
    "主手 wield": "wield", "副手 offhand": "offhand", "身體 body": "body", "頭 head": "head", "腿 legs": "legs",
    "手臂 arms": "arms", "手 hands": "hands", "腳 feet": "feet", "披風 about": "about", "腰 waist": "waist",
    "頸 neck": "neck", "手腕 wrist": "wrist", "戒指 finger×2": "finger", "持握 hold": "hold", "光源 light": "light",
}
COLOR_KEYS = {"灰": "gray", "白": "white", "藍": "blue", "紫": "purple", "橘": "orange"}


@pytest.fixture(scope="module")
def balance():
    module = load_balance()
    if module is None:
        pytest.skip("找不到 mud_design/sim/balance.py")
    return module


@pytest.mark.parametrize("level", [-100, -50, 0, 1, 10, 50, 100])   # 低於 1 級：很低等的怪物也會掉裝備
def test_numbers_match_mud_design(balance, level):
    # 設計文件改了數字，這裡會失敗，提醒要一起改 equipment.py
    m = balance.Model()
    assert equipment.G(level) == pytest.approx(m.G(level))
    for name, slot in SLOT_KEYS.items():
        assert equipment.slot_cap(level, slot) == pytest.approx(m.item_cap(level, name)), slot
    for p in balance.PRIMARY_KEYS:
        assert equipment.price(p, level) == pytest.approx(m.primary_price(level, p)), p
    for stat, value in equipment.SECONDARY_PRICE.items():
        if stat == "none":
            continue
        # 龍焰抗性不算裝備點數（設計文件 §5.5）：balance.py 的單價是 1，我們是 0
        want = 0.0 if stat == "res_dragon" else m.prices[stat]
        assert value == pytest.approx(want), stat
    assert {COLOR_KEYS[k]: v["points"] for k, v in balance.RARITY.items()} == equipment.COLOR_BONUS


def test_primary_standards_match_mud_design(balance):
    # 主屬性單價用的標準值、升級點數的比例、每級點數，跟 balance.py 一樣
    m = balance.Model()
    assert equipment.POINTS_PER_LEVEL == balance.PRIMARY_POINTS_PER_LEVEL
    for job, stats in equipment.PRIMARY_PRICE.items():
        for p, (_, std1, share) in stats.items():
            assert std1 == m.std_primaries[job][p], (job, p)
            assert share == pytest.approx(m.primary_share[job][p]), (job, p)


def test_design_doc_examples():
    # 設計文件 §3.3：1 級頭盔上限約 5.7、主手約 14.3；§3.2 的表：STR +1 是 3.7、4.9（10 級）、138.3（100 級）點
    assert equipment.slot_cap(1, "head") == pytest.approx(5.73, abs=0.01)
    assert equipment.slot_cap(1, "wield") == pytest.approx(14.33, abs=0.01)
    assert equipment.price("str", 1) == pytest.approx(3.74, abs=0.01)
    assert equipment.price("str", 10) == pytest.approx(4.9, abs=0.05)
    assert equipment.price("str", 100) == pytest.approx(138.3, abs=0.05)
    assert equipment.price("wis", 100) == pytest.approx(121.8, abs=0.05)
    assert equipment.price("con", 100) == pytest.approx(149.9, abs=0.05)
    assert equipment.price("dmg_phys", 50) == 10


def test_item_cap():
    wield, offhand = equipment.slot_cap(5, "wield"), equipment.slot_cap(5, "offhand")
    assert equipment.item_cap(5, ["wield"], two_handed=True) == (pytest.approx(wield + offhand), "主手＋副手（雙手）")
    assert equipment.item_cap(5, ["head"], two_handed=True) == (pytest.approx(equipment.slot_cap(5, "head")), "頭")
    assert equipment.item_cap(5, ["head", "body"]) == (pytest.approx(equipment.slot_cap(5, "body")), "身體")   # 用大的
    assert equipment.item_cap(5, []) == (0.0, "（沒有穿戴部位）")
    assert equipment.slot_cap(5, "finger") == pytest.approx(equipment.slot_cap(5, "wrist") / 2)   # 戒指一件是一半


# ---- 隨機裝備（設計文件 §3.3）----

def test_random_item_numbers_match_mud_design(balance):
    m = balance.Model()
    assert equipment.WPN_PER_G == m.base_per_G["wpn"]
    assert equipment.ARMOR_AC == m.cfg.armor_ac
    assert equipment.TWO_HANDED_WPN_MULT == pytest.approx(m.two_handed_wpn_mult)
    assert equipment.WEAPON_SPREAD == balance.WEAPON_SPREAD
    assert list(equipment.AFFIX_WORD.items()) == list(balance.AFFIX_WORD.items())    # 順序也要一樣：rng.choice 照順序挑
    assert (equipment.AFFIX_SPLIT, equipment.AFFIX_THIRD_CHANCE) == (balance.AFFIX_SPLIT, balance.AFFIX_THIRD_CHANCE)
    assert equipment.ARMOR_SLOTS == tuple(SLOT_KEYS[s] for s in balance.ARMOR_SLOTS)


# 等級只用 test_numbers_match_mud_design 比過單價的：「買得起」和取整卡在邊界上，單價差一點點就會抽到不同的詞綴
@pytest.mark.parametrize("level", [1, 10, 50, 100])
def test_roll_item_matches_mud_design(balance, level):
    # 同一個種子，結果要跟 balance.py 的 roll_item 一模一樣（遊戲直接照它的規則做）
    m = balance.Model()
    slots = [(name, slot, False) for name, slot in SLOT_KEYS.items()]
    slots += [(balance.TWO_HANDED_SLOT, equipment.TWO_HANDED, False), ("副手 offhand", "offhand", True)]
    for seed in range(40):
        for name, slot, offhand_weapon in slots:
            for rarity, color in COLOR_KEYS.items():
                want = m.roll_item(name, level, rarity, random.Random(seed), offhand_weapon=offhand_weapon)
                got = equipment.roll_item(slot, level, color, random.Random(seed), offhand_weapon)
                where = (seed, slot, offhand_weapon, color)
                assert (got["name"], got["affixes"]) == (want["name"], want["affixes"]), where
                assert got["base"] == pytest.approx(want["base"], rel=1e-9), where


def test_no_color_rolls_like_gray():
    assert equipment.roll_item("head", 10, None, random.Random(1)) == equipment.roll_item("head", 10, "gray", random.Random(1))
    assert equipment.roll_item("head", 10, None, random.Random(1))["affixes"] == {}
