-- 無賴漢：有玩家走進來就招呼（舊版 C 的平常動作，文字照龍焚之夜一百年後重寫）

function on_enter(actor, from)
  if not actor:is_player() or me:is_fighting() then return end   -- 照 C 版：只招呼玩家，打架中不招呼
  actor:tell(me.name .. "湊過來，壓低聲音對你說：「錢袋留下，你就能好好走出這條巷子。」")
end
