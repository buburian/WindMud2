"""門和容器的指令：open、close、lock、unlock。規則在區域製作手冊「門」「容器旗標」，檢查的順序照 C 版 act_move.c。

撬（pick）、撞（bash）要等技能做好再做。門成功時這一邊和對面那一邊一起變（doors.set_state()）；容器改它自己的 container 旗標。
"""
from .. import doors, objects
from ..act import TO_CHAR, TO_ROOM, act
from ..area import DIRECTIONS, ContainerFlag, DoorState


def has_key(ch, vnum):
    """ch 身上（背包或穿著的）有沒有遊戲號碼 vnum 的物品（鑰匙）。"""
    return any(o.vnum == vnum for o in ch.carrying + list(ch.equipment.values()))


def find_door(ch, arg):
    """玩家指定的門或東西，照這個順序（使用者選的）：

    1. 門的名字（整個字一樣，英文不分大小寫）。
    2. 方向（n、no、north 都算北）：所以 open n 一定是北邊的門。
    3. 東西：地上、背包、身上的（objects.find 的規則：開頭就行、2.box）。
    回傳方向（字串）或物品（objects.Obj）；找不到就告訴 ch 為什麼，回傳 None。
    """
    word = arg.split()[0]
    for d in DIRECTIONS:
        door = ch.room.doors.get(d)
        if door is not None and word.lower() in (k.lower() for k in door.keywords):
            return d
    direction = next((d for d in DIRECTIONS if d.startswith(word.lower())), None)
    if direction is not None:
        if direction not in ch.room.exits:
            ch.send(f"{DIRECTIONS[direction]}方沒有出口。\n")
        elif direction not in ch.room.doors:
            ch.send(f"{DIRECTIONS[direction]}方的出口沒有門。\n")
        else:
            return direction
        return None
    obj = objects.find(ch.room.contents + ch.carrying + list(ch.equipment.values()), word)
    if obj is None:
        act("這裡沒有叫做「$t」的門。", ch, t=word, to=TO_CHAR)    # 玩家打的字用 $t 帶進去
    return obj


def done_obj(ch, mine, theirs, obj):
    """容器成功了：自己看到 mine，同房間的人看到 theirs（$t 是物品的名字）。"""
    act(mine, ch, t=objects.short(obj), to=TO_CHAR)
    act(theirs, ch, t=objects.short(obj), to=TO_ROOM)


def has(obj, flag):
    return flag in obj.container


def done(ch, fmt, door):
    """成功了：自己看到「你打開了木門。」，同房間的人看到「Ming打開了木門。」"""
    act(fmt, ch, t=door.name, to=TO_CHAR)
    act(fmt, ch, t=door.name, to=TO_ROOM)


def do_open(ch, arg):
    if not arg:
        ch.send("你想打開什麼呢？\n")
        return
    d = find_door(ch, arg)
    if d is None:
        return
    if isinstance(d, objects.Obj):
        open_container(ch, d)
        return
    door = ch.room.doors[d]
    if not door.closed:
        ch.send("它已經是開著的。\n")
    elif door.locked:
        ch.send("它被鎖住了。\n")
    else:
        to, back = doors.set_state(ch.room, d, DoorState.OPEN)
        done(ch, "$n打開了$t。", door)
        doors.tell_other_side(d, to, back, opened=True)


def do_close(ch, arg):
    if not arg:
        ch.send("你想關上什麼呢？\n")
        return
    d = find_door(ch, arg)
    if d is None:
        return
    if isinstance(d, objects.Obj):
        close_container(ch, d)
        return
    door = ch.room.doors[d]
    if door.closed:
        ch.send("它已經關起來了。\n")
    else:
        to, back = doors.set_state(ch.room, d, DoorState.CLOSED)
        done(ch, "$n關上了$t。", door)
        doors.tell_other_side(d, to, back, opened=False)


def do_lock(ch, arg):
    if not arg:
        ch.send("你想鎖住什麼呢？\n")
        return
    d = find_door(ch, arg)
    if d is None:
        return
    if isinstance(d, objects.Obj):
        lock_container(ch, d)
        return
    door = ch.room.doors[d]
    if not door.closed:
        ch.send("要先關起來才能上鎖。\n")
    elif door.key is None:
        ch.send("它沒有辦法鎖起來。\n")
    elif not has_key(ch, door.key):
        ch.send("你沒有鑰匙，怎麼上鎖呢？\n")
    elif door.locked:
        ch.send("它已經被鎖起來了。\n")
    else:
        doors.set_state(ch.room, d, DoorState.LOCKED)       # 對面不會知道（照 C 版）
        done(ch, "$n鎖上了$t。", door)


def do_unlock(ch, arg):
    if not arg:
        ch.send("你想打開哪裡的鎖呢？\n")
        return
    d = find_door(ch, arg)
    if d is None:
        return
    if isinstance(d, objects.Obj):
        unlock_container(ch, d)
        return
    door = ch.room.doors[d]
    if not door.closed:
        ch.send("它沒關起來。\n")
    elif door.key is None:
        ch.send("沒辦法打開這個鎖。\n")
    elif not has_key(ch, door.key):
        ch.send("你沒有這個門的鑰匙。\n")
    elif not door.locked:
        ch.send("它沒有上鎖。\n")
    else:
        doors.set_state(ch.room, d, DoorState.CLOSED)       # 對面不會知道（照 C 版）
        done(ch, "$n打開了$t的鎖。", door)


# ---- 容器（照 C 版 act_move.c 的順序和訊息；屍體不是容器：它沒有 container 旗標，一直開著） ----

def open_container(ch, obj):
    if obj.container is None:
        ch.send("這不是個容器。\n")
    elif not has(obj, ContainerFlag.CLOSED):
        ch.send("它已經打開了。\n")
    elif not has(obj, ContainerFlag.CLOSEABLE):
        ch.send("你不能這樣作。\n")
    elif has(obj, ContainerFlag.LOCKED):
        ch.send("它被鎖住了。\n")
    elif has(obj, ContainerFlag.SEALABLE) and obj.seal > 0:
        ch.send("它被封印住了。\n")                     # 封印、解開的指令還沒做
    else:
        obj.container &= ~ContainerFlag.CLOSED
        done_obj(ch, "你打開了【$t】。", "$n打開了【$t】。", obj)


def close_container(ch, obj):
    if obj.container is None:
        ch.send("這不是容器。\n")
    elif has(obj, ContainerFlag.CLOSED):
        ch.send("它已經關起來了。\n")
    elif not has(obj, ContainerFlag.CLOSEABLE):
        ch.send("你不能這樣作。\n")
    else:
        obj.container |= ContainerFlag.CLOSED
        done_obj(ch, "你關起了【$t】。", "$n關起了【$t】。", obj)


def lock_container(ch, obj):
    if obj.container is None:
        ch.send("這不是容器。\n")
    elif not has(obj, ContainerFlag.CLOSED):
        ch.send("它沒有關起來，怎麼上鎖？\n")
    elif obj.key is None:
        ch.send("沒辦法鎖起來。\n")
    elif not has_key(ch, obj.key):
        ch.send("你沒有鑰匙，所以不能上鎖。\n")
    elif has(obj, ContainerFlag.LOCKED):
        ch.send("它被已經鎖起來了。\n")
    else:
        obj.container |= ContainerFlag.LOCKED
        done_obj(ch, "【清脆的喀啦一聲】", "$n鎖上了【$t】。", obj)


def unlock_container(ch, obj):
    if obj.container is None:
        ch.send("那不是容器。\n")
    elif not has(obj, ContainerFlag.CLOSED):
        ch.send("它沒關起來。\n")
    elif obj.key is None:
        ch.send("沒辦法打開這個鎖。\n")
    elif not has_key(ch, obj.key):
        ch.send("你沒有這個鎖的鑰匙。\n")
    elif not has(obj, ContainerFlag.LOCKED):
        ch.send("它的鎖已被打開了。\n")
    else:
        obj.container &= ~ContainerFlag.LOCKED
        done_obj(ch, "【清脆的喀啦一聲】", "$n打開【$t】的鎖。", obj)
