-- 水手：每 30 秒做一件事（舊版 C 的平常動作，文字照龍焚之夜一百年後重寫）

function on_timer()
  if me:is_fighting() then return end                            -- 照 C 版：打架中不做
  room:echo(me.name .. "一邊拉緊繩結，一邊嘿咻、嘿咻地喊著。")
end
