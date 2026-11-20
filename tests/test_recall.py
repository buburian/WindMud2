"""recall（/）：回到自己的返回點（沒設定是起始房間）、區域檔寫了 recall 就用區域的（副本先回入口）、
no_recall 的房間、打架中和休息不能用、已經在那裡、找不到、旁人的訊息、存檔的返回點、到了觸發 on_enter。
學生不能用的測試在 test_academy.py（要真的學院）。
"""
import asyncio
import re

import pytest

import mud.commands as commands
from area_helpers import make_area, make_mobile, make_room, write_json
from mud import fight, save, scripts, stats, zones
from mud.area import RoomFlag
from mud.characters import Position, characters
from mud.commands import REFUSALS
from mud.commands.system import RECALL_ARRIVE, RECALL_LEAVE, RECALL_LOST, RECALL_PRAY, RECALL_REFUSED
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
    """世界 a.json：101（起始房間）—北— 102（no_recall）、101 —東— 103（有一隻狗）。副本 b.json：201，recall 寫 101。"""
    monkeypatch.setattr(zones, "START_ROOM", 101)
    monkeypatch.setattr(fight, "TICK_SECONDS", 1000)
    rooms = [make_room(101, north=102, east=103), make_room(102, south=101), make_room(103, west=101)]
    rooms[1]["room_flags"] = int(RoomFlag.NO_RECALL)
    dog = make_mobile(101)
    dog.update(short="野狗", keywords="dog", act=2, position=7, drops=[], special=None, shop=None, long="")
    resets = [{"cmd": "M", "rare": 0, "mob_vnum": 101, "limit": 1, "room_vnum": 103, "comment": ""}]
    write_json(tmp_path, "a.json", make_area("a.json", rooms, (100, 199), mobiles=[dog], resets=resets))
    inst = make_area("b.json", [make_room(201)], (200, 299), kind="instance")
    inst["area"]["recall"] = 101
    write_json(tmp_path, "b.json", inst)
    zones.load(tmp_path)
    yield zones.world
    characters.clear()
    zones.stop()


def person(name, room=103):
    p = Player(name, FakeWriter(), zones.world.rooms[room])
    p.race, p.guild = stats.Race.HUMAN, stats.Guild.SWORD
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.skills, p.password = [], save.hash_password("secret")
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


@pytest.mark.parametrize("line", ["recall", "rec", "/"])
def test_recall_goes_to_the_start_room(world, line):
    ming = person("Ming")
    assert say(ming, line).startswith("【房間101】")
    assert ming.room.vnum == 101


def test_what_others_see(world):
    ming, wang, chen = person("Ming"), person("Wang"), person("Chen", 101)
    say(ming, "recall")
    left = plain(wang)
    assert RECALL_PRAY.replace("$n", "Ming") in left and RECALL_LEAVE.replace("$n", "Ming") in left
    assert RECALL_ARRIVE.replace("$n", "Ming") in plain(chen)


def test_own_recall_point(world):
    ming = person("Ming", 101)
    ming.recall = 103
    say(ming, "/")
    assert ming.room.vnum == 103


def test_the_area_recall_comes_first(world):
    """區域檔寫的 recall 比自己的返回點先：這個副本寫的是世界的 101（區域作者也可以寫副本裡的房間），離開副本以後才回自己的返回點（103）。"""
    async def main():
        ming = person("Ming", 101)
        ming.recall = 103
        ming.room = zones.instance("b.json", "Ming").rooms[201]
        say(ming, "recall")
        first = ming.room.vnum
        say(ming, "recall")
        return first, ming.room.vnum

    assert asyncio.run(main()) == (101, 103)


def test_no_recall_room(world):
    ming = person("Ming", 102)
    assert say(ming, "recall") == RECALL_REFUSED
    assert ming.room.vnum == 102


def test_lost(world):
    ming = person("Ming")
    ming.recall = 150                                                 # 沒有這間房
    assert say(ming, "recall") == RECALL_LOST
    assert ming.room.vnum == 103


def test_already_there(world):
    ming = person("Ming", 101)
    assert say(ming, "recall").startswith("<HP")                     # 照 C 版：什麼都不說，只有 prompt
    assert ming.room.vnum == 101


def test_not_while_fighting(world):
    ming = person("Ming")

    async def main():
        fight.start_fight(ming, next(c for c in characters if isinstance(c, Npc)))
        return say(ming, "recall")

    assert asyncio.run(main()) == REFUSALS[Position.FIGHTING]
    assert ming.room.vnum == 103


def test_not_while_resting(world):
    ming = person("Ming")
    ming.position = Position.RESTING
    assert say(ming, "recall") == REFUSALS[Position.RESTING]


def test_on_enter_fires(world, monkeypatch):
    fired = []
    monkeypatch.setattr(scripts, "fire", lambda room, when, *args: fired.append((room.vnum, when, args)))
    ming = person("Ming")
    say(ming, "recall")
    assert [f for f in fired if f[1] == "on_enter"] == [(101, "on_enter", (ming, ming, None))]


def test_recall_point_is_saved(world, tmp_path, monkeypatch):
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path / "players")
    ming = person("Ming")
    assert save.player_from(save_and_load(ming), FakeWriter()).recall is None     # 沒設定
    ming.recall = 103
    assert save.player_from(save_and_load(ming), FakeWriter()).recall == 103


def save_and_load(p):
    save.save_player(p)
    return save.load_data(p.name)
