# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案概況

最小的 MUD telnet 伺服器原型，全部程式碼在 `server.py` 一個檔案。只用標準庫（asyncio），
依賴宣告在檔頭的 PEP 723 inline metadata（`dependencies = []`），沒有 pyproject、沒有測試。

## 參考資料（唯讀，不可修改）

- `/Volumes/DevSSD/Projects/claude_project/mud_design`：新遊戲邏輯的設計規劃書（主文件 `設計文件.md`）。
- `/Volumes/DevSSD/Projects/claude_project/mud/sourcecode/WindSrc`：原始遊戲的 C 語言版本。
  要看連線通訊和核心程式時參考它，連線通訊在 `comm.c`（`game_loop_unix`、`read_from_descriptor`、`write_to_descriptor`）。
  原始碼是 Big5，搜尋要用 `LC_ALL=C grep -a`，不然會搜不到。

## 指令

```sh
uv run server.py                          # 預設 127.0.0.1:4000
uv run server.py --port 4055 --host 0.0.0.0   # 給別台電腦連
```

沒有測試套件。驗證方式是實際啟動 server，再用 client 連上去：

- 伺服器只講 **Big5（cp950）**。終端機是 UTF-8 的話，`telnet 127.0.0.1 4000` 看到的中文會是亂碼。
- 要自動驗證就寫一支 asyncio client：送出前 `.encode("cp950")`、收到後 `.decode("cp950")`。
  讀取迴圈要處理 `read()` 回傳 `b""`（EOF），否則 `quit` 之後會卡成無窮迴圈。
- 值得測的邊界：IAC 序列被切在兩個封包、中文字被切在兩個封包、兩個連線互相 `chat`。

## 架構

一條連線的資料流：`handle()` 讀 bytes → `Telnet.feed()` 切成整行字串 → 未登入時當名字，登入後交給 `command()`。

- **`Telnet`**：每條連線一個實例，逐 byte 跑的狀態機（`data / iac / opt / sb / sb_iac`），
  狀態跨 `read()` 保留。負責去掉 telnet 協商、處理換行與退格，並把要回給客戶端的拒絕協商
  累積在 `replies`，由 `handle()` 寫出。
- **`encode()`**：送出的**文字**一律經過它（`\n`→`\r\n`、cp950 編碼、`0xFF` 寫兩次），也就是用 `send()` 寫。
  telnet 控制碼（例如 `tn.replies`）則要直接 `writer.write(bytes)`，**絕不能**經過 `encode()`——IAC 就是 `0xFF`，會被寫成兩次而失效。
- **`players`**：全域 dict，`writer → 名字`，只放已登入的人；廣播就是走訪它。斷線清理在 `handle()` 的 `finally`。
- **`command()`**：指令分派，加新指令就加一個 `elif verb == ...` 分支。回傳 `False` 代表斷線。
  除了 `quit`，每條路徑最後都會補送 `PROMPT`。
- `send()` 只寫進 buffer，`drain()` 在 `handle()` 每處理完一批 read 才做一次。

## 必須守住的規則

- **收進來的一律當 bytes，收滿一行才 decode**。不要在 `Telnet` 裡提早 decode，也不要改成用文字模式讀。
  用 byte 切行之所以安全，是因為 Big5 第二碼不會是 `\r` `\n` `\0`。
- Big5 一個中文字 2 bytes（第一碼 ≥ `0x81`）。任何截斷、退格都要以「整個字」為單位（參考 `_backspace()`）。
- 廣播給其他人的訊息格式是 `"\n...\n" + PROMPT`：先換行避免接在對方 prompt 後面，說完再補回對方的 prompt。
- 協商一律拒絕：對方 WILL 回 DONT、DO 回 WONT，同一組 (verb, option) 只回一次；對方 WONT/DONT 不回，避免兩邊無限互回。
- 程式碼註解用繁體中文；telnet／編碼的陷阱用 `坑：` 開頭標記，新增同類處理時沿用這個寫法。
