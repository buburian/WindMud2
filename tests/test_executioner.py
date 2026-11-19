"""秋風城神殿大廳的執法者（真的 areas/midgaard.json 和 midgaard/執法者.lua，使用者 2026-11-19 要的）：
沒有光源的玩家走進來，密語告訴他雜貨店怎麼走；不到 5 級又不到 20 金幣的，先送 3 支火把。
也測雜貨店的火把：1 級、遊戲裡 120 小時（現實 1 小時）、20 金幣（人類 18），雜貨店不收照明用具。
"""
import re
from pathlib import Path

import pytest

import mud.commands as commands
from mud import objects, save, scripts, shops, skills, stats, weather, zones
from mud.characters import characters
from mud.config import ENCODING
from mud.npcs import Npc
from mud.players import Player

AREAS = Path(__file__).resolve().parent.parent / "areas"
SQUARE, HALL, GROCERY = 3005, 3001, 3010    # 神殿廣場（往北是大廳）、神殿大廳（執法者）、雜貨店
TORCH, LANTERN, BANNER = 3030, 3031, 3365
WAY = "執法者告訴你：雜貨店有賣火把：往南走 3 步、往東 2 步，再往北 1 步就到了。"
GIFT = "執法者告訴你：城外天黑得快，這幾支火把先拿去用。"


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


@pytest.fixture
def errors(tmp_path, monkeypatch):
    """載入真的 areas/；回傳腳本出錯的清單（沒出錯，「沒說話」才不是因為腳本壞了）。"""
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path)
    monkeypatch.setattr(weather, "current", weather.Weather(hour=12))
    found = []
    monkeypatch.setattr(scripts, "report", lambda r, msg: found.append(msg))
    zones.load(AREAS)
    yield found
    characters.clear()
    zones.stop()


def player(level=1, gold=0, room=SQUARE, race=stats.Race.ELF):
    p = Player("Ming", FakeWriter(), zones.world.rooms[room])
    p.race, p.guild = race, stats.Guild.SWORD
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.skills = skills.starter(p.guild)
    stats.set_level(p, level)
    p.gold = gold
    characters.append(p)
    return p


def walk_in(p):
    commands.command(p, "n")
    assert p.room is zones.world.rooms[HALL]
    return re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))


def torches(p):
    return [o for o in p.carrying if o.vnum == TORCH]


def test_newbie_without_money_gets_three_torches(errors):
    p = player(level=4, gold=19)
    out = walk_in(p)
    assert [o.level for o in torches(p)] == [1, 1, 1]
    assert out.count("執法者把【火把/torch】拿給你。") == 3 and GIFT in out and WAY in out
    assert out.index(GIFT) < out.index(WAY)                                 # 先送，再說怎麼走
    assert errors == []


@pytest.mark.parametrize("level, gold", [(1, 20), (5, 0)])
def test_others_only_hear_the_way(errors, level, gold):
    """買得起（20 金幣以上）、或已經 5 級：只說雜貨店怎麼走。"""
    p = player(level=level, gold=gold)
    out = walk_in(p)
    assert WAY in out and GIFT not in out and torches(p) == []
    assert errors == []


@pytest.mark.parametrize("vnum, wear", [(TORCH, False), (LANTERN, True), (BANNER, False)])
def test_anyone_with_a_light_hears_nothing(errors, vnum, wear):
    """背包裡、身上（光源位置）有火把、燈籠、戰旗：不密語（使用者要的：看有沒有光源）。"""
    p = player()
    light = objects.create(vnum, 1, None)
    if wear:
        p.equipment["light"] = light
    else:
        p.carrying.append(light)
    out = walk_in(p)
    assert "執法者告訴你" not in out and len(p.carrying) == (0 if wear else 1)
    assert errors == []


def test_any_light_counts_not_just_these_numbers(errors):
    """看的是物品種類（照明用具），不是號碼（使用者要的：之後會有別的光源）；放在袋子裡也算有。"""
    p = player()
    other = objects.create(TORCH, 1, None)
    other.vnum = 99999                                                       # 假裝是別的區域做的光源
    bag = objects.create(TORCH, 1, None)
    bag.item_type, bag.vnum = 15, 99998                                     # 一個袋子，光源放在裡面
    bag.contains.append(other)
    p.carrying.append(bag)
    out = walk_in(p)
    assert "執法者告訴你" not in out and errors == []


def test_mobiles_get_nothing(errors):
    dog = Npc("野狗", 0, zones.world.rooms[SQUARE])
    characters.append(dog)
    commands.command(dog, "n")
    assert dog.carrying == [] and errors == []


def test_torch_in_the_grocery(errors):
    """雜貨店的火把：1 級就能用、遊戲裡 120 小時（一小時 30 秒 ＝ 現實 1 小時）、20 金幣（人類 18）；雜貨店不收照明用具。"""
    grocer = next(c for c in characters if isinstance(c, Npc) and c.room is zones.world.rooms[GROCERY] and c.shop)
    torch = next(o for o in shops.stock(grocer) if o.vnum == TORCH)
    elf, human = player(level=1), player(level=1, race=stats.Race.HUMAN)
    assert shops.goods_level(elf, torch) == 1 and objects.create(TORCH, 1, None).hours == 120
    assert (shops.buy_price(elf, grocer, torch), shops.buy_price(human, grocer, torch)) == (20, 18)
    assert not shops.buys(grocer, objects.create(TORCH, 1, None))        # 執法者送的火把不能拿去賣（使用者選的）
    assert not shops.buys(grocer, objects.create(BANNER, 1, None))
