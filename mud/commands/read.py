"""read：讀系統的訊息（使用者 2026-11-20 要的）。現在有系統公告（read announce）；之後的信件（mail）這類也加在 TOPICS。"""
from .. import announce

NOTHING = "現在沒有系統公告。"


def read_announce(ch):
    ch.send((announce.current() or NOTHING) + "\n")


TOPICS = {"announce": ("系統公告", read_announce)}      # 名字（可以只打開頭）→ (說明, 讀的函式)；之後的 mail 加在這裡
WHAT = "要讀什麼？可以讀的："


def do_read(ch, arg):
    """read <東西>：讀系統的訊息，名字可以只打開頭（read ann）。沒打或找不到就列出可以讀的。"""
    word = arg.split()[0].lower() if arg.split() else ""
    found = next((fn for name, (_what, fn) in TOPICS.items() if word and name.startswith(word)), None)
    if found is None:
        ch.send(WHAT + "\n" + "\n".join(f"  {name}：{what}" for name, (what, _fn) in TOPICS.items()) + "\n")
        return
    found(ch)
