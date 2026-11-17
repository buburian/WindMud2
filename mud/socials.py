"""表情動作（socials）和說話結尾的表情：讀檔、檢查、找。指令在 commands/social.py。

使用者要的：獨立一個 JSON 檔方便修改（config.SOCIAL_FILE，socials/socials.json），內容是 C 版的 SOCIALS.TXT 和 act_comm.c 的 expression()。
格式（檔案本身就是例子）：
- expressions：[{"ending": 說的話最後一兩個字, "adverb": 加在動詞前面的字}]。say、chat、tell、reply 的話用它結尾就變成
  「你愉快地說：『…:)』」（照 C 版）。先比兩個字的，再比一個字的。
- socials：[{"name": 英文名字（小寫字母）, "alone": 沒有對象, "target": 對別人, "self": 對自己}]，照順序比對縮寫（打開頭就行）。
  - alone、self：{"you": 自己看到的, "room": 同房間的人看到的}
  - target：{"you": 自己看到的, "room": 旁人看到的, "target": 對方看到的}
  - 文字用 act 的代換碼：$n 自己、$N 對方，$e $m $s（$E $M $S）是他／她／它；可以用顏色代碼。
    alone 沒有對方，不能用 $N $E $M $S；self 的對方就是自己（照 C 版）。
    寫 "" 是不送。
規則只有一份：check()，開機（load）和測試都用它。
"""
import json
import re
from pathlib import Path

from .config import ENCODING

TOP_KEYS = {"expressions", "socials"}
EXPRESSION_KEYS = {"ending", "adverb"}
SOCIAL_KEYS = {"name", "alone", "target", "self"}
PART_KEYS = {"alone": {"you", "room"}, "target": {"you", "room", "target"}, "self": {"you", "room"}}
CODES = set("neEmMsSN")                     # act 的代換碼（$t、$T 帶進來的文字 socials 用不到）
TARGET_CODES = set("NEMS")                  # 對方的碼：alone 不能用
NAME = re.compile(r"[a-z]+")

expressions = []    # 載入的 expressions（兩個字的在前面）
table = []          # 載入的 socials（照檔案的順序）


def load(path, commands=None):
    """讀檔、檢查。有問題就 ValueError（第一個問題加總數），原本載入的不動。commands 是全部的指令名稱（預設照指令表）。"""
    global expressions, table
    if commands is None:
        from .commands import COMMANDS, IMM_COMMANDS    # 坑：commands 會 import commands/social.py，要在函式裡才 import
        commands = [c for c, _, _ in COMMANDS + IMM_COMMANDS]
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError:
        raise ValueError(f"讀不到表情動作的檔案 {path}") from None
    except json.JSONDecodeError as e:
        raise ValueError(f"{path} 不是正確的 JSON：第 {e.lineno} 行第 {e.colno} 個字") from None
    problems = check(data, commands)
    if problems:
        raise ValueError(f"{path}：{problems[0]}（共 {len(problems)} 個問題）")
    expressions = sorted(data["expressions"], key=lambda e: -len(e["ending"]))
    table = data["socials"]


def check(data, commands):
    """檢查檔案的內容，回傳全部的問題（空的就是沒問題）。commands 是指令名稱：跟指令撞名、或打全名會先找到指令的 social 用不到。"""
    problems = []
    if not _keys("檔案最上層", data, TOP_KEYS, problems):
        return problems
    if not isinstance(data["expressions"], list) or not isinstance(data["socials"], list):
        return problems + ["expressions、socials 要是清單（[…]）"]
    endings = set()
    for i, e in enumerate(data["expressions"], 1):
        where = f"expressions 第 {i} 筆"
        if not _keys(where, e, EXPRESSION_KEYS, problems):
            continue
        ending, adverb = e["ending"], e["adverb"]
        if not (isinstance(ending, str) and ending.isascii() and 1 <= len(ending) <= 2 and ending.strip() == ending):
            problems.append(f"{where}：ending 要是 1～2 個英文字母或符號，不能是 {ending!r}")
        elif ending in endings:
            problems.append(f"{where}：ending {ending!r} 重複了")
        endings.add(ending)
        if not isinstance(adverb, str) or not adverb or "$" in adverb or "{" in adverb:
            problems.append(f"{where}：adverb 要是文字（不能有 $ 和 {{），不能是 {adverb!r}")
        else:
            _big5(where, adverb, problems)
    names = set()
    for i, s in enumerate(data["socials"], 1):
        where = f"socials 第 {i} 筆"
        if not _keys(where, s, SOCIAL_KEYS, problems):
            continue
        name = s["name"]
        if not (isinstance(name, str) and NAME.fullmatch(name)):
            problems.append(f"{where}：name 只能用小寫英文字母，不能是 {name!r}")
        else:
            where = f"socials 第 {i} 筆（{name}）"
            if name in names:
                problems.append(f"{where}：name 重複了")
            names.add(name)
            hit = next((c for c in commands if c.startswith(name)), None)
            if hit is not None:
                problems.append(f"{where}：打 {name} 會先找到指令 {hit}，這個動作用不到")
        for part, keys in PART_KEYS.items():
            if not _keys(f"{where}的 {part}", s[part], keys, problems):
                continue
            for key in sorted(keys):
                _text(f"{where}的 {part}.{key}", s[part][key], part == "alone", problems)
    return problems


def _keys(where, value, keys, problems):
    if not isinstance(value, dict):
        problems.append(f"{where}：要是 {{…}}")
        return False
    missing, extra = keys - set(value), set(value) - keys
    if missing:
        problems.append(f"{where}：少了 {'、'.join(sorted(missing))}")
    if extra:
        problems.append(f"{where}：多了不認得的 {'、'.join(sorted(extra))}")
    return not missing and not extra


def _text(where, text, alone, problems):
    if not isinstance(text, str):
        problems.append(f"{where}：要是文字")
        return
    for code in re.findall(r"\$(.?)", text):
        if code not in CODES:
            problems.append(f"{where}：不認得的代換碼 ${code}（只能用 $n $N $e $E $m $M $s $S）")
        elif alone and code in TARGET_CODES:
            problems.append(f"{where}：沒有對方，不能用 ${code}")
    _big5(where, text, problems)


def _big5(where, text, problems):
    try:
        text.encode(ENCODING)
    except UnicodeEncodeError as e:
        problems.append(f"{where}：有轉不成 Big5 的字 {text[e.start]!r}")


def find(word):
    """打 word 會做哪個動作：第一個用 word 開頭的（照檔案的順序，照 C 版），沒有是 None。"""
    return next((s for s in table if s["name"].startswith(word)), None) if word else None


def adverb(text):
    """說的話 text 結尾的表情要加的字（「愉快地」），沒有是 ""（照 C 版 expression()）。"""
    text = text.rstrip()
    return next((e["adverb"] for e in expressions if text.endswith(e["ending"])), "")
