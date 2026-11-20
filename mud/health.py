"""伺服器的健康度：開機多久、記憶體、CPU、系統負載（imm 的 health 指令用，使用者 2026-11-20 要的；畫面在 commands/imm.py）。

只用標準庫，不 import 專案的其他模組。正式機是 Linux、開發機是 macOS：每個函式自己接住錯誤，
讀不到的回傳 None（畫面寫「看不到」），不丟錯。
"""
import asyncio
import os
import platform
import sys
import time
from typing import NamedTuple

try:
    import resource                         # Windows 沒有
except ImportError:
    resource = None

PROC_STATUS = "/proc/self/status"           # Linux：VmRSS 是現在佔的記憶體、VmHWM 是最高用量，單位 kB
KB = 1024
MAXRSS_IN_BYTES = ("darwin",)               # getrusage 的 ru_maxrss：macOS 是 byte，其他（Linux）是 KB
PERCENT = 100


class Start(NamedTuple):
    """開機時記下的時間。"""
    wall: float                             # 現實時間（time.time()）：畫面顯示幾點開機
    clock: float                            # time.monotonic()：算跑了多久（改系統時間不影響）
    cpu: float                              # 那時候已經用掉的 CPU 時間（time.process_time()）：算開機以來的平均使用率


started = None                              # 開機時記下的 Start；沒從 __main__ 開機（測試）是 None


def mark_start():
    """開機時呼叫一次（__main__）。"""
    global started
    started = Start(time.time(), time.monotonic(), time.process_time())


def uptime():
    """開機到現在幾秒；沒記開機時間是 None。"""
    return None if started is None else time.monotonic() - started.clock


def memory():
    """(現在佔的, 最高用量)，單位 byte，讀不到的是 None。

    Linux 讀 /proc/self/status；讀不到（macOS）最高用量改用 getrusage，現在佔的標準庫拿不到。
    """
    now, peak = proc_status()
    return now, (peak if peak is not None else max_rss())


def proc_status():
    """/proc/self/status 的 (VmRSS, VmHWM)，單位 byte；沒有這個檔（不是 Linux）、或沒有那一行是 None。"""
    try:
        with open(PROC_STATUS, encoding="ascii", errors="replace") as f:
            text = f.read()
    except OSError:
        return None, None
    found = {}
    for line in text.splitlines():
        key, _, value = line.partition(":")
        parts = value.split()
        if parts and parts[0].isdecimal():
            found[key] = int(parts[0]) * KB
    return found.get("VmRSS"), found.get("VmHWM")


def max_rss():
    """getrusage 的最高用量，單位 byte；沒有 resource 模組、或讀不到是 None。"""
    if resource is None:
        return None
    try:
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (OSError, ValueError):
        return None
    return peak if sys.platform in MAXRSS_IN_BYTES else peak * KB


def cpu_seconds():
    """這個程式累積用掉的 CPU 時間（秒；user ＋ system、全部的執行緒，從程式開始算）。"""
    return time.process_time()


def cpu_average():
    """開機以來平均的 CPU 使用率（%，一個核心滿載是 100）；沒記開機時間、還沒過時間是 None。"""
    if started is None:
        return None
    elapsed = time.monotonic() - started.clock
    if elapsed <= 0:
        return None
    return (time.process_time() - started.cpu) / elapsed * PERCENT


def load():
    """整台機器 1、5、15 分鐘的平均負載；這個平台沒有、或讀不到是 None。"""
    try:
        return os.getloadavg()
    except (AttributeError, OSError):
        return None


def cores():
    """CPU 核心數；不知道是 None。"""
    return os.cpu_count()


def tasks():
    """asyncio 的 task 數；沒有在跑的 loop（測試直接呼叫指令）是 None。"""
    try:
        return len(asyncio.all_tasks())
    except RuntimeError:
        return None


def python_version():
    return platform.python_version()
