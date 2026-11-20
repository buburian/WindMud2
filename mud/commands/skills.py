"""技能類指令：use 放技能、skills 列出會的技能。規則在玩家角色手冊「技能」。

技能只能用 use 放（使用者要的）：新增技能只要在 skills.SKILLS 加資料，不用加指令。
誰會哪個技能看 skills.known()（技能自己設計：一開始就會、要用程式加）。傷害、減益技能可以開打（使用者定的）；
補血、增益技能放在自己或同房間的玩家身上（"self" 的只有自己），不開打；被動技能不用放。
"""
from .. import affects, combos, fight, paths, skills, summons, temper
from ..area import TWO_HANDED_KINDS, WEAPON_KIND_NAMES
from ..characters import characters, find_in_room
from ..config import AFFECT_PULSE_TICKS, TICK_SECONDS
from ..npcs import Npc
from . import system
from .combat import attackable, protected
from .system import wrap


def do_use(ch, arg):
    """use <技能> [名字]：技能可以縮寫（只找自己會的），名字照 find_in_room()（開頭、2.dog）。檢查都過了才開打、打出去。"""
    words = arg.split()
    if not words:
        ch.send("你想要用什麼技能？\n")
        return
    if words[0].lower() in temper.WORDS:    # 淬火石（設計文件 §3.11）：不是技能，要打完整的名字
        from . import temper as temper_command      # 坑：commands/temper.py 用到 items，items 跟技能的模組互相用，在函式裡才 import
        temper_command.use(ch, words[1:])
        return
    skill = skills.find(ch, words[0])
    if skill is None:                       # 沒學過的、imm 的技能也是這句
        ch.send("你不會這個技能。\n")
        return
    if skill.kind == "passive":
        ch.send(PASSIVE.format(skill.name) + "\n")
        return
    if affects.controlled(ch, affects.MUTED):    # 暈、凍住、沉默：不能用技能（設計文件 §2.6）
        ch.send((system.HELD if affects.controlled(ch, affects.HELD) else SILENCED) + "\n")
        return
    if skill.target in skills.GROUP_TARGETS:
        group(ch, skill)
        return
    if skill.kind == "summon":              # 召喚：不用打名字，不開打
        if ready(ch, skill):
            skills.use(ch, skill, ch)
        return
    if skills.friendly(skill):              # 補血、增益：沒打名字是自己，只能放在玩家身上，不開打
        target = find_in_room(ch, words[1]) if len(words) > 1 else ch
        if target is None:
            ch.send("這裡沒有這個人。\n")
        elif skill.target == "self" and target is not ch:
            ch.send(skills.SELF_ONLY + "\n")
        elif skill.kind == "protect" and target is ch:
            ch.send(NOT_YOURSELF + "\n")
        elif isinstance(target, Npc):
            ch.send(f"{skill.name}只能放在玩家身上。\n")
        elif ready(ch, skill):
            skills.use(ch, skill, target)
        return
    if len(words) > 1:
        victim = find_in_room(ch, words[1])
    elif ch.fighting is not None:
        victim = ch.fighting
        # 戰鬥中可以走路：對手走了要等下一回合才會停手，所以現在的對手也要看還在不在同一間房
        if victim not in characters or victim.room is not ch.room:
            victim = None
    else:
        ch.send("你想要攻擊誰？\n")
        return
    if victim is None:
        ch.send("找不到你想攻擊的人。\n")
        return
    if not attackable(ch, victim):
        return
    if skill.opener and (ch.fighting is not None or victim.fighting is not None) and not combos.opener_ok(victim):
        ch.send(OPENER.format(skill.name) + "\n")
        return
    if protected(ch, victim) or not ready(ch, skill):   # 安全區在扣消耗之前擋
        return
    engage(ch, victim)                      # 檢查都過了才開打：沒過就不會開打
    skills.use(ch, skill, victim)


PASSIVE = "{}是被動技能，學會就一直有效，不用放。"
SILENCED = "你現在發不出聲音，不能用技能。"
OPENER = "{}只能在還沒開打時用。"            # 只能開打前用（設計文件 §2.6）：自己或目標已經在打架


NO_ENEMIES = "這裡沒有可以攻擊的對象。"
NOT_YOURSELF = "你不能保護自己。"
NOBODY_ELSE = "這裡沒有別人可以保護。"


def group(ch, skill):
    """打一群（房間裡看得到的生物全部）、放在一群自己人上（自己和同房間的玩家）：不用打名字，打了也不管。
    打一群跟傷害技能一樣：安全區不能用、檢查都過了才開打，還沒在打架的也會開打（engage 每一隻）。
    """
    if skill.target == "allies":
        targets = skills.allies(ch)
        if skill.kind == "protect" and len(targets) == 1:     # 不倒之盾：只有自己
            ch.send(NOBODY_ELSE + "\n")
        elif ready(ch, skill):
            skills.use(ch, skill, targets)
        return
    victims = skills.enemies(ch)
    if not victims:
        ch.send(NO_ENEMIES + "\n")
        return
    if protected(ch, victims[0]) or not ready(ch, skill):
        return
    for victim in victims:
        engage(ch, victim)
    skills.use(ch, skill, victims)


def ready(ch, skill):
    """冷卻、MV／MP、武器、副手都過了才是 True；沒過就送那一句。"""
    wait = ch.cooldowns.get(skill.id)
    if wait:
        ch.send(f"你還要等 {wait} 秒才能再用{skill.name}。\n")
        return False
    if not skills.affordable(ch, skill):
        ch.send(f"你的 {skills.RESOURCE_NAMES[skills.resource(skill)]} 不夠。\n")
        return False
    if not skills.weapon_ok(ch, skill):
        ch.send(f"你手上的武器不能用{skill.name}。\n")
        return False
    if not skills.offhand_ok(ch, skill):
        ch.send(skills.OFFHAND_NEEDS[skill.offhand].format(skill.name) + "\n")
        return False
    return True


def engage(ch, victim):
    """技能打出去之前，讓兩邊在戰鬥裡（使用者定的）。

    - ch 沒在打架：跟 kill 一樣開打（victim 在跟別人打，就加進那一場）。
    - ch 在打架、victim 沒在打人：victim 加進來打 ch，ch 的對手不變（照 C 版）。
    - victim 已經在打別人：不改誰打誰。
    """
    if ch.fighting is None:
        fight.start_fight(ch, victim)
    elif victim.fighting is None:
        fight.start_fight(victim, ch)


def do_skills(ch, arg):
    """skills：會的技能排成一張表（使用者 2026-11-20 選的樣子）：技能、效果、消耗、冷卻四欄對齊，冷卻中的寫還要等幾秒；
    做什麼、條件放下一行，對齊效果那一欄（太長就換行，不超過 79 格）。被動技能沒有消耗、冷卻。
    選好路以後，這條路還沒學會的技能另外列在下面「還沒學會」，照幾級學會排；還沒選的路看不到技能，
    最下面只寫可以選哪幾條、去哪裡選（paths.hint_lines，使用者要的）。
    """
    known = skills.known(ch)
    later = sorted(((lv, s) for lv, s in paths.chosen_skills(ch) if s not in known), key=lambda step: step[0])
    if not known and not later:
        ch.send("你還不會任何技能。\n")
        return
    lines = known_lines(ch, known) if known else []
    if later:
        lines += ([""] if lines else []) + later_lines(ch, later)
    hint = paths.hint_lines(ch) if known else []
    if hint:
        lines += [""] + hint
    ch.send("\n".join(lines) + "\n")


HEAD = ("技能", "效果", "消耗", "冷卻")
LATER = "還沒學會（升到那一級自動學會）："
GAP = "  "                                  # 欄和欄中間
WIDTH = 79                                  # 一行最多幾格（跟 score 一樣）


def known_lines(ch, known):
    """會的技能那張表：標題、每個技能一行（四欄對齊），下一行起是做什麼、條件（對齊效果那一欄）。"""
    rows = []
    for s in known:
        what, more = summary(ch, s)
        if s.kind == "passive":
            spent = cooldown = ""
        else:
            pool = skills.resource(s)
            spent = f"{skills.cost(s, ch.level)}" + (f" {skills.RESOURCE_NAMES[pool]}" if pool else "")    # 沒有資源的技能
            cooldown = f"{s.cooldown} 秒"
            wait = ch.cooldowns.get(s.id)
            if wait:
                cooldown += f"  還要等 {wait} 秒"
        rows.append(((f"{s.name} {s.id}", what, spent, cooldown), more + conditions(s)))
    widths = [max(system.width(cells[i]) for cells in [HEAD] + [r[0] for r in rows]) for i in range(3)]
    indent = fitting(2 + widths[0] + len(GAP), 4, [more for _, more in rows])

    def line(cells):
        return ("  " + GAP.join(system.pad(c, w) for c, w in zip(cells, widths)) + GAP + cells[3]).rstrip()

    title = "你會的技能（imm 用技能不扣消耗、不用等冷卻）：" if skills.free(ch) else "你會的技能："
    lines = [title, line(HEAD)]
    for cells, more in rows:
        lines.append(line(cells))
        if more:
            lines += [" " * indent + text for text in wrap(more, WIDTH - indent)]
    return lines


def fitting(indent, fallback, mores):
    """說明對齊的位置：有一段（「、」中間的一句）在 indent 放不下（超過 79 格）就整段都改成 fallback，同一段對齊同一個地方。"""
    longest = max((system.width(text) for more in mores for text in more), default=0) + system.width("、")   # 行尾可能接著「、」
    return indent if indent + longest <= WIDTH else fallback


def later_lines(ch, later):
    """選了的路上還沒學會的技能：幾級、技能、效果（被動的寫「被動：閃躲 +5%」），下一行起是做什麼、條件。"""
    rows = []
    for lv, s in later:
        what, more = summary(ch, s)
        more = more + conditions(s)
        if s.kind == "passive" and more:
            what, more = f"{what}：{more[0]}", more[1:]
        rows.append((f"{lv} 級", f"{s.name} {s.id}", what, more))
    level_w = max(system.width(r[0]) for r in rows)
    name_w = max(system.width(r[1]) for r in rows)
    indent = fitting(2 + level_w + len(GAP) + name_w + len(GAP), 2 + level_w + len(GAP), [r[3] for r in rows])
    lines = [LATER]
    for level, name, what, more in rows:
        lines.append("  " + system.pad(level, level_w) + GAP + system.pad(name, name_w) + GAP + what)
        if more:
            lines += [" " * indent + text for text in wrap(more, WIDTH - indent)]
    return lines


PULSE_SECONDS = AFFECT_PULSE_TICKS * TICK_SECONDS


def span(low, high):
    """範圍：一樣的只寫一個（「5」不寫「5~5」，使用者 2026-11-20 要的）。"""
    return f"{low}" if low == high else f"{low}~{high}"


def summary(ch, s):
    """skills 效果那一欄的「傷害 17~19」「補血 30」「持續 60 秒」「被動」，和下一行要寫的（[一句一句]，打好幾下的「打 2 次」最前面）。"""
    if s.kind == "passive":
        more = affects.parts(affects.Affect(source=s.id, name=s.name, duration=0, mult=s.passive))
        if s.rest_regen != 1.0:             # 調息、冥想
            more.append(f"休息、睡覺回復 ×{s.rest_regen:g}")
        if s.fight_end:                     # 收刀、回神
            more.append(f"整場戰鬥結束回 HP、MP、MV 各 {s.fight_end * 100:g}%")
        return "被動", more
    if s.kind == "protect" and s.guard:     # 守護：他被打的傷害有 30% 改由你承受
        return (f"持續 {s.guard['duration'] * TICK_SECONDS:g} 秒",
                [f"被打的傷害 {s.guard['share'] * 100:g}% 改由你承受"])
    if s.kind == "summon":                  # 召喚：叫出一隻骷髏（比你低 10 級）幫你打
        info = s.summon
        return (f"持續 {info['duration'] * TICK_SECONDS:g} 秒",
                [f"叫出一隻{summons.creature_name(s.id)}（比你低 {info['below']} 級）幫你打"])
    if s.kind == "protect":                 # 挑釁
        return f"持續 {s.affect['duration'] * TICK_SECONDS:g} 秒", ["改打你（被挑釁）"]
    if s.kind == "heal":
        low, high = skills.heal_range(ch, s)
        if s.hot:
            return (f"持續 {s.hot['jumps'] * PULSE_SECONDS:g} 秒",
                    [f"每 {PULSE_SECONDS:g} 秒補 {span(low, high)} HP，{s.hot['jumps']} 次"])
        return f"補血 {span(low, high)}", []
    if s.kind == "debuff" and s.dot:        # 持續扣血的減益：每跳 ＝ 這一下 × ratio
        low, high = skills.display_range(ch, s)
        return (f"持續 {s.dot['jumps'] * PULSE_SECONDS:g} 秒",
                [f"{s.dot['name']}：每 {PULSE_SECONDS:g} 秒傷害 {span(low, high)}，{s.dot['jumps']} 次"])
    if s.kind in ("buff", "debuff") or (s.kind == "control" and not s.hits):    # 增益、減益、控制：寫持續多久，做什麼放下一行
        a = skills.make_affect(s)
        return f"持續 {a.duration * TICK_SECONDS:g} 秒", affects.parts(a, listing=True)
    low, high = skills.display_range(ch, s)
    more = []
    if s.dot:                               # 打中後的持續傷害：燃燒：每 3 秒 第一發的 30%，3 次
        more.append(f"{s.dot['name']}：每 {PULSE_SECONDS:g} 秒 第一發的 {s.dot['ratio'] * 100:g}%，{s.dot['jumps']} 次")
    if s.onhit:                             # 打中後的減弱、控制：打中後：攻速 -10%、變慢，6 秒
        a = affects.Affect(source=s.id, name=s.name, **s.onhit)
        more.append("打中後：" + "、".join(affects.parts(a)) + f"，{a.duration * TICK_SECONDS:g} 秒")
    if s.lifesteal:
        more.append(f"吸血 {s.lifesteal * 100:g}%")
    times = [f"打 {s.hits} 次"] if s.hits > 1 else []     # 傷害是一下的範圍：打好幾下的寫幾次（猛擊打兩下，2026-11-20）
    return f"傷害 {span(low, high)}", times + more


SPLIT = "（每多一隻總量 +50%，再平分）"


def conditions(s):
    """打誰（打一群、放在一群上）和用的條件（設計文件 §2.6）：限定武器、副手、只能開打前用。"""
    out = []
    if s.target == "group":
        out.append("打房間裡全部的怪" + (SPLIT if s.hits else ""))
    elif s.target == "allies":
        out.append("同房間的其他玩家" if s.kind == "protect" else "自己和同房間的玩家" + SPLIT)
    return out + requirements(s)


def requirements(s):
    """用的條件（skills 列出來、help 技能名共用）：限定武器、副手、只能開打前用。"""
    out = []
    if s.weapon_kinds:
        kinds = set(s.weapon_kinds)
        out.append("要拿雙手武器" if kinds == TWO_HANDED_KINDS else "要拿" + "、".join(WEAPON_KIND_NAMES[k] for k in s.weapon_kinds))
    if s.offhand:
        out.append(skills.OFFHAND_NAMES[s.offhand])
    if s.opener:
        out.append("只能在還沒開打時用")
    return out
