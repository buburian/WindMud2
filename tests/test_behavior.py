"""生物平常的行為（behavior.py，設計文件 §4.11，規則在區域製作手冊 act）：走動、scavenger、主動攻擊（含半身人的「不起眼」）、
生物回血、wimpy 逃跑。

亂數換成 FakeRng；主動攻擊、wimpy 要開打，在 asyncio.run 裡做（戰鬥的 loop 不自己跑，fight.TICK_SECONDS 改很大）。
地圖：101 北 → 102、東 → 301（別的世界區域檔）、南 → 103（no_mob）、西 → 201（動態區域）、上 → 104（木門）。
"""
import asyncio
import re

import pytest

from area_helpers import make_area, make_mobile, make_room, write_area, write_json
from mud import behavior, fight, objects, skills, stats, zones
from mud.area import CONTAINER_ITEM_TYPE, ActFlag, ContainerFlag, RoomFlag
from mud.characters import Position, arrive, characters
from mud.config import ENCODING, MOBILE_TICKS
from mud.npcs import Npc
from mud.players import Player


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


class FakeRng:
    """random() 一律回傳 x（數幾次）；choice() 記下可以選的，挑第 pick 個。"""

    def __init__(self, x, pick=0):
        self.x, self.pick, self.seen, self.rolls = x, pick, None, 0

    def random(self):
        self.rolls += 1
        return self.x

    def choice(self, seq):
        self.seen = list(seq)
        return seq[self.pick]


@pytest.fixture
def world(tmp_path, monkeypatch):
    """a.json（世界 100）：101 有一隻 1 級的野狗（站著、act 0）。b.json 是別的世界區域檔（301），d.json 是動態區域（201）。"""
    monkeypatch.setattr(fight, "TICK_SECONDS", 1000)
    dog = make_mobile(1)
    dog.update(short="野狗", keywords="dog", level=1, tier="normal", tier_roll=None, attack=None, defense=None,
               archetype=None, act=0, position=7, sex=0, long="", drops=[], shop=None, special=None)
    rooms = [make_room(1, north=2, east=301, south=3, west=201, up=4), make_room(2, south=1), make_room(3, north=1),
             make_room(4, down=1)]
    rooms[2]["room_flags"] = int(RoomFlag.NO_MOB)
    for r, d in ((rooms[0], "up"), (rooms[3], "down")):
        r["exits"][d].update(locks=1, keywords="木門 door")
    reset = [{"cmd": "M", "rare": 0, "mob_vnum": 1, "limit": 1, "room_vnum": 1, "comment": ""}]
    write_json(tmp_path, "a.json", make_area("a.json", rooms, 100, mobiles=[dog], resets=reset))
    write_area(tmp_path, "b.json", [make_room(1, west=101)], area_number=300)
    write_area(tmp_path, "d.json", [make_room(1, east=101)], area_number=200, kind="dynamic")
    zones.load(tmp_path)
    yield zones.world
    characters.clear()
    zones.stop()


def use_rng(monkeypatch, x, pick=0):
    rng = FakeRng(x, pick)
    monkeypatch.setattr(behavior, "rng", rng)
    return rng


def the_dog():
    return next(c for c in characters if isinstance(c, Npc))


def person(name, room=101, race=stats.Race.HUMAN):
    p = Player(name, FakeWriter(), zones.world.rooms[room])
    p.race, p.guild = race, stats.Guild.SWORD
    p.primaries = dict(stats.RACE_PRIMARIES[race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.skills = skills.starter(p.guild)
    stats.set_level(p, 1)
    characters.append(p)
    return p


def plain(p):
    text = re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))
    p.writer.data = b""
    return text


def notified(p, *lines):
    """別人的事送到 p 那裡的樣子：先換行、一句一行、空一行再補 prompt（拿掉顏色）。"""
    return "\r\n" + "\r\n".join(lines) + "\r\n\r\n" + re.sub(r"\x1b\[[0-9;]*m", "", p.prompt())


def thing(name, keyword, cost, take=True):
    obj = objects.Obj(name, f"{name}放在這裡。", 8, [keyword])
    obj.cost, obj.take = cost, take
    return obj


# ---- 走動 ----

def test_walks_only_through_allowed_exits(world, monkeypatch):
    # 能走的：102（同一個區域檔）、104（木門開著）。301 是別的區域檔、103 是 no_mob、201 是還沒建的動態區域
    rng = use_rng(monkeypatch, 0.19)        # 20% 以內：走
    dog = the_dog()
    behavior.idle(dog)
    assert rng.seen == ["north", "up"] and dog.room.vnum == 102
    assert zones.dynamic == {}              # 沒有把動態區域建出來


def test_closed_door_is_not_a_way(world, monkeypatch):
    rng = use_rng(monkeypatch, 0.0, pick=0)
    world.rooms[101].doors["up"].closed = True
    behavior.idle(the_dog())
    assert rng.seen == ["north"]


def test_no_way_no_walk(world, monkeypatch):
    rng = use_rng(monkeypatch, 0.0)
    dog = the_dog()
    dog.room = world.rooms[104]
    world.rooms[104].doors["down"].closed = True
    behavior.idle(dog)
    assert dog.room.vnum == 104 and rng.seen is None


def test_twenty_percent(world, monkeypatch):
    use_rng(monkeypatch, 0.2)               # 沒有小於 20%：不走
    dog = the_dog()
    behavior.idle(dog)
    assert dog.room.vnum == 101


@pytest.mark.parametrize("act, position", [
    (ActFlag.SENTINEL, Position.STANDING),  # 待在原地
    (ActFlag(0), Position.RESTING),
    (ActFlag(0), Position.SLEEPING),
    (ActFlag(0), Position.FIGHTING),
])
def test_some_mobiles_stay(world, monkeypatch, act, position):
    rng = use_rng(monkeypatch, 0.0)
    dog = the_dog()
    dog.act, dog.position = act, position
    behavior.idle(dog)
    assert dog.room.vnum == 101 and rng.seen is None


def test_walking_every_mobile_ticks_in_one_block(world, monkeypatch):
    # 世界 tick 呼叫 behavior.tick()：每 MOBILE_TICKS 才走；同一個 tick 走掉的兩隻，旁邊的人收到一段、一個 prompt
    use_rng(monkeypatch, 0.0)
    cat = Npc("野貓", 0, world.rooms[101])
    characters.append(cat)
    ming = person("Ming")
    behavior.tick(MOBILE_TICKS - 1)
    assert the_dog().room.vnum == 101 and ming.writer.data == b""
    behavior.tick(MOBILE_TICKS)
    assert the_dog().room.vnum == 102 and cat.room.vnum == 102
    assert plain(ming) == notified(ming, "野狗朝北離開。", "野貓朝北離開。")


def test_arriving_looks_like_a_player(world, monkeypatch):
    use_rng(monkeypatch, 0.0)
    hua = person("Hua", room=102)
    behavior.idle(the_dog())
    assert plain(hua) == notified(hua, "野狗從南邊走了過來。")


# ---- scavenger ----

def test_scavenger_takes_the_most_valuable(world, monkeypatch):
    use_rng(monkeypatch, 0.24)              # 25% 以內：撿；走動的 20% 沒中
    dog = the_dog()
    dog.act = ActFlag.SCAVENGER
    floor = world.rooms[101].contents
    box = thing("箱子", "box", 100)
    box.item_type, box.container = CONTAINER_ITEM_TYPE, ContainerFlag.SEALABLE | ContainerFlag.SEALED
    statue = thing("石像", "statue", 1000, take=False)
    gem, potion, other_gem = thing("寶石", "gem", 50), thing("藥水", "potion", 5), thing("寶石", "gem", 50)
    floor[:] = [potion, statue, box, gem, other_gem]
    ming = person("Ming")
    behavior.idle(dog)
    # 拿不起來的、封印的不算；一樣貴撿前面的（新的）
    assert dog.carrying == [gem] and floor == [potion, statue, box, other_gem]
    assert plain(ming) == notified(ming, "野狗撿起了【寶石/gem】。")


def test_scavenger_twenty_five_percent(world, monkeypatch):
    use_rng(monkeypatch, 0.25)
    dog = the_dog()
    dog.act = ActFlag.SCAVENGER | ActFlag.SENTINEL
    world.rooms[101].contents[:] = [thing("寶石", "gem", 50)]
    behavior.idle(dog)
    assert dog.carrying == []


# ---- 主動攻擊 ----

def aggress(*after):
    """在 asyncio 裡跑一次 behavior.aggress()，回傳 after 裡每個角色在打誰（asyncio.run 結束時戰鬥會被收掉）。"""
    async def main():
        behavior.aggress()
        return [c.fighting for c in after]

    return asyncio.run(main())


def test_aggressive_attacks_a_player(world, monkeypatch):
    rng = use_rng(monkeypatch, 0.9, pick=1)
    dog = the_dog()
    dog.act = ActFlag.AGGRESSIVE
    ming, hua = person("Ming"), person("Hua")
    hua.position = Position.SLEEPING        # 睡著的照打
    assert aggress(dog, ming, hua) == [hua, None, dog]
    assert rng.seen == [ming, hua]
    assert plain(ming) == "" and plain(hua) == ""      # 跟 kill 一樣，沒有另外的訊息


@pytest.mark.parametrize("change", [
    lambda dog, ming: setattr(ming, "imm", True),                                  # 不打 imm
    lambda dog, ming: setattr(dog, "act", ActFlag(0)),                             # 不是 aggressive
    lambda dog, ming: setattr(dog, "position", Position.RESTING),                  # 生物要站著
    lambda dog, ming: setattr(ming.room, "room_flags", RoomFlag.SAFE),             # 安全區
    lambda dog, ming: setattr(ming, "room", zones.world.rooms[102]),               # 不在同一間房
])
def test_aggressive_does_not_attack(world, monkeypatch, change):
    use_rng(monkeypatch, 0.9)
    dog = the_dog()
    dog.act = ActFlag.AGGRESSIVE
    ming = person("Ming")
    change(dog, ming)
    assert aggress(dog, ming) == [None, None]


def test_aggressive_skips_players_in_a_fight(world, monkeypatch):
    rng = use_rng(monkeypatch, 0.9)
    dog = the_dog()
    dog.act = ActFlag.AGGRESSIVE
    ming, hua = person("Ming"), person("Hua")
    cat = Npc("野貓", 0, world.rooms[101])
    characters.append(cat)

    async def main():
        fight.start_fight(hua, cat)         # 阿華在打野貓：不挑他（不然等於兩隻一起打）
        behavior.aggress()
        return dog.fighting

    assert asyncio.run(main()) is ming and rng.seen == [ming]


def test_halfling_may_go_unnoticed(world, monkeypatch):
    # 第一次要打半身人時骰一次，一半不打；不打的話到他離開這間房以前都不打，回來才重骰
    dog = the_dog()
    dog.act = ActFlag.AGGRESSIVE
    tuck = person("Tuck", race=stats.Race.HALFLING)
    use_rng(monkeypatch, 0.49)              # 一半以內：不打
    assert aggress(dog) == [None]
    rng = use_rng(monkeypatch, 0.0)
    assert aggress(dog) == [None] and rng.rolls == 0 and rng.seen is None     # 不再骰，也不會被挑
    tuck.room = world.rooms[102]
    arrive(tuck)
    tuck.room = world.rooms[101]
    arrive(tuck)                            # 離開再回來
    use_rng(monkeypatch, 0.5)
    assert aggress(dog) == [tuck]


def test_halfling_noticed_stays_noticed(world, monkeypatch):
    dog = the_dog()
    dog.act = ActFlag.AGGRESSIVE
    tuck = person("Tuck", race=stats.Race.HALFLING)
    use_rng(monkeypatch, 0.5)               # 骰到打
    assert aggress(dog) == [tuck]
    rng = use_rng(monkeypatch, 0.0)
    fight.stop_fighting(dog), fight.stop_fighting(tuck)
    dog.position = tuck.position = Position.STANDING
    assert aggress(dog) == [tuck] and rng.rolls == 0      # 這次待在這裡都照第一次的結果，不重骰


# ---- 回血 ----

@pytest.mark.parametrize("position, rate", [
    (Position.STANDING, 0.10), (Position.RESTING, 0.20), (Position.SLEEPING, 0.30), (Position.FIGHTING, 0.0),
])
def test_mobiles_regen_like_players(world, position, rate):
    # 跟玩家一樣：每 REGEN_TICKS 回上限的 10%／20%／30%，打架中不回（設計文件 §4.11）
    dog = the_dog()
    dog.act, dog.position = ActFlag.SENTINEL, position
    top = dog.panel["hp"]
    dog.hp = 1.0
    for _ in range(29):
        world.tick()
    assert dog.hp == 1.0
    world.tick()
    assert dog.hp == pytest.approx(1.0 + top * rate)


# ---- wimpy ----

def wimpy_fight(ming, dog, hp_share, body):
    """Ming 跟野狗開打、野狗的 HP 剩 hp_share，接著做 body(那一場)。"""
    async def main():
        battle = fight.start_fight(ming, dog)
        dog.hp = dog.panel["hp"] * hp_share
        return body(battle)

    return asyncio.run(main())


def test_wimpy_runs_away(world, monkeypatch):
    rng = use_rng(monkeypatch, 0.24)        # 25% 以內：逃
    dog = the_dog()
    dog.act = ActFlag.WIMPY
    ming, hua = person("Ming"), person("Hua", room=102)
    got = wimpy_fight(ming, dog, 0.49, lambda battle: (behavior.wimpy(battle), dog.fighting, ming.fighting, dog.position)[1:])
    assert got == (None, None, Position.STANDING) and dog.room.vnum == 102 and rng.seen == ["north", "up"]
    assert plain(ming) == notified(ming, "野狗往北邊逃竄(Flee)了!!。")
    assert plain(hua) == notified(hua, "野狗從南邊走了過來。")


@pytest.mark.parametrize("act, share, x", [
    (ActFlag.WIMPY, 0.5, 0.0),              # HP 沒有低於一半：不骰
    (ActFlag.WIMPY, 0.49, 0.25),            # 沒有小於 25%
    (ActFlag(0), 0.1, 0.0),                 # 不是 wimpy：打到死
])
def test_wimpy_stays(world, monkeypatch, act, share, x):
    rng = use_rng(monkeypatch, x)
    dog = the_dog()
    dog.act = act
    ming = person("Ming")
    assert wimpy_fight(ming, dog, share, lambda battle: (behavior.wimpy(battle), dog.fighting)[1]) is ming
    assert rng.seen is None and rng.rolls == (1 if x == 0.25 else 0)


def test_wimpy_without_a_way_stays(world, monkeypatch):
    rng = use_rng(monkeypatch, 0.0)
    dog = the_dog()
    dog.act = ActFlag.WIMPY
    ming = person("Ming", room=104)
    dog.room = world.rooms[104]
    world.rooms[104].doors["down"].closed = True
    assert wimpy_fight(ming, dog, 0.1, lambda battle: (behavior.wimpy(battle), dog.fighting)[1]) is ming
    assert rng.seen is None


def test_wimpy_checks_at_the_end_of_a_round(world, monkeypatch):
    # Fight.tick()：每回合打完才看（停的那一秒不看）
    use_rng(monkeypatch, 0.0)
    monkeypatch.setattr(fight, "hit", lambda ch, victim, hand: None)
    dog = the_dog()
    dog.act = ActFlag.WIMPY
    ming = person("Ming")

    def ticks(battle):
        battle.tick()                       # 第 1 個 tick：打一輪，回合結束 → 逃
        return dog.room.vnum, ming.fighting

    assert wimpy_fight(ming, dog, 0.1, ticks) == (102, None)
    assert "野狗往北邊逃竄(Flee)了!!。" in plain(ming)
