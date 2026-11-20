"""召喚類技能（設計文件 §2.6，summons.py）：叫出來、比主人低 10 級、同一個技能換掉舊的、自動打主人的對手、跟著走、
時間到／主人死掉／主人離線就消失、被打死不留屍體不給經驗、打死的怪算主人的、玩家打不了牠、打一群不打牠。

借用 test_skills.py 的區域：房間 102 有 5 級的野狗和野貓，101 在南邊（START_ROOM 是 101）。
"""
import asyncio

import pytest

from mud import combat, death, objects, reserved, resets, skills, stats, summons, zones
from mud.area import MobTier
from mud.characters import characters
from mud.commands import skills as skill_commands
from mud.npcs import Npc
from test_skills import fighter, mobile, prompt_of, say, text_of, world  # noqa: F401（world 是 fixture）

STAFF = stats.Guild.STAFF


def necromancer(name="Shabu", level=20, learn=("raise_skeleton", "death_knight")):
    p = fighter(name, level=level, guild=STAFF)
    p.skills += list(learn)
    return p


def reply(p, *lines):
    return "\r\n".join(lines) + f"\r\n\r\n{prompt_of(p)}"


def skeletons():
    return [c for c in characters if isinstance(c, Npc) and c.name == "骷髏"]


def test_raise_a_skeleton(world):
    p, ming = necromancer(), fighter("Ming")
    text_of(ming)
    assert say(p, "use raise") == reply(p, "地面裂開，一具骷髏喀啦喀啦地爬了出來。")
    assert "地面裂開，一具骷髏喀啦喀啦地爬了出來。" in text_of(ming)
    [bones] = skeletons()
    assert (bones.room, bones.level, bones.tier, bones.master, bones.summon_ticks) == (p.room, 10, MobTier.NORMAL, p, 120)
    panel, _mix = stats.mob_stats(10, "normal", None, None, None)
    assert bones.panel == panel and bones.hp == panel["hp"]
    assert "骷髏/skeleton/喀啦喀啦地站在主人身邊，眼窩裡沒有光。" in say(p, "look")


def test_death_knight_is_an_elite_and_levels_bottom_out_at_1(world):
    p = necromancer(level=5)
    say(p, "use death")
    knight = next(c for c in characters if isinstance(c, Npc) and c.name == "死亡騎士")
    assert (knight.level, knight.tier) == (1, MobTier.ELITE)


def test_the_same_skill_replaces_the_old_one(world):
    p = necromancer()
    say(p, "use raise")
    first = skeletons()[0]
    p.cooldowns = {}
    assert say(p, "use raise") == reply(p, "骷髏散成一堆白骨。", "地面裂開，一具骷髏喀啦喀啦地爬了出來。")
    assert len(skeletons()) == 1 and first not in characters
    say(p, "use death")                                               # 不同技能叫的可以同時在
    assert len(summons.of(p)) == 2


def test_it_fights_your_foe(world):
    p = necromancer()
    dog = mobile("野狗")
    say(p, "use raise")

    async def main():
        from mud import fight
        fight.start_fight(p, dog)
        summons.tick()
        return skeletons()[0].fighting, dog.fighting

    assert asyncio.run(main()) == (dog, p)                            # 狗還是打你（照原本的規則）


def test_it_follows_you(world):
    p = necromancer()
    say(p, "use raise")
    [bones] = skeletons()
    say(p, "s")
    assert bones.room is p.room is zones.world.rooms[101]
    p.room = zones.world.rooms[102]                                   # 被送走（recall、goto）：下一個 tick 跟過去
    summons.tick()
    assert bones.room is p.room


def test_it_goes_away(world):
    p, ming = necromancer(), fighter("Ming")
    say(p, "use raise")
    skeletons()[0].summon_ticks = 1
    text_of(ming)
    summons.tick()
    assert skeletons() == [] and "骷髏散成一堆白骨。" in text_of(ming)
    say(p, "use death")
    death.player_dies(p)                                              # 主人死掉
    assert summons.of(p) == []
    p.room = zones.world.rooms[102]
    p.cooldowns = {}
    say(p, "use raise")
    characters.remove(p)                                              # 主人離線
    summons.tick()
    assert skeletons() == []


def test_killed_summons_leave_nothing(world):
    p = necromancer()
    say(p, "use raise")
    [bones] = skeletons()
    dog = mobile("野狗")

    async def main():
        from mud import fight
        battle = fight.start_fight(dog, bones)
        combat.land(battle, dog, bones, 10.0 ** 9, False)

    asyncio.run(main())
    assert bones not in characters
    assert not any(o.item_type == objects.CORPSE_NPC_ITEM_TYPE for o in p.room.contents)


def test_its_kills_count_for_you(world):
    p = necromancer(level=6)                                          # 20 級打 5 級的狗沒有經驗
    say(p, "use raise")
    [bones] = skeletons()
    dog = mobile("野狗")
    exp = p.exp

    async def main():
        from mud import fight
        battle = fight.start_fight(bones, dog)
        combat.land(battle, bones, dog, 10.0 ** 9, False)
        battle.flush()

    asyncio.run(main())
    assert p.exp > exp and "你共獲得了" in text_of(p)
    assert any(o.item_type == objects.CORPSE_NPC_ITEM_TYPE for o in p.room.contents)


def test_players_cannot_hit_summons(world):
    p = necromancer(learn=("raise_skeleton", "blast"))
    say(p, "use raise")
    [bones] = skeletons()
    assert say(p, "kill skeleton") == reply(p, "你不可以攻擊召喚物。")
    assert say(p, "use fireball skeleton") == reply(p, "你不可以攻擊召喚物。")
    assert bones not in skills.enemies(p) and bones not in skills.allies(p)


def test_skills_listing_for_summons(world):
    p = necromancer()
    skill_commands.do_skills(p, "")
    text = text_of(p)
    assert "喚骨術 raise_skeleton  持續 120 秒" in text and "    叫出一隻骷髏（比你低 10 級）幫你打" in text
    assert "    叫出一隻死亡騎士（比你低 10 級）幫你打" in text


@pytest.mark.parametrize("skill", ["raise_skeleton", "death_knight"])
def test_summon_texts_fit_the_rules(world, skill):
    # 名字、英文名字、look 那一行、描述在系統區域檔（區域檔的檢查看 Big5、格式）；叫出來、消失的那句是技能的訊息，在程式裡
    shape, look = summons.proto(skill), summons.TYPES[skill]
    name, keyword, rest = shape["long"].rstrip("\n").split("/")
    assert (name, keyword) == (shape["short"], shape["keywords"].split()[0]) and rest.endswith("。")
    for text in (look["arrive"], look["gone"]):
        text.encode("cp950")                                          # Big5 打得出來
        assert len(text) <= 36                                        # 世界觀的寫作規則：一行不超過 36 個中文字


def test_summons_look_like_the_system_area(world, monkeypatch):
    """骷髏、死亡騎士長什麼樣子照系統區域檔的生物 1、2（reserved.py，使用者 2026-11-20 定的）：改區域檔就跟著變。"""
    p = necromancer()
    monkeypatch.setitem(resets.mobiles, reserved.SKELETON, dict(resets.mobiles[reserved.SKELETON], short="白骨兵", keywords="bones",
                                                                long="白骨兵/bones/站著。\n", description="一副白骨。\n"))
    npc = summons.summon(p, skills.SKILLS["raise_skeleton"])
    assert (npc.name, npc.keywords, npc.long, npc.description) == ("白骨兵", ["bones"], "白骨兵/bones/站著。\n", "一副白骨。\n")
    assert npc.level == p.level - skills.SKILLS["raise_skeleton"].summon["below"]   # 等級照技能算，不用區域檔寫的
