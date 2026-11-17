-- 麵包店老闆：有玩家走進來就招呼（舊版 C 的平常動作，文字照龍焚之夜一百年後重寫）

function on_enter(actor, from)
  if not actor:is_player() or me:is_fighting() then return end   -- 照 C 版：只招呼玩家，打架中不招呼
  me:command("say 黑麥麵包剛出爐，整條街就數我這一爐最香。")
end
