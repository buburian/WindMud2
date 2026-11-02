"""開區域編輯器：uv run python -m mud.builder，再用瀏覽器打開 http://127.0.0.1:1234"""
import argparse
import logging
from pathlib import Path

from rich.logging import RichHandler

from ..config import BUILDER_DIR, BUILDER_PORT
from .server import make_server

log = logging.getLogger(__name__)


def main():
    p = argparse.ArgumentParser(description="區域編輯器")
    p.add_argument("--host", default="127.0.0.1", help="給別台電腦用就寫 0.0.0.0（沒有登入，連得到的人都能改檔）")
    p.add_argument("--port", type=int, default=BUILDER_PORT)
    args = p.parse_args()
    # 紀錄只印在畫面，不寫進 logs/：那是遊戲伺服器的，兩個程式寫同一個檔會互相干擾
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[RichHandler()])
    Path(BUILDER_DIR).mkdir(exist_ok=True)
    server = make_server(args.host, args.port, BUILDER_DIR)
    log.info(f"區域編輯器開在 http://{args.host}:{args.port}，區域檔放在 {BUILDER_DIR}/。按 Ctrl+C 結束。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
