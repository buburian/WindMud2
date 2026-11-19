"""秋風城四間公會分館的導師（真的 areas/midgaard.json 和 midgaard/ 的四個腳本，使用者 2026-11-19 要的）：
走進來聽到怎麼選路、說路名就選（paths.choose）、不是你公會的、等級不夠、換路要說兩次和錢、Lv40 選小路、腳本沒出錯。
"""
import re
from pathlib import Path

import pytest

import mud.commands as commands
from mud import paths, save, scripts, skills, stats, weather, zones
from mud.characters import characters
from mud.config import ENCODING
from mud.npcs import Npc
from mud.players import Player

AREAS = Path(__file__).resolve().parent.parent / "areas"
SWORD, STAFF = stats.Guild.SWORD, stats.Guild.STAFF
# 大路 → (走進分館前站的房間, 往哪走, 導師的名字)
HALLS = {"戰士": (3016, "s", "老教頭"), "刺客": (3026, "s", "引路人"), "元素": (3012, "s", "老學者"), "神官": (3005, "w", "老牧師")}


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


@pytest.fixture
def errors(tmp_path, monkeypatch):
    """載入真的 areas/；回傳腳本出錯的清單。"""
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path)
    monkeypatch.setattr(weather, "current", weather.Weather(hour=12))
    found = []
    monkeypatch.setattr(scripts, "report", lambda r, msg: found.append(msg))
    zones.load(AREAS)
    yield found
    characters.clear()
    zones.stop()


def player(level=10, guild=SWORD, big="戰士", gold=0, name="Ming"):
    p = Player(name, FakeWriter(), zones.world.rooms[HALLS[big][0]])
    p.race, p.guild = stats.Race.HUMAN, guild
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.skills = skills.starter(guild)
    stats.set_level(p, level)
    p.gold = gold
    characters.append(p)
    return p


def plain(p):
    text = re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))
    p.writer.data = b""
    return text


def do(p, line):
    plain(p)
    commands.command(p, line)
    return plain(p)


def walk_in(p, big):
    out = do(p, HALLS[big][1])
    assert p.room.vnum == paths.PATHS[big].hall
    return out


def test_each_mentor_stands_in_his_hall(errors):
    for big, (_from, _way, name) in HALLS.items():
        hall = zones.world.rooms[paths.PATHS[big].hall]
        mentor = next(c for c in characters if isinstance(c, Npc) and c.room is hall and "mentor" in c.keywords)
        assert mentor.name == name and mentor.script is not None
    for p in paths.PATHS.values():                                   # 小路跟著大路的分館
        assert p.hall == paths.PATHS[p.parent or p.name].hall


@pytest.mark.parametrize("big, guild", [("戰士", SWORD), ("刺客", SWORD), ("元素", STAFF), ("神官", STAFF)])
def test_walk_in_and_choose(errors, big, guild):
    p = player(guild=guild, big=big)
    name = HALLS[big][2]
    assert f"{name}說：『Ming，想走{big}這條路的話，說「{big}」就行。』" in walk_in(p, big)
    out = do(p, f"say {big}")
    first = paths.PATHS[big].skills[0][1]
    assert f"你學會了【{skills.SKILLS[first].name}】！" in out
    assert f"{name}說：『好，從今天起你就走這條路了。學會的本事，用 skills 看。』" in out
    assert p.paths == [big] and save.load_data("Ming")["paths"] == [big]     # 選好就存檔
    assert errors == []


def test_no_greeting_for_others(errors):
    for p, why in ((player(level=9), "還沒 10 級"), (player(guild=STAFF, name="Hua"), "不是劍之公會")):
        assert "老教頭說" not in walk_in(p, "戰士"), why
    p = player(name="Kai")
    paths.choose(p, "戰士")
    assert "老教頭說" not in walk_in(p, "戰士")                        # 已經選了
    assert errors == []


@pytest.mark.parametrize("level, guild, want", [
    (9, SWORD, "你還太嫩了。大路要 10 級，小路要 40 級才能選。"),
    (10, STAFF, "你不是劍之公會的人，這裡教不了你。"),
])
def test_refusals(errors, level, guild, want):
    p = player(level=level, guild=guild)
    walk_in(p, "戰士")
    assert f"老教頭說：『{want}』" in do(p, "say 戰士") and p.paths == []
    assert errors == []


def test_changing_paths_asks_twice_and_costs_gold(errors):
    p = player(level=20)
    paths.choose(p, "刺客")
    walk_in(p, "戰士")
    cost = paths.change_cost(20)
    assert f"換路要 {cost} 金幣，舊路的本事會全部忘掉。確定的話，再說一次「戰士」。" in do(p, "say 戰士")
    assert "老教頭說：『換路的錢不夠，存夠了再來。』" in do(p, "say 戰士")
    p.gold = cost + 5
    do(p, "say 戰士")
    out = do(p, "say 戰士")
    assert "你忘掉了【背刺】。" in out and "你學會了【猛力斬】！" in out and "老教頭說：『舊的就忘了吧，從頭來過。』" in out
    assert (p.paths, p.gold) == (["戰士"], 5)
    assert errors == []


def test_small_paths_at_40(errors):
    p = player(level=40)
    paths.choose(p, "戰士")
    out = walk_in(p, "戰士")
    assert "老教頭說：『你可以往下走「巨武」（雙手武器，一次打一群）或「盾衛」（拿盾，耐打、保護別人），想好了就說。』" in out
    assert "你學會了【挑釁】！" in do(p, "say 盾衛") and p.paths == ["戰士", "盾衛"]
    q = player(level=40, name="Hua")
    paths.choose(q, "刺客")
    walk_in(q, "戰士")
    assert "老教頭說：『這兩條小路接在戰士下面，你得先走戰士這條路。』" in do(q, "say 巨武")
    assert errors == []


def test_other_words_are_ignored(errors):
    p = player()
    walk_in(p, "戰士")
    assert "老教頭說" not in do(p, "say 你好")
    assert errors == []
