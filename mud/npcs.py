"""NPC（生物）：沒有連線的角色。區域檔的生物由 spawn() 做出來（resets.py 的 M）。"""
from . import stats
from .area import CHANCE_MAX, ActFlag, MobTier, parse_flags
from .characters import Character, Position, characters


class Npc(Character):
    """NPC。區域檔的生物用 spawn() 做；Npc(name, sex, room) 直接建的（測試）沒有區域檔的資料。"""

    def __init__(self, name, sex, room):
        super().__init__(name, sex, room)
        self.vnum = None                    # 遊戲號碼（區域檔的生物才有），重置的 limit 用它數
        self.keywords = []                  # 玩家用來指定牠的名字（小寫）
        self.long = ""                      # 站著時在房間裡看到的那一行
        self.description = ""               # 用 look 看牠時的描述
        self.level = 1
        self.tier = None                    # MobTier：骰過 tier_roll 之後的種類
        self.attack = self.defense = self.archetype = None   # 區域檔的代號（屬性已經照它們算好在 panel）
        self.act = ActFlag(0)
        self.panel = {}                     # 全部屬性（stats.mob_stats()，出現時算好）；直接建的（測試）沒有
        self.mix = {}                       # 攻擊類型比例，例如 {"dragon": 0.7, "phys": 0.3}
        self.hp = self.mp = self.mv = 0.0   # 現在的 HP、MP、MV（出現時補滿；怪物的 MP、MV 是 0）


def roll_tier(proto, rng):
    """重生時骰種類（tier_roll）：骰 0～9999，照順序累加各種類的機率，落在哪一段就是那個種類；都沒落到是原本的 tier。"""
    roll, total = rng.randrange(CHANCE_MAX), 0
    for tier, chance in (proto["tier_roll"] or {}).items():
        total += chance
        if roll < total:
            return MobTier(tier)
    return MobTier(proto["tier"])


def spawn(vnum, proto, room, rng):
    """照區域檔的生物 proto（已經檢查過）做一隻放進 room，加進 characters。

    名字是 short；姿勢照區域檔的 position（C 版讀了就丟，我們用它，可以做睡著的生物），不是合法的值就站著。
    """
    npc = Npc(proto["short"], proto["sex"], room)
    npc.vnum = vnum
    npc.keywords = proto["keywords"].lower().split()
    npc.long, npc.description = proto["long"], proto["description"]
    npc.level, npc.tier = proto["level"], roll_tier(proto, rng)
    npc.attack, npc.defense, npc.archetype = proto["attack"], proto["defense"], proto["archetype"]
    npc.act = ActFlag(parse_flags(proto["act"]))
    npc.panel, npc.mix = stats.mob_stats(npc.level, npc.tier, npc.attack, npc.defense, npc.archetype)
    npc.hp, npc.mp, npc.mv = npc.panel["hp"], npc.panel["mp"], npc.panel["mv"]
    position = proto["position"]
    npc.position = Position(position) if position in {p.value for p in Position} else Position.STANDING
    characters.append(npc)
    return npc
