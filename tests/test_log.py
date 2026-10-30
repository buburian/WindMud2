import logging
from datetime import date

from mud.log import DailyFileHandler


class Clock:
    """假的日期，可以手動換日。"""

    def __init__(self, day):
        self.day = day

    def __call__(self):
        return self.day


def write(handler, msg):
    handler.emit(logging.LogRecord("t", logging.INFO, __file__, 0, msg, None, None))


def names(folder):
    return sorted(p.name for p in folder.iterdir())


def read(path):
    return path.read_text(encoding="utf-8")


def test_defaults_are_5mb_and_30_files(tmp_path):
    h = DailyFileHandler(tmp_path, today=Clock(date(2026, 10, 30)))
    h.close()
    assert (h.max_bytes, h.keep) == (5 * 1024 * 1024, 30)


def test_first_file_then_next_number_when_full(tmp_path):
    h = DailyFileHandler(tmp_path, max_bytes=20, today=Clock(date(2026, 10, 30)))
    write(h, "a" * 15)                           # 加換行 16 bytes
    write(h, "b" * 15)                           # 再寫會超過 20，換下一個編號
    h.close()
    assert names(tmp_path) == ["2026-10-30_001.log", "2026-10-30_002.log"]
    assert read(tmp_path / "2026-10-30_002.log") == "b" * 15 + "\n"


def test_new_day_starts_at_001(tmp_path):
    clock = Clock(date(2026, 10, 30))
    h = DailyFileHandler(tmp_path, today=clock)
    write(h, "x")
    clock.day = date(2026, 10, 31)
    write(h, "y")
    h.close()
    assert names(tmp_path) == ["2026-10-30_001.log", "2026-10-31_001.log"]


def test_keeps_only_newest_files(tmp_path):
    h = DailyFileHandler(tmp_path, max_bytes=1, keep=3, today=Clock(date(2026, 10, 30)))
    for i in range(5):                           # 每筆都超過上限，所以每筆一個檔
        write(h, str(i))
    h.close()
    assert names(tmp_path) == ["2026-10-30_003.log", "2026-10-30_004.log", "2026-10-30_005.log"]


def test_restart_continues_todays_last_file(tmp_path):
    clock = Clock(date(2026, 10, 30))
    for msg in ("first", "second"):
        h = DailyFileHandler(tmp_path, today=clock)
        write(h, msg)
        h.close()
    assert names(tmp_path) == ["2026-10-30_001.log"]
    assert read(tmp_path / "2026-10-30_001.log") == "first\nsecond\n"


def test_restart_with_full_file_opens_next(tmp_path):
    (tmp_path / "2026-10-30_001.log").write_text("x" * 30)
    h = DailyFileHandler(tmp_path, max_bytes=20, today=Clock(date(2026, 10, 30)))
    write(h, "y")
    h.close()
    assert names(tmp_path) == ["2026-10-30_001.log", "2026-10-30_002.log"]


def test_other_files_are_never_deleted(tmp_path):
    (tmp_path / "notes_1.log").write_text("留著")
    h = DailyFileHandler(tmp_path, max_bytes=1, keep=1, today=Clock(date(2026, 10, 30)))
    for i in range(3):
        write(h, str(i))
    h.close()
    assert names(tmp_path) == ["2026-10-30_003.log", "notes_1.log"]
