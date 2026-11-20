"""enter：走進傳送門（使用者 2026-11-20 定的，規則在玩家角色手冊「副本和傳送門」）。

傳送門是物品種類 21（area.PORTAL_ITEM_TYPE），values 第 1 個是目的地的房間號碼（objects.portal_target()）。
- 目的地在現在這一份區域物件裡：就是那間（副本裡面的傳送門）。
- 目的地在副本：進到自己那一份（zones.instance(檔名, 名字)；組隊還沒做，一個人一份）。生物不進副本。
- 其他（世界、動態區域）：照走路找房間（zones.room_at，還沒建立的動態區域會建立）。
到了跟 recall 一樣：換區域的外框 ＋ 房間（system.arrival）、腳本的 on_enter(actor, nil)。
"""
import logging

from .. import light, objects, scripts, zones
from ..act import TO_CHAR, TO_ROOM, act
from ..area import PORTAL_ITEM_TYPE
from ..characters import arrive
from ..npcs import Npc
from . import system

log = logging.getLogger(__name__)

NOWHERE = "這裡沒有可以進去的地方。"
NOT_PORTAL = "你沒辦法走進【$t】。"
ENTER_SELF = "你走進了【$t】。"
ENTER_ROOM = "$n走進了【$t】。"
ENTER_ARRIVE = "$n從【$t】走了出來。"


def do_enter(ch, arg):
    """enter [名字]：沒打名字是這間房地上的第一個傳送門，打了名字照 get 的找法找地上的東西（很暗看不到地上的就找不到）。
    最低姿勢 STANDING（指令表）：打架中、休息、睡覺不能用，跟走路一樣。"""
    floor = light.floor(ch)
    words = arg.split()
    if words:
        portal = objects.find(floor, words[0])
    else:
        portal = next((o for o in floor if o.item_type == PORTAL_ITEM_TYPE), None)
    if portal is None:
        ch.send(NOWHERE + "\n")
        return
    name = objects.short(portal)
    if portal.item_type != PORTAL_ITEM_TYPE:
        act(NOT_PORTAL, ch, t=name, to=TO_CHAR)
        return
    to = destination(ch, objects.portal_target(portal))
    if to is None:                          # 開機檢查過目的地存在；生物不進副本
        if not isinstance(ch, Npc):
            log.warning(f"{ch.name} enter 傳送門 {portal.vnum}：目的地 {objects.portal_target(portal)} 找不到")
        ch.send(NOWHERE + "\n")
        return
    act(ENTER_SELF, ch, t=name, to=TO_CHAR)
    act(ENTER_ROOM, ch, t=name, to=TO_ROOM)
    before, ch.room = ch.room, to
    arrive(ch)
    act(ENTER_ARRIVE, ch, t=name, to=TO_ROOM)
    ch.send(system.arrival(ch, before))
    scripts.fire(to, "on_enter", ch, ch, None)


def destination(ch, vnum):
    """傳送門通到的房間（見最上面的說明）；找不到是 None。"""
    if vnum is None:
        return None
    if vnum in ch.room.zone.rooms:
        return ch.room.zone.rooms[vnum]
    name = zones.instance_rooms.get(vnum)
    if name is not None:
        return None if isinstance(ch, Npc) else zones.instance(name, ch.name).rooms.get(vnum)
    return zones.room_at(ch.room, vnum)
