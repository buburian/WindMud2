"""教學學院（真的 areas/academy.json）：學生站在自己那一份學院、一路走到畢業、學生重新登入和死掉回學院第一間。

學院是副本：建立要在 asyncio 裡（zones.instance 會開 tick 的 task），所以每個測試都在 asyncio.run() 裡做。
建立角色的流程（login.create 先 enroll 再站 home）在 test_login.py 用真的伺服器測。
戰鬥照 test_combat.py：fight.TICK_SECONDS 改很大、自己呼叫 tick()，亂數換成 Always。
"""
import asyncio
import re
from pathlib import Path

import pytest

import mud.commands as commands
from area_helpers import make_area, make_room, write_json
from mud import combat, death, fight, save, skills, stats, zones
from mud.area import AreaType
from mud.characters import characters
from mud.config import ACADEMY_FILE, ACADEMY_START, ENCODING
from mud.npcs import Npc
from mud.players import Player

AREAS = Path(__file__).resolve().parent.parent / "areas"


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


class Always:
    """假的亂數：random() 一律回傳 x（0.5 是打中、不浮動、不爆擊）。"""

    def __init__(self, x):
        self.x = x

    def random(self):
        return self.x


@pytest.fixture
def academy(tmp_path, monkeypatch):
    monkeypatch.setattr(fight, "TICK_SECONDS", 1000)       # 戰鬥的 loop 不會自己跑
    monkeypatch.setattr(combat, "rng", Always(0.5))
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path)
    zones.load(AREAS)
    yield
    characters.clear()
    zones.stop()


def student(name="Ming", guild=stats.Guild.SWORD):
    """剛建好的 1 級學生：跟 login.create() 一樣（一開始就會的技能、先 enroll、再站在 home()）。要在 asyncio 裡呼叫。"""
    p = Player(name, FakeWriter(), None)
    p.race, p.guild = stats.Race.HUMAN, guild
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.password = save.hash_password("secret")
    stats.set_level(p, 1)
    p.hp, p.mp, p.mv = p.panel["hp"], p.panel["mp"], p.panel["mv"]
    p.skills = skills.starter(p.guild)
    zones.enroll(p)
    p.room = zones.home(p)
    characters.append(p)
    return p


def plain(p):
    text = re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))
    p.writer.data = b""
    return text


def do(p, line):
    plain(p)
    commands.command(p, line)
    return plain(p)


def npc(name):
    return next(c for c in characters if isinstance(c, Npc) and c.name == name)


def test_a_student_starts_in_his_own_academy(academy):
    async def main():
        ming, hua = student("Ming"), student("Hua")
        assert zones.is_student(ming) and ming.vars == {"academy": {"student": True}}
        assert ming.room.vnum == ACADEMY_START and ming.room.zone.kind == AreaType.INSTANCE
        assert ming.room.zone is zones.instances[(ACADEMY_FILE, "Ming")] is not hua.room.zone   # 一個人一份
    asyncio.run(main())


def test_walk_through_the_academy_and_graduate(academy):
    async def main():
        p = student()
        assert do(p, "n").startswith("【走廊】")
        assert do(p, "n") == "【鐵門】關起來了。\r\n\r\n" + re.sub(r"\x1b\[[0-9;]*m", "", p.prompt())
        assert "【木門】關起來了。" in do(p, "e")
        do(p, "open e")
        assert do(p, "e").startswith("【儲藏室】")
        do(p, "get key")
        assert [o.name for o in p.carrying] == ["銅鑰匙"]
        do(p, "w")
        do(p, "unlock n")
        do(p, "open n")
        out = do(p, "n")                                            # 技能教室：照公會教他放一開始就會的技能（使用者要的）
        assert out.startswith("【技能教室】") and out.endswith(
            "\r\n\r\n技能教官說：『Ming，先打 skills 看看你會哪些技能。』\r\n"
            "技能教官說：『放技能打 use 技能 目標，等一下到訓練場試試看：use smash dummy。』\r\n\r\n"
            + re.sub(r"\x1b\[[0-9;]*m", "", p.prompt()))
        assert "重擊" in do(p, "skills")
        out = do(p, "n")                                            # 教官室：教官說話、放餽贈、給 1 級紫色長劍（使用者要的）
        assert out.startswith("【教官室】") and "教官說：『歡迎，Ming！" in out and "打 wear sword" in out
        # 別人在他的指令當下送來的好幾句連在一起（使用者要的）：跟房間畫面之間空一行，句子之間不空行
        sword = next(o for o in p.carrying if o.vnum == 202)               # 名字前面的詞綴是隨機的
        assert out.endswith("站在這裡。\r\n\r\n教官說：『歡迎，Ming！上場之前，先送你一份餽贈。』\r\n教官對你施展了【餽贈】。\r\n"
                            f"教官把【{sword.name}/sword】拿給你。\r\n"         # 跟 give 一樣的訊息（使用者要的）
                            "教官說：『這把長劍給你，打 wear sword 拿在手上。』\r\n教官說：『去北邊的訓練場，把稻草人打倒吧。』\r\n\r\n"
                            + re.sub(r"\x1b\[[0-9;]*m", "", p.prompt()))
        assert [a.source for a in p.affects] == ["gift"]
        do(p, "wear sword")
        do(p, "s")
        do(p, "n")                                                  # 回來：已經有長劍就不再給
        assert [o.name for o in p.carrying] == ["銅鑰匙"] and (p.equipment["wield"].vnum, p.equipment["wield"].color,
                                                              p.equipment["wield"].level) == (202, "purple", 1)
        assert do(p, "n").startswith("【訓練場】")
        do(p, "unlock n")                                           # 石門沒有鑰匙：開不了
        assert p.room.doors["north"].locked and "【石門】關起來了。" in do(p, "n")

        do(p, "use smash dummy")                                   # 用技能開打（技能教官教的）
        dummy = npc("稻草人")
        for _ in range(100):
            if dummy not in characters:
                break
            p.fight.tick()
        assert dummy not in characters and p.hp > 0
        # 同一段（兩個 prompt 中間，使用者要的）：斷氣、經驗、石門打開（腳本）、屍體裡有什麼
        block = next(b for b in plain(p).split("<HP") if "北邊的石門喀啦一聲打開了。" in b)
        assert block.index("稻草人已經斷氣") < block.index("北邊的石門喀啦一聲打開了。") < block.index("稻草人的屍體裝著：")
        assert not p.room.doors["north"].closed
        do(p, "get armor corpse")                                      # 一定掉 1 級紫色的護甲（使用者要的）
        do(p, "wear armor")
        worn = {slot: (o.vnum, o.color, o.level) for slot, o in p.equipment.items()}
        assert worn == {"wield": (202, "purple", 1), "body": (203, "purple", 1)}

        assert do(p, "n").startswith("【畢業廳】")
        out = do(p, "say 畢業")                                     # 院長收回鑰匙、送回 101
        assert "院長說：『恭喜你畢業了，Ming！外面的世界很大，好好冒險吧。』\r\n\r\n【測試房間（南）】" in out   # 新房間的畫面另起一段
        assert p.room is zones.start_room() and not zones.is_student(p) and p.carrying == []
        data = save.load_data("Ming")                               # 傳送出來就自動存好了（使用者要的）
        assert data["room"] == 101 and data["vars"] == {"academy": {}}
        assert save.player_from(data, FakeWriter()).room is zones.start_room()   # 畢業了：照存的房間
    asyncio.run(main())


def test_the_skill_teacher_names_the_skill_of_your_guild(academy):
    async def main():
        p = student(guild=stats.Guild.STAFF)
        p.room = p.room.zone.rooms[ACADEMY_START + 4]               # 教官室，往南走進技能教室
        assert "技能教官說：『放技能打 use 技能 目標，等一下到訓練場試試看：use fireball dummy。』" in do(p, "s")
        assert "火球" in do(p, "skills")
    asyncio.run(main())


def test_students_log_back_in_at_the_start_of_the_academy(academy):
    async def main():
        p = student()
        do(p, "n")
        save.save_player(p)
        characters.remove(p)
        data = save.load_data("Ming")
        assert data["room"] == ACADEMY_START + 1
        back = save.player_from(data, FakeWriter())
        assert back.room.vnum == ACADEMY_START and back.room.zone.kind == AreaType.INSTANCE and zones.is_student(back)
        assert save.player_from({**data, "room": 102}, FakeWriter()).room.vnum == ACADEMY_START   # 學生不管存在哪都回學院
        assert save.player_from({**data, "vars": {}}, FakeWriter()).room is zones.start_room()   # 不是學生：副本的房間不留
        assert save.player_from({**data, "room": 102, "vars": {}}, FakeWriter()).room.vnum == 102
    asyncio.run(main())


def test_students_who_die_go_back_to_the_start_of_the_academy(academy):
    async def main():
        p = student()
        first = p.room
        do(p, "n")
        death.player_dies(p)
        assert p.room is first                                      # 同一份學院的第一間
        p.vars = {}
        death.player_dies(p)
        assert p.room is zones.start_room()
    asyncio.run(main())


def test_without_the_academy_new_characters_are_not_students(tmp_path):
    write_json(tmp_path, "a.json", make_area("a.json", [make_room(1)], 100))
    zones.load(tmp_path)
    try:
        p = Player("Ming", FakeWriter(), None)
        zones.enroll(p)
        assert p.vars == {} and not zones.is_student(p) and zones.home(p) is zones.start_room()
        p.vars = {"academy": {"student": True}}                     # 存檔說是學生，可是學院的區域檔拿掉了：回起始房間
        assert not zones.is_student(p) and zones.home(p) is zones.start_room()
    finally:
        zones.stop()
