"""enter 和傳送門（commands/portal.py，使用者 2026-11-20 定的），用真的 areas/：城西森林 10113 的樹洞 ↔ 副本 hollow.json。

副本是一個人一份（組隊還沒做）、不自己定時重生（沒人 20 分鐘收掉）。建立副本要在 asyncio 裡（zones.instance 會開 tick 的 task）。
"""
import asyncio
import re
from pathlib import Path

import pytest

import mud.commands as commands
from mud import death, fight, objects, resets, scripts, stats, weather, zones
from mud.area import ActFlag, MobTier
from mud.characters import Position, characters
from mud.config import AREA_TICKS, ENCODING, RELEASE_TICKS
from mud.npcs import Npc
from mud.players import Player

AREAS = Path(__file__).resolve().parent.parent / "areas"
HOLLOW = 10113                      # 城西森林「往天橋的小徑口」：地上有樹洞
INSIDE = 400                        # 副本的第一間（樹洞裡），recall 點
PORTAL_LINE = "(傳送門)倒下的大樹根部裂開一個大樹洞，裡面透出幽幽的綠光。/hollow"


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


@pytest.fixture(autouse=True)
def world(monkeypatch):
    monkeypatch.setattr(weather, "current", weather.Weather(hour=12))     # 原野白天才亮
    monkeypatch.setattr(fight, "TICK_SECONDS", 1000)
    zones.load(AREAS)
    yield
    characters.clear()
    zones.stop()


def player(name, room=HOLLOW, race=stats.Race.HUMAN):
    p = Player(name, FakeWriter(), zones.world.rooms[room])
    p.race, p.guild = race, stats.Guild.SWORD
    p.primaries = dict(stats.RACE_PRIMARIES[race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    stats.set_level(p, 15)
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


def run(main):
    async def wrapped():
        try:
            main()
        finally:
            zones.stop()
    asyncio.run(wrapped())


def own_copy(name):
    return zones.instances[("hollow.json", name)]


# ---- 傳送門 ----

def test_portal_line_and_look():
    ming = player("Ming")
    assert PORTAL_LINE in say(ming, "look").split("\r\n")
    assert say(ming, "look hollow").startswith("樹根翻起來的地方裂開一個洞")                 # 物品可以細看的東西
    assert commands.find("en") is commands.find("enter") and commands.find("e") is not commands.find("enter")


def test_enter_your_own_copy():
    def main():
        ming, hua = player("Ming"), player("Hua")
        plain(hua)
        text = say(ming, "enter")
        assert ming.room.vnum == INSIDE and ming.room.zone is own_copy("Ming")
        assert re.match(r"你走進了【樹洞/hollow】。\r\n\r\n\+-+\+\r\n\| \*\*\* 樹洞（15～20 級） \*\*\* \|\r\n\+-+\+\r\n\r\n【樹洞裡】", text)
        assert "Ming走進了【樹洞/hollow】。" in plain(hua)
        say(hua, "en hollow")                                                             # 名字照 get 的找法
        assert hua.room.vnum == INSIDE and hua.room.zone is own_copy("Hua") is not own_copy("Ming")   # 一個人一份
        assert "Ming" not in say(hua, "look")
    run(main)


def test_back_out_and_recall_inside():
    def main():
        ming, hua = player("Ming"), player("Hua")
        say(ming, "enter")
        for d in ("n", "n", "n", "e"):
            say(ming, d)
        assert ming.room.vnum == 404 and ming.room.zone is own_copy("Ming")
        assert say(ming, "recall").split("\r\n")[0] == "【樹洞裡】"                       # 副本裡 recall 只回到副本的 recall 點
        assert ming.room.vnum == INSIDE and ming.room.zone is own_copy("Ming")
        plain(hua)
        text = say(ming, "enter")
        assert ming.room is zones.world.rooms[HOLLOW] and text.startswith("你走進了【樹洞口/hollow】。")
        assert "Ming從【樹洞口/hollow】走了出來。" in plain(hua)
    run(main)


@pytest.mark.parametrize("setup, line, want", [
    (lambda p: setattr(p, "room", zones.world.rooms[10114]), "enter", "這裡沒有可以進去的地方。"),
    (lambda p: p.room.contents.insert(0, objects.create(10106, 1, None)), "enter necklace", "你沒辦法走進【{}】。"),   # 狼王的牙項鍊：不是傳送門
    (lambda p: setattr(p, "position", Position.FIGHTING), "enter", "不行!!你還在戰鬥狀態中!!"),
    (lambda p: setattr(p, "position", Position.RESTING), "enter", "嗯... 你正在休息耶..。"),
    (lambda p: setattr(weather, "current", weather.Weather(hour=0)), "enter", "這裡沒有可以進去的地方。"),   # 很暗：看不到地上的東西
])
def test_refusals(setup, line, want):
    ming = player("Ming")
    setup(ming)
    found = ming.room.contents[0] if ming.room.contents else None
    name = re.sub(r"\x1b\[[0-9;]*m", "", objects.short(found)) if found else ""
    assert say(ming, line) == want.format(name) and ming.room.vnum != INSIDE and not zones.instances


def test_a_mobile_does_not_enter_an_instance():
    def main():
        npc = Npc("野狗", 0, zones.world.rooms[HOLLOW])
        characters.append(npc)
        commands.command(npc, "enter")
        assert npc.room.vnum == HOLLOW and not zones.instances
    run(main)


def test_on_enter_fires(monkeypatch):
    fired = []
    monkeypatch.setattr(scripts, "fire", lambda room, event, *args: fired.append((room.vnum, event)))
    def main():
        say(player("Ming"), "enter")
    run(main)
    assert (INSIDE, "on_enter") in fired


# ---- 副本的內容和重生 ----

def test_the_treant_and_its_drops():
    def main():
        ming = player("Ming")
        say(ming, "enter")
        treant = next(c for c in characters if isinstance(c, Npc) and c.room.zone is own_copy("Ming"))
        assert (treant.name, treant.room.vnum, treant.level, treant.tier, treant.special) == ("樹妖", 404, 15, MobTier.BOSS, "spec_poison")
        assert ActFlag.SENTINEL in treant.act and ActFlag.AGGRESSIVE not in treant.act   # 待在原地、不主動攻擊
        corpse = death.die(treant)
        purple = sorted(o.vnum for o in corpse.contains if o.color == "purple")      # 紫色一定掉（使用者 2026-11-20 改的）
        assert purple == [401, 402, 403, 404, 405, 406] and all(o.level == 15 for o in corpse.contains if o.color)
        assert {o.color for o in corpse.contains if o.color} <= {"purple", "orange"}
    run(main)


def test_instances_do_not_reset_on_their_own(monkeypatch):
    updated = []
    monkeypatch.setattr(resets, "update", lambda zone: updated.append(zone))
    def main():
        say(player("Ming"), "enter")
        copy = own_copy("Ming")
        copy.ticks = AREA_TICKS - 1
        copy.tick()
        zones.world.ticks = AREA_TICKS - 1
        zones.world.tick()
        assert updated == [zones.world]                                                 # 世界照舊、副本不重生
    run(main)


def test_an_empty_copy_is_still_released():
    def main():
        ming = player("Ming")
        say(ming, "enter")
        copy = own_copy("Ming")
        say(ming, "enter")                                                              # 出來了
        copy.empty_ticks = RELEASE_TICKS - 1
        copy.tick()
        assert ("hollow.json", "Ming") not in zones.instances
        say(ming, "enter")
        assert own_copy("Ming") is not copy                                             # 下次進去是新的一份
    run(main)


# ---- area 的入口 ----

def walk(route, start=3001):
    """照 area 的入口（"3s10wn" 這種）從 start 走，回到最後那間房的號碼。"""
    steps = {"n": "north", "e": "east", "s": "south", "w": "west", "u": "up", "d": "down"}
    room = start
    for count, d in re.findall(r"(\d*)([neswud])", route):
        for _ in range(int(count or 1)):
            room = zones.world.rooms[room].exits[steps[d]]
    return room


def test_area_shows_the_way_to_the_portal():
    assert walk(zones.routes["hollow.json"]) == HOLLOW                                  # 走到放樹洞的那間
    assert zones.routes["academy.json"] is None                                         # 沒有傳送門通進去：-----
    rows = say(player("Ming"), "area").split("\r\n")
    assert any(re.match(rf"  樹洞 +15～20 級 +副本 +{zones.routes['hollow.json']} ", r) for r in rows)
    assert any(re.match(r"  教學學院 +1～1 級 +副本 +----- ", r) for r in rows)
