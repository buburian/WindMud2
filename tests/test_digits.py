"""特殊的數字字元（Big5 打得出來的「①…⑨」「⑴…⑼」）：isdigit() 認得、int() 不認得，以前會丟錯讓玩家斷線。一律用 isdecimal() 檢查（CLAUDE.md 記的坑）。"""
import re

import pytest

import mud.commands as commands
from area_helpers import make_area, make_object, make_room, write_json
from mud import names, save, zones
from mud.characters import characters
from mud.config import ENCODING
from player_helpers import make_player_file


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


@pytest.fixture
def ming(tmp_path, monkeypatch):
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path / "players")
    write_json(tmp_path, "a.json", make_area("a.json", [make_room(1)], 100, objects=[make_object(1)]))   # 物品 101：oload 才查得到等級
    zones.load(tmp_path)
    make_player_file("Ming")
    p = save.player_from(save.load_data("Ming"), FakeWriter())
    p.imm, p.points = True, 1
    characters.append(p)
    yield p
    characters.clear()
    zones.stop()


@pytest.mark.parametrize("line, want", [
    ("kill ①.dog", "找不到你想攻擊的人。"),
    ("train str ①", "點數要寫 1 以上的整數。"),
    ("advance ming ①", "等級要是 1～100。"),
    ("oload ①", "用法：oload <號碼> [等級] [顏色]"),
    ("oload 101 ①", "等級要寫 1～100。"),
    ("ostat ②", "找不到這件物品。"),
    ("give ① coins ming", "你沒有這樣東西。"),
    ("config lines ①", "要打數字，例如 config lines 30。"),
])
def test_special_digits_do_not_disconnect(ming, line, want):
    assert commands.command(ming, line) is True
    assert re.sub(r"\x1b\[[0-9;]*m", "", ming.writer.data.decode(ENCODING)).startswith(want)


def test_number_argument():
    assert names.number_argument("①.dog") == (1, "①.dog") and names.number_argument("２.dog") == (2, "dog")   # 全形數字照樣可以
