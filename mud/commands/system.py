"""系統類指令。每個指令都長 do_xxx(writer, name, arg)，回傳 False 代表要斷線。"""
from ..config import PROMPT
from ..players import players, send
from ..save import save_player


def do_chat(writer, name, arg):
    if not arg:
        send(writer, "要說什麼？\n")
    else:
        send(writer, f"你聊天：{arg}\n")
        for other in players:
            if other is not writer:
                # 先換行，才不會接在對方的 prompt 後面；說完再補回對方的 prompt
                send(other, f"\n{name} 聊天：{arg}\n{PROMPT}")


def do_quit(writer, name, arg):
    save_player(name)
    send(writer, "再見。\n")
    # 移出玩家名單、關連線都在 server.handle() 的 finally，這裡不重複做
    return False
