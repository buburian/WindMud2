"""Discord 的 patch 通知（mud/patchnote.py）：切訊息、試跑、發完記紀錄、webhook 檔案。發送換成假的，不會真的連到 Discord。"""
import json
import subprocess
from pathlib import Path

import pytest

from mud import patchnote
from mud.patchnote import LIMIT, PatchError

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def files(tmp_path, monkeypatch):
    """草稿、紀錄、webhook 都放 tmp_path；發出去的記在 sent，Discord 回的訊息 ID 是 101、102…，HEAD 是 abc1234。"""
    sent = []

    def fake_post(url, content):
        sent.append((url, content))
        return {"id": str(100 + len(sent))}

    monkeypatch.setattr(patchnote, "post", fake_post)
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
    assert "<!-- 發到 abc1234 -->\n<!-- 訊息 ID：101 -->" in record and "新的區域：邪龍教派。" in record
    assert patchnote.last_sent(paths["record"]) == "abc1234"
    assert paths["draft"].read_text(encoding="utf-8") == ""


def test_long_notes_record_every_message_id(files):
    # 切成好幾則：每一則的 ID 都記（使用者 2026-11-20 要的）
    paths, sent = files
    paths["draft"].write_text("甲" * 1500 + "\n\n" + "乙" * 1500, encoding="utf-8")
    patchnote.send(**paths)
    assert len(sent) == 2 and "<!-- 訊息 ID：101 102 -->" in paths["record"].read_text(encoding="utf-8")


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


# ---- 討論區發文（forum，使用者 2026-11-20 要的）----

@pytest.fixture
def board(tmp_path, monkeypatch):
    """討論區的 webhook、一篇文章；發出去的記在 sent：(content, thread_name, thread_id)，開新文章回傳編號 999。"""
    sent = []

    def fake_post(url, content, thread_name=None, thread_id=None):
        sent.append((content, thread_name, thread_id))
        return {"channel_id": "999"} if thread_name else {}

    monkeypatch.setattr(patchnote, "post", fake_post)
    webhook = tmp_path / "discord-forum-webhook"
    webhook.write_text("https://discord.com/api/webhooks/2/y", encoding="utf-8")
    article = tmp_path / "文章.md"
    return article, webhook, sent


def test_forum_opens_a_new_post(board):
    article, webhook, sent = board
    article.write_text("第一段\n\n第二段\n", encoding="utf-8")
    assert patchnote.forum(article, " 測試文章 ", webhook=webhook) == ["第一段\n\n第二段"]
    assert sent == [("第一段\n\n第二段", "測試文章", None)]


def test_long_posts_go_under_the_same_post(board):
    article, webhook, sent = board
    a, b, c = "甲" * 1500, "乙" * 1500, "丙" * 1500
    article.write_text(f"{a}\n\n{b}\n\n{c}", encoding="utf-8")
    patchnote.forum(article, "長文", webhook=webhook)
    assert sent == [(a, "長文", None), (b, None, "999"), (c, None, "999")]   # 第一則開文章，後面的接在它底下


def test_forum_dry_run_sends_nothing(board):
    article, webhook, sent = board
    article.write_text("內容", encoding="utf-8")
    assert patchnote.forum(article, "標題", dry_run=True, webhook=webhook) == ["內容"] and sent == []


@pytest.mark.parametrize("text, title, problem", [
    ("內容", "  ", "要有標題"),
    ("內容", "字" * 101, "標題最多 100 個字，現在是 101 個字"),
    ("  \n", "標題", "是空的或找不到"),
])
def test_forum_refuses(board, text, title, problem):
    article, webhook, sent = board
    article.write_text(text, encoding="utf-8")
    with pytest.raises(PatchError, match=problem):
        patchnote.forum(article, title, webhook=webhook)
    assert sent == []


def test_forum_needs_its_own_webhook(board, tmp_path):
    article, _webhook, sent = board
    article.write_text("內容", encoding="utf-8")
    with pytest.raises(PatchError, match="還沒設定 webhook"):
        patchnote.forum(article, "標題", webhook=tmp_path / "沒有")


def test_forum_without_a_post_number_stops(board, monkeypatch):
    article, webhook, sent = board
    monkeypatch.setattr(patchnote, "post", lambda *args, **kw: sent.append(kw) or {})   # 不是討論區：沒有回文章的編號
    article.write_text("甲" * 1500 + "\n\n" + "乙" * 1500, encoding="utf-8")
    with pytest.raises(PatchError, match="webhook 是不是建在討論區頻道上"):
        patchnote.forum(article, "標題", webhook=webhook)
    assert len(sent) == 1


def test_post_builds_the_request(monkeypatch):
    seen = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"channel_id": "999"}'

    monkeypatch.setattr(patchnote.urllib.request, "urlopen", lambda request, timeout: seen.append(request) or Response())
    assert patchnote.post("https://x/webhook", "內容", thread_name="標題") == {"channel_id": "999"}
    patchnote.post("https://x/webhook", "接著", thread_id="999")
    first, second = seen
    assert first.full_url == "https://x/webhook?wait=true" and json.loads(first.data) == {"content": "內容", "thread_name": "標題"}
    assert second.full_url == "https://x/webhook?wait=true&thread_id=999" and json.loads(second.data) == {"content": "接著"}
    assert first.get_header("User-agent") == patchnote.USER_AGENT


def test_forum_webhook_file_is_ignored_by_git():
    result = subprocess.run(["git", "check-ignore", "-q", "patch/discord-forum-webhook"], cwd=ROOT)
    assert result.returncode == 0


def test_split_keeps_a_heading_with_what_is_under_it():
    intro = "開頭" * 600                                             # 1200 字：後面那一節整節放不下，就整節放到下一則
    sword = "## 劍之公會\n\n" + "劍" * 1100 + "\n\n- 技能"             # 一節 1100 多字
    staff = "## 杖之公會\n\n" + "杖" * 1100
    chunks = patchnote.split(f"{intro}\n\n{sword}\n\n{staff}")
    assert chunks == [intro, sword, staff]                          # 劍之公會那一節沒有被拆開（標題和內容在同一則）
    assert patchnote.split("前面\n\n## 小節\n\n內容") == ["前面\n\n## 小節\n\n內容"]   # 放得下就放在一起


def test_split_never_breaks_a_code_block():
    block = "```\n" + "樹" * 995 + "\n\n" + "枝" * 995 + "\n```"      # 區塊裡有空行，整個 2000 字
    assert patchnote.split("前面\n\n" + block) == ["前面", block]          # 整個區塊放到下一則，不從中間的空行切開



# ---- 改發過的（edit，使用者 2026-11-20 要的）----

RECORD = """# 發過的 patch 通知

## 2026-11-20（到 aaa1111）
<!-- 發到 aaa1111 -->
<!-- 訊息 ID：11 -->

## 📜 第一次

## 2026-11-20（aaa1111..bbb2222）
<!-- 發到 bbb2222 -->
<!-- 訊息 ID：21 22 -->

{long}
"""


@pytest.fixture
def record(tmp_path, monkeypatch):
    """兩筆紀錄（第二筆發了兩則）；送出去的記在 calls：(網址, 內容, 方法)。"""
    calls = []
    monkeypatch.setattr(patchnote, "call", lambda url, payload, method="POST": calls.append((url, payload, method)) or {})
    path = tmp_path / "紀錄.md"
    path.write_text(RECORD.format(long="甲" * 1500 + "\n\n" + "乙" * 1500), encoding="utf-8")
    webhook = tmp_path / "discord-webhook"
    webhook.write_text("https://discord.com/api/webhooks/1/x", encoding="utf-8")
    return path, webhook, calls


def test_edit_finds_the_entry_by_any_id(record):
    path, _webhook, _calls = record
    assert patchnote.entry_of("11", path) == (["11"], "## 📜 第一次")    # 內容裡的 ## 標題不算下一筆
    assert patchnote.entry_of("22", path)[0] == ["21", "22"]
    with pytest.raises(PatchError, match="找不到訊息 ID 99"):
        patchnote.entry_of("99", path)


def test_edit_patches_each_message(record):
    path, webhook, calls = record
    patchnote.edit("21", record=path, webhook=webhook)
    assert calls == [("https://discord.com/api/webhooks/1/x/messages/21", {"content": "甲" * 1500}, "PATCH"),
                     ("https://discord.com/api/webhooks/1/x/messages/22", {"content": "乙" * 1500}, "PATCH")]


def test_edit_dry_run_sends_nothing(record):
    path, webhook, calls = record
    assert patchnote.edit("11", dry_run=True, record=path, webhook=webhook) == [("11", "## 📜 第一次")] and calls == []


def test_edit_cannot_change_how_many_messages(record):
    path, webhook, calls = record
    path.write_text(RECORD.format(long="短短的"), encoding="utf-8")       # 原本兩則，改完一則
    with pytest.raises(PatchError, match="這一筆發的時候是 2 則（ID：21 22），改完切成 1 則"):
        patchnote.edit("21", record=path, webhook=webhook)
    assert calls == []


def test_old_entries_without_ids_still_parse(record):
    path, _webhook, _calls = record
    path.write_text("## 2026-11-20（到 aaa1111）\n<!-- 發到 aaa1111 -->\n\n內容\n" + RECORD.split("\n", 2)[2], encoding="utf-8")
    assert patchnote.entry_of("11", path) == (["11"], "## 📜 第一次")   # 沒有 ID 的舊筆不會吃掉下一筆
    assert patchnote.last_sent(path) == "bbb2222"
