"""系統類指令。每個指令都長 do_xxx(ch, arg)：ch 是下指令的角色，回傳 False 代表要斷線。"""
from ..act import TO_CHAR, TO_ROOM, TO_VICT, act
from ..area import DIRECTIONS, REVERSE, rooms
from ..characters import characters
from ..color import colorize
from ..players import online_players
from ..save import save_player


def do_look(ch, arg):
    if not arg:
        ch.send(look(ch))
        return
    room = rooms[ch.room]
    target = arg.split()[0].lower()
    # 照 C 版的順序：先找房間裡可以細看的東西（名字要整個字一樣），再把它當成方向（n、no、north 都算北）
    for keywords, text in room.extra_descriptions:
        if target in keywords:
            ch.send(block(text))
            return
    direction = next((d for d in DIRECTIONS if d.startswith(target)), None)
    if direction is None:
        ch.send("在這裡找不到你要看的東西。\n")
    elif room.exit_descriptions.get(direction):
        ch.send(block(room.exit_descriptions[direction]))
    else:                                   # 那個方向沒有出口，或出口沒寫描述
        ch.send("那裡沒有什麼特別的東西。\n")


def block(text):
    """區域作者寫的一段文字：轉顏色代碼，最後補上換行。"""
    text = colorize(text)
    return text if text.endswith("\n") else text + "\n"


def look(ch):
    """ch 所在房間的樣子：名稱、出口、描述、同房間的其他角色。登入時也用這個。"""
    room = rooms[ch.room]
    exits = "".join(" {C" + DIRECTIONS[d] for d in DIRECTIONS if d in room.exits) or " 沒有"
    # 房間的文字是區域作者寫的，可以用顏色代碼；角色名字是後面才接上去的，不會被轉
    text = colorize("{G【{Y" + room.name + "{G】{x\n{G【出口：" + exits + "{G】{x\n" + room.description)
    if not text.endswith("\n"):
        text += "\n"
    for c in characters:                    # 同房間的其他角色，玩家和 NPC 都算
        if c is not ch and c.room == ch.room:
            text += f"{c.name}站在這裡。\n"
    return text


def move(ch, direction):
    to = rooms[ch.room].exits.get(direction)
    if to is None:
        ch.send("那裡不能走。\n")
        return
    act("$n朝$t離開。", ch, t=DIRECTIONS[direction], to=TO_ROOM)
    ch.room = to
    act("$n從$t邊走了過來。", ch, t=DIRECTIONS[REVERSE[direction]], to=TO_ROOM)
    ch.send(look(ch))


def walk(direction):
    """做出「往 direction 走」的指令。"""

    def do_walk(ch, arg):
        move(ch, direction)

    return do_walk


do_north = walk("north")
do_east = walk("east")
do_south = walk("south")
do_west = walk("west")
do_up = walk("up")
do_down = walk("down")


def do_chat(ch, arg):
    if not arg:
        ch.send("要說什麼？\n")
    else:
        act("{M你聊天：$t{x", ch, t=arg, to=TO_CHAR)
        for other in online_players():     # chat 是全服頻道，自己走訪在線的玩家，有房間後也不受影響
            if other is not ch:
                act("{M$n 聊天：$t{x", ch, vch=other, t=arg, to=TO_VICT)


def do_tell(ch, arg):
    target, _, msg = arg.partition(" ")
    msg = msg.strip()
    if not target or not msg:
        ch.send("你想要告訴誰些什麼呢？\n")
        return
    victim = next((p for p in online_players() if p.name.lower() == target.lower()), None)
    if victim is None:
        ch.send("沒有找到你想說話的對象。\n")
        return
    tell(ch, victim, msg)


def do_reply(ch, arg):
    victim = ch.reply
    if victim not in characters:            # 沒人 tell 過你，或對方已經離線
        ch.send("找不到你想回答的對象。\n")
        return
    if not arg:
        ch.send("你想回答些什麼呢？\n")
        return
    tell(ch, victim, arg)


def tell(ch, victim, msg):
    """tell 和 reply 共用：雙方各看到一句，對方之後可以用 reply 回你。"""
    act("{G你告訴$N：$t{x", ch, vch=victim, t=msg, to=TO_CHAR)
    act("{G$n告訴你：$t{x", ch, vch=victim, t=msg, to=TO_VICT)
    victim.reply = ch


def do_quit(ch, arg):
    save_player(ch.name)
    ch.send("再見。\n")
    # 移出角色名單、關連線都在 server.handle() 的 finally，這裡不重複做
    return False
