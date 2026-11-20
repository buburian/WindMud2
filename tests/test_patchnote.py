"""Discord 的 patch 通知（mud/patchnote.py）：切訊息、試跑、發完記紀錄、webhook 檔案。發送換成假的，不會真的連到 Discord。"""
import subprocess
from pathlib import Path

import pytest

from mud import patchnote
from mud.patchnote import LIMIT, PatchError

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def files(tmp_path, monkeypatch):
    """草稿、紀錄、webhook 都放 tmp_path；發出去的記在 sent，HEAD 是 abc1234。"""
    sent = []
    monkeypatch.setattr(patchnote, "post", lambda url, content: sent.append((url, content)))
    monkeypatch.setattr(patchnote, "git", lambda *args: "abc1234")
    paths = {"draft": tmp_path / "草稿.md", "record": tmp_path / "紀錄.md", "webhook": tmp_path / "discord-webhook"}
    paths["webhook"].write_text("https://discord.com/api/webhooks/1/x\n", encoding="utf-8")
    return paths, sent


def test_split_keeps_short_text_whole():
    assert patchnote.split("一\n\n二") == ["一\n\n二"]


def test_split_exactly_at_the_limit():
    text = "字" * LIMIT
    assert patchnote.split(text) == [text]


def test_split_by_paragraph():
    a, b = "甲" * 1500, "乙" * 1500
    assert patchnote.split(f"{a}\n\n{b}") == [a, b]


def test_split_long_paragraph_by_line_then_by_size():
    lines = ["丙" * 1500, "丁" * 1500]
    assert patchnote.split("\n".join(lines)) == lines
    huge = "戊" * (LIMIT * 2 + 5)
    chunks = patchnote.split(huge)
    assert [len(c) for c in chunks] == [LIMIT, LIMIT, 5] and "".join(chunks) == huge


def test_every_chunk_fits():
    text = "\n\n".join("段落" * n for n in range(1, 400, 7))
    assert all(len(c) <= LIMIT for c in patchnote.split(text))


def test_dry_run_sends_and_records_nothing(files):
    paths, sent = files
    paths["draft"].write_text("新的區域：邪龍教派。\n", encoding="utf-8")
    assert patchnote.send(dry_run=True, **paths) == ["新的區域：邪龍教派。"]
    assert sent == [] and not paths["record"].exists()
    assert paths["draft"].read_text(encoding="utf-8") == "新的區域：邪龍教派。\n"


def test_send_posts_records_and_clears_the_draft(files):
    paths, sent = files
    paths["draft"].write_text("新的區域：邪龍教派。\n", encoding="utf-8")
    patchnote.send(**paths)
    assert sent == [("https://discord.com/api/webhooks/1/x", "新的區域：邪龍教派。")]
    record = paths["record"].read_text(encoding="utf-8")
    assert "<!-- 發到 abc1234 -->" in record and "新的區域：邪龍教派。" in record
    assert patchnote.last_sent(paths["record"]) == "abc1234"
    assert paths["draft"].read_text(encoding="utf-8") == ""


def test_next_send_starts_after_the_last_one(files, monkeypatch):
    paths, sent = files
    paths["draft"].write_text("第一次", encoding="utf-8")
    patchnote.send(**paths)
    monkeypatch.setattr(patchnote, "git", lambda *args: "def5678")
    paths["draft"].write_text("第二次", encoding="utf-8")
    patchnote.send(**paths)
    record = paths["record"].read_text(encoding="utf-8")
    assert "（abc1234..def5678）" in record and record.index("第一次") < record.index("第二次")
    assert patchnote.last_sent(paths["record"]) == "def5678"


def test_empty_draft_is_not_sent(files):
    paths, sent = files
    paths["draft"].write_text("\n  \n", encoding="utf-8")
    with pytest.raises(PatchError, match="是空的"):
        patchnote.send(**paths)
    assert sent == []


def test_missing_webhook_says_so(files):
    paths, sent = files
    paths["webhook"].unlink()
    paths["draft"].write_text("內容", encoding="utf-8")
    with pytest.raises(PatchError, match="還沒設定 webhook"):
        patchnote.send(**paths)
    assert sent == [] and not paths["record"].exists()
    assert paths["draft"].read_text(encoding="utf-8") == "內容"       # 沒發出去，草稿留著


def test_webhook_must_be_a_url(files):
    paths, sent = files
    paths["webhook"].write_text("not a url", encoding="utf-8")
    paths["draft"].write_text("內容", encoding="utf-8")
    with pytest.raises(PatchError, match="不是網址"):
        patchnote.send(**paths)


def test_webhook_file_is_ignored_by_git():
    """webhook 網址是密碼：.gitignore 要排除它，不能被 git add 加進去推到 GitHub。"""
    result = subprocess.run(["git", "check-ignore", "-q", "patch/discord-webhook"], cwd=ROOT)
    assert result.returncode == 0
