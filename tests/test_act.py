import pytest

from mud.act import TO_CHAR, TO_NOTVICT, TO_ROOM, TO_VICT, act
from mud.config import ENCODING
from mud.players import SEX_FEMALE, SEX_MALE, SEX_NEUTRAL, Player, players


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
    # 小明（男）、小美（女）、阿華（男）都在線
    ws = {}
    for name, sex in (("小明", SEX_MALE), ("小美", SEX_FEMALE), ("阿華", SEX_MALE)):
        ws[name] = FakeWriter()
        players[ws[name]] = Player(name, sex)
    yield ws
    players.clear()


def to_other(text):
    # 送給別人：前面換行、後面補對方的 prompt
    return f"\r\n{text}\r\nHP100> "


def test_n_is_you_for_self_and_name_for_others(online):
    ming, mei, hua = online["小明"], online["小美"], online["阿華"]
    act("$n笑了。", ming, to=TO_CHAR)
    act("$n笑了。", ming, to=TO_ROOM)
    assert ming.text() == "你笑了。\r\n"
    assert mei.text() == to_other("小明笑了。")
    assert hua.text() == to_other("小明笑了。")


def test_target_name_and_pronouns(online):
    ming, mei, hua = online["小明"], online["小美"], online["阿華"]
    act("$n拍拍$N：$e $m $s / $E $M $S", ming, vch=mei, to=TO_NOTVICT)
    assert hua.text() == to_other("小明拍拍小美：他 他 他的 / 她 她 她的")


def test_neutral_pronouns(online):
    ming, mei = online["小明"], online["小美"]
    players[ming].sex = SEX_NEUTRAL
    act("$e $m $s", ming, to=TO_VICT, vch=mei)
    assert mei.text() == to_other("它 它 它的")


def test_text_arguments(online):
    ming = online["小明"]
    act("$n說：$t（$T）", ming, t="你好", T="小聲", to=TO_CHAR)
    assert ming.text() == "你說：你好（小聲）\r\n"


def test_each_target_type_reaches_right_people(online):
    ming, mei, hua = online["小明"], online["小美"], online["阿華"]
    cases = [
        (TO_CHAR, {ming}),
        (TO_VICT, {mei}),
        (TO_ROOM, {mei, hua}),
        (TO_NOTVICT, {hua}),
    ]
    for to, readers in cases:
        for w in online.values():
            w.data = b""
        act("嗨", ming, vch=mei, to=to)
        assert {w for w in online.values() if w.data} == readers


def test_colors_in_fmt_but_not_in_player_text(online):
    ming = online["小明"]
    act("{M$n說：$t{x", ming, t="{R紅字", to=TO_CHAR)  # 玩家打的 {R 不能變色
    assert ming.text() == "\x1b[35;1m你說：{R紅字\x1b[0m\r\n"


def test_bad_code_is_kept_and_logged(online, caplog):
    ming = online["小明"]
    act("$x $N", ming, to=TO_CHAR)           # $x 不存在；$N 沒給對象
    assert ming.text() == "$x $N\r\n"
    assert caplog.text.count("act：無法代換") == 2
