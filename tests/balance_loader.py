"""測試用：直接讀 mud_design 的 sim/balance.py，拿來比對數字（test_equipment.py、test_stats.py）。"""
import importlib.util
import sys
from pathlib import Path

BALANCE = Path(__file__).resolve().parents[2] / "mud_design" / "sim" / "balance.py"


def load_balance():
    """載入 balance.py；找不到 mud_design 是 None（呼叫的人跳過測試）。

    唯讀：不寫 .pyc，也不把 sim/ 加進 sys.path。讀得到卻載入失敗要讓測試失敗，不然數字不同步也看不出來。
    """
    if not BALANCE.exists():
        return None
    if "mud_design_balance" in sys.modules:
        return sys.modules["mud_design_balance"]
    old = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location("mud_design_balance", BALANCE)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module             # dataclass 要從 sys.modules 找到自己的模組
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    finally:
        sys.dont_write_bytecode = old
    return module
