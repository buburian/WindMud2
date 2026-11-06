"""flee（commands/combat.py）：機率照 DEX、戰鬥中不能走、成功跑掉（雙方停手、訊息）、失敗要等、關著的門、沒有出口。

戰鬥的 loop 不自己跑（fight.TICK_SECONDS 改很大），開打和 flee 在同一個 asyncio.run 裡。亂數換成 FakeRng。
"""
import asyncio
import re
from types import SimpleNamespace

import pytest

import mud.commands as commands
from area_helpers import make_area, make_mobile, make_room, write_json
from mud import fight, skills, stats, zones
from mud.area import Apply
from mud.characters import Position, characters
from mud.commands import combat as combat_commands
from mud.config import ENCODING
from mud.npcs import Npc
from mud.players import Player


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


class FakeRng:
    """random() 一律回傳 x；choice() 記下可以選的出口，挑第 pick 個。"""

    def __init__(self, x, pick=0):
        self.x, self.pick, self.seen = x, pick, None

    def random(self):
        return self.x

    def choice(self, seq):
        self.seen = list(seq)
        return seq[self.pick]


@pytest.fixture
def world(tmp_path, monkeypatch):
    """房間 101 —北— 102 —東— 103，兩條路都是門（開著）。102 有一隻野狗。"""
    monkeypatch.setattr(fight, "TICK_SECONDS", 1000)
    dog = make_mobile(1)
    dog.update(short="野狗", keywords="dog 野狗", level=1, tier="normal", tier_roll=None, attack=None, defense=None,
               archetype=None, act=0, position=7, sex=0, long="", drops=[])
    rooms = [make_room(1, north=2), make_room(2, south=1, east=3), make_room(3, west=2)]
    for r, d in ((rooms[0], "north"), (rooms[1], "south"), (rooms[1], "east"), (rooms[2], "west")):
        r["exits"][d].update(locks=1, keywords="木門 door")
    reset = [{"cmd": "M", "rare": 0, "mob_vnum": 1, "limit": 1, "room_vnum": 2, "comment": ""}]
    write_json(tmp_path, "a.json", make_area("a.json", rooms, 100, mobiles=[dog], resets=reset))
    zones.load(tmp_path)
    yield zones.world
    characters.clear()
    zones.stop()


def use_rng(monkeypatch, x, pick=0):
    rng = FakeRng(x, pick)
    monkeypatch.setattr(combat_commands, "rng", rng)
    return rng


def fighter(name, room=102):
    p = Player(name, FakeWriter(), zones.world.rooms[room])
    p.race, p.guild = stats.Race.HUMAN, stats.Guild.SWORD
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    stats.set_level(p, 1)
    characters.append(p)
    return p


def the_dog():
    return next(c for c in characters if isinstance(c, Npc))


def plain(p):
    text = re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))
    p.writer.data = b""
    return text


def say(p, line):
    plain(p)
    commands.command(p, line)
    return plain(p).rsplit("\r\n\r\n", 1)[0]


def in_fight(p, body):
    """p 開打野狗，接著做 body()，回傳 body 的結果（都在同一個 asyncio.run 裡）。

    坑：asyncio.run() 結束時戰鬥會被收掉（大家都停手），還在不在打要在 body 裡看。
    """
    async def main():
        fight.start_fight(p, the_dog())
        return body()

    return asyncio.run(main())


# ---- 機率 ----

@pytest.mark.parametrize("dex, gear, chance", [(0, 0, 0.10), (27.5, 0, 0.45), (55, 0, 0.80), (12, 0, 0.1 + 0.7 * 12 / 55),
                                               (50, 10, 0.80), (40, 15, 0.80), (40, 10, 0.1 + 0.7 * 50 / 55)])
def test_chance_follows_dex(dex, gear, chance):
    p = Player("Ming", None, None)
    p.primaries = {"dex": dex}
    p.equipment = {"neck_1": SimpleNamespace(affects=[(Apply.DEX, gear)])} if gear else {}
    assert stats.flee_chance(p) == pytest.approx(chance)


def test_creatures_have_no_dex():
    assert stats.flee_chance(Npc("野狗", 0, None)) == pytest.approx(0.10)


@pytest.mark.parametrize("roll, fled", [(0.25, True), (0.26, False)])
def test_the_roll_uses_the_chance(world, monkeypatch, roll, fled):
    use_rng(monkeypatch, roll)                                        # 人類 DEX 12：25.3%
    ming = fighter("Ming")
    assert in_fight(ming, lambda: (say(ming, "flee"), ming.fighting is None)[1]) is fled


# ---- 戰鬥中不能走 ----

def test_cannot_walk_in_a_fight(world):
    ming = fighter("Ming")
    assert in_fight(ming, lambda: say(ming, "s")) == "不行!!你還在戰鬥狀態中!!"
    assert ming.room.vnum == 102


def test_not_fighting(world):
    assert say(fighter("Ming"), "flee") == "你在害怕什麼呢？你沒有在跟任何一個人戰鬥啊。"


def test_cannot_flee_while_sleeping(world):
    ming = fighter("Ming")
    ming.position = Position.SLEEPING
    assert say(ming, "f") == "在你的睡夢中嗎？"


# ---- 成功、失敗 ----

def test_flee_runs_away(world, monkeypatch):
    rng = use_rng(monkeypatch, 0.0, pick=1)
    ming, hua, lin = fighter("Ming"), fighter("Hua"), fighter("Lin", room=103)
    dog = the_dog()
    plain(hua), plain(lin)
    got, after = in_fight(ming, lambda: (say(ming, "flee"), (ming.fighting, dog.fighting, ming.position, dog.position)))
    assert rng.seen == ["south", "east"] and ming.room.vnum == 103
    assert got.startswith("你從戰鬥中逃跑了!!\r\n【")                 # 接著看到新房間
    assert after == (None, None, Position.STANDING, Position.STANDING)   # 他和打他的都停手
    assert "Ming往東邊逃竄(Flee)了!!。" in plain(hua)
    assert "Ming從西邊走了過來。" in plain(lin)


def test_failing_means_waiting(world, monkeypatch):
    rng = use_rng(monkeypatch, 0.99)
    ming = fighter("Ming")

    def body():
        out = [say(ming, "flee")]
        rng.x = 0.0                                                   # 下一次一定成功，可是要先等
        out.append(say(ming, "flee"))
        skills.tick()
        out.append(say(ming, "flee"))
        out.append(ming.room.vnum)
        skills.tick()
        out.append(say(ming, "flee").split("\r\n")[0])
        return out

    assert in_fight(ming, body) == ["你逃跑失敗了。", "你還要等 2 秒才能再逃跑。", "你還要等 1 秒才能再逃跑。", 102,
                                    "你從戰鬥中逃跑了!!"]


def test_closed_doors_are_not_exits(world, monkeypatch):
    rng = use_rng(monkeypatch, 0.0)
    ming = fighter("Ming")
    room = world.rooms[102]
    room.doors["south"].closed = True
    in_fight(ming, lambda: say(ming, "flee"))
    assert rng.seen == ["east"] and ming.room.vnum == 103


def test_no_way_out(world, monkeypatch):
    use_rng(monkeypatch, 0.0)
    ming = fighter("Ming")
    for d in ("south", "east"):
        world.rooms[102].doors[d].closed = True
    got = in_fight(ming, lambda: (say(ming, "flee"), ming.fighting is not None))
    assert got == ("這裡沒有可以逃跑的出口！", True) and "flee" not in ming.cooldowns    # 沒逃：還在打，不用等


def test_waiting_does_not_break_skills_or_mstat(world, monkeypatch):
    # flee 的等待跟技能冷卻放在一起（cooldowns["flee"]）：skills、mstat 照樣看得了
    use_rng(monkeypatch, 0.99)
    ming = fighter("Ming")
    ming.imm = True
    got = in_fight(ming, lambda: (say(ming, "flee"), say(ming, "skills"), say(ming, "mstat ming")))
    assert got[0] == "你逃跑失敗了。" and got[1].startswith("你會的技能") and "冷卻 flee 2" in got[2]
