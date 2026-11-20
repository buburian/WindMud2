-- 引路人（盜賊公會入口）：劍之公會的玩家在這裡選職業（mud/paths.py，使用者 2026-11-19 要的）
-- 職業「刺客」10 級可以選；進階職業「雙刃」「暗殺」40 級可以選。換職業要錢：先講價錢，再說一次才換
local GUILD = "phys"
local BIG = "刺客"
local SMALLS = {["雙刃"] = true, ["暗殺"] = true}
local REPLY = {
  ok = "好，從今天起你就是這個職業了。學會的本事，用 skills 看。",
  changed = "舊的就忘了吧，從頭來過。",
  too_low = "你還太嫩了。職業要 10 級，進階職業要 40 級才能選。",
  wrong_guild = "你不是劍之公會的人，這裡教不了你。",
  not_yours = "這兩個進階職業接在刺客下面，你得先當刺客。",
  already = "你本來就是這個職業。",
  poor = "換職業的錢不夠，存夠了再來。",
}

function on_enter(actor, from)
  if not actor:is_player() or me:is_fighting() or actor.guild ~= GUILD then return end
  if actor.level >= 10 and actor:path() == nil then
    me:command("say " .. actor.name .. "，想當刺客的話，說「刺客」就行。")
  elseif actor.level >= 40 and actor:path() == BIG and actor:subpath() == nil then
    me:command("say 你可以選進階職業「雙刃」（兩手各拿一把，連續地打）或「暗殺」（打暈、讓敵人變弱），想好了就說。")
  end
end

function on_say(actor, text)
  if text ~= BIG and not SMALLS[text] then return end
  local price = actor:path_price(text)
  if price > 0 and actor.vars.change ~= text then
    actor.vars.change = text
    me:command("say 換職業要 " .. price .. " 金幣，原本那個職業的本事會全部忘掉。確定的話，再說一次「" .. text .. "」。")
    return
  end
  actor.vars.change = nil
  me:command("say " .. REPLY[actor:choose_path(text)])
end
