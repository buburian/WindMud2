"""管理員（imm）的指令：只有存檔 imm 是 true 的玩家找得到（commands.find 的 is_imm）。

不是 imm 打這些指令，跟打不存在的指令一樣是「什麼？」（照 C 版）。
"""
import logging
from collections import Counter

from .. import death, stats
from ..act import TO_CHAR, TO_NOTVICT, act, notify
from ..characters import find_in_room
from ..npcs import Npc
from ..players import online_players

log = logging.getLogger(__name__)


def do_advance(ch, arg):
    """advance <名字> <等級>：把在線上的玩家升到（或降到）那個等級。"""
    name, _, level = arg.partition(" ")
    level = level.strip()
    if not name or not level:
        ch.send("用法：advance <名字> <等級>\n")
        return
    victim = next((p for p in online_players() if p.name.lower() == name.lower()), None)
    if victim is None:
        ch.send("沒有找到這個玩家。\n")
        return
    if not victim.panel:                    # 沒有屬性（測試直接建的玩家）
        ch.send("這個玩家沒有屬性，不能改等級。\n")
        return
    if not level.isdigit() or not 1 <= int(level) <= stats.MAX_LEVEL:
        ch.send(f"等級要是 1～{stats.MAX_LEVEL}。\n")
        return
    level, old = int(level), victim.level
    if level == old:
        ch.send(f"{victim.name} 已經是 {level} 級了。\n")
        return
    taken = Counter(stats.set_level(victim, level))
    victim.exp = 0.0                        # 這一級的經驗從 0 開始（不然降級後可能已經超過需求）
    log.info(f"{ch.name} 把 {victim.name} 從 {old} 級改成 {level} 級")
    if level > old:
        msg = f"你升到 {level} 級了！多了 {level - old} 點主屬性點數，用 train 分配。"
    else:
        msg = f"你降到 {level} 級了。"
        if taken:
            names = stats.STAT_NAMES
            msg += "扣回的主屬性：" + "、".join(f"{names[k]} -{taken[k]}" for k in stats.PRIMARY_KEYS if taken[k]) + "。"
    if victim is ch:
        ch.send(msg + "\n")
        return
    ch.send(f"{victim.name} {'升' if level > old else '降'}到 {level} 級了。\n")
    notify(victim, msg)


def do_slay(ch, arg):
    """slay <名字>：直接殺死同房間的生物（照 C 版），原地留下屍體。玩家的死亡還沒做，不能殺玩家。"""
    words = arg.split()
    if not words:
        ch.send("你想要屠殺(Slay)誰？\n")
        return
    victim = find_in_room(ch, words[0])
    if victim is None:
        ch.send("找不到你想要屠殺的人。\n")
        return
    if victim is ch:
        ch.send("屠殺(Slay)無法對自己使用。\n")
        return
    if not isinstance(victim, Npc):
        ch.send("玩家的死亡還沒做，現在只能屠殺生物。\n")
        return
    act("你相當殘酷地屠殺(Slay)$N，$E變成一堆的肉塊與血水!!", ch, victim, to=TO_CHAR)
    act("$n相當殘酷地屠殺(Slay)$N，$E變成一堆的肉塊與血水!!", ch, victim, to=TO_NOTVICT)
    log.info(f"{ch.name} 屠殺了 {victim.name}（房間 {victim.room.vnum}）")
    death.die(victim)
