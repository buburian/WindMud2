-- 毛皮店老闆：每 30 秒做一件事（舊版 C 的平常動作，文字照龍焚之夜一百年後重寫）

function on_timer()
  if me:is_fighting() then return end                            -- 照 C 版：打架中不做
  room:echo(me.name .. "低著頭，一針一針地縫著硬皮小帽。")
end
