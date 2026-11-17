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
