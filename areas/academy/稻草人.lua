-- 稻草人（訓練場）：被打倒時，北邊往畢業廳的石門打開
function on_death(killer)
  room:door("north", "open")
  room:echo("北邊的石門喀啦一聲打開了。")
end
