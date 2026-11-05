"""處理玩家輸入的指令：照 COMMANDS 的順序，找第一個用輸入開頭的指令。"""
from ..characters import Position as P
from . import doors, imm, system

# 指令表：(指令, 函式, 最低姿勢)。輸入的字照這個順序比對，第一個用它開頭的指令就是答案（c 會找到 chat）。
# 要改優先順序，調整這裡的順序就好；新指令加在後面，原本的縮寫才不會變。
# 最低姿勢照 C 版的指令表（睡覺時哪些能用是使用者確認過的判斷，表在玩家角色手冊「姿勢和指令」）：
# 系統類（chat、tell、who、score、train、quit…）睡著也能用；look、say、weather、門的指令要醒著；走路要站起來。
COMMANDS = [
    # 方向放最前面：n、e、s、w、u、d 都是走路。休息、睡覺不能走；
    # 戰鬥中照舊可以走：C 版戰鬥中不能走（要用 flee），但還沒有 flee，做 flee 時改成 STANDING
    ("north", system.do_north, P.FIGHTING),
    ("east", system.do_east, P.FIGHTING),
    ("south", system.do_south, P.FIGHTING),
    ("west", system.do_west, P.FIGHTING),
    ("up", system.do_up, P.FIGHTING),
    ("down", system.do_down, P.FIGHTING),
    ("look", system.do_look, P.RESTING),
    ("chat", system.do_chat, P.SLEEPING),
    ("tell", system.do_tell, P.SLEEPING),
    ("reply", system.do_reply, P.SLEEPING),
    ("quit", system.do_quit, P.DEAD),
    ("weather", system.do_weather, P.RESTING),  # w 還是 west，wea 才是 weather
    ("score", system.do_score, P.DEAD),         # s 還是 south，sc 才是 score
    ("train", system.do_train, P.SLEEPING),     # t 還是 tell，tr 才是 train
    ("rest", system.do_rest, P.SLEEPING),       # r、re 還是 reply，res 才是 rest
    ("sleep", system.do_sleep, P.SLEEPING),     # sl
    ("stand", system.do_stand, P.SLEEPING),     # st
    ("who", system.do_who, P.DEAD),             # wh
    ("say", system.do_say, P.RESTING),          # sa
    ("save", system.do_save, P.DEAD),           # sa 還是 say，sav 才是 save
    ("open", doors.do_open, P.RESTING),         # o
    ("close", doors.do_close, P.RESTING),       # c 還是 chat，cl 才是 close
    ("lock", doors.do_lock, P.RESTING),         # l、lo 還是 look，loc 才是 lock
    ("unlock", doors.do_unlock, P.RESTING),     # u 還是 up，un 才是 unlock
]

# 管理員（imm）才找得到的指令，接在 COMMANDS 後面找，原本的縮寫都不受影響
IMM_COMMANDS = [
    ("advance", imm.do_advance, P.DEAD),
]

# 姿勢不夠時的訊息（照 C 版 interp.c）
REFUSALS = {
    P.DEAD: "不要再欺騙自己了，你已經死亡了。",
    P.MORTAL: "你受傷太嚴重了。",
    P.INCAP: "你受傷太嚴重了。",
    P.STUNNED: "你現在還昏迷不醒。",
    P.SLEEPING: "在你的睡夢中嗎？",
    P.RESTING: "嗯... 你正在休息耶..。",
    P.FIGHTING: "不行!!你還在戰鬥狀態中!!",
}


def lookup(word, is_imm=False):
    """找第一個用 word 開頭的指令，回傳 (函式, 最低姿勢)；找不到是 None。is_imm 才會找 IMM_COMMANDS。"""
    for cmd, func, position in COMMANDS + (IMM_COMMANDS if is_imm else []):
        if cmd.startswith(word):
            return func, position
    return None


def find(word, is_imm=False):
    """找第一個用 word 開頭的指令的函式；找不到回傳 None。"""
    found = lookup(word, is_imm)
    return found[0] if found else None


def command(ch, line):
    """處理角色 ch 下的一行指令（玩家或 NPC 都可以）。回傳 False 代表要斷線。"""
    verb, _, arg = line.partition(" ")
    verb, arg = verb.lower(), arg.strip()
    ch.sent = False
    if line:
        found = lookup(verb, getattr(ch, "imm", False))
        if found is None:
            ch.send("什麼？\n")
        elif ch.position < found[1]:            # 姿勢不夠，例如睡著時 look
            ch.send(REFUSALS[ch.position] + "\n")
        elif found[0](ch, arg) is False:
            return False
    # 有送出訊息就先空一行再補 prompt；只按 Enter（沒有訊息）就直接補（使用者要的）
    ch.send(("\n" if ch.sent else "") + ch.prompt())
    return True
