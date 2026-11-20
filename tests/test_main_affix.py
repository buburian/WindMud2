"""必出的主詞綴（物品的 main_affix，使用者 2026-11-19 定的，區域製作手冊「main_affix」）：
主詞綴不抽、拿 60%、名字最後是它；次詞綴、第三條不重複；橘色另外多拿總點數的 30%；買不起 1 點照舊抽；
沒寫的抽法和亂數一樣；做物品（objects.create）、商店的價錢、區域檔檢查。
"""
import random
from pathlib import Path

import pytest

from area_helpers import make_object
from mud import area, equipment, objects, zones
from mud.area import Apply

AREAS = Path(__file__).resolve().parent.parent / "areas"
SLOTS = ("wield", "offhand", "body", "head", equipment.TWO_HANDED, "finger")
COLORS = ("white", "blue", "purple", "orange")


def points(rolled, level):
    return sum(n * equipment.price(k, level) for k, n in rolled["affixes"].items())


def budget(slot, level, color):
    return equipment.cap(level, slot) * equipment.COLOR_BONUS[color]


@pytest.mark.parametrize("forced", ["str", "hp", "dmg_phys", "res_spell"])
def test_the_main_affix_is_always_it(forced):
    for seed in range(40):
        for slot in SLOTS:
            for level in (20, 60, 100):
                color = COLORS[seed % 4]
                rolled = equipment.roll_item(slot, level, color, random.Random(seed), forced=forced)
                main_share = budget(slot, level, color) * equipment.AFFIX_SPLIT[0]
                if equipment.price(forced, level) > budget(slot, level, color) * (1.3 if color == "orange" else 1):
                    continue                                        # 全部點數也買不起 1 點：照舊抽（下面另外測）
                assert rolled["name"].endswith(equipment.AFFIX_WORD[forced]), (seed, slot, level)
                assert rolled["affixes"][forced] * equipment.price(forced, level) >= main_share - equipment.price(forced, level)
                others = [w for w in rolled["name"].split("之")[:-1]]
                assert equipment.AFFIX_WORD[forced] not in others          # 次詞綴不會跟它一樣


def test_orange_gets_30_percent_more():
    for seed in range(30):
        for slot in SLOTS:
            level = 50
            full = budget(slot, level, "orange")
            plain = points(equipment.roll_item(slot, level, "orange", random.Random(seed)), level)
            forced = points(equipment.roll_item(slot, level, "orange", random.Random(seed), forced="hp"), level)
            assert full - 1 < plain <= full + 1e-9                       # 一般的橘色：用滿上限
            assert full * 1.3 - 1 < forced <= full * 1.3 + 1e-9          # 必出的橘色：130%
            purple = points(equipment.roll_item(slot, level, "purple", random.Random(seed), forced="hp"), level)
            assert purple <= budget(slot, level, "purple") + 1e-9        # 其他顏色沒有多


@pytest.mark.parametrize("forced", ["hp", "str", "dmg_phys"])
def test_orange_extra_goes_to_the_main_affix(forced):
    # 力量、傷害不是補零頭的屬性（1 點 ＝ 1 單位的），多的 30% 要真的加在它身上，不是變成零頭
    level, full = 50, budget("body", 50, "orange")
    for seed in range(10):
        rolled = equipment.roll_item("body", level, "orange", random.Random(seed), forced=forced)
        want = full * (equipment.AFFIX_SPLIT[0] + equipment.MAIN_AFFIX_BONUS)
        assert rolled["affixes"][forced] * equipment.price(forced, level) > want - equipment.price(forced, level)


def test_too_little_for_60_percent_gets_it_all():
    # 60% 買不起 1 點、全部買得起（小件裝備的主屬性）：全部點數都給它，沒有次詞綴、第三條（使用者選的）
    cases = [(slot, level) for slot in ("finger", "neck", "waist") for level in range(1, 101)
             if budget(slot, level, "white") * 0.6 < equipment.price("str", level) <= budget(slot, level, "white")]
    assert cases
    for slot, level in cases[:20]:
        rolled = equipment.roll_item(slot, level, "white", random.Random(level), forced="str")
        assert rolled["name"] == "蠻力" and rolled["affixes"]["str"] == int(budget(slot, level, "white") // equipment.price("str", level))
        assert set(rolled["affixes"]) <= {"str"} | {k for k in equipment.AFFIX_WORD if abs(equipment.price(k, level) - 1) < 1e-6}


def test_too_poor_to_afford_it_rolls_as_usual():
    # 1 級的戒指（上限的一半）白色：主詞綴的 60% 買不起 1 點力量（1 級 3.74 點）
    slot, level = "finger", 1
    assert equipment.price("str", level) > budget(slot, level, "white") * equipment.AFFIX_SPLIT[0]
    for seed in range(10):
        assert (equipment.roll_item(slot, level, "white", random.Random(seed), forced="str")
                == equipment.roll_item(slot, level, "white", random.Random(seed)))


def test_without_it_nothing_changes():
    for seed in range(20):
        for slot in SLOTS:
            assert (equipment.roll_item(slot, 40, "orange", random.Random(seed), forced=None)
                    == equipment.roll_item(slot, 40, "orange", random.Random(seed)))


# ---- 做物品、商店 ----

@pytest.fixture
def test_area():
    zones.load(AREAS)
    yield
    zones.stop()


def test_create_uses_the_area_file(test_area):
    assert objects.protos[105]["main_affix"] == "hp"                 # test.json 的測試盾牌
    for seed in range(10):
        shield = objects.create(105, 30, "orange", random.Random(seed))
        assert shield.main_affix == "hp" and shield.name.endswith("活力測試盾牌")
        assert dict(shield.affects)[Apply.HP] > 0
    assert objects.create(109, 30, "orange", random.Random(1)).main_affix is None


def test_shop_price_counts_the_extra(test_area):
    shield = objects.create(105, 30, "orange", for_sale=True)
    full = budget(shield.slot, 30, "orange")
    assert objects.full_price(shield, 30) == objects.gear_price(full * 1.3, 30)
    shield = objects.create(105, 30, "purple", for_sale=True)
    assert objects.full_price(shield, 30) == objects.gear_price(budget(shield.slot, 30, "purple"), 30)


# ---- 區域檔檢查 ----

def random_gear(**changes):
    o = make_object(101)
    o.update(affects=[], **changes)
    return o


@pytest.mark.parametrize("o, want", [
    (random_gear(main_affix="hp"), None),
    (random_gear(main_affix="res_dragon"), "main_affix 要寫 str、int"),
    (random_gear(main_affix=3), "不能是 3"),
    (make_object(101) | {"main_affix": "hp"}, "寫了 affects 是固定裝備"),
    (random_gear(item_type=8, wear_flags=1, values=[0, 0, 0, 0], main_affix="hp"), "沒有穿戴部位、不是裝備"),
    (random_gear(item_type=8, wear_flags="1|16384", values=[0, 0, 0, 0], main_affix="hp"), "這個部位沒有點數"),
])
def test_area_check(o, want):
    problems = []
    area.check_object("物品 101", o, problems)
    if want is None:
        assert problems == []
    else:
        assert len(problems) == 1 and want in problems[0], problems
