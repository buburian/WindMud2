"""生物的 special（specials.py，設計文件 §4.11，規則在區域製作手冊 special）：打架用的（時間、傷害、倍率、招式名稱、劇毒）、
平常的（janitor、fido）、名字的表跟手冊比對。

打架用的：戰鬥的 loop 不自己跑（fight.TICK_SECONDS 改很大），自己呼叫 Fight.tick()；平砍換成什麼都不做（fight.hit），
special 那一下的 damage.strike 換成固定值。開打和 tick 在同一個 asyncio.run 裡。
"""
import asyncio
import re
from pathlib import Path

import pytest

from area_helpers import make_area, make_mobile, make_room, write_json
from mud import affects, area, behavior, combat, damage, fight, objects, skills, specials, stats, zones
from mud.area import CORPSE_NPC_ITEM_TYPE, DRINK_CON_ITEM_TYPE, TRASH_ITEM_TYPE, ActFlag, Apply
from mud.characters import Position, characters
from mud.config import ENCODING, SPECIAL_TICKS
from mud.npcs import Npc
from mud.players import Player

AREA_MANUAL = Path(__file__).resolve().parent.parent / "docs" / "區域製作手冊.md"


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


class Pick:
    """choice() 挑第 n 個。"""

    def __init__(self, n):
        self.n = n

    def choice(self, seq):
        return seq[self.n]


@pytest.fixture
def world(tmp_path, monkeypatch):
    """房間 101 有一隻 1 級的野狗（站著、不會走），special 由各測試設定。"""
    monkeypatch.setattr(fight, "TICK_SECONDS", 1000)
    monkeypatch.setattr(fight, "hit", lambda ch, victim, hand: None)     # 平砍不打：只看 special
    dog = make_mobile(1)
    dog.update(short="野狗", keywords="dog", level=1, tier="normal", tier_roll=None, attack=None, defense=None,
               archetype=None, act=int(ActFlag.SENTINEL), position=7, sex=0, long="", drops=[], shop=None, special=None,
               special_ratio=None, poison_ratio=None)
    reset = [{"cmd": "M", "rare": 0, "mob_vnum": 1, "limit": 1, "room_vnum": 1, "comment": ""}]
    write_json(tmp_path, "a.json", make_area("a.json", [make_room(1)], 100, mobiles=[dog], resets=reset))
    zones.load(tmp_path)
    yield zones.world
    characters.clear()
    zones.stop()


def the_dog(special=None, ratio=None, poison=None):
    dog = next(c for c in characters if isinstance(c, Npc))
    dog.special, dog.special_ratio, dog.poison_ratio = special, ratio, poison
    return dog


def person(name):
    p = Player(name, FakeWriter(), zones.world.rooms[101])
    p.race, p.guild = stats.Race.HUMAN, stats.Guild.SWORD
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.skills = skills.starter(p.guild)
    stats.set_level(p, 1)
    p.hp = p.panel["hp"] = 1000.0           # 打不死（要測打死的另外調）
    characters.append(p)
    return p


def plain(p):
    text = re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))
    p.writer.data = b""
    return text


def strikes(monkeypatch, dmg, crit=False):
    """special 那一下的 damage.strike 換成固定值，記下傷害類型。"""
    kinds = []

    def strike(a, d, rng, kind=None, hand=0, source=None):
        kinds.append(kind)
        return dmg, crit

    monkeypatch.setattr(damage, "strike", strike)
    return kinds


def fight_for(ming, dog, n):
    """Ming 跟野狗開打，跑 n 個 tick，回傳每個 tick 後 Ming 的 HP。"""
    async def main():
        battle = fight.start_fight(ming, dog)
        hps = []
        for _ in range(n):
            battle.tick()
            hps.append(ming.hp)
        return hps

    return asyncio.run(main())


# ---- 打架用的：時間、傷害 ----

def test_first_after_six_seconds_then_every_six(world, monkeypatch):
    kinds = strikes(monkeypatch, 10.0)
    ming, dog = person("Ming"), the_dog("spec_breath_fire", ratio=2.5)
    hps = fight_for(ming, dog, 2 * SPECIAL_TICKS + 1)
    # 第 6、12 個 tick 各打一下：10 × 2.5 ＝ 25
    assert [i + 1 for i in range(len(hps)) if hps[i] != (hps[i - 1] if i else 1000.0)] == [SPECIAL_TICKS, 2 * SPECIAL_TICKS]
    assert hps[-1] == 1000.0 - 50 and kinds == ["dragon", "dragon"]


@pytest.mark.parametrize("dmg, ratio, lost", [
    (10.0, None, 18.0),                     # 沒寫倍率：1.8（跟重擊一樣）
    (10.0, 0.5, 5.0),
    (0.3, None, 1.0),                       # 打中最低 1 點
    (0.0, 2.5, 0.0),                        # 沒打中是 0
])
def test_damage_times_ratio(world, monkeypatch, dmg, ratio, lost):
    strikes(monkeypatch, dmg)
    ming, dog = person("Ming"), the_dog("spec_cast_mage", ratio=ratio)
    assert fight_for(ming, dog, SPECIAL_TICKS)[-1] == pytest.approx(1000.0 - lost)


class Always:
    def random(self):
        return 0.5                          # 打中、不浮動、不爆擊


@pytest.mark.parametrize("name, kind", [("spec_breath_fire", "dragon"), ("spec_cast_mage", "spell")])
def test_special_damage_uses_its_own_attack_points(world, monkeypatch, name, kind):
    # 「跟平砍一下一樣算、換傷害類型」：點數用牠平常攻擊的（物理），減傷照 special 的類型。
    # 只會物理攻擊的生物，龍焰、法術的點數是 0：直接用的話吐息會打 0（真的連線時看到的）
    monkeypatch.setattr(combat, "rng", Always())
    ming, dog = person("Ming"), the_dog(name)
    assert dog.mix == {"phys": 1.0} and dog.panel[f"dmg_{kind}"] == 0
    want = damage.per_hit(dog, ming, kind, source="phys") * specials.SPECIAL_RATIO
    assert want > damage.per_hit(dog, ming, kind) * specials.SPECIAL_RATIO
    assert fight_for(ming, dog, SPECIAL_TICKS)[-1] == pytest.approx(1000.0 - want)


def test_no_special_no_wait(world, monkeypatch):
    kinds = strikes(monkeypatch, 10.0)
    for name in (None, "spec_janitor", "spec_guard"):       # 沒有、平常的、先不做的：打架時不放
        ming, dog = person("Ming"), the_dog(name)
        assert fight_for(ming, dog, SPECIAL_TICKS)[-1] == 1000.0 and not specials.in_fights(dog)
        characters.remove(ming)
    assert kinds == []


# ---- 招式名稱、訊息 ----

@pytest.mark.parametrize("name, kind, noun", [
    ("spec_breath_acid", "dragon", "酸液龍燄"), ("spec_breath_fire", "dragon", "灼熱龍燄"),
    ("spec_breath_frost", "dragon", "冰冷龍燄"), ("spec_breath_gas", "dragon", "毒氣龍燄"),
    ("spec_breath_lightning", "dragon", "閃電龍燄"),
    ("spec_cast_mage", "spell", "法術"), ("spec_cast_cleric", "spell", "法術"), ("spec_cast_undead", "spell", "法術"),
    ("spec_cast_psionicist", "spell", "法術"), ("spec_cast_judge", "spell", "法術"), ("spec_cast_ghost", "spell", "法術"),
])
def test_messages_name_the_move(world, monkeypatch, name, kind, noun):
    # 生物的 special 也寫「使用X攻擊」（平砍不寫）；吐息算龍焰傷害，施法算法術傷害
    kinds = strikes(monkeypatch, 20.0)
    ming, hua, dog = person("Ming"), person("Hua"), the_dog(name, ratio=1)
    fight_for(ming, dog, SPECIAL_TICKS)
    assert kinds == [kind]
    assert plain(ming).startswith(f"\r\n野狗使用{noun}攻擊你，對你造成") and f"使用{noun}攻擊Ming，對他造成" in plain(hua)


def test_breath_any_picks_a_breath_each_time(world, monkeypatch):
    strikes(monkeypatch, 20.0)
    monkeypatch.setattr(specials, "rng", Pick(4))
    ming, dog = person("Ming"), the_dog("spec_breath_any")
    fight_for(ming, dog, SPECIAL_TICKS)
    assert "野狗使用閃電龍燄攻擊你" in plain(ming)


def test_a_miss_says_so(world, monkeypatch):
    strikes(monkeypatch, 0.0)
    ming, dog = person("Ming"), the_dog("spec_breath_fire")
    fight_for(ming, dog, SPECIAL_TICKS)
    assert "野狗使用灼熱龍燄攻擊你，但是失手了.(0)" in plain(ming)


# ---- 劇毒 ----

def test_poison_bites_then_burns_three_times(world, monkeypatch):
    kinds = strikes(monkeypatch, 10.0)
    ming, dog = person("Ming"), the_dog("spec_poison", ratio=2, poison=0.4)
    fight_for(ming, dog, SPECIAL_TICKS)
    text = plain(ming)
    assert kinds == ["spell"] and "野狗使用利牙攻擊你，對你造成" in text and text.count("你突然覺得自己得病了。") == 1
    poison = ming.affects[0]
    # 每跳 ＝ 咬的那一下（10 × 2 ＝ 20）× 0.4 ＝ 8，跳 3 次（跟火球的燃燒一樣）
    assert (poison.source, poison.name, poison.duration, poison.periodic, poison.hurt) == ("spec_poison", "劇毒", 9, {"hp": -8.0}, "毒傷")
    before = ming.hp
    for _ in range(3):
        affects.tick()
    assert ming.hp == before - 8 and "你被【劇毒】毒傷了.(8)" in plain(ming)
    for _ in range(6):
        affects.tick()
    assert ming.affects == [] and ming.hp == before - 24 and plain(ming).endswith(
        "你覺得你的病好多了。\r\n\r\n" + re.sub(r"\x1b\[[0-9;]*m", "", ming.prompt()))


def test_poison_ratio_defaults_and_minimum(world, monkeypatch):
    strikes(monkeypatch, 1.0)                # 1 × 1.8 ＝ 1.8，× 0.3 ＝ 0.54：最低 1 點
    ming, dog = person("Ming"), the_dog("spec_poison")
    fight_for(ming, dog, SPECIAL_TICKS)
    assert ming.affects[0].periodic == {"hp": -1}


@pytest.mark.parametrize("dmg, hp", [(0.0, 1000.0), (5.0, 1.0)])     # 沒咬中；咬死了
def test_no_poison_when_missed_or_dead(world, monkeypatch, dmg, hp):
    strikes(monkeypatch, dmg)
    ming, dog = person("Ming"), the_dog("spec_poison")
    ming.hp = hp
    fight_for(ming, dog, SPECIAL_TICKS)
    assert "spec_poison" not in [a.source for a in ming.affects] and "得病了" not in plain(ming)


# ---- 平常的：janitor、fido ----

def thing(name, keyword, cost, item_type=8, take=True):
    obj = objects.Obj(name, f"{name}放在這裡。", item_type, [keyword])
    obj.cost, obj.take = cost, take
    return obj


def test_janitor_picks_up_trash_one_at_a_time(world):
    dog = the_dog("spec_janitor")
    hua = person("Hua")
    gem, trash, bottle, potion = thing("寶石", "gem", 50), thing("垃圾", "trash", 50, TRASH_ITEM_TYPE), \
        thing("水壺", "flask", 50, DRINK_CON_ITEM_TYPE), thing("藥水", "potion", 5)
    heavy = thing("垃圾堆", "heap", 0, TRASH_ITEM_TYPE, take=False)
    armor = thing("皮甲", "armor", 0, 9)    # 裝備不看 cost（都寫 0），照基本價格：HP +20 是 20 點（使用者選的）
    armor.slot, armor.color, armor.level, armor.affects = "body", "white", 10, [(Apply.HP, 20)]
    floor = zones.world.rooms[101].contents
    floor[:] = [gem, armor, heavy, trash, bottle, potion]
    for _ in range(4):
        behavior.idle(dog)
    # 拿得起來的垃圾、液體容器、基本價格小於 10 的，一次撿一件（地上第一件）；寶石 50、皮甲 20 不撿
    assert dog.carrying == [potion, bottle, trash] and floor == [gem, armor, heavy]
    assert plain(hua).count("野狗拾起了一些垃圾。") == 3


def test_fido_eats_a_corpse_and_drops_what_was_inside(world):
    dog = the_dog("spec_fido")
    hua = person("Hua")
    sword, gem, potion = thing("長劍", "sword", 0), thing("寶石", "gem", 50), thing("藥水", "potion", 5)
    corpse = objects.Obj("野兔的屍體", "野兔的屍體橫躺在地上。", CORPSE_NPC_ITEM_TYPE, ["corpse"])
    corpse.contains = [sword, gem]
    floor = zones.world.rooms[101].contents
    floor[:] = [potion, corpse]
    behavior.idle(dog)
    assert floor == [sword, gem, potion] and corpse.contains == []
    assert plain(hua).startswith("\r\n野狗很兇惡地吞食了一具屍體。\r\n")
    behavior.idle(dog)                      # 沒有屍體了：什麼都不做
    assert floor == [sword, gem, potion] and plain(hua) == ""


def test_idle_specials_need_to_stand(world):
    dog = the_dog("spec_janitor")
    dog.position = Position.RESTING
    zones.world.rooms[101].contents[:] = [thing("垃圾", "trash", 0, TRASH_ITEM_TYPE)]
    behavior.idle(dog)
    assert dog.carrying == []


# ---- 名字的表 ----

def test_special_names_match_the_manual():
    section = AREA_MANUAL.read_text(encoding="utf-8").split("### special（特殊程式）", 1)[1].split("\n## ", 1)[0]
    assert sorted(area.SPECIALS) == sorted(set(re.findall(r"spec_\w+", section)))
    # 每個名字剛好是一種：打架用的、平常的、先不做的
    groups = [set(specials.FIGHTING), set(specials.IDLE), set(specials.NOT_YET)]
    assert set().union(*groups) == set(area.SPECIALS) and sum(map(len, groups)) == len(area.SPECIALS)
    assert set(specials.NOT_YET) == {"spec_guard", "spec_executioner", "spec_cast_adept", "spec_thief", "spec_mayor",
                                     "spec_repairman"}
