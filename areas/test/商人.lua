-- 生物 1「測試商人」：有人說「你好」，就回一句話
function on_say(actor, text)
  if text == "你好" then
    me:command("say 歡迎光臨，" .. actor.name .. "！")
  end
end
