"""Lv15、Lv25 的公會被動（設計文件 §2.6，2026-11-20 使用者定的：不是打架用的，讓玩家少休息）：
調息、冥想（休息、睡覺回復 ×1.5，跟吃喝的加倍疊在一起；站著不變）；
收刀、回神（整場戰鬥結束 HP、MP、MV 各回上限的 10%；打死第一隻、逃跑不算，隊友打死也算）；升到那一級自動學會、登入補學。
"""
import pytest

from mud import death, paths, skills, stats
from mud.characters import Position
from mud.commands import combat as combat_commands
from test_skills import fighter, in_fight, mobile, world  # noqa: F401（world 是 fixture）

BREATH, MEDITATE = skills.SKILLS["breath_control"], skills.SKILLS["meditate"]
SHEATHE, RECOLLECT = skills.SKILLS["sheathe"], skills.SKILLS["recollect"]


def low(p):
    """HP、MP、MV 都只剩 1。"""
    p.hp = p.mp = p.mv = 1.0
    return p


# ---- 調息、冥想 ----

@pytest.mark.parametrize("position, rate, times", [(Position.RESTING, 0.20, 1.5), (Position.SLEEPING, 0.30, 1.5),
                                                   (Position.STANDING, 0.10, 1.0)])
@pytest.mark.parametrize("guild, skill", [(stats.Guild.SWORD, BREATH), (stats.Guild.STAFF, MEDITATE)])
def test_rest_regen(world, position, rate, times, guild, skill):
    p, plain = low(fighter("Shabu", level=15, guild=guild)), low(fighter("Ming", level=15, guild=guild))
    skills.learn(p, skill)
    for x in (p, plain):
        x.position = position
        stats.regen(x)
    for key in ("hp", "mp", "mv"):                                   # HP、MP、MV 都算
        assert getattr(p, key) - 1 == pytest.approx(p.panel[key] * rate * times)
        assert getattr(plain, key) - 1 == pytest.approx(plain.panel[key] * rate)


def test_rest_regen_stacks_with_meals(world):
    p = low(fighter("Shabu", level=15))
    skills.learn(p, BREATH)
    p.position, p.meal_bonus = Position.SLEEPING, {"hp": 2}
    stats.regen(p)
    assert p.hp - 1 == pytest.approx(p.panel["hp"] * 0.30 * 2 * 1.5)      # 吃過再睡：30% × 2 × 1.5 ＝ 90%


# ---- 收刀、回神 ----

@pytest.mark.parametrize("guild, skill", [(stats.Guild.SWORD, SHEATHE), (stats.Guild.STAFF, RECOLLECT)])
def test_the_last_foe_dying_gives_back_10_percent(world, guild, skill):
    p = low(fighter("Shabu", level=25, guild=guild))
    skills.learn(p, skill)
    dog = mobile("野狗")

    def body():
        death.die(dog)
        return p.hp, p.mp, p.mv

    assert in_fight([(p, dog)], body) == pytest.approx(tuple(1 + p.panel[k] * 0.10 for k in ("hp", "mp", "mv")))


def test_it_stops_at_the_maximum(world):
    p = fighter("Shabu", level=25)
    skills.learn(p, SHEATHE)
    p.hp = p.panel["hp"] - 1

    def body():
        death.die(mobile("野狗"))
        return p.hp

    assert in_fight([(p, mobile("野狗"))], body) == p.panel["hp"]


def test_not_until_the_whole_fight_is_over(world):
    """一次打兩隻：打死第一隻、另一隻還在打你，不回；最後一隻死了才回。"""
    p = low(fighter("Shabu", level=25))
    skills.learn(p, SHEATHE)
    dog, cat = mobile("野狗"), mobile("野貓")

    def body():
        death.die(dog)
        first = p.hp
        death.die(cat)
        return first, p.hp

    first, last = in_fight([(p, dog), (cat, p)], body)
    assert first == 1 and last == pytest.approx(1 + p.panel["hp"] * 0.10)


def test_a_teammate_killing_it_counts(world):
    p, ming = low(fighter("Shabu", level=25)), fighter("Ming", level=25)
    skills.learn(p, SHEATHE)
    dog = mobile("野狗")

    def body():
        death.die(dog, killer=ming)
        return p.hp

    assert in_fight([(p, dog), (ming, dog)], body) == pytest.approx(1 + p.panel["hp"] * 0.10)


def test_fleeing_does_not_count(world):
    p = low(fighter("Shabu", level=25))
    skills.learn(p, SHEATHE)
    dog = mobile("野狗")

    def body():
        combat_commands.escape(p, "south")                          # 逃走了，牠之後才死
        death.die(dog)
        return p.hp

    assert in_fight([(p, dog)], body) == 1


def test_without_the_skill_nothing_happens(world):
    p = low(fighter("Shabu", level=25))
    dog = mobile("野狗")

    def body():
        death.die(dog)
        return p.hp

    assert in_fight([(p, dog)], body) == 1


# ---- 怎麼學 ----

@pytest.mark.parametrize("guild, at_15, at_25", [(stats.Guild.SWORD, "調息", "收刀"), (stats.Guild.STAFF, "冥想", "回神")])
def test_learned_on_level_up(world, guild, at_15, at_25):
    p = fighter("Shabu", level=5, guild=guild)
    paths.learn_upto(p)
    stats.set_level(p, 15)
    assert (paths.LEARNED, at_15) in paths.level_up_lines(p, 14)
    stats.set_level(p, 25)
    assert (paths.LEARNED, at_25) in paths.level_up_lines(p, 15)


def test_old_characters_learn_them_when_logging_in(world):
    p = fighter("Shabu", level=30)
    assert [s.name for s in paths.catch_up(p)] == ["猛擊", "調息", "收刀"]
    assert paths.catch_up(p) == []                                   # 學過了不再說
