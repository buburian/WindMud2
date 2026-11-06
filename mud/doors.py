"""門的共用動作：找門的對面、兩邊一起設定、告訴對面的人。指令（commands/doors.py）和重置 D（resets.py）都用這裡。

門兩邊都要寫（check_files() 會查），兩邊各是一個 area.Door；開、關、鎖的時候兩邊一起變（照 C 版）。
"""
from .act import notify
from .area import DIRECTIONS, REVERSE
from .characters import Position, characters


def other_side(room, direction):
    """room 往 direction 那扇門的對面：(對面的房間, 往回的門)。

    對面還沒建立（沒人去過的動態區域）、往回的出口沒指回 room、或往回的出口沒有門，就是 (None, None)。
    坑：zones 會 import resets、resets 會 import 這裡，所以 zones 要在函式裡才 import，不然開機時繞成一圈。
    """
    from . import zones
    to = zones.find_room(room, room.exits[direction])
    back = REVERSE[direction]
    if to is None or to.exits.get(back) != room.vnum or back not in to.doors:
        return None, None
    return to, to.doors[back]


def set_state(room, direction, state):
    """把 room 往 direction 的門和對面那一邊一起設成 state（area.DoorState）。回傳 other_side() 的結果，給要通知對面的人用。"""
    room.doors[direction].set(state)
    to, back = other_side(room, direction)
    if back is not None:
        back.set(state)
    return to, back


def tell_other_side(direction, to, back, opened):
    """門被打開、關上以後，對面的人看到「南方的木門被打開了。」（玩家的 open、close 和腳本的 room:door 共用）。

    to、back 是 set_state() 回傳的對面；沒有對面就什麼都不做。上鎖、開鎖對面不知道（照 C 版），不要呼叫它。
    """
    if back is not None:
        tell_room(to, f"{DIRECTIONS[REVERSE[direction]]}方的{back.name}被{'打開' if opened else '關起來'}了。")


def tell_room(room, text):
    """門的對面發生的事（被打開、關上，之後還有被撞開）：room 裡醒著、看得見的人收到 text。

    看得見：房間不暗，或暗但有光源（room.dark()）。
    """
    if room.dark():
        return
    for c in characters:
        if c.room is room and c.position > Position.SLEEPING:
            notify(c, text)
