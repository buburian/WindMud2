"""金幣掉落（玩家角色手冊「金幣」，使用者 2026-11-18 定的）：公式和種類倍率、屍體裡的金幣、拿起來變成身上的金幣。"""
import logging
import re

import pytest

import mud.commands as commands
from area_helpers import make_area, make_mobile, make_object, make_room, write_json
from mud import combat, death, inventory, objects, stats, weather, zones
from mud.area import MONEY_ITEM_TYPE, MobTier
from mud.characters import characters
from mud.config import ENCODING
from mud.npcs import Npc
from mud.players import Player

LOW, HIGH = 0.0, 0.999999999                # rng.random() 最小、最大：±10% 的兩頭


class Rng:
    """假的亂數：random() 一律回傳 x，randint 回傳最小值，randrange 回傳 0（掉落表每一行都掉）；記下叫了哪些。"""

    def __init__(self, x=0.5):
        self.x, self.calls = x, []

    def random(self):
        self.calls.append("random")
        return self.x

    def randint(self, a, _):
        self.calls.append("randint")
        return a

    def randrange(self, _):
        self.calls.append("randrange")
        return 0


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


class Out:
    """自動拾取的訊息收在這裡（combat.loot 的 out）。"""

    def __init__(self):
        self.pairs = []

    def tell(self, pairs):
        self.pairs += pairs


# ---- 公式 ----

@pytest.mark.parametrize("x", [LOW, 0.25, 0.5, 0.75, HIGH])
def test_level_one_normal_mob_drops_two_or_three(x):
    assert stats.drop_gold(1, MobTier.NORMAL, Rng(x)) in (2, 3)


def test_both_ends_of_the_spread():
    assert stats.drop_gold(1, MobTier.NORMAL, Rng(LOW)) == 2 and stats.drop_gold(1, MobTier.NORMAL, Rng(HIGH)) == 3
    assert 4000 <= stats.drop_gold(100, MobTier.NORMAL, Rng(LOW)) < stats.drop_gold(100, MobTier.NORMAL, Rng(HIGH)) <= 5000


def test_spread_is_ten_percent():
    middle = stats.drop_gold(50, MobTier.NORMAL, Rng(0.5))
    assert stats.drop_gold(50, MobTier.NORMAL, Rng(LOW)) == stats.shown(middle * 0.9)
    assert stats.drop_gold(50, MobTier.NORMAL, Rng(HIGH)) == pytest.approx(middle * 1.1, abs=1)


@pytest.mark.parametrize("tier, ratio", [
    (MobTier.TRASH, 0.0214), (MobTier.NORMAL, 1.0), (MobTier.ELITE, 2.364), (MobTier.BOSS, 2.525),
])
def test_tiers_follow_the_exp(tier, ratio):
    """使用者選的：種類倍率照經驗的比例（同級打這種怪的經驗 ÷ 打一般怪的）。"""
    assert stats.gold_ratio(tier) == pytest.approx(ratio, abs=0.001)
    exp = stats.kill_exp(30, 30, tier, early=False) / stats.kill_exp(30, 30, MobTier.NORMAL, early=False)
    assert stats.gold_ratio(tier) == pytest.approx(exp)


def test_low_trash_drops_nothing():
    assert stats.drop_gold(1, MobTier.TRASH, Rng(HIGH)) == 0
    assert stats.drop_gold(20, MobTier.TRASH, Rng(HIGH)) == 0
    assert stats.drop_gold(40, MobTier.TRASH, Rng(LOW)) >= 1


# ---- 屍體 ----

@pytest.fixture
def world(tmp_path, monkeypatch):
    """房間 101：野狗（生物 101，5 級一般怪，掉治療藥水）。物品 101 治療藥水、102 一小堆錢（區域檔的金錢，20 枚）。"""
    monkeypatch.setattr(weather, "current", weather.Weather(hour=12))
    dog = make_mobile(101)
    dog.update(short="野狗", keywords="dog", level=5, tier="normal", tier_roll=None, position=7, act=0, long="", shop=None,
               drops=[{"obj_vnum": 101, "color": None, "chance": 10000, "tiers": None}])
    potion = make_object(101)
    potion.update(short="治療藥水", keywords="potion", item_type=10, wear_flags="1", values=[5, "fly", "", ""], weight=1,
                  affects=[], extra_descriptions=[], script=None)
    coins = make_object(102)
    coins.update(short="一小堆錢", keywords="coins gold", long="一小堆錢散落在地上", item_type=MONEY_ITEM_TYPE,
                 wear_flags="1", values=[20, 0, 0, 0], affects=[], extra_descriptions=[], script=None)
    resets = [{"cmd": "M", "rare": 0, "mob_vnum": 101, "limit": 1, "room_vnum": 101, "comment": ""}]
    write_json(tmp_path, "a.json", make_area("a.json", [make_room(101), make_room(102)], (100, 199),
                                             mobiles=[dog], objects=[potion, coins], resets=resets))
    zones.load(tmp_path)
    yield next(c for c in characters if isinstance(c, Npc))
    characters.clear()
    zones.stop()


def money_in(corpse):
    return [o for o in corpse.contains if o.item_type == MONEY_ITEM_TYPE]


def test_corpse_has_the_coins_last(world):
    rng = Rng(0.5)
    corpse = objects.make_corpse(world, rng)
    want = stats.drop_gold(5, MobTier.NORMAL, Rng(0.5))
    assert [o.name for o in corpse.contains] == ["治療藥水", "一些金幣"]
    coins = corpse.contains[-1]
    assert (coins.coins, coins.keywords, coins.long, coins.take) == (want, ["coins", "gold"], "一堆金幣被遺留在地上。", True)
    assert rng.calls[-1] == "random"                                    # 最後才骰：原本的亂數順序不變


def test_one_coin():
    one, two = objects.money(1), objects.money(2)
    assert (one.name, one.keywords, one.long, one.coins) == ("一枚金幣", ["coin", "gold"], "一枚金幣被留在地上。", 1)
    assert (two.name, two.coins, two.cost, two.weight) == ("一些金幣", 2, 0, 0)     # 價格 0（照 C 版）


def test_given_gold_goes_into_the_corpse(world):
    world.gold = 100
    corpse = objects.make_corpse(world, Rng(0.5))
    assert money_in(corpse)[0].coins == stats.drop_gold(5, MobTier.NORMAL, Rng(0.5)) + 100 and world.gold == 0


def test_shopkeepers_drop_gold_too(world):
    world.shopkeeper = True
    world.carrying = [objects.create(101, 5, None)]
    corpse = objects.make_corpse(world, Rng(0.5))
    assert [o.name for o in corpse.contains] == ["治療藥水", "一些金幣"]     # 店裡的東西消失，掉落表和金幣照掉


def test_no_coins_when_it_is_zero(world, monkeypatch):
    monkeypatch.setattr(stats, "drop_gold", lambda *args: 0)
    assert money_in(objects.make_corpse(world, Rng())) == []
    bare = Npc("石像", 0, world.room)                                   # 測試直接建的生物：沒有種類，不掉
    assert bare.tier is None and money_in(objects.make_corpse(bare, Rng())) == []


# ---- 拿起來 ----

def person(name, room, carrying=0):
    """有屬性的玩家（才會檢查件數、負重），背包裡 carrying 顆石頭。"""
    p = Player(name, FakeWriter(), room)
    p.race, p.guild = stats.Race.ELF, stats.Guild.SWORD
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.skills = []
    stats.set_level(p, 10)
    p.page_lines = 60
    for _ in range(carrying):
        stone = objects.Obj("石頭", "一顆石頭在這裡。", 13, ["stone"])
        stone.take, stone.weight = True, 1
        p.carrying.append(stone)
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


def killed(dog, gold=None):
    """野狗死了，屍體裡的金幣改成 gold 枚（None 照骰的）。"""
    corpse = death.die(dog, Rng(0.5))
    if gold is not None:
        money_in(corpse)[0].coins = gold
    return corpse


def test_get_coins_from_the_corpse(world):
    ming, hua = person("Ming", world.room), person("Hua", world.room)
    corpse = killed(world, 37)
    plain(hua)
    assert say(ming, "get coins corpse") == "你把【一些金幣/coins gold】從【野狗的屍體/corpse】拿出來。\r\n你估算一下裡面共有【37】枚金幣。"
    assert ming.gold == 37 and ming.carrying == [] and money_in(corpse) == []      # 變成身上的金幣，不進背包
    assert "Ming把【一些金幣/coins gold】從【野狗的屍體/corpse】拿出來。" in plain(hua)
    assert "（0/35 件，" in say(ming, "inventory")


def test_one_coin_has_no_estimate(world):
    ming = person("Ming", world.room)
    corpse = killed(world)
    corpse.contains[-1] = objects.money(1)
    assert say(ming, "get coin corpse") == "你把【一枚金幣/coin gold】從【野狗的屍體/corpse】拿出來。"
    assert ming.gold == 1


def test_get_all_from_the_corpse(world):
    ming = person("Ming", world.room)
    killed(world, 37)
    assert say(ming, "get all corpse") == ("你把【治療藥水/potion】從【野狗的屍體/corpse】拿出來。\r\n"
                                           "你把【一些金幣/coins gold】從【野狗的屍體/corpse】拿出來。\r\n你估算一下裡面共有【37】枚金幣。")
    assert ming.gold == 37 and [o.name for o in ming.carrying] == ["治療藥水"]


def test_a_full_pack_still_takes_the_coins(world):
    ming = person("Ming", world.room, carrying=stats.CARRY_COUNT)
    corpse = killed(world, 37)
    assert say(ming, "get all corpse") == ("【治療藥水/potion】你不能攜帶這麼多的物品。\r\n"           # 拿不動說一次
                                           "你把【一些金幣/coins gold】從【野狗的屍體/corpse】拿出來。\r\n你估算一下裡面共有【37】枚金幣。")
    assert ming.gold == 37 and [o.name for o in corpse.contains] == ["治療藥水"]
    corpse.contains.append(objects.money(5))
    assert say(ming, "get coins corpse").startswith("你把【一些金幣/coins gold】") and ming.gold == 42


def test_autoloot_takes_the_coins(world):
    ming = person("Ming", world.room)
    ming.autoloot = True
    corpse = killed(world, 37)
    out = Out()
    combat.loot(out, ming, corpse)
    assert [t for who, t in out.pairs if who is ming][-1] == "你估算一下裡面共有【37】枚金幣。"
    assert ming.gold == 37 and corpse.contains == []


def test_coins_on_the_floor(world):
    ming = person("Ming", world.room)
    world.room.contents.insert(0, objects.money(20))
    assert "一堆金幣被遺留在地上。/coins gold" in say(ming, "look")
    assert say(ming, "get coins") == "你拿起了【一些金幣/coins gold】。\r\n你估算一下裡面共有【20】枚金幣。"
    assert ming.gold == 20 and world.room.contents == []


def test_money_from_the_area_file(world):
    """區域檔的金錢物品（物品種類 20）：values 第 1 個是幾枚。"""
    ming = person("Ming", world.room)
    pile = objects.create(102, 1, None)
    assert pile.coins == 20
    world.room.contents.insert(0, pile)
    assert say(ming, "get coins") == "你拿起了【一小堆錢/coins gold】。\r\n你估算一下裡面共有【20】枚金幣。"
    assert ming.gold == 20


def test_a_million_is_logged(world, caplog):
    ming = person("Ming", world.room)
    world.room.contents.insert(0, objects.money(1_000_000))
    with caplog.at_level(logging.INFO):
        say(ming, "get coins")
    assert ming.gold == 1_000_000 and "Ming 拿到 1000000 枚金幣" in caplog.text


def test_coins_never_count(world):
    """金錢不會在背包裡，所以件數、負重也不用算它。"""
    ming = person("Ming", world.room, carrying=stats.CARRY_COUNT)
    world.room.contents.insert(0, objects.money(3))
    assert inventory.over_limit(ming, world.room.contents[0]) == "count"   # 一般的檢查會擋
    assert say(ming, "get coins").startswith("你拿起了【一些金幣") and ming.gold == 3
