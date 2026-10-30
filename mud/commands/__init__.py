"""處理玩家輸入的指令：照 COMMANDS 的順序，找第一個用輸入開頭的指令。"""
from ..config import PROMPT
from ..players import send
from . import system

# 指令表。輸入的字照這個順序比對，第一個用它開頭的指令就是答案（c 會找到 chat）。
# 要改優先順序，調整這裡的順序就好。
COMMANDS = [
    ("chat", system.do_chat),
    ("quit", system.do_quit),
]


def find(word):
    """找第一個用 word 開頭的指令；找不到回傳 None。"""
    for cmd, func in COMMANDS:
        if cmd.startswith(word):
            return func
    return None


def command(writer, name, line):
    """處理一行指令。回傳 False 代表要斷線。"""
    verb, _, arg = line.partition(" ")
    verb, arg = verb.lower(), arg.strip()
    if line:
        func = find(verb)
        if func is None:
            send(writer, "什麼？\n")
        elif func(writer, name, arg) is False:
            return False
    send(writer, PROMPT)
    return True
