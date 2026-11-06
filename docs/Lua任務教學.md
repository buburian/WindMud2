# Lua 任務教學

這份教區域作者用 Lua 腳本做任務：NPC 交代任務、記住玩家做到哪裡、收東西、數打倒幾隻怪、最後給獎勵。
它是從[區域製作手冊「腳本」](區域製作手冊.md#腳本)拆出來的教學，只講做任務用得到的東西。
全部的觸發時機、函式、上限和開機檢查，以手冊為準。

先講清楚兩件事：

- 遊戲裡沒有「任務系統」：沒有任務指令，也沒有任務清單。任務就是 NPC 的腳本，加上記在玩家身上的變數。
- 現在的獎勵只能給物品。給經驗、給金幣還不能做（手冊寫的「先不給」）。

下面的遊戲畫面都是實際跑出來的。`>` 開頭的那行是玩家打的指令；每段最後的 prompt（`<HP 64/64 MP 28/28 MV 35/35>` 那行）省略了。
生物、物品的 `keywords` 只寫英文，所以玩家指定牠們都打英文（`give bun elder`、`kill wolf`），畫面上顯示的是中文的 `short`（「村長」「包子」）。
例子的區域檔都叫 `village.json`，`area_number` 是 300（所以檔案裡的生物 1，在遊戲裡是 301）。

## 目錄

1. [腳本放哪](#腳本放哪)
2. [第一個任務](#第一個任務)
3. [記進度](#記進度)
4. [收集任務](#收集任務)
5. [打怪任務](#打怪任務)
6. [給獎勵](#給獎勵)
7. [只能做一次，還是可以重複](#只能做一次還是可以重複)
8. [好幾個 NPC 一起](#好幾個-npc-一起)
9. [房間幫忙：提示、門、擋路、傳送](#房間幫忙提示門擋路傳送)
10. [跨區域的任務](#跨區域的任務)
11. [常見錯誤](#常見錯誤)
12. [完整範例：村長的包子](#完整範例村長的包子)

## 腳本放哪

**腳本**是寫給生物或房間的一小段程式。有事情發生時（有人說話、有人走進來、牠被打死……），遊戲就去跑腳本裡對應的那一段。
這種「有事發生就跑」叫做**觸發**。

腳本是獨立的 `.lua` 檔，放在跟區域檔同名的資料夾裡：`village.json` 的腳本放在 `village/`。

```
areas/
  village.json
  village/
    村長.lua
    麵包師傅.lua
```

區域檔裡，生物（或房間）的 `script` 只寫用哪個檔：

```json
"script": {"file": "村長.lua", "timer": null}
```

- `timer` 是定時做事用的（`on_timer`），做任務用不到，寫 `null`。
- 沒有腳本的生物、房間寫 `"script": null`。
- 好幾隻生物可以用同一個檔（例如三隻野狼都用 `野狼.lua`）。
- 檔案用 UTF-8 存。開機時每個腳本都會先檢查一次，語法錯、函式名字打錯就不開機，細節見手冊的[寫在哪](區域製作手冊.md#寫在哪)。
- 用區域編輯器的話，腳本放在 `builder_area/區域檔名/`。

腳本裡的基本寫法：

- 腳本由一個一個**函式**組成：`function on_say(actor, text)` 到對應的 `end` 是一個函式。
  `on_say` 這個名字決定它什麼時候跑（有人說話的時候）。每個名字什麼時候跑，見手冊的[觸發時機和參數](區域製作手冊.md#觸發時機和參數)。
- 括號裡是遊戲交給你的資料（叫**參數**）：`actor` 是說話的人，`text` 是他說的話。
- `me` 是腳本的主人（這隻生物自己），`room` 是牠所在的房間。
- `--` 後面到行尾是**註解**，給人看的，遊戲不管。

## 第一個任務

最簡單的任務：玩家對村長說「任務」，村長交代一件事，並且記住「他接了」。

```lua
-- 村長.lua：玩家說「任務」，村長交代任務，並在玩家身上記下「接了」
function on_say(actor, text)
  if text == "任務" then
    actor.vars.bun = 1
    me:command("say " .. actor.name .. "，幫我去東邊的麵包店，問問師傅我訂的包子好了沒。")
  end
end
```

- `on_say`：玩家在這間房裡 `say` 的時候跑。只有玩家說的才算，生物說的不算。
- `text == "任務"`：整句要剛好是「任務」。玩家打 `say 任務`，`text` 就是 `"任務"`。
- `actor.vars.bun = 1`：在玩家身上記一個叫 `bun` 的**變數**（記東西的格子），值是 1。它會存進玩家的存檔，下線再上來還在。
- `me:command("say ...")`：村長照一般的指令說話。`..` 是把字接起來，`actor.name` 是玩家的名字。

```
> say 你好
你說：『你好』

> say 任務
你說：『任務』

村長說：『Ming，幫我去東邊的麵包店，問問師傅我訂的包子好了沒。』
```

村長只聽「任務」，所以「你好」他不理。

玩家的存檔（`players/ming.json`）裡，`vars` 那一段會變成 `{"village": {"bun": 1}}`。
`village` 是區域檔的名字：每個區域檔的變數分開放，別的區域也有 `bun` 也不會混在一起。

## 記進度

任務通常有好幾步。用**一個變數記「做到第幾步」**最好懂：

| `actor.vars.bun` | 意思 |
|---|---|
| `nil`（沒有值） | 還沒接 |
| `1` | 接了，要去問麵包師傅 |
| `2` | 師傅回話了 |
| `"完成"` | 做完了 |

每一步都一樣：先看他現在在第幾步，對了才做事，再前進一步。

```lua
-- 村長.lua：傳話任務。actor.vars.bun 記做到哪一步：
--   nil：還沒接　1：要去問麵包師傅　2：師傅回話了　"完成"：做完了
function on_say(actor, text)
  if text ~= "任務" then
    return                                -- 不是說「任務」就不理
  end
  local step = actor.vars.bun             -- 先把進度拿出來
  if step == nil then                     -- 還沒接：交代任務，前進到第 1 步
    actor.vars.bun = 1
    me:command("say 幫我去東邊的麵包店，問問師傅我訂的包子好了沒。")
  elseif step == 1 then                   -- 接了，還沒去問：提醒他
    me:command("say 還沒去嗎？麵包店就在東邊。")
  elseif step == 2 then                   -- 師傅回話了：任務完成
    actor.vars.bun = "完成"
    me:command("say 明天才好啊？辛苦你跑一趟了。")
  else                                    -- 做完了
    me:command("say 謝謝你上次幫忙。")
  end
end
```

```lua
-- 麵包師傅.lua：在第 1 步的人說「包子」，師傅回話，前進到第 2 步
function on_say(actor, text)
  if text == "包子" and actor.vars.bun == 1 then
    actor.vars.bun = 2
    me:command("say 村長的包子啊？跟他說明天才好。")
  end
end
```

- 兩個 NPC 寫在同一個區域檔，看的是玩家身上**同一個** `bun`：村長設成 1，師傅看到 1 才回話、設成 2，村長再看到 2 就算完成。
- `if … elseif … else … end`：從上往下找第一個對的，只做那一段。
- `local step = actor.vars.bun`：先把進度放在 `step`。`local` 是這一次用的暫時變數，跑完就忘。
- `~=` 是「不等於」。`return` 是到此為止，後面都不做。

```
> say 任務
你說：『任務』

村長說：『幫我去東邊的麵包店，問問師傅我訂的包子好了沒。』

> say 任務
你說：『任務』

村長說：『還沒去嗎？麵包店就在東邊。』

> e
【麵包店】
【出口： 西】

麵包師傅站在這裡。

> say 包子
你說：『包子』

麵包師傅說：『村長的包子啊？跟他說明天才好。』

> w
【村子廣場】
【出口： 東】

村長站在這裡。

> say 任務
你說：『任務』

村長說：『明天才好啊？辛苦你跑一趟了。』

> say 任務
你說：『任務』

村長說：『謝謝你上次幫忙。』
```

### 變數的規則

| 寫法 | 記在哪 | 什麼時候清掉 |
|---|---|---|
| `actor.vars.名字` | 玩家身上，這個區域檔的 | 不會清：跟著玩家存檔，下線也在 |
| `me.vars.名字` | 這隻生物身上 | 牠死掉時 |
| `room.vars.名字` | 這間房間上 | 區域重置時 |
| `local 名字 = …` | 這一次 | 跑完就忘 |

- **任務進度要記在 `actor.vars`**（玩家身上）。記在 `me.vars` 的話，NPC 一死就不見了。
- 值只能是 `nil`、`true`／`false`、數字、字串。不能存表格（`{…}`），存了算腳本出錯。
- 存 `nil` 就是把變數拿掉。
- 名字可以用中文，要寫成 `actor.vars["包子"]`。
- 玩家的變數是**分區域檔**的：同一個區域檔裡的 NPC、房間看到同一份；別的區域檔看不到，要用 `read_var`（見[跨區域的任務](#跨區域的任務)）。
- 觸發的人是生物時，`actor.vars` 是那隻生物自己的變數（牠死掉就沒了），所以要先檢查是不是玩家（見[常見錯誤](#常見錯誤)）。

更多細節見手冊的[變數](區域製作手冊.md#變數)。

## 收集任務

### 叫他自己交出來

`actor:take_item(號碼)` 從他的背包拿走一件：拿到了是 `true`，背包裡沒有是 `false`。所以「檢查有沒有」和「拿走」可以一起做：

```lua
-- 村長.lua：在第 1 步的人說「交貨」，背包裡有包子（物品 1）就收下
function on_say(actor, text)
  if text == "交貨" and actor.vars.bun == 1 then
    if actor:take_item(1) then            -- 拿走一個包子：拿到了是 true，背包裡沒有是 false
      actor.vars.bun = "完成"
      me:command("say 就是這個味道！謝謝你。")
    else
      me:command("say 你身上沒有包子啊。")
    end
  end
end
```

```
> say 交貨
你說：『交貨』

村長說：『你身上沒有包子啊。』

> i
你目前所攜帶的東西有：
     包子/bun
（1/35 件，負重 1/140）

> say 交貨
你說：『交貨』

村長說：『就是這個味道！謝謝你。』
```

- 號碼照[號碼規則](區域製作手冊.md#號碼規則)：腳本裡 1～99 是**這個區域檔**的（這裡的 1 是這個檔的物品 1），100 以上是完整號碼（別的區域的物品）。
- 只看背包裡的，穿在身上的拿不走。要看身上有沒有穿著，用 `actor:wears_item(號碼)`。
- 只想看有沒有、不拿走，用 `actor:has_item(號碼)`。
- 一次拿一件。要收好幾件，用下面 give 的寫法一件一件數比較簡單。

### 用 give 交給 NPC

玩家打 `give pelt tanner`（把狼皮給皮匠），皮匠的 `on_give(actor, item, gold)` 就會跑：

- `item`：給的物品號碼（照號碼規則，自己區域的是 1～99）。給金幣時是 `nil`。
- `gold`：給的金幣數量。給東西時是 `0`。
- 東西已經在 NPC 身上了才跑。

```lua
-- 皮匠.lua：收三張狼皮（物品 3）。actor.vars.pelt：nil 還沒接、1 在收、"完成" 收齊了
function on_say(actor, text)
  if text == "任務" and actor.vars.pelt == nil then
    actor.vars.pelt = 1
    me:command("say 幫我收三張狼皮來，一張一張 give 給我就好。")
  end
end

-- 有人 give 東西給皮匠
function on_give(actor, item, gold)
  if item ~= 3 or actor.vars.pelt ~= 1 then
    return                                -- 不是狼皮，或沒在做這個任務：不理
  end
  me:take_item(3)                         -- 收到的狼皮從皮匠身上拿掉，不然會一直堆在他身上
  local n = (actor.vars.pelts or 0) + 1   -- 收過幾張（第一次是 nil，當作 0）
  actor.vars.pelts = n
  if n < 3 then
    me:command("say 還差 " .. (3 - n) .. " 張。")
  else
    actor.vars.pelt = "完成"
    me:command("say 三張都齊了，做得好！")
  end
end
```

```
> say 任務
你說：『任務』

皮匠說：『幫我收三張狼皮來，一張一張 give 給我就好。』

> give pelt tanner
你把【狼皮/pelt】拿給皮匠。

皮匠說：『還差 2 張。』

> give bun tanner
你把【包子/bun】拿給皮匠。

> give pelt tanner
你把【狼皮/pelt】拿給皮匠。

皮匠說：『還差 1 張。』

> give pelt tanner
你把【狼皮/pelt】拿給皮匠。

皮匠說：『三張都齊了，做得好！』
```

要注意：

- 給錯的東西（上面的包子）、還沒接任務就給的狼皮，都留在皮匠身上，不會退回去。皮匠死掉時，這些東西會掉進屍體。
- `me:take_item(3)` 是把皮匠身上的一張狼皮拿掉。不拿掉的話，收到的東西會一直堆在他身上。
- 區域檔有寫 `shop`（商店）的生物不收東西：玩家看到「村長拒絕拿【包子/bun】。」，`on_give` 也不會跑。任務 NPC 的 `shop` 寫 `null`。

## 打怪任務

怪物被打死時，會跑牠的 `on_death(killer)`。`killer` 是打死牠的人，就在這裡幫他記一隻。

```lua
-- 野狼.lua：被打死的時候，幫打死牠的玩家記一隻
function on_death(killer)
  if killer == nil or not killer:is_player() then
    return                                -- 沒有人打死牠（例如 imm 的 slay），或是被生物打死的
  end
  if killer.vars.wolf == 1 then           -- 正在做打狼任務才算
    local n = (killer.vars.wolves or 0) + 1
    killer.vars.wolves = n
    killer:tell("你已經打倒了 " .. n .. " 隻野狼。")
  end
end
```

```lua
-- 獵人.lua：打狼任務。actor.vars.wolf：nil 還沒接、1 在打、"完成" 做完了
--                      actor.vars.wolves：打倒了幾隻（野狼的腳本幫忙數）
function on_say(actor, text)
  if text ~= "任務" then
    return
  end
  local step = actor.vars.wolf
  local n = actor.vars.wolves or 0        -- 還沒打過是 nil，當作 0
  if step == nil then
    actor.vars.wolf = 1
    me:command("say 北邊的野狼越來越多了，幫我打倒 3 隻。")
  elseif step == 1 and n < 3 then
    me:command("say 才 " .. n .. " 隻，還不夠。")
  elseif step == 1 then
    actor.vars.wolf = "完成"
    me:command("say 謝啦，這下村子安全多了。")
  end
end
```

- `killer` 可能是 `nil`：沒有人打死牠（例如 imm 用 `slay`）。直接寫 `killer.vars` 會出錯，所以先檢查。
- `killer` 也可能是生物，所以要用 `killer:is_player()` 檢查。
- 算的是**打出最後一下**的人。
- `on_death` 沒有 `actor`，打死牠的人就是 `killer`。
- `actor.vars.wolves or 0`：變數還沒有值時是 `nil`，`nil` 不能拿來加減、比大小。`or 0` 的意思是「沒有就當 0」。
- 野狼和獵人要寫在**同一個區域檔**，看的才是同一個 `wolves`。不同區域檔見[跨區域的任務](#跨區域的任務)。

打倒野狼時，腳本說的話接在「斷氣」「經驗」後面，跟這一回合的訊息是同一段：

```
> kill wolf
你使用直拳攻擊野狼，對它造成輕微的擦傷.(2)
野狼已經斷氣，倒在地上死亡了!!
你共獲得了【15】點的經驗點數。
你已經打倒了 1 隻野狼。
野狼的屍體裝著：
     空無一物。
```

傷害、經驗的數字每次不一樣。`on_death` 裡用 `tell`、`room:echo`、`me:command("say ...")` 說的話都一樣，接在同一段裡。

打了兩隻就回去，和打夠三隻再回去：

```
> say 任務
你說：『任務』

獵人說：『才 2 隻，還不夠。』

> say 任務
你說：『任務』

獵人說：『謝啦，這下村子安全多了。』
```

## 給獎勵

```lua
actor:give_item(號碼, 等級, 顏色)
```

- **等級一定要寫**（1 以上的整數），常用 `actor.level`（跟他一樣等級）。沒寫算腳本出錯，東西不會給。
- 顏色是裝備的品質：`"gray"`、`"white"`、`"blue"`、`"purple"`、`"orange"`，寫別的算腳本出錯。
  不寫就沒有隨機屬性；不是裝備的東西（包子）不用寫。下面的例子寫藍色，長劍抽到隨機屬性，名字前面也多了隨機的詞（例如「鐵壁之活力長劍」）。
- 區域檔寫了 `affects` 的固定裝備，給的時候會檢查點數上限，超過算腳本出錯。沒寫顏色時上限是 0，所以固定裝備要寫顏色。
- 生物的腳本給別人東西，訊息跟玩家用 `give` 一樣：收到的人看到「獵人把【包子/bun】拿給你。」，同一間房的其他人看到「獵人將【包子/bun】拿給Ming。」。
  訊息就出現在 `give_item` 那一行跑的時候，所以在後面那句 `say` 的前面。
- 房間的腳本沒有「誰給的」，給了也不說話，要自己 `actor:tell` 一句。
- 不看背包的件數、負重，一定放得進去（跟 imm 的 `oload` 一樣）。
- **現在不能給經驗、金幣**，也不能補血、扣血（手冊寫的「先不給」）。

打狼任務做完時，給一把長劍和一個包子：

```lua
-- 獵人.lua：打狼任務做完，給獎勵
function on_say(actor, text)
  if text ~= "任務" then
    return
  end
  local step = actor.vars.wolf
  local n = actor.vars.wolves or 0
  if step == nil then
    actor.vars.wolf = 1
    me:command("say 北邊的野狼越來越多了，幫我打倒 3 隻。")
  elseif step == 1 and n < 3 then
    me:command("say 才 " .. n .. " 隻，還不夠。")
  elseif step == 1 then
    actor.vars.wolf = "完成"
    actor:give_item(2, actor.level, "blue")   -- 物品 2（長劍），等級跟他一樣，藍色
    actor:give_item(1, 1)                     -- 物品 1（包子），等級 1，沒有顏色
    me:command("say 謝啦，這把長劍和包子送你。")
  end
end
```

```
> say 任務
你說：『任務』

獵人把【鐵壁之活力長劍/sword】拿給你。
獵人把【包子/bun】拿給你。
獵人說：『謝啦，這把長劍和包子送你。』

> i
你目前所攜帶的東西有：
     包子/bun
     鐵壁之活力長劍/sword
（2/35 件，負重 6/140）
```

長劍的名字每次不一樣：屬性是隨機抽的。

忘了寫等級的話（獵人.lua）：

```lua
-- 不好的寫法：沒寫等級
function on_say(actor, text)
  if text == "任務" then
    actor:give_item(2)                    -- 等級沒寫：算腳本出錯，東西不會給
  end
end
```

線上的 imm 會看到：

```
[腳本出錯] village.json 生物 301 獵人：village/獵人.lua:4: 等級一定要寫，要是 1 以上的整數，不能是 nil
```

## 只能做一次，還是可以重複

**只能做一次**：最後一步設成 `"完成"`，之後就不再前進。前面的例子都是這樣：`"完成"` 存在玩家身上，一直都在。

**可以重複**：做完把進度清回 `nil`，下次又從頭開始。要記做過幾次，另外用一個變數數。

```lua
-- 村長.lua：可以重複的包子任務。做完把進度清回 nil，下次說「任務」又從頭開始
function on_say(actor, text)
  if text == "任務" and actor.vars.bun == nil then
    actor.vars.bun = 1
    me:command("say 再幫我買一個包子吧。")
  elseif text == "交貨" and actor.vars.bun == 1 then
    if actor:take_item(1) then
      actor.vars.bun = nil                                    -- 清掉：可以再接一次
      actor.vars.bun_times = (actor.vars.bun_times or 0) + 1  -- 記做過幾次
      me:command("say 謝啦，這是你第 " .. actor.vars.bun_times .. " 次幫我買包子了。")
    end
  end
end
```

```
> say 任務
你說：『任務』

村長說：『再幫我買一個包子吧。』

> say 交貨
你說：『交貨』

村長說：『謝啦，這是你第 1 次幫我買包子了。』

> say 任務
你說：『任務』

村長說：『再幫我買一個包子吧。』

> say 交貨
你說：『交貨』

村長說：『謝啦，這是你第 2 次幫我買包子了。』
```

**每次區域重置只送一個（大家搶）**：記在 `room.vars`，區域重置時才清掉。這是所有玩家共用的，不是每個人一份。

```lua
-- 老人.lua：每次區域重置，只送第一個來問的人一個包子（記在房間上，大家共用）
function on_say(actor, text)
  if text == "包子" then
    if room.vars.given then
      me:command("say 今天的包子已經送完了。")
    else
      room.vars.given = true              -- 記在房間：區域重置時才清掉
      actor:give_item(1, 1)
      me:command("say 拿去吧，趁熱吃。")
    end
  end
end
```

Ming 先問：

```
> say 包子
你說：『包子』

老人把【包子/bun】拿給你。
老人說：『拿去吧，趁熱吃。』
```

同一間房的 Hua 看到：

```
Ming說：『包子』

老人將【包子/bun】拿給Ming。

老人說：『拿去吧，趁熱吃。』
```

Hua 再問，要等到區域重置以後才拿得到：

```
> say 包子
你說：『包子』

老人說：『今天的包子已經送完了。』
```

- 副本每一份的房間是分開的，`room.vars` 也各自一份。
- 腳本拿不到日期和真實時間（只有 `hour()` 是遊戲裡現在幾點），所以做不出「每天一次」。

## 好幾個 NPC 一起

### 用玩家身上的進度串起來

[記進度](#記進度)的例子就是兩個 NPC 串成一個任務：村長和師傅都看玩家身上的 `bun`。
同一個區域檔的 NPC 看到同一份變數，所以**一個 NPC 讓進度前進一步，另一個 NPC 就看得到**。要串更多 NPC，就多幾步。

### NPC 之間說話

有時候想讓 NPC 互相對話。要注意三件事：

1. **生物 `say` 的話不會觸發別人的 `on_say`**，只有玩家說的才算。NPC 之間要用 `tell` 加對方的英文名字（keywords）叫對方，對方的 `on_tell(actor, text)` 會跑。生物 `tell` 生物，玩家看不到。
2. **一串觸發裡，每個 NPC 只跑一次**。「一串」是玩家的一個指令引起的全部腳本。
   師傅 `tell` 學徒、學徒馬上 `tell` 回師傅：師傅這一串已經跑過了，聽不到。學徒先 `wait` 一下再回就可以，`wait` 完是新的一串。
3. **`on_tell` 的 `actor` 是叫他的 NPC，不是玩家**。所以給玩家東西、改玩家的變數，都要由玩家觸發的那個 NPC 來做。

```lua
-- 麵包師傅.lua：在第 1 步的人說「包子」，給他包子，再叫學徒去補貨
function on_say(actor, text)
  if text == "包子" and actor.vars.bun == 1 then
    actor.vars.bun = 2
    actor:give_item(1, 1)                 -- 包子由師傅自己給：只有他的 actor 是玩家
    me:command("say 村長的包子好了，拿去吧。")
    me:command("tell apprentice 補貨")    -- 用 tell 叫學徒（生物 say 的話不會觸發 on_say）
  end
end

-- 學徒回話了
function on_tell(actor, text)
  if text == "好了" then
    me:command("say 動作真快。")
  end
end
```

```lua
-- 學徒.lua：師傅叫他補貨，等 2 秒再回話
function on_tell(actor, text)
  if text == "補貨" then
    wait(2)                               -- 先等一下：等完是新的一串，師傅才聽得到他回話
    me:command("say 包子蒸好了！")
    me:command("tell baker 好了")
  end
end
```

```
> say 包子
你說：『包子』

麵包師傅把【包子/bun】拿給你。
麵包師傅說：『村長的包子好了，拿去吧。』
```

2 秒後：

```
學徒說：『包子蒸好了！』

麵包師傅說：『動作真快。』
```

學徒沒有 `wait`、馬上回話的話：

```lua
-- 學徒.lua（不好的寫法）：沒有 wait，馬上回話
function on_tell(actor, text)
  if text == "補貨" then
    me:command("say 包子蒸好了！")
    me:command("tell baker 好了")          -- 師傅這一串已經跑過了，聽不到
  end
end
```

```
> say 包子
你說：『包子』

麵包師傅把【包子/bun】拿給你。
麵包師傅說：『村長的包子好了，拿去吧。』
學徒說：『包子蒸好了！』
```

師傅的「動作真快。」不會出現。

- 生物下 `tell` 時，**先找同一間房的**，找不到才找線上的玩家。所以線上剛好有個叫 Apprentice 的玩家，`tell apprentice` 照樣叫到同一間房的學徒，不會跑去那個玩家那裡。
  （玩家下 `tell` 是反過來：先找線上的玩家，找不到才找同一間房的生物。）
- `wait(秒數)` 等的時候遊戲照跑，一次最多 600 秒。等完時，主人（腳本的 NPC）或觸發的人（`actor`）不在同一個房間了，腳本就默默停掉（見[常見錯誤](#常見錯誤)、手冊的[wait](區域製作手冊.md#wait)）。

## 房間幫忙：提示、門、擋路、傳送

### 走進來給提示

`on_enter(actor, from)` 在有人走進房間以後跑。房間和生物都可以寫；房間的腳本寫在區域檔那間房間的 `script`。

```lua
-- 森林小徑.lua（房間的腳本）：在打狼任務中的人走進來，給他一句提示
function on_enter(actor, from)
  if actor:is_player() and actor.vars.wolf == 1 then
    actor:tell("{Y樹林深處傳來狼嚎，野狼就在附近。{x")
  end
end
```

```
> n
【森林小徑】
【出口： 北 南】

樹林深處傳來狼嚎，野狼就在附近。
```

- 先看到房間，才看到提示。
- `actor:tell(文字)` 只給他一個人看。文字可以用[顏色代碼](區域製作手冊.md#顏色代碼)（`{Y` 亮黃、`{x` 回到原本的顏色）。
- 生物走進來也會跑，所以要 `actor:is_player()`。
- `from` 是從哪個方向進來（`"south"`……）；被 `transfer` 送進來是 `nil`。

### 用門當關卡

`room:door(方向, 動作)` 開、關、鎖、開鎖門，動作寫 `"open"`、`"close"`、`"lock"`、`"unlock"`。門的兩邊一起變，不用鑰匙，鎖著的門也可以直接 `"open"`。

```lua
-- 狼王.lua：狼王被打倒，北邊的鐵門打開（門是大家共用的，誰經過都能走）
function on_death(killer)
  room:door("north", "open")              -- 鎖著也直接打開，兩邊一起變
  room:echo("北邊的鐵門喀啦一聲打開了。")
end
```

打倒狼王之前，門是關著的：

```
> look n
那裡沒有什麼特別的東西。
鐵門是關著的。
```

打倒狼王時，這間房裡的人看到腳本 `room:echo` 的那句：

```
北邊的鐵門喀啦一聲打開了。
```

門對面那間房（河邊）醒著的人，跟玩家自己開門時一樣看到：

```
南方的鐵門被打開了。
```

- 那個方向要有門（區域檔出口的 `locks` 不是 0），沒有門算腳本出錯。
- 腳本開門、關門時，這間房的人不會收到任何訊息，要自己 `room:echo`（整個房間醒著的人看得到）。
- 門對面那間房醒著的人會看到「被打開了」「被關起來了」。鎖、開鎖對面不知道（跟玩家一樣）。
- **門是大家共用的**：打開以後，誰經過都能走。區域檔有這扇門的重置 `D` 的話，區域重置時門又會照 `D` 關回去。
- 要「每個人分開算」的關卡，用下面的擋路。

### 擋路（每個人分開算）

`on_command(actor, cmd, arg)` 在有人打指令、遊戲處理之前跑。`return true` 就擋住，這個指令不做。

```lua
-- 守衛.lua：打狼任務做完的人才能往西走（每個人分開算）
function on_command(actor, cmd, arg)
  if cmd == "west" and actor:is_player() and actor.vars.wolf ~= "完成" then
    actor:tell("守衛擋住了你：「先幫獵人把狼打完再說。」")
    return true                           -- 擋住：這個指令就不做了
  end
end
```

還沒做完：

```
> w
守衛擋住了你：「先幫獵人把狼打完再說。」
```

做完以後：

```
> w
【獵場】
【出口： 東】
```

- `cmd` 是指令的全名：玩家打 `w` 也是 `"west"`。
- 看的是**這個人**身上的進度，所以每個人分開算。

### 送到別的地方

`actor:transfer(房號)` 把他送到那間房。不能送進副本。送的是玩家就馬上存檔。

```lua
-- 船夫.lua：打狼任務做完的人說「渡河」，送他到對岸（房間 5）
function on_say(actor, text)
  if text == "渡河" and actor.vars.wolf == "完成" then
    me:command("say 坐穩了。")
    actor:transfer(5)                     -- 送過去，會馬上存檔；送完他就不在這裡了，所以放最後
  end
end
```

```
> say 渡河
你說：『渡河』

船夫說：『坐穩了。』

【對岸】
【出口： 沒有】
```

- 送完他就不在這個房間了：後面再 `me:command("say ...")` 他聽不到，再 `wait` 也會停掉。所以 `transfer` 放最後。
- 那邊房間的 `on_enter` 會跑，`from` 是 `nil`。

## 跨區域的任務

玩家的變數是分區域檔的：`forest.json` 的腳本寫 `actor.vars.bun`，是 forest 自己的 `bun`，跟 `village.json` 的 `bun` 是兩個。
要看別的區域檔的變數，用：

```lua
actor:read_var("區域檔名", "名字")
```

- 區域檔名不含 `.json`。
- **只能看、不能改**。
- 觸發的人是生物時，拿到的是 `nil`。

```lua
-- forest/獵人.lua：村子（village.json）的包子任務做完的人，獵人才肯給他任務
function on_say(actor, text)
  if text ~= "任務" then
    return
  end
  if actor:read_var("village", "bun") ~= "完成" then   -- 看 village.json 的變數 bun
    me:command("say 我不認識你。先去幫村長的忙吧。")
    return
  end
  if actor.vars.wolf == nil then          -- 這是 forest.json 自己的變數
    actor.vars.wolf = 1
    me:command("say 村長介紹來的？好，北邊的野狼交給你了。")
  end
end
```

村子的包子任務還沒做完：

```
> say 任務
你說：『任務』

獵人說：『我不認識你。先去幫村長的忙吧。』
```

做完以後：

```
> say 任務
你說：『任務』

獵人說：『村長介紹來的？好，北邊的野狼交給你了。』
```

這時玩家存檔的 `vars` 是 `{"forest": {"wolf": 1}, "village": {"bun": "完成"}}`：兩個區域分開放。

- 生物的腳本算牠自己那個區域檔的。重置的 `M` 可以放別的檔的生物：`forest.json` 的野狼被放進 `village.json` 的房間，牠的腳本記的還是 forest 的變數。

## 常見錯誤

### 忘了檢查是不是玩家

`on_enter`、`on_tell`、`on_death` 的人都可能是生物，生物走進房間也會觸發 `on_enter`。沒檢查的話：

- `actor.vars` 是那隻生物自己的變數，任務的判斷會亂掉。
- 生物的 `guild`、`race` 是 `nil`，拿來接字串會出錯。

房間 2 的腳本 `歡迎.lua`：

```lua
-- 不好的寫法：沒檢查 is_player()，生物走進來也會跑
function on_enter(actor, from)
  actor:tell("你的公會是 " .. actor.guild .. "。")   -- 生物的 guild 是 nil，接字串會出錯
end
```

野狗走進房間 2（遊戲號碼 302）時，線上的 imm 看到：

```
[腳本出錯] village.json 房間 302：village/歡迎.lua:3: attempt to concatenate a nil value (field 'guild')
```

`on_death` 的 `killer` 是 `nil` 時也一樣（野狼.lua，imm 用 `slay` 殺了牠）：

```lua
-- 不好的寫法：沒檢查 killer 是不是 nil
function on_death(killer)
  killer.vars.wolves = (killer.vars.wolves or 0) + 1   -- slay 的時候 killer 是 nil，這行出錯
end
```

```
[腳本出錯] village.json 生物 301 野狼：village/野狼.lua:3: attempt to index a nil value (local 'killer')
```

### 以為 NPC 說的話會觸發 on_say

生物 `say` 的話不會觸發任何 `on_say`。NPC 之間用 `tell`，見[好幾個 NPC 一起](#好幾個-npc-一起)。

### wait 之後玩家走掉了

`wait` 等完時，觸發的人離線、死掉、或不在同一個房間，腳本就**默默停掉**：後面的都不做，也不算出錯。

```lua
-- 不好的寫法：先記成完成，等 3 秒才給獎勵
function on_say(actor, text)
  if text == "任務" and actor.vars.wolf == 1 then
    actor.vars.wolf = "完成"
    me:command("say 等等，我去拿獎勵。")
    wait(3)
    actor:give_item(2, actor.level, "blue")   -- 他 3 秒內走掉，這行就不會跑：任務完成了，獎勵卻沒拿到
    me:command("say 這把長劍送你。")
  end
end
```

玩家說完「任務」馬上走開，就會變成：任務記成完成了，長劍卻沒拿到。
重要的事（記進度、給東西）放在 `wait` 前面，`wait` 後面只放不重要的話：

```lua
-- 好的寫法：先給獎勵、記完成，wait 之後只放不重要的話
function on_say(actor, text)
  if text == "任務" and actor.vars.wolf == 1 then
    actor.vars.wolf = "完成"
    actor:give_item(2, actor.level, "blue")
    me:command("say 這把長劍送你。")
    wait(3)
    me:command("say 有空再來玩啊。")      -- 他走掉了也沒關係
  end
end
```

### 變數存表格

獵人.lua：

```lua
-- 不好的寫法：變數存表格
function on_say(actor, text)
  actor.vars.killed = {"野狼", "狼王"}    -- 變數只能存 nil、true／false、數字、字串，這行出錯
end
```

```
[腳本出錯] village.json 生物 301 獵人：village/獵人.lua:3: 變數只能存 nil、true／false、數字、字串
```

要記好幾樣東西，就用好幾個變數（例如 `actor.vars.wolves`、`actor.vars.kings`）。

### 只能整句比對

`text == "任務"` 要整句一樣：玩家說「請問有什麼任務嗎」不算。腳本裡沒有 `find`、`match` 這些找字的方法。
真的要看句子裡有沒有某個詞，可以自己寫一個小函式：

```lua
-- 句子裡有沒有某個詞（沙箱沒有 find，自己一段一段比）
function contains(text, word)
  for i = 1, #text - #word + 1 do
    if text:sub(i, i + #word - 1) == word then
      return true
    end
  end
  return false
end

function on_say(actor, text)
  if contains(text, "任務") then
    me:command("say 你想接任務嗎？說「任務」就好。")
  end
end
```

```
> say 請問有什麼任務嗎
你說：『請問有什麼任務嗎』

村長說：『你想接任務嗎？說「任務」就好。』
```

### 出錯了怎麼看

- 出錯只停掉**這一次**，下次觸發照樣跑。
- 玩家看不到任何東西。
- 伺服器記一筆 log，線上的 imm 看到一行 `[腳本出錯]`：哪個區域檔、哪間房間或哪隻生物（遊戲號碼）、腳本檔和第幾行、錯在哪。
- 同一個錯一分鐘只提醒一次。
- 腳本有語法錯、`on_` 函式的名字打錯（例如 `on_sya`），伺服器不會開機，並說錯在哪。
  區域編輯器也會檢查，或用 `uv run python -m mud.areacheck` 先檢查（見手冊的[檢查區域檔](區域製作手冊.md#檢查區域檔)）。

### 其他

- 生物、物品的 `keywords` 只寫英文。腳本裡叫生物、指定物品的指令也用英文名字（`tell apprentice`、`give bun ...`）。
- 號碼：腳本裡 1～99 是自己這個區域檔的，100 以上是完整號碼。`on_give` 拿到的 `item` 也是這個寫法。
- 寫在函式外面的程式，每次觸發都會跑一次。最外層只寫函式。
- 有寫 `shop` 的 NPC 不收 `give`，`on_give` 不會跑。

## 完整範例：村長的包子

把上面的東西串起來。三個 NPC、三個腳本：

1. 對村長說「任務」：要去麵包店。
2. 對麵包師傅說「包子」：拿到包子。
3. `give bun elder`（把包子給村長）：村長收下包子，再請你去北邊打 3 隻野狼。
4. 打倒 3 隻野狼，回去對村長說「任務」：拿到一把藍色長劍。只能做一次。

檔案：

```
areas/
  village.json
  village/
    村長.lua
    麵包師傅.lua
    野狼.lua
```

`village.json` 裡跟任務有關的部分（節錄，`…` 是省略的欄位，寫法照[區域製作手冊](區域製作手冊.md)）：

```json
"rooms": [
  {"vnum": 1, "name": "村子廣場", "exits": {"east": {"to_room": 2, …}, "north": {"to_room": 3, …}}, "script": null, …},
  {"vnum": 2, "name": "麵包店", "exits": {"west": {"to_room": 1, …}}, "script": null, …},
  {"vnum": 3, "name": "森林小徑", "exits": {"south": {"to_room": 1, …}}, "script": null, …}
],
"mobiles": [
  {"vnum": 1, "keywords": "elder", "short": "村長", "shop": null, "script": {"file": "村長.lua", "timer": null}, …},
  {"vnum": 2, "keywords": "baker", "short": "麵包師傅", "shop": null, "script": {"file": "麵包師傅.lua", "timer": null}, …},
  {"vnum": 3, "keywords": "wolf", "short": "野狼", "shop": null, "script": {"file": "野狼.lua", "timer": null}, …}
],
"objects": [
  {"vnum": 1, "keywords": "bun", "short": "包子", "item_type": 19, "wear_flags": "1", "affects": [], …},
  {"vnum": 2, "keywords": "sword", "short": "長劍", "item_type": 5, "wear_flags": "1|8192", "affects": [], …}
],
"resets": [
  {"cmd": "M", "rare": 0, "mob_vnum": 1, "limit": 1, "room_vnum": 1, "comment": "村長"},
  {"cmd": "M", "rare": 0, "mob_vnum": 2, "limit": 1, "room_vnum": 2, "comment": "麵包師傅"},
  {"cmd": "M", "rare": 0, "mob_vnum": 3, "limit": 3, "room_vnum": 3, "comment": "野狼"},
  {"cmd": "M", "rare": 0, "mob_vnum": 3, "limit": 3, "room_vnum": 3, "comment": "野狼"},
  {"cmd": "M", "rare": 0, "mob_vnum": 3, "limit": 3, "room_vnum": 3, "comment": "野狼"}
]
```

```lua
-- 村長.lua：「村長的包子」任務。actor.vars.bun 記做到哪一步：
--   nil：還沒接
--   1：要去麵包店拿包子
--   2：拿到包子了，要 give 給村長
--   3：要去北邊打 3 隻野狼（actor.vars.wolves 記打了幾隻，野狼.lua 幫忙數）
--   "完成"：做完了（只能做一次）

-- 有人走進廣場：照進度給提示
function on_enter(actor, from)
  if not actor:is_player() then
    return                                        -- 生物走進來不理
  end
  local step = actor.vars.bun
  if step == nil then
    me:command("say " .. actor.name .. "，我有件事想拜託你，說「任務」聽聽看吧。")
  elseif step == 3 and (actor.vars.wolves or 0) >= 3 then
    me:command("say 你回來啦！說「任務」跟我報告吧。")
  end
end

-- 說「任務」：接任務、問進度、領獎勵
function on_say(actor, text)
  if text ~= "任務" then
    return
  end
  local step = actor.vars.bun
  local wolves = actor.vars.wolves or 0
  if step == nil then
    actor.vars.bun = 1
    me:command("say 幫我去東邊的麵包店，跟師傅說「包子」，把我訂的包子拿回來。")
  elseif step == 1 then
    me:command("say 麵包店在東邊，跟師傅說「包子」就好。")
  elseif step == 2 then
    me:command("say 包子拿到了？打 give bun elder 給我吧。")
  elseif step == 3 and wolves < 3 then
    me:command("say 野狼才打倒 " .. wolves .. " 隻，還差一些。")
  elseif step == 3 then
    actor.vars.bun = "完成"
    actor.vars.wolves = nil                       -- 用不到了，清掉
    actor:give_item(2, actor.level, "blue")       -- 獎勵：物品 2（長劍），等級跟他一樣，藍色
    me:command("say 太好了！這把長劍送你，謝謝你幫了村子這麼多。")
  else
    me:command("say 謝謝你上次幫忙。")
  end
end

-- give 東西給村長：在第 2 步給的是包子（物品 1）才算
function on_give(actor, item, gold)
  if item == 1 and actor.vars.bun == 2 then
    me:take_item(1)                               -- 收到的包子從村長身上拿掉
    actor.vars.bun = 3
    actor.vars.wolves = 0
    me:command("say 就是這個味道！對了，北邊的森林最近野狼很多，幫我打倒 3 隻吧。")
  end
end
```

```lua
-- 麵包師傅.lua：在第 1 步的人說「包子」，給他包子，前進到第 2 步
function on_say(actor, text)
  if text == "包子" and actor.vars.bun == 1 then
    actor.vars.bun = 2
    actor:give_item(1, 1)                         -- 物品 1（包子），等級 1
    me:command("say 村長訂的包子，剛蒸好的，拿去吧。")
  end
end
```

```lua
-- 野狼.lua：在第 3 步的玩家打死牠，幫他記一隻
function on_death(killer)
  if killer == nil or not killer:is_player() then
    return                                        -- 沒有人打死牠，或是被生物打死的
  end
  if killer.vars.bun == 3 then
    local n = (killer.vars.wolves or 0) + 1
    killer.vars.wolves = n
    if n < 3 then
      killer:tell("你已經打倒了 " .. n .. " 隻野狼。")
    else
      killer:tell("野狼打夠了，回村子找村長吧。")
    end
  end
end
```

從頭玩一次（Ming 從麵包店出發）：

```
> w
【村子廣場】
【出口： 北 東】

村長站在這裡。

村長說：『Ming，我有件事想拜託你，說「任務」聽聽看吧。』

> say 任務
你說：『任務』

村長說：『幫我去東邊的麵包店，跟師傅說「包子」，把我訂的包子拿回來。』

> e
【麵包店】
【出口： 西】

麵包師傅站在這裡。

> say 包子
你說：『包子』

麵包師傅把【包子/bun】拿給你。
麵包師傅說：『村長訂的包子，剛蒸好的，拿去吧。』

> w
【村子廣場】
【出口： 北 東】

村長站在這裡。

> give bun elder
你把【包子/bun】拿給村長。

村長說：『就是這個味道！對了，北邊的森林最近野狼很多，幫我打倒 3 隻吧。』

> n
【森林小徑】
【出口： 南】

野狼站在這裡。
野狼站在這裡。
野狼站在這裡。
```

打倒第一隻、第二隻：

```
> kill wolf
你使用直拳攻擊野狼，對它造成輕微的擦傷.(2)
野狼已經斷氣，倒在地上死亡了!!
你共獲得了【12】點的經驗點數。
你已經打倒了 1 隻野狼。
野狼的屍體裝著：
     空無一物。

> kill wolf
你使用直拳攻擊野狼，對它造成輕微的擦傷.(2)
野狼已經斷氣，倒在地上死亡了!!
你共獲得了【12】點的經驗點數。
你已經打倒了 2 隻野狼。
野狼的屍體裝著：
     空無一物。
```

先回去問一次：

```
> s
【村子廣場】
【出口： 北 東】

村長站在這裡。

> say 任務
你說：『任務』

村長說：『野狼才打倒 2 隻，還差一些。』
```

再去打倒第三隻：

```
> kill wolf
你使用直拳攻擊野狼，對它造成輕微的擦傷.(2)
野狼已經斷氣，倒在地上死亡了!!
你共獲得了【12】點的經驗點數。
野狼打夠了，回村子找村長吧。
野狼的屍體裝著：
     空無一物。
```

回到廣場，村長看到你就說話（`on_enter`）：

```
> s
【村子廣場】
【出口： 北 東】

村長站在這裡。

村長說：『你回來啦！說「任務」跟我報告吧。』

> say 任務
你說：『任務』

村長把【賢者之致命長劍/sword】拿給你。
村長說：『太好了！這把長劍送你，謝謝你幫了村子這麼多。』

> i
你目前所攜帶的東西有：
     賢者之致命長劍/sword
（1/35 件，負重 5/140）

> say 任務
你說：『任務』

村長說：『謝謝你上次幫忙。』
```

最後 Ming 存檔的 `vars` 是 `{"village": {"bun": "完成"}}`：`wolves` 清掉了，只留下「完成」。
