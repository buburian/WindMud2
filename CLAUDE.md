# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案概況

最小的 MUD telnet 伺服器原型，程式碼在 `mud/` 套件，網路用標準庫 asyncio。
執行期依賴只有 rich（畫面上的紀錄顯示）；開發依賴是 pytest（`pyproject.toml` 的 dev group）。

## 參考資料（唯讀，不可修改）

- `/Volumes/DevSSD/Projects/claude_project/mud_design`：新遊戲邏輯的設計規劃書（主文件 `設計文件.md`）。
- `/Volumes/DevSSD/Projects/claude_project/mud/sourcecode/WindSrc`：原始遊戲的 C 語言版本。
  **只是參考：這是新遊戲，不是把 C 版改寫**，不照它的結構和命名。要看連線通訊和核心程式時參考它，連線通訊在 `comm.c`（`game_loop_unix`、`read_from_descriptor`、`write_to_descriptor`）。
  原始碼是 Big5，搜尋要用 `LC_ALL=C grep -a`，不然會搜不到。

## 指令

都要在專案根目錄執行（套件沒有安裝，`python -m mud` 靠目前目錄找到 `mud/`）：

```sh
uv run python -m mud                              # 預設 127.0.0.1:4000
uv run python -m mud --port 4055 --host 0.0.0.0   # 給別台電腦連
uv run pytest                                     # 全部測試
uv run pytest tests/test_telnet.py::test_encode   # 單一測試
```

- `tests/test_telnet.py` 是 `Telnet` 狀態機的單元測試；`tests/test_commands.py` 測指令縮寫比對、tell、reply 和 quit；`tests/test_color.py` 測顏色代碼；`tests/test_act.py` 測 `act()` 的代換和送給誰；
  `tests/test_log.py` 測紀錄檔的編號、換檔和刪舊檔；`tests/test_area.py` 測區域載入；
  `tests/test_server.py` 用 port 0 開真的伺服器，兩個 client 登入、chat、quit。
  用到房間的測試要自己先 `area.load(areas 資料夾)`：`area.rooms` 是全域的，不要依賴別的測試先載入過。
- `test_server.py` 的 client 連線一定要在 `finally` 關掉：Python 3.12 起，離開 `async with server` 會等所有連線斷掉，
  測試中途失敗時不先關就會永遠卡住。

### 手動連線

伺服器只講 **Big5（cp950）**。終端機維持 UTF-8，中間用 luit 轉碼：

```sh
brew install luit                          # 只要裝一次
uv run python -m mud                       # 視窗 1：開伺服器
luit -encoding Big5 telnet 127.0.0.1 4000  # 視窗 2：連線
```

- 直接用 UTF-8 終端機 telnet，中文會是亂碼。
- **不要把終端機切成 Big5**：在 macOS 26 上，Big5 視窗用輸入法打中文會整個卡死（iTerm2、Terminal.app 都會），跟伺服器無關。
- telnet 是 line mode，由本機終端機自己處理倒退鍵，一次只刪一個 byte。所以刪一個 Big5 中文字要按兩次倒退鍵，只按一次會送出半個字。
- **luit 的 Big5 對照表有錯**：13752 個字裡有 191 個轉錯，其中 134 個是漢字，很多是常用字（例如 往、成、為、馬、活、應）。
  畫面上這些字會顯示成別的字，但伺服器送出的 bytes 是對的（用 Python `cp950` 解得回來）。看到怪字先別懷疑伺服器。

## 架構

核心程式要模組化開發（使用者要求）：`mud/` 依職責分檔，新功能放進對應模組或開新模組，不要塞回單一檔案。
`config.py` 放共用常數，`__main__.py` 解析參數、開伺服器。

一條連線的資料流：`server.py` 的 `handle()` 讀 bytes → `Telnet.feed()` 切成整行字串 → 未登入時當名字，登入後交給 `command()`。

- **`Telnet`**（`telnet.py`）：每條連線一個實例，逐 byte 跑的狀態機（`data / iac / opt / sb / sb_iac`），
  狀態跨 `read()` 保留。負責去掉 telnet 協商、處理換行與退格，並把要回給客戶端的拒絕協商
  累積在 `replies`，由 `handle()` 寫出。
- **`encode()`**（`telnet.py`）：送出的**文字**一律經過它（`\n`→`\r\n`、cp950 編碼、`0xFF` 寫兩次），也就是用 `send()` 寫。
  telnet 控制碼（例如 `START`、`tn.replies`）則要直接 `writer.write(bytes)`，**絕不能**經過 `encode()`——IAC 就是 `0xFF`，會被寫成兩次而失效。
- **`players`**（`players.py`）：全域 dict，`writer → Player`，只放已登入的人。`Player` 有 `name`、`sex`（還沒有地方選，
  先都預設男 `SEX_MALE`）、`reply`（最後一個 tell 我的人的 writer）、`room`（所在房間的 vnum，登入時是 `config.START_ROOM`）。
  斷線清理在 `handle()` 的 `finally`，
  也會清掉別人身上指向這條連線的 `reply`。它和 `send()` 獨立一檔，是因為 `commands/`、`act.py`、`server.py` 都要用，放其中一邊會互相 import。
- **`act()`**（`act.py`）：送訊息給別人一律用它。`to` 決定送給誰：`TO_CHAR` 自己、`TO_VICT` 對象、`TO_ROOM` 同房間自己以外、
  `TO_NOTVICT` 同房間自己和對象以外。`ch`、`vch` 都是 writer。全服頻道（chat）不用 `TO_ROOM`，要自己走訪所有玩家。
  代換碼（字母跟 C 版一樣）：`$n`/`$N` 名字（`$n` 送給自己時變「你」）、`$e $m`/`$E $M` 他她它、`$s`/`$S` 他的她的它的、
  `$t`/`$T` 帶進來的文字；小寫是自己、大寫是對象。寫錯的碼原樣保留，並在伺服器視窗印警告。
- **指令**（`commands/`）：`__init__.py` 的 `COMMANDS` 是指令表，輸入的字照表的順序找**第一個用它開頭的指令**
  （例如 `c` → chat），表的順序就是縮寫的優先順序。指令依類別分檔：系統類在 `system.py`，技能法術類之後另開檔。
  加新指令：在類別檔寫 `do_xxx(writer, name, arg)`（回傳 `False` 代表斷線），再加進 `COMMANDS`。
  `command()` 會在指令跑完後補送 `PROMPT`（斷線時不送）。
  `COMMANDS` 最前面是六個方向（`n e s w u d` 都是走路），接著 `look`。方向指令用 `walk(方向)` 做出來，共用 `move()`。
  `look()` 回傳房間畫面的字串，登入時 `server.py` 也用它。
- **區域**（`area.py`、`areas/`）：開機時 `load()` 讀 `areas/*.json`，存成 `rooms`（vnum → `Room`）。
  現在只取 `vnum`、`name`、`description`、`exits.<方向>.to_room`，其他欄位不管。
  重複的 vnum、出口指到不存在的房間 → 丟 `ValueError`，開機停止。
  **區域檔格式是我們自己的**：舊區域的流程是 `.are` → area2json → 我們的區域編輯器處理 → 才給伺服器用。
  `mud_design/area_convert/out/*.json` 只是拿來打底的參考，伺服器不直接載入它。
  `areas/test.json` 是測試區域（房間 1 南、2 北，南北相連），目前以 area2json 的輸出打底，
  之後會照使用者的指示改成真正的區域檔格式。`area` 和每個房間的欄位**一個都不能少**，
  巢狀欄位也要有範例值（`extra_descriptions`、`script`、`overridden_exits` 各放一筆）：使用者靠它看系統還缺哪些功能。
  房間的文字可以用顏色代碼。
- **顏色**（`color.py`）：字串裡寫代碼，`colorize()` 換成 C 版 `merc.h` 的色碼：`{r{R{g{G{y{Y{b{B{m{M{c{C{w{W{D`
  （小寫暗、大寫亮），`{x` 回到原本顏色，`{{` 印出 `{`，不認得的代碼原樣留著。不能巢狀：`{x` 是全部回到原本顏色。
  `act()` 會先對 fmt 做 `colorize()` 再代換 `$` 碼，所以玩家打的代碼會原樣顯示。`send()` 不轉代碼，要顏色就自己包 `colorize()`。
  目前 chat 用 `{M`（亮紫），tell／reply 用 `{G`（亮綠），跟 C 版一樣。
- **存檔**（`save.py`）：`save_player()` 還沒實作，只是留好位置；`quit` 會呼叫它。直接斷線（沒打 quit）不會存檔。
- **紀錄**（`log.py`）：`__main__` 啟動時呼叫 `setup()`。畫面用 rich 的 `RichHandler`，同時用 `DailyFileHandler` 存到
  `logs/日期_編號.log`（例如 `2026-10-30_001.log`）：換日從 001 重新編號，超過 5MB 換下一個編號，只留最新 30 個檔。
  檔名格式不符的檔案不會被刪。
- `send()` 只寫進 buffer，`drain()` 在 `handle()` 每處理完一批 read 才做一次。

## 必須守住的規則

- **收進來的一律當 bytes，收滿一行才 decode**。不要在 `Telnet` 裡提早 decode，也不要改成用文字模式讀。
  用 byte 切行之所以安全，是因為 Big5 第二碼不會是 `\r` `\n` `\0`。
- Big5 一個中文字 2 bytes（第一碼 ≥ `0x81`）。任何截斷、退格都要以「整個字」為單位（參考 `_backspace()`）。
- 送給別人的訊息用 `act()`，不要自己 `send()`：`act()` 會包成 `"\n...\n" + PROMPT`（先換行避免接在對方 prompt 後面，
  說完再補回對方的 prompt）；送給自己只加換行，prompt 由 `command()` 補。
  已知限制：一個指令對同一個別人送兩次 `act()`，對方會看到兩個 prompt。要送多行，就放在同一段文字裡。
- 協商：一連上就送 `START`（`IAC DO BINARY`）請客戶端用 8-bit 傳。坑：沒談好 BINARY，macOS 的 telnet 會把每個 byte 的
  第 8 bit 拿掉，中文全壞（加 `-8` 也一樣）。對方回 `WILL BINARY` 是答應，不再回覆。
  其他一律拒絕：對方 WILL 回 DONT、DO 回 WONT，同一組 (verb, option) 只回一次；對方 WONT/DONT 不回，避免兩邊無限互回。
- 玩家打的字（訊息內容、名字）一律用 `$t`、`$n` 這些代換碼帶進 `act()`，不要用 f-string 拼進 fmt：
  拼進去的字會被當成顏色代碼，玩家就能自己上色。
- 系統訊息用 `logging.getLogger(__name__)` 記錄，不要用 `print()`。
- 程式碼註解用繁體中文；telnet／編碼的陷阱用 `坑：` 開頭標記，新增同類處理時沿用這個寫法。
