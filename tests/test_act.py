import pytest

from mud.act import TO_CHAR, TO_NOTVICT, TO_ROOM, TO_VICT, act
from mud.characters import SEX_FEMALE, SEX_MALE, SEX_NEUTRAL, characters
from mud.config import ENCODING
from mud.npcs import Npc
from mud.players import Player


# act() 只比較兩個角色的 room 是不是同一個，用兩個不同的物件代表兩間房就夠了
HERE, THERE = object(), object()


class FakeWriter:
    """假的連線：只把送出的 bytes 收起來。"""

    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data

    def text(self):
        return self.data.decode(ENCODING)


@pytest.fixture
def online():
    # 小明（男）、小美（女）、阿華（男）都在線，站在同一個房間
    ps = {}
    for name, sex in (("小明", SEX_MALE), ("小美", SEX_FEMALE), ("阿華", SEX_MALE)):
        ps[name] = Player(name, FakeWriter(), HERE, sex)
        characters.append(ps[name])
    yield ps
    characters.clear()


@pytest.fixture
def dog(online):
    # 一隻野狗（NPC）跟大家站在同一個房間；online 結束時會一起清掉
    npc = Npc("野狗", SEX_NEUTRAL, online["小明"].room)
    characters.append(npc)
    return npc


def to_other(text):
    # 送給別人：前面換行、後面補對方的 prompt
    return f"\r\n{text}\r\nHP100> "


def test_n_is_you_for_self_and_name_for_others(online):
    ming, mei, hua = online["小明"], online["小美"], online["阿華"]
    act("$n笑了。", ming, to=TO_CHAR)
    act("$n笑了。", ming, to=TO_ROOM)
    assert ming.writer.text() == "你笑了。\r\n"
    assert mei.writer.text() == to_other("小明笑了。")
    assert hua.writer.text() == to_other("小明笑了。")


def test_target_name_and_pronouns(online):
    ming, mei, hua = online["小明"], online["小美"], online["阿華"]
    act("$n拍拍$N：$e $m $s / $E $M $S", ming, vch=mei, to=TO_NOTVICT)
    assert hua.writer.text() == to_other("小明拍拍小美：他 他 他的 / 她 她 她的")


def test_neutral_pronouns(online):
    ming, mei = online["小明"], online["小美"]
    ming.sex = SEX_NEUTRAL
    act("$e $m $s", ming, to=TO_VICT, vch=mei)
    assert mei.writer.text() == to_other("它 它 它的")


def test_text_arguments(online):
    ming = online["小明"]
    act("$n說：$t（$T）", ming, t="你好", T="小聲", to=TO_CHAR)
    assert ming.writer.text() == "你說：你好（小聲）\r\n"


def test_room_targets_only_same_room(online):
    ming, mei, hua = online["小明"], online["小美"], online["阿華"]
    hua.room = THERE                            # 阿華在別的房間
    act("嗨", ming, to=TO_ROOM)
    act("嗨", ming, vch=mei, to=TO_NOTVICT)
    assert mei.writer.text() == to_other("嗨")  # 只收到 TO_ROOM 那一次
    assert hua.writer.data == b""


def test_each_target_type_reaches_right_people(online):
    ming, mei, hua = online["小明"], online["小美"], online["阿華"]
    cases = [
        (TO_CHAR, {ming}),
        (TO_VICT, {mei}),
        (TO_ROOM, {mei, hua}),
        (TO_NOTVICT, {hua}),
    ]
    for to, readers in cases:
        for p in online.values():
            p.writer.data = b""
        act("嗨", ming, vch=mei, to=to)
        assert {p for p in online.values() if p.writer.data} == readers


def test_colors_in_fmt_but_not_in_player_text(online):
    ming = online["小明"]
    act("{M$n說：$t{x", ming, t="{R紅字", to=TO_CHAR)  # 玩家打的 {R 不能變色
    assert ming.writer.text() == "\x1b[35;1m你說：{R紅字\x1b[0m\r\n"


def test_bad_code_is_kept_and_logged(online, caplog):
    ming = online["小明"]
    act("$x $N", ming, to=TO_CHAR)           # $x 不存在；$N 沒給對象
    assert ming.writer.text() == "$x $N\r\n"
    assert caplog.text.count("act：無法代換") == 2


def test_npc_as_actor(online, dog):
    # NPC 也能當訊息的主角
    act("$n朝北離開。", dog, to=TO_ROOM)
    for p in online.values():
        assert p.writer.text() == to_other("野狗朝北離開。")


def test_npc_as_target(online, dog):
    # NPC 當對象：$N 是它的名字，代名詞是「它」
    ming, mei = online["小明"], online["小美"]
    act("$n拍拍$N：$E $M $S", ming, vch=dog, to=TO_NOTVICT)
    assert mei.writer.text() == to_other("小明拍拍野狗：它 它 它的")


def test_room_with_npc(online, dog):
    # 房間裡有 NPC 時，送給同房間的訊息不會出錯，玩家收到的跟沒有 NPC 時一樣
    ming, mei, hua = online["小明"], online["小美"], online["阿華"]
    act("$n笑了。", ming, to=TO_ROOM)
    assert mei.writer.text() == hua.writer.text() == to_other("小明笑了。")
