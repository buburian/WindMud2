"""一條連線從登入到離線的流程。"""
from .commands import command
from .config import PROMPT
from .players import players, send
from .telnet import START, Telnet


async def handle(reader, writer):
    tn = Telnet()
    name = None
    writer.write(START)                             # 協商是控制碼，直接寫 bytes，不能經過 encode()
    send(writer, "Login: ")
    try:
        while True:
            data = await reader.read(4096)
            if not data:                            # 對方斷線
                break
            lines = tn.feed(data)
            if tn.replies:
                writer.write(bytes(tn.replies))
                tn.replies.clear()
            for line in lines:
                line = line.strip()
                if name is None:
                    if line:
                        name = line
                        players[writer] = name
                        print(f"{name} 登入，目前 {len(players)} 人", flush=True)
                        send(writer, f"歡迎，{name}。\n{PROMPT}")
                    else:
                        send(writer, "Login: ")
                elif not command(writer, name, line):
                    return
            await writer.drain()
    except OSError:                                 # 坑：對方直接關掉連線，不要讓整台伺服器掛掉
        pass
    finally:
        if players.pop(writer, None) is not None:
            print(f"{name} 離線，目前 {len(players)} 人", flush=True)
        writer.close()
