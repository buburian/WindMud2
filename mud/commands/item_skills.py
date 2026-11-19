"""會放技能的物品（設計文件 §3.8，使用者 2026-11-17 定的；規則在玩家角色手冊「會放技能的物品」）：
quaff 藥水、recite 卷軸、zap 魔杖、brandish 魔棒。

- 物品上寫的是技能的 key（Obj.skills），用一次就照順序各放一次：不扣消耗、沒有冷卻、不用學會（skills.use(..., pay_cost=False)）。
- 物品的 level 是最低使用等級：不夠就不能用、不會用掉（跟穿裝備同一句）。一定成功，沒有 C 版的失敗率。
- 對誰放（使用者定的）：沒寫對象時看技能種類：增益對自己；傷害打架中對對手，沒打架就問要對誰。
  技能本來的規則照算：增益只放玩家、傷害只打生物、安全區不能打（commands.combat.protected）、很暗找不到人。
  每個技能的對象都先檢查過，有一個不行就只說那句、東西不會用掉（使用者定的）。
- 魔杖、魔棒要拿在持握的位置（hold），charges 是剩幾次，用一次少 1，到 0 就碎掉；剩 0 次的用了直接碎掉（照 C 版）。
- 訊息照 C 版（act_obj.c 的 do_quaff、do_recite、do_zap、do_brandish）。
"""
from .. import inventory, light, objects, skills
from ..act import TO_CHAR, TO_ROOM, act
from ..area import POTION_ITEM_TYPE, SCROLL_ITEM_TYPE, STAFF_ITEM_TYPE, WAND_ITEM_TYPE
from ..characters import characters, find_in_room, in_room
from ..npcs import Npc
from .combat import SUMMONED, protected
from .skills import engage

HOLD = "hold"                               # 魔杖、魔棒要拿在這個位置（inventory.SLOTS）
NOT_FOR_MOBS = "{}只能放在玩家身上。"          # 跟 use 一樣
NOT_PLAYERS = "你不可以攻擊玩家。"             # 跟 use 一樣


def first_word(arg):
    words = arg.split()
    return words[0] if words else ""


def too_low(ch, obj):
    """等級不夠（物品的 level 是最低使用等級）：說那句、回傳 True。東西不會用掉。"""
    if ch.level >= obj.level:
        return False
    ch.send(inventory.LEVEL_TOO_LOW.format(obj.level) + "\n")
    return True


def default_target(ch, skill):
    """沒寫對象時（使用者定的）：增益對自己；傷害打架中是對手（還在同一間房），不然是 None（要問）。"""
    if skills.friendly(skill):
        return ch
    victim = ch.fighting
    return victim if victim in characters and victim.room is ch.room else None


def plan(ch, obj, victim, ask):
    """每個技能放給誰：[(技能, 對象)]。victim 是指定的對象（None 是沒寫，照 default_target）；
    有一個不行就說那句、回傳 None（東西不會用掉，使用者定的）。ask 是傷害技能找不到對象時說的。
    """
    pairs = []
    for sid in obj.skills:
        skill = skills.SKILLS.get(sid)
        if skill is None:                   # 存檔裡的技能已經拿掉了：跳過
            continue
        target = victim or default_target(ch, skill)
        if target is None:
            ch.send(ask + "\n")
            return None
        if skill.target == "self" and target is not ch:
            ch.send(skills.SELF_ONLY + "\n")
            return None
        if skills.friendly(skill) and isinstance(target, Npc):
            ch.send(NOT_FOR_MOBS.format(skill.name) + "\n")
            return None
        if not skills.friendly(skill):
            if not isinstance(target, Npc):
                ch.send(NOT_PLAYERS + "\n")
                return None
            if target.master is not None:   # 召喚物（summons.py）
                ch.send(SUMMONED + "\n")
                return None
            if protected(ch, target):        # 安全區：說 C 版那句
                return None
        pairs.append((skill, target))
    return pairs


def cast(ch, pairs):
    """照順序放：傷害技能先開打（跟 use 一樣）。前面的把對象打死、對象離開了，後面的就不放。"""
    for skill, target in pairs:
        if target not in characters or target.room is not ch.room:
            continue
        if not skills.friendly(skill):
            engage(ch, target)
        skills.use(ch, skill, target, pay_cost=False)


def do_quaff(ch, arg):
    """quaff <藥水>：從背包拿出來喝，每個技能都對自己放（照 C 版）。"""
    word = first_word(arg)
    if not word:
        ch.send("你想要服下什麼樣的藥水？\n")
        return
    obj = objects.find(ch.carrying, word)
    if obj is None:
        ch.send("你沒有這種藥水。\n")
        return
    if obj.item_type != POTION_ITEM_TYPE:
        ch.send("你只能服下藥水。\n")
        return
    swallow(ch, obj, "你服下了【$t】。", "$n服下(Quaff)了【$t】。")


def swallow(ch, obj, mine, theirs):
    """藥水（quaff）、藥錠（eat，設計文件 §3.9：藥錠不算食物）：檢查等級、每個技能對自己放，東西用掉。不行就不用掉。"""
    if too_low(ch, obj):
        return
    pairs = plan(ch, obj, ch, "")
    if pairs is None:
        return
    name = objects.short(obj)
    act(mine, ch, t=name, to=TO_CHAR)
    act(theirs, ch, t=name, to=TO_ROOM)
    ch.carrying.remove(obj)
    cast(ch, pairs)


def do_recite(ch, arg):
    """recite <卷軸> [對象]：從背包拿出來唸。沒寫對象：增益對自己，傷害打架中對對手（使用者定的）。"""
    words = arg.split()
    obj = objects.find(ch.carrying, words[0]) if words else None
    if obj is None:
        ch.send("你沒有這種卷軸。\n")
        return
    if obj.item_type != SCROLL_ITEM_TYPE:
        ch.send("你只能朗讀卷軸(Scroll)。\n")
        return
    victim = None
    if len(words) > 1:
        victim = find_in_room(ch, words[1])
        if victim is None:
            ch.send("你找不到你想要閱讀的捲軸。\n")     # 照 C 版的字（對象找不到）
            return
    if too_low(ch, obj):
        return
    pairs = plan(ch, obj, victim, "你想要攻擊誰？")
    if pairs is None:
        return
    name = objects.short(obj)
    act("你朗讀著【$t】。", ch, t=name, to=TO_CHAR)
    act("$n朗讀著(Recite)【$t】。", ch, t=name, to=TO_ROOM)
    ch.carrying.remove(obj)
    cast(ch, pairs)


def held(ch, item_type, nothing, wrong):
    """持握位置的魔杖或魔棒；沒拿、拿的不對就說那句、回傳 None。"""
    obj = ch.equipment.get(HOLD)
    if obj is None:
        ch.send(nothing + "\n")
        return None
    if obj.item_type != item_type:
        ch.send(wrong + "\n")
        return None
    return obj


def used_up(ch, obj, mine, theirs):
    """次數少 1（剩 0 次的也算用了一次），到 0 就碎掉：從身上拿掉，說那兩句。"""
    obj.charges -= 1
    if obj.charges > 0:
        return
    name = objects.short(obj)
    act(mine, ch, t=name, to=TO_CHAR)
    act(theirs, ch, t=name, to=TO_ROOM)
    del ch.equipment[HOLD]
    inventory.changed(ch)


WAND_GONE = ("你的【$t】爆炸成了一堆的碎片。", "$n的【$t】爆炸成了一堆的碎片。")             # 照 C 版
STAFF_GONE = ("【$t】燃燒起來射出陣陣光芒後消失不見了。", "【$t】燃燒起來射出陣陣光芒後消失不見了。")   # 照 C 版（加上【】）


def do_zap(ch, arg):
    """zap [對象]：甩動持握位置的魔杖。沒寫對象：增益對自己，傷害打架中對對手，沒打架就問（使用者定的）。"""
    wand = held(ch, WAND_ITEM_TYPE, "你手上沒有握著任何東西可以拿來甩動。", "你只能夠甩動著魔杖(Wand)。")
    if wand is None:
        return
    word = first_word(arg)
    victim = None
    if word:
        victim = find_in_room(ch, word)
        if victim is None:
            ch.send("你找不到你想甩動的魔杖(Wand)。\n")    # 照 C 版的字（對象找不到）
            return
    if too_low(ch, wand):
        return
    if wand.charges > 0:
        pairs = plan(ch, wand, victim, "你想要甩動些什麼？")
        if pairs is None:
            return
        name, target = objects.short(wand), (pairs[0][1] if pairs else ch)
        if target is ch:
            act("你對著你自己甩動(Zap)【$t】。", ch, t=name, to=TO_CHAR)
            act("$n對著$m自己甩動(Zap)【$t】。", ch, t=name, to=TO_ROOM)
        else:
            act("你對著$N甩動(Zap)【$t】。", ch, target, t=name, to=TO_CHAR)
            act("$n對著$N甩動(Zap)【$t】。", ch, target, t=name, to=TO_ROOM)
        cast(ch, pairs)
    used_up(ch, wand, *WAND_GONE)


def do_brandish(ch, arg):
    """brandish：揮舞持握位置的魔棒，照 C 版放給同房間的人：增益給每個看得到的玩家（包含自己），傷害打每隻看得到的生物。"""
    staff = held(ch, STAFF_ITEM_TYPE, "你手上沒有握著任何東西可以拿來揮舞。", "你只能拿魔棒(Staff)來揮舞。")
    if staff is None:
        return
    if too_low(ch, staff):
        return
    if staff.charges > 0:
        pairs = everyone(ch, staff)
        if pairs is None:
            return
        name = objects.short(staff)
        act("你揮舞著【$t】。", ch, t=name, to=TO_CHAR)
        act("$n揮舞著(Brandish)【$t】。", ch, t=name, to=TO_ROOM)
        cast(ch, pairs)
    used_up(ch, staff, *STAFF_GONE)


def everyone(ch, staff):
    """魔棒放給誰（先把名單整理好再放）：[(技能, 對象)]。傷害技能在安全區就說那句、回傳 None（不會用掉）。"""
    others = [c for c in in_room(ch) if light.visible(ch, c)]
    pairs = []
    for sid in staff.skills:
        skill = skills.SKILLS.get(sid)
        if skill is None:
            continue
        if skill.target == "self":          # 只能放自己的：只放自己
            pairs.append((skill, ch))
            continue
        if skills.friendly(skill):
            pairs += [(skill, c) for c in [ch] + others if not isinstance(c, Npc)]
            continue
        mobs = [c for c in others if isinstance(c, Npc) and c.master is None]     # 召喚物不打
        if mobs and protected(ch, mobs[0]):
            return None
        pairs += [(skill, c) for c in mobs]
    return pairs
