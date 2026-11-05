"""help：只打 help 看分類和每一類的指令；help 分類 看這一類；help 指令 看說明（指令可以縮寫，規則跟打指令一樣）。

說明文字在 help/help.json（helps.py 讀檔、檢查）。標題後面的縮寫照指令表算，指令表改了也不會寫錯。
imm 的分類（管理員）只有 imm 看得到；不是 imm 也找不到 imm 指令的說明（跟打 imm 指令一樣）。
坑：commands/__init__.py import 這個模組，這裡又要用指令表，所以 command_name 在函式裡才 import。
"""
from .. import helps
from .system import pad, width

NOT_FOUND = "對不起，找不到相對應的說明。"     # 照 C 版


def do_help(ch, arg):
    """help [分類或指令]。"""
    is_imm = getattr(ch, "imm", False)
    words = arg.split()
    if not words:
        ch.send(summary(is_imm))
        return
    word = words[0]
    if any(c["name"] == word for c in visible(is_imm)):     # 分類名稱要整個字一樣
        ch.send(category(word))
        return
    entry = entry_of(word.lower(), is_imm)
    ch.send(detail(entry, is_imm) if entry else NOT_FOUND + "\n")


def visible(is_imm):
    """看得到的分類：imm 的分類只有 imm 看得到。"""
    return [c for c in helps.categories if is_imm or not c["imm"]]


def summary(is_imm):
    """只打 help：每個分類一行，後面是這一類的指令。"""
    cats = visible(is_imm)
    w = max(width(c["name"]) for c in cats)
    lines = ["說明的分類（help 分類 或 help 指令 看細節）："]
    for c in cats:
        names = [name for e in helps.entries if e["category"] == c["name"] for name in e["commands"]]
        lines.append(f"  {pad(c['name'], w)}  {' '.join(names)}")
    return "\n".join(lines) + "\n"


def category(name):
    """help 分類：這一類的每一筆說明，指令和一句話。"""
    rows = [(" ".join(e["commands"]), e["summary"]) for e in helps.entries if e["category"] == name]
    w = max(width(cmds) for cmds, _ in rows)
    return "\n".join([f"【{name}】", *(f"  {pad(cmds, w)}  {s}" for cmds, s in rows)]) + "\n"


def entry_of(word, is_imm):
    """word 當成指令找（跟打指令一樣：第一個用它開頭的），回傳那個指令的說明；找不到是 None。"""
    from . import command_name
    name = command_name(word, is_imm)
    return next((e for e in helps.entries if name in e["commands"]), None) if name else None


def detail(entry, is_imm):
    """help 指令：標題（用法＋縮寫）和說明。"""
    short = [s for s in (shortest(c, is_imm) for c in entry["commands"]) if s]
    title = entry["usage"] + (f"（縮寫 {' '.join(short)}）" if short else "")
    return "\n".join([title, *entry["text"]]) + "\n"


def shortest(cmd, is_imm):
    """cmd 最短的縮寫（照指令表的順序，打這幾個字就會找到它）；沒有比全名短的是 None。"""
    from . import command_name
    return next((cmd[:n] for n in range(1, len(cmd)) if command_name(cmd[:n], is_imm) == cmd), None)
