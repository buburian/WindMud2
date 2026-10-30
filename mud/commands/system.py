"""系統類指令。每個指令都長 do_xxx(writer, name, arg)，回傳 False 代表要斷線。"""
from ..act import TO_CHAR, TO_VICT, act
from ..players import players, send
from ..save import save_player


def do_chat(writer, name, arg):
    if not arg:
        send(writer, "要說什麼？\n")
    else:
        act("你聊天：$t", writer, t=arg, to=TO_CHAR)
        for other in players:               # chat 是全服頻道，自己走訪，有房間後也不受影響
            if other is not writer:
                act("$n 聊天：$t", writer, vch=other, t=arg, to=TO_VICT)


def do_quit(writer, name, arg):
    save_player(name)
    send(writer, "再見。\n")
    # 移出玩家名單、關連線都在 server.handle() 的 finally，這裡不重複做
    return False
