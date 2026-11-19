"""控制類技能（設計文件 §2.6）：擲命中、暈和凍住不能出手、不能走、不能逃、不能用技能和 special，沉默不能用技能和 special，
抵抗 6 秒、已經暈著再暈沒有作用、首領時間減半、盾擊先打再暈、冰錐的變慢也照控制的規則。

借用 test_skill_kinds.py 的玩家、亂數（test_items.py 的區域：房間 102 有一隻 5 級的野狗）。
"""
import pytest

from mud import affects, behavior, combat, fight, skills, specials
from mud.area import ActFlag, MobTier
from mud.config import TICK_SECONDS
from test_items import reply, the_dog, world  # noqa: F401（world 是 fixture）
from test_skill_kinds import SHIELD, STAFF, Always, hero, in_fight, plain, say, steady, sturdy_dog, wield  # noqa: F401

HELD = "你現在動彈不得。"


def stun(ch, kind="stun", ticks=4):
    affects.add(ch, affects.Affect(source=f"test_{kind}", name="測試", duration=ticks, control=kind))


def control_of(ch, source):
    return next((a for a in ch.affects if a.source == source), None)


# ---- 放上去 ----

def test_stun_strike_rolls_to_hit_then_stuns(world):
    p = hero(learn=["stun_strike"])
    dog = the_dog()
    got = in_fight([], lambda: say(p, "use stun dog"))
    assert got == reply(p, "你對野狗施展了【擊暈】。", "野狗被打暈了！")
    a = control_of(dog, "stun_strike")
    assert (a.control, a.tag, a.duration * TICK_SECONDS) == ("stun", "暈", 4)


def test_control_can_miss(world, monkeypatch):
    monkeypatch.setattr(combat, "rng", Always(0.99))
    p = hero(learn=["stun_strike"])
    dog = the_dog()
    assert in_fight([], lambda: say(p, "use stun dog")) == reply(p, "你對野狗施展【擊暈】，但是失手了。")
    assert dog.affects == []


@pytest.mark.parametrize("skill, kind, seconds, text", [
    ("freeze", "freeze", 4, "野狗被凍住了！"), ("absolute_zero", "freeze", 8, "野狗被凍住了！"),
    ("shadow_bind", "stun", 8, "野狗被打暈了！"), ("garrote", "silence", 6, "野狗發不出聲音了！"),
    ("slow", "slow", 30, "野狗的動作變慢了。")])
def test_each_control(world, skill, kind, seconds, text):
    s = skills.SKILLS[skill]
    p = hero(guild=s.guild, learn=[skill])
    dog = the_dog()
    assert text in in_fight([], lambda: say(p, f"use {skill} dog"))
    a = control_of(dog, skill)
    assert (a.control, a.duration * TICK_SECONDS) == (kind, seconds)


def test_already_stunned_or_resisting_is_unaffected(world):
    p = hero(learn=["stun_strike"])
    dog = the_dog()
    stun(dog, "freeze", 3)
    got = in_fight([], lambda: say(p, "use stun dog"))
    assert got == reply(p, "你對野狗施展了【擊暈】。", "野狗沒有受到影響。")
    assert [a.source for a in dog.affects] == ["test_freeze"]       # 不重算時間，也不多一個
    for _ in range(3):
        affects.tick()
    assert [a.source for a in dog.affects] == [affects.RESIST_SOURCE]   # 凍住結束：抵抗 6 秒
    p.cooldowns = {}
    assert "野狗沒有受到影響。" in in_fight([], lambda: say(p, "use stun dog"))
    for _ in range(affects.RESIST_TICKS):
        affects.tick()
    assert dog.affects == []
    p.cooldowns = {}
    assert "野狗被打暈了！" in in_fight([], lambda: say(p, "use stun dog"))


def test_other_controls_are_not_resisted(world):
    p = hero(guild=STAFF, learn=["slow"])
    dog = the_dog()
    stun(dog)
    assert "野狗的動作變慢了。" in in_fight([], lambda: say(p, "use slow dog"))


def test_bosses_take_half_the_time(world):
    p = hero(guild=STAFF, learn=["freeze", "slow", "ice_shard"])
    dog = sturdy_dog()
    dog.tier = MobTier.BOSS
    in_fight([], lambda: say(p, "use freeze dog"))
    in_fight([], lambda: say(p, "use slow dog"))
    in_fight([], lambda: say(p, "use ice dog"))                   # 打中後的變慢也是控制的規則
    assert {a.source: a.duration * TICK_SECONDS for a in dog.affects} == {"freeze": 2, "slow": 15, "ice_shard": 3}


def test_shield_bash_hits_then_stuns(world):
    p = hero(learn=["shield_bash"])
    dog = sturdy_dog()
    assert say(p, "use shield dog") == reply(p, "你要拿盾才能用盾擊。")
    wield(p, SHIELD, "offhand")
    got = in_fight([], lambda: say(p, "use shield dog"))
    assert got.startswith("你使用盾擊攻擊野狗，") and "野狗被打暈了！" in got
    assert control_of(dog, "shield_bash").duration * TICK_SECONDS == 4


def test_shield_bash_misses_without_stunning(world, monkeypatch):
    monkeypatch.setattr(combat, "rng", Always(0.99))
    p = hero(learn=["shield_bash"])
    wield(p, SHIELD, "offhand")
    dog = sturdy_dog()
    in_fight([], lambda: say(p, "use shield dog"))
    assert dog.affects == []


# ---- 有作用 ----

def test_stunned_and_frozen_do_not_attack(world, monkeypatch):
    p, dog = hero(), the_dog()
    hits = []
    monkeypatch.setattr(fight, "hit", lambda ch, victim, hand: hits.append(ch))

    def body():
        battle = p.fight
        stun(dog, "freeze")
        battle.tick()
        return set(hits)

    assert in_fight([(p, dog)], body) == {p}                         # 時間照排，牠只是不出手


def test_silenced_still_attacks(world, monkeypatch):
    p, dog = hero(), the_dog()
    hits = []
    monkeypatch.setattr(fight, "hit", lambda ch, victim, hand: hits.append(ch))

    def body():
        stun(dog, "silence")
        p.fight.tick()
        return set(hits)

    assert in_fight([(p, dog)], body) == {p, dog}


@pytest.mark.parametrize("kind, used", [(None, True), ("stun", False), ("freeze", False), ("silence", False), ("slow", True)])
def test_specials_wait_while_held_or_silenced(world, monkeypatch, kind, used):
    p, dog = hero(), the_dog()
    calls = []
    monkeypatch.setattr(specials, "use", lambda battle, npc: calls.append(npc))

    def body():
        battle = p.fight
        battle.special_at[dog] = battle.ticks
        if kind:
            stun(dog, kind)
        specials.fight(battle)
        return battle.special_at[dog] > battle.ticks                 # 時間照排

    assert in_fight([(p, dog)], body) and (calls == [dog]) == used


def test_held_players_cannot_walk_flee_or_use_skills(world):
    p = hero(learn=["power_slash"])
    stun(p)
    assert say(p, "s") == reply(p, HELD)
    assert in_fight([(p, the_dog())], lambda: (say(p, "flee"), say(p, "use power"))) == (reply(p, HELD), reply(p, HELD))
    assert p.room.vnum == 102


def test_silenced_players_can_walk_but_not_use_skills(world):
    p = hero(learn=["power_slash"])
    stun(p, "silence")
    assert say(p, "use power dog") == reply(p, "你現在發不出聲音，不能用技能。")
    say(p, "s")
    assert p.room.vnum == 101


def test_held_wimpy_mobiles_do_not_run(world, monkeypatch):
    monkeypatch.setattr(behavior, "rng", Always(0.0))
    p, dog = hero(), the_dog()
    dog.act |= ActFlag.WIMPY
    dog.hp = 1

    def body():
        stun(dog)
        behavior.wimpy(p.fight)
        return dog.room.vnum, dog.fighting is p

    assert in_fight([(p, dog)], body) == (102, True)


def test_parts_names_the_control():
    a = affects.Affect(source="slow", name="緩速術", duration=30, mult={"aspd": 0.85}, control="slow")
    assert affects.parts(a) == ["攻速 -15%", "變慢"]
