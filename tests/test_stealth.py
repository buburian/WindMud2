"""看不見的人和光圈（stealth.py，玩家角色手冊「看不見的人和光圈」，使用者 2026-11-17 定的）：
隱形、藏匿、偵測、粉光（看得到、找得到、某人、走進來、主動攻擊、不同房間）、現形（出手、被打、沒打中、生物天生的、放減益）、
通透（關著、鎖著、法術穿不過）、聖光（平砍、持續扣血、護盾、窒息不算）、光圈（每一種、順序、顏色）、7 個技能（use、只能放自己、減益、物品）。
"""
import asyncio
import re

import pytest

import mud.commands as commands
from area_helpers import make_area, make_exit, make_mobile, make_object, make_room, write_json
from mud import affects, behavior, combat, fight, npcs, objects, save, skills, stats, terrain, weather, zones
from mud.area import ActFlag, AffectFlag, Locks, RoomFlag, Sector
from mud.characters import characters, find_in_room
from mud.commands.system import tags
from mud.config import ENCODING
from mud.players import Player

INVIS, HIDE, SANCT, FF = skills.SKILLS["invis"], skills.SKILLS["hide"], skills.SKILLS["sanctuary"], skills.SKILLS["faerie_fire"]


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


class First:
    """behavior.rng：骰到的都是不會發生的，choice() 挑第一個。"""
    def random(self):
        return 1.0

    def choice(self, seq):
        return seq[0]


def door(to, keywords, locks):
    e = make_exit(to)
    e.update(keywords=keywords, locks=locks, key=-1)
    return e


def mob(vnum, short, keywords, affected_by=0):
    m = make_mobile(vnum)
    m.update(short=short, keywords=keywords, level=1, tier="normal", tier_roll=None, act=0, position=7, drops=[],
             special=None, shop=None, long="", affected_by=affected_by)
    return m


def item(vnum, short, keywords, item_type, values, wear="1"):
    o = make_object(vnum)
    o.update(short=short, keywords=keywords, item_type=item_type, values=list(values), wear_flags=wear, affects=[],
             extra_descriptions=[], script=None)
    return o


@pytest.fixture
def world(tmp_path, monkeypatch):
    """101：野狗、守衛（看得到隱形）；北邊 102 隔著鎖著的木門，東邊 103 隔著法術穿不過的鐵門，西邊 104 沒有門。"""
    monkeypatch.setattr(weather, "current", weather.Weather(hour=12))
    monkeypatch.setattr(fight, "TICK_SECONDS", 1000)
    monkeypatch.setattr(behavior, "rng", First())
    monkeypatch.setattr(save, "save_player", lambda p: None)
    r101, r102, r103, r104 = make_room(101, west=104), make_room(102), make_room(103), make_room(104, east=101)
    r101["exits"].update(north=door(102, "木門 door", int(Locks.DOOR)), east=door(103, "鐵門 gate", int(Locks.PASSPROOF)))
    r102["exits"]["south"] = door(101, "木門 door", int(Locks.DOOR))
    r103["exits"]["west"] = door(101, "鐵門 gate", int(Locks.PASSPROOF))
    objs = [item(110, "隱形藥水", "potion", 10, (1, "invis", "", "")),
            item(111, "藏匿魔杖", "wand", 3, (0, 3, 3, "hide"), "1|16384")]
    resets = [{"cmd": "M", "rare": 0, "mob_vnum": v, "limit": 1, "room_vnum": 101, "comment": ""} for v in (101, 102)]
    resets += [{"cmd": "D", "if_flag": 0, "room_vnum": 101, "direction": d, "state": 2, "comment": ""} for d in ("north", "east")]
    write_json(tmp_path, "a.json", make_area("a.json", [r101, r102, r103, r104], (100, 199), objects=objs, resets=resets,
                                             mobiles=[mob(101, "野狗", "dog"), mob(102, "守衛", "guard", int(AffectFlag.DETECT_INVIS))]))
    zones.load(tmp_path)
    yield
    characters.clear()
    zones.stop()


def person(name, room=101, imm=False, knows=()):
    p = Player(name, FakeWriter(), zones.world.rooms[room])
    p.race, p.guild, p.imm = stats.Race.HUMAN, stats.Guild.SWORD, imm
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.skills = list(knows)
    stats.set_level(p, 10)
    characters.append(p)
    return p


def npc(vnum):
    return next(c for c in characters if getattr(c, "vnum", None) == vnum)


def plain(p):
    text = re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))
    p.writer.data = b""
    return text


def say(p, line):
    plain(p)
    commands.command(p, line)
    return plain(p).rsplit("\r\n\r\n", 1)[0]


def put_on(ch, skill_id):
    affects.add(ch, skills.make_affect(skills.SKILLS[skill_id]))


def look_lines(p):
    return say(p, "look").split("\r\n")


# ---- 隱形、藏匿：看不到 ----

def test_invisible_people_are_not_there(world):
    ming, hua = person("Ming"), person("Hua")
    put_on(ming, "invis")
    assert "Ming站在這裡。" not in look_lines(hua)
    assert find_in_room(hua, "ming") is None
    plain(hua)
    say(ming, "say 嗨")
    assert "某人說：『嗨』" in plain(hua)
    assert say(hua, "look ming") == "在這裡找不到你要看的東西。"
    assert find_in_room(ming, "ming") is ming                    # 自己找得到


def test_who_sees_the_invisible(world):
    ming = person("Ming")
    put_on(ming, "invis")
    boss, eye = person("Boss", imm=True), person("Eye")
    put_on(eye, "detect_invis")
    assert "(隱形)Ming站在這裡。" in look_lines(boss) and "(隱形)Ming站在這裡。" in look_lines(eye)
    put_on(eye, "detect_hidden")
    affects.remove(eye, "detect_invis")
    assert "(隱形)Ming站在這裡。" not in look_lines(eye)                 # 看得到藏匿，看不到隱形


def test_hidden_needs_detect_hidden(world):
    ming, eye = person("Ming"), person("Eye")
    put_on(ming, "hide")
    put_on(eye, "detect_invis")
    assert find_in_room(eye, "ming") is None
    put_on(eye, "detect_hidden")
    assert "(藏匿)Ming站在這裡。" in look_lines(eye)


def test_faerie_fire_shows_them(world):
    ming, hua = person("Ming"), person("Hua")
    put_on(ming, "invis")
    put_on(ming, "hide")
    put_on(ming, "faerie_fire")
    assert "(隱形)(藏匿)(粉光)Ming站在這裡。" in look_lines(hua)


def test_other_rooms_still_see_the_name(world):
    ming, hua = person("Ming"), person("Hua", 104)
    put_on(ming, "invis")
    plain(hua)
    say(ming, "tell hua 嗨")
    assert "Ming告訴你" in plain(hua)


def test_walking_in_unseen(world):
    ming, hua = person("Ming", 104), person("Hua")
    put_on(ming, "invis")
    plain(hua)
    say(ming, "east")
    assert plain(hua) == "" and ming.room.vnum == 101


def test_the_screen_and_the_names_agree(world):
    # look 和 find_in_room() 用同一個判斷：「畫面上第 n 隻」才對得上。兩隻都叫 dog，第一隻隱形
    hua = person("Hua")
    dog, guard = npc(101), npc(102)
    dog.affected_by = AffectFlag.INVISIBLE
    guard.keywords = ["dog"]
    shown = [line for line in look_lines(hua) if "站在這裡" in line]
    assert shown == ["守衛站在這裡。"]
    assert find_in_room(hua, "dog") is guard and find_in_room(hua, "2.dog") is None


def test_aggressive_creatures_need_to_see_you(world):
    ming = person("Ming")
    put_on(ming, "invis")
    dog, guard = npc(101), npc(102)
    dog.act = ActFlag.AGGRESSIVE

    async def main():
        behavior.aggress()
        first = dog.fighting
        guard.act = ActFlag.AGGRESSIVE                           # 守衛看得到隱形
        behavior.aggress()
        return first, guard.fighting

    assert asyncio.run(main()) == (None, ming)


# ---- 現形 ----

def test_attacking_reveals_you_even_on_a_miss(world):
    ming, hua = person("Ming"), person("Hua")
    put_on(ming, "invis")
    out = affects.Messages()
    combat.land(out, ming, npc(101), 0, False)
    assert not affects.has_flag(ming, AffectFlag.INVISIBLE)
    assert "Ming漸漸地現出了自己的身影。" in out.by[hua]
    assert "你不再隱形了。" in out.by[ming]


def test_being_hit_reveals_you(world):
    ming, hua = person("Ming"), person("Hua")
    put_on(ming, "hide")
    out = affects.Messages()
    combat.land(out, npc(101), ming, 0, False)
    assert not affects.has_flag(ming, AffectFlag.HIDE)
    assert "Ming現身出來了。" in out.by[hua] and "你藏匿的效果消失了!!" in out.by[ming]


def test_creatures_lose_what_they_were_born_with(world):
    ming, hua = person("Ming"), person("Hua")
    guard = npc(102)
    guard.affected_by = AffectFlag.INVISIBLE | AffectFlag.DETECT_INVIS
    assert find_in_room(hua, "guard") is None
    out = affects.Messages()
    combat.land(out, ming, guard, 0, False)
    assert guard.affected_by == AffectFlag.DETECT_INVIS             # 隱形拿掉，看得到隱形還在
    assert "守衛漸漸地現出了自己的身影。" in out.by[hua] and find_in_room(hua, "guard") is guard


def test_casting_a_buff_does_not_reveal_you(world):
    ming = person("Ming", knows=["sanctuary"])
    put_on(ming, "invis")
    say(ming, "use sanctuary")
    assert affects.has_flag(ming, AffectFlag.INVISIBLE) and affects.has_flag(ming, AffectFlag.SANCTUARY)


# ---- 通透 ----

def test_pass_door(world):
    ming = person("Ming", knows=["pass_door"])
    assert say(ming, "north") == "【木門】關起來了。"
    say(ming, "use pass")
    assert say(ming, "east") == "啊!!你沒有辦法通過【鐵門】。"            # 法術穿不過
    say(ming, "north")
    assert ming.room.vnum == 102                                   # 鎖著的也穿得過（照 C 版）


# ---- 聖光 ----

def test_sanctuary_halves_hits(world):
    ming, hua = person("Ming"), person("Hua")
    put_on(ming, "sanctuary")
    full = ming.hp
    out = affects.Messages()
    combat.land(out, npc(101), ming, 10, False)
    assert ming.hp == full - 5
    put_on(ming, "aegis")                                          # 護盾在減半之後扣
    shield = next(a for a in ming.affects if a.source == "aegis")
    before = shield.shield
    combat.land(out, npc(101), ming, 10, False)
    assert shield.shield == before - 5 and ming.hp == full - 5


def test_sanctuary_halves_damage_over_time(world):
    ming = person("Ming")
    put_on(ming, "sanctuary")
    full = ming.hp
    poison = skills.dot_affect("test", dict(name="劇毒", ratio=1.0, jumps=1, hurt="毒傷"), 10)
    affects.add(ming, poison)
    affects.pulse(ming, poison, affects.Messages())
    assert ming.hp == full - 5


def test_choking_is_not_halved(world):
    ming = person("Ming")
    put_on(ming, "sanctuary")
    ming.room.sector = Sector.UNDERWATER
    full = ming.hp
    terrain.choke()
    assert ming.hp == pytest.approx(full - ming.panel["hp"] * terrain.CHOKE_PCT)


# ---- 粉光的數字（設計文件 §2.6）----

def test_faerie_fire_lowers_dodge_and_ac_last(world):
    ming = person("Ming")
    put_on(ming, "gift")                                           # 先有別的效果加減（主屬性 +3），再乘
    before = dict(ming.panel)
    put_on(ming, "faerie_fire")
    assert ming.panel["dodge"] == pytest.approx(before["dodge"] * stats.FAERIE_FIRE_RATIO)
    assert ming.panel["res_spell"] == before["res_spell"]           # 法術抗性不另外減
    affects.remove(ming, "faerie_fire")
    assert ming.panel["dodge"] == pytest.approx(before["dodge"])


def test_faerie_fire_born_with_it(world):
    dog = npc(101)
    before = dict(dog.panel)
    assert before["ac"] > 0
    dog.affected_by = AffectFlag.FAERIE_FIRE
    npcs.recompute(dog)
    assert dog.panel["dodge"] == pytest.approx(before["dodge"] * stats.FAERIE_FIRE_RATIO)
    assert dog.panel["ac"] == pytest.approx(before["ac"] * stats.FAERIE_FIRE_RATIO)


# ---- 光圈 ----

def test_auras_in_order_and_color(world):
    ming = person("Ming")
    for sid in ("sanctuary", "faerie_fire", "pass_door", "hide", "invis"):
        put_on(ming, sid)
    assert tags(ming) == [("隱形", "{y"), ("藏匿", "{y"), ("通透", "{g"), ("粉光", "{M"), ("聖光", "{W")]
    guard = npc(102)
    guard.tier = "elite"
    guard.affected_by |= AffectFlag.SANCTUARY                        # 區域檔寫的也有光圈
    assert tags(guard) == [("菁英", "{G"), ("聖光", "{W")]


# ---- 技能 ----

def test_buffs_on_others_and_self_only(world):
    ming, hua = person("Ming", knows=["invis", "hide", "detect_invis"]), person("Hua")
    assert say(ming, "use invis hua") == "你對Hua施展了【隱身術】。"
    assert affects.has_flag(hua, AffectFlag.INVISIBLE)
    person("Wang")
    assert say(ming, "use hide wang") == skills.SELF_ONLY            # Hua 已經隱形、找不到了，換一個人
    assert say(ming, "use hide") == "你對自己施展了【藏匿技巧】。"
    assert say(ming, "use detect_invis ming") == "你對自己施展了【偵查隱形】。"    # 自己的名字可以


def test_faerie_fire(world):
    ming, hua = person("Ming", knows=["faerie_fire"]), person("Hua")
    put_on(ming, "invis")

    async def main():
        out = say(ming, "use faerie dog")
        return out, ming.fighting

    out, fighting = asyncio.run(main())
    dog = npc(101)
    assert fighting is dog and affects.has_flag(dog, AffectFlag.FAERIE_FIRE)
    assert out == "你不再隱形了。\r\n粉紅色的光圈將野狗團團圍住了。"     # 放減益也算出手：現形
    seen = plain(hua)
    assert "Ming漸漸地現出了自己的身影。" in seen and "粉紅色的光圈將野狗團團圍住了。" in seen
    assert say(ming, "use faerie hua") == "你不可以攻擊玩家。"


def test_faerie_fire_not_in_safe_rooms(world):
    ming = person("Ming", knows=["faerie_fire"])
    ming.room.room_flags = RoomFlag.SAFE
    assert "神力所保護" in say(ming, "use faerie dog")
    assert not affects.has_flag(npc(101), AffectFlag.FAERIE_FIRE) and ming.fighting is None


def test_skills_lists_them(world):
    ming = person("Ming", knows=["faerie_fire", "pass_door"])
    text = say(ming, "skills")
    assert "灼熱火燄 faerie_fire  持續 1800 秒" in text and "穿牆術 pass_door  持續 1800 秒" in text
    assert "粉光" in text and "通透" in text


def test_items_cast_them(world):
    ming, hua = person("Ming"), person("Hua")
    ming.carrying.insert(0, objects.create(110, 1, None))
    say(ming, "quaff potion")
    assert affects.has_flag(ming, AffectFlag.INVISIBLE)
    wand = objects.create(111, 1, None)
    ming.equipment["hold"] = wand
    assert say(ming, "zap hua") == skills.SELF_ONLY                 # 只能放自己的：不用掉
    assert wand.charges == 3
    say(ming, "zap")
    assert affects.has_flag(ming, AffectFlag.HIDE) and wand.charges == 2
