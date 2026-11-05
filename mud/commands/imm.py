"""管理員（imm）的指令：只有存檔 imm 是 true 的玩家找得到（commands.find 的 is_imm）。

不是 imm 打這些指令，跟打不存在的指令一樣是「什麼？」（照 C 版）。
"""
import logging
from collections import Counter

from .. import stats
from ..act import notify
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
