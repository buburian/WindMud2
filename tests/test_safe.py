"""安全區（RoomFlag.SAFE）：kill、use 傷害技能都不能開打（訊息照 C 版、不扣消耗），增益技能可以用，別的房間照打。"""
import asyncio
import re

import pytest

import mud.commands as commands
from area_helpers import make_area, make_mobile, make_room, write_json
from mud import fight, skills, stats, zones
from mud.area import RoomFlag
from mud.characters import characters
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
    """101 安全區 —北— 102，兩間各有一隻狗。"""
    monkeypatch.setattr(fight, "TICK_SECONDS", 1000)
    rooms = [make_room(101, north=102), make_room(102, south=101)]
    rooms[0]["room_flags"] = int(RoomFlag.SAFE)
    dog = make_mobile(101)
    dog.update(short="野狗", keywords="dog", act=2, position=7, drops=[], special=None, shop=None, long="")
    resets = [{"cmd": "M", "rare": 0, "mob_vnum": 101, "limit": 2, "room_vnum": v, "comment": ""} for v in (101, 102)]
    write_json(tmp_path, "a.json", make_area("a.json", rooms, (100, 199), mobiles=[dog], resets=resets))
    zones.load(tmp_path)
    yield zones.world
    characters.clear()
    zones.stop()


def fighter(room=101):
    p = Player("Ming", FakeWriter(), zones.world.rooms[room])
    p.race, p.guild = stats.Race.HUMAN, stats.Guild.SWORD
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.skills = skills.starter(p.guild)
    stats.set_level(p, 1)
    characters.append(p)
    return p


def say(p, line):
    commands.command(p, line)
    text = re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))
    p.writer.data = b""
    return text.rsplit("\r\n\r\n", 1)[0]


PROTECTED = "野狗正在受到神力所保護的房間內。"


def test_no_kill_in_a_safe_room(world):
    ming = fighter()
    assert say(ming, "kill dog") == PROTECTED
    assert ming.fighting is None


def test_no_damage_skill_and_no_cost(world):
    ming = fighter()
    mv = ming.mv
    assert say(ming, "use smash dog") == PROTECTED
    assert ming.fighting is None and ming.mv == mv and not ming.cooldowns


def test_buff_skills_still_work(world):
    ming = fighter()
    skills.learn(ming, skills.SKILLS["aegis"])
    say(ming, "use aegis")
    assert ming.affects


def test_other_rooms_fight_as_usual(world):
    ming = fighter(102)

    async def main():
        say(ming, "kill dog")
        return ming.fighting

    assert isinstance(asyncio.run(main()), Npc)
