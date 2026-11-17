-- 行醫者：有玩家走進來就招呼（舊版 C 的平常動作，文字照龍焚之夜一百年後重寫）

function on_enter(actor, from)
  if not actor:is_player() or me:is_fighting() then return end   -- 照 C 版：只招呼玩家，打架中不招呼
  local n = random(1, 2)
  if n == 1 then
    me:command("smile")
  elseif n == 2 then
    me:command("say 受了傷就過來，我替你包紮。")
  end
end
