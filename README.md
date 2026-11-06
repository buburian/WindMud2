# MUD 伺服器（Python）

用 Big5 編碼的 telnet MUD 伺服器。這份說明只講怎麼安裝、啟動、連線。
遊戲規則寫在 `docs/`（`玩家角色手冊.md`、`區域製作手冊.md`），遊戲裡打 `help` 也看得到指令說明。

## 需要的東西

- macOS 和 Homebrew
- uv：`brew install uv`
- 連線測試用的 telnet 和 cocot：`brew install telnet cocot`（macOS 從 10.13 起就不再內建 telnet）

Python 不用自己裝。第一次執行時，uv 會自動下載 Python 3.15（版本寫在 `.python-version`）和需要的套件（rich、測試用的 pytest）。
**不要用系統的 Python**，指令一律用 `uv run` 開頭。

## 安裝

```sh
git clone https://github.com/buburian/WindMud2.git mud_server
cd mud_server
uv sync          # 先把 Python 和套件裝好（可以不做，第一次 uv run 時也會自動裝）
```

## 開啟伺服器

在專案資料夾裡執行：

```sh
uv run python -m mud
```

- 預設開在 `127.0.0.1:4000`，只有這台電腦連得到。
- 換 port：`uv run python -m mud --port 4055`
- 讓別台電腦也能連：`uv run python -m mud --host 0.0.0.0`
- 按 Ctrl+C 關閉。
- 視窗會顯示誰登入、誰離線，同時存到 `logs/`。檔名是「日期_編號」，例如 `2026-11-05_001.log`；一個檔滿 5MB 換下一個編號，最多留 30 個檔。

開機時會先檢查兩樣東西，有問題就**不開機**，視窗印出第一個問題和總共幾個：

| 檢查 | 檔案 | 有問題時 |
|---|---|---|
| 區域檔 | `areas/` 裡全部的 `.json` | 用下面的「檢查區域檔」一次列出全部問題 |
| 說明檔 | `help/help.json` | 每個指令都要剛好有一筆說明，每個字都要能轉成 Big5 |

起始房間（101）一定要在 `areas/` 的世界區域裡。

**改了程式、區域檔或說明檔，都要重開伺服器才會生效。**

## 連線

伺服器只講 Big5。Mac 的終端機維持 UTF-8，中間用 cocot 把 UTF-8 和 Big5 互相轉換。
伺服器開著，另外開一個終端機視窗：

```sh
cocot -t UTF-8 -p BIG5 telnet 127.0.0.1 4000
```

- `-t UTF-8` 是終端機的編碼，`-p BIG5` 是 telnet 那一邊的編碼。
  要寫 `BIG5`，不要寫 `CP950`：macOS 的 CP950 對照表少了 249 個字。
- 第一次連線會建立角色（英文名字、密碼、性別、種族、公會）。角色存在 `players/名字.json`。
- 想測好幾個人：再開一個視窗，用同一行指令連線，換一個名字。

### 連線的注意事項

- **終端機不要切成 Big5。** 在 macOS 26 上，Big5 視窗用輸入法打中文會整個卡死，iTerm2 和內建終端機都會。
- 打錯中文時，倒退鍵要按兩次才會刪掉一個中文字。只按一次會送出半個字，變成亂碼。
- 不用 cocot、直接 telnet 的話，中文會是亂碼。
- cocot 轉漢字全部正確，只有 12 個符號會換成長得很像的字，例如「～」變「∼」、「￥」變「¥」；「€」和「¯」會變成 `#`。
- 不要用 luit：它的 Big5 對照表有錯，大約 130 個常用漢字會顯示成別的字，例如「往」會變成「⿍」。

## 設定管理員（imm）

第一個管理員要直接改存檔：

1. 先用那個角色登入一次，讓 `players/名字小寫.json` 建立起來。
2. **關掉伺服器**（不然角色離線或伺服器關掉時會存檔，把你改的蓋掉）。
3. 打開 `players/名字小寫.json`，加上 `"imm": true`。
4. 重開伺服器。

## 區域編輯器

用瀏覽器編輯區域檔：

```sh
uv run python -m mud.builder
```

- 開好之後，用瀏覽器打開 http://127.0.0.1:1234 。按 Ctrl+C 關閉。
- 換 port：`uv run python -m mud.builder --port 1235`
- 讓別台電腦也能用：`uv run python -m mud.builder --host 0.0.0.0`。
  **沒有登入**，連得到的人都能改檔，只在信得過的網路上這樣開。
- 區域檔存在 `builder_area/`。編輯器只看這個資料夾：做好的檔要自己放進 `areas/`，重開伺服器才會載入。
- 改了程式之後，編輯器也要重開（Ctrl+C 再開），只重新整理網頁不夠。

## 檢查區域檔

```sh
uv run python -m mud.areacheck                     # 檢查 areas/ 裡全部的區域檔
uv run python -m mud.areacheck areas/test.json     # 只檢查一個檔案
```

會把所有問題一次列出來；有問題時結束代碼是 1。規則跟伺服器開機時、編輯器裡的檢查一樣。

## 自動測試

```sh
uv run pytest                                      # 全部測試
uv run pytest tests/test_telnet.py                 # 只跑一個檔
```

有些測試會跟設計文件的模擬程式比對數字，它放在旁邊的 `../mud_design/sim/balance.py`。找不到這個資料夾時，那些測試會自動跳過。

## 資料夾

| 資料夾 | 放什麼 | 進 git |
|---|---|---|
| `mud/` | 伺服器的程式（`mud/builder/` 是區域編輯器） | ✓ |
| `areas/` | 伺服器載入的區域檔（`test.json` 是測試區域） | ✓ |
| `help/` | `help` 指令的說明檔 `help.json` | ✓ |
| `docs/` | 玩家角色手冊、區域製作手冊 | ✓ |
| `tests/` | 自動測試 | ✓ |
| `players/` | 角色存檔（第一次有人建角色時自動建立） | ✗ |
| `logs/` | 伺服器的紀錄檔（開機時自動建立） | ✗ |
| `builder_area/` | 區域編輯器的區域檔（資料夾在 git 裡，裡面的檔不進 git） | ✗ |
