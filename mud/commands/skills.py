"""技能類指令：use 放技能、skills 列出會的技能。規則在玩家角色手冊「技能」。

技能只能用 use 放（使用者要的）：新增技能只要在 skills.SKILLS 加資料，不用加指令。
誰會哪個技能看 skills.known()（技能自己設計：一開始就會、要用程式加）。傷害技能可以開打（使用者定的）；增益技能放在自己或同房間的玩家身上，不開打。
"""
from .. import affects, fight, skills
from ..characters import characters, find_in_room
from ..config import TICK_SECONDS
from ..npcs import Npc
from .system import wrap


def do_use(ch, arg):
    """use <技能> [名字]：技能可以縮寫（只找自己會的），名字照 find_in_room()（開頭、2.dog）。檢查都過了才開打、打出去。"""
    words = arg.split()
    if not words:
        ch.send("你想要用什麼技能？\n")
        return
    skill = skills.find(ch, words[0])
    if skill is None:                       # 沒學過的、imm 的技能也是這句
        ch.send("你不會這個技能。\n")
        return
    if skill.target == "ally":              # 增益：沒打名字是自己，只能放在玩家身上，不開打
        target = find_in_room(ch, words[1]) if len(words) > 1 else ch
        if target is None:
            ch.send("這裡沒有這個人。\n")
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
    if not isinstance(victim, Npc):
        ch.send("你不可以攻擊玩家。\n")
        return
    if not ready(ch, skill):
        return
    engage(ch, victim)                      # 檢查都過了才開打：沒過就不會開打
    skills.use(ch, skill, victim)


def ready(ch, skill):
    """冷卻、MV／MP、武器都過了才是 True；沒過就送那一句。"""
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
    """skills：列出會的技能和說明的數字（傷害、消耗、冷卻；冷卻中的寫還要等幾秒）。"""
    known = skills.known(ch)
    if not known:
        ch.send("你還不會任何技能。\n")
        return
    lines = ["你會的技能（imm 用技能不扣消耗、不用等冷卻）：" if skills.free(ch) else "你會的技能："]
    for s in known:
        pool = skills.resource(s)
        spent = f"{skills.cost(s, ch.level)}" + (f" {skills.RESOURCE_NAMES[pool]}" if pool else "")    # 沒有資源的技能
        if s.kind == "buff":                # 增益：寫持續多久，做什麼放下一行（太長就換行，不超過 79 格）
            a = affects.Affect(**s.affect)
            what = f"持續 {a.duration * TICK_SECONDS:g} 秒"
        else:
            low, high = skills.display_range(ch, s)
            what = f"傷害 {low}~{high}"
        line = f"  {s.name} {s.id}  {what}  消耗 {spent}  冷卻 {s.cooldown} 秒"
        wait = ch.cooldowns.get(s.id)
        if wait:
            line += f"  還要等 {wait} 秒"
        lines.append(line)
        if s.kind == "buff":
            lines += ["    " + more for more in wrap(affects.parts(a), 75)]
    ch.send("\n".join(lines) + "\n")
