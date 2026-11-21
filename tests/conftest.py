"""全部測試共用的設定。"""
import datetime

import pytest

from mud import skill_queue, zones

FAR_FUTURE = datetime.date(2100, 1, 1)


@pytest.fixture(autouse=True)
def no_new_areas_by_date(monkeypatch):
    """新區域（header.opened 起 14 天內）照「今天」算：測試一律用很久以後的日期，真的區域檔都不算新，
    結果才不會跟著跑測試那天變（坑：樹洞寫 2026-11-20，那 14 天內登入畫面、area 都多了東西）。要測新區域的自己換 zones.today。"""
    monkeypatch.setattr(zones, "today", lambda: FAR_FUTURE)


class NoBreach:
    """破綻的亂數：永遠沒中。"""

    def random(self):
        return 1.0


@pytest.fixture(autouse=True)
def no_breach(monkeypatch):
    """破綻（skill_queue.py）每回合打完 20%：測試一律不會有，不然比對整段戰鬥訊息的測試會偶爾多一行「露出了破綻」。要測破綻的自己換 skill_queue.rng。"""
    monkeypatch.setattr(skill_queue, "rng", NoBreach())
