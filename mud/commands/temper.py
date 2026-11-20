"""use 淬火石 <裝備>（也可以打 use temper <裝備>）：淬火身上穿著的一件裝備（設計文件 §3.11，規則和掉落在 temper.py）。

第一次打先預覽（會變成幾級橘色、屬性），再打一次同樣的指令才用掉一顆（用掉不能回復，跟換職業一樣說兩次）。
中間等級變了、換了別件、裝備變了或脫掉，就重新預覽。打架中不能用。訊息是我們定的（mud_design 說的「你定」）。
"""
from .. import equipment, inventory, objects, temper
from ..act import TO_CHAR, act
from . import items

FIGHTING = "打架中不能用淬火石。"
NONE_LEFT = "你沒有淬火石。"
WHICH = "要淬火哪一件裝備？"
NOT_WORN = "你身上沒有穿這樣東西。"
CANNOT = "【$t】不能淬火。"
TOO_HIGH = "【$t】的等級比你高，不能淬火。"
ALREADY = "【$t】已經是你這個等級的橘色了。"
PREVIEW = "【$t】會變成 $T。確定的話再打一次。"
DONE = "你用掉一顆淬火石，【$t】變成 $T 了。"


def use(ch, words):
    """use 淬火石 後面的字：words 是 [裝備的名字, …]。"""
    if ch.fighting is not None:
        ch.send(FIGHTING + "\n")
        return
    if getattr(ch, "temper_stones", 0) < 1:
        ch.send(NONE_LEFT + "\n")
        return
    if not words:
        ch.send(WHICH + "\n")
        return
    obj = objects.find(list(ch.equipment.values()), words[0])
    if obj is None:
        ch.send(NOT_WORN + "\n")
        return
    name = objects.short(obj)
    if obj.level > ch.level:
        act(TOO_HIGH, ch, t=name, to=TO_CHAR)
        return
    if obj.level == ch.level and obj.color == equipment.TEMPER_COLOR:
        act(ALREADY, ch, t=name, to=TO_CHAR)
        return
    try:
        affects, _base = temper.result(obj, ch.level)
    except ValueError:
        act(CANNOT, ch, t=name, to=TO_CHAR)
        return
    after = f"{ch.level} 級{equipment.COLOR_NAMES[equipment.TEMPER_COLOR]}：" + "、".join(
        f"{equipment.STAT_NAMES[apply.name.lower()]} {n:+d}" for apply, n in affects)
    seen = (obj, ch.level, obj.level, obj.color, tuple(obj.affects))      # 預覽的那一件、那時的樣子
    if ch.temper_pending != seen:
        ch.temper_pending = seen
        act(PREVIEW, ch, t=name, T=after, to=TO_CHAR)
        return
    ch.temper_pending = None
    ch.temper_stones -= 1
    temper.apply(obj, ch.level)
    inventory.changed(ch)                   # 屬性從頭算（HP、MP、MV 夾在新上限）
    act(DONE, ch, t=objects.short(obj), T=after, to=TO_CHAR)
    items.keep(ch)                          # 用掉的淬火石、換好的裝備馬上存
