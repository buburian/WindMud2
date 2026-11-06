"""技能：資料、消耗、說明的數字跟 balance.py 比對；smash／fireball 指令的檢查、訊息、冷卻、扣 MV／MP、打死生物；skills 指令。

要一下一下看的：把 fight.TICK_SECONDS 改很大（loop 不會自己跑），在 asyncio 裡開打、打指令（asyncio.run 結束時戰鬥會被收掉，
所以開打和指令要在同一個 asyncio.run 裡）。亂數換成 Always：0.5 是打中、不浮動、不爆擊；0.0 是打中、浮動最低、爆擊。
"""
import asyncio
import dataclasses
import random
import re
from pathlib import Path

import pytest

import mud.commands as commands
from area_helpers import make_area, make_mobile, make_room, write_json
from balance_loader import load_balance
from player_helpers import make_player_file
from mud import affects, combat, damage, death, fight, save, skills, stats, zones
from mud.area import CORPSE_NPC_ITEM_TYPE, MobTier, WeaponKind
from mud.characters import Position, characters
from mud.commands import skills as skill_commands
from mud.color import colorize
from mud.config import ENCODING
from mud.npcs import Npc
from mud.players import Player

SMASH, FIREBALL = skills.SKILLS["smash"], skills.SKILLS["fireball"]
AREAS = Path(__file__).resolve().parent.parent / "areas"


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


class Always:
    """假的亂數：random() 一律回傳 x。"""

    def __init__(self, x):
        self.x = x

    def random(self):
        return self.x


class Counting:
    """數 random() 被叫了幾次的亂數。"""

    def __init__(self):
        self.calls = 0

    def random(self):
        self.calls += 1
        return 0.5


# ---- 跟 balance.py 比對 ----

@pytest.fixture(scope="module")
def balance():
    module = load_balance()
    if module is None:
        pytest.skip("找不到 mud_design/sim/balance.py")
    return module


@pytest.fixture(scope="module")
def model(balance):
    return balance.Model()


def player(level, race, guild):
    p = Player("玩家", None, None)
    p.race, p.guild, p.level = race, guild, level
    p.primaries = dict(stats.RACE_PRIMARIES[race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.skills = skills.starter(guild)            # 跟建立角色一樣：公會一開始就會的
    stats.recompute(p)
    return p


def mob(level, tier="normal", attack=None, defense=None, archetype=None):
    n = Npc("怪物", 0, None)
    n.level, n.tier = level, MobTier(tier)
    n.panel, n.mix = stats.mob_stats(level, tier, attack, defense, archetype)
    return n


def entity(balance, model, ch):
    """我們的角色 → balance.py 的 Entity（同樣的屬性、等級、攻擊類型）。"""
    dtype = str(ch.guild) if isinstance(ch, Player) else "phys"
    mix = dict(ch.mix) if isinstance(ch, Npc) else None
    return balance.Entity("x", ch.level, model.G(ch.level), dtype, dict(ch.panel), mix)


def players():
    return [player(level, race, guild) for level in (1, 10, 50, 100)
            for race in (stats.Race.HUMAN, stats.Race.ELF, stats.Race.ORC) for guild in stats.Guild]


def own_skill(p):
    return SMASH if p.guild == stats.Guild.SWORD else FIREBALL


def test_skills_match_mud_design(balance):
    # 傷害技能照 balance.py；imm 的技能、增益技能（餽贈）是我們自己加的（balance.py 沒有）
    assert {s["id"] for s in balance.SKILLS.values()} == {s.id for s in skills.SKILLS.values()
                                                         if s.kind == "damage" and not s.imm_only}
    for name, want in balance.SKILLS.items():
        s = skills.SKILLS[want["id"]]
        assert s.name == name
        assert str(s.guild) == want["guild"]
        assert (s.kind, s.target, s.hits, s.ratio, s.cost) == (want["kind"], want["target"], want["hits"], want["ratio"], want["cost"])
        assert s.cooldown == want["cooldown"]
        assert tuple(s.weapon_kinds) == tuple(want["weapon_kinds"])


def test_cost_matches_mud_design(balance, model):
    for name, want in balance.SKILLS.items():
        s = skills.SKILLS[want["id"]]
        for level in range(1, stats.MAX_LEVEL + 1):
            assert skills.cost(s, level) == model.skill_cost(name, level), (name, level)


@pytest.mark.parametrize("skill", [SMASH, FIREBALL])
def test_cost_matches_the_manual(skill):
    # 玩家角色手冊：1 級 4、10 級 6、30 級 15、50 級 37、80 級 152、100 級 387（兩個公會一樣）
    assert [skills.cost(skill, level) for level in (1, 10, 30, 50, 80, 100)] == [4, 6, 15, 37, 152, 387]


def test_display_range_matches_mud_design(balance, model):
    # 武器做好前：浮動 ±dmg_var 當成主手武器的下限、上限帶進 skill_display_range
    for p in players():
        s, e = own_skill(p), entity(balance, model, p)
        var = model.cfg.dmg_var
        assert skills.display_range(p, s) == model.skill_display_range(e, s.name, -e.dmg * var, e.dmg * var)


@pytest.mark.parametrize("seed", range(3))
def test_skill_hit_matches_mud_design(balance, model, seed):
    # 技能的一下 ＝ 主手這一下平砍 × ratio（simulate_group 的 skill_hand），同一個種子每一下都一樣
    for a in players()[::5]:
        for d in (mob(a.level), mob(a.level, "elite", "dragon/phys", "phys", "tank")):
            s = own_skill(a)
            p = model._combat_params(entity(balance, model, a), entity(balance, model, d))
            hand = dict(p["hands"][0])
            hand["per_hit"] *= s.ratio
            hand["per_hit_t"] = {t: v * s.ratio for t, v in hand["per_hit_t"].items()}
            ours, theirs = random.Random(seed), random.Random(seed)
            for _ in range(200):
                dmg, _crit = damage.strike(a, d, ours, skills.damage_kind(s, a))
                want = model._strike_once(p, hand, theirs.random, model.cfg.dmg_var, False)
                # 1e-9：100 級的平砍本身就跟 balance.py 差 1e-12 左右（G(L) 這些小數的誤差，等級越高越大）
                assert dmg * s.ratio == pytest.approx(want, rel=1e-9)


def test_strike_with_a_kind_does_not_roll_the_type():
    # 混合型的生物平砍會先骰類型；指定了類型（技能）就不骰，少叫一次亂數
    a, d = mob(10, "normal", "dragon/phys"), player(10, stats.Race.HUMAN, stats.Guild.SWORD)
    plain, fixed = Counting(), Counting()
    damage.strike(a, d, plain)
    dmg, _crit = damage.strike(a, d, fixed, "phys")
    assert (plain.calls, fixed.calls) == (4, 3)
    assert dmg == pytest.approx(damage.per_hit(a, d, "phys"))


# ---- 指令 ----

@pytest.fixture
def world(tmp_path, monkeypatch):
    """世界：房間 101、102 南北相連，102 有 5 級的野狗和野貓（純物理）。"""
    monkeypatch.setattr(fight, "TICK_SECONDS", 1000)       # loop 不會自己跑
    monkeypatch.setattr(combat, "rng", Always(0.5))
    mobiles = []
    for vnum, short, keywords in ((1, "野狗", "dog 野狗"), (2, "野貓", "cat 野貓")):
        m = make_mobile(vnum)
        m.update(short=short, keywords=keywords, level=5, tier="normal", tier_roll=None, attack=None, defense=None,
                 archetype=None, act=0, position=7, sex=0, long="", drops=[])
        mobiles.append(m)
    rooms = [make_room(1, north=2), make_room(2, south=1)]
    resets = [{"cmd": "M", "rare": 0, "mob_vnum": v, "limit": 1, "room_vnum": 2, "comment": ""} for v in (1, 2)]
    write_json(tmp_path, "a.json", make_area("a.json", rooms, 100, mobiles=mobiles, resets=resets))
    zones.load(tmp_path)
    yield tmp_path
    characters.clear()
    zones.stop()


def mobile(name):
    return next(c for c in characters if isinstance(c, Npc) and c.name == name)


def fighter(name, room=102, level=1, guild=stats.Guild.SWORD):
    """在線上、有屬性的人類玩家。"""
    p = Player(name, FakeWriter(), zones.world.rooms[room])
    p.race, p.guild = stats.Race.HUMAN, guild
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.skills = skills.starter(guild)            # 跟建立角色一樣：公會一開始就會的
    stats.set_level(p, level)
    characters.append(p)
    return p


def raw(p):
    text = p.writer.data.decode(ENCODING)
    p.writer.data = b""
    return text


def text_of(p):
    return re.sub(r"\x1b\[[0-9;]*m", "", raw(p))


def prompt_of(p):
    return re.sub(r"\x1b\[[0-9;]*m", "", p.prompt())


def in_fight(starts, body):
    """在 asyncio 裡開打（starts 是 [(打的人, 被打的人)]），再跑 body()，回傳它的結果。"""
    async def main():
        for ch, victim in starts:
            fight.start_fight(ch, victim)
        return body()

    return asyncio.run(main())


def say(p, line):
    """p 打一行指令，回傳 p 看到的（沒有顏色）。"""
    raw(p)
    commands.command(p, line)
    return text_of(p)


def test_use_and_abbreviations():
    assert commands.find("us") is skill_commands.do_use
    assert commands.find("u") is commands.find("up") and commands.find("un") is commands.find("unlock")   # 原本的縮寫不變
    assert commands.find("sk") is skill_commands.do_skills
    assert commands.lookup("use")[1] == Position.FIGHTING
    assert commands.lookup("skills")[1] == Position.DEAD
    for name in ("smash", "fireball", "thunder"):           # 技能不是指令，只能用 use
        assert commands.command_name(name, True) is None


@pytest.mark.parametrize("line", ["use smash dog", "use sm dog", "use s dog", "us sm dog", "use SMASH DOG", "use smash do", "use smash 野"])
def test_skill_and_target_names_can_be_shortened(world, line):
    shabu = fighter("Shabu")
    assert in_fight([], lambda: say(shabu, line)).startswith("你使用重擊攻擊野狗，")


def test_only_your_own_guilds_skills(world):
    shabu, ming = fighter("Shabu"), fighter("Ming", guild=stats.Guild.STAFF)
    got = in_fight([], lambda: (say(shabu, "use fireball dog"), say(ming, "use smash dog")))
    assert got == (f"你不會這個技能。\r\n\r\n{prompt_of(shabu)}", f"你不會這個技能。\r\n\r\n{prompt_of(ming)}")
    assert skills.known(shabu) == [SMASH] and skills.known(ming) == [FIREBALL]
    assert skills.known(mobile("野狗")) == [] and skills.known(Player("Bare", None, None)) == []    # 生物、沒有屬性的角色
    assert skills.find(shabu, "f") is None and skills.find(ming, "f") is FIREBALL                    # 只找自己會的


def test_npcs_do_not_know_skills(world):
    dog = mobile("野狗")
    sent = []
    dog.send = sent.append
    commands.command(dog, "use smash shabu")
    assert sent[0] == "你不會這個技能。\n"


@pytest.mark.parametrize("line, want", [
    ("use", "你想要用什麼技能？"),
    ("use smash", "你想要攻擊誰？"),                          # 沒在打架又沒打名字
    ("use smash bird", "找不到你想攻擊的人。"),
    ("use smash 2.dog", "找不到你想攻擊的人。"),               # 只有一隻狗
    ("use smash 0.dog", "找不到你想攻擊的人。"),
    ("use smash ming", "你不可以攻擊玩家。"),
    ("use smash shabu", "你不可以攻擊玩家。"),                 # 自己
    ("use thunder dog", "你不會這個技能。"),                   # imm 的技能
    ("use xyz dog", "你不會這個技能。"),
])
def test_use_mistakes_do_not_start_a_fight(world, line, want):
    shabu = fighter("Shabu")
    fighter("Ming")
    dog = mobile("野狗")
    mv = shabu.mv
    got, fighting, its = in_fight([], lambda: (say(shabu, line), shabu.fighting, dog.fighting))
    assert got == f"{want}\r\n\r\n{prompt_of(shabu)}"
    assert (fighting, its, shabu.mv, shabu.cooldowns) == (None, None, mv, {})


@pytest.mark.parametrize("position", [Position.RESTING, Position.SLEEPING])
def test_cannot_use_skills_while_resting_or_sleeping(world, position):
    shabu = fighter("Shabu")
    shabu.position = position
    mv = shabu.mv
    fighting = in_fight([], lambda: (say(shabu, "use smash dog"), shabu.fighting)[1])
    assert (fighting, shabu.mv, shabu.cooldowns) == (None, mv, {})


def test_use_starts_a_fight(world):
    # 沒在打架：跟 kill 一樣開打，技能那一下馬上打出去，生物自動還手
    shabu = fighter("Shabu")
    dog = mobile("野狗")

    def body():
        return say(shabu, "use smash dog"), shabu.fighting, dog.fighting, shabu.fight is dog.fight is not None

    got, mine, its, same = in_fight([], body)
    assert got.startswith("你使用重擊攻擊野狗，")
    assert (mine, its, same) == (dog, shabu, True)
    assert dog.hp == pytest.approx(dog.panel["hp"] - damage.per_hit(shabu, dog, "phys") * SMASH.ratio)


@pytest.mark.parametrize("mv, cooldown, want", [(0.0, None, "你的 MV 不夠。"), (40.0, 3, "你還要等 3 秒才能再用重擊。")])
def test_failed_checks_do_not_start_a_fight(world, mv, cooldown, want):
    shabu = fighter("Shabu")
    dog = mobile("野狗")
    shabu.mv = mv
    if cooldown:
        shabu.cooldowns["smash"] = cooldown
    got, mine, its = in_fight([], lambda: (say(shabu, "use smash dog"), shabu.fighting, dog.fighting))
    assert got.startswith(want) and (mine, its) == (None, None)


def test_use_pulls_in_a_bystander(world):
    # 打野狗時對旁邊的野貓用技能：野貓加進同一場打你，你平砍還是打野狗（使用者選的，照 C 版）
    shabu = fighter("Shabu")
    dog, cat = mobile("野狗"), mobile("野貓")

    def body():
        return say(shabu, "use smash cat"), shabu.fighting, cat.fighting, cat.fight is shabu.fight

    got, mine, its, same = in_fight([(shabu, dog)], body)
    assert got.startswith("你使用重擊攻擊野貓，")
    assert (mine, its, same) == (dog, shabu, True)


def test_use_on_a_mobile_in_someone_elses_fight(world):
    shabu, ming = fighter("Shabu"), fighter("Ming")
    dog, cat = mobile("野狗"), mobile("野貓")

    def join():                                             # Shabu 沒在打架：加進 Ming 和野狗那一場，野狗還是打 Ming
        return say(shabu, "use smash dog"), shabu.fighting, dog.fighting, shabu.fight is ming.fight

    got, mine, its, same = in_fight([(ming, dog)], join)
    assert got.startswith("你使用重擊攻擊野狗，") and (mine, its, same) == (dog, ming, True)

    def hit():                                              # Shabu 在打野貓：野狗在打 Ming，直接打，不改誰打誰
        return say(shabu, "use smash dog"), shabu.fighting, dog.fighting

    shabu.cooldowns.clear()
    got, mine, its = in_fight([(ming, dog), (shabu, cat)], hit)
    assert got.startswith("你使用重擊攻擊野狗，") and (mine, its) == (cat, ming)


def test_use_the_nth_one(world):
    # 野狗、野貓都用「野」開頭：2.野 是畫面上第 2 隻（野貓）
    shabu = fighter("Shabu")
    assert in_fight([], lambda: say(shabu, "use smash 2.野")).startswith("你使用重擊攻擊野貓，")


def test_opponent_who_walked_away(world):
    # 對手被直接搬到隔壁（flee 會馬上停手，這裡不是），下一回合才會停手。這中間用技能，現在的對手也不在這間房了
    shabu = fighter("Shabu")
    dog = mobile("野狗")

    def body():
        dog.room = zones.world.rooms[101]
        return say(shabu, "use smash"), say(shabu, "use smash dog")

    assert in_fight([(shabu, dog)], body) == (f"找不到你想攻擊的人。\r\n\r\n{prompt_of(shabu)}",) * 2
    assert dog.hp == dog.panel["hp"]


def test_smash_messages_and_one_prompt(world):
    shabu, ming = fighter("Shabu"), fighter("Ming")         # Ming 站在旁邊看
    dog = mobile("野狗")

    def body():
        raw(ming)
        return say(shabu, "use smash"), text_of(ming)

    mine, seen = in_fight([(shabu, dog)], body)
    dmg = damage.per_hit(shabu, dog, "phys") * SMASH.ratio
    words, _code = combat.severity(dmg, dog.panel["hp"])
    n = stats.shown(dmg)
    tail = f"{'.' if n <= 10 else '!'}({n})"
    assert mine == f"你使用重擊攻擊野狗，對它造成{words}{tail}\r\n\r\n{prompt_of(shabu)}"     # 只有一個 prompt
    assert seen == f"\r\nShabu使用重擊攻擊野狗，對它造成{words}{tail}\r\n\r\n{prompt_of(ming)}"
    assert dog.hp == pytest.approx(dog.panel["hp"] - dmg)


def test_fireball_is_a_spell_and_costs_mp(world):
    ming = fighter("Ming", guild=stats.Guild.STAFF)
    dog = mobile("野狗")
    mp, mv = ming.mp, ming.mv
    got = in_fight([(ming, dog)], lambda: say(ming, "use fireball"))
    assert got.startswith("你使用火球攻擊野狗，")
    assert dog.hp == pytest.approx(dog.panel["hp"] - damage.per_hit(ming, dog, "spell") * FIREBALL.ratio)
    assert (ming.mp, ming.mv) == (pytest.approx(mp - skills.cost(FIREBALL, 1)), mv)


def test_crit_message(world, monkeypatch):
    shabu = fighter("Shabu")
    monkeypatch.setattr(combat, "rng", Always(0.0))
    got = in_fight([(shabu, mobile("野狗"))], lambda: say(shabu, "use smash"))
    assert got.startswith("你使用重擊攻擊野狗，爆擊！對它造成")


def test_cost_and_cooldown(world):
    shabu = fighter("Shabu")
    dog = mobile("野狗")
    mv = shabu.mv

    def body():
        first = say(shabu, "use smash")
        again = say(shabu, "use smash")
        for _ in range(5):
            zones.world.tick()
        waiting = say(shabu, "us sm")
        zones.world.tick()
        return first, again, waiting, say(shabu, "us sm")

    first, again, waiting, ready = in_fight([(shabu, dog)], body)
    assert first.startswith("你使用重擊攻擊野狗，")
    assert again.startswith("你還要等 6 秒才能再用重擊。")
    assert waiting.startswith("你還要等 1 秒才能再用重擊。")
    assert ready.startswith("你使用重擊攻擊野狗，")                 # 6 個 tick 後又能用
    assert shabu.mv == pytest.approx(mv - 2 * skills.cost(SMASH, 1))
    assert shabu.cooldowns == {"smash": 6}


@pytest.mark.parametrize("mv, ok", [(3.6, True), (3.5, True), (3.4, False)])
def test_enough_mv_is_what_the_prompt_shows(world, mv, ok):
    # 使用者選的：MV 四捨五入後（prompt 顯示的）≥ 消耗就能用，扣完最少是 0
    shabu = fighter("Shabu")
    shabu.mv = mv
    got = in_fight([(shabu, mobile("野狗"))], lambda: say(shabu, "use smash"))
    if ok:
        assert got.startswith("你使用重擊攻擊野狗，")
        assert shabu.mv == 0.0
    else:
        assert got == f"你的 MV 不夠。\r\n\r\n{prompt_of(shabu)}"
        assert (shabu.mv, shabu.cooldowns) == (mv, {})


def test_not_enough_mp(world):
    ming = fighter("Ming", guild=stats.Guild.STAFF)
    ming.mp = 1.0
    assert in_fight([(ming, mobile("野狗"))], lambda: say(ming, "use fireball")).startswith("你的 MP 不夠。")


def test_weapon_kinds(world, monkeypatch):
    # 武器還沒做：手上沒有武器，有限用武器的技能都不能用
    monkeypatch.setitem(skills.SKILLS, "smash", dataclasses.replace(SMASH, weapon_kinds=(WeaponKind.DAGGER,)))
    shabu = fighter("Shabu")
    mv = shabu.mv
    got = in_fight([(shabu, mobile("野狗"))], lambda: say(shabu, "use smash"))
    assert got == f"你手上的武器不能用重擊。\r\n\r\n{prompt_of(shabu)}"
    assert (shabu.mv, shabu.cooldowns) == (mv, {})


def test_several_hits(world, monkeypatch):
    triple = dataclasses.replace(SMASH, hits=3)
    monkeypatch.setitem(skills.SKILLS, "smash", triple)
    shabu = fighter("Shabu", level=3)
    dog = mobile("野狗")
    got = in_fight([(shabu, dog)], lambda: say(shabu, "use smash"))
    assert got.count("你使用重擊攻擊野狗，") == 3
    assert dog.hp == pytest.approx(dog.panel["hp"] - 3 * damage.per_hit(shabu, dog, "phys") * triple.ratio)


def test_killing_with_a_skill(world, monkeypatch):
    # 第一下就打死：剩下的不打；死亡訊息、經驗值跟那一下在同一段；地上有屍體
    monkeypatch.setitem(skills.SKILLS, "smash", dataclasses.replace(SMASH, hits=3, ratio=1000.0))
    shabu, ming = fighter("Shabu"), fighter("Ming")
    dog = mobile("野狗")

    def body():
        raw(ming)
        mine = say(shabu, "use smash dog")                  # 沒在打架就開打，一下就打死
        return mine, text_of(ming), shabu.fighting          # asyncio.run 結束時戰鬥會被收掉，要在裡面看

    mine, seen, fighting = in_fight([], body)
    assert mine.count("你使用重擊攻擊野狗，") == 1
    assert "野狗已經斷氣，倒在地上死亡了!!" in mine and "點的經驗點數。" in mine
    assert seen.count(prompt_of(ming)) == 1 and "野狗已經斷氣" in seen
    assert dog not in characters and fighting is None and shabu.exp > 0
    corpse = zones.world.rooms[102].contents[0]
    assert corpse.item_type == CORPSE_NPC_ITEM_TYPE


def test_skills_listing(world):
    shabu, ming = fighter("Shabu"), fighter("Ming", guild=stats.Guild.STAFF)
    low, high = skills.display_range(shabu, SMASH)
    assert say(shabu, "skills") == f"你會的技能：\r\n  重擊 smash  傷害 {low}~{high}  消耗 4 MV  冷卻 6 秒\r\n\r\n{prompt_of(shabu)}"
    low, high = skills.display_range(ming, FIREBALL)
    assert say(ming, "sk").startswith(f"你會的技能：\r\n  火球 fireball  傷害 {low}~{high}  消耗 4 MP  冷卻 6 秒\r\n")
    shabu.cooldowns["smash"] = 3
    shabu.position = Position.SLEEPING                     # 睡著也能看
    assert "冷卻 6 秒  還要等 3 秒\r\n" in say(shabu, "skills")
    bare = Player("Bare", FakeWriter(), zones.world.rooms[101])
    assert say(bare, "skills").startswith("你還不會任何技能。")


def test_display_range_has_the_damage_variance():
    # 武器做好前：傷害點數 × ratio × (1 ∓ 20%)，跟 strike() 實際打出的範圍一樣
    p = player(1, stats.Race.HUMAN, stats.Guild.SWORD)
    points = p.panel["dmg_phys"] * SMASH.ratio
    assert skills.display_range(p, SMASH) == (stats.shown(points * 0.8), stats.shown(points * 1.2))


# ---- imm 的技能、imm 用技能 ----

THUNDER = skills.SKILLS["thunder"]


def imm_fighter(name, guild=stats.Guild.SWORD):
    p = fighter(name, guild=guild)
    p.imm = True
    return p


def test_thunder_is_only_for_imm():
    assert THUNDER.imm_only and THUNDER.guild is None and skills.resource(THUNDER) is None and skills.cost(THUNDER, 50) == 0
    shabu = player(5, stats.Race.HUMAN, stats.Guild.SWORD)
    assert skills.find(shabu, "th") is None                 # 不是 imm：use th 是「你不會這個技能。」
    shabu.imm = True
    assert skills.find(shabu, "th") is THUNDER and skills.find(shabu, "t") is THUNDER


def test_who_knows_imm_skills():
    sword, staff = player(5, stats.Race.HUMAN, stats.Guild.SWORD), player(5, stats.Race.HUMAN, stats.Guild.STAFF)
    assert skills.known(sword) == [SMASH] and skills.known(staff) == [FIREBALL]
    sword.imm = staff.imm = True
    assert skills.known(sword) == [SMASH, THUNDER]
    assert skills.known(staff) == [FIREBALL, THUNDER]


@pytest.mark.parametrize("guild, line, pool", [(stats.Guild.SWORD, "use smash", "mv"), (stats.Guild.STAFF, "use fireball", "mp")])
def test_imm_pays_nothing_and_never_waits(world, guild, line, pool):
    me = imm_fighter("Shabu", guild=guild)
    setattr(me, pool, 0.0)
    dog = mobile("野狗")
    first, again = in_fight([(me, dog)], lambda: (say(me, line), say(me, line)))
    assert first.startswith("你使用") and again.startswith("你使用")         # 連打兩次、資源 0 也能用
    assert (getattr(me, pool), me.cooldowns) == (0.0, {})


@pytest.mark.parametrize("guild, kind", [(stats.Guild.SWORD, "phys"), (stats.Guild.STAFF, "spell")])
def test_thunder_hits_with_your_guilds_damage(world, guild, kind):
    me = imm_fighter("Shabu", guild=guild)
    dog = mobile("野狗")
    got = in_fight([(me, dog)], lambda: say(me, "use th"))
    assert got.startswith("你使用天雷攻擊野狗，")
    assert dog.hp == pytest.approx(dog.panel["hp"] - damage.per_hit(me, dog, kind) * THUNDER.ratio)


def test_skills_listing_for_imm(world):
    shabu = imm_fighter("Shabu")
    low, high = skills.display_range(shabu, SMASH)
    t_low, t_high = skills.display_range(shabu, THUNDER)
    assert say(shabu, "skills") == ("你會的技能（imm 用技能不扣消耗、不用等冷卻）：\r\n"
                                    f"  重擊 smash  傷害 {low}~{high}  消耗 4 MV  冷卻 6 秒\r\n"
                                    f"  天雷 thunder  傷害 {t_low}~{t_high}  消耗 0  冷卻 0 秒\r\n\r\n{prompt_of(shabu)}")


# ---- 誰會：一開始就會、要用程式加（使用者定的） ----

def test_starter_skills():
    assert skills.starter(stats.Guild.SWORD) == ["smash"] and skills.starter(stats.Guild.STAFF) == ["fireball"]
    assert THUNDER.starter == () and THUNDER.imm_only


def test_known_is_the_list():
    p = player(5, stats.Race.HUMAN, stats.Guild.SWORD)
    p.skills = []
    assert skills.known(p) == []                                      # 劍之公會也不是自動會重擊：看清單
    assert skills.learn(p, FIREBALL) and skills.learn(p, SMASH)
    assert skills.known(p) == [SMASH, FIREBALL] and p.skills == ["fireball", "smash"]   # known 照 SKILLS 的順序
    assert not skills.learn(p, SMASH)                                 # 已經會
    assert skills.forget(p, FIREBALL) and not skills.forget(p, FIREBALL)
    p.skills.append("gone")                                           # SKILLS 已經拿掉的技能：不算
    assert skills.known(p) == [SMASH]


def test_imm_only_cannot_be_learned():
    p = player(5, stats.Race.HUMAN, stats.Guild.SWORD)
    assert not skills.learn(p, THUNDER) and "thunder" not in p.skills
    p.skills.append("thunder")                                        # 就算清單裡有，不是 imm 也不會
    assert THUNDER not in skills.known(p)
    p.imm = True
    p.skills.remove("thunder")
    assert THUNDER in skills.known(p)                                 # imm 自動會


def test_another_guilds_skill_keeps_its_own_guild():
    # 劍之公會學了火球：照樣打法術、照杖之公會的標準扣 MP（使用者：先這樣，做怎麼學技能時再看）
    p = player(5, stats.Race.HUMAN, stats.Guild.SWORD)
    skills.learn(p, FIREBALL)
    assert (skills.damage_kind(FIREBALL, p), skills.resource(FIREBALL)) == ("spell", "mp")
    assert skills.cost(FIREBALL, 5) == max(1, stats.shown(stats.resource_standard(5, stats.Guild.STAFF, "mp") * FIREBALL.cost))


def test_skills_are_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path)
    zones.load(AREAS)
    try:
        p = make_player_file("Ming")
        assert p.skills == ["smash"]                                  # 跟建立角色一樣：劍之公會一開始就會重擊
        p.skills = ["fireball", "smash"]
        save.save_player(p)
        assert save.player_from(save.load_data("Ming"), FakeWriter()).skills == ["fireball", "smash"]
        data = save.load_data("Ming")
        del data["skills"]                                            # 舊存檔：補上公會一開始就會的
        assert save.player_from(data, FakeWriter()).skills == ["smash"]
    finally:
        characters.clear()
        zones.stop()


# ---- imm 的 sset ----

@pytest.mark.parametrize("line, want", [
    ("sset", "用法：sset <名字> <技能> [off]"),
    ("sset ming", "用法：sset <名字> <技能> [off]"),
    ("sset ming smash xyz", "用法：sset <名字> <技能> [off]"),
    ("sset zzz smash", "沒有找到這個玩家。"),
    ("sset ming zzz", "沒有這個技能。"),
    ("sset ming th", "天雷只有 imm 會，不能給別人。"),
    ("sset ming smash", "Ming 已經會重擊了。"),
    ("sset ming fire off", "Ming 本來就不會火球。"),
])
def test_sset_mistakes(world, line, want):
    shabu, ming = imm_fighter("Shabu"), fighter("Ming", room=101)
    assert say(shabu, line) == f"{want}\r\n\r\n{prompt_of(shabu)}"
    assert ming.skills == ["smash"]


def test_sset_learn_and_forget(world):
    shabu, ming = imm_fighter("Shabu"), fighter("Ming", room=101)    # 不在同房間也可以
    raw(ming)
    assert say(shabu, "ss mi fire") == f"Ming 學會了火球。\r\n\r\n{prompt_of(shabu)}"
    assert "你學會了火球！" in raw(ming) and skills.known(ming) == [SMASH, FIREBALL]
    assert say(shabu, "sset ming smash off") == f"Ming 忘掉了重擊。\r\n\r\n{prompt_of(shabu)}"
    assert skills.known(ming) == [FIREBALL]
    assert say(shabu, "sset shabu fire") == f"你學會了火球！\r\n\r\n{prompt_of(shabu)}"   # 給自己


def test_sset_is_only_for_imm(world):
    ming = fighter("Ming")
    assert say(ming, "sset ming fire") == f"什麼？\r\n\r\n{prompt_of(ming)}"


# ---- 增益技能：餽贈（之後教學區的 NPC 送給玩家，使用者定的） ----

GIFT = skills.SKILLS["gift"]
GIFT_LINES = ["  餽贈 gift  持續 3600 秒  消耗 0  冷卻 0 秒",
              "    每 3 秒 HP +上限的 10%、力量 +3、智慧 +3、知識 +3、體質 +3、敏捷 +3"]   # 做什麼放下一行，不超過 79 格


def gifted(name, room=102):
    p = fighter(name, room=room)
    skills.learn(p, GIFT)
    return p


def test_gift_data():
    assert (GIFT.kind, GIFT.target, GIFT.starter, GIFT.imm_only, GIFT.cooldown, skills.cost(GIFT, 50)) == ("buff", "ally", (), False, 0, 0)
    a = GIFT.affect
    assert (a["duration"], a["periodic_pct"], a["keep_on_death"]) == (3600, {"hp": 0.10}, True)
    assert a["applies"] == {k: 3.0 for k in stats.PRIMARY_KEYS}


def test_gift_on_yourself(world):
    shabu, ming = gifted("Shabu"), fighter("Ming")
    raw(ming)
    got = say(shabu, "use gift")                                      # 不是 imm、沒有消耗：不會當掉
    assert got == f"你對自己施展了【餽贈】。\r\n\r\n{prompt_of(shabu)}"
    assert "Shabu對自己施展了【餽贈】。" in text_of(ming)
    assert [a.source for a in shabu.affects] == ["gift"] and shabu.fighting is None and shabu.cooldowns == {}


def test_gift_on_others(world):
    shabu, hua, lin = gifted("Shabu"), fighter("Hua"), fighter("Lin")
    raw(hua), raw(lin)
    assert say(shabu, "us g hua") == f"你對Hua施展了【餽贈】。\r\n\r\n{prompt_of(shabu)}"
    assert "Shabu對你施展了【餽贈】。" in text_of(hua) and "Shabu對Hua施展了【餽贈】。" in text_of(lin)
    assert hua.affects[0].source == "gift" and shabu.affects == []


@pytest.mark.parametrize("line, want", [("use gift bird", "這裡沒有這個人。"), ("use gift dog", "餽贈只能放在玩家身上。")])
def test_gift_mistakes(world, line, want):
    shabu = gifted("Shabu")
    assert say(shabu, line) == f"{want}\r\n\r\n{prompt_of(shabu)}"
    assert shabu.fighting is None and mobile("野狗").affects == []


def test_gift_in_a_fight_keeps_the_opponent(world):
    shabu = gifted("Shabu")
    dog = mobile("野狗")
    got = in_fight([(shabu, dog)], lambda: (say(shabu, "use gift"), shabu.fighting))
    assert got[1] is dog and shabu.affects[0].source == "gift"


def test_gift_heals_every_3_seconds_and_overwrites(world):
    shabu = gifted("Shabu")
    say(shabu, "use gift")
    shabu.hp = 1.0
    affects.tick(), affects.tick()
    assert shabu.hp == 1.0
    affects.tick()
    assert shabu.hp == pytest.approx(1.0 + shabu.panel["hp"] * 0.10)
    say(shabu, "use gift")                                            # 再放一次：覆蓋，時間回到滿的
    assert len(shabu.affects) == 1 and shabu.affects[0].ticks == 3600


def test_gift_survives_death_and_wears_off(world):
    shabu = gifted("Shabu")
    say(shabu, "use gift")
    death.player_dies(shabu)
    assert shabu.affects[0].source == "gift"
    raw(shabu)
    for _ in range(3600):
        affects.tick()
    assert shabu.affects == [] and "你身上的【餽贈】消失了。" in text_of(shabu)


def test_an_npc_can_give_it(world):
    # 之後教學區的 NPC 直接呼叫 skills.use()：生物沒有冷卻、不用學，也不用在打架
    hua, dog = fighter("Hua"), mobile("野狗")
    raw(hua)
    skills.use(dog, GIFT, hua)
    assert hua.affects[0].source == "gift" and "野狗對你施展了【餽贈】。" in text_of(hua)


def test_skills_line_for_gift(world):
    shabu = gifted("Shabu")
    lines = say(shabu, "skills").split("\r\n")
    i = lines.index(GIFT_LINES[0])
    assert lines[i:i + 2] == GIFT_LINES and max(len(line.encode(ENCODING)) for line in lines) <= 79


def test_gift_in_score_wraps_within_79(world):
    # 說明太長就換行，接在下一行對齊，整行不超過 79 格（使用者要 score 跟 C 版一樣寬）
    shabu = gifted("Shabu")
    say(shabu, "use gift")
    lines = say(shabu, "score").split("\r\n")
    i = lines.index(" 你受到下列效果的影響：")
    assert lines[i + 1:i + 3] == [
        " 【        餽贈】 每 3 秒 HP +上限的 10%、力量 +3、智慧 +3、  還有  3600 秒",
        "                  知識 +3、體質 +3、敏捷 +3",
    ]
    assert max(len(line.encode(ENCODING)) for line in lines) <= 79


# ---- 天護（使用者定的）：護盾，HP 上限的 120%、10 秒；要用程式加，不扣消耗、沒有冷卻 ----

AEGIS = skills.SKILLS["aegis"]


def test_aegis_data():
    assert (AEGIS.name, AEGIS.kind, AEGIS.target, AEGIS.guild, AEGIS.starter, AEGIS.imm_only, AEGIS.cooldown) == \
        ("天護", "buff", "ally", None, (), False, 0)
    assert skills.cost(AEGIS, 50) == 0
    a = AEGIS.affect
    assert (a["duration"], a["shield_pct"], a.get("keep_on_death", False)) == (10, 1.2, False)


def test_aegis_is_learned_with_sset(world):
    shabu = fighter("Shabu")
    assert "aegis" not in shabu.skills                                  # 一開始不會
    imm = fighter("Imm")
    imm.imm = True
    say(imm, "sset shabu aegis")
    assert "aegis" in shabu.skills


def test_aegis_puts_a_shield_on_yourself_or_others(world):
    shabu, hua = fighter("Shabu"), fighter("Hua")
    skills.learn(shabu, AEGIS)
    assert say(shabu, "use aegis") == f"你對自己施展了【天護】。\r\n\r\n{prompt_of(shabu)}"
    a = shabu.affects[0]
    assert (a.name, a.ticks, a.shield) == ("天護", 10, pytest.approx(shabu.panel["hp"] * 1.2))
    assert shabu.cooldowns == {} and shabu.mv == shabu.panel["mv"] and shabu.fighting is None   # 不扣、沒有冷卻、不開打
    raw(hua)
    assert say(shabu, "use aegis hua") == f"你對Hua施展了【天護】。\r\n\r\n{prompt_of(shabu)}"
    assert hua.affects[0].shield == pytest.approx(hua.panel["hp"] * 1.2)


def test_aegis_absorbs_and_casting_again_refills(world):
    shabu = fighter("Shabu")
    skills.learn(shabu, AEGIS)
    say(shabu, "use aegis")
    affects.absorb(shabu, 30.0)
    say(shabu, "use aegis")                                             # 再放一次：回到滿的
    assert len(shabu.affects) == 1 and shabu.affects[0].shield == pytest.approx(shabu.panel["hp"] * 1.2)


def test_skills_lists_the_aegis_shield(world):
    shabu = fighter("Shabu")
    skills.learn(shabu, AEGIS)
    out = say(shabu, "skills")
    assert "天護 aegis  持續 10 秒  消耗 0  冷卻 0 秒" in out and "護盾 HP 上限的 120%" in out and "還剩" not in out


def test_effects_take_the_skills_name_unless_written():
    # 使用者定的：效果的 source、name 沒寫就用技能的 id、名稱；寫了照寫的（例如火球留下「燃燒」）
    a = skills.make_affect(AEGIS)
    assert (a.source, a.name) == ("aegis", "天護")
    burn = skills.Skill("fireball2", "火球", None, "buff", "ally", 0, 0.0, 0, 0.0,
                        affect=dict(source="burn", name="燃燒", duration=5))
    a = skills.make_affect(burn)
    assert (a.source, a.name) == ("burn", "燃燒")
    assert skills.make_affect(AEGIS) is not skills.make_affect(AEGIS) and "source" not in AEGIS.affect   # 每次一份新的，不改技能的資料


# ---- 技能打中最低 1 點、火球的燃燒（使用者 2026-11-06 定的） ----

def strikes(monkeypatch, dmg):
    """damage.strike() 一律回傳 (dmg, 沒爆擊)：0 是失手。"""
    monkeypatch.setattr(damage, "strike", lambda *args, **kwargs: (dmg, False))


def mage(name="Shabu"):
    return fighter(name, guild=stats.Guild.STAFF)


def test_skill_hits_do_at_least_1(world, monkeypatch):
    strikes(monkeypatch, 0.1)                                           # 打中但很小：0.1 × 1.2 → 1
    shabu, dog = fighter("Shabu"), mobile("野狗")
    before = dog.hp
    out = in_fight([], lambda: say(shabu, "use smash dog"))
    assert dog.hp == pytest.approx(before - 1) and "對它造成輕微的擦傷.(1)" in out


def test_skill_misses_still_do_0_and_leave_no_burn(world, monkeypatch):
    strikes(monkeypatch, 0.0)
    shabu, dog = mage(), mobile("野狗")
    before = dog.hp
    out = in_fight([], lambda: say(shabu, "use fireball dog"))
    assert dog.hp == before and "但是失手了.(0)" in out and dog.affects == []


def test_fireball_burns_3_times(world, monkeypatch):
    strikes(monkeypatch, 10.0)                                          # 第一發 10 × 1.2 ＝ 12，每跳 12 × 0.3 ＝ 3.6
    shabu, dog = mage(), mobile("野狗")
    in_fight([], lambda: say(shabu, "use fireball dog"))
    burn = dog.affects[0]
    assert (burn.source, burn.name, burn.duration, burn.periodic) == ("fireball", "燃燒", 9, {"hp": -12 * 0.3})
    after_hit = dog.hp
    raw(shabu)
    affects.tick(), affects.tick()
    assert dog.hp == after_hit                                          # 放下去後 3 秒才第一跳
    affects.tick()
    assert dog.hp == pytest.approx(after_hit - 3.6) and text_of(shabu) == "\r\n野狗被【燃燒】燒傷了.(4)\r\n\r\n" + prompt_of(shabu)
    for _ in range(6):
        affects.tick()
    assert dog.hp == pytest.approx(after_hit - 3 * 3.6) and dog.affects == []   # 3、6、9 秒各一次，燒完拿掉


def test_each_burn_does_at_least_1(world, monkeypatch):
    strikes(monkeypatch, 1.0)                                           # 第一發 1.2，每跳 0.36 → 1
    shabu, dog = mage(), mobile("野狗")
    in_fight([], lambda: say(shabu, "use fireball dog"))
    assert dog.affects[0].periodic == {"hp": -1}


def test_fireball_again_burns_again(world, monkeypatch):
    strikes(monkeypatch, 10.0)
    shabu, dog = mage(), mobile("野狗")
    shabu.imm = True                                                    # imm 不用等冷卻
    in_fight([], lambda: say(shabu, "use fireball dog"))
    for _ in range(4):
        affects.tick()
    in_fight([], lambda: say(shabu, "use fireball dog"))
    assert len(dog.affects) == 1 and dog.affects[0].ticks == 9          # 重新燒 3 次


def test_no_burn_when_the_first_hit_kills(world, monkeypatch):
    strikes(monkeypatch, 10.0)
    shabu, dog = mage(), mobile("野狗")
    dog.hp = 1.0
    in_fight([], lambda: say(shabu, "use fireball dog"))
    assert dog not in characters and dog.affects == []                  # 打死了：不留燃燒


def test_burns_are_heard_by_the_burned_and_hit_the_shield_first():
    p = Player("Ming", FakeWriter(), None)
    p.race, p.guild = stats.Race.HUMAN, stats.Guild.SWORD
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    stats.set_level(p, 1)
    characters.append(p)
    try:
        affects.add(p, affects.Affect("aegis", "天護", 30, shield_pct=4 / p.panel["hp"]))   # 4 點的護盾
        affects.add(p, affects.Affect("fireball", "燃燒", 9, periodic={"hp": -6.0}, hurt="燒傷"))
        top = p.hp
        raw(p)
        for _ in range(3):
            affects.tick()
        got = raw(p)
        out = re.sub(r"\x1b\[[0-9;]*m", "", got)
        assert "你被【燃燒】燒傷了.(6)（吸收 4）" in out and "你的【天護】被打破了。" in out and p.hp == pytest.approx(top - 2)
        assert colorize("{C你被【燃燒】燒傷了{x") in got                 # 被燒的那句亮青（跟被打一樣）
    finally:
        characters.clear()


def test_skills_lists_the_burn(world):
    out = say(mage(), "skills")
    assert "火球 fireball" in out and "    燃燒：每 3 秒 第一發的 30%，3 次" in out
