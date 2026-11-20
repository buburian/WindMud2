"""套裝（使用者 2026-11-20 定的，設計文件 §3.4 第 7 條；規則在區域製作手冊「套裝表」、玩家角色手冊「套裝」）。

套裝表是區域資料夾裡的 sets.json（area.SET_FILE，檢查在 area.check_sets()），zones.load() 讀進來；資料夾裡沒有就是沒有套裝。
- 套裝的物品做出來（objects.create）一律綠色、等級照套裝表、拾取後綁定，名字前面加「〔套裝名〕」。
- 身上穿齊表上每一件（照物品號碼）才有特效（stats.recompute 加進去）：
  加多少 ＝ 無條件捨去（SHARE × 每一件的點數加起來 ÷ 那個屬性每 +1 要幾點），每一件的點數跟 equipment.roll_item 的一樣
  （套裝等級、部位的上限 × 綠色的加成，有必出主詞綴再加 extra_points），所以每次都一樣。
  玩家等級超過「套裝等級 ＋ EXPIRE_LEVELS」就沒有。
"""
import json
import math
from pathlib import Path
from typing import NamedTuple

from . import equipment
from .area import SET_FILE, ItemColor, wear_slots

SHARE = 0.5                                 # 特效值這套總點數的 50%（使用者 2026-11-20 定的）
EXPIRE_LEVELS = 10                          # 玩家等級超過套裝等級 ＋ 10 就失效（12 級的套裝 22 級還有、23 級沒有）
COLOR = ItemColor.GREEN
NAME_TAG = "〔{}〕"                          # 物品名字前面加的套裝名


class Set(NamedTuple):
    name: str
    level: int
    items: tuple                            # 物品號碼
    bonus: str                              # 穿齊時加哪一個屬性（equipment.AFFIX_WORD 的代號）


table = []                                  # 載入的套裝（照 sets.json 的順序）
by_item = {}                                # 物品號碼 → Set


def load(directory):
    """讀 directory 裡的 sets.json（zones.load 檢查過了才呼叫）；沒有這個檔就是沒有套裝。"""
    global table, by_item
    path = Path(directory) / SET_FILE
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"sets": []}
    table = [Set(s["name"], s["level"], tuple(s["items"]), s["bonus"]) for s in data["sets"]]
    by_item = {v: s for s in table for v in s.items}


def set_of(vnum):
    """物品號碼 vnum 是哪一套的；不是套裝是 None。"""
    return by_item.get(vnum)


def piece_points(proto, level):
    """套裝的一件（區域檔的物品）在套裝等級的點數：跟做出來時 roll_item 用的一樣（部位上限 × 綠色的加成，必出主詞綴再多 30%）。"""
    budget = equipment.cap(level, equipment.best_slot(*wear_slots(proto))) * equipment.COLOR_BONUS[COLOR]
    return budget + (equipment.extra_points(budget, COLOR) if proto["main_affix"] else 0.0)


def strength(s):
    """穿齊 s 時加多少：無條件捨去（SHARE × 每一件的點數加起來 ÷ 那個屬性每 +1 要幾點）。紅布獵手是命中 +6。"""
    from .objects import protos             # 坑：objects 會 import 這個模組，在函式裡才 import
    total = sum(piece_points(protos[v], s.level) for v in s.items)
    return math.floor(SHARE * total / equipment.price(s.bonus, s.level) + 1e-9)


def worn(ch, s):
    """ch 身上穿了 s 的幾件（照物品號碼，兩件一樣的算一件）。"""
    on = {o.vnum for o in getattr(ch, "equipment", {}).values()}
    return sum(1 for v in s.items if v in on)


def active(ch):
    """ch 身上有特效的套裝：每一件都穿上了，而且等級沒有超過套裝等級 ＋ EXPIRE_LEVELS。"""
    return [s for s in table if worn(ch, s) == len(s.items) and ch.level <= s.level + EXPIRE_LEVELS]
