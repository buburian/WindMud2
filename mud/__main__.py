"""啟動伺服器：uv run python -m mud"""
import argparse
import asyncio
import logging

from . import zones
from .config import AREA_DIR, ENCODING, START_ROOM
from .log import setup
from .server import handle

log = logging.getLogger(__name__)


async def main():
    p = argparse.ArgumentParser(description="最小的 MUD telnet 原型")
    p.add_argument("--host", default="127.0.0.1", help="給別台電腦連就用 0.0.0.0")
    p.add_argument("--port", type=int, default=4000)
    args = p.parse_args()
    setup()                                         # 放在 parse_args 後面，--help 才不會建出 logs/
    try:
        zones.load(AREA_DIR)
    except ValueError as e:
        log.error(f"區域載入失敗：{e}")
        raise SystemExit(1)
    if START_ROOM not in zones.world.rooms:
        log.error(f"起始房間 {START_ROOM} 不在世界區域裡")
        raise SystemExit(1)
    zones.start()
    server = await asyncio.start_server(handle, args.host, args.port)
    log.info(f"伺服器開在 {args.host}:{args.port}，編碼 {ENCODING}。按 Ctrl+C 結束。")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
