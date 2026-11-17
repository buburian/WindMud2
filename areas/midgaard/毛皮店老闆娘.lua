-- 毛皮店老闆娘：有玩家走進來就招呼、每 30 秒做一件事（舊版 C 的平常動作，文字照龍焚之夜一百年後重寫）

function on_enter(actor, from)
  if not actor:is_player() or me:is_fighting() then return end   -- 照 C 版：只招呼玩家，打架中不招呼
  me:command("say 要帽子還是手套？都是自家刮的皮，擋得住北風。")
end

function on_timer()
  if me:is_fighting() then return end                            -- 照 C 版：打架中不做
  room:echo(me.name .. "刮著生皮，刮刀沙沙作響。")
end
