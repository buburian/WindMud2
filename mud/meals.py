"""吃喝的效果（設計文件 §3.9，使用者 2026-11-17 定的；規則在玩家角色手冊「吃喝」）。指令在 commands/meals.py。

不會餓、不會渴。吃喝之後連續 MEAL_TICKS（10）秒都在休息或睡覺，才有效果：
- 有 buff（食物的 buff、液體種類的 buff）：把那個 buff 技能的效果放在自己身上（跟 §3.8 一樣不扣消耗、不用學會）。
- 沒有 buff：回得快一倍（ch.meal_bonus，stats.regen 看它），到站起來或打架為止。吃的回 HP，喝的回公會的資源（劍 MV、杖 MP）。
- 10 秒內站起來、開打、死掉：這一口沒效果，正在快一倍的也停（站起來、開打、死掉的當下就 cancel()，每秒的 tick() 是保險）。
- 再吃再喝：重新數 10 秒；正在快一倍的照樣有效，數完覆蓋、不疊（我們定的，請 mud_design 補進 §3.9）。
都不存檔：下線就沒了。
"""
from . import affects, skills   # 坑：skills → affects → combat → death → fight → meals 繞一圈，要用 skills.名字，不能 from .skills import
from .act import gathering, notify
from .characters import Position, characters
from .config import MEAL_TICKS
from .stats import GUILD_RESOURCE

EAT, DRINK = "eat", "drink"
REGEN_MULT = 2                              # 回得快幾倍（休息 20% → 40%、睡覺 30% → 60%）
SEATED = (Position.RESTING, Position.SLEEPING)
STARTED = {                                 # 回得快一倍開始時說的（C 版沒有，我們定的）
    EAT: "你吃下的東西開始發揮作用，HP 恢復得比較快了。",
    DRINK: "你喝下的東西開始發揮作用，{} 恢復得比較快了。",
}
BUFFED = {EAT: "你吃下的東西開始發揮作用：【{}】。", DRINK: "你喝下的東西開始發揮作用：【{}】。"}


def start(ch, kind, buff):
    """ch 吃了（EAT）或喝了（DRINK）一口：重新數 MEAL_TICKS。buff 是技能的 key（"" 是沒有）。"""
    ch.meals[kind] = [MEAL_TICKS, buff]


def cancel(ch):
    """站起來、開打、死掉：還在等的和正在快一倍的都沒了（不說話）。"""
    ch.meals.clear()
    ch.meal_bonus.clear()


def seated(ch):
    return ch.position in SEATED and ch.fighting is None


def resource(ch, kind):
    """回得快的是哪一項：吃的是 HP；喝的是公會的資源（劍之公會 MV、杖之公會 MP；沒有公會的生物算 MV）。"""
    return "hp" if kind == EAT else GUILD_RESOURCE.get(getattr(ch, "guild", None), "mv")


def tick():
    """世界每個 tick：等的少 1 秒，到了就有效果；沒在坐著（或睡覺）就全部取消。

    吃和喝同一秒到：兩句收成一段（gathering），只有一個 prompt。
    buff 不用 skills.use()：那是「你對自己施展了」，在 tick 裡送給自己不會補 prompt，所以直接放效果、說吃喝的那句。
    """
    with gathering():
        for ch in [c for c in characters if c.meals or c.meal_bonus]:
            if not seated(ch):
                cancel(ch)
                continue
            for kind, entry in list(ch.meals.items()):
                entry[0] -= 1
                if entry[0] > 0:
                    continue
                del ch.meals[kind]
                buff = skills.SKILLS.get(entry[1]) if entry[1] else None
                if buff is not None:
                    affects.add(ch, skills.make_affect(buff))
                    notify(ch, BUFFED[kind].format(buff.name))
                else:
                    key = resource(ch, kind)
                    ch.meal_bonus[key] = REGEN_MULT
                    notify(ch, STARTED[kind].format(skills.RESOURCE_NAMES.get(key, key)))
