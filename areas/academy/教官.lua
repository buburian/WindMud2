-- 教官（教官室）：學生走進來，送他餽贈和一把 1 級紫色長劍（物品 2），再叫他去訓練場
function on_enter(actor, from)
  if actor:is_player() then
    me:command("say 歡迎，" .. actor.name .. "！上場之前，先送你一份餽贈。")
    me:use("gift", actor)
    if not actor:has_item(2) and not actor:wears_item(2) then   -- 已經有了就不再給（來回走才不會拿到一堆）
      actor:give_item(2, 1, "purple")
      me:command("say 這把長劍給你，打 wear 長劍 拿在手上。")
    end
    me:command("say 去北邊的訓練場，把稻草人打倒吧。")
  end
end
