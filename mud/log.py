"""系統紀錄：畫面用 rich 顯示，同時存檔到 logs/。"""
import logging
import os
import re
from datetime import date
from pathlib import Path

from rich.logging import RichHandler

MAX_BYTES = 5 * 1024 * 1024     # 一個檔最多 5MB
KEEP = 30                       # 最多留幾個檔（全部日期加起來）
NAME = re.compile(r"(\d{4}-\d{2}-\d{2})_(\d{3,})\.log")


class DailyFileHandler(logging.FileHandler):
    """檔名是「日期_編號.log」，例如 2026-10-30_001.log。

    換日就從 001 重新編號；這筆寫進去會超過 max_bytes，就換下一個編號。
    換檔後只留最新的 keep 個檔，更舊的刪掉。只動符合檔名格式的檔，資料夾裡其他檔案不碰。
    """

    def __init__(self, directory, max_bytes=MAX_BYTES, keep=KEEP, today=date.today):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.max_bytes, self.keep, self.today = max_bytes, keep, today
        self.day = today()
        files = self._files(self.day)
        if files and files[-1].stat().st_size < max_bytes:
            path = files[-1]                    # 今天的最後一個檔還沒滿，接著寫
        else:
            path = self._path(self.day, self._number(files[-1]) + 1 if files else 1)
        super().__init__(path, encoding="utf-8")
        self._prune()

    def emit(self, record):
        day = self.today()
        if day != self.day:
            self._switch(day, 1)
        else:
            size = self.stream.tell()
            # 空檔不換，不然一筆比上限還大的紀錄會一直開新檔
            if size and size + len(self.format(record).encode("utf-8")) + 1 > self.max_bytes:
                self._switch(day, self._number(self.baseFilename) + 1)
        super().emit(record)

    def _switch(self, day, number):
        self.stream.close()
        self.day = day
        self.baseFilename = os.path.abspath(self._path(day, number))
        self.stream = self._open()
        self._prune()

    def _prune(self):
        for old in self._files()[:-self.keep]:
            old.unlink()

    def _files(self, day=None):
        """排好序（舊到新）的紀錄檔；給 day 就只列那一天的。"""
        found = []
        for p in self.directory.iterdir():
            m = NAME.fullmatch(p.name)
            if m and (day is None or m.group(1) == day.isoformat()):
                found.append((m.group(1), int(m.group(2)), p))
        return [p for _, _, p in sorted(found)]

    def _path(self, day, number):
        return self.directory / f"{day.isoformat()}_{number:03d}.log"

    @staticmethod
    def _number(path):
        return int(NAME.fullmatch(Path(path).name).group(2))


def setup(directory="logs"):
    """畫面用 rich 顯示，同時存檔到 directory。"""
    to_file = DailyFileHandler(directory)
    to_file.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[RichHandler(), to_file])
