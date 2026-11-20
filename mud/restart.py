"""重開伺服器前的通知（使用者 2026-11-20 要的）：正式機的 deploy/update.sh 拉新版之前，送 SIGUSR1 給伺服器（python），
伺服器跟線上的玩家說幾秒後重開；update.sh 等 NOTICE_SECONDS 秒才更新、重開（重開時照舊存好玩家的檔）。

__main__ 開機時 listen()。坑：還沒有這個功能的舊版收到 SIGUSR1 會直接結束（沒存檔），所以 update.sh 先看這個檔有沒有
SIGNAL_MARK 那一行（MARK），有才送；這一行不要改名。
"""
import asyncio
import logging
import signal

from .act import notify
from .color import colorize
from .players import online_players

log = logging.getLogger(__name__)

NOTICE_SECONDS = 30                         # 通知後幾秒重開：deploy/update.sh 的 NOTICE 要一樣（tests/test_restart.py 比對）
NOTICE_TEXT = "【系統公告】伺服器 {} 秒後重新啟動（更新新版本），請先找個安全的地方。"
SIGNAL_MARK = "WINDMUD_RESTART_NOTICE"      # deploy/update.sh 用 grep 找這個字，確定跑著的程式接得住 SIGUSR1


def announce():
    """收到 SIGUSR1：跟每個線上的玩家說（睡著的也說：要重開了，大家都要知道），亮黃色。"""
    text = colorize("{Y" + NOTICE_TEXT.format(NOTICE_SECONDS) + "{x")
    players = online_players()
    for p in players:
        notify(p, text)
    log.info(f"{NOTICE_SECONDS} 秒後重開伺服器：通知了 {len(players)} 個線上的玩家")


def listen():
    """開機時（在 loop 裡）接 SIGUSR1。Windows 沒有這個信號，就不接。"""
    try:
        asyncio.get_running_loop().add_signal_handler(signal.SIGUSR1, announce)
    except (AttributeError, NotImplementedError):
        log.warning("這個系統沒有 SIGUSR1：重開前的通知不能用")
