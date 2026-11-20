"""系統區域檔（header.type 是 system，號碼 1～99）裡程式要用的東西（使用者 2026-11-20 定的，學 C 版的 limbo.are）。

屍體、金幣、召喚物的名字和描述寫在區域檔（areas/system.json），程式只記號碼：改文字改區域檔就好。
開機時 zones.load() 用 check() 看每個號碼都在、物品的種類對，少了就停止開機。號碼表在區域製作手冊「系統區域檔」。
"""
from .area import CORPSE_NPC_ITEM_TYPE, ITEM_TYPE_NAMES, MONEY_ITEM_TYPE

# 物品（號碼照 C 版 limbo：OBJ_VNUM_MONEY_ONE、MONEY_SOME、CORPSE_NPC）
MONEY_ONE = 2                               # 一枚金幣：屍體裡只有 1 枚時（objects.money）
MONEY_SOME = 3                              # 一些金幣：2 枚以上
CORPSE = 10                                 # 怪物的屍體（objects.make_corpse）：short、long 裡的 NAME_CODE 換成死掉的怪的名字
# 生物
SKELETON = 1                                # 喚骨術叫的骷髏（summons.py）
DEATH_KNIGHT = 2                            # 死亡騎士叫的死亡騎士

NAME_CODE = "$n"                            # 屍體的名字、地上那一句裡換成怪的名字（跟訊息的 $n 一樣）

OBJECTS = {MONEY_ONE: (MONEY_ITEM_TYPE, "一枚金幣"), MONEY_SOME: (MONEY_ITEM_TYPE, "一些金幣"),
           CORPSE: (CORPSE_NPC_ITEM_TYPE, "怪物的屍體")}       # 號碼 → (要是哪種物品, 是什麼)
MOBILES = {SKELETON: "喚骨術的骷髏", DEATH_KNIGHT: "死亡騎士"}   # 號碼 → 是什麼


def check(objects, mobiles):
    """objects、mobiles（遊戲號碼 → 區域檔的物品、生物，zones.load 收好的）裡有沒有程式要的號碼。回傳問題的清單。"""
    problems = []
    for vnum, (item_type, what) in OBJECTS.items():
        o = objects.get(vnum)
        if o is None:
            problems.append(f"系統區域檔少了物品 {vnum}（{what}）")
        elif o["item_type"] != item_type:
            problems.append(f"系統區域檔的物品 {vnum}（{what}）的 item_type 要是 {item_type}（{ITEM_TYPE_NAMES[item_type]}），"
                            f"不能是 {o['item_type']!r}")
    problems += [f"系統區域檔少了生物 {vnum}（{what}）" for vnum, what in MOBILES.items() if vnum not in mobiles]
    return problems
