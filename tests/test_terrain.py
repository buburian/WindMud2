"""地形（terrain.py）和飛翔術、水中呼吸術：每一種擋法、有船、有飛行、現在站的房間也算、生物不受限制、
游泳和飛行的訊息、flee 不挑走不過去的出口、窒息（扣血、護盾、死掉、imm 不會）、兩個技能的資料和消失的訊息。

坑：日夜照現實時間算，水、空中的房間晚上會暗（look 只有一句），所以都固定在白天。
"""
import asyncio
import re

import pytest

import mud.commands as commands
from area_helpers import make_area, make_mobile, make_object, make_room, write_json
from mud import affects, fight, skills, stats, terrain, weather, zones
from mud.area import AffectFlag
from mud.characters import characters
from mud.commands import combat as combat_commands
from mud.config import CHOKE_TICKS, ENCODING
from mud.npcs import Npc
from mud.players import Player

FLY, BREATHE = skills.SKILLS["fly"], skills.SKILLS["breathe"]


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


class FakeRng:
    """flee 一定成功；choice() 記下可以選的出口，挑第一個。"""

    def __init__(self):
        self.seen = None

    def random(self):
        return 0.0

    def choice(self, seq):
        self.seen = list(seq)
        return seq[0]


@pytest.fixture
def world(tmp_path, monkeypatch):
    """101 室內：北 102 空中、東 103 要船的水、南 104 水底、西 105 可游泳的水 —西— 106 可游泳的水。101 有一隻狗、一艘船的原型 101。"""
    monkeypatch.setattr(weather, "current", weather.Weather(hour=12))
    monkeypatch.setattr(zones, "START_ROOM", 101)
    monkeypatch.setattr(fight, "TICK_SECONDS", 1000)
    rooms = [make_room(101, north=102, east=103, south=104, west=105), make_room(102, south=101),
             make_room(103, west=101), make_room(104, north=101), make_room(105, east=101, west=106),
             make_room(106, east=105)]
    for r, sector in zip(rooms[1:], (9, 7, 8, 6, 6)):
        r["sector"] = sector
    dog = make_mobile(101)
    dog.update(short="野狗", keywords="dog", act=2, position=7, drops=[], special=None, shop=None, long="")
    boat = make_object(101)
    boat.update(short="木筏", keywords="raft", item_type=22, wear_flags="1", values=[0, 0, 0, 0], affects=[],
                extra_descriptions=[], script=None)
    resets = [{"cmd": "M", "rare": 0, "mob_vnum": 101, "limit": 1, "room_vnum": 101, "comment": ""}]
    write_json(tmp_path, "a.json", make_area("a.json", rooms, (100, 199), mobiles=[dog], objects=[boat], resets=resets))
    zones.load(tmp_path)
    yield zones.world
    characters.clear()
    zones.stop()


def person(name, room=101, imm=False):
    p = Player(name, FakeWriter(), zones.world.rooms[room])
    p.race, p.guild, p.imm = stats.Race.HUMAN, stats.Guild.SWORD, imm
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.skills = []
    stats.set_level(p, 1)
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


def the_dog():
    return next(c for c in characters if isinstance(c, Npc))


def give(p, skill):
    affects.add(p, skills.make_affect(skill))


# ---- 擋下來 ----

@pytest.mark.parametrize("way, message", [("n", terrain.NEED_FLY), ("e", terrain.NEED_BOAT), ("s", terrain.NEED_GILLS)])
def test_blocked_without_the_flag(world, way, message):
    ming = person("Ming")
    assert say(ming, way) == message
    assert ming.room.vnum == 101


@pytest.mark.parametrize("skill, way, to", [(FLY, "n", 102), (FLY, "e", 103), (BREATHE, "s", 104)])
def test_the_skill_lets_you_in(world, skill, way, to):
    ming = person("Ming")
    give(ming, skill)
    say(ming, way)
    assert ming.room.vnum == to


def test_a_boat_in_the_backpack(world):
    from mud import objects
    ming = person("Ming")
    ming.carrying.append(objects.create(101, 1, None))
    say(ming, "e")
    assert ming.room.vnum == 103


@pytest.mark.parametrize("room, way, message", [(102, "s", terrain.NEED_FLY), (103, "w", terrain.NEED_BOAT),
                                                (104, "n", terrain.NEED_GILLS)])
def test_the_room_you_stand_in_counts_too(world, room, way, message):
    """照 C 版：在空中、水裡時間到了（沒有旗標），往陸地也走不出去，要用 recall。"""
    ming = person("Ming", room)
    assert say(ming, way) == message
    assert ming.room.vnum == room
    say(ming, "recall")
    assert ming.room.vnum == 101


def test_creatures_are_not_limited(world):
    dog = the_dog()
    commands.command(dog, "north")
    assert dog.room.vnum == 102


def test_creatures_flag_counts(world):
    assert affects.has_flag(Npc("鳥", 0, None), AffectFlag.FLYING) is False
    bird = Npc("鳥", 0, None)
    bird.affected_by = AffectFlag.FLYING
    assert affects.has_flag(bird, AffectFlag.FLYING)


# ---- 走路的訊息 ----

def test_flying_in(world):
    ming, wang = person("Ming"), person("Wang", 102)
    give(ming, FLY)
    say(ming, "n")
    assert "Ming從南邊飛了過來。" in plain(wang)


def test_swimming(world):
    ming, wang, chen = person("Ming", 105), person("Wang", 105), person("Chen", 106)
    say(ming, "w")
    assert "Ming游向西方。" in plain(wang)
    assert "Ming從東邊游了過來。" in plain(chen)


def test_walking_into_water_from_land(world):
    ming, wang, chen = person("Ming"), person("Wang"), person("Chen", 105)
    say(ming, "w")
    assert "Ming朝西離開。" in plain(wang)                           # 從陸地走：照常
    assert "Ming從東邊游了過來。" in plain(chen)


# ---- flee ----

def test_flee_only_picks_exits_you_can_go(world, monkeypatch):
    rng = FakeRng()
    monkeypatch.setattr(combat_commands, "rng", rng)
    ming = person("Ming")

    async def main():
        fight.start_fight(ming, the_dog())
        say(ming, "flee")

    asyncio.run(main())
    assert rng.seen == ["west"] and ming.room.vnum == 105


# ---- 窒息 ----

def test_choking_under_water(world):
    ming, wang = person("Ming", 104), person("Wang", 104)
    give(wang, BREATHE)
    top = ming.panel["hp"]
    terrain.choke()
    assert ming.hp == pytest.approx(top * 0.9)
    assert wang.hp == wang.panel["hp"]
    assert re.search(r"你無法呼吸[.!]\(\d+\)", plain(ming))
    assert "Ming因窒息而口吐白沫" in plain(wang)


def test_imms_and_dry_land_do_not_choke(world):
    boss, ming = person("Boss", 104, imm=True), person("Ming", 105)
    terrain.choke()
    assert boss.hp == boss.panel["hp"] and ming.hp == ming.panel["hp"]


def test_a_shield_takes_the_choking_first(world):
    ming = person("Ming", 104)
    affects.add(ming, skills.make_affect(skills.SKILLS["aegis"]))
    terrain.choke()
    assert ming.hp == ming.panel["hp"]
    assert "吸收" in plain(ming)


def test_choking_to_death(world):
    ming = person("Ming", 104)
    ming.hp = 1
    terrain.choke()
    assert ming.room.vnum == 101 and ming.hp == 1                      # 死掉回起始房間
    assert "你已經含恨死去了" in plain(ming)


def test_the_world_tick_chokes(world, monkeypatch):
    calls = []
    monkeypatch.setattr(terrain, "choke", lambda: calls.append(zones.world.ticks))
    for _ in range(CHOKE_TICKS * 2):
        zones.world.tick()
    assert len(calls) == 2


# ---- 兩個技能 ----

@pytest.mark.parametrize("skill, flag, off", [(FLY, AffectFlag.FLYING, "你的腳緩慢的降回地面。"),
                                              (BREATHE, AffectFlag.GILLS, "你不能在水下呼吸了。")])
def test_flag_skills(world, skill, flag, off):
    assert (skill.kind, skill.target, skill.starter, skill.imm_only, skill.cooldown, skill.cost) == \
        ("buff", "ally", (), False, 0, 0)
    ming = person("Ming")
    skills.learn(ming, skill)
    say(ming, f"use {skill.id}")
    assert affects.has_flag(ming, flag)
    a = ming.affects[0]
    assert a.duration == 1800
    a.ticks = 1
    plain(ming)
    affects.tick()
    assert not affects.has_flag(ming, flag)
    assert off in plain(ming)


def test_skills_list_shows_the_flag(world):
    ming = person("Ming")
    skills.learn(ming, FLY)
    assert "飛行" in say(ming, "skills")
