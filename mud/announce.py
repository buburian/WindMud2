"""系統公告（使用者 2026-11-20 要的）：寫在 screens/announce.txt（config.ANNOUNCE_FILE），開機時 load()。

舊角色登入時接在「歡迎回來」和房間之間，前後空一行、有外框（login.enter）；平常打 `read announce` 看（commands/read.py）。
檔案沒有、只有空白是沒有公告。改了要重開伺服器才會換（跟登入畫面一樣）。
"""
import re
from pathlib import Path

from .color import colorize
from .config import ENCODING

TITLE = "【系統公告】"
WIDTH = 75                                  # 每行最多幾格：整個框不超過 79 格（外框左右的「| 」「 |」各佔 2 格）
HEIGHT = 10                                 # 最多幾行（不算標題）：太長會把登入時房間的畫面擠出去
COLOR = "{Y"                                # 外框和標題亮黃（跟換區域的提示一樣）；內容照檔案寫的，可以用顏色代碼
ANSI = re.compile(r"\x1b\[[0-9;]*m")

text = ""                                   # 載入的公告（外框做好、換成色碼）；沒有公告是空的


def shown_width(line):
    """一行在畫面上佔幾格（不算顏色代碼，中文兩格）；有轉不成 Big5 的字就丟 UnicodeEncodeError。"""
    return len(ANSI.sub("", colorize(line)).encode(ENCODING))


def load(path):
    """讀公告、檢查、做好外框。有問題就 ValueError（第一個問題加總數），原本載入的不動。開機時呼叫（__main__）。"""
    global text
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raw = ""
    except OSError:
        raise ValueError(f"讀不到系統公告 {path}") from None
    lines = raw.rstrip().split("\n") if raw.strip() else []
    problems = check(lines)
    if problems:
        raise ValueError(f"{path}：{problems[0]}（共 {len(problems)} 個問題）")
    text = box(lines)


def check(lines):
    """公告的問題（空的就是沒問題）：最多 HEIGHT 行，每行不超過 WIDTH 格，字要轉得成 Big5。"""
    problems = []
    if len(lines) > HEIGHT:
        problems.append(f"太長了：{len(lines)} 行，最多 {HEIGHT} 行")
    for i, line in enumerate(lines, 1):
        try:
            width = shown_width(line)
        except UnicodeEncodeError as e:
            problems.append(f"第 {i} 行有轉不成 Big5 的字 {e.object[e.start]!r}")
            continue
        if width > WIDTH:
            problems.append(f"第 {i} 行太寬了：{width} 格，最多 {WIDTH} 格（外框佔 4 格）")
    return problems


def box(lines):
    """外框（照最寬的那一行，半形的 + - |，跟換區域的提示一樣）：標題一行、內容每行一行。沒有內容是空的。"""
    if not lines:
        return ""
    w = max(shown_width(line) for line in [TITLE] + lines)
    edge = colorize(COLOR + "+" + "-" * (w + 2) + "+{x")
    title = colorize(COLOR + "| " + TITLE + " " * (w - shown_width(TITLE)) + " |{x")
    rows = [colorize(COLOR + "|{x " + line + "{x") + " " * (w - shown_width(line)) + colorize(" " + COLOR + "|{x") for line in lines]
    return "\n".join([edge, title, *rows, edge])
