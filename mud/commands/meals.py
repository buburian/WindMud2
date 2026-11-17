"""吃喝的指令：eat、drink、fill（設計文件 §3.9，使用者 2026-11-17 定的；規則在玩家角色手冊「吃喝」）。效果在 meals.py。

- 不會餓、不會渴。吃喝會自動坐下（站著的變成休息），打架中不能吃喝；睡著不能（指令表的最低姿勢 RESTING）。
- 一次一口：食物 Obj.bites 少 1、到 0 不見；液體容器 Obj.amount 少 1、0 是空的；噴泉喝不完。一吃一喝就用掉。
- 吃喝完 meals.start()：坐滿 10 秒才有效果（buff，或回得快一倍）。
- 藥錠不算食物（照 §3.8）：eat 藥錠馬上放技能，不用坐，打架中也能吃（item_skills.swallow）。
- fill：在噴泉旁裝滿液體容器，液體換成噴泉的；裝著別種液體要先喝完（照 C 版）。
- 訊息照 C 版（act_obj.c 的 do_eat、do_drink、do_fill）。
"""
from .. import light, meals, objects
from ..act import TO_CHAR, TO_ROOM, act
from ..area import DRINK_CON_ITEM_TYPE, FOOD_ITEM_TYPE, FOUNTAIN_ITEM_TYPE, LIQUIDS, PILL_ITEM_TYPE
from ..characters import Position
from . import item_skills

FIGHTING = "你正處於戰鬥狀態之中了!!"           # 跟 rest 一樣（打架中不能坐下）
WATER = 0                                   # 液體種類表沒有的當清水


def first_word(arg):
    words = arg.split()
    return words[0] if words else ""


def sit_down(ch):
    """吃喝前先坐下（跟 rest 一樣的句子）。打架中不能吃喝：說那句、回傳 False。休息中的不用再坐。"""
    if ch.fighting is not None or ch.position == Position.FIGHTING:
        ch.send(FIGHTING + "\n")
        return False
    if ch.position == Position.STANDING:
        ch.position = Position.RESTING
        ch.send("你坐下來休息。\n")
        act("$n坐下來休息。", ch, to=TO_ROOM)
    return True


def liquid(obj):
    """(液體的名字, 喝了的 buff 技能)。"""
    return LIQUIDS.get(obj.liquid, LIQUIDS[WATER])


def fountain_here(ch):
    """房間地上的噴泉（很暗看不到就沒有）。"""
    return next((o for o in light.floor(ch) if o.item_type == FOUNTAIN_ITEM_TYPE), None)


def do_eat(ch, arg):
    """eat <食物或藥錠>：只吃背包裡的（照 C 版）。"""
    word = first_word(arg)
    if not word:
        ch.send("你想要吃些什麼呢？\n")
        return
    obj = objects.find(ch.carrying, word)
    if obj is None:
        ch.send("你沒有這個東西。\n")
        return
    if obj.item_type == PILL_ITEM_TYPE:
        item_skills.swallow(ch, obj, "你吃下了【$t】。", "$n吃下了【$t】。")
        return
    if obj.item_type != FOOD_ITEM_TYPE:
        ch.send("這個東西是不能夠吃的。\n")
        return
    if not sit_down(ch):
        return
    name = objects.short(obj)
    act("你吃下了【$t】。", ch, t=name, to=TO_CHAR)
    act("$n吃下了【$t】。", ch, t=name, to=TO_ROOM)
    obj.bites = (obj.bites or 1) - 1
    if obj.bites <= 0:
        ch.carrying.remove(obj)
    meals.start(ch, meals.EAT, obj.buff or "")


def do_drink(ch, arg):
    """drink [容器或噴泉]：沒打東西是喝房間的噴泉。找背包、身上、地上（照 C 版 get_obj_here）。"""
    word = first_word(arg)
    if not word:
        obj = fountain_here(ch)
        if obj is None:
            ch.send("你想喝些什麼？\n")
            return
    else:
        obj = objects.find(ch.carrying + list(ch.equipment.values()) + light.floor(ch), word)
        if obj is None:
            ch.send("你找不到它。\n")
            return
    if obj.item_type not in (DRINK_CON_ITEM_TYPE, FOUNTAIN_ITEM_TYPE):
        ch.send("你沒有辦法喝它。\n")
        return
    if obj.item_type == DRINK_CON_ITEM_TYPE and not obj.amount:
        ch.send("它已經空了。\n")
        return
    if not sit_down(ch):
        return
    name, (drink, buff) = objects.short(obj), liquid(obj)
    if obj.item_type == FOUNTAIN_ITEM_TYPE:        # 噴泉喝不完
        act("你從【$t】裡喝$T，止渴了。", ch, t=name, T=drink, to=TO_CHAR)
        act("$n從【$t】裡喝$T。", ch, t=name, T=drink, to=TO_ROOM)
    else:
        act("你從【$t】中喝了點【$T】。", ch, t=name, T=drink, to=TO_CHAR)
        act("$n從【$t】中喝了點【$T】。", ch, t=name, T=drink, to=TO_ROOM)
        obj.amount -= 1
    meals.start(ch, meals.DRINK, buff)


def do_fill(ch, arg):
    """fill <容器>：在噴泉旁把背包裡的液體容器裝滿，液體換成噴泉的（照 C 版的檢查順序）。"""
    word = first_word(arg)
    if not word:
        ch.send("你想拿什麼容器來裝水？\n")
        return
    obj = objects.find(ch.carrying, word)
    if obj is None:
        ch.send("你沒有這樣東西。\n")
        return
    fountain = fountain_here(ch)
    if fountain is None:
        ch.send("這裡沒有泉水!!\n")
        return
    if obj.item_type != DRINK_CON_ITEM_TYPE:
        ch.send("這個東西不是盛裝液體的容器。\n")
        return
    if obj.amount and obj.liquid != fountain.liquid:
        ch.send("這個容器已經裝了其他的液體。\n")
        return
    if obj.amount >= obj.capacity:
        ch.send("你的容器已經裝滿了。\n")
        return
    obj.liquid, obj.amount = fountain.liquid, obj.capacity
    act("你把【$t】灌滿了$T。", ch, t=objects.short(obj), T=liquid(obj)[0], to=TO_CHAR)
