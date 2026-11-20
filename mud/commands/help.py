"""help：只打 help 只看分類（使用者 2026-11-20 要的：首頁不列指令）；help 分類 看這一類的指令；help 指令 看說明（指令可以縮寫，規則跟打指令一樣）。
指令找不到才找不是指令的說明（helps.topics，例如 help 屬性、help str：名字要打全名），再找不到才找技能（help smash、help 重擊：
英文或中文名字的全名，2026-11-20 使用者要的：做什麼，不寫數字）。

說明文字在 help/help.json（helps.py 讀檔、檢查）。標題後面的縮寫照指令表算，指令表改了也不會寫錯。
imm 的分類（管理員）只有 imm 看得到；不是 imm 也找不到 imm 指令的說明（跟打 imm 指令一樣）。
坑：commands/__init__.py import 這個模組，這裡又要用指令表，所以 command_name 在函式裡才 import。
"""
from .. import helps
from .system import pad, width

NOT_FOUND = "對不起，找不到相對應的說明。"     # 照 C 版


def do_help(ch, arg):
    """help [分類或指令]。"""
    is_imm = getattr(ch, "imm", False)
    words = arg.split()
    if not words:
        ch.send(summary(is_imm))
        return
    word = words[0]
    if any(c["name"] == word for c in visible(is_imm)):     # 分類名稱要整個字一樣
        ch.send(category(word))
        return
    entry = entry_of(word.lower(), is_imm) or topic_of(word, is_imm)
    if entry:
        ch.send(detail(entry, is_imm))
        return
    skill = skill_of(word)
    ch.send(skill_detail(skill) if skill else NOT_FOUND + "\n")


def visible(is_imm):
    """看得到的分類：imm 的分類只有 imm 看得到。"""
    return [c for c in helps.categories if is_imm or not c["imm"]]


def summary(is_imm):
    """只打 help：只列分類，一個一行（使用者 2026-11-20 要的：指令要 help 分類 才看得到）；
    不是指令的說明（topics，例如屬性）也列在最後，help 屬性 直接看內容（使用者要的）。"""
    cats = visible(is_imm)
    seen = {c["name"] for c in cats}
    lines = ["說明的分類（help 分類 看這一類有哪些指令）："]
    lines += [f"  {c['name']}" for c in cats]
    lines += [f"  {t['names'][0]}" for t in helps.topics if t["category"] in seen]
    lines.append("知道指令或技能的名字，也可以直接 help 名字，例如 help kill、help smash。")
    return "\n".join(lines) + "\n"


def category(name):
    """help 分類：這一類的每一筆說明，指令和一句話。"""
    rows = [(" ".join(e["commands"]), e["summary"]) for e in helps.entries if e["category"] == name]
    rows += [(t["names"][0], t["summary"]) for t in helps.topics if t["category"] == name]
    w = max(width(cmds) for cmds, _ in rows)
    return "\n".join([f"【{name}】", *(f"  {pad(cmds, w)}  {s}" for cmds, s in rows)]) + "\n"


def entry_of(word, is_imm):
    """word 當成指令找（跟打指令一樣：第一個用它開頭的），回傳那個指令的說明；找不到是 None。"""
    from . import command_name
    name = command_name(word, is_imm)
    return next((e for e in helps.entries if name in e["commands"]), None) if name else None


def topic_of(word, is_imm):
    """不是指令的說明：名字要打全名（英文不分大小寫），分類要看得到；找不到是 None。"""
    seen = {c["name"] for c in visible(is_imm)}
    return next((t for t in helps.topics if t["category"] in seen and word.lower() in (n.lower() for n in t["names"])), None)


def detail(entry, is_imm):
    """help 指令：標題（用法＋縮寫）和說明。不是指令的說明（topics）沒有縮寫。"""
    short = [s for s in (shortest(c, is_imm) for c in entry.get("commands", [])) if s]
    title = entry["usage"] + (f"（縮寫 {' '.join(short)}）" if short else "")
    return "\n".join([title, *entry["text"]]) + "\n"


TARGET_TEXT = {"single": "打一隻生物", "group": "打房間裡全部的怪", "ally": "放在自己或同房間的玩家身上",
               "allies": "放在自己和同房間的玩家身上", "self": "只能放在自己身上"}
NOT_LEARNED = "學不到：要用物品或別人來放"
NUMBERS = "傷害、消耗、冷卻、效果的數字，學會以後打 skills 看。"


def skill_of(word):
    """技能：英文名字（不分大小寫）或中文名字要打全名；imm 的技能找不到。找不到是 None。"""
    from .. import skills
    return next((s for s in skills.SKILLS.values() if s.id in helps.skill_texts and word.lower() in (s.id, s.name)), None)


def skill_detail(s):
    """help 技能名：名字、誰會幾級、做什麼（help.json）、種類和打誰和條件，數字不寫（用 skills 看）。"""
    return "\n".join([f"{s.name} {s.id}", who_learns(s), *helps.skill_texts[s.id], kind_text(s), NUMBERS]) + "\n"


def who_learns(s):
    """誰會、幾級：建立角色就會的、公會升級自動學的（paths.GUILD_SKILLS）、職業的（paths.PATHS），都不是就是學不到的。"""
    from .. import paths
    from ..stats import GUILD_NAMES
    for guild, steps in paths.GUILD_SKILLS.items():
        level = next((lv for lv, sid in steps if sid == s.id), None)
        if level is not None:
            return f"{GUILD_NAMES[guild]}：{level} 級自動學會"
    if s.starter:
        return "、".join(GUILD_NAMES[g] for g in s.starter) + "：一開始就會"
    for p in paths.PATHS.values():
        level = next((lv for lv, sid in p.skills if sid == s.id), None)
        if level is not None:
            job = f"{p.parent}的進階職業" if p.parent else f"{GUILD_NAMES[p.guild]}的職業"
            return f"{p.name}（{job}）：{level} 級"
    return NOT_LEARNED


def kind_text(s):
    """種類、打誰、用的條件（要拿什麼武器、要拿盾、只能開打前用），沒有數字。"""
    from .. import skills
    from .skills import requirements
    if s.kind == "passive":
        head = "被動技能，學會就一直有效"
    elif s.kind == "summon":
        head = "召喚技能"
    elif s.kind == "protect" and s.target == "allies":
        head = "保護技能，放在同房間的其他玩家身上"
    else:
        head = f"{skills.KIND_NAMES[s.kind]}技能，{TARGET_TEXT[s.target]}"
    return head + "。" + "".join(f"{need}。" for need in requirements(s))


def shortest(cmd, is_imm):
    """cmd 最短的縮寫（照指令表的順序，打這幾個字就會找到它）；沒有比全名短的是 None。"""
    from . import command_name
    return next((cmd[:n] for n in range(1, len(cmd)) if command_name(cmd[:n], is_imm) == cmd), None)
