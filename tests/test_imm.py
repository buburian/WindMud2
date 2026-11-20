import asyncio
import json
import random
import re
from pathlib import Path

import pytest

import mud.commands as commands
from mud import fight, save, stats, zones
from mud.characters import characters
from mud.color import colorize
from mud.commands import imm, system
from mud.config import ENCODING
from mud.players import Player
from area_helpers import make_area, make_room, write_json

AREAS = Path(__file__).resolve().parent.parent / "areas"


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


def player(name, is_imm=False, race=stats.Race.HUMAN):
    """在線上、有屬性的 1 級玩家。"""
    p = Player(name, FakeWriter(), zones.world.rooms[101])
    p.race, p.guild, p.imm = race, stats.Guild.SWORD, is_imm
    p.primaries = dict(stats.RACE_PRIMARIES[race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    stats.recompute(p)
    p.hp, p.mp, p.mv = p.panel["hp"], p.panel["mp"], p.panel["mv"]
    characters.append(p)
    return p


def balanced(p):
    """永遠成立：還沒分配的點數 ＋ 加過的點數 ＝ 等級 − 1，主屬性 ＝ 種族的數字 ＋ 加過的點數。"""
    base = stats.RACE_PRIMARIES[p.race]
    return (p.points + sum(p.trained.values()) == p.level - 1
            and all(p.primaries[k] == base[k] + p.trained[k] for k in stats.PRIMARY_KEYS))


# ---- 指令表 ----

def test_only_imm_finds_imm_commands():
    assert commands.find("advance") is None
    assert commands.find("advance", is_imm=True) is imm.do_advance
    assert commands.find("ad", is_imm=True) is imm.do_advance
    assert commands.find("a", is_imm=True) is system.do_area     # 玩家的 area（2026-11-20）排在前面，a 就是 area
    # 原本的縮寫不受影響
    assert commands.find("t", is_imm=True) is system.do_tell
    assert commands.find("tr") is system.do_train
    assert commands.find("s", is_imm=True) is system.do_south


def test_not_imm_typing_advance_is_unknown():
    ming = player("Ming")
    commands.command(ming, "advance ming 100")
    assert ming.writer.text() == "什麼？\r\n\r\n" + re.sub(r"\x1b\[[0-9;]*m", "", ming.prompt())
    assert ming.level == 1


# ---- advance ----

def test_advance_other_player_up():
    shabu, ming = player("Shabu", is_imm=True), player("Ming")
    ming.hp = 1
    commands.command(shabu, "advance ming 100")
    assert shabu.writer.text().startswith("Ming 升到 100 級了。\r\n")
    assert (ming.level, ming.points) == (100, 99) and balanced(ming)
    assert ming.panel["hp"] > 1000 and ming.hp == ming.panel["hp"]       # 從頭算，補滿
    # 過了 5 級：自動學會猛擊；過了 10 級還沒選職業：提醒（paths.py）
    assert ming.writer.data == ("\r\n你升到 100 級了！多了 99 點主屬性點數，用 train 分配。\r\n" + colorize("{Y你學會了【猛擊】！{x") + "\r\n"
                                "你可以選職業了：到秋風城的公會分館找導師（打 skills 看）。\r\n\r\n" + ming.prompt()).encode(ENCODING)


def test_advance_self_sends_once():
    shabu = player("Shabu", is_imm=True)
    commands.command(shabu, "adv SHABU 10")
    assert shabu.writer.text().startswith("你升到 10 級了！多了 9 點主屬性點數，用 train 分配。\r\n你學會了【猛擊】！\r\n"
                                          "你可以選職業了：到秋風城的公會分館找導師（打 skills 看）。\r\n\r\n<HP ")
    assert shabu.level == 10


def test_advance_down_takes_unspent_points_first():
    shabu = player("Shabu", is_imm=True)
    stats.set_level(shabu, 20)
    stats.train(shabu, "str", 5)            # 19 點：加 5 到力量，還剩 14
    commands.command(shabu, "advance shabu 10")     # 要扣 10 點：沒分配的 14 點就夠
    assert shabu.writer.text().startswith("你降到 10 級了。\r\n")
    assert (shabu.points, shabu.trained["str"], shabu.primaries["str"]) == (4, 5, 17) and balanced(shabu)


def test_advance_down_takes_random_trained_attributes():
    shabu = player("Shabu", is_imm=True)
    stats.set_level(shabu, 11)
    stats.train(shabu, "str", 6)
    stats.train(shabu, "dex", 4)            # 10 點全部加完
    taken = stats.set_level(shabu, 4, random.Random(1))   # 要扣 7 點，只能從加過的力量、敏捷扣
    assert len(taken) == 7 and set(taken) <= {"str", "dex"}
    assert shabu.points == 0 and sum(shabu.trained.values()) == 3 and balanced(shabu)
    assert shabu.hp == shabu.panel["hp"]


def test_advance_down_message_lists_what_was_taken():
    shabu, ming = player("Shabu", is_imm=True), player("Ming")
    stats.set_level(ming, 4)
    stats.train(ming, "con", 3)
    commands.command(shabu, "advance ming 2")
    assert ming.writer.text().startswith("\r\n你降到 2 級了。扣回的主屬性：體質 -2。\r\n")
    assert ming.primaries["con"] == 13 and balanced(ming)


@pytest.mark.parametrize("arg, want", [
    ("", "用法：advance <名字> <等級>"),
    ("ming", "用法：advance <名字> <等級>"),
    ("nobody 10", "沒有找到這個玩家。"),
    ("ming 0", "等級要是 1～100。"),
    ("ming 101", "等級要是 1～100。"),
    ("ming ten", "等級要是 1～100。"),
    ("ming 1", "Ming 已經是 1 級了。"),
])
def test_advance_mistakes(arg, want):
    shabu, ming = player("Shabu", is_imm=True), player("Ming")
    commands.command(shabu, f"advance {arg}".strip())
    assert shabu.writer.text().startswith(want + "\r\n")
    assert ming.level == 1


# ---- train ----

def test_train_adds_points():
    ming = player("Ming")
    stats.set_level(ming, 10)
    hp = ming.panel["hp"]
    commands.command(ming, "train con 3")
    assert ming.writer.text().startswith("你把 3 點加到體質，現在體質 15，還剩 6 點。\r\n")
    commands.command(ming, "tr 力量")
    assert ming.writer.text().startswith("你把 1 點加到力量，現在力量 13，還剩 5 點。\r\n")
    assert ming.panel["hp"] > hp and balanced(ming)           # 從頭算：體質加了，HP 上限變大


def test_train_alone_shows_points():
    ming = player("Ming")
    stats.set_level(ming, 3)
    commands.command(ming, "train")
    assert ming.writer.text().startswith(
        "力量 12  智慧 12  知識 12  體質 12  敏捷 12\r\n還沒分配的點數：2\r\n用法：train <屬性> [點數]，例如 train str 5\r\n")


@pytest.mark.parametrize("level, arg, want", [
    (1, "str", "你沒有可以分配的點數。"),
    (5, "luck", "要加哪一項？str int wis con dex（或力量、智慧、知識、體質、敏捷）"),
    (5, "str 0", "點數要寫 1 以上的整數。"),
    (5, "str 5", "你只有 4 點。"),
    (100, "str 44", "力量最多 55，現在 12，最多再加 43 點。"),
])
def test_train_mistakes(level, arg, want):
    ming = player("Ming")
    stats.set_level(ming, level)
    commands.command(ming, f"train {arg}")
    assert ming.writer.text().startswith(want + "\r\n")
    assert balanced(ming)


def test_train_at_cap():
    ming = player("Ming")
    stats.set_level(ming, 100)
    stats.train(ming, "str", 43)
    commands.command(ming, "train str")
    assert ming.writer.text().startswith("力量已經是最高的 55 了。\r\n")


# ---- score ----

def test_score_shows_imm_and_unspent_points():
    shabu = player("Shabu", is_imm=True)
    stats.set_level(shabu, 100)
    commands.command(shabu, "score")
    raw = shabu.writer.data.decode(ENCODING)
    text = shabu.writer.text()
    assert " 【Shabu】 人類｜劍之公會｜男｜imm\r\n" in text
    assert " 力量  12   智慧  12   知識  12   體質  12   敏捷  12     可分配 99\r\n" in text
    assert "\x1b[35;1mimm" in raw and "\x1b[33;1m可分配 99" in raw
    assert "物理傷害 \x1b[37;1m" in raw             # 數字是亮白色（名字照畫面寬度切，不是照字數）


def test_score_without_imm_or_points():
    ming = player("Ming")
    commands.command(ming, "score")
    text = ming.writer.text()
    assert "imm" not in text and "可分配" not in text


# ---- 存檔 ----

def test_imm_points_trained_are_saved(monkeypatch, tmp_path):
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path)
    shabu = player("Shabu", is_imm=True)
    stats.set_level(shabu, 30)
    stats.train(shabu, "dex", 7)
    shabu.password = save.hash_password("secret")
    save.save_player(shabu)
    again = save.player_from(save.load_data("Shabu"), FakeWriter())
    assert (again.imm, again.level, again.points, again.trained, again.primaries) == \
        (True, 30, 22, shabu.trained, shabu.primaries)


def test_gold_is_saved(monkeypatch, tmp_path):
    # 還沒有拿到金幣的地方，先是 0；存檔有這一格，之後有金幣了下線不會不見
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path)
    ming = player("Ming")
    assert ming.gold == 0
    ming.gold = 1234567890
    ming.password = save.hash_password("secret")
    save.save_player(ming)
    assert save.player_from(save.load_data("Ming"), FakeWriter()).gold == 1234567890


def test_old_save_without_new_fields_loads(monkeypatch, tmp_path):
    # 加 imm、points、trained 以前存的檔（例如 shabu.json）照樣讀得進來
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path)
    ming = player("Ming")
    ming.password = save.hash_password("secret")
    save.save_player(ming)
    path = tmp_path / "ming.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("imm", "points", "trained", "gold"):
        del data[key]
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    again = save.player_from(save.load_data("Ming"), FakeWriter())
    assert (again.imm, again.points, again.trained, again.gold) == (False, 0, {k: 0 for k in stats.PRIMARY_KEYS}, 0)


# ---- goto ----

def body(p):
    """收到的字，拿掉最後的 prompt。"""
    return p.writer.text().rsplit("\r\n\r\n", 1)[0]


def test_goto_and_givemoney_abbreviations():
    assert commands.find("go", is_imm=True) is imm.do_goto
    assert commands.find("give", is_imm=True) is not imm.do_givemoney        # give 還是 give
    assert commands.find("givem", is_imm=True) is imm.do_givemoney


def test_goto_a_room_number():
    boss, hua, ming = player("Boss", is_imm=True), player("Hua"), player("Ming")
    ming.room = zones.world.rooms[3001]
    commands.command(boss, "goto 3001")
    assert boss.room is zones.world.rooms[3001]
    assert body(boss).startswith("【秋風城神殿大廳】")                         # 到了先看房間
    assert "Boss在一陣旋風中離開了。" in hua.writer.text()                   # 照 C 版
    assert "Boss乘著旋風出現了。" in ming.writer.text()


def test_goto_a_person_or_a_mobile():
    boss, ming = player("Boss", is_imm=True), player("Ming")
    ming.room = zones.world.rooms[3001]
    commands.command(boss, "goto mi")                                        # 線上的玩家，名字打開頭
    assert boss.room is ming.room
    commands.command(boss, "goto merchant")                                  # 別的房間的生物（測試商人在 101，別的區域沒有這個名字）
    assert boss.room is zones.world.rooms[101]


@pytest.mark.parametrize("line, want", [
    ("goto", "去那兒？"),
    ("goto 99999", "沒有這個地方。"),
    ("goto 201", "沒有這個地方。"),                                           # 副本（教學學院）的房間用號碼去不了
    ("goto nobody", "沒有這個地方。"),
])
def test_goto_mistakes(line, want):
    boss = player("Boss", is_imm=True)
    commands.command(boss, line)
    assert body(boss) == want and boss.room is zones.world.rooms[101]


def test_goto_stops_the_fight():
    boss = player("Boss", is_imm=True)
    boss.room = zones.world.rooms[102]
    rabbit = next(c for c in characters if getattr(c, "vnum", None) == 103)

    async def go():
        fight.start_fight(boss, rabbit)
        assert boss.fighting is rabbit
        commands.command(boss, "goto 101")
        return boss.fighting, rabbit.fighting

    assert asyncio.run(go()) == (None, None) and boss.room is zones.world.rooms[101]


# ---- givemoney ----

def test_givemoney(monkeypatch):
    saved = []
    monkeypatch.setattr(save, "save_player", saved.append)
    boss, ming = player("Boss", is_imm=True), player("Ming")
    ming.room = zones.world.rooms[3001]                                      # 不用在同一間房
    boss.gold = 5
    commands.command(boss, "givemoney mi 100")
    assert body(boss) == "你給了Ming【100】枚金幣。"
    assert "Boss給你【100】枚金幣。" in ming.writer.text()
    assert (ming.gold, boss.gold, saved) == (100, 5, [ming])                # 自己的不會少，幫對方存檔


def test_givemoney_to_yourself():
    boss = player("Boss", is_imm=True)
    commands.command(boss, "givemoney boss 7")
    assert body(boss) == "你給了自己【7】枚金幣。" and boss.gold == 7


@pytest.mark.parametrize("line, want", [
    ("givemoney", "用法：givemoney <名字> <數量>"),
    ("givemoney ming", "用法：givemoney <名字> <數量>"),
    ("givemoney nobody 5", "沒有找到這個玩家。"),
    ("givemoney ming 0", "數量要是正整數。"),
    ("givemoney ming -5", "數量要是正整數。"),
    ("givemoney ming ①", "數量要是正整數。"),
])
def test_givemoney_mistakes(line, want):
    boss, ming = player("Boss", is_imm=True), player("Ming")
    commands.command(boss, line)
    assert body(boss) == want and ming.gold == 0


# ---- vnums：區域檔的號碼範圍和還沒用的（使用者 2026-11-20 要的） ----

def test_vnums_lists_ranges_and_the_gaps(tmp_path):
    rooms = lambda first: [make_room(first + 1)]
    write_json(tmp_path, "b.json", make_area("b.json", rooms(500), (500, 599)))
    write_json(tmp_path, "a.json", make_area("a.json", rooms(100), (100, 199)))
    write_json(tmp_path, "c.json", make_area("c.json", rooms(200), (200, 299), kind="instance"))    # 副本的也算
    zones.load(tmp_path)
    shabu = player("Shabu", is_imm=True)
    commands.command(shabu, "vn")
    assert shabu.writer.text().startswith("區域檔用掉的號碼（照號碼排；房間、生物、物品都在檔案自己的範圍裡）：\r\n"
                                   "  100～199  a.json  測試\r\n  200～299  c.json  測試\r\n  500～599  b.json  測試\r\n"
                                   "還沒用的號碼（新的區域檔可以用，1～99 是保留的）：\r\n  300～499\r\n  600 以上\r\n\r\n<HP ")


def test_vnums_is_only_for_imm():
    ming = player("Ming")
    commands.command(ming, "vnums")
    assert ming.writer.text().startswith("什麼？")


def test_area_lists_every_area(tmp_path):
    # area（玩家也能用，使用者 2026-11-20 要的）：世界、動態、副本的區域檔都列，照等級排
    for name, vnums, kind, levels, title in (("a.json", (100, 199), "world", [5, 9], "乙地"), ("b.json", (200, 299), "dynamic", [1, 3], "甲地"),
                                             ("c.json", (300, 399), "instance", [5, 20], "丙地")):
        data = make_area(name, [make_room(vnums[0] + 1)], vnums, kind=kind)
        data["area"]["header"].update(levels=levels, title=title, author="Shabu")
        write_json(tmp_path, name, data)
    zones.load(tmp_path)
    ming = player("Ming")
    commands.command(ming, "a")
    assert ming.writer.text().startswith("遊戲裡的區域：\r\n  區域  等級      種類  作者\r\n"
                                         "  甲地  1～3 級   動態  Shabu\r\n  乙地  5～9 級   世界  Shabu\r\n  丙地  5～20 級  副本  Shabu\r\n\r\n")
