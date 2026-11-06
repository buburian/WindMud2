"""NPC（生物）：沒有連線的角色。區域檔的生物由 spawn() 做出來（resets.py 的 M）。"""
from . import stats
from .area import CHANCE_MAX, ActFlag, MobTier, parse_flags, resolve
from .characters import Character, Position, characters


class Npc(Character):
    """NPC。區域檔的生物用 spawn() 做；Npc(name, sex, room) 直接建的（測試）沒有區域檔的資料。"""

    def __init__(self, name, sex, room):
        super().__init__(name, sex, room)
        self.vnum = None                    # 遊戲號碼（區域檔的生物才有），重置的 limit 用它數
        self.keywords = []                  # 玩家用來指定牠的名字（小寫）
        self.shopkeeper = False             # 店主（區域檔的 shop 不是 null）：死掉時身上的東西不放進屍體（照 C 版）
        self.long = ""                      # 站著時在房間裡看到的那一行
        self.description = ""               # 用 look 看牠時的描述
        self.level = 1
        self.tier = None                    # MobTier：骰過 tier_roll 之後的種類
        self.attack = self.defense = self.archetype = None   # 區域檔的代號（屬性已經照它們算好在 panel）
        self.act = ActFlag(0)
        self.base_panel = {}                # 出現時算好的全部屬性（stats.mob_stats()）；直接建的（測試）沒有
        self.panel = {}                     # 現在的全部屬性 ＝ base_panel ＋ 身上的效果（recompute()）
        self.mix = {}                       # 攻擊類型比例，例如 {"dragon": 0.7, "phys": 0.3}
        self.hp = self.mp = self.mv = 0.0   # 現在的 HP、MP、MV（出現時補滿；怪物的 MP、MV 是 0）
        self.drops = []                     # 掉落表（區域檔的 drops，obj_vnum 換成遊戲號碼）：死掉時 objects.make_corpse() 照它骰

    def names(self):
        """玩家用來指定牠的名字：區域檔的 keywords；直接建的（測試）沒有就用名字。"""
        return self.keywords or super().names()


def recompute(npc):
    """從頭算生物現在的屬性：出現時算好的 ＋ 身上的效果（使用者定的）。"""
    npc.panel = dict(npc.base_panel)
    stats.add_affects(npc.panel, npc)


def roll_tier(proto, rng):
    """重生時骰種類（tier_roll）：骰 0～9999，照順序累加各種類的機率，落在哪一段就是那個種類；都沒落到是原本的 tier。"""
    roll, total = rng.randrange(CHANCE_MAX), 0
    for tier, chance in (proto["tier_roll"] or {}).items():
        total += chance
        if roll < total:
            return MobTier(tier)
    return MobTier(proto["tier"])


def spawn(vnum, proto, room, rng, base):
    """照區域檔的生物 proto（已經檢查過）做一隻放進 room，加進 characters。base 是牠那個區域檔的 area_number。

    名字是 short；姿勢照區域檔的 position（C 版讀了就丟，我們用它，可以做睡著的生物），不是合法的值就站著。
    掉落表的 obj_vnum 用牠自己那個檔的 base 換算（M 可以放別的檔的生物，所以不是放牠的那個檔）。
    """
    npc = Npc(proto["short"], proto["sex"], room)
    npc.vnum = vnum
    npc.drops = [{**line, "obj_vnum": resolve(base, line["obj_vnum"])} for line in proto["drops"]]
    npc.keywords = proto["keywords"].lower().split()
    npc.long, npc.description = proto["long"], proto["description"]
    npc.level, npc.tier = proto["level"], roll_tier(proto, rng)
    npc.attack, npc.defense, npc.archetype = proto["attack"], proto["defense"], proto["archetype"]
    npc.act = ActFlag(parse_flags(proto["act"]))
    npc.shopkeeper = proto["shop"] is not None
    npc.base_panel, npc.mix = stats.mob_stats(npc.level, npc.tier, npc.attack, npc.defense, npc.archetype)
    recompute(npc)
    npc.hp, npc.mp, npc.mv = npc.panel["hp"], npc.panel["mp"], npc.panel["mv"]
    position = proto["position"]
    npc.position = Position(position) if position in {p.value for p in Position} else Position.STANDING
    characters.append(npc)
    return npc
