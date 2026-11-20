"""recall（/）：回到自己的返回點（沒設定是起始房間）、區域檔寫了 recall 就用區域的（副本裡的 recall 點）、
no_recall 的房間、休息不能用、已經在那裡、找不到、旁人的訊息、存檔的返回點、到了觸發 on_enter；
打架中會失敗（機率是 flee 的一半、等待跟 flee 共用、暈凍不能試、成功兩邊停手），亂數換成 combat.rng。
學生不能用的測試在 test_academy.py（要真的學院）。
"""
import asyncio
import re

import pytest

import mud.commands as commands
from area_helpers import make_area, make_mobile, make_room, write_json
from mud import affects, fight, save, scripts, stats, zones
from mud.area import RoomFlag
from mud.characters import Position, characters
from mud.commands import REFUSALS
from mud.commands import combat as combat_commands
from mud.commands.combat import FLEE_WAIT_TICKS, RECALL_ESCAPED, RECALL_FAILED
from mud.commands.system import HELD, RECALL_ARRIVE, RECALL_LEAVE, RECALL_LOST, RECALL_PRAY, RECALL_REFUSED
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


class FakeRng:
    """random() 一律回傳 x，記下叫了幾次。"""

    def __init__(self, x):
        self.x, self.calls = x, 0

    def random(self):
        self.calls += 1
        return self.x


def fighting(ming, *lines, roll=0.0, monkeypatch=None):
    """ming 跟狗打起來，照順序打 lines；回傳每一句看到的、狗、亂數，ming.still 是打完那幾句還在打誰。

    坑：asyncio.run() 結束時戰鬥會被收掉，還在不在打要在裡面看。
    """
    rng = FakeRng(roll)
    monkeypatch.setattr(combat_commands, "rng", rng)
    dog = next(c for c in characters if isinstance(c, Npc))

    async def main():
        fight.start_fight(ming, dog)
        seen = [say(ming, line) for line in lines]
        ming.still = ming.fighting
        return seen

    return asyncio.run(main()), dog, rng


@pytest.mark.parametrize("line", ["recall", "/"])
def test_recall_from_a_fight(world, monkeypatch, line):
    ming = person("Ming")
    (got,), dog, _ = fighting(ming, line, roll=0.0, monkeypatch=monkeypatch)
    assert got.startswith(RECALL_ESCAPED + "\r\n【房間101】")
    assert ming.room.vnum == 101 and ming.still is None and dog.fighting is None      # 兩邊都停手（跟 flee 一樣）
    assert "flee" not in ming.cooldowns


def test_failing_in_a_fight(world, monkeypatch):
    ming = person("Ming")
    wang = person("Wang")
    (got,), dog, _ = fighting(ming, "recall", roll=0.99, monkeypatch=monkeypatch)
    assert got == RECALL_FAILED
    assert ming.room.vnum == 103 and ming.still is dog
    assert ming.cooldowns["flee"] == FLEE_WAIT_TICKS
    seen = plain(wang)
    assert RECALL_PRAY.replace("$n", "Ming") in seen and RECALL_LEAVE.replace("$n", "Ming") not in seen


def test_chance_is_half_of_flee(world, monkeypatch):
    ming = person("Ming")                                             # 人類 DEX 12：flee 25.3%，recall 12.6%
    chance = stats.fight_recall_chance(ming)
    assert chance == pytest.approx(stats.flee_chance(ming) / 2) and chance == pytest.approx(0.1264, abs=1e-4)
    (got,), _, _ = fighting(ming, "recall", roll=chance, monkeypatch=monkeypatch)
    assert got == RECALL_FAILED                                       # 剛好等於機率：失敗
    ming.cooldowns.clear()
    fight.stop_fighting(ming)
    ming.room = zones.world.rooms[103]
    (got,), _, _ = fighting(ming, "recall", roll=chance - 1e-9, monkeypatch=monkeypatch)
    assert got.startswith(RECALL_ESCAPED)


@pytest.mark.parametrize("dex, chance", [(0, 0.05), (55, 0.40), (80, 0.40)])
def test_chance_tops_out_at_40_percent(world, dex, chance):
    ming = person("Ming")
    ming.primaries["dex"] = dex
    assert stats.fight_recall_chance(ming) == pytest.approx(chance)


@pytest.mark.parametrize("first, second", [("recall", "flee"), ("flee", "recall"), ("recall", "recall")])
def test_the_wait_is_shared_with_flee(world, monkeypatch, first, second):
    """失敗以後要等 2 秒，flee 和打架中的 recall 共用：不能兩個輪流試。"""
    ming, wang = person("Ming"), person("Wang")
    (_, got), _, rng = fighting(ming, first, second, roll=0.99, monkeypatch=monkeypatch)
    assert got == f"你還要等 {FLEE_WAIT_TICKS:g} 秒才能再逃跑。"
    assert rng.calls == 1 and ming.room.vnum == 103
    assert plain(wang).count(RECALL_PRAY.replace("$n", "Ming")) == (first == "recall")    # 還在等就不祈求


def test_held_cannot_recall_from_a_fight(world, monkeypatch):
    ming = person("Ming")
    affects.add(ming, affects.Affect(source="test_stun", name="測試", duration=10, control="stun"))
    (got,), _, rng = fighting(ming, "recall", monkeypatch=monkeypatch)
    assert got == HELD and rng.calls == 0 and ming.room.vnum == 103


def test_no_recall_room_in_a_fight_does_not_roll(world, monkeypatch):
    ming = person("Ming", 102)
    dog = next(c for c in characters if isinstance(c, Npc))
    dog.room = ming.room
    (got,), _, rng = fighting(ming, "recall", monkeypatch=monkeypatch)
    assert got == RECALL_REFUSED and rng.calls == 0 and "flee" not in ming.cooldowns


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
