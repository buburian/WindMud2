import asyncio
import logging
from pathlib import Path

import pytest

from mud import fight, zones
from mud.characters import SEX_NEUTRAL, Position, characters
from mud.fight import start_fight, stop_fighting
from mud.npcs import Npc

AREAS = Path(__file__).resolve().parent.parent / "areas"


@pytest.fixture
def hits(monkeypatch):
    # 一個 tick 0.01 秒；出手（hit）記下「誰打誰」
    zones.load(AREAS)
    monkeypatch.setattr(fight, "TICK_SECONDS", 0.01)
    record = []
    monkeypatch.setattr(fight, "hit", lambda ch, victim, hand: record.append((ch.name, victim.name)))
    yield record
    characters.clear()
    zones.stop()


def npc(name, vnum=101):
    c = Npc(name, SEX_NEUTRAL, zones.world.rooms[vnum])
    characters.append(c)
    return c


async def until(cond, timeout=2):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not cond():
        assert loop.time() < end, "等太久"
        await asyncio.sleep(0.005)


def test_victim_fights_back(hits):
    async def main():
        a, b = npc("甲"), npc("乙")
        f = start_fight(a, b)
        assert (a.fighting, b.fighting) == (b, a)
        assert (a.fight, b.fight) == (f, f) and f.members == [a, b]
        assert a.position == b.position == Position.FIGHTING
        assert f in zones.world.fights
        await until(lambda: len(hits) >= 4)
        assert hits[:4] == [("甲", "乙"), ("乙", "甲")] * 2    # 每回合照加入的順序出手

    asyncio.run(main())


def test_two_fights_each_have_their_own_loop(hits):
    async def main():
        a, b, c, d = npc("甲"), npc("乙"), npc("丙"), npc("丁")
        f1 = start_fight(a, b)
        await asyncio.sleep(0.005)          # 第二場晚一點開打：節拍從自己開打算起
        f2 = start_fight(c, d)
        assert f1 is not f2 and f1.task is not f2.task
        await until(lambda: ("丙", "丁") in hits and ("甲", "乙") in hits)
        stop_fighting(a)                    # 第一場結束，第二場照打
        stop_fighting(b)
        await until(lambda: f1.task.done())
        before = hits.count(("丙", "丁"))
        await until(lambda: hits.count(("丙", "丁")) >= before + 3)
        assert not f2.task.done()

    asyncio.run(main())


def test_third_person_joins_the_same_fight(hits):
    async def main():
        a, b, c = npc("甲"), npc("乙"), npc("丙")
        f = start_fight(a, b)
        assert start_fight(c, b) is f
        assert f.members == [a, b, c]
        assert (c.fighting, b.fighting) == (b, a)   # 乙原本在打甲，不會換對手

    asyncio.run(main())


def test_two_fights_merge_into_the_older_one(hits):
    async def main():
        a, b, c, d = npc("甲"), npc("乙"), npc("丙"), npc("丁")
        f1 = start_fight(a, b)
        f2 = start_fight(c, d)
        assert start_fight(a, c) is f1      # 甲改打丙：後開的第二場併進第一場
        assert f1.members == [a, b, c, d] and all(x.fight is f1 for x in (a, b, c, d))
        assert f2.members == [] and f2 not in zones.world.fights
        await until(lambda: f2.task.done())

    asyncio.run(main())


def test_fight_ends_when_opponent_leaves_the_room(hits):
    async def main():
        a, b = npc("甲"), npc("乙")
        f = start_fight(a, b)
        b.room = zones.world.rooms[102]     # 乙走掉了
        await until(lambda: f.task.done())
        assert a.fight is None and b.fight is None
        assert a.position == b.position == Position.STANDING
        assert zones.world.fights == set()

    asyncio.run(main())


def test_fight_ends_when_opponent_leaves_the_game(hits):
    async def main():
        a, b = npc("甲"), npc("乙")
        f = start_fight(a, b)
        stop_fighting(b)                    # 斷線時 server.handle() 會這樣做
        characters.remove(b)
        await until(lambda: f.task.done())
        assert a.fight is None and a.position == Position.STANDING

    asyncio.run(main())


def test_stopped_victim_is_pulled_back(hits):
    # 乙停手了但還在房間裡，甲還在打他：乙被拉回這一場（C 版也是這樣）
    async def main():
        a, b = npc("甲"), npc("乙")
        f = start_fight(a, b)
        stop_fighting(b)
        await until(lambda: b.fight is f)
        assert b.fighting is a and b.position == Position.FIGHTING

    asyncio.run(main())


def test_error_in_one_fight_only_ends_that_fight(hits, monkeypatch, caplog):
    def hit(ch, victim, hand):
        if ch.name == "甲":
            raise RuntimeError("壞掉了")
        hits.append((ch.name, victim.name))

    monkeypatch.setattr(fight, "hit", hit)

    async def main():
        a, b, c, d = npc("甲"), npc("乙"), npc("丙"), npc("丁")
        f1 = start_fight(a, b)
        f2 = start_fight(c, d)
        await until(lambda: f1.task.done())
        assert a.fight is None and b.fight is None
        before = hits.count(("丙", "丁"))
        await until(lambda: hits.count(("丙", "丁")) >= before + 3)
        assert not f2.task.done()

    with caplog.at_level(logging.ERROR):
        asyncio.run(main())
    assert "戰鬥出錯" in caplog.text


# ---- 時間軸出手：一個 tick 一個 tick 看（玩家角色手冊「戰鬥的出手順序」） ----

@pytest.fixture
def manual(monkeypatch):
    # loop 不會自己跑（一個 tick 100 秒），測試自己呼叫 f.tick()；出手記下名字，副手加「副」
    zones.load(AREAS)
    monkeypatch.setattr(fight, "TICK_SECONDS", 100)
    record = []
    monkeypatch.setattr(fight, "hit", lambda ch, victim, hand: record.append(ch.name + ("副" if hand else "")))
    yield record
    characters.clear()
    zones.stop()


def run_ticks(f, record, n):
    """跑 n 個 tick，回傳每個 tick 出手的人。"""
    out = []
    for _ in range(n):
        record.clear()
        f.tick()
        out.append(list(record))
    return out


def test_one_round_is_hit_then_rest(manual):
    # 一回合 2 tick：打一輪、停一秒。同一時間開打的人先打
    async def main():
        f = start_fight(npc("甲"), npc("乙"))
        assert run_ticks(f, manual, 4) == [["甲", "乙"], [], ["甲", "乙"], []]

    asyncio.run(main())


def test_faster_hand_hits_more_often(manual, monkeypatch):
    # 甲每回合 1.25 下：間隔 1.6 tick，出手在 0、1.6、3.2…、14.4、16、17.6；乙每回合 1 下：0、2、4…
    # 四輪打五下；同時在 8、16 時甲先（先動手）。
    # 坑：1.6 一直加，第 10 下會是 15.999999999999998，沒取整的話會掉進第 8 輪（14～16），第 9 輪少一下
    monkeypatch.setattr(fight, "attacks", lambda ch: [1.25] if ch.name == "甲" else [1.0])

    async def main():
        f = start_fight(npc("甲"), npc("乙"))
        assert run_ticks(f, manual, 18)[::2] == [
            ["甲", "乙", "甲"], ["乙", "甲"], ["乙", "甲"], ["乙", "甲"],
            ["甲", "乙", "甲"], ["乙", "甲"], ["乙", "甲"], ["乙", "甲"], ["甲", "乙", "甲"]]

    asyncio.run(main())


def test_dual_wield_main_hand_first(manual, monkeypatch):
    # 甲雙持：主手每回合 1 下、副手 0.5 下（每兩輪一下）。同一時間主手先、副手後
    monkeypatch.setattr(fight, "attacks", lambda ch: [1.0, 0.5] if ch.name == "甲" else [1.0])

    async def main():
        f = start_fight(npc("甲"), npc("乙"))
        assert run_ticks(f, manual, 6)[::2] == [["甲", "甲副", "乙"], ["甲", "乙"], ["甲", "甲副", "乙"]]

    asyncio.run(main())


def test_joiner_first_hit_is_when_joining(manual):
    # 丙在第 1 個 tick 後加入：第一下排在 1，比甲、乙在 2 的那一下先；下一下在 3，同一輪
    async def main():
        a, b, c = npc("甲"), npc("乙"), npc("丙")
        f = start_fight(a, b)
        assert run_ticks(f, manual, 1) == [["甲", "乙"]]
        start_fight(c, b)
        assert run_ticks(f, manual, 2) == [[], ["丙", "甲", "乙", "丙"]]

    asyncio.run(main())


def test_rejoining_cancels_old_schedule(manual):
    # 乙停手後馬上又加入：舊的排程作廢，同一時間不會打兩下
    async def main():
        a, b = npc("甲"), npc("乙")
        f = start_fight(a, b)
        stop_fighting(b)
        start_fight(b, a)
        assert run_ticks(f, manual, 1) == [["甲", "乙"]]

    asyncio.run(main())
