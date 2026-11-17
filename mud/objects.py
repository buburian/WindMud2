"""物品：遊戲裡真的出現的物品：生物死掉時的屍體和裡面掉落的物品（照 C 版 fight.c 的 make_corpse）、imm 用 oload 做出來的。

區域檔的物品用 create() 做：裝備寫了 affects 是固定裝備，[] 就照設計文件 §3.3 隨機抽屬性（equipment.roll_item）。
物品放在房間的 contents（地上）、別的物品的 contains（屍體裡）、角色的 carrying（背包）或 equipment（穿在身上），沒有全遊戲的名單：
區域物件釋放時房間不要了，地上的物品就跟著不見；角色身上的跟著角色，存檔用 to_data()、from_data()。
"""
import logging
import random

from . import area, equipment, names
from .act import notify
from .area import (CHANCE_MAX, CHARGED_ITEM_TYPES, CONTAINER_ITEM_TYPE, CORPSE_NPC_ITEM_TYPE, DRINK_CON_ITEM_TYPE, FOOD_ITEM_TYPE,
                   FOUNTAIN_ITEM_TYPE, LIGHT_ITEM_TYPE, SKILL_ITEM_TYPES, WEAPON_ITEM_TYPE, Apply, Attack, ContainerFlag,
                   ItemColor, WeaponKind, WearFlag, parse_flags, skill_slots, wear_slots)
from .characters import Position
from .color import colorize
from .players import online_players

log = logging.getLogger(__name__)

CORPSE_KEYWORDS = ("corpse",)               # 屍體的名字（照 C 版；使用者定的：生物、物品的名字一律英文）
CORPSE_TIMER = (10, 14)                     # 屍體過幾次 OBJ_TICKS 消失（照 C 版：10～14 個 tick，約 5～7 分鐘）
DECAY = "腐爛變成了灰塵。"                    # timer 到了的訊息（照 C 版的屍體；現在只有屍體有 timer）
# 名字的顏色（使用者選的）：裝備照顏色（終端機沒有橘色，用暗黃），其他物品照 C 版亮綠；後面的英文名字亮青（照 C 版）
COLOR_CODES = {ItemColor.GRAY: "{D", ItemColor.WHITE: "{W", ItemColor.BLUE: "{B", ItemColor.PURPLE: "{M", ItemColor.ORANGE: "{y"}
OTHER_CODE = "{G"
ENGLISH, FLOOR, RESET = colorize("{C"), colorize("{W"), colorize("{x")    # 地上那一行亮白（使用者選的，跟生物一樣）

protos = {}                                 # 遊戲號碼 → 區域檔的物品（zones.load 填，跨檔案也找得到）


class Obj:
    """遊戲裡的一件物品。區域檔的物品用 create() 做，屍體用 make_corpse() 做。只放現在用得到的資料。"""

    def __init__(self, name, long, item_type, keywords):
        self.vnum = None                    # 遊戲號碼（區域檔的物品才有；屍體沒有）
        self.keywords = keywords            # 玩家用來指定它的名字（小寫）
        self.name = name                    # 名字（區域檔的 short；隨機裝備前面接上詞綴的名稱）
        self.long = long                    # 放在地上時看到的那一行
        self.item_type = item_type          # 物品種類（手冊的 item_type 表）
        self.level = 0                      # 裝備等級：放出它的地方決定（掉落表是生物的等級）
        self.color = None                   # 裝備的顏色（area.ItemColor 的代號），不是裝備是 None
        self.affects = []                   # [(Apply, 加多少)]：固定裝備照區域檔，隨機裝備是抽到的
        self.base = {}                      # 裝備基本值：武器 dmg_min、dmg_max，護具 ac（equipment.base_values）
        self.contains = []                  # 裡面的物品（屍體）
        self.timer = None                   # 還剩幾次 OBJ_TICKS 就消失；None 是不會消失
        self.weight = 0                     # 重量（區域檔的 weight）
        self.cost = 0                       # 價格（區域檔的 cost）：裝備以外的物品的基本價格（base_price）
        self.take = False                  # 撿不撿得起來（wear_flags 有 1 take）；屍體撿不起來
        self.slot = None                    # 穿在哪個部位（equipment.best_slot：跟點數上限同一個；雙手武器是 TWO_HANDED），不是裝備是 None
        self.weapon_kind = None             # 武器才有：area.WeaponKind（values 第 1 個）
        self.attack = None                  # 武器才有：area.Attack（values 第 4 個，戰鬥訊息的「使用重砍攻擊」）
        self.container = None               # 容器才有：現在的 area.ContainerFlag（values 第 2 個開始，開關、上鎖會改它）；屍體是 None，一直開著
        self.key = None                     # 容器的鑰匙：遊戲號碼（values 第 3 個，換算跟出口的 key 一樣），None 是鎖不起來
        self.seal = 0                       # 容器的封印密碼（values 第 4 個）：可以封印又不是 0 就打不開（封印的指令還沒做）
        self.hours = None                   # 照明用具才有：還能亮幾小時（values 第 3 個；0 燒完了、負數永遠不熄，light.py）
        self.skills = []                    # 會放技能的物品（卷軸、藥水、魔杖、魔棒）：用的時候放哪些技能（技能的 id，commands/item_skills.py）
        self.charges = None                 # 魔杖、魔棒才有：還剩幾次（values 第 3 個），到 0 就碎掉
        # 吃喝（設計文件 §3.9，commands/meals.py）：不是這幾種的都是 None
        self.bites = None                   # 食物：還能吃幾口（values 第 1 個），到 0 就不見
        self.buff = None                    # 食物：坐滿 10 秒放的 buff 技能（values 第 2 個，"" 是沒有）
        self.capacity = None                # 液體容器：容量（values 第 1 個）
        self.amount = None                  # 液體容器：現在有多少（values 第 2 個），每喝少 1
        self.liquid = None                  # 液體容器、噴泉：液體種類（values 第 3 個，area.LIQUIDS）

    def is_weapon(self):
        return self.weapon_kind is not None

    def is_container(self):
        """能從裡面拿東西：容器、怪物屍體。"""
        return self.item_type in (CONTAINER_ITEM_TYPE, CORPSE_NPC_ITEM_TYPE)

    def closed(self):
        return self.container is not None and ContainerFlag.CLOSED in self.container


def create(vnum, level, color, rng=random):
    """照區域檔的物品 vnum 做一件，裝備等級 level、顏色 color（放出它的地方決定）。號碼找不到記 log、回傳 None。

    有穿戴部位的是裝備：寫了 affects 用寫好的（固定裝備），[] 照等級和顏色隨機抽，名稱接在名字前面（「疾風之蠻力長劍」）。
    灰色、沒寫顏色的裝備沒有隨機屬性。基本值（武器傷害、AC）都照等級算，不算點數。
    """
    proto = protos.get(vnum)
    if proto is None:                       # 掉落表的號碼存不存在還沒檢查：先記 log 跳過
        log.warning(f"做不出物品 {vnum}：沒有這個號碼的物品")
        return None
    obj = Obj(proto["short"], proto["long"], proto["item_type"], proto["keywords"].lower().split())
    obj.vnum, obj.level, obj.color = vnum, level, color
    obj.weight, obj.cost = proto["weight"], proto["cost"]
    obj.take = bool(parse_flags(proto["wear_flags"]) & WearFlag.TAKE)
    slot = obj.slot = equipment.best_slot(*wear_slots(proto))
    if proto["item_type"] == CONTAINER_ITEM_TYPE:
        # 鑰匙跟出口的 key 一樣寫完整的遊戲號碼（0 以下是沒有鑰匙）
        _, flags, key, seal = (int(v) if str(v).lstrip("-").isdecimal() else 0 for v in proto["values"])
        obj.container = ContainerFlag(flags & sum(ContainerFlag))
        obj.key = key if key > 0 else None
        obj.seal = seal
    if proto["item_type"] == WEAPON_ITEM_TYPE:      # 區域檢查保證武器的種類、攻擊方式是對的
        obj.weapon_kind, obj.attack = WeaponKind(int(proto["values"][0])), Attack(int(proto["values"][3]))
    if proto["item_type"] == LIGHT_ITEM_TYPE:
        obj.hours = light_hours(proto)
    if proto["item_type"] in SKILL_ITEM_TYPES:
        obj.skills, obj.charges = skill_parts(proto)
    for k, v in meal_parts(proto).items():
        setattr(obj, k, v)
    if slot is None:                        # 不是裝備：沒有屬性
        return obj
    offhand_weapon = slot == "offhand" and proto["item_type"] == WEAPON_ITEM_TYPE   # 副手武器（雙持）：給武器傷害、不給 AC
    if proto["affects"]:
        obj.base = equipment.base_values(slot, level, rng, offhand_weapon)
        obj.affects = [(Apply(a["location"]), a["modifier"]) for a in proto["affects"]]
        return obj
    rolled = equipment.roll_item(slot, level, color, rng, offhand_weapon)
    obj.base = rolled["base"]
    obj.affects = [(Apply[stat.upper()], n) for stat, n in rolled["affixes"].items()]
    obj.name = rolled["name"] + obj.name
    return obj


def light_hours(proto):
    """區域檔的照明用具可以亮幾小時（values 第 3 個）：寫錯（不是整數）當作 0、燒完了。"""
    hours = proto["values"][2]
    return int(hours) if str(hours).lstrip("-").isdecimal() else 0


def skill_parts(proto):
    """會放技能的物品：(技能的 id 清單, 剩幾次)。區域檢查保證寫的是技能的 key；不是魔杖、魔棒的剩幾次是 None。"""
    values = proto["values"]
    skills = [values[i] for i in skill_slots(proto["item_type"]) if values[i]]
    return skills, (int(values[2]) if proto["item_type"] in CHARGED_ITEM_TYPES else None)


MEAL_FIELDS = ("bites", "buff", "capacity", "amount", "liquid")


def meal_parts(proto):
    """吃喝的東西照區域檔的 values（區域檢查保證寫法對）：{欄位: 值}；不是吃喝的東西是空的。"""
    values, kind = proto["values"], proto["item_type"]
    if kind == FOOD_ITEM_TYPE:
        return {"bites": int(values[0]), "buff": values[1]}
    if kind == DRINK_CON_ITEM_TYPE:
        return {"capacity": int(values[0]), "amount": int(values[1]), "liquid": int(values[2])}
    if kind == FOUNTAIN_ITEM_TYPE:
        return {"liquid": int(values[2])}
    return {}


def base_price(obj):
    """商店的基本價格（區域製作手冊物品的 cost）：裝備是實際用掉的點數（每一項加成 × 單價加起來，負的抵掉），最低 1，灰色是 1；
    其他物品是 cost。scavenger 挑最值錢的、janitor 撿便宜的用它（商店還沒做）。
    """
    if obj.slot is None:
        return obj.cost
    if obj.color == ItemColor.GRAY:
        return 1
    return max(1, sum(n * equipment.price(a.name.lower(), obj.level) for a, n in obj.affects if a != Apply.NONE))


def make_corpse(npc, rng=random):
    """npc 死掉留下的屍體：放在牠的房間地上（最前面），CORPSE_TIMER 次 OBJ_TICKS 後消失。

    裡面是掉落表骰到的物品，加上牠背包裡的（照 C 版）；店主背包裡的不放進去、直接消失（照 C 版：防止殺店主複製東西，使用者選的）。
    """
    # 地上那一行：「野狗的屍體橫躺在地上。」，英文名字 /corpse 由 on_floor() 接在後面（使用者定的，跟其他物品一樣）
    corpse = Obj(f"{npc.name}的屍體", f"{npc.name}的屍體橫躺在地上。", CORPSE_NPC_ITEM_TYPE, list(CORPSE_KEYWORDS))
    corpse.level = npc.level
    corpse.timer = rng.randint(*CORPSE_TIMER)
    corpse.contains = roll_drops(npc, rng) + ([] if getattr(npc, "shopkeeper", False) else list(npc.carrying))
    npc.carrying = []
    npc.room.contents.insert(0, corpse)
    return corpse


def roll_drops(npc, rng=random):
    """照 npc 的掉落表，每一行各自骰（設計文件 §4.10）：tiers 是 null 或包含牠的種類才骰，機率是萬分之一。

    掉出來的物品等級是牠的等級、顏色是那一行的顏色。照掉落表的順序回傳。
    """
    found = []
    for line in npc.drops:
        if line["tiers"] is not None and npc.tier not in line["tiers"]:
            continue
        if rng.randrange(CHANCE_MAX) < line["chance"]:
            obj = create(line["obj_vnum"], npc.level, line["color"], rng)
            if obj is not None:
                found.append(obj)
    return found


def short(obj):
    """上了顏色的「名字/英文名字」（使用者選的，例如「測試藥水/potion」）：名字裝備照顏色、其他亮綠，英文名字亮青（照 C 版）。

    英文名字是 keywords 裡的英文字；沒有英文字就只有名字。名字是區域作者寫的，不轉裡面的顏色代碼（跟生物一樣）。
    """
    return colorize(COLOR_CODES.get(obj.color, OTHER_CODE)) + obj.name + english_tail(obj) + RESET


def inside(container):
    """容器、屍體裡有什麼（look in 和打死生物後看屍體共用，照 C 版 act_info.c）：每件一行、前面空 5 格。

    C 版會把一樣的合成「( 2) 」，先不做。
    """
    items = "".join(f"     {short(o)}\n" for o in container.contains) or "     空無一物。\n"
    return f"{container.name}裝著：\n{items}"


def english_tail(obj):
    """名字後面的「/英文名字」（英文亮青，照 C 版）：keywords 裡的英文字；沒有英文字是空的。"""
    english = " ".join(k for k in obj.keywords if k.isascii())
    return f"/{ENGLISH}{english}" if english else ""


def on_floor(obj):
    """房間裡看到 obj 的那一行（沒有換行）：描述亮白（跟生物一樣），後面接「/英文名字」亮青（使用者定的：「一把測試長劍插在地上。/sword」）。"""
    return FLOOR + obj.long.rstrip("\n") + english_tail(obj) + RESET


def extra_descriptions(obj):
    """物品可以細看的東西 [(小寫的名字們, 描述)]：照區域檔現在寫的（存檔不帶，區域檔改了就跟著變）。屍體、區域檔沒有的是空的。"""
    proto = protos.get(obj.vnum)
    return area.extra_descriptions(proto["extra_descriptions"]) if proto else []


def find(objs, name):
    """objs 裡（照順序）叫做 name 的那件，找不到是 None。規則跟找生物一樣（names.py：開頭就行、2.sword 是第 2 件）。"""
    return names.pick(objs, name, lambda o: o.keywords)


def weight(obj):
    """obj 的重量，加上裡面的東西（照 C 版 get_obj_weight）。"""
    return obj.weight + sum(weight(o) for o in obj.contains)


FIELDS = ("vnum", "name", "long", "item_type", "level", "color", "base", "weight", "take", "slot")
LATER_FIELDS = {"key": None, "seal": 0, "cost": 0}     # 後來才加的欄位：舊存檔沒有，用這個值


def to_data(obj):
    """存檔用（整件存，區域檔之後改了，身上的照舊）：名字、詞綴、基本值、部位、裡面的東西都在裡面。"""
    data = {k: getattr(obj, k) for k in FIELDS}
    data.update(keywords=" ".join(obj.keywords), affects=[[int(a), n] for a, n in obj.affects],
                weapon_kind=None if obj.weapon_kind is None else int(obj.weapon_kind),
                attack=None if obj.attack is None else int(obj.attack),
                container=None if obj.container is None else int(obj.container), key=obj.key, seal=obj.seal, cost=obj.cost,
                hours=obj.hours, skills=list(obj.skills), charges=obj.charges, contains=[to_data(o) for o in obj.contains],
                **{k: getattr(obj, k) for k in MEAL_FIELDS})
    return data


def from_data(data):
    """to_data() 的反過來。"""
    obj = Obj(data["name"], data["long"], data["item_type"], data["keywords"].split())
    for k in FIELDS:
        setattr(obj, k, data[k])
    obj.affects = [(Apply(a), n) for a, n in data["affects"]]
    obj.weapon_kind = None if data["weapon_kind"] is None else WeaponKind(data["weapon_kind"])
    obj.attack = None if data["attack"] is None else Attack(data["attack"])
    obj.container = None if data.get("container") is None else ContainerFlag(data["container"])
    for k, default in LATER_FIELDS.items():
        setattr(obj, k, data.get(k, default))
    if "hours" in data:
        obj.hours = data["hours"]
    elif obj.item_type == LIGHT_ITEM_TYPE:  # 舊存檔沒有 hours：照區域檔現在的值；區域檔沒有這件了就當作永遠不熄
        proto = protos.get(obj.vnum)
        obj.hours = light_hours(proto) if proto else -1
    if "skills" in data:
        obj.skills, obj.charges = list(data["skills"]), data["charges"]
    elif obj.item_type in SKILL_ITEM_TYPES:     # 舊存檔沒有：照區域檔現在的值；區域檔沒有這件了就當作沒有技能、0 次
        proto = protos.get(obj.vnum)
        obj.skills, obj.charges = skill_parts(proto) if proto else ([], 0 if obj.item_type in CHARGED_ITEM_TYPES else None)
    if "bites" in data:
        for k in MEAL_FIELDS:
            setattr(obj, k, data[k])
    elif obj.item_type in (FOOD_ITEM_TYPE, DRINK_CON_ITEM_TYPE, FOUNTAIN_ITEM_TYPE):   # 舊存檔沒有：照區域檔現在的值
        gone = [1, "", 0, 0] if obj.item_type == FOOD_ITEM_TYPE else [0, 0, 0, 0]   # 區域檔沒有這件了：一口、空的、清水
        proto = protos.get(obj.vnum) or {"item_type": obj.item_type, "values": gone}
        for k, v in meal_parts(proto).items():
            setattr(obj, k, v)
    obj.contains = [from_data(d) for d in data["contains"]]
    return obj


def update(zone):
    """每 OBJ_TICKS 個 tick（Zone.tick() 呼叫，照 C 版的 obj_update）：zone 裡地上有 timer 的物品減 1，到 0 就拿掉，裡面的東西一起不見。

    那間房醒著的玩家收到「測試商人的屍體腐爛變成了灰塵。」；同時不見好幾件就合成一段，每個人只送一次（不然會有好幾個 prompt）。
    """
    for room in zone.rooms.values():
        gone = []
        for obj in room.contents:
            if obj.timer is not None:
                obj.timer -= 1
                if obj.timer <= 0:
                    gone.append(obj)
        if not gone:
            continue
        room.contents[:] = [o for o in room.contents if o not in gone]
        text = "\n".join(f"{o.name}{DECAY}" for o in gone)
        for p in online_players():
            if p.room is room and p.position > Position.SLEEPING:
                notify(p, text)
