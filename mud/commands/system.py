"""系統類指令。每個指令都長 do_xxx(writer, name, arg)，回傳 False 代表要斷線。"""
from ..act import TO_CHAR, TO_ROOM, TO_VICT, act
from ..area import DIRECTIONS, REVERSE, rooms
from ..color import colorize
from ..players import players, send
from ..save import save_player


def do_look(writer, name, arg):
    send(writer, look(writer))


def look(writer):
    """自己所在房間的樣子：名稱、出口、描述、同房間的其他玩家。登入時也用這個。"""
    me = players[writer]
    room = rooms[me.room]
    exits = "".join(" {C" + DIRECTIONS[d] for d in DIRECTIONS if d in room.exits) or " 沒有"
    # 房間的文字是區域作者寫的，可以用顏色代碼；玩家名字是後面才接上去的，不會被轉
    text = colorize("{G【{Y" + room.name + "{G】{x\n{G【出口：" + exits + "{G】{x\n" + room.description)
    if not text.endswith("\n"):
        text += "\n"
    for w, p in players.items():
        if w is not writer and p.room == me.room:
            text += f"{p.name}站在這裡。\n"
    return text


def move(writer, direction):
    me = players[writer]
    to = rooms[me.room].exits.get(direction)
    if to is None:
        send(writer, "那裡不能走。\n")
        return
    act("$n朝$t離開。", writer, t=DIRECTIONS[direction], to=TO_ROOM)
    me.room = to
    act("$n從$t邊走了過來。", writer, t=DIRECTIONS[REVERSE[direction]], to=TO_ROOM)
    send(writer, look(writer))


def walk(direction):
    """做出「往 direction 走」的指令。"""

    def do_walk(writer, name, arg):
        move(writer, direction)

    return do_walk


do_north = walk("north")
do_east = walk("east")
do_south = walk("south")
do_west = walk("west")
do_up = walk("up")
do_down = walk("down")


def do_chat(writer, name, arg):
    if not arg:
        send(writer, "要說什麼？\n")
    else:
        act("{M你聊天：$t{x", writer, t=arg, to=TO_CHAR)
        for other in players:               # chat 是全服頻道，自己走訪，有房間後也不受影響
            if other is not writer:
                act("{M$n 聊天：$t{x", writer, vch=other, t=arg, to=TO_VICT)


def do_tell(writer, name, arg):
    target, _, msg = arg.partition(" ")
    msg = msg.strip()
    if not target or not msg:
        send(writer, "你想要告訴誰些什麼呢？\n")
        return
    victim = next((w for w, p in players.items() if p.name.lower() == target.lower()), None)
    if victim is None:
        send(writer, "沒有找到你想說話的對象。\n")
        return
    tell(writer, victim, msg)


def do_reply(writer, name, arg):
    victim = players[writer].reply
    if victim not in players:               # 沒人 tell 過你，或對方已經離線
        send(writer, "找不到你想回答的對象。\n")
        return
    if not arg:
        send(writer, "你想回答些什麼呢？\n")
        return
    tell(writer, victim, arg)


def tell(writer, victim, msg):
    """tell 和 reply 共用：雙方各看到一句，對方之後可以用 reply 回你。"""
    act("{G你告訴$N：$t{x", writer, vch=victim, t=msg, to=TO_CHAR)
    act("{G$n告訴你：$t{x", writer, vch=victim, t=msg, to=TO_VICT)
    players[victim].reply = writer


def do_quit(writer, name, arg):
    save_player(name)
    send(writer, "再見。\n")
    # 移出玩家名單、關連線都在 server.handle() 的 finally，這裡不重複做
    return False
