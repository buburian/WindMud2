"""imm 的 health：伺服器的健康度（使用者 2026-11-20 要的）。

CI 跑在 Linux、開發機是 macOS：看得到的值兩邊不一樣，所以只比標籤和格式；要比數字的把讀值的地方換掉。
"""
import asyncio
import os
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import mud.commands as commands
from mud import health, lua, stats, zones
from mud.characters import characters
from mud.commands import help as help_command
from mud.commands import imm
from mud.commands.system import width
from mud.config import ENCODING
from mud.players import Player

AREAS = Path(__file__).resolve().parent.parent / "areas"
LABELS = ["開機", "記憶體", "CPU", "負載", "遊戲", "區域", "版本"]
SCREEN_WIDTH = 79
DAY = 86400


class FakeWriter:
    """假的連線：只把送出的 bytes 收起來。"""

    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data

    def text(self):
        """收到的文字（拿掉顏色），看完就清掉。"""
        out = re.sub(r"\x1b\[[0-9;]*m", "", self.data.decode(ENCODING))
        self.data = b""
        return out


@pytest.fixture(autouse=True)
def world(monkeypatch):
    zones.load(AREAS)
    monkeypatch.setattr(health, "started", None)        # 測試沒從 __main__ 開機
    yield
    characters.clear()


def player(name, is_imm=False):
    p = Player(name, FakeWriter(), zones.world.rooms[101])
    p.race, p.guild, p.imm = stats.Race.HUMAN, stats.Guild.SWORD, is_imm
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    stats.recompute(p)
    p.hp, p.mp, p.mv = p.panel["hp"], p.panel["mp"], p.panel["mv"]
    characters.append(p)
    return p


def screen(p, line="health"):
    """下指令，回傳畫面的每一行（拿掉最後的 prompt）。"""
    commands.command(p, line)
    return p.writer.text().rsplit("\r\n\r\n", 1)[0].split("\r\n")


def row(lines, label):
    return next(line for line in lines if line.startswith(label))


def nothing_readable(monkeypatch, tmp_path):
    """像沒有 /proc、resource、getloadavg 的平台。"""
    monkeypatch.setattr(health, "PROC_STATUS", str(tmp_path / "沒有這個檔"))
    monkeypatch.setattr(health, "resource", None)
    monkeypatch.delattr(os, "getloadavg")
    monkeypatch.setattr(os, "cpu_count", lambda: None)


# ---- 指令表 ----

def test_abbreviation_and_help_title():
    assert commands.find("hea", is_imm=True) is imm.do_health
    assert commands.find("he", is_imm=True) is help_command.do_help    # h、he 還是 help
    assert help_command.shortest("health", True) == "hea"


def test_not_imm_is_unknown():
    ming = player("Ming")
    assert screen(ming) == ["什麼？"]


# ---- 畫面 ----

def test_imm_sees_every_section_within_the_screen_width():
    boss = player("Boss", is_imm=True)
    lines = screen(boss, "hea")
    assert [line.split()[0] for line in lines] == LABELS
    assert all(width(line) <= SCREEN_WIDTH for line in lines)
    assert re.fullmatch(r"記憶體  現在 (看不到|\d+\.\d MB) +最高 (看不到|\d+\.\d MB) +Lua \d+\.\d\d / 64 MB", row(lines, "記憶體"))
    assert re.fullmatch(r"CPU     累積 \d+\.\d 秒 +平均 看不到 +核心 (\d+|看不到)", row(lines, "CPU"))    # 沒開機：沒有平均
    assert row(lines, "開機") == "開機    看不到"
    assert row(lines, "區域") == "區域    世界 1            動態 0            副本 0"
    assert row(lines, "版本").startswith(f"版本    Python {sys.version_info.major}.{sys.version_info.minor}.")
    assert "Lua 5.4" in row(lines, "版本")


def test_columns_line_up():
    boss = player("Boss", is_imm=True)
    lines = screen(boss)
    for label in ("記憶體", "CPU", "遊戲", "區域", "版本"):
        line = row(lines, label)
        starts = [width(line[:m.start()]) for m in re.finditer(r"(?<=  )\S", line)]
        assert starts[:3] == [8, 26, 44], line


def test_nothing_readable_does_not_break(monkeypatch, tmp_path):
    nothing_readable(monkeypatch, tmp_path)
    boss = player("Boss", is_imm=True)
    lines = screen(boss)
    assert row(lines, "開機") == "開機    看不到"
    assert row(lines, "記憶體").startswith("記憶體  現在 看不到       最高 看不到       Lua ")
    assert re.fullmatch(r"CPU     累積 \d+\.\d 秒 +平均 看不到 +核心 看不到", row(lines, "CPU"))
    assert row(lines, "負載") == "負載    看不到"
    assert row(lines, "遊戲").endswith("task 看不到")      # 沒有在跑的 loop


def test_load_that_raises_is_unseen(monkeypatch):
    def broken():
        raise OSError("讀不到")
    monkeypatch.setattr(os, "getloadavg", broken)
    assert health.load() is None


def test_uptime_and_average_cpu(monkeypatch):
    elapsed = 2 * DAY + 3 * 3600 + 4 * 60 + 5.1          # 尾數 .1：指令讀時間前慢了快 1 秒也還是 05 秒
    wall = time.mktime((2026, 11, 20, 9, 30, 0, 0, 0, -1))
    monkeypatch.setattr(health, "started", health.Start(wall, time.monotonic() - elapsed, time.process_time() - elapsed * 0.125))
    monkeypatch.setattr(health, "load", lambda: (0.5, 1.25, 2))
    boss = player("Boss", is_imm=True)
    lines = screen(boss)
    assert row(lines, "開機") == "開機    2026-11-20 09:30  跑了 2 天 03:04:05"
    assert "平均 12.5%" in row(lines, "CPU")
    assert row(lines, "負載") == "負載    1 分 0.50         5 分 1.25         15 分 2.00"


@pytest.mark.parametrize("seconds, want", [
    (0, "00:00:00"), (59.9, "00:00:59"), (3600, "01:00:00"), (DAY - 1, "23:59:59"), (DAY, "1 天 00:00:00"), (100 * DAY + 61, "100 天 00:01:01"),
])
def test_uptime_text(seconds, want):
    assert imm.uptime_text(seconds) == want


def test_average_without_time_passed(monkeypatch):
    now = time.monotonic()
    monkeypatch.setattr(health, "started", health.Start(time.time(), now, time.process_time()))
    monkeypatch.setattr(time, "monotonic", lambda: now)
    assert health.cpu_average() is None         # 不能除以 0


def test_game_counts(monkeypatch):
    monkeypatch.setitem(zones.dynamic, "x.json", SimpleNamespace(fights={1, 2}))
    monkeypatch.setitem(zones.instances, ("y.json", "Ming"), SimpleNamespace(fights={3}))
    boss, _ming = player("Boss", is_imm=True), player("Ming")
    lines = screen(boss)
    assert row(lines, "遊戲") == f"遊戲    線上玩家 2        角色 {len(characters):<13}戰鬥 3            task 看不到"
    assert row(lines, "區域") == "區域    世界 1            動態 1            副本 1"


def test_tasks_inside_the_loop():
    boss = player("Boss", is_imm=True)

    async def run():
        return screen(boss)
    assert re.search(r"task [1-9]\d*$", row(asyncio.run(run()), "遊戲"))
    assert health.tasks() is None               # 外面沒有在跑的 loop


def test_big_numbers_still_fit(monkeypatch):
    big = 10 ** 12
    monkeypatch.setattr(health, "started", health.Start(time.time(), time.monotonic() - 9999 * DAY, 0.0))
    monkeypatch.setattr(health, "memory", lambda: (big, big))
    monkeypatch.setattr(health, "cpu_seconds", lambda: 10 ** 8)
    monkeypatch.setattr(health, "cpu_average", lambda: 12345.6)
    monkeypatch.setattr(health, "cores", lambda: 1024)
    monkeypatch.setattr(health, "load", lambda: (1234.56, 1234.56, 1234.56))
    monkeypatch.setattr(health, "tasks", lambda: 999999)
    monkeypatch.setattr(lua, "memory_used", lambda: lua.MAX_MEMORY)
    boss = player("Boss", is_imm=True)
    lines = screen(boss)
    assert all(width(line) <= SCREEN_WIDTH for line in lines), lines
    assert "秒  平均" in row(lines, "CPU")       # 太長的格子照樣隔開


# ---- 讀記憶體 ----

def test_linux_proc_status(monkeypatch, tmp_path):
    status = tmp_path / "status"
    status.write_text("Name:\tpython\nVmPeak:\t  99999 kB\nVmHWM:\t   23456 kB\nVmRSS:\t   12345 kB\nThreads:\t3\n")
    monkeypatch.setattr(health, "PROC_STATUS", str(status))
    assert health.memory() == (12345 * 1024, 23456 * 1024)
    boss = player("Boss", is_imm=True)
    assert row(screen(boss), "記憶體").startswith("記憶體  現在 12.1 MB      最高 22.9 MB      Lua ")


def test_proc_status_without_the_lines_falls_back(monkeypatch, tmp_path):
    status = tmp_path / "status"
    status.write_text("Name:\tpython\n")
    monkeypatch.setattr(health, "PROC_STATUS", str(status))
    monkeypatch.setattr(health, "max_rss", lambda: 5 * 1024 * 1024)
    assert health.memory() == (None, 5 * 1024 * 1024)


@pytest.mark.parametrize("platform, want", [("darwin", 2048), ("linux", 2048 * 1024)])
def test_getrusage_units(monkeypatch, tmp_path, platform, want):
    # ru_maxrss：macOS 是 byte、Linux 是 KB
    monkeypatch.setattr(health, "PROC_STATUS", str(tmp_path / "沒有這個檔"))
    fake = SimpleNamespace(RUSAGE_SELF=0, getrusage=lambda who: SimpleNamespace(ru_maxrss=2048))
    monkeypatch.setattr(health, "resource", fake)
    monkeypatch.setattr(sys, "platform", platform)
    assert health.memory() == (None, want)


def test_getrusage_that_raises(monkeypatch):
    def broken(who):
        raise OSError("讀不到")
    monkeypatch.setattr(health, "resource", SimpleNamespace(RUSAGE_SELF=0, getrusage=broken))
    assert health.max_rss() is None
