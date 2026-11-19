-- 執法者：有玩家走進來就招呼（舊版 C 的平常動作，文字照龍焚之夜一百年後重寫）；
-- 身上沒有光源的玩家，密語告訴他雜貨店怎麼走；不到 5 級又買不起火把的，先送他 3 支（使用者 2026-11-19 要的）

local LIGHT = 1                           -- 物品種類：照明用具（看種類不看號碼：之後有別的光源也算）
local TORCH = 3030
local TORCH_PRICE = 20                    -- 雜貨店的火把（人類 18，照 20 算）
local FREE_TORCHES = 3
local FREE_BELOW = 5                      -- 不到 5 級才送

function on_enter(actor, from)
  if not actor:is_player() or me:is_fighting() then return end   -- 照 C 版：只招呼玩家，打架中不招呼
  me:command("say 神殿裡不准動刀動劍。記住了。")
  if actor:has_item_type(LIGHT) or actor:wears_item_type(LIGHT) then return end
  if actor.gold < TORCH_PRICE and actor.level < FREE_BELOW then
    for i = 1, FREE_TORCHES do
      actor:give_item(TORCH, 1)
    end
    me:command("tell " .. actor.name .. " 城外天黑得快，這幾支火把先拿去用。")
  end
  me:command("tell " .. actor.name .. " 雜貨店有賣火把：往南走 3 步、往東 2 步，再往北 1 步就到了。")
end
