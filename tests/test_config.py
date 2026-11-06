"""config 指令（玩家角色手冊「設定」）：列出、開關 autoloot、分頁每頁幾行、存檔。訊息照 C 版 do_config、do_pagelen。"""
import re

import pytest

import mud.commands as commands
from area_helpers import make_area, make_room, write_json
from mud import save, zones
from mud.characters import characters
from mud.color import colorize
from mud.config import ENCODING, PAGE_LINES
from mud.npcs import Npc
from mud.players import Player
from player_helpers import make_player_file


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


@pytest.fixture
def ming(tmp_path, monkeypatch):
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path / "players")
    write_json(tmp_path, "a.json", make_area("a.json", [make_room(1)], 100))
    zones.load(tmp_path)
    make_player_file("Ming")
    p = save.player_from(save.load_data("Ming"), FakeWriter())
    characters.append(p)
    yield p
    characters.clear()
    zones.stop()


def do(p, line):
    p.writer.data = b""
    commands.command(p, line)
    return re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))


def reply(p, line):
    """指令的回覆（拿掉最後的空行和 prompt）。"""
    return do(p, line).rsplit("\r\n\r\n", 1)[0]


def test_config_is_co():
    assert commands.command_name("co") == "config"


def test_config_lists_the_settings(ming):
    assert ming.autoloot is False and ming.page_lines == PAGE_LINES          # 預設：自動拾取關、每頁 20 行（照 C 版）
    assert reply(ming, "config") == ("[ 關鍵字   ] 選項說明\r\n"
                                     "[-autoloot ] 你放棄自動搜刮屍體物品。\r\n"
                                     "[ LINES 20 ] 每頁 20 行暫停一次（config lines 數字，19～60）。")
    ming.autoloot = True
    assert "[+AUTOLOOT ] 你將會自動搜刮屍體物品。" in reply(ming, "config")


def test_config_colors(ming):
    ming.writer.data = b""
    commands.command(ming, "config")
    raw = ming.writer.data.decode(ENCODING)
    assert colorize("{M[ 關鍵字   ]") in raw and colorize("{c[-autoloot ]") in raw
    ming.autoloot = True
    ming.writer.data = b""
    commands.command(ming, "config")
    assert colorize("{C[+AUTOLOOT ]") in ming.writer.data.decode(ENCODING)


def test_toggle_autoloot(ming):
    assert reply(ming, "config +autoloot") == "Autoloot 已設定成開啟。" and ming.autoloot is True
    assert reply(ming, "config -AutoLoot") == "Autoloot 已設定成關閉。" and ming.autoloot is False   # 不分大小寫
    assert reply(ming, "co +autoloot") == "Autoloot 已設定成開啟。"


@pytest.mark.parametrize("arg, want", [
    ("autoloot", "想要開啟或關閉什麼選項?"),          # 沒有 + 或 -（照 C 版）
    ("+xyz", "有這個選項嗎？"),
    ("+", "有這個選項嗎？"),
])
def test_config_mistakes(ming, arg, want):
    assert reply(ming, "config " + arg) == want and ming.autoloot is False


def test_page_lines(ming):
    assert reply(ming, "config lines 30") == "每頁每【30】行暫停一次。" and ming.page_lines == 30
    assert reply(ming, "config lines") == "每頁每【20】行暫停一次。" and ming.page_lines == 20       # 不打數字是 20
    assert reply(ming, "config lines 19") == "每頁每【19】行暫停一次。" and ming.page_lines == 19
    assert reply(ming, "config lines 18") == "一頁不允許少於【19】行。" and ming.page_lines == 19    # 太少不改
    assert reply(ming, "config lines 61") == "現在應該沒有螢幕有超過【60】行的吧!!" and ming.page_lines == 60   # 太多設成 60
    assert reply(ming, "config LINES 60") == "每頁每【60】行暫停一次。"
    assert reply(ming, "config lines abc") == "要打數字，例如 config lines 30。" and ming.page_lines == 60
    assert reply(ming, "config lines ①") == "要打數字，例如 config lines 30。"     # 坑：isdigit() 認得、int() 不認得的字
    assert reply(ming, "config lines ３０") == "每頁每【30】行暫停一次。"          # 全形數字照樣可以


def test_settings_are_saved(ming):
    do(ming, "config +autoloot")
    do(ming, "config lines 40")
    save.save_player(ming)
    data = save.load_data("Ming")
    assert (data["autoloot"], data["page_lines"]) == (True, 40)
    back = save.player_from(data, FakeWriter())
    assert (back.autoloot, back.page_lines) == (True, 40)
    old = {k: v for k, v in data.items() if k not in ("autoloot", "page_lines")}   # 舊存檔沒有：預設
    back = save.player_from(old, FakeWriter())
    assert (back.autoloot, back.page_lines) == (False, PAGE_LINES)


def test_mobiles_have_no_settings(ming):
    dog = Npc("野狗", 0, ming.room)
    said = []
    dog.send = said.append
    commands.command(dog, "config")
    assert said[0] == "你沒有可以設定的東西。\n"


def test_players_without_attributes_still_have_settings():
    p = Player("Ming", FakeWriter(), None)
    assert p.autoloot is False and p.page_lines == PAGE_LINES
