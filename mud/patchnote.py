"""Discord 的 patch 通知（給玩家看的更新說明，使用者 2026-11-20 要的）。

流程（使用者選的：先給他看，他說好才發）：上線後把上次發過之後的修改寫成草稿 patch/草稿.md，
給使用者看過、他說「發」才跑 send，發完記進 patch/紀錄.md、草稿清空。只寫玩家感受得到的，imm 的指令不寫（使用者選的）。

    uv run python -m mud.patchnote since          # 上次發過之後的 commit（寫草稿用）
    uv run python -m mud.patchnote send --dry-run # 試跑：印出會發的幾則，不發、不記
    uv run python -m mud.patchnote send           # 發到 Discord，記進紀錄

webhook 網址（知道它就能發訊息到頻道，所以是密碼）放在 patch/discord-webhook，.gitignore 排除，不進 git。
只用標準庫，不 import 遊戲的模組。
"""
import argparse
import datetime
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

PATCH_DIR = Path("patch")
DRAFT = PATCH_DIR / "草稿.md"
RECORD = PATCH_DIR / "紀錄.md"
WEBHOOK = PATCH_DIR / "discord-webhook"
LIMIT = 2000                                # Discord 一則訊息最多 2000 個字
USER_AGENT = "WindMud-patchnote/1.0"        # 坑：urllib 預設的 User-Agent 會被 Discord 前面的 Cloudflare 擋掉（403）
TIMEOUT = 15
SENT = re.compile(r"^<!-- 發到 ([0-9a-f]{7,40}) -->$", re.M)   # 紀錄裡每一筆的標記：這一筆發到哪個 commit
RECORD_HEAD = "# 發過的 patch 通知\n\n`uv run python -m mud.patchnote send` 發完自動加在最後面；最後一筆的 commit 是下一次草稿的起點。\n"


class PatchError(Exception):
    """發不出去或不能發：訊息直接給人看。"""


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


def last_sent(record=RECORD):
    """紀錄裡最後一筆發到的 commit；還沒發過是 None。"""
    if not record.exists():
        return None
    found = SENT.findall(record.read_text(encoding="utf-8"))
    return found[-1] if found else None


def since(record=RECORD):
    """上次發過之後的 commit（舊的在前），一行一個「短號碼 日期 標題」。"""
    start = last_sent(record)
    span = [f"{start}..HEAD"] if start else ["HEAD"]
    return git("log", "--reverse", "--format=%h %ad %s", "--date=short", *span)


def split(text, limit=LIMIT):
    """切成每則不超過 limit 個字：照段落（空行）切，一段太長再照行切，一行太長才硬切。"""
    chunks, current = [], ""

    def add(piece, sep):
        nonlocal current
        joined = current + sep + piece if current else piece
        if len(joined) <= limit:
            current = joined
            return True
        if current:
            chunks.append(current)
        current = ""
        if len(piece) <= limit:
            current = piece
            return True
        return False

    for para in text.strip().split("\n\n"):
        if add(para, "\n\n"):
            continue
        for line in para.split("\n"):
            if add(line, "\n"):
                continue
            for i in range(0, len(line), limit):
                add(line[i:i + limit], "\n")
    if current:
        chunks.append(current)
    return chunks


def webhook_url(path=WEBHOOK):
    try:
        url = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise PatchError(f"還沒設定 webhook：把 Discord 的 webhook 網址存進 {path}（README「Discord 的 patch 通知」）") from None
    if not url.startswith("https://"):
        raise PatchError(f"{path} 裡面不是網址（要 https:// 開頭）")
    return url


def post(url, content):
    """發一則訊息到 Discord（webhook）。"""
    body = json.dumps({"content": content}).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT):
            pass
    except urllib.error.HTTPError as e:
        raise PatchError(f"Discord 回了 {e.code}：{e.read().decode('utf-8', 'replace')[:200]}") from None
    except urllib.error.URLError as e:
        raise PatchError(f"連不到 Discord：{e.reason}") from None


def send(dry_run=False, draft=DRAFT, record=RECORD, webhook=WEBHOOK):
    """發草稿；回傳發了（或試跑會發）的幾則。發完記進紀錄、草稿清空。"""
    text = draft.read_text(encoding="utf-8").strip() if draft.exists() else ""
    if not text:
        raise PatchError(f"{draft} 是空的，沒有東西可以發")
    chunks = split(text)
    if dry_run:
        return chunks
    url = webhook_url(webhook)
    head = git("rev-parse", "--short", "HEAD")
    start = last_sent(record)
    for chunk in chunks:
        post(url, chunk)
    old = record.read_text(encoding="utf-8") if record.exists() else RECORD_HEAD
    today = datetime.date.today().isoformat()
    span = f"{start}..{head}" if start else f"到 {head}"
    record.write_text(f"{old.rstrip()}\n\n## {today}（{span}）\n<!-- 發到 {head} -->\n\n{text}\n", encoding="utf-8")
    draft.write_text("", encoding="utf-8")
    return chunks


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m mud.patchnote", description="Discord 的 patch 通知")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("since", help="上次發過之後的 commit")
    p = sub.add_parser("send", help="把 patch/草稿.md 發到 Discord")
    p.add_argument("--dry-run", action="store_true", help="只印出會發的內容，不發、不記")
    args = parser.parse_args(argv)
    try:
        if args.action == "since":
            print(since() or "上次發過之後沒有新的 commit。")
            return 0
        chunks = send(dry_run=args.dry_run)
    except PatchError as e:
        print(e, file=sys.stderr)
        return 1
    for i, chunk in enumerate(chunks, 1):
        print(f"----- 第 {i}／{len(chunks)} 則（{len(chunk)} 字） -----\n{chunk}")
    print("試跑：沒有發，也沒有記。" if args.dry_run else f"發好了，共 {len(chunks)} 則，記進 {RECORD}。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
