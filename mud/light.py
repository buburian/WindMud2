"""光源和黑暗（照 C 版 room_is_dark、can_see，規則在玩家角色手冊「黑暗和光源」，使用者 2026-11-17 定的：照 C 版全部擋）。

很暗的房間：看不到房間（look 只有一句）、找不到別人（characters.find_in_room）、撿不到地上的東西（floor()）、
同房間的人的名字變「某人」（act.fill）、看不到誰走進來。自己的背包、身上的東西照樣看得到（C 版連這些都看不到，不做）。
暗處也看得到的（night_vision）：imm、精靈（種族技能「夜視」）、生物（簡化：C 版只有出生在暗房的生物有夜視）。

照明用具（物品種類 1）一定穿在光源的位置；Obj.hours 是還能亮幾小時（0 燒完了、負數永遠不熄），
玩家身上的每遊戲小時（HOUR_TICKS）少 1（burn()），地上的不燒。

坑：act 會用到這裡，這裡要用 weather（weather 又 import act），所以 act、characters 在函式裡才 import 這個模組。
"""
from . import stealth, weather
from .act import TO_ROOM, gathering, notify, act
from .area import LIGHT_ITEM_TYPE, RoomFlag, Sector
from .characters import characters, in_room
from .players import online_players
from .stats import Race

DARK_TEXT = "這裡黑漆漆的一片，拿個照明用具吧。"     # look 看到的（照 C 版）
EYES_TEXT = "你看到一雙煥發著紅光的雙眼。"          # 暗處有夜視的人（照 C 版）
BURNT_OUT = "【$t】燃燒殆盡了。"                    # 照明用具燒完（照 C 版：自己和同房間的人都是這句）
SOMEONE = "某人"                                    # 看不到的人的名字（照 C 版 PERS）
BRIGHT_SECTORS = (Sector.INSIDE, Sector.CITY)       # 晚上也不會暗的地形（照 C 版）
NIGHT = (weather.Sunlight.SET, weather.Sunlight.DARK)
LIGHT_SLOT = "light"                                # 照明用具穿的位置（inventory.SLOTS）


def lit(obj):
    """obj 是亮著的照明用具：還有時數（0 是燒完了，負數永遠不熄）。"""
    return obj.item_type == LIGHT_ITEM_TYPE and obj.hours != 0


def dark(room):
    """room 很暗（照 C 版 room_is_dark）：有亮著的光源就不暗；有 DARK 旗標就暗；室內、城市不暗；日落、晚上就暗。

    光源：房間裡有人在光源位置拿著亮的照明用具，或地上有亮的照明用具（背包裡的不算）。
    act 每個收訊息的人都會問一次：先看旗標、地形、日夜，房間本來會暗才去找光源（結果跟 C 版的順序一樣）。
    沒有旗標、地形的房間（測試直接拿 object() 當房間）當作室內、不暗。
    """
    flags, sector = getattr(room, "room_flags", 0), getattr(room, "sector", Sector.INSIDE)
    if RoomFlag.DARK not in RoomFlag(flags) and (sector in BRIGHT_SECTORS or weather.current.sunlight not in NIGHT):
        return False
    return not lighted(room)


def lighted(room):
    """room 裡有亮著的光源：地上的，或有人穿在光源位置的。"""
    if any(lit(o) for o in room.contents):
        return True
    return any((o := c.equipment.get(LIGHT_SLOT)) is not None and lit(o) for c in characters if c.room is room)


def night_vision(ch):
    """ch 在暗處也看得到：imm、精靈（種族技能夜視）、生物（簡化成生物都看得到）。"""
    from .npcs import Npc                   # 坑：npcs 會用到 act，在函式裡才 import
    return isinstance(ch, Npc) or getattr(ch, "imm", False) or getattr(ch, "race", None) == Race.ELF


def can_see_room(ch):
    """ch 看得到他所在的房間：房間不暗，或他有夜視。"""
    return night_vision(ch) or not dark(ch.room)


def visible(reader, ch):
    """reader 看不看得到 ch（act 的名字、找人、look 列出來、看誰走進來）：自己看得到；不在同一間房（chat、tell）也照樣看得到名字。
    同一間房：看得到房間（不暗或有夜視），而且 ch 沒有隱形、藏匿起來（stealth.unseen()）。
    """
    return reader is ch or reader.room is not ch.room or (can_see_room(reader) and not stealth.unseen(reader, ch))


def floor(ch):
    """ch 看得到的地上的東西：看不到房間就是空的（撿東西、look in、開關容器找地上的都用它）。"""
    return ch.room.contents if can_see_room(ch) else []


def darkness(ch):
    """看不到房間時 look 的畫面：那一句，房間裡每個有夜視的玩家再加一雙紅眼睛（照 C 版；生物不算）。"""
    from .npcs import Npc
    eyes = [EYES_TEXT for c in in_room(ch) if not isinstance(c, Npc) and getattr(c, "race", None) == Race.ELF]
    return "\n".join([DARK_TEXT] + eyes) + "\n"


def burn():
    """世界每 HOUR_TICKS（遊戲裡 1 小時）呼叫一次（照 C 版 char_update）：在線玩家（imm 除外）光源位置上的照明用具少 1 小時，
    到 0 燒完：自己和同房間的人看到「【火把】燃燒殆盡了。」，東西不見。負數永遠不熄；地上的不燒。
    """
    from . import inventory, objects
    with gathering():                       # 旁邊的人一個 prompt
        for p in online_players():
            obj = p.equipment.get(LIGHT_SLOT)
            if p.imm or obj is None or obj.item_type != LIGHT_ITEM_TYPE or not obj.hours or obj.hours < 0:
                continue
            obj.hours -= 1
            if obj.hours:
                continue
            del p.equipment[LIGHT_SLOT]
            name = objects.short(obj)
            notify(p, BURNT_OUT.replace("$t", name))
            act(BURNT_OUT, p, t=name, to=TO_ROOM)
            inventory.changed(p)
