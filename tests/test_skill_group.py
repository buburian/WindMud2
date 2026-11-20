"""打一群、放在一群自己人上（設計文件 §2.6）：房間裡看得到的生物全部、每多一隻總量 +50% 再平分、還沒在打架的也開打、
燃燒和持續扣血也分、控制每隻各自擲命中而且完整、群體治療（自己和同房間的玩家）。

借用 test_skills.py 的區域：房間 102 有 5 級的野狗和野貓（純物理），101 在南邊。
"""
import re

import pytest

from mud import affects, combat, damage, skills, stats, zones
from mud.area import AffectFlag, RoomFlag
from mud.commands import skills as skill_commands
from test_skills import Always, fighter, in_fight, mobile, prompt_of, say, text_of, world  # noqa: F401（world 是 fixture）

STAFF = stats.Guild.STAFF


def mage(name="Shabu", learn=(), level=10, room=102):
    p = fighter(name, room=room, level=level, guild=STAFF)
    p.skills += list(learn)
    return p


def sturdy(*names):
    """這幾隻 HP 很多（技能打不死）。"""
    out = [mobile(n) for n in names]
    for m in out:
        m.hp = 10 ** 6
    return out


def reply(p, *lines):
    return "\r\n".join(lines) + f"\r\n\r\n{prompt_of(p)}"


def test_share():
    assert [skills.share(n) for n in (1, 2, 3, 4)] == [1.0, 0.75, pytest.approx(2 / 3), 0.625]
    assert skills.share(100) > 0.5                                  # 再多也不會低於一半


def test_blast_hits_every_mobile_and_splits(world):
    p = mage(learn=["blast"])
    dog, cat = sturdy("野狗", "野貓")
    got, fighting = in_fight([], lambda: (say(p, "use blast"), (p.fighting, dog.fighting, cat.fighting)))
    for m in (dog, cat):
        dmg = damage.per_hit(p, m, "spell") * 2.3 * 0.75            # 2 隻：每隻 75%
        assert 10 ** 6 - m.hp == pytest.approx(dmg)
    assert got.count("你使用爆炎攻擊") == 2
    assert fighting == (dog, p, p)                                   # 還沒在打架的也開打：你打第一隻，每隻都打你


def test_one_mobile_takes_it_all(world):
    p = mage(learn=["blast"])
    dog, cat = sturdy("野狗", "野貓")
    cat.room = zones.world.rooms[101]
    in_fight([], lambda: say(p, "use blast"))
    assert 10 ** 6 - dog.hp == pytest.approx(damage.per_hit(p, dog, "spell") * 2.3)


def test_unseen_mobiles_are_not_hit(world):
    p = mage(learn=["blast"])
    dog, cat = sturdy("野狗", "野貓")
    cat.affected_by |= AffectFlag.INVISIBLE
    in_fight([], lambda: say(p, "use blast"))
    assert cat.hp == 10 ** 6 and 10 ** 6 - dog.hp == pytest.approx(damage.per_hit(p, dog, "spell") * 2.3)


def test_nobody_to_hit_or_a_safe_room(world):
    p = mage(learn=["blast"], room=101)
    mp = p.mp
    assert say(p, "use blast") == reply(p, "這裡沒有可以攻擊的對象。")
    q = mage("Ming", learn=["blast"])
    q.room.room_flags |= RoomFlag.SAFE
    assert say(q, "use blast") == reply(q, "野狗正在受到神力所保護的房間內。")
    assert (p.mp, q.mp, q.fighting) == (mp, q.panel["mp"], None)


def test_burns_are_split_too(world):
    p = mage(learn=["flame_wave"])
    dog, cat = sturdy("野狗", "野貓")
    in_fight([], lambda: say(p, "use flame dog"))                    # 名字打了也不管
    for m in (dog, cat):
        hit = damage.per_hit(p, m, "spell") * 1.4 * 0.75
        assert hit * 0.3 > 1
        burn = next(a for a in m.affects if a.source == "flame_wave")
        assert (burn.tag, burn.periodic) == ("燃燒", {"hp": pytest.approx(-max(1, hit * 0.3))})


def test_group_dots_are_split(world):
    p = mage(learn=["embers"])
    dog, cat = sturdy("野狗", "野貓")
    got = in_fight([], lambda: say(p, "use embers"))
    assert "你對野狗施展了【餘燼】。" in got and "你對野貓施展了【餘燼】。" in got
    for m in (dog, cat):
        each = damage.per_hit(p, m, "spell") * 0.6 * 0.75
        assert each > 1                                              # 比最低 1 點大，才看得出有沒有分
        assert next(a for a in m.affects if a.source == "embers").periodic == {"hp": pytest.approx(-max(1, each))}


def test_group_controls_are_whole_and_roll_each(world, monkeypatch):
    p = mage(learn=["frost_ring", "blizzard"])
    dog, cat = sturdy("野狗", "野貓")
    got = in_fight([], lambda: say(p, "use frost"))
    assert "野狗被凍住了！" in got and "野貓被凍住了！" in got
    assert [a.duration for m in (dog, cat) for a in m.affects] == [4, 4]
    monkeypatch.setattr(combat, "rng", Always(0.99))
    p.cooldowns = {}
    got = in_fight([], lambda: say(p, "use blizzard"))
    assert got.count("但是失手了") == 2


def test_smoke_bomb_blinds(world):
    p = fighter("Shabu")
    p.skills.append("smoke_bomb")
    dog, cat = sturdy("野狗", "野貓")
    chance = damage.hit_chance(dog, p)
    got = in_fight([], lambda: say(p, "use smoke"))
    assert "野狗什麼都看不見了！" in got and "野貓什麼都看不見了！" in got
    assert damage.hit_chance(dog, p) == pytest.approx(chance * 0.5)


def test_mass_heal_heals_every_player_and_splits(world):
    p, ming = mage(learn=["mass_heal"]), mage("Ming")
    p.hp = ming.hp = 1
    text_of(ming)
    each = stats.shown(p.panel["dmg_spell"] * 3.95 * 0.75)
    mine = say(p, "use mass")
    assert mine == reply(p, "你施展了【群體治療】。", f"你恢復了 {each} 點 HP。", f"Ming恢復了 {each} 點 HP。")
    assert text_of(ming) == f"\r\nShabu施展了【群體治療】。\r\n你恢復了 {each} 點 HP。\r\n\r\n{prompt_of(ming)}"
    assert mobile("野狗").fighting is None and p.fighting is None    # 不開打


def test_wellspring_heals_over_time_for_everyone(world):
    p, ming = mage(learn=["wellspring"]), mage("Ming")
    say(p, "use well")
    each = p.panel["dmg_spell"] * 0.1 * 0.75
    for c in (p, ming):
        assert next(a for a in c.affects if a.source == "wellspring").periodic == {"hp": pytest.approx(each)}
    assert mobile("野狗").affects == []


def test_whirlwind_needs_a_two_handed_weapon(world):
    p = fighter("Shabu")
    p.skills.append("whirlwind")
    assert say(p, "use whirl") == reply(p, "你手上的武器不能用旋風斬。")


def test_listing_says_who_it_hits(world):
    p = mage(learn=["blast", "frost_ring", "mass_heal"])
    skill_commands.do_skills(p, "")
    text = text_of(p)
    assert re.search(r"爆炎 blast +傷害 .*\r\n +打房間裡全部的怪（每多一隻總量 \+50%，再平分）", text)
    assert re.search(r"\r\n +凍住、打房間裡全部的怪\r\n", text)
    assert re.search(r"\r\n +自己和同房間的玩家（每多一隻總量 \+50%，再平分）", text)


def test_group_effects_tagged(world):
    p = mage(learn=["embers"])
    dog, _cat = sturdy("野狗", "野貓")
    in_fight([], lambda: say(p, "use embers"))
    assert affects.has_tag(dog, "燃燒")
