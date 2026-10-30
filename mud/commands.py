"""處理玩家輸入的指令。"""
from .config import PROMPT
from .players import players, send


def command(writer, name, line):
    """處理一行指令。回傳 False 代表要斷線。"""
    verb, _, arg = line.partition(" ")
    verb, arg = verb.lower(), arg.strip()
    if not line:
        pass
    elif verb == "chat":
        if not arg:
            send(writer, "要說什麼？\n")
        else:
            send(writer, f"你聊天：{arg}\n")
            for other in players:
                if other is not writer:
                    # 先換行，才不會接在對方的 prompt 後面；說完再補回對方的 prompt
                    send(other, f"\n{name} 聊天：{arg}\n{PROMPT}")
    elif verb == "quit":
        send(writer, "再見。\n")
        return False
    else:
        send(writer, "什麼？\n")
    send(writer, PROMPT)
    return True
