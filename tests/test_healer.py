"""秋風城的行醫者（真的 areas/midgaard.json 和 midgaard/行醫者.lua）：1～10 級的玩家走進神殿祭壇，牠放餽贈給他。

招呼是腳本的 random(1, 2)、測試沒載入表情動作，所以只看餽贈那一句和身上的效果，不比整段畫面。
腳本出錯會被接住、只記 log，所以每個測試都看 scripts.report 有沒有被叫到（不然「沒有餽贈」可能只是腳本出錯）。
"""
import re
from pathlib import Path

import pytest

import mud.commands as commands
from mud import save, scripts, skills, stats, zones
from mud.characters import characters
from mud.config import ENCODING
from mud.npcs import Npc
from mud.players import Player

AREAS = Path(__file__).resolve().parent.parent / "areas"
HALL, ALTAR, HEALER = 3001, 3054, 3012     # 神殿大廳（往北是祭壇）、神殿祭壇、行醫者
GIFT_TEXT = "行醫者對你施展了【餽贈】。"


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


@pytest.fixture
def errors(tmp_path, monkeypatch):
    """載入真的 areas/；回傳腳本出錯的清單。"""
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path)
    found = []
    monkeypatch.setattr(scripts, "report", lambda r, msg: found.append(msg))
    zones.load(AREAS)
    altar = zones.world.rooms[ALTAR]
    assert any(isinstance(c, Npc) and c.vnum == HEALER and c.room is altar for c in characters)
    yield found
    characters.clear()
    zones.stop()


def player(level):
    """站在神殿大廳、有全部屬性的玩家。"""
    p = Player("Ming", FakeWriter(), zones.world.rooms[HALL])
    p.race, p.guild = stats.Race.HUMAN, stats.Guild.SWORD
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.skills = skills.starter(p.guild)
    stats.set_level(p, level)
    p.hp, p.mp, p.mv = p.panel["hp"], p.panel["mp"], p.panel["mv"]
    characters.append(p)
    return p


def walk_in(ch):
    """往北走進神殿祭壇，回傳看到的字。"""
    commands.command(ch, "n")
    assert ch.room is zones.world.rooms[ALTAR]
    if isinstance(ch, Player):
        return re.sub(r"\x1b\[[0-9;]*m", "", ch.writer.data.decode(ENCODING))
    return ""


@pytest.mark.parametrize("level", [1, 10])
def test_low_level_player_gets_gift(errors, level):
    p = player(level)
    out = walk_in(p)
    assert GIFT_TEXT in out
    assert [a.source for a in p.affects] == ["gift"]
    assert errors == []


def test_already_has_gift_is_not_cast_again(errors):
    """身上已經有餽贈（例如剛剛才拿到、走出去又走回來）：不再放，剩下的時間也不補滿（使用者要的，用 actor:has_affect）。"""
    p = player(1)
    walk_in(p)
    gift = p.affects[0]
    gift.ticks -= 100
    commands.command(p, "s")
    p.writer.data = b""
    out = walk_in(p)
    assert GIFT_TEXT not in out
    assert p.affects == [gift] and gift.ticks == gift.duration - 100
    assert errors == []


@pytest.mark.parametrize("level", [11, 50])
def test_level_11_and_up_gets_nothing(errors, level):
    p = player(level)
    out = walk_in(p)
    assert "餽贈" not in out
    assert p.affects == []
    assert errors == []


def test_mobile_walking_in_gets_nothing(errors):
    dog = Npc("野狗", 0, zones.world.rooms[HALL])
    characters.append(dog)
    walk_in(dog)
    assert dog.affects == []
    assert errors == []
