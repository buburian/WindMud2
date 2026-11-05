"""help 指令的說明檔（config.HELP_FILE，help/help.json）：讀檔、檢查。指令本身在 commands/help.py。

格式（檔案本身就是例子）：
- categories：[{"name": 分類名稱, "imm": 是不是只有 imm 看得到}]，順序就是 help 畫面的順序。
- entries：[{"category": 分類, "commands": [這筆說明的指令，一筆可以好幾個], "usage": 標題（用法）,
  "summary": 分類畫面裡的一句話, "text": [說明，一行一個字串]}]。
標題後面的「（縮寫 k）」由程式照指令表算，不寫在檔案裡。
規則只有一份：check()，開機（load）和測試都用它。每個指令都要剛好有一筆說明，所以新增指令沒寫說明就開不了機。
"""
import json
from pathlib import Path

from .config import ENCODING

TOP_KEYS = {"categories": list, "entries": list}
CATEGORY_KEYS = {"name": str, "imm": bool}
ENTRY_KEYS = {"category": str, "commands": list, "usage": str, "summary": str, "text": list}
TYPE_NAMES = {str: "要是文字", bool: "要寫 true 或 false", list: "要是清單（[…]）"}

categories = []     # 載入的分類（照檔案的順序）
entries = []        # 載入的說明


def load(path):
    """讀說明檔、檢查。有問題就 ValueError（第一個問題加總數），原本載入的不動。"""
    from .commands import COMMANDS, IMM_COMMANDS    # 坑：commands 會 import 回這裡（commands/help.py），要在函式裡才 import
    global categories, entries
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError:
        raise ValueError(f"讀不到說明檔 {path}") from None
    except json.JSONDecodeError as e:
        raise ValueError(f"{path} 不是正確的 JSON：第 {e.lineno} 行第 {e.colno} 個字") from None
    problems = check(data, [c for c, _, _ in COMMANDS], [c for c, _, _ in IMM_COMMANDS])
    if problems:
        raise ValueError(f"{path}：{problems[0]}（共 {len(problems)} 個問題）")
    categories, entries = data["categories"], data["entries"]


def check(data, commands, imm_commands):
    """檢查說明檔的內容，回傳全部的問題（空的就是沒問題）。commands、imm_commands 是指令表裡的指令名稱。"""
    problems = []
    if not _fields("檔案最上層", data, TOP_KEYS, problems):
        return problems
    imm_of = {}                                 # 分類名稱 → 是不是 imm 的分類
    for i, c in enumerate(data["categories"], 1):
        where = f"categories 第 {i} 筆"
        if not _fields(where, c, CATEGORY_KEYS, problems):
            continue
        if c["name"] in imm_of:
            problems.append(f"{where}：分類「{c['name']}」重複了")
        imm_of[c["name"]] = c["imm"]
        _big5(where, c["name"], problems)
    seen = {}                                   # 指令 → 寫在第幾筆
    used = set()                                # 有說明的分類
    for i, e in enumerate(data["entries"], 1):
        where = f"entries 第 {i} 筆"
        if not _fields(where, e, ENTRY_KEYS, problems):
            continue
        if not all(isinstance(t, str) for t in e["commands"] + e["text"]):
            problems.append(f"{where}：commands、text 裡面要都是文字")
            continue
        if not e["commands"]:
            problems.append(f"{where}：commands 是空的，要寫這筆說明的是哪些指令")
            continue
        where = f"entries 第 {i} 筆（{' '.join(e['commands'])}）"
        if e["category"] not in imm_of:
            problems.append(f"{where}：沒有「{e['category']}」這個分類（categories 裡有：{'、'.join(imm_of)}）")
        used.add(e["category"])
        for cmd in e["commands"]:
            if cmd not in commands and cmd not in imm_commands:
                problems.append(f"{where}：沒有 {cmd} 這個指令")
            elif cmd in seen:
                problems.append(f"{where}：{cmd} 已經寫在 entries 第 {seen[cmd]} 筆了")
            else:
                seen[cmd] = i
                is_imm = cmd in imm_commands
                if e["category"] in imm_of and imm_of[e["category"]] != is_imm:
                    problems.append(f"{where}：{cmd} 是{' imm 指令，要放在 imm 的分類' if is_imm else '一般指令，不能放在 imm 的分類'}"
                                    f"（「{e['category']}」的 imm 是 {str(imm_of[e['category']]).lower()}）")
        for text in (e["usage"], e["summary"], *e["text"]):
            _big5(where, text, problems)
    for name in imm_of:
        if name not in used:
            problems.append(f"分類「{name}」沒有任何說明")
    missing = [c for c in (*commands, *imm_commands) if c not in seen]
    if missing:
        problems.append(f"{'、'.join(missing)} 沒有說明")
    return problems


def _fields(where, item, keys, problems):
    """item 要是物件、欄位剛好是 keys、型別對。回傳能不能往下檢查。"""
    if not isinstance(item, dict):
        problems.append(f"{where} 要是一個物件（{{…}}），現在是 {json.dumps(item, ensure_ascii=False)}")
        return False
    missing, extra = [k for k in keys if k not in item], [k for k in item if k not in keys]
    if missing:
        problems.append(f"{where} 少了欄位：{'、'.join(missing)}")
    if extra:
        problems.append(f"{where} 多了欄位：{'、'.join(extra)}（只能有 {'、'.join(keys)}）")
    ok = not missing
    for k, t in keys.items():
        if k in item and not isinstance(item[k], t):
            problems.append(f"{where} 的 {k} {TYPE_NAMES[t]}，現在是 {json.dumps(item[k], ensure_ascii=False)}")
            ok = False
    return ok


def _big5(where, text, problems):
    """text 的每個字都要轉得成 Big5：轉不過去的字，玩家的畫面會顯示不出來。"""
    for ch in dict.fromkeys(text):
        try:
            ch.encode(ENCODING)
        except UnicodeEncodeError:
            problems.append(f"{where}：「{ch}」（U+{ord(ch):04X}）轉不成 Big5，玩家看不到這個字：{text}")
