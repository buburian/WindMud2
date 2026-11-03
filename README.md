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
- 這些紀錄也會存到 `logs/` 資料夾。檔名是「日期_編號」，例如 `2026-10-30_001.log`。一個檔滿 5MB 就換下一個編號，最多留 30 個檔。
- 改了程式之後，要重開伺服器才會生效。

## 自動測試

```sh
uv run pytest
```

## 檢查區域檔

```sh
uv run python -m mud.areacheck                     # 檢查 areas/ 裡全部的區域檔
uv run python -m mud.areacheck areas/test.json     # 只檢查一個檔案
```

會把所有問題一次列出來；有問題時結束代碼是 1。規則見 `docs/區域製作手冊.md`。

## 區域編輯器

用瀏覽器編輯區域檔。區域檔存在 `builder_area/` 資料夾（第一次開會自動建立）。

```sh
uv run python -m mud.builder
```

- 開好之後，用瀏覽器打開 http://127.0.0.1:1234
- 換 port：`uv run python -m mud.builder --port 1235`
- 讓別台電腦也能用：`uv run python -m mud.builder --host 0.0.0.0`。
  **沒有登入**，連得到的人都能改檔，只在信得過的網路上這樣開。
- 左欄上方可以切換要編輯的東西：房間、生物、物品、重置（生物放在哪個房間、給牠什麼物品、門一開始的狀態……）。
- 中間的地圖可以用滑鼠拖拉移動，用滾輪（觸控板用兩指捏合）放大縮小。點一間房，它會回到中間。
- 改的內容會自動檢查，規則跟 `mud.areacheck` 一樣。有問題也能存，還沒寫完可以先存起來。
- 編輯器只看 `builder_area/`。做好的區域檔要自己放進 `areas/`，遊戲伺服器才會載入。

## 在 Mac 上連線測試

伺服器只講 Big5。Mac 的終端機維持 UTF-8，中間用 cocot 把 UTF-8 和 Big5 互相轉換。

### 1. 安裝工具（只要做一次）

```sh
brew install telnet cocot
```

macOS 從 10.13 起就不再內建 telnet，所以要自己裝。

### 2. 連線

伺服器開著，另外開一個終端機視窗：

```sh
cocot -t UTF-8 -p BIG5 telnet 127.0.0.1 4000
```

`-t UTF-8` 是終端機的編碼，`-p BIG5` 是 telnet 那一邊的編碼。要寫 `BIG5`，不要寫 `CP950`：macOS 的 CP950 對照表少了 249 個字。

看到 `Login:` 就輸入名字。登入後會站在測試區域南邊的房間（區域檔在 `areas/test.json`，寫法見 `docs/區域製作手冊.md`）。

### 3. 試試看

| 輸入 | 結果 |
|---|---|
| `look` | 看看所在的房間：名稱、出口、描述、同房間的人 |
| `look n` | 往北看會看到什麼（其他方向也可以，例如 `look south`） |
| `look 牌子`、`look sign` | 細看房間裡的東西。測試區域南邊的房間有一塊牌子 |
| `north`、`south` | 往北、往南走。測試區域只有南北兩間房；六個方向 north、east、south、west、up、down 都能用 |
| `chat 你好` | 所有在線的人都會看到你說的話（亮紫色） |
| `tell 阿華 你好` | 只有阿華看得到（亮綠色） |
| `reply 好啊` | 回覆最後一個 tell 你的人 |
| `weather` | 看現在幾點、天氣怎樣。在室內看不到 |
| `quit` | 離開遊戲 |

指令可以縮寫：系統會照指令表的順序，找第一個用你輸入的字開頭的指令。例如 `n` 就是 `north`，`s` 就是 `south`，`l` 就是 `look`，`c` 就是 `chat`，`t` 就是 `tell`，`r` 就是 `reply`，`q` 就是 `quit`。`w` 是 `west`，所以 `weather` 最少要打 `wea`。

想測兩個人聊天：再開一個視窗，用同一行指令連線，換一個名字登入。

### 注意

- **終端機不要切成 Big5。** 在 macOS 26 上，Big5 視窗用輸入法打中文會整個卡死，iTerm2 和內建終端機都會。
- 打錯中文時，倒退鍵要按兩次才會刪掉一個中文字。只按一次會送出半個字，變成亂碼。
- 不用 cocot、直接 telnet 的話，中文會是亂碼。
- cocot 轉漢字全部正確，只有 12 個符號會換成長得很像的字，例如「～」變「∼」、「￥」變「¥」；「€」和「¯」會變成 `#`。
- 不要用 luit：它的 Big5 對照表有錯，大約 130 個常用漢字會顯示成別的字，例如「往」會變成「⿍」。
