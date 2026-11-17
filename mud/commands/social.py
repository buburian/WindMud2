"""表情動作（socials，照 C 版 interp.c 的 check_social）：資料在 socials.py（socials/socials.json），這裡是做動作。

打的字不是指令時才找動作（commands.run()），所以指令的縮寫優先。規則在玩家角色手冊「表情動作」（使用者 2026-11-17 定的）：
- 沒打名字是 alone；打自己的名字是 self；打別人：同一間房的人或生物是 target，
  不在同一間房的玩家也可以（「遠遠地，」，照 C 版），生物一定要同一間房。
- 對生物做：牠醒著的話 16 次裡 8 次回一樣的動作、4 次給你一巴掌（照 C 版；C 版還有 1 次會開打，使用者選不做）。
- `*動作`：20 級以上的玩家把動作廣播給所有線上的人看，前面加「[動作]」（照 C 版；C 版之後要等 5 秒，我們沒有指令的等待，不做）。
- 睡著只能 snore（照 C 版）；很暗看不到人（找人照 find_in_room，遠的也要看得到房間）。
"""
import random

from .. import light, names, socials
from ..act import TO_CHAR, TO_NOTVICT, TO_ROOM, TO_VICT, act, fill, notify
from ..characters import Position, characters, find_in_room
from ..npcs import Npc
from ..players import online_players

rng = random                                # 生物的反應（測試換掉）
BROADCAST = "*"                             # 打在動作前面就是廣播
BROADCAST_LEVEL = 20                        # 廣播要幾級（照 C 版）
BROADCAST_TAG = "{C[動作] "                 # 廣播的字前面（照 C 版：亮青）
FAR = "遠遠地，"                             # 對不在同一間房的玩家（照 C 版）
NOT_HERE = "他們不在這兒。"                   # 找不到（照 C 版）
NOT_HERE_MOB = "他們不在這裡。"               # 不在同一間房的生物（照 C 版）
SLEEP_SOCIAL = "snore"                      # 睡著也能做的（照 C 版）
REACT_SIDES = 16                            # 生物的反應：骰 0～15（照 C 版 number_bits(4)）
REACT_SAME = range(1, 9)                    # 回一樣的動作
REACT_SLAP = range(9, 13)                   # 給一巴掌（C 版 0 是開打，使用者選不做）
SLAP = ("你給了$N一個大巴掌。", "$n給了你一個大巴掌。", "$n給了$N一個大巴掌。哇，真響!!。")


def social(ch, verb, arg):
    """verb 不是指令時：是動作就做，回傳 True；不是動作（或不能廣播）回傳 False，由呼叫的人說「什麼？」。"""
    from . import REFUSALS                  # 坑：commands 會 import 這裡，在函式裡才 import
    broadcast = verb.startswith(BROADCAST)
    s = socials.find(verb[len(BROADCAST):] if broadcast else verb)
    if s is None or (broadcast and (isinstance(ch, Npc) or ch.level < BROADCAST_LEVEL)):
        return False
    if ch.position < Position.SLEEPING or (ch.position == Position.SLEEPING and s["name"] != SLEEP_SOCIAL):
        ch.send(REFUSALS[ch.position] + "\n")
        return True
    word = arg.split()[0] if arg.split() else ""
    if not word:
        say(ch, None, s["alone"], broadcast)
        return True
    victim = find_in_room(ch, word) or far_away(ch, word)
    if victim is None:
        ch.send(NOT_HERE + "\n")
    elif victim is ch:                      # 對自己：對方就是自己（照 C 版，$M 是自己）
        say(ch, ch, s["self"], broadcast)
    elif broadcast and not isinstance(victim, Npc):
        say(ch, victim, s["target"], broadcast)
    elif victim.room is not ch.room:
        if isinstance(victim, Npc):
            ch.send(NOT_HERE_MOB + "\n")
        else:                               # 遠遠地：只有自己和對方看到（照 C 版）
            send(FAR + s["target"]["you"], ch, victim, TO_CHAR)
            send(FAR + s["target"]["target"], ch, victim, TO_VICT)
    else:
        say(ch, victim, s["target"], False)
        if not isinstance(ch, Npc) and isinstance(victim, Npc) and victim.position > Position.SLEEPING:
            react(victim, ch, s)
    return True


def far_away(ch, word):
    """不在同一間房的角色（照 C 版 get_char_world）：先找線上玩家、再找生物，名字的規則跟找人一樣。
    很暗、看不到房間就找不到（照 C 版 can_see）。找到生物的話 social() 說「他們不在這裡。」（照 C 版）。
    """
    if not light.can_see_room(ch):
        return None
    others = [c for c in characters if c.room is not ch.room]
    ordered = [c for c in others if not isinstance(c, Npc)] + [c for c in others if isinstance(c, Npc)]
    return names.pick(ordered, word, lambda c: c.names())


def say(ch, victim, part, broadcast):
    """送一個動作：part 是 alone（victim 是 None）、self（victim 是自己）或 target。廣播是所有線上的人，不然是同一間房。"""
    if broadcast:
        for p in online_players():
            key = "you" if p is ch else "target" if p is victim and "target" in part else "room"
            text = part[key]
            if text:
                text = fill(BROADCAST_TAG + text + "{x", ch, victim, None, None, p)
                if p is ch:
                    ch.send(text + "\n")
                else:
                    notify(p, text)
        return
    send(part["you"], ch, victim, TO_CHAR)
    if "target" not in part:                # alone、self：同房間的其他人
        send(part["room"], ch, victim, TO_ROOM)
    else:
        send(part["target"], ch, victim, TO_VICT)
        send(part["room"], ch, victim, TO_NOTVICT)


def send(text, ch, victim, to):
    if text:                                # "" 是不送
        act(text, ch, victim, to=to)


def react(npc, player, s):
    """玩家對生物做了動作，生物的反應（照 C 版）：一半回一樣的動作、四分之一給一巴掌，其他沒反應（C 版會開打，使用者選不做）。"""
    roll = rng.randrange(REACT_SIDES)
    if roll in REACT_SAME:
        part = s["target"]
        lines = (part["you"], part["target"], part["room"])
    elif roll in REACT_SLAP:
        lines = SLAP
    else:
        return
    send(lines[1], npc, player, TO_VICT)    # 生物自己那句送了也沒人看
    send(lines[2], npc, player, TO_NOTVICT)


def do_socials(ch, arg):
    """socials：列出全部的動作，一行 6 個、每個 12 格（照 C 版）；比 11 個字長的（congratulation）後面至少空一格，才不會黏在一起。"""
    listed = [s["name"] for s in socials.table]
    if not listed:
        ch.send("現在沒有任何動作。\n")
        return
    rows = ["".join(n.ljust(11) + " " for n in listed[i:i + 6]).rstrip() for i in range(0, len(listed), 6)]
    ch.send("\n".join(rows) + "\n")
