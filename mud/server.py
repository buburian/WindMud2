"""一條連線從登入到離線的流程。"""
import logging

from .characters import characters
from .commands import command
from .commands.system import look
from .config import PROMPT
from .players import Player, online_players, send
from .telnet import START, Telnet

log = logging.getLogger(__name__)


async def handle(reader, writer):
    tn = Telnet()
    me = None                                       # 登入後是這條連線的玩家（Player）
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
                if me is None:
                    if line:
                        me = Player(line, writer)
                        characters.append(me)
                        log.info(f"{me.name} 登入，目前 {len(online_players())} 人")
                        me.send(f"歡迎，{me.name}。\n" + look(me) + PROMPT)
                    else:
                        send(writer, "Login: ")
                elif not command(me, line):
                    return
            await writer.drain()
    except OSError:                                 # 坑：對方直接關掉連線，不要讓整台伺服器掛掉
        pass
    finally:
        if me is not None:
            characters.remove(me)
            log.info(f"{me.name} 離線，目前 {len(online_players())} 人")
            for p in online_players():              # 別人的 reply 還指著這個玩家，清掉記憶體才放得掉
                if p.reply is me:
                    p.reply = None
        writer.close()
