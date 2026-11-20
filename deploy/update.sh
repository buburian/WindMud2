#!/usr/bin/env bash
# 主機自己更新（windmud-update.timer 每分鐘跑一次；裝法見 README「自動部署」）。
# GitHub 的 release 分支是測試通過的版本（.github/workflows/test.yml 推的）：跟現在的不一樣就拉下來、重開 windmud。
# 開不起來就退回原本的版本，記在 .git/windmud-failed，那個版本不再試（不然每分鐘重開一次）。
# 坑：整支包在 main() 裡。git merge 會換掉這支檔案本身，bash 是邊讀邊跑的；包成函式，bash 會先整個讀完才開始跑。
set -euo pipefail

REPO="${REPO:-https://github.com/buburian/WindMud2.git}"
BRANCH="${BRANCH:-release}"
UV="${UV:-$HOME/.local/bin/uv}"
SERVICE="${SERVICE:-windmud}"
PORT="${PORT:-8080}"
WAIT="${WAIT:-30}"                          # 重開以後最多等幾秒 port 開起來
NOTICE="${NOTICE:-30}"                      # 先在遊戲裡通知，幾秒後才更新、重開（跟 mud/restart.py 的 NOTICE_SECONDS 一樣）

up() {
    # 服務是 active，而且 port 連得上，才算開起來（Type=simple 一啟動就是 active，開機檢查沒過也是）
    for _ in $(seq "$WAIT"); do
        sleep 1
        if systemctl is-active --quiet "$SERVICE" && (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then
            return 0
        fi
    done
    return 1
}

notice() {
    # 重開前先在遊戲裡通知（使用者 2026-11-20 要的）：送 SIGUSR1 給 python，伺服器跟線上的玩家說幾秒後重開，等那麼久再更新。
    # 送給 python、不送給 uv：服務的主程式是 uv（ExecStart 的 uv run），uv 不一定會轉送 SIGUSR1，沒接的程式收到會直接結束。
    # 坑：還沒有這個功能的舊版收到 SIGUSR1 也會直接結束（沒存檔）：先看現在的程式有沒有 mud/restart.py 的記號才送。
    # 伺服器沒在跑、找不到 python 就不通知、不等。
    local main pid
    grep -qs "WINDMUD_RESTART_NOTICE" mud/restart.py || return 0
    main=$(systemctl show -p MainPID --value "$SERVICE" 2>/dev/null || true)
    if [ -z "$main" ] || [ "$main" = 0 ]; then
        return 0
    fi
    pid=$(pgrep -P "$main" -f "python" | head -n 1 || true)
    if [ -z "$pid" ]; then
        return 0
    fi
    if kill -USR1 "$pid"; then
        echo "通知線上的玩家：$NOTICE 秒後重開"
        sleep "$NOTICE"
    fi
}

main() {
    cd "$(dirname "$0")/.."
    local failed new old
    failed="$(git rev-parse --git-dir)/windmud-failed"
    git fetch --quiet "$REPO" "$BRANCH"
    new=$(git rev-parse FETCH_HEAD)
    old=$(git rev-parse HEAD)
    if [ "$new" = "$old" ] || git merge-base --is-ancestor "$new" "$old"; then
        return 0                            # 沒有新版（release 比現在舊也一樣：不往回退）
    fi
    if [ "$(cat "$failed" 2>/dev/null)" = "$new" ]; then
        return 0                            # 這個版本上次開不起來：等下一個新版
    fi
    echo "更新 ${old:0:7} → ${new:0:7}：$(git log -1 --format=%s "$new")"
    notice                                  # 先通知、等一下，再換檔案（換了檔案，跑著的伺服器之後才 import 的模組會讀到新版）
    git merge --ff-only --quiet "$new"      # 主機上改過 git 裡的檔就會失敗、什麼都不動（set -e 在這裡結束）
    if "$UV" sync --locked --quiet && sudo systemctl restart "$SERVICE" && up; then
        rm -f "$failed"
        echo "開起來了：$(git log -1 --format='%h %s')"
        return 0
    fi
    echo "${new:0:7} 開不起來，退回 ${old:0:7}" >&2
    sudo journalctl -u "$SERVICE" -n 30 --no-pager >&2 || true
    echo "$new" > "$failed"
    git reset --hard --quiet "$old"
    "$UV" sync --locked --quiet
    sudo systemctl restart "$SERVICE"
    if up; then
        echo "退回 ${old:0:7}，開起來了"
    else
        echo "退回 ${old:0:7} 也開不起來" >&2
    fi
    return 1
}

main "$@"
