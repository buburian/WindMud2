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
- 正式開給別人連、掛掉要自動重開：`./serve.sh`（開在 `0.0.0.0:8080`，掛掉 5 秒後重開；`PORT=4000 ./serve.sh` 換 port）。
  開機不到 10 秒就結束（區域檔寫錯、port 被占用）不會一直重開，會停下來讓你看錯誤。
  Linux 主機也可以交給 systemd 管，見下面的「用 systemd 管理（Linux）」。
- 視窗會顯示誰登入、誰離線，同時存到 `logs/`。檔名是「日期_編號」，例如 `2026-11-05_001.log`；一個檔滿 5MB 換下一個編號，最多留 30 個檔。

開機時會先檢查這些東西，有問題就**不開機**，視窗印出第一個問題和總共幾個：

| 檢查 | 檔案 | 有問題時 |
|---|---|---|
| 區域檔 | `areas/` 裡全部的 `.json` | 用下面的「檢查區域檔」一次列出全部問題 |
| 說明檔 | `help/help.json` | 每個指令都要剛好有一筆說明，每個字都要能轉成 Big5 |
| 表情動作 | `socials/socials.json` | 欄位、代換碼要對，名字不能跟指令撞，每個字都要能轉成 Big5 |
| 登入畫面 | `screens/login.txt` | 連最後問名字那一行不超過 24 行，每行不超過 79 格（中文字算兩格，顏色代碼不算），每個字都要能轉成 Big5 |

起始房間（秋風城的神殿大廳 3001）一定要在 `areas/` 的世界區域裡。

連上來先清掉畫面、顯示登入畫面（`screens/login.txt`），再問名字。畫面可以直接改這個檔，可以用顏色代碼（寫法見區域製作手冊的[顏色代碼](docs/區域製作手冊.md#顏色代碼)），
檔案最後多一個空行，問名字之前就空一行。

**改了程式、區域檔、說明檔、表情動作或登入畫面，都要重開伺服器才會生效。**

### 用 systemd 管理（Linux）

Linux 主機可以把伺服器交給 systemd：開機自動開，掛掉 5 秒後重開，用 `systemctl` 開關。
設定檔是 `deploy/windmud.service`，跑的指令跟 `./serve.sh` 一樣（`0.0.0.0:8080`）。

裝一次：

```sh
uv sync                                          # 用要跑伺服器的帳號，先裝好 Python 和套件
which uv                                         # 記下 uv 在哪裡（通常是 ~/.local/bin/uv）
sudo cp deploy/windmud.service /etc/systemd/system/
sudo nano /etc/systemd/system/windmud.service    # 把「你的帳號」換掉；uv 不在 ~/.local/bin 就改 ExecStart 的路徑
sudo systemctl daemon-reload
sudo systemctl enable --now windmud              # 開機自動開，現在也開起來
```

平常用：

```sh
sudo systemctl start windmud      # 開
sudo systemctl stop windmud       # 關（先存好線上玩家的檔）
sudo systemctl restart windmud    # 重開（改了程式、區域檔…以後）
systemctl status windmud          # 有沒有在跑、最後幾行紀錄
journalctl -u windmud -f          # 一直看新的紀錄，Ctrl+C 離開
```

- `systemctl stop` 送的是 SIGINT，跟按 Ctrl+C 一樣：伺服器關掉每條連線、存好線上玩家的檔再結束，1 秒內就好，紀錄裡看得到「離線」。
  等了很久（最多 30 秒）才停，就是訊號沒送到伺服器，玩家沒存到。
- 換 port：改 `/etc/systemd/system/windmud.service` 裡的 `--port 8080`，再 `sudo systemctl daemon-reload`、`sudo systemctl restart windmud`。改了這個檔都要 `daemon-reload`。
- 開機就掛（區域檔寫錯、port 被占用）：重開 3 次都掛就停下來，不再重開。用 `journalctl -u windmud` 看錯誤，修好以後 `sudo systemctl reset-failed windmud` 再 `start`。
  1 分鐘內 start、restart 超過 4 次也會被擋下（伺服器停著），一樣 `reset-failed` 再 `start`。
- 不要同時開 `./serve.sh`，port 會撞在一起。
- 伺服器自己的紀錄照樣寫在 `logs/`。

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
