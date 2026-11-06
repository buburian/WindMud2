"""give（commands/items.py，照 C 版 act_obj.c 的 do_give，使用者定的）：給東西、給金幣、店主不收、放不下、訊息、給完存檔。"""
import re

import pytest

import mud.commands as commands
from area_helpers import make_area, make_mobile, make_object, make_room, write_json
from mud import objects, save, stats, zones
from mud.characters import Position, characters
from mud.config import ENCODING
from mud.npcs import Npc
from mud.players import Player


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


@pytest.fixture
def world(tmp_path, monkeypatch):
    """房間 101、102 南北相連；102 有野狗和商人（店主）。物品 101 藥水（重 1）、102 石頭（重 200）。"""
    monkeypatch.setattr(save, "PLAYER_DIR", str(tmp_path / "players"))
    objs = []
    for vnum, short, keywords, weight in ((1, "藥水", "potion 藥水", 1), (2, "石頭", "rock 石頭", 200)):
        o = make_object(vnum)
        o.update(short=short, keywords=keywords, item_type=13, wear_flags="1", extra_flags=0, values=[0, 0, 0, 0],
                 weight=weight, affects=[])
        objs.append(o)
    mobs = []
    for vnum, short, keywords, shop in ((1, "野狗", "dog 野狗", None), (2, "商人", "merchant 商人", make_mobile(1)["shop"])):
        m = make_mobile(vnum)
        m.update(short=short, keywords=keywords, level=1, tier="normal", tier_roll=None, attack=None, defense=None,
                 archetype=None, act=0, position=7, sex=0, long="", drops=[], shop=shop)
        mobs.append(m)
    resets = [{"cmd": "M", "rare": 0, "mob_vnum": v, "limit": 1, "room_vnum": 2, "comment": ""} for v in (1, 2)]
    write_json(tmp_path, "a.json", make_area("a.json", [make_room(1, north=2), make_room(2, south=1)], 100,
                                             mobiles=mobs, resets=resets, objects=objs))
    zones.load(tmp_path)
    yield tmp_path
    characters.clear()
    zones.stop()


def person(name, level=1, room=102):
    p = Player(name, FakeWriter(), zones.world.rooms[room])
    p.race, p.guild = stats.Race.HUMAN, stats.Guild.SWORD
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.password = save.hash_password("secret")
    stats.set_level(p, level)
    characters.append(p)
    return p


def mob(name):
    return next(c for c in characters if isinstance(c, Npc) and c.name == name)


def potion():
    return objects.create(101, 1, None)


def plain(p):
    text = re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))
    p.writer.data = b""
    return text


def say(p, line):
    plain(p)
    commands.command(p, line)
    return plain(p).rsplit("\r\n\r\n", 1)[0]


# ---- 給東西 ----

def test_give_to_a_player(world):
    ming, hua, lin = person("Ming", level=2), person("Hua"), person("Lin")
    ming.carrying.append(potion())
    plain(hua), plain(lin)
    assert say(ming, "gi potion hua") == "你把【藥水/potion】拿給Hua。"
    assert "Ming把【藥水/potion】拿給你。" in plain(hua) and "Ming將【藥水/potion】拿給Hua。" in plain(lin)
    assert ming.carrying == [] and [o.name for o in hua.carrying] == ["藥水"]
    assert [d["name"] for d in save.load_data("Ming")["carrying"]] == []    # 給完幫給的人存檔（照 C 版）


def test_give_to_a_creature(world):
    ming = person("Ming")
    ming.carrying.append(potion())
    assert say(ming, "give potion dog") == "你把【藥水/potion】拿給野狗。"
    assert [o.name for o in mob("野狗").carrying] == ["藥水"]


def test_shopkeepers_refuse(world):
    ming, hua = person("Ming"), person("Hua")
    ming.carrying.append(potion())
    plain(hua)
    assert say(ming, "give potion merchant") == "商人拒絕拿【藥水/potion】。"
    assert "Ming想要拿【藥水/potion】給商人，但是它拒絕了。" in plain(hua)              # 商人是中性：它
    assert [o.name for o in ming.carrying] == ["藥水"] and mob("商人").carrying == []


@pytest.mark.parametrize("line, want", [
    ("give", "你想把什麼物品給誰？"),
    ("give potion", "你想把什麼物品給誰？"),
    ("give rock hua", "你沒有這樣東西。"),
    ("give potion bird", "他們不在這裡。"),
])
def test_give_mistakes(world, line, want):
    ming = person("Ming")
    person("Hua")
    ming.carrying.append(potion())
    assert say(ming, line) == want
    assert [o.name for o in ming.carrying] == ["藥水"]


def test_the_player_must_have_room(world):
    ming, hua = person("Ming"), person("Hua")
    ming.carrying.append(objects.create(102, 1, None))                # 石頭重 200，人類 1 級拿不動
    assert say(ming, "give rock hua") == "Hua沒辦法攜帶這麼重的物品。"
    hua.carrying = [potion() for _ in range(stats.CARRY_COUNT)]
    ming.carrying = [potion()]
    assert say(ming, "give potion hua") == "Hua沒辦法攜帶這麼多的物品。"
    assert len(ming.carrying) == 1


def test_creatures_have_no_limits(world):
    ming = person("Ming")
    ming.carrying.append(objects.create(102, 1, None))
    assert say(ming, "give rock dog") == "你把【石頭/rock】拿給野狗。"   # 生物不檢查件數、負重


def test_give_needs_to_be_awake(world):
    ming = person("Ming")
    ming.position = Position.SLEEPING
    assert say(ming, "give potion dog") == "在你的睡夢中嗎？"


# ---- 給金幣 ----

def test_give_gold(world):
    ming, hua, lin = person("Ming", level=2), person("Hua"), person("Lin")
    ming.gold = 1000
    plain(hua), plain(lin)
    assert say(ming, "give 300 coins hua") == "你給Hua一些金幣。"
    assert "Ming給你【300】枚金幣。" in plain(hua) and "Ming給Hua一些金幣。" in plain(lin)
    assert (ming.gold, hua.gold) == (700, 300)
    assert save.load_data("Ming")["gold"] == 700                       # 給完存檔
    assert say(ming, "give 5 c dog") == "你給野狗一些金幣。" and mob("野狗").gold == 5   # coins 可以縮寫，生物也收


@pytest.mark.parametrize("line, want", [
    ("give 0 coins hua", "抱歉，你不能這樣做。"),
    ("give -5 coins hua", "抱歉，你不能這樣做。"),
    ("give 5 gold hua", "抱歉，你不能這樣做。"),
    ("give 5 coins", "你想把什麼物品給誰？"),
    ("give 5 coins bird", "他們不在這裡。"),
    ("give 5000 coins hua", "你沒有這麼多金幣。"),
])
def test_give_gold_mistakes(world, line, want):
    ming, hua = person("Ming", level=2), person("Hua")
    ming.gold = 1000
    assert say(ming, line) == want
    assert (ming.gold, hua.gold) == (1000, 0)


def test_level_one_cannot_give_gold(world):
    ming, hua = person("Ming"), person("Hua")
    ming.gold = 1000
    assert say(ming, "give 10 coins hua") == "你的等級不足以給人金幣。" and hua.gold == 0


def test_big_gifts_are_logged(world, caplog):
    ming, hua = person("Ming", level=2), person("Hua")
    ming.gold = 2_000_000
    with caplog.at_level("INFO"):
        say(ming, "give 1000000 coins hua")
    assert "Ming 給了 Hua 1000000 枚金幣" in caplog.text
