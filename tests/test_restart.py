"""重開伺服器前的通知（mud/restart.py、deploy/update.sh，使用者 2026-11-20 要的）：收到 SIGUSR1 跟線上的玩家說幾秒後重開；
update.sh 的秒數、找的記號跟程式一樣。"""
import asyncio
import os
import re
import signal
import subprocess
from pathlib import Path

import pytest

from mud import restart
from mud.characters import Position, characters
from mud.color import colorize
from mud.config import ENCODING
from mud.players import Player

ROOT = Path(__file__).resolve().parent.parent
UPDATE = ROOT / "deploy" / "update.sh"


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


@pytest.fixture
def online():
    players = [Player(name, FakeWriter(), None) for name in ("Ming", "Hua")]
    players[1].position = Position.SLEEPING
    characters.extend(players)
    yield players
    characters.clear()


NOTICE = colorize("{Y【系統公告】伺服器 30 秒後重新啟動（更新新版本），請先找個安全的地方。{x")


def test_everyone_online_is_told(online):
    restart.announce()
    for p in online:                                                  # 睡著的也收得到
        assert NOTICE in p.writer.data.decode(ENCODING)


@pytest.mark.skipif(not hasattr(signal, "SIGUSR1"), reason="這個系統沒有 SIGUSR1")
def test_sigusr1_tells_them(online):
    async def main():
        restart.listen()
        os.kill(os.getpid(), signal.SIGUSR1)
        for _ in range(100):
            if online[0].writer.data:
                break
            await asyncio.sleep(0.01)

    asyncio.run(main())
    assert NOTICE in online[0].writer.data.decode(ENCODING)


def test_update_script_waits_as_long_as_the_notice_says():
    script = UPDATE.read_text(encoding="utf-8")
    assert re.search(r'^NOTICE="\$\{NOTICE:-(\d+)\}"', script, re.M)[1] == str(restart.NOTICE_SECONDS)


def test_update_script_looks_for_the_mark():
    # 舊版收到 SIGUSR1 會直接結束：update.sh 先找 restart.py 裡的記號，有才送
    script = UPDATE.read_text(encoding="utf-8")
    assert f'grep -qs "{restart.SIGNAL_MARK}" mud/restart.py' in script
    assert restart.SIGNAL_MARK in (ROOT / "mud" / "restart.py").read_text(encoding="utf-8")
    assert script.index("    notice  ") < script.index('git merge --ff-only --quiet "$new"')   # 先通知、等，再換檔案


def test_update_script_syntax():
    assert subprocess.run(["bash", "-n", str(UPDATE)]).returncode == 0
