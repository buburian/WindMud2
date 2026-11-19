-- 行醫者：有玩家走進來就招呼（舊版 C 的平常動作，文字照龍焚之夜一百年後重寫）；
-- 1～10 級、身上還沒有餽贈的玩家再送他餽贈（使用者要的：來回走不會一直放）

function on_enter(actor, from)
  if not actor:is_player() or me:is_fighting() then return end   -- 照 C 版：只招呼玩家，打架中不招呼
  local n = random(1, 2)
  if n == 1 then
    me:command("smile")
  elseif n == 2 then
    me:command("say 我年輕時也是從這座神殿出發的。")
  end
  if actor.level < 11 and not actor:has_affect("gift") then
    me:use("gift", actor)
  end
end
