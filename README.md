# MUD 伺服器（Python 原型）

用 Big5 編碼的 telnet MUD 伺服器原型。目前可以登入、用 `chat` 聊天、用 `quit` 離開。

## 需要的東西

- macOS 和 Homebrew
- uv：`brew install uv`

第一次執行時，uv 會自動下載 Python 3.15（版本寫在 `.python-version`）和測試用的 pytest。

## 開啟伺服器

在專案資料夾裡執行：

```sh
uv run python -m mud
```

- 預設開在 `127.0.0.1:4000`，只有這台電腦連得到。
- 換 port：`uv run python -m mud --port 4055`
- 讓別台電腦也能連：`uv run python -m mud --host 0.0.0.0`
- 視窗會顯示誰登入、誰離線。按 Ctrl+C 關閉。
- 改了程式之後，要重開伺服器才會生效。

## 自動測試

```sh
uv run pytest
```

## 在 Mac 上連線測試

伺服器只講 Big5。Mac 的終端機維持 UTF-8，中間用 luit 把 UTF-8 和 Big5 互相轉換。

### 1. 安裝工具（只要做一次）

```sh
brew install telnet luit
```

macOS 從 10.13 起就不再內建 telnet，所以要自己裝。

### 2. 連線

伺服器開著，另外開一個終端機視窗：

```sh
luit -encoding Big5 telnet 127.0.0.1 4000
```

看到 `Login:` 就輸入名字。

### 3. 試試看

| 輸入 | 結果 |
|---|---|
| `chat 你好` | 所有在線的人都會看到你說的話 |
| `quit` | 離開遊戲 |

指令可以縮寫：系統會照指令表的順序，找第一個用你輸入的字開頭的指令。例如 `c` 就是 `chat`，`q` 就是 `quit`。

想測兩個人聊天：再開一個視窗，用同一行指令連線，換一個名字登入。

### 注意

- **終端機不要切成 Big5。** 在 macOS 26 上，Big5 視窗用輸入法打中文會整個卡死，iTerm2 和內建終端機都會。
- 打錯中文時，倒退鍵要按兩次才會刪掉一個中文字。只按一次會送出半個字，變成亂碼。
- 不用 luit、直接 telnet 的話，中文會是亂碼。
