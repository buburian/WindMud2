"""商店（shops.py、commands/shops.py，設計文件 §3.7）：list、buy、sell、value 的每一句和檢查的順序、價格（人類、防刷錢、最低 1）、
開店時間、賣不完（每件重做）、只賣 G 給店主的、賣掉消失、buy_types、等級、容器、兩個店主、很暗、存檔。
"""
import re

import pytest

import mud.commands as commands
from area_helpers import make_area, make_mobile, make_object, make_room, write_json
from mud import equipment, light, objects, save, shops, stats, weather, zones
from mud.area import BUYER_LEVEL, RoomFlag
from mud.characters import Position, characters
from mud.commands import REFUSALS
from mud.config import ENCODING
from mud.players import Player

SHOP = {"buy_types": [5, 15], "profit_buy": 150, "profit_sell": 50, "open_hour": 6, "close_hour": 20}
UNREACHABLE = "test.json"                   # 測試區域：沒有路走得到，防刷錢的檢查不算它的店


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


def mob(vnum, short, keywords, shop=None, level=10):
    m = make_mobile(vnum)
    m.update(short=short, keywords=keywords, shop=shop, level=level, act=2, position=7, tier_roll=None, drops=[],
             special=None, long="")
    return m


def item(vnum, short, keywords, item_type, cost, values=(0, 0, 0, 0), wear="1", affects=()):
    o = make_object(vnum)
    o.update(short=short, keywords=keywords, item_type=item_type, cost=cost, values=list(values), wear_flags=wear,
             affects=list(affects), extra_descriptions=[], script=None)
    return o


def M(vnum, room):
    return {"cmd": "M", "rare": 0, "mob_vnum": vnum, "limit": 1, "room_vnum": room, "comment": ""}


def G(vnum, color=None, level=None):
    return {"cmd": "G", "rare": 0, "obj_vnum": vnum, "color": color, "level": level, "limit": 0, "comment": ""}


@pytest.fixture
def world(tmp_path, monkeypatch):
    """101：商人（賣麵包、長劍、箱子，收武器和容器）和男孩（賣藥水，什麼都不收）。102：野狗（不是店主，身上有麵包）。103：很暗，有商人 104。"""
    monkeypatch.setattr(weather, "current", weather.Weather(hour=12))
    saved = []
    monkeypatch.setattr(save, "save_player", saved.append)
    rooms = [make_room(101, north=102), make_room(102, south=101), make_room(103)]
    rooms[2]["room_flags"] = int(RoomFlag.DARK)
    mobs = [mob(101, "商人", "merchant", SHOP), mob(102, "男孩", "boy",
                                                  dict(SHOP, buy_types=[], profit_buy=100, profit_sell=100)),
            mob(103, "野狗", "dog"), mob(104, "暗商", "shade", SHOP)]
    objs = [item(101, "麵包", "bread", 19, 10, (1, "", 0, 0)),
            item(102, "長劍", "sword", 5, 0, (2, 0, 0, 3), "1|8192", [{"location": 1, "modifier": 1}]),
            item(103, "箱子", "box", 15, 20, (50, 0, 0, 0)),
            item(104, "藥水", "potion", 10, 400, (5, "fly", "", ""))]
    resets = [M(101, 101), G(101), G(102, "white", 1), G(103), M(102, 101), G(104), M(103, 102), G(101), M(104, 103), G(101)]
    write_json(tmp_path, "a.json", make_area("a.json", rooms, (100, 199), mobiles=mobs, objects=objs, resets=resets))
    zones.load(tmp_path)
    yield saved
    characters.clear()
    zones.stop()


def npc(vnum):
    return next(c for c in characters if getattr(c, "vnum", None) == vnum)


def person(name, room=101, race=stats.Race.ELF, gold=1000):
    p = Player(name, FakeWriter(), zones.world.rooms[room])
    p.race, p.guild = race, stats.Guild.SWORD
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.skills = []
    stats.set_level(p, 10)
    p.gold = gold
    characters.append(p)
    return p


def plain(p):
    text = re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))
    p.writer.data = b""
    return text


def say(p, line):
    plain(p)
    commands.command(p, line)
    return plain(p).rsplit("\r\n\r\n", 1)[0]


def mine(p, vnum):
    return [o for o in p.carrying if o.vnum == vnum]


# ---- 價格（設計文件 §3.7）----

def test_prices_follow_the_design(world):
    keeper, bread = npc(101), npc(101).carrying[-1]
    elf, human = person("Ming"), person("Wang", race=stats.Race.HUMAN)
    assert shops.buy_price(elf, keeper, bread) == 15                 # 10 × 150%
    assert shops.buy_price(human, keeper, bread) == 14               # × 0.90 ＝ 13.5，四捨五入
    box = next(o for o in keeper.carrying if o.vnum == 103)
    assert shops.sell_price(elf, keeper, box) == 10                  # 20 × 50%
    assert shops.sell_price(human, keeper, box) == 11                # × 1.10
    sword = next(o for o in keeper.carrying if o.vnum == 102)
    assert shops.buy_price(elf, keeper, sword) == stats.shown(objects.base_price(sword) * 1.5)   # 裝備是點數


def test_selling_never_pays_more_than_buying(world):
    keeper, box = npc(101), next(o for o in npc(101).carrying if o.vnum == 103)
    keeper.shop = dict(SHOP, profit_buy=100, profit_sell=120)
    human = person("Wang", race=stats.Race.HUMAN)
    assert shops.sell_price(human, keeper, box) == shops.buy_price(human, keeper, box) == 18      # 20 × 0.9；不是 20 × 1.2 × 1.1


def test_price_is_at_least_one(world):
    keeper, bread = npc(101), npc(101).carrying[-1]
    bread.cost = 0
    assert shops.buy_price(person("Ming"), keeper, bread) == 1


# ---- list ----

def test_list(world):
    ming = person("Ming")
    keeper = npc(101)
    lines = say(ming, "list").split("\r\n")
    assert lines[0] == "【 Lv    價格】 物品："
    assert lines[1:] == [f"【{o.level:>3} {shops.buy_price(ming, keeper, o):>7}】 {o.name}/{o.keywords[0]}" for o in keeper.carrying]
    assert lines[3] == "【 10      15】 麵包/bread"                 # G 沒寫等級：店主的等級
    assert lines[2].startswith("【  1 ")                             # G 寫了等級 1


def test_list_finds_by_name(world):
    ming = person("Ming")
    assert say(ming, "list bre") == "【 Lv    價格】 物品：\r\n【 10      15】 麵包/bread"
    assert say(ming, "list xyz") == "這裡沒有賣你想買的東西。"


def test_list_only_what_the_resets_gave(world):
    ming = person("Ming")
    keeper = npc(101)
    picked = objects.create(104, 1, None)                            # 店主撿到的：不賣
    keeper.carrying.insert(0, picked)
    assert "藥水" not in say(ming, "list")
    keeper.carrying = [picked]
    assert say(ming, "list") == "你不能夠在這裡買任何東西。"
    assert not any(o.for_sale for o in npc(103).carrying)          # 不是店主的生物，G 給的不是店裡的貨


def test_no_shopkeeper_here(world):
    ming = person("Ming", 102)
    for line in ("list", "buy bread", "sell bread", "value bread"):
        assert say(ming, line) == shops.NO_SHOP


def test_dark_room_has_no_shop(world):
    ming = person("Wang", 103, race=stats.Race.HUMAN)                # 精靈有夜視，看得到
    assert say(ming, "list") == shops.NO_SHOP
    assert say(person("Ming", 103), "list").startswith("【 Lv")
    torch = objects.Obj("火把", "", 1, ["torch"])
    torch.hours = -1
    ming.equipment["light"] = torch
    assert light.dark(ming.room) is False and say(ming, "list").startswith("【 Lv")


@pytest.mark.parametrize("hour, said", [(5, shops.NOT_YET), (6, None), (20, None), (21, shops.CLOSED)])
def test_opening_hours(world, monkeypatch, hour, said):
    monkeypatch.setattr(weather, "current", weather.Weather(hour=hour))
    ming = person("Ming")
    text = say(ming, "list")
    assert (text == f"商人說：『{said}』") if said else text.startswith("【 Lv")


def test_needs_standing(world):
    ming = person("Ming")
    ming.position = Position.RESTING
    assert say(ming, "buy bread") == REFUSALS[Position.RESTING]


# ---- buy ----

def test_buy_one(world):
    ming, wang = person("Ming"), person("Wang")
    keeper = npc(101)
    sword = next(o for o in keeper.carrying if o.vnum == 102)
    price = shops.buy_price(ming, keeper, sword)
    assert say(ming, "buy sword") == "你買下了【長劍/sword】。"
    assert "Ming買下了【長劍/sword】。" in plain(wang)
    [got] = mine(ming, 102)
    assert ming.gold == 1000 - price and got is not sword and not got.for_sale
    # 照區域檔重做一件：固定裝備的屬性一樣，武器傷害這時才算（展示的那件沒有）
    assert (got.level, got.color, got.affects, got.name) == (1, "white", sword.affects, "長劍")
    assert got.base and not sword.base
    assert sword in keeper.carrying                                   # 賣不完
    assert world == [ming]                                            # 買完存檔


def test_buy_several(world):
    ming = person("Ming")
    assert say(ming, "buy 3 bread") == "你一次買下了【3】個【麵包/bread】。"
    assert len(mine(ming, 101)) == 3 and ming.gold == 1000 - 45


@pytest.mark.parametrize("line, gold, want", [
    ("buy bread", 14, "商人告訴你：你沒有足夠的金幣買下【麵包/bread】。"),
    ("buy 3 bread", 30, "商人告訴你：你只能夠買下【2】個!!"),
    ("buy 3 bread", 14, "商人告訴你：好可憐，你連一個都買不起。"),
])
def test_not_enough_gold(world, line, gold, want):
    ming = person("Ming", gold=gold)
    assert say(ming, line) == want
    assert ming.gold == gold and not mine(ming, 101)


@pytest.mark.parametrize("line, want", [
    ("buy", "你想買什麼東西呢？"),
    ("buy xyz", "商人告訴你：我不賣那樣東西 -- 試試看【list】這個指令。"),
    ("buy 5", "商人告訴你：我不賣那樣東西 -- 試試看【list】這個指令。"),
    ("buy 0 bread", "你想要買多少樣？數字必須大於【0】。"),
    ("buy potion", "商人告訴你：我不賣那樣東西 -- 試試看【list】這個指令。"),      # 男孩賣的，商人沒有
])
def test_buy_mistakes(world, line, want):
    ming = person("Ming")
    assert say(ming, line) == want and ming.gold == 1000


def test_name_the_shopkeeper(world):
    ming = person("Ming")
    assert say(ming, "buy potion boy") == "你買下了【藥水/potion】。"
    assert ming.gold == 1000 - 400
    assert say(ming, "list bread boy") == "這裡沒有賣你想買的東西。"
    assert say(ming, "list all boy") == "【 Lv    價格】 物品：\r\n【 10     400】 藥水/potion"   # all 是全部（照 C 版）


def test_buy_needs_room(world):
    ming = person("Ming")
    ming.carrying = [objects.create(101, 1, None) for _ in range(stats.CARRY_COUNT - 2)]
    assert say(ming, "buy 3 bread") == "你沒有辦法攜帶這麼多的物品。"
    assert say(ming, "buy 2 bread").startswith("你一次買下了")
    ming.carrying = []
    npc(101).carrying[-1].weight = 1000
    assert say(ming, "buy bread") == "你沒有辦法攜帶這麼重的物品。"
    assert ming.gold == 1000 - 30


def test_buy_does_not_look_at_level(world):
    ming = person("Ming")
    stats.set_level(ming, 1)
    assert say(ming, "buy bread") == "你買下了【麵包/bread】。"         # 10 級的麵包，1 級也買得到（使用者選的）


# ---- sell、value ----

def test_sell(world):
    ming, wang = person("Ming"), person("Wang")
    box = objects.create(103, 1, None)
    ming.carrying.append(box)
    assert say(ming, "sell box") == "你賣掉【箱子/box】，老闆給了你【10】枚金幣。"
    assert "Ming賣掉【箱子/box】。" in plain(wang)
    assert ming.gold == 1010 and box not in ming.carrying
    assert not any(o is box for o in npc(101).carrying)              # 直接消失（使用者選的）
    assert world == [ming]


@pytest.mark.parametrize("verb", ["sell", "value"])
def test_sell_and_value_refuse_the_same_way(world, verb):
    ming = person("Ming")
    ming.carrying = [objects.create(101, 1, None), objects.create(102, 20, "white"), objects.create(103, 1, None)]
    ming.carrying[2].contains.append(objects.create(101, 1, None))
    assert say(ming, f"{verb} bread") == "商人絲毫沒有買下【麵包/bread】的興趣。"      # 不是 buy_types 的種類
    assert say(ming, f"{verb} sword") == "商人告訴你：你這東西的等級太高了，我買不起..!!"   # 20 級，店主 10 級
    assert say(ming, f"{verb} box") == "你要先把【箱子/box】裡面的東西拿出來。"
    assert say(ming, f"{verb} box boy") == "男孩絲毫沒有買下【箱子/box】的興趣。"   # buy_types 是空的：什麼都不收
    assert ming.gold == 1000 and len(ming.carrying) == 3


@pytest.mark.parametrize("line, want", [
    ("sell", "你想要賣掉些什麼？"),
    ("sell xyz", "商人告訴你：你沒有你所要賣的東西。"),
    ("value", "你想評估什麼物品的價錢？"),
    ("value xyz", "商人告訴你：你有這樣東西嗎？"),
])
def test_sell_and_value_mistakes(world, line, want):
    assert say(person("Ming"), line) == want


def test_value_is_what_sell_pays(world):
    ming = person("Wang", race=stats.Race.HUMAN)
    ming.carrying.append(objects.create(103, 1, None))
    assert say(ming, "value box") == "商人告訴你：我可以以【11】枚金幣的價錢買下【箱子/box】。"
    assert ming.gold == 1000 and mine(ming, 103)
    assert say(ming, "sell box") == "你賣掉【箱子/box】，老闆給了你【11】枚金幣。"


def test_colorless_things_are_priced_by_cost(world):
    keeper = npc(101)
    sword = next(o for o in keeper.carrying if o.vnum == 102)
    sword.color, sword.cost = None, 40                                # G 沒寫顏色：不算裝備，照 cost（使用者定的）
    assert shops.buy_price(person("Ming"), keeper, sword) == 60


def test_no_two_shops_in_the_real_areas_make_money():
    """真的 areas/：在一家買、拿去另一家賣，不能賺錢（人類、其他種族都是）。§3.7 的防刷錢只比同一家店，
    兩家店的倍率要區域作者自己顧（秋風城的毛皮店、珠寶店收購倍率因此調低過，使用者 2026-11-17 選的）。
    測試區域 test.json 的店不算：沒有路走得到，玩家去不了（使用者 2026-11-18 選的）。
    賣的是真的買到的那件：照買的人的等級（-1 的貨）做、隨機裝備當下抽（店裡的還沒抽，拿它去賣只值 1 枚），所以 1～100 級都算。"""
    import random
    from mud.config import AREA_DIR
    zones.load(AREA_DIR)
    try:
        keepers = [c for c in characters if getattr(c, "shop", None) and c.room.area.name != UNREACHABLE]
        rng, found = random.Random(7), []
        for race in stats.Race:
            ch = Player("Ming", FakeWriter(), None)
            ch.race = race
            for ch.level in range(1, 101):
                for a in keepers:
                    for obj in shops.stock(a):
                        pay = shops.buy_price(ch, a, obj)
                        for _ in range(3 if obj.unrolled else 1):
                            got = objects.create(obj.vnum, shops.goods_level(ch, obj), obj.color, rng)
                            for b in keepers:
                                if shops.buys(b, got) and got.level <= b.level and shops.sell_price(ch, b, got) > pay:
                                    found.append((race.value, ch.level, a.name, obj.name, b.name))
        assert any(o.unrolled and o.level == BUYER_LEVEL for a in keepers for o in shops.stock(a))   # 真的有 -1 的隨機裝備
        assert found == []
    finally:
        characters.clear()
        zones.stop()


# ---- 買的時候才抽屬性、level -1 是買的人的等級（使用者 2026-11-18 定的）----

@pytest.fixture
def goods(tmp_path, monkeypatch):
    """101：商人賣 5 級白色隨機盾牌、-1 的白色隨機盾牌、-1 的固定長劍、-1 的麵包（倍率 100%）；野狗（不是店主）身上 -1 的盾牌。"""
    monkeypatch.setattr(weather, "current", weather.Weather(hour=12))
    monkeypatch.setattr(save, "save_player", lambda p: None)
    shop = dict(SHOP, buy_types=[9], profit_buy=100, profit_sell=100)
    objs = [item(101, "麵包", "bread", 19, 10, (1, "", 0, 0)),
            item(102, "長劍", "sword", 5, 0, (2, 0, 0, 3), "1|8192", [{"location": 1, "modifier": 1}]),
            item(105, "盾牌", "shield", 9, 0, wear="1|512")]
    resets = [M(101, 101), G(105, "white", 5), G(105, "white", -1), G(102, "white", -1), G(101, None, -1),
              M(103, 101), G(105, "white", -1)]
    write_json(tmp_path, "a.json", make_area("a.json", [make_room(101)], (100, 199), objects=objs, resets=resets,
                                             mobiles=[mob(101, "商人", "merchant", shop), mob(103, "野狗", "dog", level=7)]))
    zones.load(tmp_path)
    yield npc(101)
    characters.clear()
    zones.stop()


def at_level(name, level):
    p = person(name)
    stats.set_level(p, level)
    return p


def full(level):
    """白色盾牌（副手）level 級、點數用滿的價錢（倍率 100%、不是人類）。"""
    return shops.price(objects.gear_price(equipment.cap(level, "offhand"), level))


def test_list_shows_only_the_name(goods):
    ming = at_level("Ming", 10)
    shields = [o for o in goods.carrying if o.vnum == 105]
    assert all(o.unrolled and o.affects == [] and o.name == "盾牌" for o in shields)
    lines = say(ming, "list").split("\r\n")
    assert lines[1:] == [f"【 10 {10:>7}】 麵包/bread",                                   # -1：自己的等級
                         f"【 10 {shops.price(objects.base_price(goods.carrying[1], 10)):>7}】 長劍/sword",
                         f"【 10 {full(10):>7}】 盾牌/shield",
                         f"【  5 {full(5):>7}】 盾牌/shield"]                               # 只有名字，看不到抽到什麼


def test_buyer_level_changes_the_price(goods):
    low, high = at_level("Ming", 10), at_level("Hua", 30)
    shield = goods.carrying[2]                                                             # -1 的盾牌
    assert (shops.goods_level(low, shield), shops.goods_level(high, shield)) == (10, 30)
    assert shops.buy_price(low, goods, shield) == full(10) < shops.buy_price(high, goods, shield) == full(30)
    sword = goods.carrying[1]                                                              # -1 的固定裝備：照買的人的等級算點數
    assert shops.buy_price(high, goods, sword) == shops.price(objects.base_price(sword, 30)) > shops.buy_price(low, goods, sword)
    assert shops.buy_price(high, goods, goods.carrying[0]) == 10                          # 不是裝備：照 cost


def test_buying_rolls_each_one(goods):
    ming = at_level("Ming", 30)
    assert say(ming, "buy 2 shield") == "你一次買下了【2】個【盾牌/shield】。"
    a, b = [o for o in ming.carrying if o.vnum == 105]
    for got in (a, b):
        assert got.level == 30 and got.affects and got.name.endswith("盾牌") and got.name != "盾牌"
        assert got.base and not got.unrolled and not got.for_sale
    assert a is not b and ming.gold == 1000 - 2 * full(30)
    assert all(o.unrolled for o in goods.carrying if o.vnum == 105)                       # 店裡的照舊沒抽


def test_selling_back_never_pays_more(goods):
    """抽出來的點數不會超過上限：買到的賣回去（100% 收）不會比買的貴。"""
    ming = at_level("Ming", 40)
    ming.gold = 10 ** 6
    for _ in range(20):
        say(ming, "buy 2.shield")                                                         # 5 級的那面
        say(ming, "buy shield")                                                           # -1 的那面
    for got in [o for o in ming.carrying if o.vnum == 105]:
        assert shops.sell_price(ming, goods, got) <= (full(5) if got.level == 5 else full(40))


def test_minus_one_for_an_ordinary_mob_is_its_level(goods):
    [shield] = npc(103).carrying
    assert shield.level == 7 and shield.affects and not shield.for_sale                  # 不是店主：跟 null 一樣，生物的等級
