import re
from pathlib import Path

import pytest

import mud.commands as commands
from area_helpers import make_exit, make_room, write_area
from mud import stats, zones
from mud.characters import SEX_NEUTRAL, Position, characters
from mud.commands import system
from mud.config import ENCODING
from mud.npcs import Npc
from mud.players import Player

AREAS = Path(__file__).resolve().parent.parent / "areas"
ANY = Position.DEAD                 # 指令表的最低姿勢：什麼姿勢都能用
W, X = "\x1b[37;1m", "\x1b[0m"     # 亮白、回到原本顏色
MERCHANT = "一位測試商人/merchant/站在櫃檯後面。"   # areas/test.json 的生物 1 的 long
RABBIT = "一隻野兔/rabbit/在草叢裡跳來跳去。"          # areas/test.json 的生物 3（練功用，北邊房間 3 隻）

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
    monkeypatch.setattr(commands, "COMMANDS", [("cast", cast, ANY), ("channel", channel, ANY), ("chat", chat, ANY)])
    assert commands.find("c") is cast
    assert commands.find("ch") is channel
    assert commands.find("cha") is channel
    assert commands.find("chat") is chat
    assert commands.find("x") is None


def test_order_decides_priority(monkeypatch):
    monkeypatch.setattr(commands, "COMMANDS", [("chat", chat, ANY), ("channel", channel, ANY)])
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


def test_quit_abbreviation_disconnects():
    # 存檔在 server.handle() 的 finally（直接斷線也存），test_login.py 測
    ming = Player("小明", FakeWriter(), None)   # 用不到房間
    assert commands.command(ming, "q") is False
    assert ming.writer.data == "再見。\r\n".encode(ENCODING)


def test_unknown_command():
    ming = Player("小明", FakeWriter(), None)   # 用不到房間
    assert commands.command(ming, "xyz") is True
    assert ming.writer.data == "什麼？\r\n\r\n> ".encode(ENCODING)


@pytest.fixture
def online():
    # 小明、阿華、Bob 都在線；要站在房間裡的測試用 stand_in() 載入區域
    ps = {}
    for name in ("小明", "阿華", "Bob"):
        ps[name] = Player(name, FakeWriter(), None)
        characters.append(ps[name])
    yield ps
    characters.clear()


def test_tell_reaches_only_target_in_green(online):
    ming, hua, bob = online["小明"], online["阿華"], online["Bob"]
    commands.command(ming, "tell 阿華 晚點見")
    assert ming.writer.data == "\x1b[32;1m你告訴阿華：晚點見\x1b[0m\r\n\r\n> ".encode(ENCODING)
    assert hua.writer.data == "\r\n\x1b[32;1m小明告訴你：晚點見\x1b[0m\r\n\r\n> ".encode(ENCODING)
    assert bob.writer.data == b""


def test_tell_english_name_ignores_case(online):
    commands.command(online["小明"], "t bob hi")
    assert "小明告訴你：hi".encode(ENCODING) in online["Bob"].writer.data


def test_tell_unknown_target(online):
    ming = online["小明"]
    commands.command(ming, "tell 小美 你好")
    assert ming.writer.data == "沒有找到你想說話的對象。\r\n\r\n> ".encode(ENCODING)


def test_reply_goes_back_to_last_teller(online):
    ming, hua = online["小明"], online["阿華"]
    commands.command(ming, "tell 阿華 晚點見")
    ming.writer.data = hua.writer.data = b""
    commands.command(hua, "r 好啊")
    assert hua.writer.data == "\x1b[32;1m你告訴小明：好啊\x1b[0m\r\n\r\n> ".encode(ENCODING)
    assert ming.writer.data == "\r\n\x1b[32;1m阿華告訴你：好啊\x1b[0m\r\n\r\n> ".encode(ENCODING)


def test_reply_without_teller_or_after_teller_left(online):
    ming, hua = online["小明"], online["阿華"]
    commands.command(hua, "reply 嗨")
    assert hua.writer.data == "找不到你想回答的對象。\r\n\r\n> ".encode(ENCODING)
    commands.command(ming, "tell 阿華 晚點見")
    characters.remove(ming)                      # 小明離線了
    hua.writer.data = b""
    commands.command(hua, "reply 嗨")
    assert hua.writer.data == "找不到你想回答的對象。\r\n\r\n> ".encode(ENCODING)


def test_reply_missing_message(online):
    ming, hua = online["小明"], online["阿華"]
    commands.command(ming, "tell 阿華 晚點見")
    hua.writer.data = b""
    commands.command(hua, "reply")
    assert hua.writer.data == "你想回答些什麼呢？\r\n\r\n> ".encode(ENCODING)


def test_tell_missing_message(online):
    ming = online["小明"]
    for line in ("tell", "tell 阿華"):
        ming.writer.data = b""
        commands.command(ming, line)
        assert ming.writer.data == "你想要告訴誰些什麼呢？\r\n\r\n> ".encode(ENCODING)


@pytest.fixture
def world(online):
    # 三個人都站在房間 101
    stand_in(AREAS, online)
    return online


def stand_in(folder, online):
    """載入 folder 的區域，大家都站在世界的房間 101。"""
    zones.load(folder)
    for p in online.values():
        p.room = zones.world.rooms[101]


@pytest.fixture
def dog(world):
    # 一隻野狗（NPC）也站在房間 101；online 結束時會一起清掉
    npc = Npc("野狗", SEX_NEUTRAL, zones.world.rooms[101])
    characters.append(npc)
    return npc


def test_look_shows_room_and_others(world):
    ming = world["小明"]
    commands.command(ming, "look")
    # 房間描述後空一行再列其他人，亮白（使用者定的）
    # 生物先（areas/test.json 的 M 把測試商人放在這裡，站著就顯示 long）、玩家後
    want = ROOM1 + "\r\n" + W + MERCHANT + X + "\r\n" + W + "阿華站在這裡。" + X + "\r\n" + W + "Bob站在這裡。" + X + "\r\n\r\n> "
    assert ming.writer.data == want.encode(ENCODING)


def test_walk_north_then_follow(world):
    ming, hua, bob = world["小明"], world["阿華"], world["Bob"]
    commands.command(ming, "n")
    assert ming.room.vnum == 102
    assert hua.writer.data == "\r\n小明朝北離開。\r\n\r\n> ".encode(ENCODING)
    assert bob.writer.data == "\r\n小明朝北離開。\r\n\r\n> ".encode(ENCODING)
    # 自己走過去之後自動 look：新房間有三隻練功用的野兔（沒有別的玩家），出口只有南
    assert ming.writer.data == (
        "\x1b[32;1m【\x1b[33;1m測試房間（北）\x1b[32;1m】\x1b[0m\r\n"
        "\x1b[32;1m【出口： \x1b[36;1m南\x1b[32;1m】\x1b[0m\r\n"
        "這是測試區域北邊的房間。\r\n往南可以回到剛才的房間。\r\n"
        "\r\n" + (W + RABBIT + X + "\r\n") * 3 +
        "\r\n> "                                  # 有訊息：prompt 前空一行
    ).encode(ENCODING)

    ming.writer.data = bob.writer.data = b""
    commands.command(hua, "north")               # 阿華跟上去
    assert ming.writer.data == "\r\n阿華從南邊走了過來。\r\n\r\n> ".encode(ENCODING)
    assert bob.writer.data == "\r\n阿華朝北離開。\r\n\r\n> ".encode(ENCODING)
    assert "小明站在這裡。".encode(ENCODING) in hua.writer.data


def test_no_exit_that_way(world):
    ming = world["小明"]
    commands.command(ming, "south")
    assert ming.writer.data == "那裡不能走。\r\n\r\n> ".encode(ENCODING)
    assert ming.room.vnum == 101


@pytest.mark.parametrize("line", ["look n", "look no", "look north", "l n"])
def test_look_direction_shows_exit_description(world, line):
    # 101 往北有木門（重置 D 讓它開著）：描述後面接著說門的狀態
    ming = world["小明"]
    commands.command(ming, line)
    assert ming.writer.data == "往北看，是測試區域北邊的房間。\r\n木門是開著的。\r\n\r\n> ".encode(ENCODING)


@pytest.mark.parametrize("line", ["look 牌子", "look sign", "look SIGN"])
def test_look_extra_description(world, line):
    ming = world["小明"]
    commands.command(ming, line)
    # 描述裡的 {R…{x 會變成亮紅色
    want = "牌子上寫著：這裡是測試區域。牆上有一行\x1b[31;1m紅色\x1b[0m的字。\r\n\r\n> "
    assert ming.writer.data == want.encode(ENCODING)


@pytest.mark.parametrize("line, want", [
    ("look s", "那裡沒有什麼特別的東西。"),    # 101 往南沒有出口
    ("look 牌", "在這裡找不到你要看的東西。"),  # 名字要整個字一樣
    ("look x", "在這裡找不到你要看的東西。"),
])
def test_look_nothing_there(world, line, want):
    ming = world["小明"]
    commands.command(ming, line)
    assert ming.writer.data == f"{want}\r\n\r\n> ".encode(ENCODING)


def test_sign_is_only_in_its_own_room(world):
    ming = world["小明"]
    commands.command(ming, "n")
    ming.writer.data = b""
    commands.command(ming, "look 牌子")
    assert ming.writer.data == "在這裡找不到你要看的東西。\r\n\r\n> ".encode(ENCODING)


def test_look_direction_without_description(online, tmp_path):
    # 有出口但沒寫描述（make_room 的出口描述是空字串）
    write_area(tmp_path, "a.json", [make_room(1, north=2), make_room(2)])
    stand_in(tmp_path, online)
    ming = online["小明"]
    commands.command(ming, "look n")
    assert ming.writer.data == "那裡沒有什麼特別的東西。\r\n\r\n> ".encode(ENCODING)


def test_things_come_before_directions(online, tmp_path):
    # 照 C 版：名字跟方向撞在一起時，先看東西
    r = make_room(1)
    r["exits"]["north"] = make_exit(1, "往北看。\n")
    r["extra_descriptions"] = [{"keywords": "north 北牆", "description": "北牆上刻著字。\n"}]
    write_area(tmp_path, "a.json", [r])
    stand_in(tmp_path, online)
    ming = online["小明"]
    commands.command(ming, "look north")
    assert ming.writer.data == "北牆上刻著字。\r\n\r\n> ".encode(ENCODING)


def test_look_shows_npc(world, dog):
    # NPC 也會列在房間裡，而且排在玩家前面（使用者定的：先生物、再玩家、最後地上的物品）
    ming = world["小明"]
    commands.command(ming, "look")
    want = (ROOM1 + "\r\n" + W + MERCHANT + X + "\r\n" + W + "野狗站在這裡。" + X + "\r\n" + W + "阿華站在這裡。" + X + "\r\n"
            + W + "Bob站在這裡。" + X + "\r\n\r\n> ")
    assert ming.writer.data == want.encode(ENCODING)


def test_npc_can_walk(world, dog):
    # NPC 也能下指令：走到北邊，原本房間的玩家都看到它離開
    assert commands.command(dog, "north") is True
    assert dog.room.vnum == 102
    for p in world.values():
        assert p.writer.data == "\r\n野狗朝北離開。\r\n\r\n> ".encode(ENCODING)


# ---- 有屬性的玩家：prompt 和 score（使用者選的樣子） ----

def stat_player(race="orc", guild="phys"):
    p = Player("Zzqa", FakeWriter(), None)
    p.race, p.guild = stats.Race(race), stats.Guild(guild)
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    stats.recompute(p)
    p.hp, p.mp, p.mv = p.panel["hp"], p.panel["mp"], p.panel["mv"]
    return p


def test_prompt_shows_hp_mp_mv_colored_by_how_much_is_left():
    # 現在的值：超過 2/3 綠、超過 1/3 黃、其他紅；上限是一般顏色
    p = stat_player()
    p.hp, p.mv = p.panel["hp"] * 0.25, p.panel["mv"] * 0.5          # 62 的 1/4、39 的 1/2
    assert p.prompt() == "<HP \x1b[31;1m16\x1b[0m/62 MP \x1b[32;1m26\x1b[0m/26 MV \x1b[33;1m20\x1b[0m/39> "
    assert commands.command(p, "xyz") is True
    assert p.writer.data == ("什麼？\r\n\r\n" + p.prompt()).encode(ENCODING)   # 指令跑完補的也是它


def test_prompt_without_stats_is_plain():
    assert Player("小明", FakeWriter(), None).prompt() == "> "


def test_score_layout():
    p = stat_player()
    p.hp = p.panel["hp"] * 0.25
    commands.command(p, "sc")
    text = p.writer.data.decode(ENCODING)
    rule = "=" * 52
    assert re.sub(r"\x1b\[[0-9;]*m", "", text) == "\r\n".join([
        rule,
        " 【Zzqa】 獸人｜劍之公會｜等級 1｜經驗 0/100｜男",       # 經驗：這一級累積的 / 升級要的
        rule,
        " 主屬性  力量 14  智慧 11  知識 11  體質 12  敏捷 12",
        "",
        " HP  [=====---------------]     16 / 62",
        " MP  [====================]     26 / 26",
        " MV  [====================]     39 / 39",
        "",
        " 攻擊  物理傷害   4   法術傷害   0   命中      16",
        "       爆擊率     8   爆擊傷害   4   攻速      22",
        " 防禦  閃躲      11   物理抗性   8   法術抗性  15",
        "       龍焰抗性   0   AC         0",
        rule,
        "",
        p.prompt().replace("\x1b[32;1m", "").replace("\x1b[31;1m", "").replace("\x1b[0m", ""),
    ])
    assert "\x1b[30;1m法術傷害   0\x1b[0m" in text          # 劍之公會用不到法術傷害：整格變暗
    assert "\x1b[31;1m=====\x1b[30;1m---------------\x1b[0m" in text   # HP 條：紅色的滿格、暗灰的空格


def test_score_shows_exp_until_max_level():
    p = stat_player()
    p.exp = 34.6
    commands.command(p, "sc")
    assert "｜等級 1｜經驗 35/100｜男" in re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))
    p.writer.data = b""
    p.level = stats.MAX_LEVEL                       # 滿等不再拿經驗，不顯示
    commands.command(p, "sc")
    assert "｜等級 100｜男" in re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))


def test_score_without_stats():
    ming = Player("小明", FakeWriter(), None)
    commands.command(ming, "score")
    assert ming.writer.data == "你沒有屬性可以看。\r\n\r\n> ".encode(ENCODING)


def test_blank_line_before_prompt_only_after_a_message():
    # 使用者要的：有訊息時訊息和 prompt 中間空一行；只按 Enter（沒有訊息）就直接補 prompt
    ming = Player("小明", FakeWriter(), None)
    commands.command(ming, "")
    assert ming.writer.data == b"> "
    ming.writer.data = b""
    commands.command(ming, "xyz")
    assert ming.writer.data == "什麼？\r\n\r\n> ".encode(ENCODING)
