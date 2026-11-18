"""商店（設計文件 §3.7，使用者 2026-11-17 定的；規則在玩家角色手冊「商店」）：找店主、開店時間、賣什麼、價格。指令在 commands/shops.py。

- 店主：區域檔的生物寫了 shop（npc.shop）。同一間房、看得到的店主照 look 的順序找，可以用名字指定。
- 賣的東西：重置 G 給店主的（Obj.for_sale），賣不完：買到的是那一件的複製品。
  店主自己撿到的不賣；玩家賣給店的直接消失（使用者選的）。
- 價格：基本價格（objects.base_price：有顏色的裝備照點數和等級算，其他是 cost）× 這家店的倍率（%），人類再乘種族技能「交易」，四捨五入、最低 1。
  賣得的錢最多等於這個人向這家店買同一件要付的錢（防刷錢，§3.7）。
"""
from . import light, names, objects, stats, weather
from .characters import in_room

TRADE_BUY = 0.90                            # 人類的種族技能「交易」：向商店買 ×0.90（玩家角色手冊的種族表，§3.6）
TRADE_SELL = 1.10                           # 賣給商店 ×1.10
NO_SHOP = "你不能在這裡買東西啊。"            # 照 C 版 find_keeper
NOT_YET = "抱歉，現在還不到小店的營業時間。"
CLOSED = "抱歉，已經打烊了，明天請早。"


def keepers(ch):
    """ch 看得到的店主，照 look 的順序（很暗看不到就沒有）。"""
    return [c for c in in_room(ch) if getattr(c, "shop", None) and light.visible(ch, c)]


def find_keeper(ch, name=""):
    """name 沒寫是第一個店主；寫了是那個名字的店主（跟找生物一樣：開頭就行、2.boy）。找不到是 None。"""
    found = keepers(ch)
    if not name:
        return found[0] if found else None
    return names.pick(found, name, lambda c: c.names())


def closed(keeper):
    """還沒開或已經關了：店主要說的那句；開著是 None。用遊戲時間，open_hour～close_hour 兩頭都算開著（照 C 版）。"""
    hour, shop = weather.current.hour, keeper.shop
    if hour < shop["open_hour"]:
        return NOT_YET
    if hour > shop["close_hour"]:
        return CLOSED
    return None


def stock(keeper):
    """店裡賣的東西（重置 G 給店主的），照背包的順序。"""
    return [o for o in keeper.carrying if o.for_sale]


def buys(keeper, obj):
    """這家店收不收這種東西：buy_types 裡有它的物品種類（空的就什麼都不收）。"""
    return obj.item_type in keeper.shop["buy_types"]


def human(ch):
    return getattr(ch, "race", None) == stats.Race.HUMAN


def price(x):
    """價格是整數：四捨五入，最低 1 枚金幣。"""
    return max(1, stats.shown(x))


def buy_price(ch, keeper, obj):
    """ch 向 keeper 買 obj 要付的錢：基本價格 × profit_buy%，人類 × TRADE_BUY。"""
    return price(objects.base_price(obj) * keeper.shop["profit_buy"] / 100 * (TRADE_BUY if human(ch) else 1))


def sell_price(ch, keeper, obj):
    """ch 把 obj 賣給 keeper 拿到的錢：基本價格 × profit_sell%，人類 × TRADE_SELL；最多等於他向這家店買同一件要付的錢。"""
    offer = price(objects.base_price(obj) * keeper.shop["profit_sell"] / 100 * (TRADE_SELL if human(ch) else 1))
    return min(offer, buy_price(ch, keeper, obj))
