"""區域檔：格式、檢查，以及把房間建成 Room。

區域檔是我們自己的格式，每個欄位的意思寫在 docs/區域製作手冊.md。
規則只在 check_files() 一份：伺服器開機（zones.load）、檢查工具（python -m mud.areacheck）和區域編輯器都用它。
開機後真的在跑的區域（世界、動態區域、副本）在 zones.py。

號碼規則：檔案裡的房間、生物號碼只能是 1～99，遊戲裡的號碼是 area.header.area_number 加上它
（房間和生物的號碼分開算）。
要指到房間或物品時（to_room、key、recall），寫 1～99 是同一個區域（一樣加上 area_number），
100 以上是完整號碼（指到別的區域）。所以遊戲號碼 1～99 是保留的：有房間用了它，
別的區域寫 1～99 就分不出是指哪一個（area_number 不能是 0）。
"""
import enum
import json
import math
from pathlib import Path

from . import equipment

DIRECTIONS = {"north": "北", "east": "東", "south": "南", "west": "西", "up": "上", "down": "下"}
REVERSE = {"north": "south", "east": "west", "south": "north", "west": "east", "up": "down", "down": "up"}


# 手冊的表在程式裡的定義，要跟手冊一模一樣（tests/test_area.py 會比對數字和名字）。
# 程式裡用名字（例如 RoomFlag.SAFE），不要直接寫數字。
class RoomFlag(enum.IntFlag):
    """房間旗標（room_flags）。名字是手冊的 C 版名稱；可以用 | 合起來，2 沒有用到。"""
    DARK = 1                                # 很暗
    NO_MOB = 4                              # 怪物不會走進來
    INDOORS = 8                             # 室內
    UNDERGROUND = 16                        # 地底：吸血鬼白天在這裡不怕陽光
    CLANREST_LV1 = 32                       # 幫派休息室（第 1 級）
    CLANREST_LV2 = 64                       # 幫派休息室（第 2 級）
    CLANREST_LV3 = 128                      # 幫派休息室（第 3 級）
    CLANROOM = 256                          # 幫派房間：只有這個幫派的人能進來
    PRIVATE = 512                           # 私人房間：最多 2 個人
    SAFE = 1024                             # 安全區：不能戰鬥
    SOLITARY = 2048                         # 單人房：最多 1 個人
    PET_SHOP = 4096                         # 寵物店
    NO_RECALL = 8192                        # 不能用回城
    CONE_OF_SILENCE = 16384                 # 不能說話（頻道和 tell 都不能用）
    NO_MURDER = 32768                       # 不能殺玩家
    FEN = 65536                             # 沼氣：不會飛的人會中毒
    NO_SUMMON = 131072                      # 不能用召喚術（C 版註解：不可 cast summon 的房間）
    HALF_GAIN = 262144                      # 回復力減半
    NO_TELEPORT = 524288                    # 傳送術不會落在這間房
    DEADTRAPS = 1048576                     # 死亡陷阱：走進來就會死（神族除外）
    BANK = 2097152                          # 銀行
    DAMAGETRAP = 4194304                    # 每個 tick 扣一半的生命、法力和體力
    EQBANK = 8388608                        # 裝備銀行


class Sector(enum.IntEnum):
    """地形（sector）。名字是手冊的 C 版名稱；一間房只會有一種。"""
    INSIDE = 0                              # 室內
    CITY = 1                                # 城市
    FIELD = 2                               # 原野
    FOREST = 3                              # 森林
    HILLS = 4                               # 丘陵
    MOUNTAIN = 5                            # 山地
    WATER_SWIM = 6                          # 可以游泳過去的水
    WATER_NOSWIM = 7                        # 要有船才能過去的水
    UNDERWATER = 8                          # 水底，要會在水裡呼吸
    AIR = 9                                 # 空中，要會飛
    DESERT = 10                             # 沙漠


class Locks(enum.IntEnum):
    """門的種類（出口的 locks）。1～8 都是門。

    手冊的表沒有名稱，名字照 C 版的門旗標：PICKPROOF 撬不開、BASHPROOF 撞不開、PASSPROOF 法術穿不過去。
    """
    NO_DOOR = 0                             # 沒有門
    DOOR = 1                                # 門
    PICKPROOF = 2                           # 門，撬不開
    BASHPROOF = 3                           # 門，撞不開
    PICKPROOF_BASHPROOF = 4                 # 門，撬不開也撞不開
    PASSPROOF = 5                           # 門，法術穿不過去
    PICKPROOF_PASSPROOF = 6                 # 門，撬不開、法術穿不過去
    BASHPROOF_PASSPROOF = 7                 # 門，撞不開、法術穿不過去
    PICKPROOF_BASHPROOF_PASSPROOF = 8       # 門，撬不開、撞不開、法術穿不過去


class AreaType(enum.StrEnum):
    """區域的種類（area.header.type）。值就是區域檔裡寫的字串，要跟手冊「三種區域」的表一樣。"""
    WORLD = "world"                         # 世界區域：開機就建好，沒人也不釋放
    DYNAMIC = "dynamic"                     # 動態區域：有人走進去才建立，大家共用一份；沒有玩家一段時間就釋放
    INSTANCE = "instance"                   # 副本區域：用 enter 進去、recall 出來，一個隊伍一份；沒有玩家一段時間就釋放


# 生物的種類、攻擊類型、攻防傾向、原型（mud_design 設計文件 §4.1～§4.3）。值是區域檔裡寫的代號，要跟手冊的表一樣。
# 怪物的屬性和經驗值由程式照「等級 ＋ 這幾個欄位」算，區域檔不寫數值。
class MobTier(enum.StrEnum):
    """生物的種類（tier，必填）。"""
    TRASH = "trash"                         # 垃圾怪：裝備完整度 ×0，經驗加成 ×0.1
    NORMAL = "normal"                       # 一般怪：裝備完整度 ×0.5，經驗加成 ×1.2
    ELITE = "elite"                         # 菁英怪：裝備完整度 ×1，經驗加成 ×1.1
    BOSS = "boss"                           # Boss 怪：裝備完整度 ×1.1，經驗加成 ×1.0


class AttackType(enum.StrEnum):
    """攻擊類型（attack）。只用一種寫 "phys"；主／次搭配寫 "dragon/phys"（主 70%、次 30%）；null 是純物理。"""
    PHYS = "phys"                           # 物理
    SPELL = "spell"                         # 法術
    DRAGON = "dragon"                       # 龍焰（只有怪物有）


class Defense(enum.StrEnum):
    """攻防傾向（defense）：擅長的抗性 : 不擅長的 ＝ 2 : 0.5，再換算回原本物抗＋法抗的合計，總點數不變。null 是標準。"""
    PHYS = "phys"                           # 物抗 ×1.6、法抗 ×0.4（原本一樣時；怕法術）
    SPELL = "spell"                         # 法抗 ×1.6、物抗 ×0.4（原本一樣時；怕物理）


class Archetype(enum.StrEnum):
    """原型（archetype）：把可調點數重新分配，總點數不變。null 是標準。"""
    TANK = "tank"                           # 坦克：HP、抗性、閃躲 ×2；攻擊類 ×0.5
    BERSERKER = "berserker"                 # 狂戰：傷害、攻速、爆擊 ×2；HP、抗性、閃躲 ×0.5
    AGILE = "agile"                         # 敏捷：閃躲、命中、攻速 ×2；HP、抗性 ×0.5
    EXTREME_TANK = "extreme_tank"           # 極端坦克：可調的 25% 全部放 HP


class ItemColor(enum.StrEnum):
    """掉落裝備的顏色（drops 的 color，設計文件 §3.3 的稀有度）。點數上限要乘上它的加成。"""
    GRAY = "gray"                           # 灰：×0，沒有屬性
    WHITE = "white"                         # 白：×1，該級最佳裝備
    BLUE = "blue"                           # 藍：×1.2
    PURPLE = "purple"                       # 紫：×1.3
    ORANGE = "orange"                       # 橘：×1.4


CHANCE_MAX = 10000                          # 機率以萬分之一為單位（tier_roll、drops 的 chance）：10000 是 100%


class Apply(enum.IntEnum):
    """物品加成加在哪裡（affects 的 location）。名字是手冊表的代號；6～16 跟 mud_design 的 STAT_KEYS 一樣。"""
    NONE = 0                                # 無
    STR = 1                                 # 力量
    DEX = 2                                 # 敏捷
    INT = 3                                 # 智慧
    WIS = 4                                 # 知識
    CON = 5                                 # 體質
    HP = 6                                  # HP
    DMG_PHYS = 7                            # 物理傷害
    DMG_SPELL = 8                           # 法術傷害
    HIT = 9                                 # 命中
    DODGE = 10                              # 閃躲
    CRIT = 11                               # 爆擊率
    CRITDMG = 12                            # 爆擊傷害
    SPEED = 13                              # 攻速
    RES_PHYS = 14                           # 物理抗性
    RES_SPELL = 15                          # 法術抗性
    RES_DRAGON = 16                         # 龍焰抗性（不算點數）


class WearFlag(enum.IntFlag):
    """物品能不能拿起來、穿在哪裡（wear_flags）。名字是手冊的 C 版名稱，位置照設計文件 §3.3 的裝備欄位。"""
    TAKE = 1                                # 可以拿起來（不是位置）
    FINGER = 2                              # 戒指
    NECK = 4                                # 頸
    BODY = 8                                # 身體
    HEAD = 16                               # 頭
    LEGS = 32                               # 腿
    FEET = 64                               # 腳
    HANDS = 128                             # 手
    ARMS = 256                              # 手臂
    SHIELD = 512                            # 副手：盾牌或副手武器
    ABOUT = 1024                            # 披風
    WAIST = 2048                            # 腰
    WRIST = 4096                            # 手腕
    WIELD = 8192                            # 主手
    HOLD = 16384                            # 持握


class ExtraFlag(enum.IntFlag):
    """物品的特性旗標（extra_flags）。1～256 照 C 版，512 是新系統加的。"""
    GLOW = 1                                # 發亮
    HUM = 2                                 # 低鳴
    DARK = 4                                # 黑暗
    LOCK = 8                                # 鎖
    EVIL = 16                               # 邪惡
    INVIS = 32                              # 隱形
    MAGIC = 64                              # 魔法
    NODROP = 128                            # 無法丟棄
    BLESS = 256                             # 祝福
    TWO_HANDED = 512                        # 雙手：武器同時佔主手和副手，點數上限是兩格加起來


# 穿戴位置 → equipment.py 的部位（點數上限用）。TAKE 不是位置。
WEAR_SLOTS = {
    WearFlag.FINGER: "finger", WearFlag.NECK: "neck", WearFlag.BODY: "body", WearFlag.HEAD: "head",
    WearFlag.LEGS: "legs", WearFlag.FEET: "feet", WearFlag.HANDS: "hands", WearFlag.ARMS: "arms",
    WearFlag.SHIELD: "offhand", WearFlag.ABOUT: "about", WearFlag.WAIST: "waist", WearFlag.WRIST: "wrist",
    WearFlag.WIELD: "wield", WearFlag.HOLD: "hold",
}
LIGHT_ITEM_TYPE = 1                         # 物品種類 1 照明用具：不在 wear_flags 裡，放在光源的位置


# 每一層要剛好有這些欄位
TOP_KEYS = ("schema_version", "file", "area", "rooms", "mobiles", "objects", "resets")
AREA_KEYS = ("header", "recall", "no_teleport", "clan_recall", "gem")
HEADER_KEYS = ("levels", "author", "title", "area_number", "type")
ROOM_KEYS = ("vnum", "name", "description", "room_flags", "sector", "exits", "extra_descriptions", "script")
EXIT_KEYS = ("description", "keywords", "locks", "key", "to_room")
EXTRA_KEYS = ("keywords", "description")
SCRIPT_KEYS = ("trigger", "function")
TRIGGER_KEYS = ("value", "names")
MOBILE_KEYS = ("vnum", "keywords", "short", "long", "description", "level", "tier", "tier_roll",
               "attack", "defense", "archetype", "act", "affected_by", "alignment",
               "race", "sex", "position",
               "drops", "script", "actions", "fight_actions", "shop", "special")
DROP_KEYS = ("obj_vnum", "color", "chance", "tiers")    # 掉落表的一行
ACTION_KEYS = ("when", "mode", "text")
FIGHT_KEYS = ("rate", "message", "command")
SHOP_KEYS = ("buy_types", "profit_buy", "profit_sell", "open_hour", "close_hour")
OBJECT_KEYS = ("vnum", "keywords", "short", "long", "item_type", "extra_flags", "wear_flags",
               "values", "weight", "cost", "affects", "extra_descriptions", "script")
AFFECT_KEYS = ("location", "modifier")
# 重置：每種指令的欄位（照順序執行，G 跟著前面最近的 M）。舊版的 E（穿裝備、給坐騎）拿掉了：生物不穿裝備
RESET_KEYS = {
    "M": ("cmd", "rare", "mob_vnum", "limit", "room_vnum", "comment"),             # 把生物放進房間
    "G": ("cmd", "rare", "obj_vnum", "color", "level", "limit", "comment"),                      # 給生物一件物品
    "O": ("cmd", "if_flag", "obj_vnum", "color", "level", "limit", "room_vnum", "comment"),      # 把物品放進房間
    "P": ("cmd", "if_flag", "obj_vnum", "color", "level", "limit", "container_vnum", "comment"), # 把物品放進容器
    "D": ("cmd", "if_flag", "room_vnum", "direction", "state", "comment"),         # 門一開始的狀態
    "R": ("cmd", "if_flag", "room_vnum", "exit_count", "comment"),                 # 打亂出口
    "*": ("cmd", "comment"),                                                       # 整行註解
}
RESET_NUMBERS = ("mob_vnum", "obj_vnum", "room_vnum", "container_vnum")   # 照號碼規則寫的欄位


class Room:
    """一個房間。"""

    def __init__(self, vnum, name, description, exits, room_flags, sector, exit_descriptions, extra_descriptions):
        self.vnum = vnum
        self.name = name
        self.description = description
        self.exits = exits                  # 方向 → 房間 vnum
        self.room_flags = room_flags        # 房間旗標（RoomFlag，用 | 合起來的）
        self.sector = sector                # 地形（Sector）
        self.exit_descriptions = exit_descriptions    # 方向 → 往那個方向看到的樣子（look 方向）
        self.extra_descriptions = extra_descriptions  # [(小寫的名字們, 描述)]：可以細看的東西（look 牌子）
        self.zone = None                    # 屬於哪個區域物件（zones.Zone），建進區域物件時設定


def parse_flags(value):
    """room_flags（生物的 act、affected_by 也一樣）的寫法：數字（0、5），或字串（"0"、"5"、"1|4"，用 | 把幾個數字合起來）。

    "1|4" 跟 5 一樣。格式不對就丟 ValueError。
    """
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"要寫數字或字串，不能是 {value!r}")
    parts = [value] if isinstance(value, int) else [p.strip() for p in value.split("|")]
    result = 0
    for p in parts:
        if isinstance(p, str):
            if not (p.isascii() and p.isdigit()):
                raise ValueError(f"看不懂 {value!r}")
            p = int(p)
        if p < 0:
            raise ValueError(f"不能是負數：{value!r}")
        result |= p
    return result


def resolve(base, number):
    """號碼規則：1～99 是同一個區域（加上 area_number），100 以上照寫的號碼。"""
    return base + number if number <= 99 else number


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)   # JSON 的 true 在 Python 也算 int，要排除


def check_files(paths, reference=()):
    """照手冊檢查區域檔，回傳 {檔案: [問題, …]}，沒問題就是空清單。

    reference 是其他拿來對照的檔案：只查一個檔時，靠它知道別的區域有哪些房間，
    才能檢查通到別的區域的出口、跨檔案的號碼重複。它們自己的問題不會報出來。
    """
    checked = {p.resolve() for p in paths}
    problems, found = {}, {}
    for path in paths:
        problems[path] = []
        data = read_json(path, problems[path])
        if data is not None:
            found[path] = check_structure(path.name, data, problems[path])

    # 跨檔案：遊戲號碼不能重複。先登記對照用的檔案，重複時算在要檢查的檔案頭上。
    # 房間和生物的號碼分開算（房間 101 和生物 101 可以同時存在）
    def owners(key, label, vnums_of):
        owner = {}
        for path in reference:
            if path.resolve() not in checked:
                for number in game_numbers(path, key):
                    owner.setdefault(number, path.name)
        for path, info in found.items():
            for vnum in vnums_of(info):
                number = info.base + vnum
                if number in owner:
                    problems[path].append(f"{path.name}：{label} {number} 跟 {owner[number]} 重複")
                else:
                    owner[number] = path.name
        return owner

    owner = owners("rooms", "房間", lambda info: info.vnums)
    # 每個檔案是哪一種區域（檔名 → AreaType），出口通到別的檔案時要看
    kinds = {path.name: area_kind(path) for path in reference if path.resolve() not in checked}
    kinds.update({path.name: info.kind for path, info in found.items()})
    # 出口和 recall 指到的房間要存在；副本只能用 enter 進去、recall 出來，所以出口不能跨進或跨出副本
    for path, info in found.items():
        for vnum, d, to in info.exits:
            target = resolve(info.base, to)
            if target not in owner:
                problems[path].append(f"{path.name}：房間 {vnum} 往 {d} 的出口指到不存在的房間 {target}")
            elif owner[target] != path.name and info.kind == AreaType.INSTANCE:
                problems[path].append(f"{path.name}：房間 {vnum} 往 {d} 的出口通到 {owner[target]} 的房間 {target}，"
                                      f"副本的出口不能通到別的區域（要用 recall 出來）")
            elif owner[target] != path.name and kinds.get(owner[target]) == AreaType.INSTANCE:
                problems[path].append(f"{path.name}：房間 {vnum} 往 {d} 的出口通到副本 {owner[target]} 的房間 {target}，"
                                      f"副本不能走進去（要用 enter）")
        if info.recall is not None and resolve(info.base, info.recall) not in owner:
            problems[path].append(f"{path.name}：area.recall 指到不存在的房間 {resolve(info.base, info.recall)}")
    owners("mobiles", "生物", lambda info: info.mobiles)
    owners("objects", "物品", lambda info: info.objects)
    # 固定裝備：物品可能在別的檔（寫完整號碼），所以用全部讀到的檔（含對照用的）去找物品和生物
    objects, mob_levels = world_items([*paths, *reference])
    for path, info in found.items():
        data = read_json(path, [])
        if info.base is not None and isinstance(data, dict):
            check_fixed_items(path.name, data, info.base, objects, mob_levels, problems[path])
    return problems


def world_items(paths):
    """全部檔案的物品（遊戲號碼 → 物品）和生物的等級（遊戲號碼 → level）。格式不對的就略過（別的規則會報錯）。"""
    objects, mob_levels = {}, {}
    for path in {p.resolve(): p for p in paths}.values():
        data = read_json(path, [])
        try:
            base = data["area"]["header"]["area_number"]
        except (KeyError, TypeError):
            continue
        if not is_int(base):
            continue
        for key, out, value in (("objects", objects, lambda o: o), ("mobiles", mob_levels, lambda m: m.get("level"))):
            for item in data.get(key) if isinstance(data.get(key), list) else []:
                if isinstance(item, dict) and is_int(item.get("vnum")) and 1 <= item["vnum"] <= 99:
                    out.setdefault(base + item["vnum"], value(item))
    return objects, mob_levels


def check_fixed_items(name, data, base, objects, mob_levels, problems):
    """固定裝備（物品寫了 affects）放出來的地方：加成的點數不能超過「等級和部位的上限 × 顏色加成」（設計文件 §3.3）。

    放出來的地方和等級：掉落表 drops 用這隻生物的等級；重置 G 寫 null 用前面最近那筆 M 的生物等級；O、P 寫在 level。
    顏色 null、gray 的加成是 ×0：只有不算點數的加成（例如龍焰抗性）才放得進去。
    """
    def place(where, obj_vnum, level, color):
        if is_int(obj_vnum) and is_int(level) and obj_vnum >= 1:
            check_fixed_item(where, resolve(base, obj_vnum), objects, level, color, problems)

    for m in data.get("mobiles") if isinstance(data.get("mobiles"), list) else []:
        if isinstance(m, dict) and isinstance(m.get("drops"), list):
            for i, d in enumerate(m["drops"]):
                if isinstance(d, dict):
                    place(f"{name}：生物 {m.get('vnum')} 的 drops 第 {i + 1} 行", d.get("obj_vnum"), m.get("level"), d.get("color"))
    m_level = None                          # 前面最近那筆 M 的生物等級（G 的 level 寫 null 時用）
    for i, r in enumerate(data.get("resets") if isinstance(data.get("resets"), list) else []):
        if not isinstance(r, dict):
            continue
        if r.get("cmd") == "M":
            m_level = mob_levels.get(resolve(base, r["mob_vnum"])) if is_int(r.get("mob_vnum")) else None
        elif r.get("cmd") in ("G", "O", "P"):
            level = m_level if r.get("cmd") == "G" and r.get("level") is None else r.get("level")
            place(f"{name}：resets 第 {i + 1} 筆（{r['cmd']}）", r.get("obj_vnum"), level, r.get("color"))


def check_fixed_item(where, number, objects, level, color, problems):
    """一個放出物品的地方：物品 number 是固定裝備的話，點數不能超過上限。寫錯的地方就略過（別的規則會報錯）。"""
    obj = objects.get(number)
    affects = obj.get("affects") if isinstance(obj, dict) else None
    if not (isinstance(affects, list) and affects) or not (color is None or color in codes(ItemColor)):
        return
    terms = []                              # [(屬性代號, 加多少, 每 +1 幾點)]
    for a in affects:
        if not (isinstance(a, dict) and is_int(a.get("location")) and a["location"] in [x.value for x in Apply]
                and is_int(a.get("modifier"))):
            return
        if a["location"] != Apply.NONE:
            stat = Apply(a["location"]).name.lower()
            terms.append((stat, a["modifier"], equipment.price(stat, level)))
    try:
        wear = parse_flags(obj.get("wear_flags"))
        two_handed = bool(parse_flags(obj.get("extra_flags")) & ExtraFlag.TWO_HANDED)
    except ValueError:
        return
    slots = [slot for flag, slot in WEAR_SLOTS.items() if wear & flag]
    if obj.get("item_type") == LIGHT_ITEM_TYPE:
        slots.append("light")
    cap, slot_text = equipment.item_cap(level, slots, two_handed)
    bonus = 0.0 if color is None else equipment.COLOR_BONUS[color]
    total = sum(n * p for _, n, p in terms)
    if total <= cap * bonus + 1e-9:
        return
    # 顯示：點數無條件進位、上限無條件捨去到小數 3 位，畫面上一定看得出點數比較大
    items = " ＋ ".join(f"{equipment.STAT_NAMES[s]} {n:+d} × {decimal_text(p)}" for s, n, p in terms)
    color_text = equipment.COLOR_NAMES[color] if color else "沒寫顏色（null）"
    problems.append(f"{where}放出物品 {number}「{obj.get('short')}」：加成點數 {items} ＝ {decimal_text(round_up(total))}，"
                    f"超過 {level} 級{slot_text}、{color_text}的上限 {decimal_text(round_down(cap))} × {decimal_text(bonus)} ＝ "
                    f"{decimal_text(round_down(cap * bonus))}（設計文件 §3.3）")


def round_up(x):
    return math.ceil(x * 1000 - 1e-9) / 1000


def round_down(x):
    return math.floor(x * 1000 + 1e-9) / 1000


def decimal_text(x):
    """最多小數 3 位，不要多餘的 0：3.741、20、1.2。"""
    return f"{x:.3f}".rstrip("0").rstrip(".")


class Found:
    """check_structure 找到、可以拿來做跨檔案檢查的東西。area_number 不對時全部是空的。"""

    def __init__(self):
        self.base = None                    # area_number
        self.kind = None                    # 格式沒問題的 header.type（AreaType）
        self.vnums = []                     # 號碼沒問題的房間（檔案號碼）
        self.exits = []                     # [(房間檔案號碼, 方向, to_room)]：格式沒問題的出口
        self.recall = None                  # 格式沒問題的 recall
        self.mobiles = []                   # 號碼沒問題的生物（檔案號碼）
        self.objects = []                   # 號碼沒問題的物品（檔案號碼）


def read_json(path, problems):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as e:
        problems.append(f"{Path(path).name}：讀不到，或不是正確的 JSON（{e}）")
        return None


def game_numbers(path, key="rooms"):
    """盡量算出一個檔案的房間（key="mobiles" 是生物）有哪些遊戲號碼（給對照用，格式不對的部分就略過）。"""
    data = read_json(path, [])
    try:
        base = data["area"]["header"]["area_number"]
        items = data[key]
    except (KeyError, TypeError):
        return []
    if not is_int(base) or not isinstance(items, list):
        return []
    return [base + r["vnum"] for r in items
            if isinstance(r, dict) and is_int(r.get("vnum")) and 1 <= r["vnum"] <= 99]


def area_kind(path):
    """盡量讀出一個檔案的 header.type（給對照用，讀不到就是 None）。"""
    data = read_json(path, [])
    try:
        return data["area"]["header"]["type"]
    except (KeyError, TypeError):
        return None


def check_keys(obj, keys, where, problems):
    """obj 要是 dict，而且欄位剛好是 keys。回傳 obj 是不是 dict。"""
    if not isinstance(obj, dict):
        problems.append(f"{where}要寫成 {{…}}，不能是 {obj!r}")
        return False
    problems += [f"{where}少了欄位 {k}" for k in keys if k not in obj]
    problems += [f"{where}多了不認得的欄位 {k}" for k in obj if k not in keys]
    return True


def check_structure(name, data, problems):
    """檢查一個檔案自己的結構，問題加進 problems。回傳 Found，給跨檔案檢查用。"""
    found = Found()
    if not check_keys(data, TOP_KEYS, f"{name}：檔案最上層", problems):
        return found
    if "schema_version" in data and not (is_int(data["schema_version"]) and data["schema_version"] == 1):
        problems.append(f"{name}：schema_version 要是 1，不能是 {data['schema_version']!r}")
    if "file" in data and data["file"] != name:
        problems.append(f"{name}：file 要寫實際的檔名 {name!r}，不能是 {data['file']!r}")
    base, recall, kind = check_area(name, data["area"], problems) if "area" in data else (None, None, None)
    found.kind = kind
    rooms = check_rooms(name, data, base, problems)
    mobiles = check_mobiles(name, data, base, problems)
    objects = check_objects(name, data, base, problems)
    check_resets(name, data, problems)
    if base is not None:                    # 沒有 area_number 就算不出遊戲號碼，跨檔案的檢查只好略過
        found.base, found.mobiles, found.objects = base, mobiles, objects
        if rooms is not None:               # rooms 整個不對時，房間的跨檔案檢查也略過
            found.vnums, found.exits = rooms
            found.recall = recall
    return found


def check_number(name, label, vnum, where, seen, base, problems):
    """檔案裡的號碼（房間、生物）：1～99、檔案裡不重複、遊戲號碼不小於 100。沒問題就記進 seen，回傳 True。"""
    if not (is_int(vnum) and 1 <= vnum <= 99):
        problems.append(f"{name}：{label}號碼 {vnum!r} 不在 1～99")
    elif vnum in seen:
        problems.append(f"{name}：{label} {vnum} 在這個檔案裡重複")
    elif base is not None and base + vnum < 100:
        problems.append(f"{where}的遊戲號碼是 area_number {base} ＋ {vnum} ＝ {base + vnum}，不能小於 100（1～99 是保留的）")
    else:
        seen.append(vnum)
        return True
    return False


def check_rooms(name, data, base, problems):
    """檢查 rooms。回傳 (號碼沒問題的房間, 格式沒問題的出口 [(房間, 方向, to_room)])；rooms 整個不對是 None。"""
    if "rooms" not in data:
        return None
    if not isinstance(data["rooms"], list):
        problems.append(f"{name}：rooms 要寫成 […]，不能是 {data['rooms']!r}")
        return None
    vnums, exits = [], []
    for i, r in enumerate(data["rooms"]):
        vnum = r.get("vnum") if isinstance(r, dict) else None
        where = f"{name}：房間 {vnum} " if is_int(vnum) else f"{name}：第 {i + 1} 間房間 "
        if not check_keys(r, ROOM_KEYS, where, problems):
            continue
        room_exits = check_room(where, r, problems)
        if "vnum" in r and check_number(name, "房間", vnum, where, vnums, base, problems):
            exits += [(vnum, d, to) for d, to in room_exits]
    return vnums, exits


def check_mobiles(name, data, base, problems):
    """檢查 mobiles。回傳號碼沒問題的生物（檔案號碼）。"""
    if "mobiles" not in data:
        return []
    if not isinstance(data["mobiles"], list):
        problems.append(f"{name}：mobiles 要寫成 […]，不能是 {data['mobiles']!r}")
        return []
    vnums = []
    for i, m in enumerate(data["mobiles"]):
        vnum = m.get("vnum") if isinstance(m, dict) else None
        where = f"{name}：生物 {vnum} " if is_int(vnum) else f"{name}：第 {i + 1} 隻生物 "
        if not check_keys(m, MOBILE_KEYS, where, problems):
            continue
        check_mobile(where, m, problems)
        if "vnum" in m:
            check_number(name, "生物", vnum, where, vnums, base, problems)
    return vnums


def check_area(name, area, problems):
    """檢查 area 區塊。回傳 (area_number, recall, type)，不對的就是 None。"""
    base = recall = kind = None
    if not check_keys(area, AREA_KEYS, f"{name}：area ", problems):
        return None, None, None
    header = area.get("header")
    if "header" in area and check_keys(header, HEADER_KEYS, f"{name}：area.header ", problems):
        levels = header.get("levels")
        if "levels" in header and not (isinstance(levels, list) and len(levels) == 2
                                       and all(is_int(x) for x in levels) and levels[0] <= levels[1]):
            problems.append(f"{name}：area.header.levels 要寫 [最低, 最高] 兩個整數，最低不能大於最高，不能是 {levels!r}")
        for k in ("author", "title"):
            if k in header and not isinstance(header[k], str):
                problems.append(f"{name}：area.header.{k} 要是字串，不能是 {header[k]!r}")
        if "area_number" in header:
            if is_int(header["area_number"]) and header["area_number"] >= 1:
                base = header["area_number"]
            else:
                problems.append(f"{name}：area.header.area_number 要是正整數（1～99 是保留的號碼，area_number 不能是 0），"
                                f"不能是 {header['area_number']!r}")
        if "type" in header:
            if header["type"] in codes(AreaType):
                kind = AreaType(header["type"])
            else:
                problems.append(f"{name}：area.header.type 要寫 {'、'.join(t.value for t in AreaType)} 其中一個，"
                                f"不能是 {header['type']!r}")
    if "recall" in area and area["recall"] is not None:
        if is_int(area["recall"]) and area["recall"] >= 1:
            recall = area["recall"]
        else:
            problems.append(f"{name}：area.recall 要是 null 或房間號碼，不能是 {area['recall']!r}")
    if "no_teleport" in area and not (area["no_teleport"] is None or (is_int(area["no_teleport"]) and area["no_teleport"] in (0, 1))):
        problems.append(f"{name}：area.no_teleport 要是 null、0 或 1，不能是 {area['no_teleport']!r}")
    for k in ("clan_recall", "gem"):
        if k in area and not (area[k] is None or (is_int(area[k]) and area[k] >= 0)):
            problems.append(f"{name}：area.{k} 要是 null 或不小於 0 的整數，不能是 {area[k]!r}")
    return base, recall, kind


def check_room(where, r, problems):
    """檢查一間房間（號碼以外的部分）。回傳格式沒問題的出口 [(方向, to_room)]，給跨檔案檢查用。"""
    if "name" in r and not (isinstance(r["name"], str) and r["name"].strip()):
        problems.append(f"{where}的 name 不能是空的")
    if "description" in r and not isinstance(r["description"], str):
        problems.append(f"{where}的 description 要是字串，不能是 {r['description']!r}")
    if "room_flags" in r:
        try:
            unknown = parse_flags(r["room_flags"]) & ~sum(RoomFlag)
        except ValueError as e:
            problems.append(f"{where}的 room_flags {e}")
        else:
            if unknown:
                bits = [1 << i for i in range(unknown.bit_length()) if unknown >> i & 1]
                problems.append(f"{where}的 room_flags 用了沒有的旗標 {bits}")
    if "sector" in r and not (is_int(r["sector"]) and r["sector"] in Sector):
        problems.append(f"{where}的 sector 要寫 0～{max(Sector)} 的整數，不能是 {r['sector']!r}")

    exits = []
    if "exits" in r:
        if not isinstance(r["exits"], dict):
            problems.append(f"{where}的 exits 要寫成 {{…}}，不能是 {r['exits']!r}")
        else:
            for d, e in r["exits"].items():
                if d not in DIRECTIONS:
                    problems.append(f"{where}的出口方向 {d!r} 不對（只能是 {'、'.join(DIRECTIONS)}）")
                elif check_exit(f"{where}往 {d} 的出口", e, problems):
                    exits.append((d, e["to_room"]))
    if "extra_descriptions" in r:
        check_extra_descriptions(where, r["extra_descriptions"], problems)
    if "script" in r and r["script"] is not None:
        check_script(f"{where}的 script ", r["script"], problems)
    return exits


def check_extra_descriptions(where, eds, problems):
    """可以細看的東西（房間和物品都有）：[{keywords, description}]。"""
    if not isinstance(eds, list):
        problems.append(f"{where}的 extra_descriptions 要寫成 […]，不能是 {eds!r}")
        return
    for j, ed in enumerate(eds):
        w = f"{where}的 extra_descriptions 第 {j + 1} 項"
        if check_keys(ed, EXTRA_KEYS, w, problems):
            if "keywords" in ed and not (isinstance(ed["keywords"], str) and ed["keywords"].split()):
                problems.append(f"{w}的 keywords 不能是空的")
            if "description" in ed and not isinstance(ed["description"], str):
                problems.append(f"{w}的 description 要是字串，不能是 {ed['description']!r}")


def check_exit(where, e, problems):
    """檢查一個出口。回傳 to_room 能不能拿來做跨檔案檢查。"""
    if not check_keys(e, EXIT_KEYS, where, problems):
        return False
    for k in ("description", "keywords"):
        if k in e and not isinstance(e[k], str):
            problems.append(f"{where}的 {k} 要是字串，不能是 {e[k]!r}")
    if "locks" in e and not (is_int(e["locks"]) and e["locks"] in Locks):
        problems.append(f"{where}的 locks 要是 0～{max(Locks)} 的整數，不能是 {e['locks']!r}")
    if "key" in e and not (is_int(e["key"]) and e["key"] >= -1):
        problems.append(f"{where}的 key 要是 -1、0 或物品號碼，不能是 {e['key']!r}")
    if "to_room" not in e:
        return False
    if not (is_int(e["to_room"]) and e["to_room"] >= 1):
        problems.append(f"{where}號碼 {e['to_room']!r} 不對")
        return False
    return True


def check_script(where, s, problems):
    """script 先保留，只檢查形狀：{"trigger": {"value": 整數, "names": [字串…]}, "function": 字串}。"""
    if not check_keys(s, SCRIPT_KEYS, where, problems):
        return
    if "trigger" in s and check_keys(s["trigger"], TRIGGER_KEYS, f"{where}的 trigger ", problems):
        t = s["trigger"]
        if "value" in t and not (is_int(t["value"]) and t["value"] >= 0):
            problems.append(f"{where}的 trigger.value 要是不小於 0 的整數，不能是 {t['value']!r}")
        if "names" in t and not (isinstance(t["names"], list) and all(isinstance(x, str) for x in t["names"])):
            problems.append(f"{where}的 trigger.names 要是字串的清單，不能是 {t['names']!r}")
    if "function" in s and not (isinstance(s["function"], str) and s["function"].strip()):
        problems.append(f"{where}的 function 不能是空的")


def check_objects(name, data, base, problems):
    """檢查 objects。回傳號碼沒問題的物品（檔案號碼）。"""
    if "objects" not in data:
        return []
    if not isinstance(data["objects"], list):
        problems.append(f"{name}：objects 要寫成 […]，不能是 {data['objects']!r}")
        return []
    vnums = []
    for i, o in enumerate(data["objects"]):
        vnum = o.get("vnum") if isinstance(o, dict) else None
        where = f"{name}：物品 {vnum} " if is_int(vnum) else f"{name}：第 {i + 1} 個物品 "
        if not check_keys(o, OBJECT_KEYS, where, problems):
            continue
        check_object(where, o, problems)
        if "vnum" in o:
            check_number(name, "物品", vnum, where, vnums, base, problems)
    return vnums


def check_object(where, o, problems):
    """檢查一個物品（號碼以外的部分）。只看寫法：數字代表什麼（種類、旗標、values…）還沒檢查，
    只有主手、副手不能同時寫。"""
    for k in ("keywords", "short"):
        if k in o and not (isinstance(o[k], str) and o[k].strip()):
            problems.append(f"{where}的 {k} 不能是空的")
    check_strs(where, o, ("long",), problems)
    check_ints(where, o, ("item_type", "weight", "cost"), problems)
    for k in ("extra_flags", "wear_flags"):
        if k in o:
            try:
                parse_flags(o[k])
            except ValueError as e:
                problems.append(f"{where}的 {k} {e}")
    # 主手、副手只能寫一個：兩個都寫會用主手的上限算點數，放到副手就多拿了點數（設計文件 §3.3）
    try:
        wear = parse_flags(o.get("wear_flags"))
    except ValueError:
        wear = 0
    if wear & WearFlag.WIELD and wear & WearFlag.SHIELD:
        problems.append(f"{where}的 wear_flags {o['wear_flags']!r} 同時有 8192 主手和 512 副手：武器只能放做出來的那一手，"
                        f"主手武器寫 8192，副手武器寫 512")
    # values：4 個，意思看物品種類；法術類物品的部分要寫法術名稱，所以可以是字串
    if "values" in o and not (isinstance(o["values"], list) and len(o["values"]) == 4
                              and all(is_int(v) or isinstance(v, str) for v in o["values"])):
        problems.append(f"{where}的 values 要寫 4 個數字或字串，不能是 {o['values']!r}")
    if "affects" in o:
        if not isinstance(o["affects"], list):
            problems.append(f"{where}的 affects 要寫成 […]，不能是 {o['affects']!r}")
        else:
            for j, a in enumerate(o["affects"]):
                w = f"{where}的 affects 第 {j + 1} 項"
                if check_keys(a, AFFECT_KEYS, w, problems):
                    check_ints(w, a, AFFECT_KEYS, problems)
    if "extra_descriptions" in o:
        check_extra_descriptions(where, o["extra_descriptions"], problems)
    if o.get("script") is not None:
        check_script(f"{where}的 script ", o["script"], problems)


def check_resets(name, data, problems):
    """檢查 resets，只看寫法。號碼指到的東西存不存在、G 前面有沒有 M、D 的出口有沒有門，都還沒檢查。"""
    if "resets" not in data:
        return
    if not isinstance(data["resets"], list):
        problems.append(f"{name}：resets 要寫成 […]，不能是 {data['resets']!r}")
        return
    for i, r in enumerate(data["resets"]):
        where = f"{name}：resets 第 {i + 1} 筆"
        cmd = r.get("cmd") if isinstance(r, dict) else None
        if not (isinstance(cmd, str) and cmd in RESET_KEYS):
            problems.append(f"{where}的 cmd 要是 {'、'.join(RESET_KEYS)} 其中一個，不能是 {cmd!r}")
            continue
        w = f"{where}（{cmd}）"
        if not check_keys(r, RESET_KEYS[cmd], w, problems):
            continue
        check_ints(w, r, ("rare", "limit", "if_flag", "state", "exit_count"), problems)
        check_strs(w, r, ("comment",), problems)
        for k in RESET_NUMBERS:
            if k in r and not (is_int(r[k]) and r[k] >= 1):
                problems.append(f"{w}的 {k} 號碼 {r[k]!r} 不對")
        if "direction" in r and r["direction"] not in DIRECTIONS:
            problems.append(f"{w}的 direction {r['direction']!r} 不對（只能是 {'、'.join(DIRECTIONS)}）")
        if "color" in r:
            check_color(w, r["color"], problems)
        # 物品的等級（設計文件 §3.3）：G 寫 null 是用前面那筆 M 的怪物等級；O、P 沒有怪物帶著，一定要寫
        if "level" in r and not (is_int(r["level"]) or (cmd == "G" and r["level"] is None)):
            allowed = "null（用前面那筆 M 的怪物等級）或整數" if cmd == "G" else "整數（O、P 沒有怪物帶著，一定要寫）"
            problems.append(f"{w}的 level 是物品的等級，要是 {allowed}，不能是 {r['level']!r}")


def check_color(where, color, problems):
    """裝備的顏色（掉落表、重置 G O P 的 color）：null（不是裝備）或 ItemColor 的代號。"""
    if color is not None and color not in codes(ItemColor):
        problems.append(f"{where}的 color 要是 null（不是裝備）或 {'、'.join(codes(ItemColor))} 其中一個，不能是 {color!r}")


def codes(cls):
    """一個代號定義（StrEnum）的全部代號。用 list 比對：寫成 [] 這種不能雜湊的值也不會出錯。"""
    return [c.value for c in cls]


def check_mob_codes(where, m, problems):
    """生物的 tier（必填）和 attack、defense、archetype（null 是預設）：只能寫手冊表裡的代號。"""
    if "tier" in m and m["tier"] not in codes(MobTier):
        problems.append(f"{where}的 tier 要寫 {'、'.join(codes(MobTier))} 其中一個，不能是 {m['tier']!r}")
    if "attack" in m and m["attack"] is not None and not is_attack(m["attack"]):
        problems.append(f"{where}的 attack 要是 null、{'、'.join(codes(AttackType))} 其中一個，"
                        f"或「主/次」兩個不一樣的（例如 \"dragon/phys\"），不能是 {m['attack']!r}")
    for k, cls in (("defense", Defense), ("archetype", Archetype)):
        if k in m and m[k] is not None and m[k] not in codes(cls):
            problems.append(f"{where}的 {k} 要是 null 或 {'、'.join(codes(cls))} 其中一個，不能是 {m[k]!r}")


def check_tier_roll(where, m, problems):
    """重生時骰種類（tier_roll，設計文件 §4.9）：null 是固定 tier。
    寫成 {種類: 機率}：種類不能是 tier 自己（剩下的機率就是它），機率是萬分之一，加起來不能超過 10000。"""
    roll = m.get("tier_roll")
    if roll is None:
        return
    if not isinstance(roll, dict):
        problems.append(f"{where}的 tier_roll 要是 null 或 {{種類: 機率}}，例如 {{\"boss\": 100}}，不能是 {roll!r}")
        return
    good = []
    for k, v in roll.items():
        if k not in codes(MobTier):
            problems.append(f"{where}的 tier_roll 的種類要是 {'、'.join(codes(MobTier))} 其中一個，不能是 {k!r}")
        elif k == m.get("tier"):
            problems.append(f"{where}的 tier_roll 不用寫基本種類 {k}（剩下的機率就是它）")
        if is_int(v) and 1 <= v <= CHANCE_MAX:
            good.append(v)
        else:
            problems.append(f"{where}的 tier_roll 的 {k} 要是 1～{CHANCE_MAX} 的整數（萬分之一，100 是 1%），不能是 {v!r}")
    if sum(good) > CHANCE_MAX:
        problems.append(f"{where}的 tier_roll 加起來是 {' ＋ '.join(map(str, good))} ＝ {sum(good)}，"
                        f"不能超過 {CHANCE_MAX}（100%）")


def check_drops(where, m, problems):
    """掉落表（drops，設計文件 §4.10）：每一行各自骰。沒有掉落寫 []。"""
    if "drops" not in m:
        return
    if not isinstance(m["drops"], list):
        problems.append(f"{where}的 drops 要寫成 […]（沒有掉落寫 []），不能是 {m['drops']!r}")
        return
    for i, d in enumerate(m["drops"]):
        w = f"{where}的 drops 第 {i + 1} 行"
        if not check_keys(d, DROP_KEYS, f"{w} ", problems):
            continue
        if "obj_vnum" in d and not (is_int(d["obj_vnum"]) and d["obj_vnum"] >= 1):
            problems.append(f"{w}的 obj_vnum 要是物品號碼，不能是 {d['obj_vnum']!r}")
        if "color" in d:
            check_color(w, d["color"], problems)
        if "chance" in d and not (is_int(d["chance"]) and 1 <= d["chance"] <= CHANCE_MAX):
            problems.append(f"{w}的 chance 要是 1～{CHANCE_MAX} 的整數（萬分之一，100 是 1%），不能是 {d['chance']!r}")
        tiers = d.get("tiers")
        if "tiers" in d and tiers is not None and not (
                isinstance(tiers, list) and tiers and all(t in codes(MobTier) for t in tiers) and len(set(tiers)) == len(tiers)):
            problems.append(f"{w}的 tiers 要是 null（所有種類都會掉）或不重複的種類清單（例如 [\"boss\"]），不能是 {tiers!r}")


def is_attack(value):
    """attack 的寫法：只用一種（"phys"），或主／次兩種不一樣的（"dragon/phys"，主 70%、次 30%）。"""
    if not isinstance(value, str):
        return False
    parts = value.split("/")
    return len(parts) in (1, 2) and all(p in codes(AttackType) for p in parts) and len(set(parts)) == len(parts)


def check_ints(where, obj, keys, problems):
    for k in keys:
        if k in obj and not is_int(obj[k]):
            problems.append(f"{where}的 {k} 要是整數，不能是 {obj[k]!r}")


def check_strs(where, obj, keys, problems):
    for k in keys:
        if k in obj and not isinstance(obj[k], str):
            problems.append(f"{where}的 {k} 要是字串，不能是 {obj[k]!r}")


def check_mobile(where, m, problems):
    """檢查一隻生物（號碼以外的部分）。只看寫法：數字代表什麼（旗標、性別、種族…）還沒檢查。"""
    for k in ("keywords", "short"):
        if k in m and not (isinstance(m[k], str) and m[k].strip()):
            problems.append(f"{where}的 {k} 不能是空的")
    check_strs(where, m, ("long", "description", "race"), problems)
    check_ints(where, m, ("level", "alignment", "sex", "position"), problems)
    check_mob_codes(where, m, problems)
    for k in ("act", "affected_by"):
        if k in m:
            try:
                parse_flags(m[k])
            except ValueError as e:
                problems.append(f"{where}的 {k} {e}")
    check_tier_roll(where, m, problems)
    check_drops(where, m, problems)
    if m.get("script") is not None:
        check_script(f"{where}的 script ", m["script"], problems)
    for k, keys, ints, strs in (("actions", ACTION_KEYS, ("when", "mode"), ("text",)),
                                ("fight_actions", FIGHT_KEYS, ("rate",), ("message", "command"))):
        if k not in m:
            continue
        if not isinstance(m[k], list):
            problems.append(f"{where}的 {k} 要寫成 […]，不能是 {m[k]!r}")
            continue
        for j, item in enumerate(m[k]):
            w = f"{where}的 {k} 第 {j + 1} 項"
            if check_keys(item, keys, w, problems):
                check_ints(w, item, ints, problems)
                check_strs(w, item, strs, problems)
    if m.get("shop") is not None and check_keys(m["shop"], SHOP_KEYS, f"{where}的 shop ", problems):
        shop = m["shop"]
        if "buy_types" in shop and not (isinstance(shop["buy_types"], list) and all(is_int(t) for t in shop["buy_types"])):
            problems.append(f"{where}的 shop 的 buy_types 要是整數的清單，不能是 {shop['buy_types']!r}")
        check_ints(f"{where}的 shop ", shop, ("profit_buy", "profit_sell", "open_hour", "close_hour"), problems)
    if m.get("special") is not None and not (isinstance(m["special"], str) and m["special"].strip()):
        problems.append(f"{where}的 special 要是 null 或函式名稱，不能是 {m['special']!r}")


def build_room(base, r):
    """把一個（已經檢查過的）房間變成 Room。"""
    exits = {d: resolve(base, e["to_room"]) for d, e in r["exits"].items()}
    exit_descriptions = {d: e["description"] for d, e in r["exits"].items()}
    # 名字用空白隔開（例如 "牌子 sign"），存成小寫，英文比對時不分大小寫
    extra_descriptions = [([k.lower() for k in ed["keywords"].split()], ed["description"])
                          for ed in r["extra_descriptions"]]
    return Room(base + r["vnum"], r["name"], r["description"], exits,
                RoomFlag(parse_flags(r["room_flags"])), Sector(r["sector"]), exit_descriptions, extra_descriptions)
