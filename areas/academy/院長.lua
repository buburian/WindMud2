-- 院長（畢業廳）：學生說「畢業」，收回鑰匙、送他到外面的世界（101）
-- actor.vars.student 是建立角色時程式設的（config.ACADEMY_STUDENT），拿掉就算畢業
function on_say(actor, text)
  if text == "畢業" then
    actor.vars.student = nil
    actor:take_item(1)
    me:command("say 恭喜你畢業了，" .. actor.name .. "！外面的世界很大，好好冒險吧。")
    actor:transfer(101)
  end
end
