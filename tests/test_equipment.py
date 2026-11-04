import importlib.util
import sys
from pathlib import Path

import pytest

from mud import equipment

BALANCE = Path(__file__).resolve().parents[2] / "mud_design" / "sim" / "balance.py"

# balance.py 的部位名稱 → 我們的部位代號
SLOT_KEYS = {
    "主手 wield": "wield", "副手 offhand": "offhand", "身體 body": "body", "頭 head": "head", "腿 legs": "legs",
    "手臂 arms": "arms", "手 hands": "hands", "腳 feet": "feet", "披風 about": "about", "腰 waist": "waist",
    "頸 neck": "neck", "手腕 wrist": "wrist", "戒指 finger×2": "finger", "持握 hold": "hold", "光源 light": "light",
}
COLOR_KEYS = {"灰": "gray", "白": "white", "藍": "blue", "紫": "purple", "橘": "orange"}


@pytest.fixture(scope="module")
def balance():
    """直接讀 mud_design 的 balance.py（唯讀：不寫 .pyc，也不把 sim/ 加進 sys.path）。

    只有找不到 mud_design 才跳過；讀得到卻載入失敗要讓測試失敗，不然數字不同步也看不出來。
    """
    if not BALANCE.exists():
        pytest.skip("找不到 mud_design/sim/balance.py")
    old = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location("mud_design_balance", BALANCE)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module             # dataclass 要從 sys.modules 找到自己的模組
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = old
    return module


@pytest.mark.parametrize("level", [1, 50, 100])
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


def test_design_doc_examples():
    # 設計文件 §3.3：1 級頭盔上限約 5.7、主手約 14.3；§3.2：1 級 STR +1 約 3.7 點、10 級約 5.7 點
    assert equipment.slot_cap(1, "head") == pytest.approx(5.73, abs=0.01)
    assert equipment.slot_cap(1, "wield") == pytest.approx(14.33, abs=0.01)
    assert equipment.price("str", 1) == pytest.approx(3.74, abs=0.01)
    assert equipment.price("str", 10) == pytest.approx(5.7, abs=0.05)
    assert equipment.price("dmg_phys", 50) == 10


def test_item_cap():
    wield, offhand = equipment.slot_cap(5, "wield"), equipment.slot_cap(5, "offhand")
    assert equipment.item_cap(5, ["wield"], two_handed=True) == (pytest.approx(wield + offhand), "主手＋副手（雙手）")
    assert equipment.item_cap(5, ["head"], two_handed=True) == (pytest.approx(equipment.slot_cap(5, "head")), "頭")
    assert equipment.item_cap(5, ["head", "body"]) == (pytest.approx(equipment.slot_cap(5, "body")), "身體")   # 用大的
    assert equipment.item_cap(5, []) == (0.0, "（沒有穿戴部位）")
    assert equipment.slot_cap(5, "finger") == pytest.approx(equipment.slot_cap(5, "wrist") / 2)   # 戒指一件是一半
