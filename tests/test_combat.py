"""戰鬥：kill、一下攻擊的訊息、一回合合成一段、打死生物（屍體、經驗值、升級）、玩家被打死、存檔的經驗值。

要一下一下看的：把 fight.TICK_SECONDS 改很大（loop 不會自己跑），在 asyncio 裡開打，自己呼叫 Fight.tick()；
亂數換成 Always（random() 一律回傳同一個數）：0.5 是打中、不浮動、不爆擊；0.0 是打中、浮動最低、爆擊；0.99 是沒打中。
"""
import asyncio
import re

import pytest

import mud.commands as commands
from area_helpers import make_area, make_mobile, make_room, write_json
from mud import combat, damage, fight, save, stats, zones
from mud.area import CORPSE_NPC_ITEM_TYPE
from mud.characters import Position, characters
from mud.color import colorize
from mud.commands import combat as combat_commands
from mud.config import ENCODING
from mud.npcs import Npc
from mud.players import Player
from player_helpers import make_player_file


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


class Always:
    """假的亂數：random() 一律回傳 x。"""

    def __init__(self, x):
        self.x = x

    def random(self):
        return self.x


@pytest.fixture
def world(tmp_path, monkeypatch):
    """世界：房間 101、102 南北相連，102 有一隻 5 級的野狗（純物理）。"""
    monkeypatch.setattr(fight, "TICK_SECONDS", 1000)       # loop 不會自己跑：測試自己呼叫 tick()
    monkeypatch.setattr(combat, "rng", Always(0.5))
    dog = make_mobile(1)
    dog.update(short="野狗", keywords="dog 野狗", level=5, tier="normal", tier_roll=None, attack=None, defense=None,
               archetype=None, act=0, position=7, sex=0, long="", drops=[])
    rooms = [make_room(1, north=2), make_room(2, south=1)]
    reset = [{"cmd": "M", "rare": 0, "mob_vnum": 1, "limit": 1, "room_vnum": 2, "comment": ""}]
    write_json(tmp_path, "a.json", make_area("a.json", rooms, 100, mobiles=[dog], resets=reset))
    zones.load(tmp_path)
    yield tmp_path
    characters.clear()
    zones.stop()


def the_dog():
    return next(c for c in characters if isinstance(c, Npc))


def fighter(name, room=102, level=1):
    """在線上、有屬性的人類劍之公會玩家。"""
    p = Player(name, FakeWriter(), zones.world.rooms[room])
    p.race, p.guild = stats.Race.HUMAN, stats.Guild.SWORD
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    stats.set_level(p, level)
    characters.append(p)
    return p


def raw(p):
    text = p.writer.data.decode(ENCODING)
    p.writer.data = b""
    return text


def text_of(p):
    return re.sub(r"\x1b\[[0-9;]*m", "", raw(p))


def prompt_of(p):
    return re.sub(r"\x1b\[[0-9;]*m", "", p.prompt())


def one_round(*starts):
    """在 asyncio 裡開打（starts 是 (打的人, 被打的人)），自己跑一個回合。回傳那一場。"""
    async def main():
        f = None
        for ch, victim in starts:
            f = fight.start_fight(ch, victim)
        f.tick()
        return f

    return asyncio.run(main())


# ---- kill ----

def test_kill_is_k():
    assert commands.find("k") is combat_commands.do_kill
    assert commands.find("kill") is combat_commands.do_kill


@pytest.mark.parametrize("arg, want", [
    ("", "你想要攻擊誰？"),
    ("cat", "找不到你想攻擊的人。"),
    ("ming", "你不可以攻擊玩家。"),
    ("shabu", "你不可以攻擊玩家。"),                       # 自己也是玩家
])
def test_kill_mistakes(world, arg, want):
    shabu = fighter("Shabu")
    fighter("Ming")
    commands.command(shabu, f"kill {arg}".strip())
    assert text_of(shabu) == f"{want}\r\n\r\n{prompt_of(shabu)}"
    assert shabu.fighting is None


def test_kill_needs_the_same_room(world):
    shabu = fighter("Shabu", room=101)
    commands.command(shabu, "kill dog")
    assert text_of(shabu).startswith("找不到你想攻擊的人。")


def test_kill_finds_names_by_their_beginning(world):
    # 名字只打開頭就行，同名的用 2.dog（characters.find_in_room，規則在 tests/test_targets.py）
    shabu = fighter("Shabu")
    dog = the_dog()

    async def main():
        commands.command(shabu, "kill 2.dog")               # 只有一隻狗
        missed = shabu.fighting
        commands.command(shabu, "kill do")
        return missed, shabu.fighting

    assert asyncio.run(main()) == (None, dog)


@pytest.mark.parametrize("position", [Position.RESTING, Position.SLEEPING])
def test_cannot_kill_while_resting_or_sleeping(world, position):
    shabu = fighter("Shabu")
    shabu.position = position
    commands.command(shabu, "kill dog")
    assert shabu.fighting is None


def test_kill_starts_a_fight_and_the_mobile_fights_back(world):
    shabu = fighter("Shabu")
    dog = the_dog()

    async def main():
        commands.command(shabu, "kill 野狗")
        raw(shabu)
        commands.command(shabu, "kill dog")                 # 已經在打
        return shabu.fighting, dog.fighting, shabu.fight is dog.fight, text_of(shabu)

    me, it, same, again = asyncio.run(main())
    assert (me, it, same) == (dog, shabu, True)
    assert again.startswith("你現在正在為自己的戰鬥努力著!!")


# ---- 一下攻擊的訊息 ----

def test_hit_messages(world):
    shabu, ming = fighter("Shabu"), fighter("Ming")
    dog = the_dog()
    one_round((shabu, dog))
    mine = damage.per_hit(shabu, dog, "phys")
    words, code = combat.severity(mine, dog.panel["hp"])
    n = stats.shown(mine)
    punct = "." if n <= 10 else "!"
    got = raw(shabu)
    # 自己那句亮綠、程度照 % 上色、後面回到一般顏色（照 C 版）
    assert got.startswith("\r\n\x1b[32;1m你使用直拳攻擊野狗，對它造成" + colorize(code) + words + "\x1b[0m" + f"{punct}({n})")
    plain = re.sub(r"\x1b\[[0-9;]*m", "", got)
    theirs = stats.shown(damage.per_hit(dog, shabu, "phys"))
    assert f"\r\n野狗攻擊你，對你造成{combat.severity(theirs, shabu.panel['hp'])[0]}" in plain   # 生物沒有武器名稱
    assert plain.count(prompt_of(shabu)) == 1                # 一回合好幾下，只有一個 prompt
    assert f"Shabu使用直拳攻擊野狗，對它造成{words}{punct}({n})" in text_of(ming)   # 同房間的人那句不上色
    assert dog.hp == pytest.approx(dog.panel["hp"] - mine * hits_in_first_round(shabu))


def hits_in_first_round(ch):
    """開打的第一個回合（時間 0～2）出手幾下：第一下在 0，之後每隔 2 ÷ 攻速。"""
    interval = 2 / damage.attacks_per_round(ch)
    return sum(1 for i in range(10) if i * interval < 2)


def test_crit_and_miss_messages(world, monkeypatch):
    shabu = fighter("Shabu")
    dog = the_dog()
    monkeypatch.setattr(combat, "rng", Always(0.0))
    one_round((shabu, dog))
    assert "你使用直拳攻擊野狗，爆擊！對它造成" in text_of(shabu)
    monkeypatch.setattr(combat, "rng", Always(0.99))
    fight.stop_fighting(shabu)
    fight.stop_fighting(dog)
    one_round((shabu, dog))
    assert "你使用直拳攻擊野狗，但是失手了.(0)" in text_of(shabu)


@pytest.mark.parametrize("percent, words", [
    (0.1, "輕微的擦傷"), (5, "輕微的擦傷"), (5.5, "輕微的擦傷"), (6, "普通的擦傷"), (25, "很深的傷口"),
    (26, "*輕微的打擊*"), (58, "*嚴重的傷害*"), (59, "**很嚴重的傷害**"), (100, "***致-命-的-創-傷***"),
    (101, "****石-破-天-驚-的-創-傷****"), (500, "*****超-乎-想-像-的-創-傷*****"), (501, "*****鬼--哭--神--號--的--創--傷*****"),
])
def test_severity_follows_c(percent, words):
    # 傷害佔 HP 上限的 %（無條件捨去成整數），照 C 版 dam_message 的分段
    assert combat.severity(percent, 100)[0] == words


# ---- 打死生物 ----

def test_killing_a_mobile(world):
    shabu, ming = fighter("Shabu"), fighter("Ming")
    dog = the_dog()
    dog.hp = 0.1                                            # 第一下就死
    one_round((shabu, dog))
    lines = text_of(shabu).split("\r\n")
    want_exp = stats.kill_exp(1, 5, dog.tier)
    # 打死的那一下、死亡訊息、經驗值在同一段，只有一個 prompt
    assert lines[1].startswith("你使用直拳攻擊野狗，")
    assert lines[2:4] == ["野狗已經斷氣，倒在地上死亡了!!", f"你共獲得了【{stats.shown(want_exp)}】點的經驗點數。"]
    assert dog not in characters and shabu.fighting is None and shabu.fight is None
    assert [o.item_type for o in zones.world.rooms[102].contents] == [CORPSE_NPC_ITEM_TYPE]
    assert shabu.exp == pytest.approx(want_exp)
    assert "野狗已經斷氣，倒在地上死亡了!!" in text_of(ming)
    assert ming.exp == 0                                    # 只給打出最後一下的人


def test_killing_levels_up(world):
    shabu = fighter("Shabu")
    dog = the_dog()
    dog.hp = 0.1
    shabu.exp = stats.exp_to_level(1) - 1
    one_round((shabu, dog))
    assert shabu.level == 2 and shabu.points == 1 and shabu.hp == shabu.panel["hp"]
    assert "【恭喜!!你提升了一級】現在是 2 級，多了 1 點主屬性點數，用 train 分配。" in text_of(shabu)
    assert shabu.exp == pytest.approx(stats.kill_exp(1, 5, dog.tier) - 1)


def test_gain_exp_can_level_up_more_than_once():
    p = Player("Shabu", None, None)
    p.race, p.guild = stats.Race.HUMAN, stats.Guild.SWORD
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    stats.recompute(p)
    assert stats.gain_exp(p, stats.exp_to_level(1) + stats.exp_to_level(2) + 1) == 2
    assert (p.level, p.points) == (3, 2) and p.exp == pytest.approx(1)
    stats.set_level(p, stats.MAX_LEVEL - 1)
    p.exp = 0
    assert stats.gain_exp(p, 10 ** 9) == 1 and p.level == stats.MAX_LEVEL and p.exp == 0   # 滿等就停
    assert stats.gain_exp(p, 100) == 0 and p.exp == 0


def test_max_level_gets_no_exp(world):
    shabu = fighter("Shabu", level=stats.MAX_LEVEL)
    dog = the_dog()
    dog.hp = 0.1
    one_round((shabu, dog))
    assert "經驗" not in text_of(shabu) and shabu.exp == 0


def test_slay_gives_no_exp(world):
    shabu = fighter("Shabu")
    shabu.imm = True
    commands.command(shabu, "slay dog")
    assert shabu.exp == 0 and "經驗" not in text_of(shabu)


# ---- 玩家被打死 ----

def test_player_killed_goes_back_to_start_room(world):
    shabu, ming = fighter("Shabu"), fighter("Ming")
    dog = the_dog()
    shabu.hp = 0.1                                          # 野狗的第一下就死
    f = one_round((shabu, dog))
    assert shabu.room is zones.start_room() and shabu.hp == 1 and shabu.position == Position.STANDING
    assert shabu.fighting is None and dog.fighting is None and dog.hp > 0
    text = text_of(shabu)
    assert "*********************你已經含恨死去了*********************" in text and text.count(prompt_of(shabu)) == 1
    assert "Shabu已經斷氣，倒在地上死亡了!!" in text_of(ming)
    f.tick()
    f.tick()
    assert text_of(shabu) == "" and shabu.hp == 1           # 野狗不再打他


# ---- 攻速 ----

def test_attacks_use_speed(world):
    shabu = fighter("Shabu")
    assert fight.attacks(shabu) == [damage.attacks_per_round(shabu)]
    assert fight.attacks(Npc("測試", 0, None)) == [1.0]      # 沒有屬性的（測試直接建的）


# ---- 存檔、advance ----

def test_exp_is_saved(world, monkeypatch):
    monkeypatch.setattr(save, "PLAYER_DIR", world / "players")
    p = make_player_file("Shabu")
    p.exp = 42.5
    save.save_player(p)
    data = save.load_data("Shabu")
    assert save.player_from(data, None).exp == 42.5
    del data["exp"]                                         # 舊存檔沒有 exp
    assert save.player_from(data, None).exp == 0.0


def test_advance_resets_exp(world):
    shabu = fighter("Shabu")
    shabu.imm, shabu.exp = True, 50
    commands.command(shabu, "advance shabu 3")
    assert shabu.level == 3 and shabu.exp == 0
