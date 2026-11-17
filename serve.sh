#!/usr/bin/env bash
# 開伺服器給別台電腦連（預設 0.0.0.0:8080），掛掉就自動重開。按 Ctrl+C 結束。
#
# 用法：./serve.sh
#       PORT=4000 ./serve.sh        # 換 port（HOST 也可以這樣換）
#
# 開機不到 QUICK 秒就結束，多半是區域檔、說明檔寫錯，或 port 被占用：重開也一樣會掛，所以停下來，不一直重開。
cd "$(dirname "$0")" || exit 1

HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8080}
WAIT=5        # 掛掉後等幾秒再重開
QUICK=10      # 開機不到幾秒就結束：不重開

say() { echo "[serve.sh] $(date '+%F %T') $*"; }

trap 'echo; say "結束。"; exit 0' INT TERM HUP

while true; do
  start=$(date +%s)
  say "開伺服器 ${HOST}:${PORT}"
  uv run python -m mud --host "$HOST" --port "$PORT"
  code=$?
  ran=$(( $(date +%s) - start ))
  say "伺服器結束了（結束代碼 ${code}，跑了 ${ran} 秒）"
  if [ "$ran" -lt "$QUICK" ]; then
    say "開機不到 ${QUICK} 秒就結束：多半是區域檔、說明檔寫錯，或 port 被占用。先不重開，看上面的錯誤。"
    exit 1
  fi
  say "${WAIT} 秒後重開"
  sleep "$WAIT"
done
