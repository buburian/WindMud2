# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案概況

最小的 MUD telnet 伺服器原型，程式碼在 `mud/` 套件，網路用標準庫 asyncio。
執行期依賴是 rich（畫面上的紀錄顯示）和 lupa（Lua 腳本，`uv add` 加的）；開發依賴是 pytest（`pyproject.toml` 的 dev group）。

## 參考資料（唯讀，不可修改）

- `/Volumes/DevSSD/Projects/claude_project/mud_design`：新遊戲邏輯的設計規劃書（主文件 `design/設計文件.md`）。
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
uv run python -m mud.areacheck                    # 檢查 areas/ 全部的區域檔（有問題時結束代碼 1）
uv run python -m mud.areacheck areas/test.json    # 只檢查一個區域檔
uv run python -m mud.builder                      # 區域編輯器，瀏覽器開 http://127.0.0.1:1234（區域檔存在 builder_area/）
```

- `tests/test_telnet.py` 是 `Telnet` 狀態機的單元測試；`tests/test_commands.py` 測指令縮寫比對、tell、reply 和 quit；`tests/test_color.py` 測顏色代碼；`tests/test_act.py` 測 `act()` 的代換和送給誰；
  `tests/test_log.py` 測紀錄檔的編號、換檔和刪舊檔；`tests/test_area.py` 測區域載入，也比對手冊的數字表跟程式的定義；`tests/test_areacheck.py` 測區域檔檢查的每條規則；
  要自己做區域檔的測試，用 `tests/area_helpers.py` 做出完整的檔案再改欄位（直接 `from area_helpers import …`）；
  `tests/test_server.py` 用 port 0 開真的伺服器，兩個 client 登入、chat、quit；另一個測試讓 tick 和幾場戰鬥一直跑，確認玩家打字照樣馬上回應。
  `tests/test_login.py` 也開真的伺服器，測建立角色、密碼、名字規則、存檔、斷線存檔、重複登入接手。`tests/test_imm.py` 測 imm 指令、advance、train；`tests/test_position.py` 測姿勢、rest／sleep／stand、睡覺時能用的指令、say、who、save。`tests/test_resets.py` 測生物的重置（M、limit、rare、tier_roll、時機、look）。`tests/test_doors.py` 測門（兩邊都要寫的檢查、走路、open／close／lock／unlock、對面看得到、look、重置 D、副本各自的門）。
  `tests/test_objects.py` 測物品（固定、隨機裝備、掉落表、屍體、slay、look 和 look in、屍體消失、區域物件釋放後不見）。
  `tests/test_damage.py` 把傷害公式、`strike()` 的每一下、經驗值跟 balance.py 比對（用同一個種子）；`tests/test_combat.py` 測 kill、訊息、
  一回合合成一段、打死生物、經驗值和升級、玩家被打死、存檔的經驗值（`fight.TICK_SECONDS` 改很大、自己呼叫 `tick()`，亂數換成 `Always`）。
  `tests/test_skills.py` 把技能的資料、消耗、說明的數字、技能那一下跟 balance.py 比對，也測 use 的每種拒絕（沒過不會開打）、開打、把旁邊的生物拉進來、訊息、冷卻、扣 MV／MP、打死、skills 指令
  （坑：`asyncio.run()` 結束時戰鬥會被收掉，開打和打指令要在同一個 `asyncio.run()` 裡）。
  `tests/test_targets.py` 測 `find_in_room()`（名字開頭、`n.名字`、照 look 的順序、自己最後）。
  `tests/test_items.py` 測 get、drop、wear、remove、inventory、equipment、oload 的每種訊息和限制、背包和裝備的存檔；
  `tests/test_gear.py` 測裝備的屬性（跟 balance.py 的 `primary_bundle`、`apply_points` 比對）、手冊的負重／武器重量／攻擊方式表、武器傷害、雙持、打架中換武器、技能的武器。
  `tests/test_object_resets.py` 測重置 G、O、P、R、生物身上的東西進屍體（店主的消失）、test.json 載入後商人身上的東西和箱子裡的麵包；
  `tests/test_containers.py` 測容器的 open、close、lock、unlock、找的順序、鑰匙、關著不能拿、封印、存檔帶容器狀態、門用真的鑰匙。
  `tests/test_give.py` 測 give（給東西、給金幣、店主不收、放不下、1 級不能給金幣、給完存檔、log）。
  `tests/test_scripts.py` 測 Lua 腳本：沙箱（拿不到的名字、碰不到 Python、指令數上限、記憶體）、開機檢查的每一條、10 個觸發時機、每個函式、vars、wait、出錯的提醒
  （wait 用假的 `scripts.schedule`，自己呼叫 `later.run()`；區域檔和 .lua 用 `build()` 寫進 `tmp_path`）。
  `tests/test_config.py` 測 config（列出、開關、lines 的範圍、存檔）；`tests/test_pager.py` 測分頁（假指令 many 送很多行：每個按鍵、打別的指令、別人的訊息、quit、出錯）。
  `tests/test_academy.py` 用真的 `areas/` 測教學學院：一人一份、一路走到畢業（技能教官照公會教 use、掉落、穿上、`say 畢業`）、學生重新登入和死掉回學院、沒有學院的區域檔時。
  `tests/test_flee.py` 測 flee（DEX 的機率、戰鬥中不能走、成功、失敗要等、關著的門、沒有出口）。
  `tests/test_affects.py` 測身上的效果（覆蓋和疊加、暫時加減屬性、每 3 tick 跳、矮人的堅韌、扣死給誰經驗、時間到、死掉、存檔、score 最下面那段、affect、mstat），自己呼叫 `affects.tick()`。
  `tests/test_examine.py` 測 exam 的每一行、ostat、mstat、物品種類和武器種類的名稱表（跟手冊比對）、地上那一行接英文名字。
  `tests/test_help.py` 檢查真的 `help/help.json`（每個指令都有說明）、`helps.check()` 的每條規則、help 的三種畫面、縮寫、imm 的分類。
  要登入的測試先用 `tests/player_helpers.py` 的 `make_player_file()` 存好角色（密碼 `PASSWORD`），存檔資料夾用 monkeypatch 把 `save.PLAYER_DIR` 指到 `tmp_path`。
  `tests/test_stats.py` 比對種族、公會、裸裝屬性、MP／MV 跟玩家角色手冊、balance.py；`test_equipment.py`、`test_stats.py` 讀 balance.py 用 `tests/balance_loader.py`
  （唯讀：不寫 .pyc、不改 mud_design；找不到 mud_design 才跳過）。
  `tests/test_builder.py` 用 port 0 開真的區域編輯器（資料夾是 `tmp_path`），用 urllib 打 API；也比對網頁的數字表跟 `area.py` 的定義、手冊的表。
  `tests/test_weather.py` 測天氣（時間、日夜、天空一次只走一格、送給誰、weather 指令）；`tests/test_clock.py` 測定時器；`tests/test_zones.py` 測區域物件（動態區域、副本的建立和釋放、tick）；`tests/test_fight.py` 測戰鬥 loop 和時間軸的出手順序。
  用到房間的測試要自己先 `zones.load(areas 資料夾)`：`zones.world` 是全域的，不要依賴別的測試先載入過。
  角色的 `room` 是 Room 物件：載入之後再把角色放進 `zones.world.rooms[101]` 這種房間（重新載入後舊的 Room 就不是世界裡的了）。
  `characters` 也是全域的：測試加進去的角色（玩家、NPC）要在 fixture 結束時 `characters.clear()`，不然會跑進別的測試的 look 裡。
  會開 loop 的動作（`zones.start()`、`zones.instance()`、`start_fight()`）要在 `asyncio.run()` 裡做，fixture 結束時 `zones.stop()`；
  要等時間的測試用 monkeypatch 把 `zones.TICK_SECONDS`、`fight.TICK_SECONDS` 改成很小的數字（`zones.RELEASE_TICKS`、`zones.HOUR_TICKS` 改小），
  要一個 tick 一個 tick 看的（例如戰鬥的出手順序）就把 `TICK_SECONDS` 改很大、自己呼叫 `tick()`；其他
  用 `until(條件)` 輪詢等待，不要寫死等多久。
- `test_server.py` 的 client 連線一定要在 `finally` 關掉：Python 3.12 起，離開 `async with server` 會等所有連線斷掉，
  測試中途失敗時不先關就會永遠卡住。

### 手動連線

伺服器只講 **Big5（cp950）**。終端機維持 UTF-8，中間用 cocot 轉碼：

```sh
brew install telnet cocot                       # 只要裝一次
uv run python -m mud                            # 視窗 1：開伺服器
cocot -t UTF-8 -p BIG5 telnet 127.0.0.1 4000    # 視窗 2：連線
```

- 第一次連線要建立角色：英文名字、密碼（打的時候畫面不顯示字）、性別、種族、公會。存檔在 `players/`（不進 git）。

- 直接用 UTF-8 終端機 telnet，中文會是亂碼。
- **不要把終端機切成 Big5**：在 macOS 26 上，Big5 視窗用輸入法打中文會整個卡死（iTerm2、Terminal.app 都會），跟伺服器無關。
- telnet 是 line mode，由本機終端機自己處理倒退鍵，一次只刪一個 byte。所以刪一個 Big5 中文字要按兩次倒退鍵，只按一次會送出半個字。
- cocot 用系統的 iconv 轉碼。整張字表來回測過：漢字全對，只有 12 個符號不同（例如 ～→∼、￥→¥，€、¯ 變成 `#`）。
  `-p` 要寫 `BIG5`：macOS 的 CP950 表少了 249 個字。
- **不要用 luit**：它的 Big5 對照表有錯，134 個漢字會轉錯，很多是常用字（例如 往、成、為、馬）。
  看到畫面上的怪字，先確認轉碼工具，伺服器送出的 bytes 是對的（用 Python `cp950` 解得回來）。

## 架構

核心程式要模組化開發（使用者要求）：`mud/` 依職責分檔，新功能放進對應模組或開新模組，不要塞回單一檔案。
`config.py` 放共用常數，`__main__.py` 解析參數、開伺服器。

一條連線的資料流：`server.py` 的 `handle()` 用 `login.Connection` 讀 bytes → `Telnet.feed()` 切成整行字串，一次給一行（`readline()`）
→ 先 `login()`（問名字、密碼，或建立角色）→ 登入後每一行交給 `command()`。

- **`Telnet`**（`telnet.py`）：每條連線一個實例，逐 byte 跑的狀態機（`data / iac / opt / sb / sb_iac`），
  狀態跨 `read()` 保留。負責去掉 telnet 協商、處理換行與退格，並把要回給客戶端的拒絕協商
  累積在 `replies`，由 `Connection.readline()` 寫出。
  打密碼時 `echo_off()`／`echo_on()` 送 `WILL ECHO`／`WONT ECHO`（客戶端就不顯示打的字）：`echo_off()` 會把 `(DO, ECHO)` 記成回過，
  對方回 `DO ECHO` 是答應，不能再回 `WONT`；沒問過就收到 `DO ECHO` 照舊拒絕。
- **`encode()`**（`telnet.py`）：送出的**文字**一律經過它（`\n`→`\r\n`、cp950 編碼、`0xFF` 寫兩次），也就是用 `send()` 寫。
  telnet 控制碼（例如 `START`、`tn.replies`）則要直接 `writer.write(bytes)`，**絕不能**經過 `encode()`——IAC 就是 `0xFF`，會被寫成兩次而失效。
- **角色**（`characters.py`、`players.py`、`npcs.py`）：玩家和 NPC 都是角色（使用者要求先分好骨架，資料只放現在用得到的）。
  - **玩家角色的規則寫在 `docs/玩家角色手冊.md`**（mud_design 定的，使用者確認）：等級、主屬性、種族、公會（沒有職業）、HP／MP／MV 和回復、負重、武器重量限制、戰鬥的出手順序、雙持、定時做的事。
    做了要同步更新手冊開頭的進度表。數字的推導在 mud_design 的設計文件，手冊只寫規則。
  - `Character`：`name`、`sex`、`room`（所在的 **Room 物件**，不是號碼：兩份副本的同號房間是不同的 Room，
    所以 `act()`、`look()` 比 `c.room == ch.room` 時看不到別份的人）、`position`、`fighting`（正在打誰）、`fight`（在哪一場）。
    `send(text)` 送文字給這個角色，預設什麼都不做。
    **姿勢用 `Position`**（`characters.py`）：**使用者說很重要**，就是手冊生物那章的 position 表（0 DEAD～7 STANDING），
    也是角色（玩家和生物）現在狀態的定義，遊戲用它判斷角色是在休息、站著走動還是在戰鬥；不要另外發明一套。
    改手冊的表要一起改它（`tests/test_area.py` 會比對）。現在只有戰鬥會切換 FIGHTING／STANDING。
    全域的 `characters` 是遊戲裡所有的角色（玩家和 NPC，所有區域物件裡的），找同房間的人都從這裡找。
  - `Player(name, writer, room, sex)`：多了 `writer`（連線）和 `reply`（最後一個 tell 我的玩家），`send()` 寫到連線。
    建立角色或讀檔時才填的屬性：`password`（雜湊）、`race`、`guild`、`level`、`primaries`（角色自己的主屬性）、`resource_roll`、`skills`（會的技能，見下面「技能」）、
    `hp`／`mp`／`mv`（現在的值）、`panel`（全部次要屬性的快取）、`gold`（金幣，放在 `Character`：玩家存檔，生物只有別人 give 給牠的；還沒有拿到金幣的地方）。直接 `Player(...)` 建出來的（測試）沒有屬性，`score` 會說看不到。
    升級點數：`points`（還沒分配的）、`trained`（每項主屬性靠升級加了幾點，降級扣回用），**永遠成立 `points ＋ Σ trained ＝ 等級 − 1`**、
    主屬性 ＝ 種族的數字 ＋ `trained`（有測試）。`stats.set_level()` 改等級（升級加 `points`；降級先扣 `points`，不夠再隨機扣加過點的屬性，使用者選的；
    改完從頭算、HP／MP／MV 補滿），`stats.train()` 加點（每項最高 `PRIMARY_CAP` 55）。
    **經驗值**（玩家角色手冊「經驗值」，設計文件 §4.7）：`exp` 是這一級累積的（小數）；`stats.kill_exp()`、`exp_to_level()` 照 balance.py
    （常數 `TIER_DIFFICULTY`、`TIER_EXP_MULT`… 有測試比對）；`gain_exp()` 滿了就 `set_level(等級 ＋ 1)`、扣掉需求，可以連升，滿等不加。
    **前期經驗加成**（`exp_early()`，2026-11-05 使用者定）：打怪的 `kill_exp()` 乘（1 ＋ 加成），1 級 ＋50%、到 99 級 0（`EXP_EARLY_BONUS`、`EXP_EARLY_CURVE`）；
    升級需求 `exp_to_level()` 用 `kill_exp(..., early=False)`，不乘加成。跟種類的經驗加成（`TIER_EXP_MULT`）是兩回事。
    `advance` 改等級時 `exp` 歸 0。`score` 的等級那行寫「經驗 35 / 139」。
    `cooldowns`：技能 id → 還要等幾個 tick（見下面「技能」），不存檔。
    `imm`：管理員（存檔的 `imm`），找得到 `IMM_COMMANDS`。舊存檔沒有 `imm`、`points`、`trained`、`exp`，讀檔時當作 False、0、0、0。
    **第一個 imm 要直接改存檔加 `"imm": true`**，改之前伺服器要先關（不然那個角色離線或伺服器關掉時會存檔，把改的蓋掉）。
    **prompt 每個角色自己的**（`ch.prompt()`，使用者選的樣子）：玩家是 `<HP 62/62 MP 25/25 MV 38/38> `，
    現在的值照剩多少變色（超過 2/3 綠、超過 1/3 黃、其他紅，`level_color()`），上限一般顏色；
    沒有屬性的角色（`Character.prompt()`，例如測試直接建的）是 `config.PROMPT` 的 `> `。
    `online_players()` 是在線的玩家（chat 只找他們；玩家下 tell 先找他們，找不到才找同房間的生物；
    **生物下 tell 先找同一間房**（使用者定的：生物的名字是英文，可能跟線上的玩家同名），找不到才找線上的玩家）。模組的 `send(writer, text)` 給還沒登入時用。
  - **屬性**（`stats.py`，玩家角色手冊、設計文件 §2.6、§3.6、§8）：`Race`（6 個，存檔寫代號 human…spirit）、`Guild`（`SWORD = "phys"` 劍之公會、
    `STAFF = "spell"` 杖之公會，代號跟 balance.py 一樣）、`RACE_PRIMARIES`（手冊的種族表）。
    `naked()` 是裸裝次要屬性（0.75 × 參考值 × G(L) × Σ 主屬性 ÷ 公會標準 × 切片；公會用不到的傷害、龍焰抗性是 0），
    `resources()` 是 MP／MV 上限（兩個公會都有，創角骰一次 0.95～1.05 的倍率，MP、MV 同一個），公會標準用 `equipment.standard_primary()`。
    `recompute(player)` 從頭算 `panel`（設計文件 §8.2：升級、改主屬性、穿脫裝備都從頭算，不要加加減減）；AC 全部來自裝備（護具的基本值）。裝備怎麼加見下面「背包和裝備」。
    數字抄 balance.py，`tests/test_stats.py` 直接比對，設計文件改數字時要一起改。初始主屬性先用種族的數字（公會怎麼套上去還沒決定）。
  - **登入和建立角色**（`login.py`，一問一答照順序寫）：名字 3～12 個英文字母（照 C 版，保留字不行），存成第一個字大寫。
    有存檔就問密碼（錯了就斷線）；沒有就建立：密碼兩次（至少 5 個字）、性別、種族、公會，選完就建好、`zones.enroll()`、站在 `zones.home()`、存檔。
    存檔前再看一次檔案在不在（兩條連線同時建同一個名字，後面的不能蓋掉前面的）。密碼雜湊用 `asyncio.to_thread` 做，不卡住別人。
    **重複登入**（使用者選的，照 C 版）：已經在線上又用對的密碼登入，舊連線收到訊息並斷線，新連線接手同一個 Player（換 `writer`），站在原地。
  - `Npc`（生物）：`send()` 什麼都不做，所以送給 NPC 的訊息等於沒送。區域檔的生物由 `npcs.spawn()` 做出來（重置的 `M`）：
    `name` 是區域檔的 `short`，另外存 `vnum`（遊戲號碼）、`keywords`、`long`、`description`、`level`、`tier`（骰過 `tier_roll`，`roll_tier()`）、
    `attack`／`defense`／`archetype`（代號，算屬性用）、`act`（`area.ActFlag`）。姿勢照區域檔的 `position`（C 版讀了就丟，我們用它），寫錯就站著。
    **出現時就算好全部屬性**：`stats.mob_stats(level, tier, attack, defense, archetype)` 照 balance.py 的 `Model.area_mob()`
    （等級 ＋ 種類的裝備完整度和進度加成 → 攻擊類型 → 原型 → 攻防傾向），存在 `npc.base_panel`（SECONDARY_KEYS、dmg_dragon、mp、mv、wpn、ac；
    `npc.panel` ＝ 它 ＋ 身上的效果，`npcs.recompute()`；測試直接設 `panel` 沒有 `base_panel` 的生物不要放效果）、
    `npc.mix`（攻擊類型比例），HP 補滿；怪物 MP、MV 是 0。常數（`MOB_TIER_FILL`、`ARCHETYPE_TILT`、`BASE_PER_G`…）抄 balance.py，
    `tests/test_stats.py` 比對常數，也把 4 等級 × 4 種類 × 7 攻擊 × 3 攻防 × 5 原型全部跟 `area_mob()` 比。`Npc(name, sex, room)` 直接建的（測試）沒有區域檔的資料。
    `spawn(vnum, proto, room, rng, base)` 也存 `npc.drops`（掉落表，`obj_vnum` 用**牠自己那個檔**的 `base` 換算：M 可以放別的檔的生物），
    所以 `resets.mobiles` 的值是 `(area_number, 生物)`。`names()` 是別人指定牠用的名字（keywords；玩家是名字），`characters.find_in_room()` 用它。
    **生物、物品的 keywords 一律只寫英文**（使用者 2026-11-06 定的；屍體只認 `corpse`）。門的名字、可以細看的東西不算。區域檔檢查還沒擋中文（要擋照區域檔格式的流程，先改手冊）。
    **死掉**（`death.die(npc, killer=)`，照 C 版 raw_kill）：先跑牠的 on_death（腳本，牠被 destroy 了就到此為止）→ 打牠的人和牠停手 → `objects.make_corpse()` → 移出 `characters`（重置的 limit 數不到牠，下次重置再放）。
    imm 的 slay、戰鬥打到 HP 0（`combat.py`）都呼叫它。死亡慘叫（C 版 death_cry）還沒做。
    **玩家死掉**（`death.player_dies()`，使用者選的簡單做法）：打他的人和他停手、`affects.on_death()`、回 `zones.start_room()`、HP 1、站著；不掉東西、不留屍體、不扣經驗。
    look 裡站著、有 `long` 的生物顯示 `long`（照 C 版），其他照姿勢寫「名字站在這裡。」…（`system.appearance()`）。
  - 登入成功的 `Player` 由 `login()` 加進 `characters`；斷線清理在 `handle()` 的 `finally`：先 `stop_fighting()`、存檔，再移出 `characters`，
    也清掉別人身上指向這個玩家的 `reply`。**只在 `me.writer` 還是自己的連線時才做**：被新連線接手的舊連線只關掉，不然會把角色移出遊戲（有測試）。
- **`act()`**（`act.py`）：送訊息給別人一律用它。`to` 決定送給誰：`TO_CHAR` 自己、`TO_VICT` 對象、`TO_ROOM` 同房間自己以外、
  `TO_NOTVICT` 同房間自己和對象以外。`ch`、`vch` 都是角色（玩家或 NPC）。全服頻道（chat）不用 `TO_ROOM`，要自己走訪所有玩家。
  **`TO_ROOM`、`TO_NOTVICT` 不送給睡著的人**（照 C 版）；`TO_VICT` 照送，所以 chat、tell 睡著也收得到。
  代換碼（字母跟 C 版一樣）：`$n`/`$N` 名字（`$n` 送給自己時變「你」）、`$e $m`/`$E $M` 他她它、`$s`/`$S` 他的她的它的、
  `$t`/`$T` 帶進來的文字；小寫是自己、大寫是對象。寫錯的碼原樣保留，並在伺服器視窗印警告。
  `compose()` 跟 `act()` 一樣算出「誰收到什麼」但不送（`act()` 就是用它）：要把好幾句合成一段再送的地方用（戰鬥的一回合）。
  不是哪個角色做的事、而是系統主動送的訊息（例如天氣），用 `notify(ch, text)`：跟 `act()` 送給別人一樣先換行、再補 prompt
  （`act()` 送給別人時就是呼叫它）。`notify()` 不轉顏色代碼。對方自己的指令還沒跑完（在 `scripts.commanding` 裡）就不補 prompt，見下面「腳本」；
  這時好幾句連在一起不空行（使用者要的，`ch.notified`：上一個送的是 notify；`Player.send()` 設回 False），跟指令自己的訊息之間空一行，
  `apart=True` 是另起一段、前面一定空一行（腳本的 `transfer` 送新房間的畫面）。
  **`act.blocks`**（使用者要的：一段裡發生的事一起送）：正在收訊息的一段（戰鬥一回合 `Fight.collecting()`、技能那幾下、`affects.tick()` 的 `Messages`）。
  有的話 `notify()` 放進最上面那一段、那一段結束時每個人送一次，所以打死生物時腳本（on_death）說的話在「斷氣」後面、只有一個 prompt。
  `round()` 不自己 flush，由 `Fight.tick()` 的 `collecting()` 收（連回合後的 on_fight）。
  **`act.gathering()`**（使用者要的：旁邊的人也只有一個 prompt）：`command()` 和一串腳本（`scripts.one_chain()`，例如 on_timer）開一段 `act.Block`，
  送給別人的收起來、結束時每人 notify 一次；已經在收了（戰鬥一回合、外面的指令）就併進外面那段。下指令的那個人不收在 `Block` 裡（照他自己的指令的回覆送）。
- **指令**（`commands/`）：`__init__.py` 的 `COMMANDS` 是指令表，輸入的字照表的順序找**第一個用它開頭的指令**
  （例如 `c` → chat），表的順序就是縮寫的優先順序。指令依類別分檔：系統類在 `system.py`，戰鬥在 `combat.py`，技能在 `skills.py`。
  加新指令：在類別檔寫 `do_xxx(ch, arg)`（`ch` 是下指令的角色，回傳 `False` 代表斷線），再加進 `COMMANDS`。
  **指令表每一筆是 `(指令, 函式, 最低姿勢)`**（照 C 版）：`command()` 先比 `ch.position`，不夠就送 `REFUSALS` 的訊息（照 C 版 interp.c）。
  睡覺、休息時能用哪些是使用者確認過的判斷，表在玩家角色手冊「姿勢和指令」：系統類（chat、tell、reply、who、score、train、quit、
  rest、sleep、stand、imm 指令）睡著也能用；look、say、weather、門的指令要醒著（RESTING）；走路是 STANDING（照 C 版）——休息、睡覺、
  **戰鬥中都不能走，戰鬥中要用 flee**（使用者要的）。新指令加在表的後面，原本的縮寫才不會變
  （所以 rest 要打 res，r、re 還是 reply）。`find()` 回傳函式，`lookup()` 回傳 (函式, 最低姿勢)，`command_name()` 回傳指令名稱（三個共用同一個比對 `_first()`）。
  rest、sleep、stand、say、who 在 `system.py`，訊息照 C 版 act_move.c；睡覺時 rest 是醒過來坐著休息（C 版沒有）；戰鬥中不能改姿勢。
  say 亮白色（照 C 版）；who 照等級排、顏色跟 score 一致。
  **imm 指令**放 `imm.py`，加進 `IMM_COMMANDS`：`find(word, is_imm)` 先找 `COMMANDS`，是 imm 才接著找 `IMM_COMMANDS`，所以原本的縮寫不受影響；
  不是 imm 打 imm 指令，跟打不存在的指令一樣是「什麼？」（照 C 版）。現在有 `advance <名字> <等級>`（在線上的玩家，可以升也可以降，1～100）、
  `slay <名字>`（`sla` 起，直接殺死同房間的生物，訊息照 C 版，不給經驗；不能殺玩家）、`oload`、`ostat`、`mstat`（見下面「背包和裝備」）、
  `restore <名字或 all>`（`resto`，照 C 版補滿 HP／MP／MV，另外清技能冷卻；名字先找同房間、再找線上玩家）、
  `affect <名字> <poison|regen|bless|blind|clear>`（`af`，測試用的效果 `TEST_EFFECTS`，見下面「身上的效果」）、
  `sset <名字> <技能> [off]`（`ss`，照 C 版的名字，讓線上的玩家學會／忘掉技能，imm_only 的不能給）。
  **玩家的指令排在 imm 指令前面**：同字首的玩家指令會搶走 imm 指令的縮寫（之前加了 affects，imm 打 `a` 就變成 affects）。
  **`kill <名字>`**（`commands/combat.py`，`k`，最低姿勢 FIGHTING 照 C 版）：開打同房間的生物，牠自動還手；**不可以打玩家**（使用者要的，自己也不行）。
  **`flee`**（`f`，最低姿勢 FIGHTING，規則在玩家角色手冊「戰鬥」）：機率 `stats.flee_chance()` ＝ min(80%, 10% ＋ 70% × DEX ÷ 55)，DEX 是自己的 ＋ 裝備加的（使用者定的）。
  檢查：沒在打架 → 還在等（`cooldowns["flee"]`，失敗設 `FLEE_WAIT_TICKS` 2，`skills.tick()` 減）→ 開著的出口（關著的門不算）→ 骰 `rng.random()`。
  成功：`rng.choice(出口)` → `death.stop_all()`（自己和打自己的都停手）→ `system.move(ch, 方向, leave=…)`（`leave` 是原本房間看到的那句）。不扣經驗。
  **找同房間的角色一律用 `characters.find_in_room()`**（使用者定的：kill、slay、use，**之後要找生物的指令都用它**，不要另外寫比對）：
  名字跟指令一樣只要打開頭（任何一個 `names()` 用輸入開頭，英文不分大小寫）；`3.dog` 是第 3 個對得上的（照 C 版 number_argument，`0.dog`、`3.` 找不到）；
  順序照 look 畫面（`characters.in_room()`：生物在前、玩家在後，look 也用它），自己排最後（自己也找得到）。
  比對的規則只寫在 `names.py`（`number_argument()`、`pick()`），找物品的 `objects.find()` 也用它（get、wear、`2.sword`…）。
  **`use <技能> [名字]`**（`commands/skills.py`，`us`，最低姿勢 FIGHTING）：**技能只能用 use 放**（使用者要的，技能不是指令；新增技能不用加指令）。
  技能名稱可以縮寫，只找自己會的（`skills.find()`）。檢查順序：沒打技能 → 不會 → 目標（打了名字用 `find_in_room()`；沒打名字是現在的對手，
  還要在同一間房；沒在打架又沒打名字是「你想要攻擊誰？」）→ 玩家 → 冷卻 → MV／MP → 武器，**都過了才開打**（`engage()`），再 `skills.use()`。
  `engage()`（使用者定的）：自己沒在打架就 `start_fight(自己, 目標)`（可以用技能開打）；自己在打架、目標沒在打人就 `start_fight(目標, 自己)`：
  目標加進來打你，**你平砍還是打原本的對手**（照 C 版）；目標已經在打別人就不改誰打誰。
  `skills`（`sk`，什麼姿勢都能用）列出會的技能、傷害範圍、消耗、冷卻。
  **`help`**（`commands/help.py`，`h`，什麼姿勢都能用，使用者選的樣子）：只打 help 是每個分類一行、後面列這一類的指令；
  `help 分類`（整個字一樣）列這一類的指令和一句話；`help 指令` 看說明，**指令跟打指令一樣可以縮寫**（`command_name()`，先轉小寫，`help K` 也是 kill）；
  都不是：「對不起，找不到相對應的說明。」（照 C 版）。imm 的分類（管理員）只有 imm 看得到，不是 imm 也找不到 imm 指令的說明。
  - **說明文字在 `help/help.json`**（`config.HELP_FILE`，使用者選的：不用改程式就能改說明），格式寫在 `helps.py` 開頭：
    `categories`（順序就是畫面的順序、`imm`）、`entries`（`category`、`commands`（一筆可以好幾個，走路的六個方向是一筆）、`usage`、`summary`、`text` 一行一個字串）。
    標題後面的「（縮寫 k）」由程式照指令表算（`shortest()`），不寫在檔案裡。說明不寫會隨等級變的數字（消耗這類），改成「用 skills 看」。
  - 檢查只有一份 `helps.check()`：欄位剛好、型別、分類存在不重複、每個分類都有說明、指令是真的、**每個指令剛好一筆**、imm 指令放 imm 的分類、
    **每個字都轉得成 Big5**。`__main__` 開機時 `helps.load()`，有問題就停止開機（跟區域檔一樣）：**新增或改指令、改規則時，`help/help.json` 要一起改**，
    沒寫說明伺服器開不了機、`test_help.py` 也會失敗。
  - 坑：`commands/__init__.py` import `commands/help.py`，它又要用指令表：`command_name` 在函式裡才 import；`helps.load()` 也是在函式裡才 import 指令表。
    模組在 `__init__` 裡叫 `help_command`（叫 help 會蓋掉 Python 內建的 `help()`）。
  `train <屬性> [點數]` 分配升級點數（`tr` 起才找得到，`t` 還是 tell），屬性可以寫 str 或中文。
  走路、look 這類指令 NPC 也能用（`command(npc, line)`）；reply、quit 只給玩家用（NPC 沒有 `reply`，quit 對它沒意義）。
  `command()` 會在指令跑完後補送 `ch.prompt()`（斷線時不送）。**這個指令有送出訊息就先空一行再補 prompt**，只按 Enter 就直接補（使用者要的）：
  `Player.send()` 會把 `ch.sent` 設成 True，`command()` 開始時歸零。登入的歡迎畫面、`notify()` 也一樣空一行。
  `COMMANDS` 最前面是六個方向（`n e s w u d` 都是走路），接著 `look`。方向指令用 `walk(方向)` 做出來，共用 `move()`。
  `look()` 回傳房間畫面的字串，登入時 `login.py` 也用它。房間描述後**空一行**，再照順序列房間裡的東西（使用者定的）：
  先生物（NPC），再玩家（`characters.in_room()`，找人的 `n.名字` 也照這個順序），最後是地上的物品（`room.contents` 的 `long`，新的在前）；生物、玩家、地上的物品都是**亮白**。
  每個角色照姿勢寫「X站在這裡。」「X躺在這裡睡覺。」…（`LOOK_POSITIONS`）；房間沒有別人就不空行。
  **名字前面的標記**（`tags()`、`tagged()`，使用者要的，照 C 版 show_char_to_char）：生物的種類「(菁英)」亮綠、「(首領)」亮紅（`TIER_TAGS`，一般、雜魚沒有）。
  之後做 buff／debuff：重要效果的光圈（C 版的 (聖光)、(火燄)…）也從 `tags()` 回傳，就會接在那一行前面。
  `score` 看自己的全部屬性（`sc` 起才找得到），使用者選的樣子：**寬 `SCORE_WIDTH` 79 格（跟 C 版一樣），每個數字的位置固定**
  （不照內容算寬度：經驗留 7 位數、HP／MP／MV 7 位數、次要屬性 8 位數，金幣 `gold` 放在等級那行的最後，再長也只往右）。
  暗灰框線、名字用房間標題的綠框黃字、HP／MP／MV 有條（紅、藍、綠，20 格）、下半部三欄對齊，公會用不到的傷害整格變暗；
  imm 在抬頭加「｜imm」，有沒分配的點數就在主屬性後面加「可分配 N」；身上有效果時最下面加一段（見「身上的效果」）。
  有顏色代碼的字補空白用 `cell()`（顏色代碼不佔格）。數字四捨五入成整數（`stats.shown()`，不用 `round()`）。
  對齊用 `width()`：Big5 中文字 2 bytes 也佔 2 格，所以寬度就是 cp950 的 byte 數。
  坑：框線、條、分隔只用 ASCII 和全形字（`=`、`-`、`｜`），不要用 ─ ■ ‧ 這種「寬度不一定」的符號，UTF-8 終端機可能只佔 1 格，會對不齊。
  `look in 東西`（`i`、`in` 都算，最先找，照 C 版）：看地上屍體裡有什麼（「野狗的屍體裝著：」，每件一行、前面空 5 格，空的是「空無一物。」）。
  `look 東西或方向`（照 C 版的順序）：先找房間的 `extra_descriptions`（名字要整個字一樣，英文不分大小寫），
  再當成方向（`n`、`no`、`north` 都算北）顯示出口的 `description`，**不是**隔壁房間的描述。
  沒出口或出口沒描述 →「那裡沒有什麼特別的東西。」；都對不上 →「在這裡找不到你要看的東西。」
- **區域**（`area.py`、`areas/`）：`area.py` 只管區域檔的格式、檢查和 `build_room()`；開機後真的在跑的區域在 `zones.py`（見下面「區域物件」）。
  **規則只有一份：`check_files()`**，照手冊檢查每一個欄位（欄位要剛好，少了或多了都算錯），把所有問題收集起來。
  `zones.load()` 先呼叫它，有問題就報第一個（加上總數）並停止開機，原本的區域物件不動；沒問題才建房間。
  檢查工具 `mud/areacheck.py` 也是呼叫它，所以伺服器和工具的判斷永遠一樣。
  **區域檔格式的流程（使用者定的）：先改手冊和 `areas/test.json`；使用者全部確認後，才會請你照手冊改系統。**
  在那之前，系統只改到「還讀得懂 test.json」為止：`check_files()` 認得新欄位、檢查寫法，
  `tests/area_helpers.py` 和編輯器的 `new_area()` 補上欄位，讓伺服器開得了機、測試會過；遊戲裡的效果不做。
  照手冊改系統時，`check_files()`、`tests/area_helpers.py`、
  區域編輯器（`builder/server.py` 的 `new_area()`、`builder/static/model.js` 的 `newRoom()`、`newExit()` 和畫面）要一起改。
  `Room` 上存了 `name`、`description`、出口（`exits`、`exit_descriptions`）、`doors`（見下面「門」）、`extra_descriptions`、`room_flags`、`sector`，
  還有 `contents`（地上的物品，見下面「物品」）。
  **手冊的三張數字表在 `area.py` 寫成有名字的定義**（使用者要求程式裡不能只有數字）：`RoomFlag`（room_flags）、
  `Sector`（sector）、`Locks`（出口的 locks）。另外 `AreaType`（`header.type`：`world`、`dynamic`、`instance`）是字串的定義，
  手冊「三種區域」的表、編輯器 `model.js` 的 `AREA_TYPES` 都要跟它一樣（有測試比對）。名字用手冊的 C 版名稱（locks 的表沒有名稱，照 C 版的門旗標取），
  中文意思寫在每一行的註解。檢查區域檔只認這些定義；`Room` 存的是 `RoomFlag`、`Sector`，印出來看得到名字
  （例如 `<RoomFlag.DARK|NO_MOB: 5>`）。**改手冊的表時要一起改這些定義**：`tests/test_area.py` 會比對數字和名字，
  註解的中文意思測試看不到，要自己對。**程式裡用名字（例如 `RoomFlag.SAFE`），不要直接寫數字。**
  `room_flags` 用 `parse_flags()` 解析：可以寫數字（`5`），
  也可以寫字串（`"5"`、`"1|4"`，`|` 是把幾個數字的位元合起來，`"1|3"` 是 3 不是 4），只能用 `RoomFlag` 裡有的旗標；
  `sector` 只能寫 0～10 的一個整數（地形一間房只有一種）。伺服器還沒用到這兩個值，只是先存在 `Room` 上。
  **號碼規則**（使用者定的）：
  - 檔案裡的房間、物品、生物號碼各自只能是 1～99；遊戲裡的號碼 ＝ `area.header.area_number` ＋ 檔案號碼（3200 ＋ 3 ＝ 3203）。
    三種號碼分開算（房間 101 和生物 101 可以同時存在），跨檔案的重複檢查也是各算各的。
  - 出口 `to_room` 寫 1～99 是同一個區域（一樣加上 area_number），100 以上是完整號碼，用來通到別的區域。
    門的鑰匙 `key`、區域的 `recall` 也照這個規則（`key` 寫 -1 或 0 是不用鑰匙）；這兩個還沒實作，做的時候要照規則換算。
  - 所以遊戲號碼 1～99 是保留的（`area_number` 不能是 0）：算出來小於 100 就報錯。`area_number` 不必是 100 的倍數。
    `key` 指到的物品存不存在還沒檢查（物品目前只檢查格式）。
    **區域檔格式是我們自己的**：舊區域的流程是 `.are` → area2json → 我們的區域編輯器處理 → 才給伺服器用。
    `mud_design/tools/area_convert/out/*.json` 只是拿來打底的參考，伺服器不直接載入它；兩者已經不同：
    房間沒有 `area_number`，改成寫在 `area.header`；等級範圍只有一個 `header.levels`（`[最低, 最高]`）；
    沒有 `area.name`，之後遊戲要用 header 的資料自己組出顯示的名稱；
    `room_flags`（數字或字串）、`sector`（整數）不是 `{"value": …, "names": …}` 這種 dict；沒有 `overridden_exits`。
    `areas/test.json` 是測試區域（世界區域，`type` 是 `world`）：`area_number` 100，房間 1（南）、2（北）在遊戲裡是 101、102，南北相連；
    起始房間 `config.START_ROOM` 是 101。之後會照使用者的指示繼續改格式。`area`、每個房間、每隻生物、每個物品和每筆重置的欄位**一個都不能少**，
    巢狀欄位也要有範例值（`extra_descriptions` 放一筆；`script`：房間 2 用 `areas/test/鐘聲.lua`、生物 1 用 `商人.lua`、物品 2 是物品的舊格式；生物 1「測試商人」的每個欄位都有值，生物 2「測試坐騎」示範 null／空的寫法；生物 3「野兔」是練功用的 1 級一般怪，重置放 3 隻在房間 2（使用者要的）；
    物品 1～4 是藥水、長劍、箱子、麵包（重置用到 1、3、4），物品 2「測試長劍」每個欄位都有值；物品 5～9 是給 `oload` 試裝備用的（盾牌、匕首（副手）、大劍（雙手）、戒指、皮甲，都沒寫 affects，給顏色就抽隨機屬性；不在重置裡，使用者同意加的）；
    `resets` 每種指令各一筆；房間 1 往北、房間 2 往南的出口是同一扇木門（門兩邊都要寫），給 `D` 的範例用）：使用者靠它看系統還缺哪些功能。
    房間的文字可以用顏色代碼。
    **每個欄位的意思和新系統的實作進度寫在 `docs/區域製作手冊.md`**：改區域檔格式、或做了新的區域功能時，
    要同步更新它（開頭的進度總表，以及各欄位「新系統」那一欄）。
  - **生物（`mobiles`）**：最上層的清單，欄位照舊版 `#MOBILES`（含 A、F、P、R 行）加上 `#SHOPS`（`shop`）、`#SPECIALS`（`special`）整理，
    名稱沿用 area2json；`act`、`affected_by` 寫法同 `room_flags`，`sex` 是整數。
    使用者刪掉了舊版的 `hitroll`、`ac`、`hit_dice`、`damage_dice`、`gold`、`custom`（K 行）、`exp`：系統之後也不用，不要加回來。
    **經驗值只照 `mud_design` 設計文件 §4.7 算**（看怪物種類、等級差和玩家等級的前期經驗加成；使用者 2026-11-03 決定），生物身上沒有經驗倍數。
    **怪物的屬性由程式照「等級 ＋ 種類 ＋ 三個開關」算（設計文件 §4.1～§4.3），區域檔不寫數值**。四個欄位放在 `level` 後面，
    都寫代號（使用者選的），定義在 `area.py`：`tier` 種類（`MobTier`，必填：trash、normal、elite、boss）、
    `attack` 攻擊類型（`AttackType`：一種 `"phys"` 或主／次 `"dragon/phys"`，主 70%、次 30%）、`defense` 攻防傾向（`Defense`）、
    `archetype` 原型（`Archetype`）；後三個寫 `null` 是預設。`check_mob_codes()` 檢查代號；
    手冊的表、編輯器 `tables.js` 的 `MOB_TIERS` 等、`area.py` 的定義三邊要一樣（`test_builder.py` 會比對）。
    `tier_roll`（設計文件 §4.9）：重生時變成其他種類的機率 `{"boss": 100}`，`null` 是固定 `tier`；不能寫 `tier` 自己、加起來不超過 10000。
    `drops` 掉落表（§4.10，取代了舊的 `random_drop`，不要加回來）：每一行 `obj_vnum`、`color`（`ItemColor`：gray～orange，
    不是裝備寫 `null`）、`chance`、`tiers`（`null` 是所有種類都會掉），每一行各自骰。
    **機率一律用萬分之一**（`CHANCE_MAX` 10000 是 100%，使用者選的，跟 `rare` 一樣）。
    物品種類只有一張表：手冊物品那章的 item_type 表（1 照明用具～26 藥錠），商店 `shop.buy_types` 也用它，不要再寫一份。
    使用者會看過再刪減欄位，所以 `check_mobile()` 現在**只檢查寫法**（欄位剛好、型別、號碼），數字代表什麼還沒檢查，
    也還沒寫成有名字的定義（欄位定案後再照「程式裡不能只有數字」補上）。
  - **物品（`objects`）**：最上層的清單，放在 `mobiles` 後面，欄位照舊版 `#OBJECTS`（含 A、E、P 行）整理，名稱沿用 area2json（不放 `values_raw`）。
    使用者刪掉了舊版的 `action_description`、`cost_per_day`：系統之後也不用，不要加回來。
    `cost`（價格）使用者拿掉後又放回來了，可以是 0；商店的 `profit_buy`、`profit_sell` 是乘在它上面的倍率。
    `affects.location`（使用者定的）：0～5 主屬性（照 C 版），6～15 是設計文件 10 種可以用點數買的次要屬性（HP、物理傷害…法術抗性，
    代號同 mud_design 的 STAT_KEYS），16 是龍焰抗性（不算點數，區域作者另外給，設計文件 §5.5）；C 版的 6 性別拿掉了。
    舊區域的 location 數字意思不同，轉檔工具只沿用文字、不帶屬性過來。
    special 的吐息（`spec_breath_*`）算龍焰傷害、施法（`spec_cast_*`）和 `spec_poison` 算法術傷害，是普通攻擊以外額外多打的（使用者定的，設計文件 §4.1）。
    **生物做事只留 special 和腳本**（使用者定的）：舊版的 `actions`、`fight_actions` 拿掉了，寫了是不認得的欄位，不要加回來；舊區域重寫時用腳本寫。
    生物的 `level` 照寫的值，不隨機加減（不照 C 版的 ±1），想要變化用 `tier_roll`。
    武器傷害（`values` 第 2、3 格）、護具防護力（第 1、3 格）由裝備等級算（設計文件 §3.3），作者寫 0；檢查不管這幾格，
    編輯器的 `VALUE_FIELDS` 把它們標成 `auto`（顯示但不能改）。
    `extra_flags` 1～256 照 C 版，512 是新加的「雙手」（使用者定的）：武器同時佔主手和副手，點數上限是兩格加起來（設計文件 §3.3）。
    `area.py` 有 `Apply`（location）、`WearFlag`、`ExtraFlag` 三個定義（跟手冊、`tables.js` 比對）。
    **武器種類**（設計文件 §3.3，2026-11-04 使用者定的）寫在武器 `values` 的第 1 個：`WeaponKind` 1～11（匕首…長槍，全部物理類，沒有弓、法術武器），
    `TWO_HANDED_KINDS`（大劍、戰斧、戰鎚、長槍）一定要勾 512 雙手、單手的不能勾；`DEFAULT_ATTACK` 是每種預設的攻擊方式。
    `Attack` 是 `values` 第 4 個的攻擊方式 0～13（名字用 Merc 的 attack_table，手冊只有中文），`MOB_ONLY_ATTACKS`（重擊、利牙、吸取）武器不能用。
    數值不分種類；背刺只能用匕首（技能還沒做）。手冊的武器種類表、攻擊方式表跟這些定義比對（`test_area.py`），編輯器的 `WEAPON_KINDS` 也比對（`test_builder.py`）。
    **固定裝備**（使用者定的，設計文件 §3.3）：物品寫了 `affects` 就用固定的、不隨機抽；`[]` 才照等級和顏色抽。
    `check_files()` 跨檔案檢查每個放出物品的地方（掉落表用生物等級；`G` 的 level 是 null 就用前面 `M` 的生物等級；`O`、`P` 用 level），
    點數（數值 × 單價）不能超過「部位上限 × 顏色加成」；null、gray 是 ×0，只放得進不算點數的龍焰抗性。
    上限和單價在 `equipment.py`（照 `mud_design/sim/balance.py`，不 import area）；`tests/test_equipment.py` 直接讀 balance.py 比對
    （不寫 .pyc、不改 mud_design；找不到 mud_design 才跳過）。設計文件改數字時要一起改 `equipment.py`。
    `item_type`、`affects.location` 寫數字，`extra_flags`、`wear_flags` 寫法同 `room_flags`。`values` 是 4 個整數或字串：
    法術類（卷軸、藥水、藥錠的第 2～4 個，魔杖、魔棒的第 4 個）寫法術名稱；容器旗標這類要相加，`values` 裡不能用 `|`（C 版用 atoi 讀）。
    `check_object()` 大多只檢查寫法，例外有兩個：主手 8192 和副手 512 同時寫是錯的（使用者定的：武器只能放做出來的那一手，
    兩個都寫會用主手的上限算點數，放到副手就多拿點數）；武器（`item_type` 5）用 `check_weapon()` 查種類、雙手、攻擊方式。可以細看的東西跟房間共用 `check_extra_descriptions()`。物品號碼跟房間、生物分開算。
    `wear_flags` 的位置照 `mud_design` 設計文件 §3.3 的裝備欄位（使用者要求）：512 shield 當「副手」（盾牌或副手武器，雙持的出手規則在玩家角色手冊），
    1 take（能不能撿起來）留著；光源不在 wear_flags，照明用具自己放光源位置。
  - **重置（`resets`）**：最上層的清單，照舊版 `#RESETS` 一串指令照順序執行（`M G O P D R` 和 `*` 註解），`G` 跟著前面最近的 `M`。
    每種 `cmd` 的欄位在 `area.RESET_KEYS`，名稱沿用 area2json。`direction` 寫方向名稱（同出口），`state` 寫數字。
    **使用者說生物不穿裝備**：舊版的 `E`（穿裝備；`wear_loc` 100 是給坐騎）連同坐騎一起拿掉了，`wear_loc` 表也拿掉，不要加回來。
    `G`、`O`、`P` 有 `color`、`level`（使用者定的，設計文件 §3.3）：顏色寫在放出物品的地方（掉落表、G、O、P），物品本身沒有顏色，
    同一件物品在不同地方可以不同色；不是裝備寫 `null`，檢查跟掉落表共用 `check_color()`。物品等級：掉落表用怪物的等級；
    `G` 寫 `null` 也是前面那筆 `M` 的怪物等級（商店要賣低等裝備就自己寫）；`O`、`P` 沒有怪物帶著，一定要寫整數。
    `rare` 的中文叫「**出現機率**」（使用者改的；不要叫稀有度，設計文件的稀有度是裝備的顏色）：只決定生物或物品多常出現，
    **不影響經驗值**（設計文件 §4.8）。
    使用者會再刪改，所以 `check_resets()` 只檢查寫法；號碼指到的東西存不存在、`G` 前面有沒有 `M`、`D` 的出口有沒有門都還沒查。
    **重置做了 `M` 和 `D`**（`resets.py`，照 C 版 `reset_area`、`area_update`）：`rare` 骰萬分之一；`limit` 數同號碼的生物，
    sentinel 數同房間、其他數**同一個區域物件**（手冊寫整個遊戲，但每份副本要各自有生物，使用者確認過）；`tier_roll` 骰種類。
    生物可以是別的區域檔的（`resets.mobiles` 是全部檔案的生物表，遊戲號碼 → (area_number, 區域檔資料)）；房間不在這個區域物件就記 log 跳過。
    `D` 用 `doors.set_state()`，一筆同時設兩邊（C 版一筆只設一邊）；房間或方向沒有門就記 log 跳過。
    **G、O、P、R**（照手冊和 C 版 db.c）：`reset_area()` 記住上一筆 M 這一次放出來的生物（`last_mob`），G 只給它（沒放出來就不做），`rare` 跟 M 同一個骰法（`appears()`），等級 null 是生物等級，放進 `npc.carrying`；
    O 在區域檔的房間沒有玩家（`players_in()`）、地上還沒有同號碼的才放；P 找這個區域物件裡第一件 `container_vnum`（`objects_in()`：地上和生物背包），裡面還沒有才放（照 WindSrc，有玩家也放）；
    R 把前 `exit_count` 個方向的出口、出口描述、門一起隨機對調（`swap_exits()`，C 版的 `d1 = 亂數(d0, n−1)`）。G、O、P 的 `limit`、`if_flag` 不用（手冊寫 C 版沒用到）。
- **區域物件**（`zones.py`，使用者定的三種，`header.type` 決定）：
  - 世界區域（`world`）：開機時把所有 world 檔建進**一個**區域物件 `zones.world`，永遠不釋放。
  - 動態區域（`dynamic`）：有人走進去才建立（`room_at()`），大家共用一份（`zones.dynamic`，檔名 → Zone）。
  - 副本區域（`instance`）：`zones.instance(檔名, 擁有者)` 建立，一個擁有者一份（擁有者用名字；之後是隊長的名字）。
    只能用 enter 進去、recall 出來，所以 `check_files()` 不准出口跨進或跨出副本。enter、recall、傳送門（之後做成物品）、組隊、死亡回 1 號房**還沒做**。
  - 動態區域和副本連續 `RELEASE_TICKS`（1200 tick，20 分鐘）沒有玩家就 `release()`：停掉裡面的戰鬥、移走留下的角色、從名單拿掉。
    在 tick 裡數（`zone.empty_ticks`），有玩家就歸 0，所以實際上是 20 分鐘再加 0～1 秒。下一個人進去時重新建立，裡面全部重來。
  - 區域檔開機時就讀好、檢查好（`templates`），建立動態區域和副本時不讀檔。
  - 每個區域物件記住它有哪些區域檔（`zone.areas`，`resets.AreaReset`，世界有很多個），每間 Room 的 `room.area` 指到它的那個。
    **重置時機照 C 版**（使用者選的）：建立時 `resets.reset_zone()` 一次（世界在 `load()`、動態區域在 `room_at()`、副本在 `instance()`）；
    `Zone.tick()` 每 `AREA_TICKS`（60）呼叫 `resets.update()`：每個區域檔 `age` 加 1，到 3 以後沒有玩家就重置，有玩家到 15 才重置，
    14 時那個區域檔房間裡醒著的玩家收到「你聽到一陣腳步聲。」；重置後 `age` 骰 0～3。
    重新載入（`load()` → `stop()`）會把所有生物從 `characters` 拿掉再重放；釋放區域物件本來就會移走留下的角色。
  - 每間 Room 有 `zone` 指回它的區域物件。走路用 `room_at(from_room, vnum)`：先找自己所在的區域物件
    （所以在副本、動態區域裡走會留在同一份），再找世界，最後是動態區域。
    `find_room()` 順序一樣，但**不會建立**還沒建的動態區域（找門的對面用：關門不能把動態區域建起來）。
- **教學學院**（規則在玩家角色手冊「教學學院」，使用者 2026-11-06 定的）：`areas/academy.json`（副本，`area_number` 200）＋ `areas/academy/` 的三個腳本；
  `builder_area/` 也放了一樣的一份給編輯器。新角色建好就進自己那一份（`zones.instance(ACADEMY_FILE, 名字)`）。
  - 「家」是 `zones.home(player)`：學生（`zones.is_student()`：有學院的區域檔，而且 `player.vars["academy"]["student"]`）是學院的第一間 `ACADEMY_START`，其他人是 `start_room()`。
    建角（`login.create()` 先 `enroll()`）、讀檔（`save.player_from()`：學生一律回家，其他人房間不在世界才回家）、玩家死掉（`death.player_dies()`）都用它。
  - 畢業是院長的腳本拿掉 `student`（`config.ACADEMY_STUDENT`，名字兩邊要一樣），再 `transfer(101)`。程式裡沒有別的畢業判斷。
    腳本的 `transfer` 送玩家就存檔（使用者要的，`script_api.transfer()`），所以畢業馬上存進去。
  - 房間的描述就是教學（`{Y【教學】{x` 那幾行），改教學內容改區域檔就好。
- **tick 和戰鬥的 loop**（使用者定的；C 版是全遊戲一個鐘，我們不照它）：
  - tick loop：世界和全部動態區域**共用一個**（世界 tick，`zones.start()` 開始），每次先做世界、再做每個動態區域；
    **副本每份自己一個**（建立時開始，釋放時結束）。間隔 `TICK_SECONDS` 固定 1 秒（使用者 2026-11-04 從 30 秒改成 1 秒，不加亂數）。
    **定時做的事都用「每幾個 tick 做一次」定義**（使用者定的）：數字在 `config.py`（`ROUND_TICKS` 2、`HOUR_TICKS` 30、`REGEN_TICKS` 30、`AREA_TICKS` 60、`OBJ_TICKS` 30、`AFFECT_PULSE_TICKS` 3、`RELEASE_TICKS` 1200），
    表在玩家角色手冊「定時做的事」，改數字要一起改表。每個區域物件一次 tick 要做的事寫在 `Zone.tick()`，用 `self.ticks % N == 0`：
    世界每 `HOUR_TICKS` 走一次天氣、每 `REGEN_TICKS`（30）所有在線玩家回復一次（`stats.regen()`，照姿勢：站 10%、休息 20%、睡 30%，
    戰鬥中不回）、每個 tick 數技能的冷卻（`skills.tick()`）、走身上的效果（`affects.tick()`）；動態區域、副本數要不要釋放。世界的變換（NPC 行動……）之後加在這裡。
    **掛在角色身上的定時事情（回復、技能冷卻、身上的效果）放世界 tick、全部角色一起做**：副本的 loop 跟世界節拍不同步，放各區域的 tick 會走來走去多做或少做。
  - **天氣**（`weather.py`，tick 的第一個功能）：**全遊戲一個**（`weather.current`），只由世界 tick 走時間（每 `HOUR_TICKS` 呼叫一次 `weather.tick()`），
    副本的 tick 不動它。照 C 版的 `weather_update()`：每 30 tick（30 秒）是遊戲裡 1 小時（一天 24 小時、一個月 35 天、一年 17 個月），
    開機時從現實時間算出來，重開機後接得上。日夜（`Sunlight`）在 6、7、19、20 點改變並通知。
    天空（`Sky`）用氣壓決定，**一小時最多走一格**（晴天 ⇄ 陰天 ⇄ 下雨 ⇄ 打雷）：使用者要求天氣要漸進，不能從晴天直接跳到下雨，有測試。
    **使用者要隨機、季節影響小**：氣壓往季節的目標靠的力氣比 C 版小（`PULL` 1，目標乾季 1010、雨季 990；C 版是 2、1015／985，
    乾季幾乎不下雨）。現在每個季節四種天空都會出現，只是雨季多雨、乾季多晴（有測試）；調這些數字前先模擬看比例。
    **室內只看房間旗標 `8 INDOORS`**（使用者選的，照 C 版）：地形 `0 室內` 不算，地形只管走路。
    通知只送給**室外**（房間沒有 `RoomFlag.INDOORS`）、**醒著**（姿勢比 SLEEPING 高）的玩家；同一小時的好幾句合成一段，只補一次 prompt。
    `weather` 指令（指令表後面，`wea` 起才找得到）：室外顯示幾點、天空、風向；室內「你現在在室內是看不到天氣的。」
    `update(rng)` 的亂數從參數傳進來，測試用假的亂數控制結果。
  - 戰鬥 loop（`fight.py`）：**一場戰鬥一個**，一場＝同一間房裡互打的一群人。每個 tick（1 秒）跑一次，從開打算起，各跑各的節拍。
    一回合 ＝ `ROUND_TICKS`（2）tick：每回合的第一個 tick 打一輪、下一個 tick 停（`Fight.tick()`）。
    **出手照時間軸**（使用者選的，規則在玩家角色手冊「戰鬥的出手順序」，參考 balance.py 的 `simulate_timeline`）：
    `Fight.queue` 是 heapq，每隻手一筆 `(下一次出手的時間, 加入的順序, 第幾隻手, 角色)`，時間用 tick 算、開打是 0。
    `join()` 把每隻手的第一下排在現在；`round()` 把這一回合結束前的出手照時間打出來，每打一下加上間隔 `ROUND_TICKS ÷ 每回合次數`。
    同一時間先加入的先（`start_fight()` 讓先動手的人先加入）、主手先。停手又加入會拿新的順序號碼，舊的排程作廢（`joined`）。
    坑：時間每次加完要取到小數 9 位，不然浮點誤差會把剛好在回合邊界的出手排錯回合（有測試）。
    `attacks(ch)` 是每隻手每回合出手幾次：照攻速 `[damage.attacks_per_round(ch)]`，**雙持**（主手、副手都拿武器）是 `[A × 0.70, A × 0.3608…]`（`damage.DUAL_WIELD_MAIN`、`DUAL_OFFHAND`，跟 balance.py 比對）；沒有屬性的是 `[1.0]`。`hit(ch, victim, hand)` 的 hand 0 是主手。
    **打架中換武器**：`round()` 拿出一筆、`hit()` 之前先看 `hand >= len(attacks(ch))`（脫掉副手武器）就丟掉，不然會用空手多打一下；穿上副手武器 `Fight.arm(ch)` 把副手排在「現在 ＋ 一次間隔」（不排現在：一直換武器會多打）。`Fight.armed` 記排了幾隻手。
    `start_fight()` 開打：第三個人加入同一場；兩場的人互打就把後開的併進先開的（一個人同時只在一場）；被打的人自動還手。
    對手離開遊戲或不在同一間房就停手（`stop_fighting()`），沒人在打這場就結束。戰鬥屬於所在的區域物件（`zone.fights`）。
    對手停了手但還在同一間房、又被打到：拉回這一場（在別場就合併），C 版也是這樣。
    **出手**：`fight.hit()` 呼叫 `combat.hit()`（測試照舊可以換掉 `fight.hit`、`fight.attacks`）。
    - **傷害公式在 `damage.py`**（設計文件 §2.3～§2.5、§8.1），照 balance.py 寫：命中、減傷（物理、法術加 AC，龍焰只看龍抗）、
      `per_hit()` ＝（傷害點數 ＋ 武器基本傷害）×（1 − 減傷）× 1.0778^(L攻 − L守)、爆擊、攻速，參考值用持有者自己的等級。
      `strike(a, d, rng)` 是一下（`(傷害, 爆擊)`，沒中是 0），**亂數順序跟 balance.py 的 `_strike_once` 一樣**（混合型先骰類型 → 命中 → ±20% → 爆擊），
      `tests/test_damage.py` 用同一個種子比對每一下，改它時不能多叫或少叫一次亂數。空手的玩家、生物每一下 ±20%（照模擬）；**玩家那隻手拿武器時，武器值 ＝ 下限 ＋ (上限 − 下限) × 亂數，放在 ±20% 那一格、不再 ±20%**（mud_design 確認的；balance.py 沒有拿武器的函數，`test_gear.py` 比對公式）。
      生物的攻擊類型是 `npc.mix`，玩家是自己公會那一種；武器基本傷害生物是 `panel["wpn"]`，玩家是那隻手的武器（`damage.weapon_in()`）。拿武器時訊息的「直拳」換成武器的攻擊方式（`area.ATTACK_NAMES`，手冊的表，有測試）。
      技能用同一個 `strike()`，多給 `kind`（技能的公會）：一定是這個類型、不骰類型。
    - `combat.hit()` ＝ `strike()` ＋ `land()`；`land(battle, ch, victim, dmg, crit, attack)` 是打出去的一下（平砍和技能共用），回傳目標死了沒：扣 HP、C 版 dam_message 的訊息（程度看傷害佔 HP 上限幾 %，`SEVERITY` 表；自己那句亮綠、被打亮青、同房間的不上色，
      玩家用「直拳」，生物沒有武器名稱，爆擊加「爆擊！」；使用者選的）。HP ≤ 0：「$n已經斷氣，倒在地上死亡了!!」，
      生物 → 打出最後一下的玩家拿經驗（`stats.gain_exp`，還沒組隊）→ `death.die()`；玩家 → 「你已經含恨死去了」→ `death.player_dies()`。
      HP 到 0 之後那段是 `slain(out, killer, victim)`：`out` 是有 `tell()` 的（`Fight`，或身上的效果那個 tick 的 `affects.Messages`），被持續扣血扣死也用它。
      亂數用 `combat.rng`（測試換掉）。一開始就記住 `ch.fight`：打死時 `die()` 會把它清掉。
    - **一回合的訊息合成一段**：`combat` 用 `act.compose()` 放進 `Fight.messages`（`Fight.tell()`），`round()` 結束（`finally`）時 `flush()`，
      每個人只 `notify()` 一次（一下一個 notify 會冒出好幾個 prompt）。`flush(me=ch)`：ch 那段當作指令的回覆送（`send`，prompt 由 `command()` 補），技能用。
    - **技能**（`skills.py`，規則在玩家角色手冊「技能」，設計文件 §2.6）：`Skill` 的資料照 balance.py 的 `SKILLS`，**新增傷害技能只要在 `SKILLS` 加一筆**
      （還有 `help/help.json` 的說明）。**技能自己設計誰會**（使用者定的）：`starter` 是建立角色就會的公會，空的要用程式加（`learn()`：之後的學習、技能書，現在是 imm 的 `sset`）；
      `imm_only` 是只有 imm 會（imm 自動會，`learn()` 不加；balance.py 沒有，測試只比其他的）。
      會的技能是 `Player.skills`（id 的清單，存檔）：建立角色時是 `starter(公會)`，舊存檔沒有就補上；之後新增的 starter 技能舊角色不會自動會。
      `known()` 照 SKILLS 的順序：`ch.skills` 裡有的 ＋ imm 的 imm_only（SKILLS 拿掉的 id 不算）；不會的用 use 是「你不會這個技能。」。
      **`guild` 是技能的路數，不是誰會**：傷害類型（`damage_kind()`）、扣 MV 還是 MP（`resource()`）、`cost()` 用哪個公會標準都看它（學了別的公會的技能也照技能的公會）；
      `None`（imm 的技能）是使用的人的公會（固定寫法術的話劍之公會打不痛），沒有資源、`cost()` 是 0。
      現在的 imm 技能是測試用的天雷（`thunder`，1 下、比率 10，數字是我們訂的）。**imm 用任何技能都不扣、不設冷卻**（`free()`，使用者選的，方便測試）。
      `cost()` ＝ max(1, .5 進位(這個等級的公會標準 MV／MP × 消耗比率))（`stats.resource_standard`，不是自己的上限）；
      夠不夠付看**四捨五入後**的 MV／MP（prompt 上的數字，使用者選的），扣完最少 0。
      `display_range()`（skills 顯示）：拿主手武器是設計文件的（傷害點數 ＋ 武器下限／上限）× 比率；空手是傷害點數 × 比率 × (1 ∓ `DMG_VAR`)（使用者選的，跟實際一樣）。
      `use()`：`pay()`（扣消耗、`cooldowns[id] = 冷卻`；沒有資源的不扣、冷卻 0 的不設，所以生物也能用這種技能）→
      傷害技能打 `hits` 次（`strike(kind) × ratio` → `land()`，死了就停），**打指令當下就打**（不排進時間軸，平砍照打），最後 `flush(me=ch)`；
      **增益技能**（`kind` `"buff"`、`target` `"ally"`）走 `buff()`：把 `make_affect(skill)`（`skill.affect` 是 `Affect` 的欄位，每次 deepcopy 一份；
      **`source`、`name` 沒寫就用技能的 id、名稱**，使用者定的，不一樣才寫）放到目標身上、送訊息，不開打。
      use 指令對增益技能：沒打名字是自己，打了名字用 `find_in_room()`，只能放玩家（`ready()` 是冷卻、MV／MP、武器的檢查，兩種技能共用）。
      **餽贈**（`gift`，使用者定的，之後教學區的 NPC 送給玩家）：每 3 秒補 HP 上限的 10%、主屬性各 +3，3600 秒，死掉後還在；要用程式加、不扣消耗、沒有冷卻。
      **打中最低 `MIN_SKILL_DAMAGE` 1 點**（使用者定的，技能不是平砍；失手還是 0）。**持續傷害** `Skill.dot`（火球的燃燒：name、ratio 0.3、jumps 3、hurt 燒傷）：
      第一發打中、目標沒死就 `dot_affect()`（每 3 tick 跳、共 jumps 次、每跳 ＝ 第一發 × ratio 最低 1，來源是技能 id），
      走 `affects.pulse()` 的持續扣 HP（護盾、扣死、矮人照舊），`Affect.hurt` 有寫就每跳說「你被【燃燒】燒傷了.(6)」（`combat.damage_tail()` 跟戰鬥訊息共用）。
      **天護**（`aegis`，使用者定的）：護盾 HP 上限的 120%、10 秒，要用程式加、不扣消耗、沒有冷卻；`skills` 列出時寫「護盾 HP 上限的 120%」（`affects.parts(listing=True)`）。
      **NPC 直接呼叫 `skills.use(npc, SKILLS["gift"], 玩家)` 就能放**（不用學、不用在打架）。`skills` 指令的增益技能：那一行寫持續多久，做什麼放下一行（`system.wrap()`，不超過 79 格）。
      冷卻用 tick 數：世界每個 tick `skills.tick()` 減 1，所以實際等 5～6 秒。
      `weapon_ok()`：有限用武器的技能，主手要拿那種武器（空手不行）；技能那一下用主手的武器。還沒做：學習、技能書、補血、減益、打一群、怪物打架時用技能。
    - 坑：`fight` → `combat` → `death` → `fight` 繞一圈：這幾個模組互相都用 `from . import 模組`，不要 `from .fight import stop_fighting`、`from .combat import hit`。
    - 還沒做：安全區、生物回血、生物主動攻擊、生物逃跑、C 版「快死了」「昏迷」（HP ≤ 0 就是死）。
  - **身上的效果**（buff／debuff，`affects.py`，規則在玩家角色手冊「身上的效果」，設計文件 §2.6）：`ch.affects` 是 `Affect` 的清單，玩家和生物都有。
    `Affect`：`source`（哪個技能放的，**同一個來源只有一份**：`add()` 是覆蓋，不同來源就疊）、`name`、`duration`、`ticks`（還剩）、
    `elapsed`（放下去後幾個 tick，**跳的時間點看它、不看剩下的**：矮人每 tick 減 2，用剩下的會跳錯時間）、
    `applies`（屬性加減，`stats.add_affects()` 加進 panel：次要屬性照加；**主屬性照 `primary_bundle(公會, 主屬性, 被放的人自己的等級)` 換算**（使用者定的），
    生物沒有公會不算；負重、MP／MV 上限、55 上限只看自己的主屬性）、`periodic`（hp／mp／mv 每 `AFFECT_PULSE_TICKS` 3 加減固定量）、
    `periodic_pct`（每跳一次加減**當時上限**的幾成，例如餽贈的 `{"hp": 0.10}`；扣 HP 的也算矮人的堅韌、也會扣死，`drains_hp()`）、
    `flags`（`area.AffectFlag`，現在只是記號；`AFFECT_FLAG_NAMES` 跟手冊比對）、`keep_on_death`、`off_message`（有寫才用，沒寫是共用的 `affects.off_message()`：「你身上的【名字】消失了。」，使用者要的）、
    **護盾** `shield_pct`（HP 上限的幾倍，使用者 2026-11-06 定的效果，名字是我取的「護盾」）和 `shield`（還剩幾點，`add()` 照當時的上限算，覆蓋就是回到滿的）。
    扣 HP 的地方只有兩個，都先 `affects.absorb()`（先放的先扣，扣光的拿掉）：`combat.land()`（平砍、技能；訊息加「（吸收 N）」`ABSORBED`）、
    `affects.pulse()`（持續扣血）。被打破的訊息 `broken_messages()` 放進同一段。**新增會扣 HP 的地方也要先 absorb**。
    效果變了就 `changed()`：從頭算（玩家 `stats.recompute`、生物 `npcs.recompute`），HP／MP／MV 夾在新上限（`stats.clamp`，上限變高不補）。
    `tick()` 在世界 tick 每個 tick 做（全部角色，副本裡的也是；離線的不在 `characters`，所以時間停住）：`elapsed` ＋1、`ticks` 減 1
    （矮人身上持續扣 HP 的減 `TOUGH_STEP` 2）、`elapsed` 是 3 的倍數就跳、`ticks ≤ 0` 拿掉（跳完才拿掉，60 tick 剛好跳 20 次）。
    跳：加不超過上限，MP／MV 最少 0，**HP 扣到 0 就死**（使用者定的）：`combat.slain(out, ch.fighting, ch)`，打架中算被他正在打的對手打死（照常給經驗），
    沒在打架 `fighting` 是 None、誰都不給。一個 tick 的訊息（消失、死掉）收在 `Messages`，每人只 notify 一次。
    存檔整個存（`to_data()`／`from_data()`，剩下的時間和 `elapsed` 都在），讀檔先放回效果再 `recompute()`。
    **沒有 affects 指令**（使用者要的）：身上的效果照 C 版列在 `score` 最下面（`system.affect_lines()`，`parts()` 是做什麼、`seconds_left()` 是實際還要等的秒數）；
    說明太長就用 `wrap()` 換行，接在下一行對齊，不超過 79 格。mstat 用 `describe()` 寫成一行。真正的效果、放效果的技能、光圈還沒做（光圈接 `system.tags()`）。
  - 定時器共用 `clock.every()`：照 `loop.time()` 排時間不會越跑越慢，超時了從現在重新算、不追趕。
  - **loop 裡做的事不能卡住**：`Zone.tick()`、`Fight.tick()` 都是普通函式，要很快做完，不能 `time.sleep`、不能讀檔。
    每個 loop 自己接住錯誤：tick 出錯記 log、下次照跑（世界 tick 裡每個區域物件分開接）；一場戰鬥出錯只結束那一場。
  - task 一定要有人拿著（asyncio 只用弱參照記 task）：`zones.world_task`、副本的 `zone.task`、戰鬥的 `fight.task`。
- **區域編輯器**（`mud/builder/`）：給區域作者用的網頁，畫面照設計稿（https://claude.ai/artifact/UwgbazUdvQKNEiPLQE8GW5）。
  區域檔存在 `builder_area/`（`config.BUILDER_DIR`），port 1234（`config.BUILDER_PORT`）。只用標準庫，前端不用打包工具。
  - 後端 `server.py`（`ThreadingHTTPServer`）：給網頁檔案，讀、存、檢查區域檔的 JSON API（清單寫在檔案開頭）。
    檔名只收 `英數字_-.json`，網頁檔案只給 `static/` 裡的。存檔格式跟 `areas/test.json` 一樣（縮排 2、中文照寫、結尾不換行），
    `test.json` 存回去要一個 byte 都不差（有測試）。
  - **檢查只用 `area.check_files()`**：還沒存的內容寫進暫存資料夾的同名檔去檢查，對照 `builder_area/` 裡其他檔名的檔
    （同名的舊檔不對照，不然會全部「重複」）。有問題也照樣存，還沒寫完也要能存。
  - 讀檔時也回傳別的檔的房間名（`elsewhere`）、生物名（`elsewhere_mobiles`）、物品名（`elsewhere_objects`），給號碼旁的名字標籤用。
  - 前端 `static/`：`model.js` 是純資料操作，`editor.js` 是編輯畫面的外框和房間畫面，`files.js` 選檔畫面，`settings.js` 區域設定（含區域種類 `type` 的下拉選單），
    `ui.js` 小工具，`forms.js` 綁在區域檔物件上的表單欄位（改了直接寫回），`app.js` 用網址的 `#檔名` 換畫面。
    載入的 JSON 直接改，**沒動到的欄位原樣存回去**（例如 `"1|4"`、物品的 `script`）。
    房間、生物的 `script` 是兩格（`forms.js` 的 `scriptFields()`：`file`、`timer`，兩格都空著存成 null）；物品的只顯示（`scriptRow()`）。
    檢查腳本用 `check_files(..., script_root=編輯器的資料夾)`，所以 `.lua` 放在 `builder_area/區域檔名/`。
  - **左欄上方切換四種畫面**（`state.mode`）：房間（中間地圖、右邊分頁，多一個「重置」分頁在 `roomresets.js`）、
    生物（`mobiles.js`）、物品（`objects.js`）：沒有地圖，右邊表單佔滿；重置總覽（`resets.js`）：照檔案順序的表格，可拖曳排順序。
    各畫面模組拿 `editor.js` 的 `ctx`（`state`、`edited()`、`rebuild()`、`refresh()`、`goRoom()`、`chipOf()`），不互相 import 成一圈。
    **分頁規則（使用者定的）**：只有一份的欄位放同一個分頁，可以一直新增的清單才各自一個分頁。
  - **號碼一律比算出來的遊戲號碼**（`model.js` 照 `area.resolve()` 寫了一份）：同一區域也可能寫完整號碼（101 指到房間 1）。
    房間、生物、物品的號碼分開算。改號碼時這個檔裡指到它的地方一起改（出口、recall、重置、生物掉落表的 obj_vnum、出口的 key，`renumberThing()`）；
    刪除時指到它的重置一起刪，M、O 後面跟著的 G、P 也一起刪（`deleteRoom()`、`deleteThing()`），確認視窗會寫刪幾筆。
  - 重置的分組：緊接在 M 後面的 G、O 後面的 P 算跟著它（`followersOf()`、`leaderOf()`）。房間分頁新增時，M、O、D、R 加在最後，
    G、P 插在它跟著的那筆後面；總覽新增時插在選到的那筆後面。
  - 區域檔的文字一律當純文字放進畫面（`h()` 的子元素字串是 textNode），不用 `innerHTML`。
  - `model.js` 有旗標、地形、門的數字表，`tables.js` 有生物、物品、重置用的數字表（畫面用的短名字）。**改手冊的表時要一起改**：
    `test_builder.py` 會比對 `model.js` 跟 `area.py` 的定義、`tables.js` 跟手冊的表。
- **門**（規則在區域製作手冊「門」）：出口的 `keywords` 是門的名字，只有 `locks` 不是 0（有門）的出口才用到。
  門的種類只看 `locks`（0 沒有門，1～8 是門加上撬不開、撞不開、法術穿不過的組合，對照表在手冊，程式裡是 `area.Locks`），區域檔沒有 `door_flags`。
  - `area.Door`：`build_room()` 放進 `room.doors`（方向 → Door，只有有門的出口）。名字清單、`locks`、`key`（遊戲號碼；-1、0 是 `None`，鎖不起來），
    現在的狀態 `closed`、`locked`（一開始開著，重置 D 設定，`Door.set(DoorState)`）。`name` 是第一個名字，沒寫是「門」。每份副本自己的 Room，門各自分開。
  - **門兩邊都要寫**（使用者選的）：`check_doors()` 查有門的出口通到的房間，往回的出口（反方向、指回來）也要有門；單向出口不算。
    算在有門的那一邊；門在別的檔時沒寫門的那一邊也報（編輯器只檢查一個檔）。兩邊一起變靠 `doors.other_side()`、`doors.set_state()`（`mud/doors.py`，指令和 D 共用）。
    坑：`zones` → `resets` → `doors`，所以 `doors.other_side()` 在函式裡才 import `zones`。
  - 指令在 `commands/doors.py`：open、close、lock、unlock（RESTING，照 C 版），檢查順序照 C 版 act_move.c。撬 pick、撞 bash **等技能做好再做**（使用者選的）。
    `find_door()` 找的順序（使用者定的）：門的名字（整個字一樣）→ 方向 → 東西（地上、背包、身上，`objects.find()`）；回傳方向或 Obj，所以 `open n` 一定是門（C 版是先找東西）。拿到 Obj 就走容器那幾個函式（`open_container()`…，訊息照 C 版）。
    `has_key()`：背包或身上有那個遊戲號碼的物品（照 C 版 has_key 看身上全部）。
  - 門關著還要走過去：有 `keywords` → 「【鐵門】關起來了。」（取 `keywords` 的第一個字）；
    **沒寫 `keywords` → 用方向，例如「北方關起來了。」**（C 版沒寫時是顯示 door，我們不照它）。
  - **對面看得到**（使用者要的）：打開、關上（之後的撞開也是）時，對面房間醒著的人收到「南方的木門被打開了。」（`doors.tell_room()`）；
    對面很暗（`Room.dark()`：`RoomFlag.DARK` 而且沒有光源，光源是物品，還沒做）就看不到。上鎖、開鎖對面不知道（照 C 版）。
    那一句是 `doors.tell_other_side()`，玩家的 open／close 和腳本的 `room:door` 共用（腳本真的打開、關上了才說，使用者要的）。
  - look 的出口：關著的門是紫色 `*北`（照 C 版）；`look 方向` 描述後面加「木門是關著的。」／「是開著的。」。
- **物品**（`objects.py`，規則在區域製作手冊「屍體」、玩家角色手冊「物品和裝備」）：遊戲裡真的出現的物品：屍體和裡面掉落的、重置 G／O／P 放的、imm 用 `oload` 做的。
  - **容器**：`obj.container`（`area.ContainerFlag`，從 values 第 2 個開始，開關、上鎖改它）、`key`（values 第 3 個，換算跟出口的 key 一樣，`area_number` ＝ 遊戲號碼 − 檔案號碼）、`seal`。屍體的 `container` 是 None，一直開著。
    關著的拿不出東西（「【X】關起來了。」）、`look in` 看不到（「它是蓋起來的。」）；封印著的撿不起來；可以封印又有密碼的打不開（封印的指令還沒做）。
  - **生物死掉**：屍體裡 ＝ 掉落表 ＋ 牠背包裡的；**店主（`npc.shopkeeper`）背包裡的直接消失**（使用者選的，照 C 版）。
  - `Obj`：`vnum`、`keywords`、`name`（short）、`long`、`item_type`、`level`、`color`、`affects`（`[(Apply, 數值)]`）、`base`（武器傷害範圍或 AC）、`contains`、`timer`、
    `weight`、`take`（wear_flags 有 1；屍體沒有）、`slot`（`equipment.best_slot()`，跟點數上限同一個；雙手武器是 `TWO_HANDED`）、武器的 `weapon_kind`、`attack`。只放現在用得到的。
    **沒有全遊戲的物品名單**：放在 `room.contents`（地上，新的在前）、`obj.contains`（屍體裡）、角色的 `carrying`、`equipment`；
    地上的在區域物件釋放、重新載入時房間不要了就跟著不見（使用者要的，有測試）。
  - `find(objs, name)` 跟找生物同一個規則（`names.py`）。`to_data()`／`from_data()` 是存檔用的，整件存（區域檔改了身上的照舊）。
  - `protos`：遊戲號碼 → 區域檔的物品（`zones.load()` 跟 `resets.mobiles` 一起在 `stop()` 後面換）。`create(vnum, level, color, rng)` 照區域檔做一件：
    有穿戴部位的是裝備，寫了 `affects` 用寫好的（固定裝備），`[]` 就 `equipment.roll_item()` 隨機抽，名稱接在名字前面（「疾風之蠻力長劍」，使用者選的）。
    部位用 `area.wear_slots()` ＋ `equipment.best_slot()`（固定裝備檢查上限也用這兩個，所以是同一個部位）；副手的武器是副手武器。號碼找不到記 log、回傳 None。
  - **`equipment.roll_item()` 照 balance.py 的 `Model.roll_item` 寫，亂數的用法和順序一模一樣**：`tests/test_equipment.py` 用同一個種子比對每個部位、顏色、等級，
    結果要完全一樣（詞綴、名稱）。改它時不能多叫或少叫一次亂數，`AFFIX_WORD` 的順序也不能動（`rng.choice` 照順序挑）。
  - `make_corpse(npc, rng)`：「野狗的屍體」（`area.CORPSE_NPC_ITEM_TYPE`）、地上「野狗的屍體橫躺在地上。」（後面由 `on_floor()` 接 /corpse，使用者定的）、名字只有 `corpse`（使用者定的：生物、物品的名字一律英文）、`timer` 10～14（照 C 版）；
    `roll_drops()` 每一行各自骰（`tiers` 對不上不骰，萬分之一），物品等級是生物等級、顏色是那一行的。
  - 名字（使用者選的，`short()`）：「測試藥水/potion」。名字裝備照顏色（灰 `{D`、白 `{W`、藍 `{B`、紫 `{M`、橘用暗黃 `{y`），其他亮綠 `{G`；
    `/` 後面是 keywords 裡的英文字，亮青 `{C`（照 C 版），沒有英文字就只有名字。地上那一行（`on_floor()`）：描述亮白，後面接「/英文名字」亮青（`english_tail()`，使用者定的：「一把測試長劍插在地上。/sword」）。區域作者寫的名字不轉顏色代碼（跟生物一樣）。
  - **消失**：`Zone.tick()` 每 `OBJ_TICKS`（30）呼叫 `objects.update()`，地上有 `timer` 的減 1，到 0 連同裡面的東西一起拿掉，醒著的人看到「野狗的屍體腐爛變成了灰塵。」
    （同時好幾具合成一段、只 notify 一次）。**不管屍體有沒有東西都照時間消失**（使用者選的，照 C 版）。
    坑：呼叫要放在 `Zone.tick()` 兩個提早的 `return` 前面，不然世界的、有人站著的副本裡的屍體不會爛（有測試）。
- **背包和裝備**（`inventory.py`、指令在 `commands/items.py`，規則在玩家角色手冊「物品和裝備」，訊息照 C 版 act_obj.c）：
  - `ch.carrying`（新的在前）、`ch.equipment`（部位 → Obj；部位、eq 的名稱和順序是 `inventory.SLOTS`，照 C 版 where_name；戒指 `finger_l`／`finger_r`，
    雙手武器只放在 `wield`，`blocker()` 把副手當成被它佔住）。**生物不穿裝備**（使用者說的）：wear、remove 對生物是「你沒有辦法使用這項物品。」
  - get（地上、`get x 屍體`；`get all` 跳過撿不起來的，拿不動說一次就停，照 C 版）、drop、
    give（照 C 版：給同房間的人、`give N coins 名字` 給金幣、1 級不能給金幣、店主不收、對方是玩家要 `over_limit()` 放得下，給完 `keep()` 幫給的人存檔）、
    wear（`wear x` 換下原本的；`wear all` 只穿空的部位，副手武器排最後）、
    remove（`remove all` 照 SLOTS 的順序，副手在主手前）、inventory（最後一行件數和負重，使用者選的）、equipment。最低姿勢照 C 版：前四個 RESTING（打架中可以），後兩個 DEAD。
  - 限制：裝備等級（角色等級 < 裝備等級不能穿，設計文件 §3.4）、件數 `stats.CARRY_COUNT` 35、負重 `stats.carry_limit()`（STR 表、獸人 ×1.25，身上穿的也算）、
    武器重量 `stats.wield_limit()`（每一把武器自己比）；兩張表抄手冊（`test_gear.py` 比對）。生物不檢查件數、負重。
    副手武器要主手先拿（單手）武器；雙持時不能先卸主手（這兩句訊息是新加的）。
  - 訊息合成一段送（`inventory.Lines`：自己那段是指令的回覆，別人每人 notify 一次）。
  - 穿脫之後 `inventory.changed()`：`stats.refresh()`（從頭算、HP／MP／MV 夾在新上限）、打架中 `Fight.arm()`。
  - **屬性**（設計文件 §8.2，mud_design 確認）：`stats.recompute()` ＝ 裸裝 ＋ MP／MV ＋ 每件 `gear_bonus()`：次要屬性（含龍焰抗性）照加、
    主屬性 × `primary_bundle(公會, p, **裝備等級**)`（照 balance.py，`test_gear.py` 跟 `apply_points` 比對）、AC 加總。負重、武器重量、MP、MV 只看角色自己的主屬性；
    score、mstat 的主屬性顯示角色 ＋ 裝備、效果加的（`extra_primaries()`，四捨五入顯示）；flee 的 DEX 只算角色 ＋ 裝備（`gear_primaries()`）。
  - 存檔多 `carrying`、`equipment`（`objects.to_data()`），讀檔先放回裝備再 `recompute()`；舊存檔沒有就是空的。死掉不掉東西。
  - imm 的 `oload <號碼> [等級] [顏色]`（`commands/imm.py`，`ol`）：撿得起來放自己背包，撿不起來放地上（同房間看得到，照 C 版）；不檢查件數、負重。
  - `examine`（`ex`，`commands/items.py` 的 `identify()`）：**只看背包和身上的**（使用者要的），句型照 C 版 identify，每種東西只列有的行。
    imm 的 `ostat <名字>`（`os`：背包、身上、地上、地上屍體裡，照這個順序）／`ostat <號碼>`（區域檔的寫法）、`mstat <名字>`（`m`：同房間的生物或玩家）：
    全部資料，數字留小數。名稱用 `area.ITEM_TYPE_NAMES`、`WEAPON_KIND_NAMES`、`ATTACK_NAMES`（手冊的表，有測試）、`equipment.STAT_NAMES`、`SLOT_NAMES`、`COLOR_NAMES`。
- **腳本**（Lua，規則在區域製作手冊「腳本」，使用者 2026-11-06 定的）：房間、生物的 `script` 是 `{"file": "x.lua", "timer": 秒數或 null}`，
  `.lua` 放在跟區域檔同名的資料夾（`areas/test/`）。物品的腳本還沒做（物品的 `script` 還是舊格式 `{"trigger", "function"}`，`check_object_script()`）。
  - 開機檢查在 `area.check_lua()`（`check_files()` 呼叫，所以伺服器、`areacheck`、編輯器一樣）：檔案、資料夾、UTF-8、Big5、語法、最外層跑得過、不認得的 `on_` 函式、timer 和 on_timer 成對、timer 1～3600。
    觸發時機的表是 `area.ROOM_TRIGGERS`（5 種）、`MOB_TRIGGERS`（10 種）。最外層用 `lua.check_env()` 跑（`me`、`room` 是假的替身）。
  - `lua.py`：沙箱（全遊戲一個 lupa 的 Lua 5.4）。每次觸發重新 `load()`（新的 env）、`spawn()` 回傳 coroutine、`step()` 跑一段（`done`／`wait`／`error`）。
    每一段 `BUDGET` 10 萬個指令（count hook）；超過、或 Python 判定出錯（`wrap()` 包的函式丟錯）就 `kill`：腳本裡每個指令都丟錯誤，pcall 接不住。
    腳本沒有 coroutine、os、io、load、debug…；字串的方法只留 `byte char len lower upper sub format rep reverse`。
    給 Lua 的角色、房間是 handle（Lua 的表，方法是綁好的 Python 函式），`obj_of()` 用腳本拿不到的弱參照表換回來。
  - `scripts.py`：讀好每個 .lua（`library`）、接上主人（`attach_room()`、`attach_mob()`）、`fire(房間, 時機, actor, 參數…)`（先房間、再生物照 `arrived`）、
    `fire_owner()`（只跑一個主人）、wait（`schedule()`，測試換掉）、出錯 `report()`（記 log、線上 imm 一行，同一個錯 `REPORT_EVERY` 60 秒一次）、`tick()` 數 timer。
    **一串裡每個主人只跑一次**（使用者選的，`chain`；`one_chain()` 最外面那次清掉：`fire()`、`fire_owner()`、wait 完的 `later()`）：
    只擋「繞回自己」的話，好幾隻生物互相觸發每一條路都跑一次（10 隻 3 萬多次、伺服器卡 5 秒）。
    `running` 是正在跑的堆疊，最多 `MAX_DEPTH` 5 層；actor 是主人自己也不跑。**錯誤都在這裡接住**，不往外丟。
    `commanding` 是正在打指令的人的堆疊（`command()` 推進來）：`act.notify()` 送給還在裡面的人時當作指令的回覆、不補 prompt
    （生物的腳本在他說話的當下回話，才不會有兩個 prompt；指令跑完 `command()` 補一個）。
  - **`docs/Lua任務教學.md`**（使用者要的，從手冊獨立出來，只講怎麼做任務）：例子都實際跑過。改了腳本的函式、訊息、規則時，教學裡的例子和畫面也要跟著對。
  - `script_api.py`：給腳本的名字和函式（`me`、`room`、`actor` 的欄位和方法、`random`、`hour`、vars、號碼換算、`transfer`、`load_mob`、`mob:use`…）。
    `give_item`：主人是生物、給的是別人時，訊息跟 give 一樣（`items.GIVEN_TO_YOU`、`GIVEN_SEEN`，使用者要的）；房間的腳本不說話。
    判定「算腳本出錯」就丟 `ScriptError`。玩家的 vars 在 `player.vars[區域檔名][名字]`（存檔），生物、房間的在自己的 `vars`。
  - 觸發的地方：`commands.command()`（on_command，`quit` 不觸發）、`system.move()`（on_enter）、`do_say()`（**只有玩家說的**，使用者選的：生物之間對話用 tell）、`do_tell()`（找不到線上玩家才找同房間的生物，on_tell）、
    `items.do_give()`／`give_gold()`、`death.die(npc, killer=)`（on_death，倒下之前）、`Fight.tick()`（on_fight）、`npcs.spawn()`（on_born）、
    `resets.reset_area()`（先清那個區域檔房間的 vars，再 on_reset）、`Zone.tick()`（on_timer，放在提早的 return 前面）。`zones.stop()` 取消全部在等的。
  - 坑：coroutine 一定要用 lupa 的 `函式.coroutine()` 建、Python `send()` 接著跑。在 Lua 裡 `coroutine.resume` 的話，腳本呼叫 Python、Python 再回頭讀 Lua
    （handle 換回角色、腳本觸發別的腳本）時，lupa 會讀錯，拿到 `(thread, function)` 這種 tuple。所以 hook 由 coroutine 自己掛（開始時、每次 wait 回來時）。
  - 坑：Python 的錯不能穿過 Lua（lupa 釋放上一個錯的 traceback 時會讓整個程式當掉，整套測試跑才碰得到）：`lua.wrap()` 在 Python 這邊接住，回傳 `(成功了沒, 值或錯)`。
  - 坑：`LuaError` 要從 `lupa.lua54` import（`lupa.LuaError` 是另一個類別，接不到）；從 coroutine 丟出來的 `LuaMemoryError` 沒有訊息。
  - 坑：Run 結束時一定要 `finish()`（放掉 handle）：handle 的方法抓著 Run、Run 抓著 handle，Python 和 Lua 互相抓著，兩邊的垃圾回收都收不掉，
    每次觸發漏約 10 KB，Lua 記憶體用完整個程式當掉（PANIC，不是 Python 的錯誤）。`test_finished_runs_free_their_memory` 看著它。
- **顏色**（`color.py`）：字串裡寫代碼，`colorize()` 換成 C 版 `merc.h` 的色碼：`{r{R{g{G{y{Y{b{B{m{M{c{C{w{W{D`
  （小寫暗、大寫亮），`{x` 回到原本顏色，`{{` 印出 `{`，不認得的代碼原樣留著。不能巢狀：`{x` 是全部回到原本顏色。
  `act()` 會先對 fmt 做 `colorize()` 再代換 `$` 碼，所以玩家打的代碼會原樣顯示。`send()` 不轉代碼，要顏色就自己包 `colorize()`。
  目前 chat 用 `{M`（亮紫），tell／reply 用 `{G`（亮綠），跟 C 版一樣。
- **存檔**（`save.py`）：一個角色一個 JSON 檔 `players/名字小寫.json`（`config.PLAYER_DIR`，不進 git），先寫暫存檔再 `os.replace`。
  存主屬性、等級、經驗值 `exp`、種族、公會、`resource_roll`、HP／MP／MV、房間號碼、身上的效果 `affects`、腳本的變數 `vars`，**也寫一份全部次要屬性 `panel`**（使用者要的：打開檔案就看得到全屬性）。
  讀檔（`player_from()`）時次要屬性一律從頭算、蓋掉檔案那份，HP／MP／MV 夾在新上限以內；房間不在世界區域（動態、副本）就站起始房間。
  密碼只存 `hashlib.scrypt` 的雜湊（每個角色自己的鹽），比對用 `hmac.compare_digest`。
  離線時存：quit 和直接斷線都在 `handle()` 的 `finally` 存，`do_quit` 不另外存。建好角色時也存。
  `save` 指令（`sav` 起才找得到，`sa` 還是 say）手動存，什麼姿勢都能用（照 C 版）；存檔失敗記 log、告訴玩家找管理員。
- **紀錄**（`log.py`）：`__main__` 啟動時呼叫 `setup()`。畫面用 rich 的 `RichHandler`，同時用 `DailyFileHandler` 存到
  `logs/日期_編號.log`（例如 `2026-10-30_001.log`）：換日從 001 重新編號，超過 5MB 換下一個編號，只留最新 30 個檔。
  檔名格式不符的檔案不會被刪。
- **設定和分頁**（規則在玩家角色手冊「設定」，使用者 2026-11-06 定的，照 C 版 do_config、show_string）：
  - `config`（`commands/system.py`，`co`）：開關是一張表 `CONFIG_TOGGLES`（名稱、Player 的欄位、說明），加開關只要加一筆；`config lines N` 是分頁每頁幾行
    （`config.PAGE_LINES` 20、`PAGE_LINES_MIN` 19、`PAGE_LINES_MAX` 60）。`Player.autoloot`、`page_lines` 存檔。不做單獨的 `autoloot` 指令（會搶 imm 指令 `a` 的縮寫）。
  - 自動拾取在 `combat.slain()` 的 `loot()`：打死生物的玩家在同一間房（`death.die()` 回傳屍體），開了就 `items.take_all()`、沒開就 `objects.inside()`（look in 也用它）；
    訊息用 `inventory.Lines.pairs()` 放進同一段（`out.tell`），所以在斷氣、經驗後面、只有一個 prompt。
  - 分頁在 `pager.py`：`command()` 先給 `pager.key()`（分頁中的按鍵），再用 `pager.collect()` 把送給這個玩家的字收在 `ch.capture`（`Player.send()` 看它），
    跑完 `pager.show()` 決定整段送還是送一頁、補 prompt（分頁中 `Player.prompt()` 是分頁提示）。指令本身在 `run()`。
    坑：`collect()` 出錯時也要把收起來的字送出去（`finally`）；quit 回傳 False 時 `command()` 自己把字送出去、不補 prompt；
    重複登入接手時 `login.enter()` 清掉舊連線的 `pages`（新連線沒看過前面那幾頁）。
  - 坑：玩家打的數字用 `isdecimal()` 檢查再 `int()`，不要用 `isdigit()`：Big5 打得出來的「①…⑨」「⑴…⑼」isdigit 認得、int 不認得，
    會丟錯讓玩家斷線（`handle()` 只接 OSError）。全部的地方都換過了，有測試（`tests/test_digits.py`）。
- `send()` 只寫進 buffer，`drain()` 在 `handle()` 每處理完一批 read 才做一次。

## 必須守住的規則

- Avoid unnecessary secondary labels and descriptions. Let the layout do the explaining.
- **收進來的一律當 bytes，收滿一行才 decode**。不要在 `Telnet` 裡提早 decode，也不要改成用文字模式讀。
  用 byte 切行之所以安全，是因為 Big5 第二碼不會是 `\r` `\n` `\0`。
- Big5 一個中文字 2 bytes（第一碼 ≥ `0x81`）。任何截斷、退格都要以「整個字」為單位（參考 `_backspace()`）。
- 送給別人的訊息用 `act()`，不要自己 `send()`：`act()` 會包成 `"\n...\n\n" + 對方的 prompt()`（先換行避免接在對方 prompt 後面，
  說完空一行再補回對方的 prompt）；送給自己只加換行，prompt 由 `command()` 補。
  一個指令對同一個別人送好幾次 `act()` 沒關係：`command()` 用 `act.gathering()` 把送給別人的收成一段，指令跑完每人送一次、一個 prompt（使用者要的）。
- 協商：一連上就送 `START`（`IAC DO BINARY`）請客戶端用 8-bit 傳。坑：沒談好 BINARY，macOS 的 telnet 會把每個 byte 的
  第 8 bit 拿掉，中文全壞（加 `-8` 也一樣）。對方回 `WILL BINARY` 是答應，不再回覆。
  其他一律拒絕：對方 WILL 回 DONT、DO 回 WONT，同一組 (verb, option) 只回一次；對方 WONT/DONT 不回，避免兩邊無限互回。
- 玩家打的字（訊息內容、名字）一律用 `$t`、`$n` 這些代換碼帶進 `act()`，不要用 f-string 拼進 fmt：
  拼進去的字會被當成顏色代碼，玩家就能自己上色。
- 系統訊息用 `logging.getLogger(__name__)` 記錄，不要用 `print()`。
- 程式碼註解用繁體中文；telnet／編碼的陷阱用 `坑：` 開頭標記，新增同類處理時沿用這個寫法。
