"""門的指令：open、close、lock、unlock。規則在區域製作手冊「門」，檢查的順序照 C 版 act_move.c。

撬（pick）、撞（bash）要等技能做好再做。成功時這一邊和對面那一邊一起變（doors.set_state()）。
"""
from .. import doors
from ..act import TO_CHAR, TO_ROOM, act
from ..area import DIRECTIONS, REVERSE, DoorState


def has_key(ch, vnum):
    """ch 身上有沒有遊戲號碼 vnum 的鑰匙。物品還沒做，所以現在沒有人有鑰匙。"""
    return False


def find_door(ch, arg):
    """玩家指定的門：先找門的名字（整個字一樣，英文不分大小寫），再當成方向（n、no、north 都算北）。

    回傳方向；找不到就告訴 ch 為什麼，回傳 None。
    """
    word = arg.split()[0]
    for d in DIRECTIONS:
        door = ch.room.doors.get(d)
        if door is not None and word.lower() in (k.lower() for k in door.keywords):
            return d
    direction = next((d for d in DIRECTIONS if d.startswith(word.lower())), None)
    if direction is None:
        act("這裡沒有叫做「$t」的門。", ch, t=word, to=TO_CHAR)    # 玩家打的字用 $t 帶進去
    elif direction not in ch.room.exits:
        ch.send(f"{DIRECTIONS[direction]}方沒有出口。\n")
    elif direction not in ch.room.doors:
        ch.send(f"{DIRECTIONS[direction]}方的出口沒有門。\n")
    else:
        return direction
    return None


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
    door = ch.room.doors[d]
    if not door.closed:
        ch.send("它已經是開著的。\n")
    elif door.locked:
        ch.send("它被鎖住了。\n")
    else:
        to, back = doors.set_state(ch.room, d, DoorState.OPEN)
        done(ch, "$n打開了$t。", door)
        if back is not None:
            doors.tell_room(to, f"{DIRECTIONS[REVERSE[d]]}方的{back.name}被打開了。")


def do_close(ch, arg):
    if not arg:
        ch.send("你想關上什麼呢？\n")
        return
    d = find_door(ch, arg)
    if d is None:
        return
    door = ch.room.doors[d]
    if door.closed:
        ch.send("它已經關起來了。\n")
    else:
        to, back = doors.set_state(ch.room, d, DoorState.CLOSED)
        done(ch, "$n關上了$t。", door)
        if back is not None:
            doors.tell_room(to, f"{DIRECTIONS[REVERSE[d]]}方的{back.name}被關起來了。")


def do_lock(ch, arg):
    if not arg:
        ch.send("你想鎖住什麼呢？\n")
        return
    d = find_door(ch, arg)
    if d is None:
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
