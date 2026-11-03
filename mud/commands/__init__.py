"""處理玩家輸入的指令：照 COMMANDS 的順序，找第一個用輸入開頭的指令。"""
from ..config import PROMPT
from . import system

# 指令表。輸入的字照這個順序比對，第一個用它開頭的指令就是答案（c 會找到 chat）。
# 要改優先順序，調整這裡的順序就好。
COMMANDS = [
    ("north", system.do_north),             # 方向放最前面：n、e、s、w、u、d 都是走路
    ("east", system.do_east),
    ("south", system.do_south),
    ("west", system.do_west),
    ("up", system.do_up),
    ("down", system.do_down),
    ("look", system.do_look),
    ("chat", system.do_chat),
    ("tell", system.do_tell),
    ("reply", system.do_reply),
    ("quit", system.do_quit),
    ("weather", system.do_weather),         # 放最後：w 還是 west，wea 才是 weather
]


def find(word):
    """找第一個用 word 開頭的指令；找不到回傳 None。"""
    for cmd, func in COMMANDS:
        if cmd.startswith(word):
            return func
    return None


def command(ch, line):
    """處理角色 ch 下的一行指令（玩家或 NPC 都可以）。回傳 False 代表要斷線。"""
    verb, _, arg = line.partition(" ")
    verb, arg = verb.lower(), arg.strip()
    if line:
        func = find(verb)
        if func is None:
            ch.send("什麼？\n")
        elif func(ch, arg) is False:
            return False
    ch.send(PROMPT)
    return True
