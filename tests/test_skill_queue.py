"""打架中更順（skill_queue.py，設計文件 §2.6，使用者 2026-11-21 定的）：技能排隊、破綻、有餽贈時技能只扣一半。

用 test_skills.py 的世界（102 有 5 級的野狗、野貓）。平砍換成不打（fight.hit），一段訊息裡只有技能、破綻、受傷狀態；
自己呼叫 Fight.tick()（第 1、3、5… 個是回合打完的那個 tick）、skills.tick()（冷卻減 1）。破綻的亂數預設不會中（conftest.py），要的自己換。
"""
import pytest

from test_skills import Always, Counting, fighter, in_fight, mobile, prompt_of, raw, say, text_of, world  # noqa: F401（world 是 fixture）
from mud import affects, death, fight, skill_queue, skills, stats, zones
from mud.characters import characters
from mud.commands import combat as combat_command
from mud.commands.system import condition

SMASH, PUMMEL, BERSERK = skills.SKILLS["smash"], skills.SKILLS["pummel"], skills.SKILLS["berserk"]
REAL_HIT = fight.hit


@pytest.fixture(autouse=True)
def no_swings(monkeypatch):
    monkeypatch.setattr(fight, "hit", lambda ch, victim, hand: None)


@pytest.fixture(autouse=True)
def no_fight_errors(caplog):
    """Fight.tick() 出錯只記 log、結束那一場：沒看 log 的話，「靜靜不放」跟「當掉」分不出來。"""
    yield
    assert "戰鬥出錯" not in caplog.text


def segment(p):
    """p 收到的一段（notify 送的）：中間那幾行；只能有一個 prompt。"""
    text = text_of(p)
    assert text.count(prompt_of(p)) == 1, text
    lines = text.split("\r\n")
    assert lines[0] == "" and lines[-2] == "" and lines[-1] == prompt_of(p), text
    return lines[1:-2]


class Escapes:
    """flee、打架中 recall 一定成功的亂數（flee 挑第一個出口）。"""

    def random(self):
        return 0.0

    def choice(self, seq):
        return seq[0]


def tick_cooldowns(n):
    for _ in range(n):
        skills.tick()


def test_using_a_skill_on_cooldown_in_a_fight_queues_it(world):
    shabu, dog = fighter("Shabu"), mobile("野狗")

    def body():
        return say(shabu, "use smash"), say(shabu, "use smash"), dict(shabu.queued)

    first, again, queued = in_fight([(shabu, dog)], body)
    assert first.startswith("你使用重擊攻擊野狗，")
    assert again == f"重擊還要等 6 秒，好了就放。\r\n\r\n{prompt_of(shabu)}"
    assert queued == {"smash": None}                                # 沒打名字：放的時候打當時的對手


def test_not_fighting_still_waits(world):
    shabu, dog = fighter("Shabu"), mobile("野狗")
    shabu.cooldowns["smash"] = 3
    got = say(shabu, "use smash dog")
    assert got.startswith("你還要等 3 秒才能再用重擊。")
    assert (shabu.queued, shabu.fighting, dog.fighting) == ({}, None, None)     # 不排、不開打


def test_queued_skill_fires_when_ready_in_the_fights_segment(world):
    shabu, dog = fighter("Shabu"), mobile("野狗")
    mv = shabu.mv

    def body():
        say(shabu, "use smash")
        say(shabu, "use smash")
        tick_cooldowns(5)
        shabu.fight.tick()
        waiting = text_of(shabu)
        tick_cooldowns(1)
        shabu.fight.tick()
        return waiting, segment(shabu), dict(shabu.queued)

    waiting, got, queued = in_fight([(shabu, dog)], body)
    assert waiting == ""                                            # 還沒好：不放
    assert got[0].startswith("你使用重擊攻擊野狗，") and got[-1] == "野狗" + condition(dog)
    assert queued == {} and shabu.cooldowns == {"smash": 6}
    assert shabu.mv == pytest.approx(mv - 2 * skills.cost(SMASH, 1))


def test_same_skill_again_changes_the_target_and_keeps_its_place(world):
    shabu, dog, cat = fighter("Shabu"), mobile("野狗"), mobile("野貓")
    shabu.skills.append("pummel")
    shabu.cooldowns.update(smash=3, pummel=3)

    def body():
        say(shabu, "use smash")
        say(shabu, "use pummel")
        say(shabu, "use smash cat")
        return list(shabu.queued.items()), cat.fighting

    queued, cats = in_fight([(shabu, dog)], body)
    assert queued == [("smash", cat), ("pummel", None)]
    assert cats is None                                             # 排起來還沒放：不開打


def test_each_fires_when_its_own_cooldown_is_done(world):
    shabu, dog = fighter("Shabu"), mobile("野狗")
    shabu.skills.append("pummel")
    shabu.cooldowns.update(smash=2, pummel=1)

    def body():
        say(shabu, "use smash")
        say(shabu, "use pummel")
        tick_cooldowns(1)
        shabu.fight.tick()
        first = segment(shabu)
        tick_cooldowns(1)
        shabu.fight.tick()
        return first, segment(shabu)

    first, second = in_fight([(shabu, dog)], body)
    assert first[0].startswith("你使用猛擊攻擊野狗") and not any("重擊" in line for line in first)
    assert second[0].startswith("你使用重擊攻擊野狗")


def test_ready_at_the_same_time_fire_in_queue_order(world):
    shabu, dog = fighter("Shabu"), mobile("野狗")
    shabu.skills.append("pummel")
    shabu.cooldowns.update(smash=1, pummel=1)

    def body():
        say(shabu, "use pummel")
        say(shabu, "use smash")
        tick_cooldowns(1)
        shabu.fight.tick()
        return segment(shabu), dict(shabu.queued)

    got, queued = in_fight([(shabu, dog)], body)
    first_pummel = next(i for i, line in enumerate(got) if line.startswith("你使用猛擊"))
    first_smash = next(i for i, line in enumerate(got) if line.startswith("你使用重擊"))
    assert first_pummel < first_smash and got[-1] == "野狗" + condition(dog)
    assert queued == {}


def test_failing_checks_say_the_usual_line_and_drop_it(world):
    shabu, dog = fighter("Shabu"), mobile("野狗")
    shabu.cooldowns["smash"] = 1

    def body():
        say(shabu, "use smash")
        shabu.mv = 0.0
        tick_cooldowns(1)
        shabu.fight.tick()
        return segment(shabu), dict(shabu.queued)

    got, queued = in_fight([(shabu, dog)], body)
    assert got == ["你的 MV 不夠。", "野狗" + condition(dog)]
    assert queued == {}


def test_named_target_gone_is_dropped_quietly(world):
    shabu, dog, cat = fighter("Shabu"), mobile("野狗"), mobile("野貓")
    shabu.cooldowns["smash"] = 1

    def body():
        say(shabu, "use smash cat")
        cat.room = zones.world.rooms[101]                           # 不在這裡了
        tick_cooldowns(1)
        shabu.fight.tick()
        return text_of(shabu), dict(shabu.queued), cat.fighting

    assert in_fight([(shabu, dog)], body) == ("", {}, None)


def test_held_keeps_it_queued_until_free(world):
    shabu, dog = fighter("Shabu"), mobile("野狗")
    shabu.cooldowns["smash"] = 1

    def body():
        say(shabu, "use smash")
        affects.add(shabu, affects.Affect("test_stun", "暈", 10, control="stun"))
        tick_cooldowns(1)
        shabu.fight.tick()
        held = (text_of(shabu), dict(shabu.queued))
        affects.remove(shabu, "test_stun")
        shabu.fight.tick()
        return held, segment(shabu)

    (held_text, held_queue), got = in_fight([(shabu, dog)], body)
    assert held_text == "" and held_queue == {"smash": None}
    assert got[0].startswith("你使用重擊攻擊野狗，")


def test_queued_buff_messages_go_into_the_segment(world):
    shabu, dog = fighter("Shabu"), mobile("野狗")
    ming = fighter("Ming")
    shabu.skills.append("berserk")
    shabu.cooldowns["berserk"] = 1

    def body():
        say(shabu, "use berserk")
        raw(ming)
        tick_cooldowns(1)
        shabu.fight.tick()
        return segment(shabu), segment(ming)

    mine, theirs = in_fight([(shabu, dog)], body)
    assert mine[0] == f"你對自己施展了【{BERSERK.name}】。" and mine[-1] == "野狗" + condition(dog)
    assert theirs == [f"Shabu對自己施展了【{BERSERK.name}】。"]
    assert affects.has_tag(shabu, BERSERK.name) or any(a.source == "berserk" for a in shabu.affects)


def test_auto_fired_skill_can_kill(world, monkeypatch):
    monkeypatch.setattr(fight, "hit", REAL_HIT)                     # 真的平砍
    shabu, dog = fighter("Shabu"), mobile("野狗")
    shabu.cooldowns["smash"] = 2

    def body():
        say(shabu, "use smash")
        shabu.fight.tick()                                          # 回合：平砍
        raw(shabu)
        dog.hp = 1.0
        tick_cooldowns(2)
        shabu.fight.tick()                                          # 停的那一秒：排著的重擊放出去、打死
        return segment(shabu), dict(shabu.queued)

    got, queued = in_fight([(shabu, dog)], body)
    assert got[0].startswith("你使用重擊攻擊野狗，") and any("斷氣" in line for line in got)
    assert not any(line.startswith("野狗") and line.endswith("。") and "斷氣" not in line and "屍體" not in line for line in got)
    assert queued == {} and dog not in characters


# ---- 清掉 ----

def test_killing_the_only_foe_clears_the_queue(world):
    shabu, dog = fighter("Shabu"), mobile("野狗")
    shabu.cooldowns["smash"] = 3

    def body():
        say(shabu, "use smash")
        shabu.breach = True
        death.die(dog, killer=shabu)
        return dict(shabu.queued), shabu.breach

    assert in_fight([(shabu, dog)], body) == ({}, False)


def test_another_foe_still_fighting_keeps_the_queue(world):
    shabu, dog, cat = fighter("Shabu"), mobile("野狗"), mobile("野貓")
    shabu.cooldowns["smash"] = 3

    def body():
        say(shabu, "use smash")
        death.die(dog, killer=shabu)
        return dict(shabu.queued)

    assert in_fight([(shabu, dog), (cat, shabu)], body) == {"smash": None}     # 野貓還在打他：戰鬥還沒結束


@pytest.mark.parametrize("line", ["flee", "recall"])
def test_flee_and_recall_clear_the_queue(world, monkeypatch, line):
    monkeypatch.setattr(combat_command, "rng", Escapes())
    shabu, dog = fighter("Shabu"), mobile("野狗")
    shabu.cooldowns["smash"] = 3

    def body():
        say(shabu, "use smash")
        shabu.breach = True
        say(shabu, line)
        return shabu.fighting, dict(shabu.queued), shabu.breach

    assert in_fight([(shabu, dog)], body) == (None, {}, False)


def test_foe_walking_away_clears_the_queue(world):
    shabu, dog = fighter("Shabu"), mobile("野狗")
    shabu.cooldowns["smash"] = 3

    def body():
        say(shabu, "use smash")
        dog.room = zones.world.rooms[101]
        shabu.fight.tick()                                          # 回合：兩邊都發現對手不在同一間房，停手
        return shabu.fighting, dict(shabu.queued)

    assert in_fight([(shabu, dog)], body) == (None, {})


def test_ending_the_fight_clears_the_queue(world):
    shabu, dog = fighter("Shabu"), mobile("野狗")
    shabu.cooldowns["smash"] = 3

    def body():
        say(shabu, "use smash")
        fight.end(shabu.fight)
        return dict(shabu.queued)

    assert in_fight([(shabu, dog)], body) == {}


def test_dying_clears_the_queue(world):
    shabu, dog = fighter("Shabu"), mobile("野狗")
    shabu.cooldowns["smash"] = 3

    def body():
        say(shabu, "use smash")
        death.player_dies(shabu)
        return dict(shabu.queued)

    assert in_fight([(shabu, dog)], body) == {}


# ---- 破綻 ----

def test_breach_shows_before_the_condition_only_to_you(world, monkeypatch):
    monkeypatch.setattr(skill_queue, "rng", Always(0.0))
    shabu, dog = fighter("Shabu"), mobile("野狗")
    ming = fighter("Ming")

    def body():
        raw(ming)
        shabu.fight.tick()
        return segment(shabu), text_of(ming), shabu.breach

    mine, theirs, breach = in_fight([(shabu, dog)], body)
    assert mine == ["野狗露出了破綻！", "野狗" + condition(dog)]
    assert theirs == "" and breach


def test_each_player_rolls_and_mobiles_do_not(world, monkeypatch):
    rolls = Counting()
    monkeypatch.setattr(skill_queue, "rng", rolls)
    shabu, ming, dog = fighter("Shabu"), fighter("Ming"), mobile("野狗")

    def body():
        shabu.fight.tick()

    in_fight([(shabu, dog), (ming, dog)], body)
    assert rolls.calls == 2


def test_breach_lasts_until_the_next_round(world, monkeypatch):
    monkeypatch.setattr(skill_queue, "rng", Always(0.0))
    shabu, dog = fighter("Shabu"), mobile("野狗")

    def body():
        shabu.fight.tick()                                          # 回合打完：有破綻
        monkeypatch.setattr(skill_queue, "rng", Always(1.0))
        shabu.fight.tick()                                          # 停的那一秒：還在
        kept = shabu.breach
        shabu.fight.tick()                                          # 下一回合打完：沒中就過了
        return kept, shabu.breach

    assert in_fight([(shabu, dog)], body) == (True, False)


def test_breach_lets_one_skill_skip_its_cooldown(world):
    shabu, dog = fighter("Shabu"), mobile("野狗")
    mv = shabu.mv
    shabu.cooldowns["smash"] = 4

    def body():
        shabu.breach = True
        return say(shabu, "use smash"), say(shabu, "use smash"), shabu.breach

    taken, again, breach = in_fight([(shabu, dog)], body)
    assert taken.startswith("你抓住了破綻！\r\n你使用重擊攻擊野狗，")
    assert again.startswith("重擊還要等 6 秒，好了就放。")           # 冷卻重新算；一次只多一個
    assert breach is False and shabu.mv == pytest.approx(mv - skills.cost(SMASH, 1))


def test_a_ready_skill_does_not_use_the_breach(world):
    shabu, dog = fighter("Shabu"), mobile("野狗")

    def body():
        shabu.breach = True
        return say(shabu, "use smash"), shabu.breach

    got, breach = in_fight([(shabu, dog)], body)
    assert got.startswith("你使用重擊攻擊野狗，") and breach is True


def test_breach_stays_when_the_skill_cannot_go(world):
    shabu, dog = fighter("Shabu"), mobile("野狗")
    shabu.cooldowns["smash"] = 4
    shabu.mv = 0.0

    def body():
        shabu.breach = True
        return say(shabu, "use smash"), shabu.breach, dict(shabu.queued)

    got, breach, queued = in_fight([(shabu, dog)], body)
    assert got.startswith("你的 MV 不夠。")
    assert breach is True and queued == {}


def test_breach_fires_the_first_queued_skill(world, monkeypatch):
    shabu, dog = fighter("Shabu"), mobile("野狗")
    shabu.skills.append("pummel")
    shabu.cooldowns.update(smash=4, pummel=4)

    def body():
        say(shabu, "use smash")
        say(shabu, "use pummel")
        monkeypatch.setattr(skill_queue, "rng", Always(0.0))
        shabu.fight.tick()
        return segment(shabu), list(shabu.queued), shabu.breach

    got, queued, breach = in_fight([(shabu, dog)], body)
    assert got[:2] == ["野狗露出了破綻！", "你抓住了破綻！"]
    assert got[2].startswith("你使用重擊攻擊野狗，") and got[-1] == "野狗" + condition(dog)
    assert queued == ["pummel"] and breach is False and shabu.cooldowns["smash"] == 6


def test_breach_stays_when_the_queued_skill_cannot_go(world, monkeypatch):
    shabu, dog = fighter("Shabu"), mobile("野狗")
    shabu.cooldowns["smash"] = 4

    def body():
        say(shabu, "use smash")
        shabu.mv = 0.0
        monkeypatch.setattr(skill_queue, "rng", Always(0.0))
        shabu.fight.tick()
        return segment(shabu), dict(shabu.queued), shabu.breach

    got, queued, breach = in_fight([(shabu, dog)], body)
    assert got == ["野狗露出了破綻！", "你的 MV 不夠。", "野狗" + condition(dog)]
    assert queued == {} and breach is True


def test_breach_skips_queued_skills_that_cannot_go(world, monkeypatch):
    shabu, dog, cat = fighter("Shabu"), mobile("野狗"), mobile("野貓")
    shabu.skills.append("pummel")
    shabu.cooldowns.update(smash=4, pummel=4)

    def body():
        say(shabu, "use smash cat")
        say(shabu, "use pummel")
        cat.room = zones.world.rooms[101]                           # 排最前面那個打名字的不在這裡了：不算
        monkeypatch.setattr(skill_queue, "rng", Always(0.0))
        shabu.fight.tick()
        return segment(shabu), dict(shabu.queued), shabu.breach

    got, queued, breach = in_fight([(shabu, dog)], body)
    assert got[:2] == ["野狗露出了破綻！", "你抓住了破綻！"] and got[2].startswith("你使用猛擊攻擊野狗")
    assert queued == {} and breach is False


def test_breach_works_for_buffs_too(world):
    shabu, dog = fighter("Shabu"), mobile("野狗")
    shabu.skills.append("berserk")
    shabu.cooldowns["berserk"] = 4

    def body():
        shabu.breach = True
        return say(shabu, "use berserk")

    got = in_fight([(shabu, dog)], body)
    assert got.startswith(f"你抓住了破綻！\r\n你對自己施展了【{BERSERK.name}】。")


# ---- 有餽贈時技能只扣一半 ----

def gift(p):
    affects.add(p, skills.make_affect(skills.SKILLS["gift"]))


@pytest.mark.parametrize("level", range(1, 101))
def test_gift_halves_the_cost(level):
    from test_skills import player
    p = player(level, stats.Race.HUMAN, stats.Guild.SWORD)
    full = [skills.cost(s, level) for s in (SMASH, skills.SKILLS["fireball"])]
    assert [skills.spend(p, s) for s in (SMASH, skills.SKILLS["fireball"])] == full
    gift(p)
    assert [skills.spend(p, s) for s in (SMASH, skills.SKILLS["fireball"])] == [max(1, (c + 1) // 2) for c in full]   # 四捨五入、最少 1


def test_gift_keeps_free_skills_free():
    from test_skills import player
    p = player(1, stats.Race.HUMAN, stats.Guild.SWORD)
    gift(p)
    assert skills.spend(p, skills.SKILLS["gift"]) == 0 and skills.spend(p, skills.SKILLS["thunder"]) == 0


def test_gift_pays_half_and_skills_shows_half(world):
    shabu, dog = fighter("Shabu", level=20), mobile("野狗")
    gift(shabu)
    mv, half = shabu.mv, skills.spend(shabu, SMASH)
    assert half < skills.cost(SMASH, 20)
    assert f"{half} MV" in say(shabu, "skills")
    in_fight([(shabu, dog)], lambda: say(shabu, "use smash"))
    assert shabu.mv == pytest.approx(mv - half)
