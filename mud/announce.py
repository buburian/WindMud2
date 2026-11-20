"""系統公告（使用者 2026-11-20 要的）：寫在 screens/announce.txt（config.ANNOUNCE_FILE），開機時 load()。

舊角色登入時接在「歡迎回來」和房間之間，前後空一行、有外框（login.enter）；平常打 `read announce` 看（commands/read.py）。
兩個地方都呼叫 current()：檔案的內容、開放 14 天內的新區域（使用者 2026-11-20 要的，zones.new_areas()，每次照當天的日期算）、版本。
檔案沒有、只有空白，又沒有新區域，就是沒有公告。檔案改了要重開伺服器才會換（跟登入畫面一樣）。
"""
import re
from pathlib import Path

from .color import colorize
from .config import ENCODING

TITLE = "【系統公告】"
VERSION = "版本 "                            # 框裡最後一行：「版本 7d3539e」
NEW_AREA = "新區域："                        # 新區域那一行：「新區域：樹洞（15～20 級，副本），入口 3s10wn2wsw」
TOO_WIDE_INDENT = "    "                    # 新區域那一行太寬：「入口 …」換到下一行，前面空 4 格
WIDTH = 75                                  # 每行最多幾格：整個框不超過 79 格（外框左右的「| 」「 |」各佔 2 格）
HEIGHT = 10                                 # 最多幾行（不算標題）：太長會把登入時房間的畫面擠出去
COLOR = "{Y"                                # 外框和標題亮黃（跟換區域的提示一樣）；內容照檔案寫的，可以用顏色代碼
ANSI = re.compile(r"\x1b\[[0-9;]*m")

lines = []                                  # 載入的 announce.txt（檢查過，每行一個字串）；沒有是空的
version = None                              # 開機時讀的 git 版本號（health.commit()）；讀不到是 None


def shown_width(line):
    """一行在畫面上佔幾格（不算顏色代碼，中文兩格）；有轉不成 Big5 的字就丟 UnicodeEncodeError。"""
    return len(ANSI.sub("", colorize(line)).encode(ENCODING))


def load(path, commit=None):
    """讀公告、檢查。有問題就 ValueError（第一個問題加總數），原本載入的不動。開機時呼叫（__main__）。
    commit 是 git 的版本號（health.commit()）：有公告才在框裡最後加一行「版本 …」（使用者 2026-11-20 要的），不算在 HEIGHT 裡。"""
    global lines, version
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raw = ""
    except OSError:
        raise ValueError(f"讀不到系統公告 {path}") from None
    found = raw.rstrip().split("\n") if raw.strip() else []
    problems = check(found)
    if problems:
        raise ValueError(f"{path}：{problems[0]}（共 {len(problems)} 個問題）")
    lines, version = found, commit


def current():
    """登入、read announce 看到的公告（外框做好、換成色碼）：announce.txt 的內容、開放 14 天內的新區域、版本。
    檔案是空的又沒有新區域，就是沒有公告（空字串）；有新區域的話，檔案是空的也有框（使用者 2026-11-20 要的）。"""
    news = new_area_lines()
    if not lines and not news:
        return ""
    return box(lines + news + ([VERSION + version] if version else []))


def new_area_lines():
    """開放 14 天內的區域（zones.new_areas()，新開的在前），每個一行：「新區域：樹洞（15～20 級，副本），入口 3s10wn2wsw」。
    入口跟 area 的入口欄一樣，沒有入口（-----）就不寫；一行超過 WIDTH，「入口 …」換到下一行。不算在 HEIGHT 裡。"""
    from . import zones
    from .area import AreaType
    from .commands.system import AREA_KINDS, AREA_NO_ENTRANCE, entrance   # 坑：commands 會 import read → announce，在函式裡才 import
    out = []
    for name, header in zones.new_areas():
        low, high = header["levels"]
        head = f"{NEW_AREA}{header['title']}（{low}～{high} 級，{AREA_KINDS[AreaType(header['type'])]}）"
        way = entrance(name)
        if way == AREA_NO_ENTRANCE:
            out.append(head)
        elif shown_width(f"{head}，入口 {way}") <= WIDTH:
            out.append(f"{head}，入口 {way}")
        else:
            out += [head, f"{TOO_WIDE_INDENT}入口 {way}"]
    return out


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
