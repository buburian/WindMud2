"""一條連線從登入到離線的流程。"""
import logging

from .characters import characters
from .commands import command
from .fight import stop_fighting
from .login import Connection, login
from .players import online_players
from .save import save_player
from .telnet import START

log = logging.getLogger(__name__)


async def handle(reader, writer):
    conn = Connection(reader, writer)
    me = None                                       # 登入後是這條連線的玩家（Player）
    writer.write(START)                             # 協商是控制碼，直接寫 bytes，不能經過 encode()
    try:
        me = await login(conn)                      # 問名字、密碼，或建立新角色
        if me is None:                              # 登入途中斷線，或密碼錯
            return
        while True:
            line = await conn.readline()
            if line is None:                        # 對方斷線
                break
            if not command(me, line):
                return
    except OSError:                                 # 坑：對方直接關掉連線，不要讓整台伺服器掛掉
        pass
    finally:
        # 重複登入時角色被新連線接手了（writer 換成新的）：這條舊連線只要關掉，不能把角色移出遊戲
        if me is not None and me.writer is writer:
            stop_fighting(me)
            try:
                save_player(me)                     # quit 和直接斷線都存
            except OSError:
                log.exception(f"{me.name} 存檔失敗")
            characters.remove(me)
            log.info(f"{me.name} 離線，目前 {len(online_players())} 人")
            for p in online_players():              # 別人的 reply 還指著這個玩家，清掉記憶體才放得掉
                if p.reply is me:
                    p.reply = None
        writer.close()
