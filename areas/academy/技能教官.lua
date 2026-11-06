-- 技能教官（技能教室）：學生走進來，教他用 skills 看技能、用 use 放技能（照他的公會說一開始就會的技能）
function on_enter(actor, from)
  if actor:is_player() then
    local skill = "smash"
    if actor.guild == "spell" then skill = "fireball" end
    me:command("say " .. actor.name .. "，先打 skills 看看你會哪些技能。")
    me:command("say 放技能打 use 技能 目標，等一下到訓練場試試看：use " .. skill .. " 稻草人。")
  end
end
