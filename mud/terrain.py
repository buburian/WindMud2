"""地形（sector）對玩家的限制、走路的訊息、窒息（照 C 版 move_char，規則在玩家角色手冊「地形」，使用者 2026-11-17 定的）。

- 空中（9）要飛行；要船的水（7）要飛行，或背包裡有船；水底（8）要水中呼吸（blocked()）。
  現在站的房間和要去的房間都算（照 C 版，使用者定的）：飛行在空中時間到了就走不出去，要用 recall 離開。
  空中、水底的房間又是 no_recall 的話會卡住：那是區域設計的問題，程式不擋（使用者說的）。
  只限制玩家，生物不受限制（照 C 版）。旗標用 affects.has_flag()（飛翔術、水中呼吸術，生物區域檔的 affected_by 也算）。
- 在水底、沒有水中呼吸的在線玩家（imm 除外，照 C 版）每 CHOKE_TICKS 窒息，扣 HP 上限的 CHOKE_PCT（choke()）。
- 走路扣 MV 不做（使用者定的）。晚上變暗在 light.py。
"""
from . import affects, combat
from .act import TO_CHAR, TO_ROOM, compose
from .area import BOAT_ITEM_TYPE, AffectFlag, Sector
from .npcs import Npc
from .players import online_players

CHOKE_PCT = 0.10                            # 窒息每次扣 HP 上限的幾成（使用者選的：大約 30 秒會死）
NEED_FLY = "你還沒有到會飛的地步。"           # 擋下來的訊息照 C 版
NEED_BOAT = "很明顯地，你需要有一艘船才能夠去那裡。"
NEED_GILLS = "你要會潛水才能過去那裡。"
CHOKE_SELF = "{C你無法呼吸{x"                 # 窒息（照 C 版的句子，後面接扣多少 combat.damage_tail()；被扣的人亮青，跟燒傷一樣）
CHOKE_ROOM = "$n因窒息而口吐白沫"
WALK_AWAY = "$n朝$t離開。"                    # 原本房間的人看到的（system.move 的預設）
SWIM_AWAY = "$n游向$t方。"                    # 從水裡走到水裡（照 C 版：兩邊都是可游泳的水或水底）
WALK_IN = "$n從$t邊走了過來。"                # 走進去的房間的人看到的
FLY_IN = "$n從$t邊飛了過來。"                 # 有飛行（照 C 版排在游泳前面）
SWIM_IN = "$n從$t邊游了過來。"                # 走進可游泳的水（照 C 版：只看要去的房間，水底不算）
WATER = (Sector.WATER_SWIM, Sector.UNDERWATER)


def blocked(ch, frm, to):
    """ch 能不能從 frm 走到 to：不能就回傳那一句（照 C 版），可以是 None。生物不受限制。

    兩間房都算（照 C 版 move_char）：任何一間是空中就要飛行，是要船的水就要飛行或船，是水底就要水中呼吸。
    """
    if isinstance(ch, Npc):
        return None
    sectors = (frm.sector, to.sector)
    flying = affects.has_flag(ch, AffectFlag.FLYING)
    if Sector.AIR in sectors and not flying:
        return NEED_FLY
    if (Sector.WATER_NOSWIM in sectors and not flying
            and not any(o.item_type == BOAT_ITEM_TYPE for o in ch.carrying)):
        return NEED_BOAT
    if Sector.UNDERWATER in sectors and not affects.has_flag(ch, AffectFlag.GILLS):
        return NEED_GILLS
    return None


def can_go(ch, room, direction):
    """flee 挑出口用：往 direction 走得過去（地形）。對面還沒建立（沒人去過的動態區域）不知道地形，當作走得過去。"""
    from . import zones                     # 坑：zones 繞一圈會 import 到 commands，在函式裡才 import
    to = zones.find_room(room, room.exits[direction])
    return to is None or blocked(ch, room, to) is None


def leave_text(frm, to, leave):
    """原本房間的人看到的那句：照常走路（WALK_AWAY）又是從水裡到水裡就換成游泳的；flee 這種自己給的句子不換。"""
    return SWIM_AWAY if leave == WALK_AWAY and frm.sector in WATER and to.sector in WATER else leave


def arrive_text(ch, to):
    """走進去的房間的人看到的那句：有飛行的是飛過來，走進可游泳的水是游過來，其他是走過來（照 C 版的順序）。"""
    if affects.has_flag(ch, AffectFlag.FLYING):
        return FLY_IN
    return SWIM_IN if to.sector == Sector.WATER_SWIM else WALK_IN


def choke():
    """世界每 CHOKE_TICKS 呼叫一次：在水底、沒有水中呼吸的在線玩家（imm 除外）扣 HP 上限的 CHOKE_PCT。

    跟持續扣血一樣：護盾先吸收、扣到 0 就死（打架中算他正在打的對手打死的）。一次的訊息每人只送一次（affects.Messages）。
    """
    out = affects.Messages()
    for p in list(online_players()):
        if (p.imm or not getattr(p, "panel", None) or p.room.sector != Sector.UNDERWATER
                or affects.has_flag(p, AffectFlag.GILLS)):
            continue
        dmg = p.panel["hp"] * CHOKE_PCT
        taken, broken = affects.absorb(p, dmg)
        p.hp -= dmg - taken
        tail = combat.damage_tail(dmg, taken)
        out.tell(compose(CHOKE_SELF + tail, p, to=TO_CHAR))
        out.tell(compose(CHOKE_ROOM + tail, p, to=TO_ROOM))
        out.tell(affects.broken_messages(p, broken))
        if p.hp <= 0:
            combat.slain(out, p.fighting, p)
    out.flush()
