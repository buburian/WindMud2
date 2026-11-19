"""測試用：直接讀 mud_design 的 sim/skill_tree.py（技能草案的資料），拿來比對技能的數字（test_skill_tree.py）。"""
import importlib.util
import sys
from pathlib import Path

SKILL_TREE = Path(__file__).resolve().parents[2] / "mud_design" / "sim" / "skill_tree.py"


def load_skill_tree():
    """載入 skill_tree.py；找不到 mud_design 是 None（呼叫的人跳過測試）。

    唯讀：不寫 .pyc，也不把 sim/ 加進 sys.path（它只有資料，不 import 別的檔）。讀得到卻載入失敗要讓測試失敗。
    """
    if not SKILL_TREE.exists():
        return None
    if "mud_design_skill_tree" in sys.modules:
        return sys.modules["mud_design_skill_tree"]
    old = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location("mud_design_skill_tree", SKILL_TREE)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    finally:
        sys.dont_write_bytecode = old
    return module
