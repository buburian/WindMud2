import re
from pathlib import Path

import pytest

import mud.commands as commands
from area_helpers import make_exit, make_room, write_area
from mud import stats, zones
from mud.area import MobTier
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
BOX = "一個木頭做的測試箱子放在角落。/\x1b[36;1mbox"   # areas/test.json 的物品 3（重置 O 放在北邊房間），英文名字亮青

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


def test_quit_disconnects():
    # 存檔在 server.handle() 的 finally（直接斷線也存），test_login.py 測
    ming = Player("小明", FakeWriter(), None)   # 用不到房間
    assert commands.command(ming, "QUIT") is False
    assert ming.writer.data == "再見。\r\n".encode(ENCODING)


@pytest.mark.parametrize("line", ["q", "qu", "qui", "Q"])
def test_quit_must_be_spelled_out(line):
    # 使用者 2026-11-20 要的：q 不小心按到（分頁看完了還按 q）不會離開，照 C 版 do_qui 提醒
    ming = Player("小明", FakeWriter(), None)
    assert commands.command(ming, line) is True
    assert ming.writer.data.decode(ENCODING).startswith(commands.FULL_WORD["quit"] + "\r\n")


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
    # 自己走過去之後自動 look：新房間有三隻練功用的野兔（沒有別的玩家）、地上一個箱子，出口只有南
    assert ming.writer.data == (
        "\x1b[32;1m【\x1b[33;1m測試房間（北）\x1b[32;1m】\x1b[0m\r\n"
        "\x1b[32;1m【出口： \x1b[36;1m南\x1b[32;1m】\x1b[0m\r\n"
        "這是測試區域北邊的房間。\r\n往南可以回到剛才的房間。\r\n"
        "\r\n" + (W + RABBIT + X + "\r\n") * 3 + W + BOX + X + "\r\n" +
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
    write_area(tmp_path, "a.json", [make_room(101, north=102), make_room(102)])
    stand_in(tmp_path, online)
    ming = online["小明"]
    commands.command(ming, "look n")
    assert ming.writer.data == "那裡沒有什麼特別的東西。\r\n\r\n> ".encode(ENCODING)


def test_things_come_before_directions(online, tmp_path):
    # 照 C 版：名字跟方向撞在一起時，先看東西
    r = make_room(101)
    r["exits"]["north"] = make_exit(101, "往北看。\n")
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


# ---- look 角色（照 C 版 show_char_to_char_1，使用者選的三樣：描述、受傷狀態、旁邊的人看到打量） ----

def test_look_at_a_mobile(world):
    ming, hua, bob = world["小明"], world["阿華"], world["Bob"]
    commands.command(ming, "look merchant")
    # areas/test.json 的測試商人：區域檔的描述，接著受傷狀態（剛出現，HP 是滿的），最後是可能掉落
    # （一般怪：測試長劍那行只有首領會掉，不列；重置 G 給牠的東西不列）
    want = "這是測試區域的商人，臉上一直掛著笑容。\r\n測試商人十分的健康，完整。\r\n可能掉落：測試藥水。\r\n\r\n> "
    assert ming.writer.data == want.encode(ENCODING)
    for p in (hua, bob):
        assert p.writer.data == "\r\n小明對測試商人仔細地上下打量了一番。\r\n\r\n> ".encode(ENCODING)


def test_possible_drops_go_by_its_tier(world):
    # 設計文件 §4.10：照掉落表的順序，只列這隻的種類會骰的行；首領的測試商人多了測試長劍
    ming = world["小明"]
    merchant = next(c for c in characters if isinstance(c, Npc) and c.vnum == 101)
    merchant.tier = MobTier.BOSS
    commands.command(ming, "look merchant")
    assert "可能掉落：測試長劍、測試藥水。\r\n".encode(ENCODING) in ming.writer.data


def line(vnum, chance=10000, color="white", tiers=None):
    return {"obj_vnum": vnum, "color": color, "chance": chance, "tiers": tiers}


def test_possible_drops_only_names_each_once(world, dog):
    # 同一件寫好幾行（不同顏色）只列一次；機率 0、找不到的號碼不列；只有名字，不上顏色
    dog.keywords, dog.tier = ["dog"], MobTier.NORMAL
    dog.drops = [line(105, color="blue"), line(999), line(102, chance=0), line(105, color="orange"), line(101, color=None)]
    ming = world["小明"]
    commands.command(ming, "look dog")
    assert ming.writer.data == "你看不出來它有任何特殊的地方。\r\n可能掉落：測試盾牌、測試藥水。\r\n\r\n> ".encode(ENCODING)


def test_long_possible_drops_wrap_at_79(world, dog):
    # 太長換行（不超過 79 格），接在第一個名字那裡對齊
    dog.keywords, dog.tier = ["dog"], MobTier.NORMAL
    dog.drops = [line(v) for v in range(101, 112)]
    ming = world["小明"]
    commands.command(ming, "look dog")
    text = ming.writer.data.decode(ENCODING).split("\r\n")
    drops = text[1:text.index("")]
    assert drops[0].startswith("可能掉落：測試藥水、") and len(drops) == 2
    assert drops[1].startswith(" " * 10 + "測試") and drops[1].endswith("裝備綁定戒指。")
    assert all(len(d.encode(ENCODING)) <= 79 for d in drops)


def test_no_line_without_possible_drops(world, dog):
    dog.keywords, dog.tier = ["dog"], MobTier.NORMAL
    dog.drops = [line(102, tiers=["boss"])]
    ming = world["小明"]
    commands.command(ming, "look dog")
    assert ming.writer.data == "你看不出來它有任何特殊的地方。\r\n\r\n> ".encode(ENCODING)


def test_look_at_a_player(world):
    ming, hua, bob = world["小明"], world["阿華"], world["Bob"]
    bob.position = Position.SLEEPING        # 睡著的人看不到打量（跟其他同房間的事一樣）
    commands.command(ming, "look 阿華")
    # 玩家沒有描述（照 C 版那句）；直接建的玩家沒有屬性，所以沒有受傷狀態
    assert ming.writer.data == "你看不出來他有任何特殊的地方。\r\n\r\n> ".encode(ENCODING)
    assert hua.writer.data == "\r\n小明對你仔細地上下打量了一番。\r\n\r\n> ".encode(ENCODING)
    assert bob.writer.data == b""


def test_look_at_yourself(world):
    ming, hua = world["小明"], world["阿華"]
    commands.command(ming, "look 小明")
    assert ming.writer.data == "你看不出來他有任何特殊的地方。\r\n\r\n> ".encode(ENCODING)
    assert hua.writer.data == b""           # 看自己不打量


def test_directions_come_before_characters(world, dog):
    # 名字只比開頭：look d 還是往下看（101 往下沒有出口），要看野狗打 look dog（使用者核准的順序：東西 → 方向 → 角色）
    dog.keywords = ["dog"]
    ming = world["小明"]
    commands.command(ming, "look d")
    assert ming.writer.data == "那裡沒有什麼特別的東西。\r\n\r\n> ".encode(ENCODING)
    ming.writer.data = b""
    commands.command(ming, "look dog")
    # 直接建的野狗：沒有描述、沒有屬性（沒有受傷狀態）
    assert ming.writer.data == "你看不出來它有任何特殊的地方。\r\n\r\n> ".encode(ENCODING)


def test_look_at_the_second_one(world, dog):
    # n.名字 照 look 畫面的順序；生物的描述可以用顏色代碼（跟房間描述一樣，使用者定的）
    second = Npc("野狗", SEX_NEUTRAL, zones.world.rooms[101])
    dog.keywords = second.keywords = ["dog"]
    second.description = "一隻{R紅眼睛{x的野狗。"
    characters.append(second)
    ming = world["小明"]
    commands.command(ming, "look 2.dog")
    assert ming.writer.data == "一隻\x1b[31;1m紅眼睛\x1b[0m的野狗。\r\n\r\n> ".encode(ENCODING)


@pytest.mark.parametrize("hp, want", [
    (1000, "十分的健康，完整。"), (999, "有少許的瘀青。"), (900, "有少許的瘀青。"), (899, "帶著一些瘀青。"),
    (800, "帶著一些瘀青。"), (799, "有一些小傷口。"), (700, "有一些小傷口。"), (699, "有幾處明顯的傷口。"),
    (600, "有幾處明顯的傷口。"), (599, "佈滿很多明顯的傷口。"), (500, "佈滿很多明顯的傷口。"), (499, "開始大量的出血，不止。"),
    (400, "開始大量的出血，不止。"), (399, "身上都是鮮紅的血液。"), (300, "身上都是鮮紅的血液。"), (299, "腸子流了出來。"),
    (200, "腸子流了出來。"), (199, "快要死了。"), (100, "快要死了。"), (99, "瀕臨死亡。"), (0, "瀕臨死亡。"),
])
def test_look_shows_how_hurt(world, hp, want):
    # HP 剩幾 %（大於等於，照 C 版的 11 句）；HP 上限 1000，所以 999 是 99.9%。encode 也確認每句都轉得成 Big5
    wolf = Npc("野狼", SEX_NEUTRAL, zones.world.rooms[101])
    wolf.keywords, wolf.panel, wolf.hp = ["wolf"], {"hp": 1000.0}, float(hp)
    characters.append(wolf)
    ming = world["小明"]
    commands.command(ming, "look wolf")
    assert ming.writer.data == f"你看不出來它有任何特殊的地方。\r\n野狼{want}\r\n\r\n> ".encode(ENCODING)


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


def score_of(p):
    p.writer.data = b""
    commands.command(p, "sc")
    return p.writer.data.decode(ENCODING)


def test_score_layout():
    # 使用者選的樣子：寬 79 格（跟 C 版一樣），每個數字的位置固定
    p = stat_player()
    p.hp = p.panel["hp"] * 0.25
    text = score_of(p)
    heavy, thin = "=" * 79, "-" * 79
    assert re.sub(r"\x1b\[[0-9;]*m", "", text) == "\r\n".join([
        heavy,
        " 【Zzqa】 獸人｜劍之公會｜男",
        thin,
        " 等級 1      經驗 0 / 100                        金幣 0  淬火石 0",   # 經驗：這一級累積的 / 升級要的；淬火石（temper.py）
        " 力量  14   智慧  11   知識  11   體質  12   敏捷  12",
        thin,
        " HP  [=====---------------]       16 / 62",
        " MP  [====================]       26 / 26",
        " MV  [====================]       39 / 39",
        thin,
        " 攻擊  物理傷害        4       法術傷害        0       命中           16",
        "       爆擊率          8       爆擊傷害        4       攻速           22",
        " 防禦  閃躲           11       物理抗性        8       法術抗性       15",
        "       龍焰抗性        0       AC              0",
        heavy,
        "",
        p.prompt().replace("\x1b[32;1m", "").replace("\x1b[31;1m", "").replace("\x1b[0m", ""),
    ])
    assert "\x1b[30;1m法術傷害        0\x1b[0m" in text    # 劍之公會用不到法術傷害：整格變暗
    assert "\x1b[31;1m=====\x1b[30;1m---------------\x1b[0m" in text   # HP 條：紅色的滿格、暗灰的空格


def test_score_has_room_for_big_numbers():
    # 經驗 7 位數、金幣 10 位數、淬火石 4 位數、HP 和屬性 5 位數，每一行都不超過 79 格，位置也不會跑掉
    p = stat_player()
    p.level, p.exp, p.gold, p.points, p.temper_stones = 99, 9999999, 2147483647, 98, 9999
    p.panel = {k: 99999.0 for k in p.panel}
    p.hp = p.mp = p.mv = 99999.0
    lines = re.sub(r"\x1b\[[0-9;]*m", "", score_of(p)).split("\r\n")[:-2]
    assert max(len(line.encode(ENCODING)) for line in lines) == 79
    assert lines[3].startswith(" 等級 99     經驗 9999999 / ") and lines[3].endswith("金幣 2147483647  淬火石 9999")
    assert lines[3].index("金幣") == " 等級 1      經驗 0 / 100                        金幣 0".index("金幣")
    assert lines[6] == " HP  [====================]    99999 / 99999"
    assert lines[10] == " 攻擊  物理傷害    99999       法術傷害    99999       命中        99999"


def test_score_shows_exp_until_max_level():
    p = stat_player()
    p.exp = 34.6
    assert " 等級 1      經驗 35 / 100 " in re.sub(r"\x1b\[[0-9;]*m", "", score_of(p))
    p.level = stats.MAX_LEVEL                       # 滿等不再拿經驗，不顯示；金幣照樣在原本的位置
    text = re.sub(r"\x1b\[[0-9;]*m", "", score_of(p))
    assert " 等級 100" + " " * 40 + "金幣 0  淬火石 0\r\n" in text and "經驗" not in text


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
