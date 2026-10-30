"""系統類指令。每個指令都長 do_xxx(writer, name, arg)，回傳 False 代表要斷線。"""
from ..act import TO_CHAR, TO_VICT, act
from ..players import players, send
from ..save import save_player


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
