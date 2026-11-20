"""保護類技能（設計文件 §2.6）：挑釁（怪馬上改打你、一定成功、被挑釁 6 秒）、群體挑釁、
守護和不倒之盾（被保護的人被打的傷害幾成改由你承受：先扣你的護盾、可以扣死你、離開房間就停、時間到就停、持續扣血也算）。

借用 test_skills.py 的區域：房間 102 有 5 級的野狗和野貓，101 在南邊（START_ROOM 是 101）。
"""
import re

import pytest

from mud import affects, combat, protect, skills
from mud.area import MobTier
from mud.config import TICK_SECONDS
from test_skills import fighter, in_fight, mobile, prompt_of, say, text_of, world  # noqa: F401（world 是 fixture）


@pytest.fixture(autouse=True)
def no_guards():
    protect.guards.clear()
    yield
    protect.guards.clear()


def knight(name="Shabu", learn=(), room=102):
    p = fighter(name, room=room, level=10)
    p.skills += list(learn)
    return p


def reply(p, *lines):
    return "\r\n".join(lines) + f"\r\n\r\n{prompt_of(p)}"


# ---- 挑釁 ----

def test_taunt_turns_the_mobile_on_you(world):
    p, ming = knight(learn=["taunt"]), knight("Ming")
    dog = mobile("野狗")
    got, foe = in_fight([(ming, dog)], lambda: (say(p, "use taunt dog"), dog.fighting))
    assert got == reply(p, "你對野狗施展了【挑釁】。", "野狗被激怒了！", "野狗十分的健康，完整。")
    assert foe is p
    provoked = next(a for a in dog.affects if a.source == "taunt")
    assert (provoked.tag, provoked.duration * TICK_SECONDS) == ("被挑釁", 6)


def test_taunt_always_works_even_on_bosses(world, monkeypatch):
    from test_skills import Always
    monkeypatch.setattr(combat, "rng", Always(0.99))                 # 打不中也一樣：不擲命中
    p, ming = knight(learn=["taunt"]), knight("Ming")
    dog = mobile("野狗")
    dog.tier = MobTier.BOSS
    assert in_fight([(ming, dog)], lambda: (say(p, "use taunt dog"), dog.fighting)[1]) is p


def test_challenge_turns_everyone(world):
    p, ming = knight(learn=["challenge"]), knight("Ming")
    dog, cat = mobile("野狗"), mobile("野貓")
    foes = in_fight([(ming, dog)], lambda: (say(p, "use challenge"), dog.fighting, cat.fighting)[1:])
    assert foes == (p, p)                                            # 還沒在打架的貓也開打
    assert all(affects.has_tag(m, "被挑釁") for m in (dog, cat))


# ---- 守護 ----

def test_guard_takes_part_of_the_damage(world):
    p, ming = knight(learn=["guard"]), knight("Ming")
    dog = mobile("野狗")
    plain_p = text_of
    assert say(p, "use guard ming") == reply(p, "你對Ming施展了【守護】。")
    hp, mine = p.hp, ming.hp

    def body():
        combat.land(ming.fight, dog, ming, 20.0, False)
        ming.fight.flush()
        return plain_p(p), text_of(ming)

    seen, theirs = in_fight([(dog, ming)], body)
    assert (ming.hp, p.hp) == (pytest.approx(mine - 14), pytest.approx(hp - 6))    # 30% 改由你承受
    assert "你替Ming擋下了 6 點傷害。" in seen and "Shabu替你擋下了 6 點傷害。" in theirs
    assert "對你造成" in theirs and "(14)" in theirs                 # 他的訊息寫他自己受的


def test_guard_hits_your_shield_first(world):
    p, ming = knight(learn=["guard"]), knight("Ming")
    say(p, "use guard ming")
    skills.use(p, skills.SKILLS["aegis"], p, pay_cost=False)
    hp = p.hp
    in_fight([(mobile("野狗"), ming)], lambda: combat.land(ming.fight, mobile("野狗"), ming, 20.0, False))
    assert p.hp == hp and p.affects[0].shield == pytest.approx(p.panel["hp"] * 1.2 - 6)


def test_guard_stops_when_either_leaves(world):
    p, ming = knight(learn=["guard"]), knight("Ming")
    say(p, "use guard ming")
    say(p, "s")
    assert protect.split(ming, 20.0) == (20.0, [])                   # 不在同一間房：停了
    say(p, "n")
    assert protect.split(ming, 20.0) == (20.0, [])                   # 回來也不會再有


def test_guard_stops_when_time_runs_out(world):
    p, ming = knight(learn=["guard"]), knight("Ming")
    say(p, "use guard ming")
    for _ in range(29):
        protect.tick()
    assert protect.split(ming, 20.0)[0] == pytest.approx(14.0)
    protect.tick()
    assert protect.split(ming, 20.0) == (20.0, []) and ming not in protect.guards


def test_guard_mistakes(world):
    p = knight(learn=["guard", "last_stand"])
    assert say(p, "use guard") == reply(p, "你不能保護自己。")
    assert say(p, "use guard dog") == reply(p, "守護只能放在玩家身上。")
    assert say(p, "use last") == reply(p, "這裡沒有別人可以保護。")
    assert p.cooldowns == {}


def test_last_stand_guards_everyone_else(world):
    p, ming, hua = knight(learn=["last_stand"]), knight("Ming"), knight("Hua")
    say(p, "use last")
    assert [protect.split(c, 20.0)[0] for c in (ming, hua)] == [10.0, 10.0]
    assert p not in protect.guards


def test_two_guards_add_up(world):
    p, hua, ming = knight(learn=["guard"]), knight("Hua", learn=["last_stand"]), knight("Ming")
    say(p, "use guard ming")
    say(hua, "use last")
    left, parts = protect.split(ming, 20.0)
    assert left == pytest.approx(4.0) and [(g.name, n) for g, n in parts] == [("Shabu", 6.0), ("Hua", 10.0)]


def test_guard_covers_damage_over_time(world):
    p, ming = knight(learn=["guard"]), knight("Ming")
    say(p, "use guard ming")
    hp, mine = p.hp, ming.hp
    affects.add(ming, affects.Affect(source="x", name="測試毒", duration=30, periodic={"hp": -10.0}))
    for _ in range(3):
        affects.tick()
    assert (ming.hp, p.hp) == (pytest.approx(mine - 7), pytest.approx(hp - 3))


def test_the_guardian_can_die(world):
    p, ming = knight(learn=["guard"]), knight("Ming")
    say(p, "use guard ming")
    p.hp = 1
    in_fight([(mobile("野狗"), ming)], lambda: combat.land(ming.fight, mobile("野狗"), ming, 20.0, False))
    assert p.room.vnum == 101 and p.hp == 1                        # 死掉回起始房間（玩家死掉的規則）
    assert protect.split(ming, 20.0) == (20.0, [])


def test_skills_listing_for_protection(world):
    p = knight(learn=["taunt", "guard", "last_stand"])
    from mud.commands import skills as skill_commands
    skill_commands.do_skills(p, "")
    text = text_of(p)
    assert re.search(r"挑釁 taunt +持續 6 秒 .*\r\n +改打你（被挑釁）\r\n", text)
    assert re.search(r"守護 guard +持續 30 秒 .*\r\n +被打的傷害 30% 改由你承受\r\n", text)
    assert re.search(r"不倒之盾 last_stand +持續 10 秒 .*\r\n +被打的傷害 50% 改由你承受、同房間的其他玩家\r\n", text)


def test_guards_never_take_more_than_all_of_it(world):
    p, hua = knight(learn=["last_stand"]), knight("Hua", learn=["last_stand"])
    kai, ming = knight("Kai", learn=["guard"]), knight("Ming")
    for c, line in ((p, "use last"), (hua, "use last"), (kai, "use guard ming")):
        say(c, line)
    left, parts = protect.split(ming, 20.0)
    assert left == 0 and [(g.name, n) for g, n in parts] == [("Shabu", 10.0), ("Hua", 10.0)]   # 50% ＋ 50%，守護的 30% 沒得分
