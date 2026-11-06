"""分頁（玩家角色手冊「設定」，C 版 comm.c 的 show_string）：一個指令的回覆超過每頁幾行（player.page_lines），先送一頁，停下來等按鍵。

- 只分頁「指令的回覆」：command() 跑的時候，送給下指令的玩家的字收在 ch.capture（collect()），跑完交給 show()。
  腳本、生物在他指令當下回的話也算這個回覆。
- 別人、戰鬥主動送來的（act.notify）不收、不分頁，照樣馬上送（照 C 版）；分頁中 ch.prompt() 是分頁提示（Player.prompt）。
- 分頁中打的字先給 key()：Enter、c 下一頁；r 重印這一頁；b 重印上一頁；q 結束；
  其他：結束分頁、這一行照常當指令（使用者選的，C 版是吃掉）。最後一頁送完就結束，補一般的 prompt。
- 分頁的狀態不存檔（每頁幾行有存）。
"""
import contextlib

PROMPT = "【請按下 (c)繼續, (r)重印本頁, (b)重印上頁, (q)離開, 或 RETURN】："   # 照 C 版
NEXT, AGAIN, BACK, QUIT = ("", "c"), "r", "b", "q"


class Pages:
    """還沒看完的回覆：每一行（不含換行）、每頁幾行、現在這一頁從第幾行開始。"""

    def __init__(self, lines, size):
        self.lines, self.size, self.start = lines, size, 0


def capturing(ch):
    """要不要收 ch 這個指令的回覆：有分頁設定的玩家，而且還沒在收（腳本讓別的角色下指令時不會再收一次）。"""
    return hasattr(ch, "page_lines") and ch.capture is None


@contextlib.contextmanager
def collect(ch):
    """command() 用：這個指令送給 ch 的字先收起來，yield 一個 list，跑完放進收到的整段（一個字串）。

    坑：出錯時也要把收起來的字送出去（不然指令出錯連前面的訊息都看不到），所以在 finally 裡處理。
    """
    reply = []
    if not capturing(ch):
        yield reply
        return
    ch.capture = []
    ok = False
    try:
        yield reply
        ok = True
    finally:
        text, ch.capture = "".join(ch.capture), None
        if ok:
            reply.append(text)
        elif text:
            ch.send(text)


def show(ch, text):
    """指令跑完：text 是收起來的回覆。不超過一頁整段送；超過就送第一頁、記住剩下的。最後補 prompt（有訊息就先空一行）。"""
    lines = split(text)
    if hasattr(ch, "page_lines") and len(lines) > ch.page_lines:
        ch.pages = Pages(lines, ch.page_lines)
        send_page(ch)
        return
    ch.send(text + ("\n" if ch.sent else "") + ch.prompt())


def split(text):
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def send_page(ch):
    """送現在這一頁；是最後一頁就結束分頁（後面補一般的 prompt），不然補分頁提示。"""
    pages = ch.pages
    page = pages.lines[pages.start:pages.start + pages.size]
    if pages.start + pages.size >= len(pages.lines):
        ch.pages = None
    ch.send("\n".join(page) + "\n\n" + ch.prompt())


def key(ch, line):
    """分頁中打的一行：是按鍵就處理掉、回傳 True；不是分頁中、或打了別的（結束分頁），回傳 False，照常當指令。"""
    pages = getattr(ch, "pages", None)
    if pages is None:
        return False
    word = line.strip().lower()
    if word in NEXT:
        pages.start += pages.size
    elif word == BACK:
        pages.start = max(0, pages.start - pages.size)
    elif word == QUIT:
        ch.pages = None
        ch.send(ch.prompt())
        return True
    elif word != AGAIN:
        ch.pages = None                     # 打了別的：不看剩下的，這一行照常當指令（使用者選的）
        return False
    send_page(ch)
    return True
