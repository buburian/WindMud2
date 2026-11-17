-- 雜貨店老闆：有玩家走進來就招呼（舊版 C 的平常動作，文字照龍焚之夜一百年後重寫）

function on_enter(actor, from)
  if not actor:is_player() or me:is_fighting() then return end   -- 照 C 版：只招呼玩家，打架中不招呼
  me:command("say 要火把還是水袋？天黑了出城不帶火把，可是會摔進溝裡的。")
end
