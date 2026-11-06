"""處理玩家輸入的指令：照 COMMANDS 的順序，找第一個用輸入開頭的指令。"""
from .. import act, pager, scripts
from ..characters import Position as P
from . import combat, doors, imm, items, skills, system
from . import help as help_command          # 不叫 help：名字會蓋掉 Python 內建的 help()

# 指令表：(指令, 函式, 最低姿勢)。輸入的字照這個順序比對，第一個用它開頭的指令就是答案（c 會找到 chat）。
# 要改優先順序，調整這裡的順序就好；新指令加在後面，原本的縮寫才不會變。
# 最低姿勢照 C 版的指令表（睡覺時哪些能用是使用者確認過的判斷，表在玩家角色手冊「姿勢和指令」）：
# 系統類（chat、tell、who、score、train、quit…）睡著也能用；look、say、weather、門的指令要醒著；走路要站著、沒在打架。
COMMANDS = [
    # 方向放最前面：n、e、s、w、u、d 都是走路。休息、睡覺、戰鬥中都不能走（照 C 版；戰鬥中要用 flee）
    ("north", system.do_north, P.STANDING),
    ("east", system.do_east, P.STANDING),
    ("south", system.do_south, P.STANDING),
    ("west", system.do_west, P.STANDING),
    ("up", system.do_up, P.STANDING),
    ("down", system.do_down, P.STANDING),
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
    ("kill", combat.do_kill, P.FIGHTING),       # k；休息、睡覺不能用（照 C 版）
    ("skills", skills.do_skills, P.DEAD),       # sk；跟 score 一樣什麼姿勢都能看
    ("help", help_command.do_help, P.DEAD),     # h；什麼姿勢都能看，說明在 help/help.json
    ("use", skills.do_use, P.FIGHTING),         # us（u 還是 up、un 是 unlock）；放技能，可以開打；休息、睡覺不能用
    # 物品（照 C 版的最低姿勢：拿、丟、穿、脫要醒著，打架中可以；看背包、裝備什麼姿勢都行）
    ("get", items.do_get, P.RESTING),           # g
    ("drop", items.do_drop, P.RESTING),         # d 還是 down，dr 才是 drop
    ("wear", items.do_wear, P.RESTING),         # wea 還是 weather，要打完整的 wear
    ("remove", items.do_remove, P.RESTING),     # r、re 還是 reply、res 是 rest，rem 才是 remove
    ("inventory", items.do_inventory, P.DEAD),  # i、inv
    ("equipment", items.do_equipment, P.DEAD),  # e 還是 east，eq 才是 equipment
    ("examine", items.do_examine, P.RESTING),   # ex；只看背包和身上的（照 C 版要醒著）
    ("flee", combat.do_flee, P.FIGHTING),       # f；戰鬥中逃跑（照 C 版的最低姿勢）
    ("give", items.do_give, P.RESTING),         # g 還是 get，gi 才是 give（照 C 版的最低姿勢）
    ("config", system.do_config, P.DEAD),       # co；什麼姿勢都能用（照 C 版）
    ("!", system.do_again, P.DEAD),             # 重複上一個指令：command() 先換掉（again()），還沒打過指令才會跑到這裡
]

# 管理員（imm）才找得到的指令，接在 COMMANDS 後面找，原本的縮寫都不受影響
IMM_COMMANDS = [
    ("advance", imm.do_advance, P.DEAD),
    ("slay", imm.do_slay, P.DEAD),
    ("oload", imm.do_oload, P.DEAD),            # o 還是 open，ol 才是 oload
    ("ostat", imm.do_ostat, P.DEAD),            # os
    ("mstat", imm.do_mstat, P.DEAD),            # m
    ("restore", imm.do_restore, P.DEAD),        # res 還是 rest，resto 才是 restore
    ("affect", imm.do_affect, P.DEAD),          # a 還是 advance，af 才是 affect
    ("sset", imm.do_sset, P.DEAD),              # s 還是 south、sa 是 say…，ss 才是 sset
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


def _first(word, is_imm):
    """指令表裡第一個用 word 開頭的那一筆 (指令, 函式, 最低姿勢)；找不到是 None。is_imm 才會找 IMM_COMMANDS。"""
    for entry in COMMANDS + (IMM_COMMANDS if is_imm else []):
        if entry[0].startswith(word):
            return entry
    return None


def lookup(word, is_imm=False):
    """找第一個用 word 開頭的指令，回傳 (函式, 最低姿勢)；找不到是 None。"""
    entry = _first(word, is_imm)
    return entry[1:] if entry else None


def command_name(word, is_imm=False):
    """找第一個用 word 開頭的指令，回傳它的名稱（help 用）；找不到是 None。"""
    entry = _first(word, is_imm)
    return entry[0] if entry else None


def find(word, is_imm=False):
    """找第一個用 word 開頭的指令的函式；找不到回傳 None。"""
    found = lookup(word, is_imm)
    return found[0] if found else None


def command(ch, line):
    """處理角色 ch 下的一行指令（玩家或 NPC 都可以）。回傳 False 代表要斷線。

    分頁中打的字先給 pager.key()（按鍵就到此為止）。送給他的回覆先收起來（pager.collect），跑完由 pager.show() 決定要不要分頁、補 prompt。
    """
    if pager.key(ch, line):
        return True
    line = again(ch, line)
    verb, _, arg = line.partition(" ")
    verb, arg = verb.lower(), arg.strip()
    ch.sent = ch.notified = False
    with act.gathering():                   # 這個指令送給別人的訊息合成一段，每人一個 prompt（使用者要的）
        with pager.collect(ch) as reply:
            keep = run(ch, line, verb, arg)
        text = "".join(reply)
        if not keep:                        # 要斷線（quit）：收起來的字送出去，不補 prompt
            if text:
                ch.send(text)
            return False
        # 有送出訊息就先空一行再補 prompt；只按 Enter（沒有訊息）就直接補（使用者要的）
        pager.show(ch, text)
    return True


def again(ch, line):
    """「!」開頭的一行換成上一個指令（照 C 版，使用者要的）；其他有字的記成上一個指令。

    只按 Enter、「!」本身不記（C 版連空行都記，那樣按完 Enter 再打 ! 就什麼都不做）。還沒打過指令就照打的跑，由 do_again() 說。
    分頁的按鍵不會走到這裡（pager.key() 先處理掉），所以翻頁的 c、r 不會被記成上一個指令。
    """
    if not hasattr(ch, "last_line"):        # 生物沒有（腳本讓牠打的指令不用重複）
        return line
    if line.strip().startswith("!"):
        return ch.last_line or line
    if line.strip():
        ch.last_line = line
    return line


def run(ch, line, verb, arg):
    """找到指令、檢查姿勢、執行。回傳 False 代表要斷線。"""
    if not line:
        return True
    name = command_name(verb, getattr(ch, "imm", False))
    scripts.commanding.append(ch)           # 腳本給他的訊息當作這個指令的回覆（prompt 由 command() 補）
    try:
        # 腳本的 on_command：遊戲處理之前，房間先、再房間裡的生物；有一個擋住就不照平常處理（quit 擋不住，使用者選的）
        if name == "quit" or not scripts.fire(ch.room, "on_command", ch, ch, name or verb, arg):
            found = lookup(verb, getattr(ch, "imm", False))
            if found is None:
                ch.send("什麼？\n")
            elif ch.position < found[1]:        # 姿勢不夠，例如睡著時 look
                ch.send(REFUSALS[ch.position] + "\n")
            elif found[0](ch, arg) is False:
                return False
    finally:
        scripts.commanding.pop()
    return True
