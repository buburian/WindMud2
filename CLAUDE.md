# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案概況

最小的 MUD telnet 伺服器原型，程式碼在 `mud/` 套件。只用標準庫（asyncio），沒有執行期依賴；
唯一的開發依賴是 pytest（`pyproject.toml` 的 dev group）。

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

- `tests/test_telnet.py` 是 `Telnet` 狀態機的單元測試；`tests/test_commands.py` 測指令縮寫比對和 quit；
  `tests/test_server.py` 用 port 0 開真的伺服器，兩個 client 登入、chat、quit。
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

## 架構

核心程式要模組化開發（使用者要求）：`mud/` 依職責分檔，新功能放進對應模組或開新模組，不要塞回單一檔案。
`config.py` 放共用常數，`__main__.py` 解析參數、開伺服器。

一條連線的資料流：`server.py` 的 `handle()` 讀 bytes → `Telnet.feed()` 切成整行字串 → 未登入時當名字，登入後交給 `command()`。

- **`Telnet`**（`telnet.py`）：每條連線一個實例，逐 byte 跑的狀態機（`data / iac / opt / sb / sb_iac`），
  狀態跨 `read()` 保留。負責去掉 telnet 協商、處理換行與退格，並把要回給客戶端的拒絕協商
  累積在 `replies`，由 `handle()` 寫出。
- **`encode()`**（`telnet.py`）：送出的**文字**一律經過它（`\n`→`\r\n`、cp950 編碼、`0xFF` 寫兩次），也就是用 `send()` 寫。
  telnet 控制碼（例如 `START`、`tn.replies`）則要直接 `writer.write(bytes)`，**絕不能**經過 `encode()`——IAC 就是 `0xFF`，會被寫成兩次而失效。
- **`players`**（`players.py`）：全域 dict，`writer → 名字`，只放已登入的人；廣播就是走訪它。斷線清理在 `handle()` 的 `finally`。
  它和 `send()` 獨立一檔，是因為 `commands/`、`server.py` 都要用，放其中一邊會互相 import。
- **指令**（`commands/`）：`__init__.py` 的 `COMMANDS` 是指令表，輸入的字照表的順序找**第一個用它開頭的指令**
  （例如 `c` → chat），表的順序就是縮寫的優先順序。指令依類別分檔：系統類在 `system.py`，技能法術類之後另開檔。
  加新指令：在類別檔寫 `do_xxx(writer, name, arg)`（回傳 `False` 代表斷線），再加進 `COMMANDS`。
  `command()` 會在指令跑完後補送 `PROMPT`（斷線時不送）。
- **存檔**（`save.py`）：`save_player()` 還沒實作，只是留好位置；`quit` 會呼叫它。直接斷線（沒打 quit）不會存檔。
- `send()` 只寫進 buffer，`drain()` 在 `handle()` 每處理完一批 read 才做一次。

## 必須守住的規則

- **收進來的一律當 bytes，收滿一行才 decode**。不要在 `Telnet` 裡提早 decode，也不要改成用文字模式讀。
  用 byte 切行之所以安全，是因為 Big5 第二碼不會是 `\r` `\n` `\0`。
- Big5 一個中文字 2 bytes（第一碼 ≥ `0x81`）。任何截斷、退格都要以「整個字」為單位（參考 `_backspace()`）。
- 廣播給其他人的訊息格式是 `"\n...\n" + PROMPT`：先換行避免接在對方 prompt 後面，說完再補回對方的 prompt。
- 協商：一連上就送 `START`（`IAC DO BINARY`）請客戶端用 8-bit 傳。坑：沒談好 BINARY，macOS 的 telnet 會把每個 byte 的
  第 8 bit 拿掉，中文全壞（加 `-8` 也一樣）。對方回 `WILL BINARY` 是答應，不再回覆。
  其他一律拒絕：對方 WILL 回 DONT、DO 回 WONT，同一組 (verb, option) 只回一次；對方 WONT/DONT 不回，避免兩邊無限互回。
- 程式碼註解用繁體中文；telnet／編碼的陷阱用 `坑：` 開頭標記，新增同類處理時沿用這個寫法。
