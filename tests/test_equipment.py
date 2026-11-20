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


@pytest.mark.parametrize("level", [1, 5, 30, 100])
def test_main_affix_matches_mud_design(balance, level):
    # 必出的主詞綴（main_affix）：balance.py 的 roll_item 也有，同一個種子結果要一樣（含 60% 買不起、全部點數給它的情況）
    m = balance.Model()
    assert balance.MAIN_AFFIX_BONUS == equipment.MAIN_AFFIX_BONUS
    slots = [(name, slot, False) for name, slot in SLOT_KEYS.items() if equipment.cap(1, slot) > 0]   # 持握、光源沒有點數，不能寫
    slots += [(balance.TWO_HANDED_SLOT, equipment.TWO_HANDED, False), ("副手 offhand", "offhand", True)]
    for forced in ("str", "dmg_phys", "hp", "speed"):
        for seed in range(10):
            for name, slot, offhand_weapon in slots:
                for rarity, color in COLOR_KEYS.items():
                    want = m.roll_item(name, level, rarity, random.Random(seed), offhand_weapon=offhand_weapon, main_affix=forced)
                    got = equipment.roll_item(slot, level, color, random.Random(seed), offhand_weapon, forced)
                    assert (got["name"], got["affixes"]) == (want["name"], want["affixes"]), (forced, seed, slot, color)


def test_no_color_rolls_like_gray():
    assert equipment.roll_item("head", 10, None, random.Random(1)) == equipment.roll_item("head", 10, "gray", random.Random(1))
    assert equipment.roll_item("head", 10, None, random.Random(1))["affixes"] == {}


# ---- 淬火石（設計文件 §3.11，照 balance.py 的 Model.temper_item）----

@pytest.mark.parametrize("old_level, new_level", [(1, 15), (11, 15), (20, 20), (30, 60), (5, 100)])
def test_temper_matches_mud_design(balance, old_level, new_level):
    # 同一個種子做出來的裝備，淬火後的屬性、武器傷害、AC 要跟 balance.py 一樣（各部位、顏色、有沒有必出主詞綴）
    m = balance.Model()
    assert (balance.TEMPER_RARITY, equipment.TEMPER_COLOR) in COLOR_KEYS.items()
    slots = [(name, slot, False) for name, slot in SLOT_KEYS.items() if equipment.cap(1, slot) > 0]
    slots += [(balance.TWO_HANDED_SLOT, equipment.TWO_HANDED, False), ("副手 offhand", "offhand", True)]
    checked = 0
    for forced in (None, "str", "hp"):
        for seed in range(12):
            for name, slot, offhand_weapon in slots:
                for rarity, color in COLOR_KEYS.items():
                    item = m.roll_item(name, old_level, rarity, random.Random(seed), offhand_weapon=offhand_weapon, main_affix=forced)
                    got = equipment.roll_item(slot, old_level, color, random.Random(seed), offhand_weapon, forced)
                    try:
                        want = m.temper_item(item, new_level)
                    except ValueError:
                        with pytest.raises(ValueError):
                            equipment.temper(list(got["affixes"].items()), got["base"], slot, old_level, color, new_level, forced)
                        continue
                    affixes, base = equipment.temper(list(got["affixes"].items()), got["base"], slot, old_level, color, new_level, forced)
                    where = (forced, seed, slot, color)
                    assert dict(affixes) == want["affixes"] and [k for k, _ in affixes] == list(got["affixes"]), where
                    assert base == pytest.approx(want["base"], rel=1e-9), where
                    checked += 1
    assert checked > 100


def test_temper_example_from_the_design_document():
    # 設計文件 §3.11 的例子：Lv11 白色手套（攻速 +3、命中 +1、HP +1，random.Random(7)）淬火到 Lv15 → 橘色 攻速 +7、命中 +1、HP +1
    got = equipment.roll_item("hands", 11, "white", random.Random(7))
    assert got["affixes"] == {"speed": 3, "hit": 1, "hp": 1}
    affixes, base = equipment.temper(list(got["affixes"].items()), got["base"], "hands", 11, "white", 15)
    assert affixes == [("speed", 7), ("hit", 1), ("hp", 1)]
    assert base == {"ac": equipment.cap(15, "hands") * equipment.ARMOR_AC}


def test_temper_keeps_dragon_resistance():
    # 固定裝備的龍焰抗性不算點數：原樣留著、不參加分配；只有它的不能淬火
    affixes, _ = equipment.temper([("hp", 5), ("res_dragon", 25)], {}, "neck", 10, "blue", 20)
    assert affixes[1] == ("res_dragon", 25) and affixes[0][1] > 5
    with pytest.raises(ValueError):
        equipment.temper([("res_dragon", 25)], {}, "neck", 10, "blue", 20)


@pytest.mark.parametrize("affixes, slot, old_level, color, level", [
    ([("hp", 5)], "head", 10, "gray", 20),                          # 灰色
    ([], "head", 10, "white", 20),                                  # 沒有屬性
    ([("hp", 5)], "hold", 10, "white", 20),                         # 持握沒有點數
    ([("hp", 5)], "head", 30, "white", 20),                         # 等級比玩家高
    ([("hp", 5)], "head", 20, "orange", 20),                        # 已經是這個等級的橘色
    ([("hp", -2)], "head", 10, "white", 20),                        # 固定裝備的負數屬性
])
def test_temper_refuses(affixes, slot, old_level, color, level):
    with pytest.raises(ValueError):
        equipment.temper(affixes, {}, slot, old_level, color, level)
