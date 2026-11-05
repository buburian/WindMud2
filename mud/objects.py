"""物品：遊戲裡真的出現的物品。現在只有生物死掉時的屍體，和屍體裡照掉落表骰到的物品（照 C 版 fight.c 的 make_corpse）。

區域檔的物品用 create() 做：裝備寫了 affects 是固定裝備，[] 就照設計文件 §3.3 隨機抽屬性（equipment.roll_item）。
物品放在房間的 contents（地上）或別的物品的 contains（屍體裡），沒有全遊戲的名單：
區域物件釋放時房間不要了，裡面的物品就跟著不見。撿起來、背包、存檔還沒做。
"""
import logging
import random

from .act import notify
from .area import CHANCE_MAX, CORPSE_NPC_ITEM_TYPE, WEAPON_ITEM_TYPE, Apply, ItemColor, wear_slots
from .characters import Position
from .color import colorize
from . import equipment
from .players import online_players

log = logging.getLogger(__name__)

CORPSE_KEYWORDS = ("corpse", "屍體")         # 屍體的名字（C 版只有 corpse，加上中文）
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
    slot = equipment.best_slot(*wear_slots(proto))
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


def make_corpse(npc, rng=random):
    """npc 死掉留下的屍體：放在牠的房間地上（最前面），裡面是掉落表骰到的物品，CORPSE_TIMER 次 OBJ_TICKS 後消失。"""
    # 地上那一行照生物 long 的寫法，中間夾英文名字（使用者定的）
    corpse = Obj(f"{npc.name}的屍體", f"{npc.name}的屍體/corpse/橫躺在地上。", CORPSE_NPC_ITEM_TYPE, list(CORPSE_KEYWORDS))
    corpse.level = npc.level
    corpse.timer = rng.randint(*CORPSE_TIMER)
    corpse.contains = roll_drops(npc, rng)
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
    english = " ".join(k for k in obj.keywords if k.isascii())
    tail = f"/{ENGLISH}{english}" if english else ""
    return colorize(COLOR_CODES.get(obj.color, OTHER_CODE)) + obj.name + tail + RESET


def on_floor(obj):
    """房間裡看到 obj 的那一行（沒有換行）：亮白（使用者選的，跟生物一樣）。"""
    return FLOOR + obj.long.rstrip("\n") + RESET


def find(objs, word):
    """objs 裡叫做 word 的第一件：名字要整個字一樣，英文不分大小寫（跟門、細看一樣）。找不到是 None。"""
    word = word.lower()
    return next((o for o in objs if word in o.keywords), None)


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
