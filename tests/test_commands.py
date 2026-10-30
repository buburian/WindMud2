from pathlib import Path

import pytest

import mud.commands as commands
from area_helpers import make_exit, make_room, write_area
from mud import area
from mud.characters import SEX_NEUTRAL, characters
from mud.commands import system
from mud.config import ENCODING
from mud.npcs import Npc
from mud.players import Player

AREAS = Path(__file__).resolve().parent.parent / "areas"

# 站在房間 101 用 look 看到的樣子（不含其他角色）
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


def cast(ch, arg):
    pass


def channel(ch, arg):
    pass


def chat(ch, arg):
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
    ming = Player("小明", FakeWriter())
    assert commands.command(ming, "q") is False
    assert saved == ["小明"]
    assert ming.writer.data == "再見。\r\n".encode(ENCODING)


def test_unknown_command():
    ming = Player("小明", FakeWriter())
    assert commands.command(ming, "xyz") is True
    assert ming.writer.data == "什麼？\r\nHP100> ".encode(ENCODING)


@pytest.fixture
def online():
    # 小明、阿華、Bob 都在線，站在同一個房間
    ps = {}
    for name in ("小明", "阿華", "Bob"):
        ps[name] = Player(name, FakeWriter())
        characters.append(ps[name])
    yield ps
    characters.clear()


def test_tell_reaches_only_target_in_green(online):
    ming, hua, bob = online["小明"], online["阿華"], online["Bob"]
    commands.command(ming, "tell 阿華 晚點見")
    assert ming.writer.data == "\x1b[32;1m你告訴阿華：晚點見\x1b[0m\r\nHP100> ".encode(ENCODING)
    assert hua.writer.data == "\r\n\x1b[32;1m小明告訴你：晚點見\x1b[0m\r\nHP100> ".encode(ENCODING)
    assert bob.writer.data == b""


def test_tell_english_name_ignores_case(online):
    commands.command(online["小明"], "t bob hi")
    assert "小明告訴你：hi".encode(ENCODING) in online["Bob"].writer.data


def test_tell_unknown_target(online):
    ming = online["小明"]
    commands.command(ming, "tell 小美 你好")
    assert ming.writer.data == "沒有找到你想說話的對象。\r\nHP100> ".encode(ENCODING)


def test_reply_goes_back_to_last_teller(online):
    ming, hua = online["小明"], online["阿華"]
    commands.command(ming, "tell 阿華 晚點見")
    ming.writer.data = hua.writer.data = b""
    commands.command(hua, "r 好啊")
    assert hua.writer.data == "\x1b[32;1m你告訴小明：好啊\x1b[0m\r\nHP100> ".encode(ENCODING)
    assert ming.writer.data == "\r\n\x1b[32;1m阿華告訴你：好啊\x1b[0m\r\nHP100> ".encode(ENCODING)


def test_reply_without_teller_or_after_teller_left(online):
    ming, hua = online["小明"], online["阿華"]
    commands.command(hua, "reply 嗨")
    assert hua.writer.data == "找不到你想回答的對象。\r\nHP100> ".encode(ENCODING)
    commands.command(ming, "tell 阿華 晚點見")
    characters.remove(ming)                      # 小明離線了
    hua.writer.data = b""
    commands.command(hua, "reply 嗨")
    assert hua.writer.data == "找不到你想回答的對象。\r\nHP100> ".encode(ENCODING)


def test_reply_missing_message(online):
    ming, hua = online["小明"], online["阿華"]
    commands.command(ming, "tell 阿華 晚點見")
    hua.writer.data = b""
    commands.command(hua, "reply")
    assert hua.writer.data == "你想回答些什麼呢？\r\nHP100> ".encode(ENCODING)


def test_tell_missing_message(online):
    ming = online["小明"]
    for line in ("tell", "tell 阿華"):
        ming.writer.data = b""
        commands.command(ming, line)
        assert ming.writer.data == "你想要告訴誰些什麼呢？\r\nHP100> ".encode(ENCODING)


@pytest.fixture
def world(online):
    # 三個人都站在房間 101
    area.load(AREAS)
    return online


@pytest.fixture
def dog(world):
    # 一隻野狗（NPC）也站在房間 101；online 結束時會一起清掉
    npc = Npc("野狗", SEX_NEUTRAL, 101)
    characters.append(npc)
    return npc


def test_look_shows_room_and_others(world):
    ming = world["小明"]
    commands.command(ming, "look")
    want = ROOM1 + "阿華站在這裡。\r\nBob站在這裡。\r\nHP100> "
    assert ming.writer.data == want.encode(ENCODING)


def test_walk_north_then_follow(world):
    ming, hua, bob = world["小明"], world["阿華"], world["Bob"]
    commands.command(ming, "n")
    assert ming.room == 102
    assert hua.writer.data == "\r\n小明朝北離開。\r\nHP100> ".encode(ENCODING)
    assert bob.writer.data == "\r\n小明朝北離開。\r\nHP100> ".encode(ENCODING)
    # 自己走過去之後自動 look：新房間只有自己，出口只有南
    assert ming.writer.data == (
        "\x1b[32;1m【\x1b[33;1m測試房間（北）\x1b[32;1m】\x1b[0m\r\n"
        "\x1b[32;1m【出口： \x1b[36;1m南\x1b[32;1m】\x1b[0m\r\n"
        "這是測試區域北邊的房間。\r\n往南可以回到剛才的房間。\r\n"
        "HP100> "
    ).encode(ENCODING)

    ming.writer.data = bob.writer.data = b""
    commands.command(hua, "north")               # 阿華跟上去
    assert ming.writer.data == "\r\n阿華從南邊走了過來。\r\nHP100> ".encode(ENCODING)
    assert bob.writer.data == "\r\n阿華朝北離開。\r\nHP100> ".encode(ENCODING)
    assert "小明站在這裡。".encode(ENCODING) in hua.writer.data


def test_no_exit_that_way(world):
    ming = world["小明"]
    commands.command(ming, "south")
    assert ming.writer.data == "那裡不能走。\r\nHP100> ".encode(ENCODING)
    assert ming.room == 101


@pytest.mark.parametrize("line", ["look n", "look no", "look north", "l n"])
def test_look_direction_shows_exit_description(world, line):
    ming = world["小明"]
    commands.command(ming, line)
    assert ming.writer.data == "往北看，是測試區域北邊的房間。\r\nHP100> ".encode(ENCODING)


@pytest.mark.parametrize("line", ["look 牌子", "look sign", "look SIGN"])
def test_look_extra_description(world, line):
    ming = world["小明"]
    commands.command(ming, line)
    # 描述裡的 {R…{x 會變成亮紅色
    want = "牌子上寫著：這裡是測試區域。牆上有一行\x1b[31;1m紅色\x1b[0m的字。\r\nHP100> "
    assert ming.writer.data == want.encode(ENCODING)


@pytest.mark.parametrize("line, want", [
    ("look s", "那裡沒有什麼特別的東西。"),    # 101 往南沒有出口
    ("look 牌", "在這裡找不到你要看的東西。"),  # 名字要整個字一樣
    ("look x", "在這裡找不到你要看的東西。"),
])
def test_look_nothing_there(world, line, want):
    ming = world["小明"]
    commands.command(ming, line)
    assert ming.writer.data == f"{want}\r\nHP100> ".encode(ENCODING)


def test_sign_is_only_in_its_own_room(world):
    ming = world["小明"]
    commands.command(ming, "n")
    ming.writer.data = b""
    commands.command(ming, "look 牌子")
    assert ming.writer.data == "在這裡找不到你要看的東西。\r\nHP100> ".encode(ENCODING)


def test_look_direction_without_description(online, tmp_path):
    # 有出口但沒寫描述（make_room 的出口描述是空字串）
    write_area(tmp_path, "a.json", [make_room(1, north=2), make_room(2)])
    area.load(tmp_path)
    ming = online["小明"]
    commands.command(ming, "look n")
    assert ming.writer.data == "那裡沒有什麼特別的東西。\r\nHP100> ".encode(ENCODING)


def test_things_come_before_directions(online, tmp_path):
    # 照 C 版：名字跟方向撞在一起時，先看東西
    r = make_room(1)
    r["exits"]["north"] = make_exit(1, "往北看。\n")
    r["extra_descriptions"] = [{"keywords": "north 北牆", "description": "北牆上刻著字。\n"}]
    write_area(tmp_path, "a.json", [r])
    area.load(tmp_path)
    ming = online["小明"]
    commands.command(ming, "look north")
    assert ming.writer.data == "北牆上刻著字。\r\nHP100> ".encode(ENCODING)


def test_look_shows_npc(world, dog):
    # NPC 跟玩家一樣，會列在房間裡
    ming = world["小明"]
    commands.command(ming, "look")
    want = ROOM1 + "阿華站在這裡。\r\nBob站在這裡。\r\n野狗站在這裡。\r\nHP100> "
    assert ming.writer.data == want.encode(ENCODING)


def test_npc_can_walk(world, dog):
    # NPC 也能下指令：走到北邊，原本房間的玩家都看到它離開
    assert commands.command(dog, "north") is True
    assert dog.room == 102
    for p in world.values():
        assert p.writer.data == "\r\n野狗朝北離開。\r\nHP100> ".encode(ENCODING)
