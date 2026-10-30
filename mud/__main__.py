"""啟動伺服器：uv run python -m mud"""
import argparse
import asyncio

from .config import ENCODING
from .server import handle


async def main():
    p = argparse.ArgumentParser(description="最小的 MUD telnet 原型")
    p.add_argument("--host", default="127.0.0.1", help="給別台電腦連就用 0.0.0.0")
    p.add_argument("--port", type=int, default=4000)
    args = p.parse_args()
    server = await asyncio.start_server(handle, args.host, args.port)
    print(f"伺服器開在 {args.host}:{args.port}，編碼 {ENCODING}。按 Ctrl+C 結束。", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
