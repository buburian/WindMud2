-- 武器店老闆：有玩家走進來就招呼（舊版 C 的平常動作，文字照龍焚之夜一百年後重寫）

function on_enter(actor, from)
  if not actor:is_player() or me:is_fighting() then return end   -- 照 C 版：只招呼玩家，打架中不招呼
  local n = random(1, 2)
  if n == 1 then
    me:command("say 我打的劍有時候不太直，可是很耐砍，你看看？")
  elseif n == 2 then
    room:echo(me.name .. "忙著把剛打好的劍浸進水桶，嘶的一聲冒出白煙。")
  end
end
