"""Discord 的 patch 通知（給玩家看的更新說明，使用者 2026-11-20 要的）。

流程（使用者選的：先給他看，他說好才發）：上線後把上次發過之後的修改寫成草稿 patch/草稿.md，
給使用者看過、他說「發」才跑 send，發完記進 patch/紀錄.md（連 Discord 回的訊息 ID）、草稿清空。只寫玩家感受得到的，imm 的指令不寫（使用者選的）。

    uv run python -m mud.patchnote since          # 上次發過之後的 commit（寫草稿用）
    uv run python -m mud.patchnote send --dry-run # 試跑：印出會發的幾則，不發、不記
    uv run python -m mud.patchnote send           # 發到 Discord，記進紀錄
    uv run python -m mud.patchnote edit 訊息ID [--dry-run]   # 改發過的：先改紀錄裡那一筆，再把它送去蓋掉 Discord 上的（一樣先給使用者看）
    uv run python -m mud.patchnote forum 文章.md --title 標題 [--dry-run]   # 在討論區開一篇新文章（一樣先給使用者看）
文章改了不修改舊的（使用者 2026-11-20 選的）：使用者自己在 Discord 刪掉舊的，再重貼一篇。

webhook 網址（知道它就能發訊息到頻道，所以是密碼）放在 patch/discord-webhook（patch 通知的頻道）、
patch/discord-forum-webhook（討論區，webhook 要建在討論區頻道上），.gitignore 排除，不進 git。
只用標準庫，不 import 遊戲的模組。
"""
import argparse
import datetime
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PATCH_DIR = Path("patch")
DRAFT = PATCH_DIR / "草稿.md"
RECORD = PATCH_DIR / "紀錄.md"
WEBHOOK = PATCH_DIR / "discord-webhook"
FORUM_WEBHOOK = PATCH_DIR / "discord-forum-webhook"   # 討論區頻道的 webhook（使用者 2026-11-20 要的：在討論區發文章）
LIMIT = 2000                                # Discord 一則訊息最多 2000 個字
TITLE_LIMIT = 100                           # 討論區文章的標題最多 100 個字
USER_AGENT = "WindMud-patchnote/1.0"        # 坑：urllib 預設的 User-Agent 會被 Discord 前面的 Cloudflare 擋掉（403）
TIMEOUT = 15
SENT = re.compile(r"^<!-- 發到 ([0-9a-f]{7,40}) -->$", re.M)   # 紀錄裡每一筆的標記：這一筆發到哪個 commit
ENTRY = re.compile(r"^## .*\n<!-- 發到 [0-9a-f]{7,40} -->\n(?:<!-- 訊息 ID：([0-9? ]*) -->\n)?\n", re.M)   # 一筆的開頭，[1] 是訊息 ID
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


def paragraphs(text):
    """照空行切成段落；``` 包起來的區塊裡的空行不切（不然區塊會斷在兩則訊息中間，Discord 上就亂了）。"""
    out, current, fenced = [], [], False
    for line in text.split("\n"):
        if line.startswith("```"):
            fenced = not fenced
        if not line.strip() and not fenced:
            if current:
                out.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        out.append("\n".join(current))
    return out


def sections(text):
    """段落照標題（# 開頭）分節：一節是一個標題到下一個標題前（標題前面的那些自己一節）。"""
    groups = []
    for para in paragraphs(text.strip()):
        if para.startswith("#") or not groups:
            groups.append([para])
        else:
            groups[-1].append(para)
    return groups


def split(text, limit=LIMIT):
    """切成每則不超過 limit 個字：盡量整節放在同一則（標題和它底下的內容不分開），一節太長再照段落（空行）切，
    一段太長再照行切，一行太長才硬切。"""
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

    for group in sections(text):
        if add("\n\n".join(group), "\n\n"):
            continue
        for para in group:
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


def post(url, content, thread_name=None, thread_id=None):
    """發一則訊息到 Discord（webhook），回傳 Discord 回的訊息（wait=true）。
    thread_name：在討論區開一篇新文章（標題），回傳的 channel_id 是文章的編號；thread_id：接在那篇文章底下。"""
    payload = {"content": content, **({"thread_name": thread_name} if thread_name else {})}
    query = urllib.parse.urlencode({"wait": "true", **({"thread_id": thread_id} if thread_id else {})})
    return call(f"{url}?{query}", payload)


def call(url, payload, method="POST"):
    """送一個要求給 Discord，回傳它回的 JSON（沒有內容是 {}）。"""
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method=method,
                                     headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read() or b"{}")
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
    ids = [str(post(url, chunk).get("id", "?")) for chunk in chunks]   # Discord 的訊息 ID（使用者 2026-11-20 要的：以後要找、要刪用）
    old = record.read_text(encoding="utf-8") if record.exists() else RECORD_HEAD
    today = datetime.date.today().isoformat()
    span = f"{start}..{head}" if start else f"到 {head}"
    record.write_text(f"{old.rstrip()}\n\n## {today}（{span}）\n<!-- 發到 {head} -->\n<!-- 訊息 ID：{' '.join(ids)} -->\n\n{text}\n",
                      encoding="utf-8")
    draft.write_text("", encoding="utf-8")
    return chunks


def entry_of(message_id, record=RECORD):
    """紀錄裡記著這個訊息 ID 的那一筆：(這一筆的全部 ID, 內容)。"""
    text = record.read_text(encoding="utf-8") if record.exists() else ""
    heads = list(ENTRY.finditer(text))
    for i, head in enumerate(heads):
        ids = (head[1] or "").split()
        if message_id in ids:
            end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
            return ids, text[head.end():end].strip()
    raise PatchError(f"{record} 裡找不到訊息 ID {message_id}")


def edit(message_id, dry_run=False, record=RECORD, webhook=WEBHOOK):
    """把 Discord 上發過的那一筆改成紀錄裡現在寫的（先改 patch/紀錄.md 那一筆，再跑這個）。
    message_id 是那一筆的任何一個 ID；回傳 [(ID, 內容)]。Discord 只能改內容、不能多一則或少一則。"""
    ids, text = entry_of(message_id, record)
    chunks = split(text)
    if "?" in ids or len(chunks) != len(ids):
        raise PatchError(f"這一筆發的時候是 {len(ids)} 則（ID：{' '.join(ids)}），改完切成 {len(chunks)} 則："
                         "則數不一樣改不了，要在 Discord 刪掉再重發")
    pairs = list(zip(ids, chunks))
    if dry_run:
        return pairs
    url = webhook_url(webhook)
    for message, chunk in pairs:
        call(f"{url}/messages/{message}", {"content": chunk}, method="PATCH")
    return pairs


def forum(path, title, dry_run=False, webhook=FORUM_WEBHOOK):
    """在討論區開一篇新文章：path 是文章（Markdown），title 是標題。回傳發了（或試跑會發）的幾則。
    超過 2000 字就切開（split()）：第一則是文章本體，後面的接在同一篇文章底下。不記紀錄。"""
    text = Path(path).read_text(encoding="utf-8").strip() if Path(path).exists() else ""
    if not text:
        raise PatchError(f"{path} 是空的或找不到，沒有東西可以發")
    title = title.strip()
    if not title:
        raise PatchError("要有標題（--title）")
    if len(title) > TITLE_LIMIT:
        raise PatchError(f"標題最多 {TITLE_LIMIT} 個字，現在是 {len(title)} 個字")
    chunks = split(text)
    if dry_run:
        return chunks
    url = webhook_url(webhook)
    thread = post(url, chunks[0], thread_name=title).get("channel_id")
    if len(chunks) > 1 and not thread:
        raise PatchError("Discord 沒有回文章的編號，後面幾則接不上去（webhook 是不是建在討論區頻道上？）")
    for chunk in chunks[1:]:
        post(url, chunk, thread_id=thread)
    return chunks


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m mud.patchnote", description="Discord 的 patch 通知")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("since", help="上次發過之後的 commit")
    p = sub.add_parser("send", help="把 patch/草稿.md 發到 Discord")
    p.add_argument("--dry-run", action="store_true", help="只印出會發的內容，不發、不記")
    f = sub.add_parser("forum", help="在討論區開一篇新文章")
    f.add_argument("file", help="文章（Markdown）")
    f.add_argument("--title", required=True, help=f"標題（最多 {TITLE_LIMIT} 個字）")
    f.add_argument("--dry-run", action="store_true", help="只印出會發的內容，不發")
    e = sub.add_parser("edit", help="把 Discord 上發過的那一筆改成 patch/紀錄.md 現在寫的")
    e.add_argument("id", help="那一筆的訊息 ID（紀錄裡的「訊息 ID」）")
    e.add_argument("--dry-run", action="store_true", help="只印出會改成什麼，不改")
    args = parser.parse_args(argv)
    try:
        if args.action == "since":
            print(since() or "上次發過之後沒有新的 commit。")
            return 0
        if args.action == "edit":
            pairs = edit(args.id, dry_run=args.dry_run)
            for message, chunk in pairs:
                print(f"----- 訊息 {message}（{len(chunk)} 字） -----\n{chunk}")
            print("試跑：沒有改。" if args.dry_run else f"改好了，共 {len(pairs)} 則。")
            return 0
        if args.action == "forum":
            chunks = forum(args.file, args.title, dry_run=args.dry_run)
        else:
            chunks = send(dry_run=args.dry_run)
    except PatchError as e:
        print(e, file=sys.stderr)
        return 1
    for i, chunk in enumerate(chunks, 1):
        print(f"----- 第 {i}／{len(chunks)} 則（{len(chunk)} 字） -----\n{chunk}")
    if args.dry_run:
        print("試跑：沒有發" + ("。" if args.action == "forum" else "，也沒有記。"))
    elif args.action == "forum":
        print(f"發好了：討論區的新文章「{args.title.strip()}」，共 {len(chunks)} 則。")
    else:
        print(f"發好了，共 {len(chunks)} 則，記進 {RECORD}。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
