import json
from pathlib import Path

import pytest

import mud.commands as commands
from mud import area
from mud.commands import system
from mud.config import ENCODING
from mud.players import Player, players

AREAS = Path(__file__).resolve().parent.parent / "areas"

# 站在房間 101 用 look 看到的樣子（不含其他玩家）
ROOM1 = (
    "\x1b[32;1m【\x1b[33;1m測試房間（南）\x1b[32;1m】\x1b[0m\r\n"
    "\x1b[32;1m【出口： \x1b[36;1m北\x1b[32;1m】\x1b[0m\r\n"
    "這是測試區域南邊的房間。\r\n往北可以走到另一個房間。\r\n"
)


class FakeWriter:
    """假的連線：只把送出的 bytes 收起來。"""

    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


def cast(writer, name, arg):
    pass


def channel(writer, name, arg):
    pass


def chat(writer, name, arg):
    pass


def test_first_command_starting_with_input_wins(monkeypatch):
    monkeypatch.setattr(commands, "COMMANDS", [("cast", cast), ("channel", channel), ("chat", chat)])
    assert commands.find("c") is cast
    assert commands.find("ch") is channel
    assert commands.find("cha") is channel
    assert commands.find("chat") is chat
    assert commands.find("x") is None


def test_order_decides_priority(monkeypatch):
    monkeypatch.setattr(commands, "COMMANDS", [("chat", chat), ("channel", channel)])
    assert commands.find("ch") is chat
    assert commands.find("chan") is channel


def test_real_table():
    assert commands.find("n") is system.do_north
    assert commands.find("s") is system.do_south
    assert commands.find("l") is system.do_look
    assert commands.find("c") is system.do_chat
    assert commands.find("t") is system.do_tell
    assert commands.find("r") is system.do_reply
    assert commands.find("q") is system.do_quit


def test_quit_abbreviation_saves_and_disconnects(monkeypatch):
    saved = []
    monkeypatch.setattr(system, "save_player", saved.append)
    w = FakeWriter()
    assert commands.command(w, "小明", "q") is False
    assert saved == ["小明"]
    assert w.data == "再見。\r\n".encode(ENCODING)


def test_unknown_command():
    w = FakeWriter()
    assert commands.command(w, "小明", "xyz") is True
    assert w.data == "什麼？\r\nHP100> ".encode(ENCODING)


@pytest.fixture
def online():
    # 小明、阿華、Bob 都在線
    ws = {}
    for name in ("小明", "阿華", "Bob"):
        ws[name] = FakeWriter()
        players[ws[name]] = Player(name)
    yield ws
    players.clear()


def test_tell_reaches_only_target_in_green(online):
    ming, hua, bob = online["小明"], online["阿華"], online["Bob"]
    commands.command(ming, "小明", "tell 阿華 晚點見")
    assert ming.data == "\x1b[32;1m你告訴阿華：晚點見\x1b[0m\r\nHP100> ".encode(ENCODING)
    assert hua.data == "\r\n\x1b[32;1m小明告訴你：晚點見\x1b[0m\r\nHP100> ".encode(ENCODING)
    assert bob.data == b""


def test_tell_english_name_ignores_case(online):
    commands.command(online["小明"], "小明", "t bob hi")
    assert "小明告訴你：hi".encode(ENCODING) in online["Bob"].data


def test_tell_unknown_target(online):
    ming = online["小明"]
    commands.command(ming, "小明", "tell 小美 你好")
    assert ming.data == "沒有找到你想說話的對象。\r\nHP100> ".encode(ENCODING)


def test_reply_goes_back_to_last_teller(online):
    ming, hua = online["小明"], online["阿華"]
    commands.command(ming, "小明", "tell 阿華 晚點見")
    ming.data = hua.data = b""
    commands.command(hua, "阿華", "r 好啊")
    assert hua.data == "\x1b[32;1m你告訴小明：好啊\x1b[0m\r\nHP100> ".encode(ENCODING)
    assert ming.data == "\r\n\x1b[32;1m阿華告訴你：好啊\x1b[0m\r\nHP100> ".encode(ENCODING)


def test_reply_without_teller_or_after_teller_left(online):
    ming, hua = online["小明"], online["阿華"]
    commands.command(hua, "阿華", "reply 嗨")
    assert hua.data == "找不到你想回答的對象。\r\nHP100> ".encode(ENCODING)
    commands.command(ming, "小明", "tell 阿華 晚點見")
    del players[ming]                            # 小明離線了
    hua.data = b""
    commands.command(hua, "阿華", "reply 嗨")
    assert hua.data == "找不到你想回答的對象。\r\nHP100> ".encode(ENCODING)


def test_reply_missing_message(online):
    ming, hua = online["小明"], online["阿華"]
    commands.command(ming, "小明", "tell 阿華 晚點見")
    hua.data = b""
    commands.command(hua, "阿華", "reply")
    assert hua.data == "你想回答些什麼呢？\r\nHP100> ".encode(ENCODING)


def test_tell_missing_message(online):
    ming = online["小明"]
    for line in ("tell", "tell 阿華"):
        ming.data = b""
        commands.command(ming, "小明", line)
        assert ming.data == "你想要告訴誰些什麼呢？\r\nHP100> ".encode(ENCODING)


@pytest.fixture
def world(online):
    # 三個人都站在房間 101
    area.load(AREAS)
    return online


def test_look_shows_room_and_others(world):
    ming = world["小明"]
    commands.command(ming, "小明", "look")
    want = ROOM1 + "阿華站在這裡。\r\nBob站在這裡。\r\nHP100> "
    assert ming.data == want.encode(ENCODING)


def test_walk_north_then_follow(world):
    ming, hua, bob = world["小明"], world["阿華"], world["Bob"]
    commands.command(ming, "小明", "n")
    assert players[ming].room == 102
    assert hua.data == "\r\n小明朝北離開。\r\nHP100> ".encode(ENCODING)
    assert bob.data == "\r\n小明朝北離開。\r\nHP100> ".encode(ENCODING)
    # 自己走過去之後自動 look：新房間只有自己，出口只有南
    assert ming.data == (
        "\x1b[32;1m【\x1b[33;1m測試房間（北）\x1b[32;1m】\x1b[0m\r\n"
        "\x1b[32;1m【出口： \x1b[36;1m南\x1b[32;1m】\x1b[0m\r\n"
        "這是測試區域北邊的房間。\r\n往南可以回到剛才的房間。\r\n"
        "HP100> "
    ).encode(ENCODING)

    ming.data = bob.data = b""
    commands.command(hua, "阿華", "north")       # 阿華跟上去
    assert ming.data == "\r\n阿華從南邊走了過來。\r\nHP100> ".encode(ENCODING)
    assert bob.data == "\r\n阿華朝北離開。\r\nHP100> ".encode(ENCODING)
    assert "小明站在這裡。".encode(ENCODING) in hua.data


def test_no_exit_that_way(world):
    ming = world["小明"]
    commands.command(ming, "小明", "south")
    assert ming.data == "那裡不能走。\r\nHP100> ".encode(ENCODING)
    assert players[ming].room == 101


@pytest.mark.parametrize("line", ["look n", "look no", "look north", "l n"])
def test_look_direction_shows_exit_description(world, line):
    ming = world["小明"]
    commands.command(ming, "小明", line)
    assert ming.data == "往北看，是測試區域北邊的房間。\r\nHP100> ".encode(ENCODING)


@pytest.mark.parametrize("line", ["look 牌子", "look sign", "look SIGN"])
def test_look_extra_description(world, line):
    ming = world["小明"]
    commands.command(ming, "小明", line)
    # 描述裡的 {R…{x 會變成亮紅色
    assert ming.data == "牌子上寫著：這裡是測試區域。牆上有一行\x1b[31;1m紅色\x1b[0m的字。\r\nHP100> ".encode(ENCODING)


@pytest.mark.parametrize("line, want", [
    ("look s", "那裡沒有什麼特別的東西。"),    # 101 往南沒有出口
    ("look 牌", "在這裡找不到你要看的東西。"),  # 名字要整個字一樣
    ("look x", "在這裡找不到你要看的東西。"),
])
def test_look_nothing_there(world, line, want):
    ming = world["小明"]
    commands.command(ming, "小明", line)
    assert ming.data == f"{want}\r\nHP100> ".encode(ENCODING)


def test_sign_is_only_in_its_own_room(world):
    ming = world["小明"]
    commands.command(ming, "小明", "n")
    ming.data = b""
    commands.command(ming, "小明", "look 牌子")
    assert ming.data == "在這裡找不到你要看的東西。\r\nHP100> ".encode(ENCODING)


def test_look_direction_without_description(online, tmp_path):
    # 有出口但沒寫描述
    data = {"area": {"header": {"area_number": 100}}, "rooms": [
        {"vnum": 1, "name": "甲", "description": "", "room_flags": 0, "sector": 0, "extra_descriptions": [],
         "exits": {"north": {"to_room": 2, "description": ""}}},
        {"vnum": 2, "name": "乙", "description": "", "room_flags": 0, "sector": 0, "extra_descriptions": [],
         "exits": {}},
    ]}
    (tmp_path / "a.json").write_text(json.dumps(data), encoding="utf-8")
    area.load(tmp_path)
    ming = online["小明"]
    commands.command(ming, "小明", "look n")
    assert ming.data == "那裡沒有什麼特別的東西。\r\nHP100> ".encode(ENCODING)


def test_things_come_before_directions(online, tmp_path):
    # 照 C 版：名字跟方向撞在一起時，先看東西
    data = {"area": {"header": {"area_number": 100}}, "rooms": [
        {"vnum": 1, "name": "甲", "description": "", "room_flags": 0, "sector": 0,
         "extra_descriptions": [{"keywords": "north 北牆", "description": "北牆上刻著字。\n"}],
         "exits": {"north": {"to_room": 1, "description": "往北看。\n"}}},
    ]}
    (tmp_path / "a.json").write_text(json.dumps(data), encoding="utf-8")
    area.load(tmp_path)
    ming = online["小明"]
    commands.command(ming, "小明", "look north")
    assert ming.data == "北牆上刻著字。\r\nHP100> ".encode(ENCODING)
