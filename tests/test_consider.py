"""consider（commands/combat.do_consider、damage.power_gap，使用者 2026-11-19 要的）：拒絕的訊息、7 句的分段、
戰力換算成等級差（跟設計文件 §4.3、§4.7 對得上）、受傷／聖光／護盾、打不中、不改任何東西。
"""
import math

import pytest

import mud.commands as commands
from area_helpers import make_area, make_mobile, make_room, write_json
from mud import affects, combat, damage, zones
from mud.area import AffectFlag
from mud.characters import Position, characters
from mud.commands import REFUSALS
from mud.commands import combat as combat_commands
from mud.commands import system
from mud.config import ENCODING
from mud.npcs import Npc
from test_combat import fighter


def mob(vnum, short, keywords, level, tier="normal"):
    m = make_mobile(vnum)
    m.update(short=short, keywords=keywords, level=level, tier=tier, tier_roll=None, attack=None, defense=None,
             archetype=None, act=0, position=7, sex=0, long="", drops=[])
    return m


@pytest.fixture
def world(tmp_path, monkeypatch):
    """房間 101、102；102 有 5 級的野狗、6 級的老狗、5 級菁英的狼、5 級首領的熊、另一隻 5 級的野狗（都不走動：act 0 但沒有 tick）。"""
    mobs = [mob(101, "野狗", "dog", 5), mob(102, "老狗", "hound", 6), mob(103, "灰狼", "wolf", 5, "elite"),
            mob(104, "大熊", "bear", 5, "boss")]
    reset = [{"cmd": "M", "rare": 0, "mob_vnum": v, "limit": 2, "room_vnum": 102, "comment": ""} for v in (101, 102, 103, 104, 101)]
    write_json(tmp_path, "a.json", make_area("a.json", [make_room(101, north=102), make_room(102, south=101)], (100, 199),
                                             mobiles=mobs, resets=reset))
    monkeypatch.setattr(zones, "START_ROOM", 101)
    zones.load(tmp_path)
    yield
    characters.clear()
    zones.stop()


def npc(vnum, n=0):
    return [c for c in characters if isinstance(c, Npc) and c.vnum == vnum][n]


def say(p, line):
    p.writer.data = b""
    commands.command(p, line)
    return p.writer.data.decode(ENCODING).split("\r\n")[0]


def test_refusals(world):
    ming, hua = fighter("Ming"), fighter("Hua")
    assert say(ming, "consider") == "你想考慮要殺誰啊？"                     # 照 C 版
    assert say(ming, "consider nobody") == "找不到你想攻擊的人。"            # 跟 kill 一樣
    assert say(ming, "consider hua") == "你不可以攻擊玩家。"
    assert say(ming, "consider ming") == "你不可以攻擊玩家。"               # 自己也是


def test_abbreviation():
    for word in ("co", "con", "cons"):                                       # consider 排在 config 前面（使用者要的）
        assert commands.find(word) is combat_commands.do_consider
    assert commands.find("conf") is system.do_config


@pytest.mark.parametrize("gap, want", [
    (-math.inf, "你可以毫不費力的對付野狗。"), (-5.01, "你可以毫不費力的對付野狗。"),
    (-5, "野狗根本不是你的對手。"), (-2.01, "野狗根本不是你的對手。"),
    (-2, "野狗看起來滿容易對付的。"), (-0.51, "野狗看起來滿容易對付的。"),
    (-0.5, "野狗是一個好對手!"), (0, "野狗是一個好對手!"), (0.49, "野狗是一個好對手!"),
    (0.5, "野狗說，除非你有點運氣。"), (1.49, "野狗說，除非你有點運氣。"),
    (1.5, "野狗大笑，不把你放在眼裡。"), (2.99, "野狗大笑，不把你放在眼裡。"),
    (3, "你將會受到死神的眷顧。"), (math.inf, "你將會受到死神的眷顧。"),
])
def test_seven_sentences(world, monkeypatch, gap, want):
    """每段包含下限、不含上限（手冊的表）。"""
    monkeypatch.setattr(damage, "power_gap", lambda a, d: gap)
    assert say(fighter("Ming"), "consider dog") == want


def test_power_gap_matches_the_design(world):
    """戰力換算成等級差：同樣的怪 0、高 1 級 1、同級的菁英 3.6、首領 4.2（設計文件 §4.3 的等效等級差）。"""
    dog = npc(101)
    assert damage.power_gap(dog, npc(101, 1)) == 0
    assert damage.power_gap(dog, npc(102)) == pytest.approx(1.0, abs=0.02)
    assert damage.power_gap(dog, npc(103)) == pytest.approx(3.6, abs=0.1)
    assert damage.power_gap(dog, npc(104)) == pytest.approx(4.2, abs=0.1)
    assert damage.power_gap(npc(102), dog) == pytest.approx(-damage.power_gap(dog, npc(102)))   # 反過來看是負的


def test_hurt_sanctuary_and_shield(world):
    """受傷、對方有聖光：對方相對變強；自己有護盾：變弱。HP 少一半 ＝ 戰力少一半 ＝ log 2 ÷ log 1.30 級。"""
    ming, dog = fighter("Ming", level=5), npc(101)
    base = damage.power_gap(ming, dog)
    half = math.log(2) / math.log(1.30)
    ming.hp /= 2
    assert damage.power_gap(ming, dog) == pytest.approx(base + half)
    ming.hp *= 2
    dog.affected_by = AffectFlag.SANCTUARY                                   # 打牠的傷害減一半
    assert damage.power_gap(ming, dog) == pytest.approx(base + half)
    dog.affected_by = AffectFlag(0)
    ming.affects.append(affects.Affect("aegis", "天護", 10, shield=ming.hp))  # 護盾 ＝ 多一倍的 HP
    assert damage.power_gap(ming, dog) == pytest.approx(base - half)


def test_cannot_hit(world):
    """打不中的那邊戰力是 0：你打不中是死神那句，牠打不中是第一句，兩邊都打不中是好對手。"""
    ming, dog = fighter("Ming", level=5), npc(101)
    ming.panel["hit"] = 0
    assert say(ming, "consider dog") == "你將會受到死神的眷顧。"
    dog.panel["hit"] = 0
    assert say(ming, "consider dog") == "野狗是一個好對手!"
    ming.panel["hit"] = 100
    assert say(ming, "consider dog") == "你可以毫不費力的對付野狗。"


def test_only_looking(world, monkeypatch):
    """consider 只是看：不開打、不改 HP、不用戰鬥的亂數；休息時可以，睡覺不行。"""
    class NoDice:
        def random(self):
            raise AssertionError("consider 不能用到戰鬥的亂數")
    monkeypatch.setattr(combat, "rng", NoDice())
    ming, dog = fighter("Ming", level=5), npc(101)
    before = (ming.hp, dog.hp)
    ming.position = Position.RESTING
    assert say(ming, "consider dog") == "你將會受到死神的眷顧。"           # 裸裝 ≈ 低 8.8 級，一般怪 ≈ 低 3.6 級（§4.3、§4.4）
    assert (ming.hp, dog.hp) == before and ming.fight is None and dog.fight is None and ming.position == Position.RESTING
    ming.position = Position.SLEEPING
    assert say(ming, "consider dog") == REFUSALS[Position.SLEEPING]
