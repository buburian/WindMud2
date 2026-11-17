"""表情動作（socials.py、commands/social.py）和說話結尾的表情：真的 socials.json 檢查得過、check() 的每條規則、
縮寫、沒對象／對別人／對自己、遠遠地、找不到、不在同一間房的生物、睡著只能 snore、生物的反應、廣播、很暗、
socials 指令、生物也能做、say／chat／tell／reply 的表情。
"""
import copy
import json
import re

import pytest

import mud.commands as commands
from area_helpers import make_area, make_mobile, make_room, write_json
from mud import socials, stats, zones
from mud.area import RoomFlag
from mud.characters import Position, characters
from mud.commands import REFUSALS, social
from mud.config import ENCODING, SOCIAL_FILE
from mud.npcs import Npc
from mud.players import Player

COMMAND_NAMES = [c for c, _, _ in commands.COMMANDS + commands.IMM_COMMANDS]
DATA = json.loads(open(SOCIAL_FILE, encoding="utf-8").read())


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


class FakeRng:
    def __init__(self, roll):
        self.roll = roll

    def randrange(self, n):
        return self.roll


@pytest.fixture
def world(tmp_path, monkeypatch):
    """101 —北— 102；103 很暗。101 有一隻狗（dog），102 有一隻貓（cat）。"""
    monkeypatch.setattr(socials, "table", [])
    monkeypatch.setattr(socials, "expressions", [])
    socials.load(SOCIAL_FILE)
    monkeypatch.setattr(social, "rng", FakeRng(15))                 # 預設生物沒反應
    rooms = [make_room(101, north=102), make_room(102, south=101), make_room(103)]
    rooms[2]["room_flags"] = int(RoomFlag.DARK)
    mobs = []
    for vnum, short, kw in ((101, "野狗", "dog"), (102, "野貓", "cat")):
        m = make_mobile(vnum)
        m.update(short=short, keywords=kw, act=2, position=7, drops=[], special=None, shop=None, long="")
        mobs.append(m)
    resets = [{"cmd": "M", "rare": 0, "mob_vnum": v, "limit": 1, "room_vnum": v, "comment": ""} for v in (101, 102)]
    write_json(tmp_path, "a.json", make_area("a.json", rooms, (100, 199), mobiles=mobs, resets=resets))
    zones.load(tmp_path)
    yield zones.world
    characters.clear()
    zones.stop()


def person(name, room=101, level=1):
    p = Player(name, FakeWriter(), zones.world.rooms[room])
    p.race, p.guild = stats.Race.HUMAN, stats.Guild.SWORD
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.skills = []
    stats.set_level(p, level)
    characters.append(p)
    return p


def plain(p):
    text = re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))
    p.writer.data = b""
    return text


def say(p, line):
    plain(p)
    commands.command(p, line)
    return plain(p).rsplit("\r\n\r\n", 1)[0]


def mob(name):
    return next(c for c in characters if isinstance(c, Npc) and c.name == name)


SMILE = next(s for s in DATA["socials"] if s["name"] == "smile")


def fill(text, n="", N="", M="他", m="他"):
    """代換碼換成名字：$M、$m 是他／她／它（玩家預設是男的「他」，生物 sex 0 是「它」）。"""
    return text.replace("$n", n).replace("$N", N).replace("$M", M).replace("$m", m)


# ---- 檔案 ----

def test_the_real_file_is_fine():
    assert socials.check(DATA, COMMAND_NAMES) == []
    assert len(DATA["socials"]) == 278 and len(DATA["expressions"]) == 18


def broken(change):
    data = copy.deepcopy(DATA)
    change(data)
    return socials.check(data, COMMAND_NAMES)


@pytest.mark.parametrize("change, problem", [
    (lambda d: d["socials"].append(copy.deepcopy(d["socials"][0])), "name 重複了"),
    (lambda d: d["socials"][0].update(name="lo"), "會先找到指令 look"),
    (lambda d: d["socials"][0].update(name="Smile"), "只能用小寫英文字母"),
    (lambda d: d["socials"][0]["alone"].update(room="$n對$N笑"), "沒有對方，不能用 $N"),
    (lambda d: d["socials"][0]["target"].update(you="$x"), "不認得的代換碼 $x"),
    (lambda d: d["socials"][0]["target"].pop("target"), "少了 target"),
    (lambda d: d["socials"][0].update(extra=1), "多了不認得的 extra"),
    (lambda d: d["socials"][0]["self"].update(you="你笑😀"), "轉不成 Big5"),
    (lambda d: d["expressions"].append({"ending": ":)", "adverb": "又"}), "ending ':)' 重複了"),
    (lambda d: d["expressions"].append({"ending": ":-))", "adverb": "又"}), "1～2 個"),
    (lambda d: d["expressions"].append({"ending": "@", "adverb": "{R紅"}), "不能有 $ 和 {"),
])
def test_check_rules(change, problem):
    assert any(problem in p for p in broken(change))


def test_self_can_name_yourself_as_the_other():
    assert broken(lambda d: d["socials"][0]["self"].update(room="$n對$M自己笑")) == []      # self 的對方就是自己


# ---- 做動作 ----

def test_alone(world):
    ming, wang = person("Ming"), person("Wang")
    assert say(ming, "smile") == SMILE["alone"]["you"]
    assert fill(SMILE["alone"]["room"], "Ming") in plain(wang)


def test_abbreviation_follows_the_file_order(world):
    assert socials.find("smi")["name"] == "smile"                     # smile 在 smirk 前面
    assert say(person("Ming"), "smi") == SMILE["alone"]["you"]


def test_commands_come_first(world):
    ming = person("Ming")
    say(ming, "n")                                                    # 是 north，不是 n 開頭的動作（nod…）
    assert ming.room.vnum == 102


def test_at_someone_in_the_room(world):
    ming, wang, chen = person("Ming"), person("Wang"), person("Chen")
    assert say(ming, "smile wang") == fill(SMILE["target"]["you"], N="Wang")
    assert fill(SMILE["target"]["target"], "Ming") in plain(wang)
    assert fill(SMILE["target"]["room"], "Ming", "Wang") in plain(chen)


def test_at_yourself(world):
    ming, wang = person("Ming"), person("Wang")
    die = socials.find("die")
    assert say(ming, "die ming") == die["self"]["you"]
    assert "Ming直挺挺地倒在他自己身邊" in plain(wang)              # $M 是自己


def test_far_away_player(world):
    ming, wang, chen = person("Ming"), person("Wang", 102), person("Chen")
    assert say(ming, "smile wang") == "遠遠地，" + fill(SMILE["target"]["you"], N="Wang")
    assert "遠遠地，" + fill(SMILE["target"]["target"], "Ming") in plain(wang)
    assert "微笑" not in plain(chen)                                  # 旁邊的人看不到


@pytest.mark.parametrize("line, message", [("smile cat", social.NOT_HERE_MOB), ("smile nobody", social.NOT_HERE)])
def test_cannot_find(world, line, message):
    assert say(person("Ming"), line) == message


def test_sleeping_only_snore(world):
    ming = person("Ming")
    ming.position = Position.SLEEPING
    assert say(ming, "smile") == REFUSALS[Position.SLEEPING]
    assert say(ming, "snore") == socials.find("snore")["alone"]["you"]


def test_unknown_word_is_still_what(world):
    assert say(person("Ming"), "xyzzy") == "什麼？"


# ---- 生物的反應 ----

@pytest.mark.parametrize("roll, seen", [(1, "野狗愉快的向你微笑。"), (8, "野狗愉快的向你微笑。"),
                                        (9, "野狗給了你一個大巴掌。"), (12, "野狗給了你一個大巴掌。")])
def test_creatures_answer(world, monkeypatch, roll, seen):
    monkeypatch.setattr(social, "rng", FakeRng(roll))
    ming = person("Ming")
    assert seen in say(ming, "smile dog")
    assert mob("野狗").fighting is None


@pytest.mark.parametrize("roll", [0, 13, 15])                         # 0：C 版會開打，使用者選不做
def test_creatures_ignore(world, monkeypatch, roll):
    monkeypatch.setattr(social, "rng", FakeRng(roll))
    ming = person("Ming")
    assert say(ming, "smile dog") == fill(SMILE["target"]["you"], M="它")
    assert mob("野狗").fighting is None and ming.fighting is None


def test_creatures_can_do_socials(world):
    ming = person("Ming")
    plain(ming)
    commands.command(mob("野狗"), "bark")
    assert "野狗像隻狗樣的狂吠。" in plain(ming)


# ---- 廣播 ----

def test_broadcast_needs_level_20(world):
    assert say(person("Ming", level=19), "*smile") == "什麼？"


def test_broadcast(world):
    ming, wang, chen = person("Ming", level=20), person("Wang", 102), person("Chen", 103)
    assert say(ming, "*smile") == "[動作] " + SMILE["alone"]["you"]
    for p in (wang, chen):
        assert "[動作] " + fill(SMILE["alone"]["room"], "Ming") in plain(p)


def test_broadcast_at_someone(world):
    ming, wang, chen = person("Ming", level=20), person("Wang", 102), person("Chen", 103)
    assert say(ming, "*smile wang") == "[動作] " + fill(SMILE["target"]["you"], N="Wang")
    assert "[動作] " + fill(SMILE["target"]["target"], "Ming") in plain(wang)
    assert "[動作] " + fill(SMILE["target"]["room"], "Ming", "Wang") in plain(chen)


# ---- 很暗 ----

def test_in_the_dark(world):
    ming, wang = person("Ming", 103), person("Wang", 103)
    assert say(ming, "smile wang") == social.NOT_HERE                  # 看不到人，遠的也找不到
    say(ming, "smile")
    assert fill(SMILE["alone"]["room"], "某人") in plain(wang)


# ---- socials 指令 ----

def test_socials_lists_six_a_row(world):
    ming = person("Ming")
    ming.page_lines = 60                                              # 47 行：一頁放得下
    rows = say(ming, "socials").split("\r\n")
    assert rows[0].split() == [s["name"] for s in DATA["socials"][:6]]
    assert sum(len(r.split()) for r in rows) == 278


# ---- 說話的表情 ----

@pytest.mark.parametrize("text, adverb", [("hi :)", "愉快地"), ("hi :-)", "興高采烈地"), ("why?", "疑惑地"),
                                          ("no?!", "憤怒地"), ("go!!", "高聲地"), ("wow :!", "興奮地"),
                                          ("hmm :*", "無知地"), ("ok :) ", "愉快地"), ("hi!", ""), ("plain", "")])
def test_adverbs(world, text, adverb):
    assert socials.adverb(text) == adverb


def test_say_chat_tell_reply(world):
    ming, wang = person("Ming"), person("Wang")
    assert say(ming, "say hi :)") == "你愉快地說：『hi :)』"
    assert "Ming愉快地說：『hi :)』" in plain(wang)
    assert say(ming, "chat hi :(") == "你傷心地聊天：hi :("
    assert "Ming 傷心地聊天：hi :(" in plain(wang)
    assert say(ming, "tell wang ok?") == "你疑惑地告訴Wang：ok?"
    assert "Ming疑惑地告訴你：ok?" in plain(wang)
    assert say(wang, "reply yes :!") == "你興奮地告訴Ming：yes :!"
    assert say(ming, "say plain") == "你說：『plain』"
