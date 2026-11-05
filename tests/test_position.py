import re
from pathlib import Path

import pytest

import mud.commands as commands
from mud import save, stats, zones
from mud.characters import Position, characters
from mud.config import ENCODING
from mud.players import Player

AREAS = Path(__file__).resolve().parent.parent / "areas"
P = Position


class FakeWriter:
    """假的連線：只把送出的 bytes 收起來。"""

    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data

    def text(self):
        """收到的文字（拿掉顏色），看完就清掉。"""
        out = re.sub(r"\x1b\[[0-9;]*m", "", self.data.decode(ENCODING))
        self.data = b""
        return out


@pytest.fixture(autouse=True)
def world():
    zones.load(AREAS)
    yield
    characters.clear()


def player(name, position=P.STANDING, room=101, with_stats=False, is_imm=False, race=stats.Race.HUMAN):
    p = Player(name, FakeWriter(), zones.world.rooms[room])
    p.position, p.imm = position, is_imm
    if with_stats:
        p.race, p.guild = race, stats.Guild.SWORD
        p.primaries = dict(stats.RACE_PRIMARIES[race])
        p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
        stats.recompute(p)
        p.hp, p.mp, p.mv = p.panel["hp"], p.panel["mp"], p.panel["mv"]
    characters.append(p)
    return p


# ---- rest、sleep、stand（訊息照 C 版） ----

@pytest.mark.parametrize("start, cmd, mine, theirs, end", [
    (P.STANDING, "rest", "你坐下來休息。", "Ming坐下來休息。", P.RESTING),
    (P.STANDING, "sleep", "你一躺下就睡著了。", "Ming一躺下就睡著了。", P.SLEEPING),
    (P.STANDING, "stand", "你不是已經站起來了嗎？", None, P.STANDING),
    (P.RESTING, "res", "你已經在休息了啊。", None, P.RESTING),
    (P.RESTING, "sl", "你一躺下就睡著了。", "Ming一躺下就睡著了。", P.SLEEPING),
    (P.RESTING, "st", "你站了起來。", "Ming站了起來。", P.STANDING),
    (P.SLEEPING, "rest", "你醒過來，坐著休息。", "Ming醒過來，坐著休息。", P.RESTING),
    (P.SLEEPING, "sleep", "你已經睡得很熟了。", None, P.SLEEPING),
    (P.SLEEPING, "stand", "你醒過來，站了起來。", "Ming醒過來，站了起來。", P.STANDING),
    (P.FIGHTING, "rest", "你正處於戰鬥狀態之中了!!", None, P.FIGHTING),
    (P.FIGHTING, "sleep", "你正處於戰鬥狀態之中了!!", None, P.FIGHTING),
    (P.FIGHTING, "stand", "你正處於戰鬥狀態之中了!!", None, P.FIGHTING),
])
def test_rest_sleep_stand(start, cmd, mine, theirs, end):
    ming, hua = player("Ming", start), player("Hua")
    commands.command(ming, cmd)
    assert ming.writer.text() == mine + "\r\n\r\n> "
    assert hua.writer.text() == (f"\r\n{theirs}\r\n\r\n> " if theirs else "")
    assert ming.position == end


# ---- 睡覺、休息時能用哪些指令（玩家角色手冊「姿勢和指令」） ----

@pytest.mark.parametrize("line", ["look", "say 你好", "weather", "n", "south"])
def test_sleeping_cannot(line):
    ming = player("Ming", P.SLEEPING)
    commands.command(ming, line)
    assert ming.writer.text() == "在你的睡夢中嗎？\r\n\r\n> "
    assert ming.room.vnum == 101


@pytest.mark.parametrize("line", ["chat 嗨", "tell hua 嗨", "who", "score", "train", "rest", "stand"])
def test_sleeping_can(line):
    ming, _ = player("Ming", P.SLEEPING), player("Hua")
    commands.command(ming, line)
    assert "在你的睡夢中嗎？" not in ming.writer.text()


def test_sleeping_can_quit():
    assert commands.command(player("Ming", P.SLEEPING), "quit") is False


def test_resting_must_stand_up_to_walk():
    ming = player("Ming", P.RESTING)
    commands.command(ming, "n")
    assert ming.writer.text() == "嗯... 你正在休息耶..。\r\n\r\n> " and ming.room.vnum == 101
    commands.command(ming, "look")
    assert ming.writer.text().startswith("【測試房間（南）】")
    commands.command(ming, "say 嗨")
    assert ming.writer.text().startswith("你說：『嗨』")


def test_fighting_can_still_walk():
    # 還沒有 flee：戰鬥中照舊可以走（做 flee 時改）
    ming = player("Ming", P.FIGHTING)
    commands.command(ming, "n")
    assert ming.room.vnum == 102


def test_sleepers_do_not_hear_the_room_but_get_chat_and_tell():
    ming, hua = player("Ming"), player("Hua", P.SLEEPING)
    commands.command(ming, "say 你好")
    commands.command(ming, "rest")
    assert hua.writer.text() == ""                  # 同房間的事（say、坐下）睡著聽不到
    commands.command(ming, "chat 大家好")
    commands.command(ming, "tell hua 起床")
    assert hua.writer.text() == ("\r\nMing 聊天：大家好\r\n\r\n> " + "\r\nMing告訴你：起床\r\n\r\n> ")


def test_look_shows_positions():
    ming = player("Ming")
    player("Hua", P.RESTING)
    player("Bob", P.SLEEPING)
    player("Ann", P.FIGHTING)
    player("Joe")
    commands.command(ming, "look")
    text = ming.writer.text()
    for line in ("Hua坐在這裡休息。", "Bob躺在這裡睡覺。", "Ann正在這裡戰鬥。", "Joe站在這裡。"):
        assert line + "\r\n" in text


def test_regen_follows_the_new_position():
    ming = player("Ming", with_stats=True)
    ming.hp = 1.0
    commands.command(ming, "sleep")
    stats.regen(ming)
    assert ming.hp == pytest.approx(1 + ming.panel["hp"] * 0.30)      # 睡覺回 30%


# ---- say ----

def test_say():
    ming, hua = player("Ming"), player("Hua")
    commands.command(ming, "sa 你好{R")              # 玩家打的 {R 不會變成顏色
    assert ming.writer.data == "\x1b[37;1m你說：『你好{R』\x1b[0m\r\n\r\n> ".encode(ENCODING)
    assert hua.writer.data == "\r\n\x1b[37;1mMing說：『你好{R』\x1b[0m\r\n\r\n> ".encode(ENCODING)


def test_say_nothing():
    ming = player("Ming")
    commands.command(ming, "say")
    assert ming.writer.text() == "你想說些什麼呢？\r\n\r\n> "


# ---- who ----

def test_who():
    player("Ming", with_stats=True)
    shabu = player("Shabu", with_stats=True, is_imm=True, race=stats.Race.HALFLING)
    stats.set_level(shabu, 100)
    commands.command(shabu, "wh")
    assert shabu.writer.text().split("\r\n")[:4] == [
        "【線上玩家】",
        " [100 半身人 劍之公會] Shabu（imm）",
        " [  1 人類   劍之公會] Ming",
        "共 2 人。",
    ]


# ---- save ----

def test_save_writes_the_file(monkeypatch, tmp_path):
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path)
    ming = player("Ming", P.SLEEPING, room=102, with_stats=True)     # 睡著也能存（照 C 版）
    ming.password = save.hash_password("secret")
    commands.command(ming, "sav")
    assert ming.writer.text().startswith("存檔好了。\r\n\r\n<HP ")
    data = save.load_data("Ming")
    assert data["room"] == 102 and data["level"] == 1


def test_save_without_stats():
    ming = player("Ming")
    commands.command(ming, "save")
    assert ming.writer.text() == "你沒有可以存的資料。\r\n\r\n> "


def test_save_failure_is_reported(monkeypatch, caplog):
    def broken(p):
        raise OSError("磁碟滿了")

    monkeypatch.setattr(save, "save_player", broken)
    ming = player("Ming", with_stats=True)
    commands.command(ming, "save")
    assert ming.writer.text().startswith("存檔失敗了，請告訴管理員。\r\n")
    assert "Ming 存檔失敗" in caplog.text
