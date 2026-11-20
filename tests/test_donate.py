"""donate（使用者 2026-11-20 要的，照 C 版 do_donate）：用真的 areas/ 的秋風城，奉獻箱在神殿祭壇 3054。
只能捐背包裡的裝備、穿著的要先脫、綁定的不能捐、放不下、donate all、祭壇那間房聽到聲音、捐完存檔、奉獻箱不見了。
"""
import re
from pathlib import Path

import pytest

import mud.commands as commands
from mud import objects, save, skills, stats, zones
from mud.characters import Position, characters
from mud.config import DONATION_PIT, ENCODING
from mud.players import Player

AREAS = Path(__file__).resolve().parent.parent / "areas"
HALL, ALTAR = 3001, 3054                    # 神殿大廳、神殿祭壇（奉獻箱在這裡）
SWORD, TORCH, BOUND_RING = 3350, 3030, 110  # 制式長劍、火把（沒有顏色，不算裝備）、拾取後綁定的戒指（test.json）


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


@pytest.fixture
def world(monkeypatch):
    zones.load(AREAS)
    saved = []
    monkeypatch.setattr(save, "save_player", saved.append)
    yield saved
    characters.clear()
    zones.stop()


def player(name="Ming", room=HALL, position=Position.STANDING):
    p = Player(name, FakeWriter(), zones.world.rooms[room])
    p.race, p.guild = stats.Race.HUMAN, stats.Guild.SWORD
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.skills = skills.starter(p.guild)
    stats.set_level(p, 10)
    p.position = position
    characters.append(p)
    return p


def give(p, vnum, color="white"):
    obj = objects.create(vnum, 10, color)
    p.carrying.insert(0, obj)
    return obj


def text(p):
    out = re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))
    p.writer.data = b""
    return out


def pit():
    return next(o for o in zones.world.rooms[ALTAR].contents if o.vnum == DONATION_PIT)


def test_donate_sends_it_to_the_pit_and_the_altar_hears_it(world):
    ming, hua = player(), player("Hua")
    awake, asleep = player("Bob", ALTAR), player("Ann", ALTAR, Position.SLEEPING)
    sword = give(ming, SWORD)
    commands.command(ming, "don sword")
    assert sword not in ming.carrying and pit().contains[0] is sword
    name = objects.short(sword)
    assert text(ming).startswith(f"你把【{colorless(name)}】捐獻傳送到【奉獻箱/donation pit】。")
    assert f"Ming把【{colorless(name)}】捐獻傳送到【奉獻箱/donation pit】。" in text(hua)
    assert "你聽到奉獻箱裡面發生一聲巨響!!" in text(awake)
    assert text(asleep) == ""                                         # 睡著的聽不到
    assert world == [ming]                                           # 捐完存檔


def colorless(s):
    from mud.color import colorize
    return re.sub(r"\x1b\[[0-9;]*m", "", colorize(s))


def test_the_donor_at_the_altar_hears_it_too(world):
    ming = player(room=ALTAR)
    give(ming, SWORD)
    commands.command(ming, "donate sword")
    assert "你聽到奉獻箱裡面發生一聲巨響!!" in text(ming)


@pytest.mark.parametrize("line, want", [
    ("donate", "你想捐贈些什麼？"),
    ("donate axe", "你沒有這樣的物品。"),
    ("donate torch", "只能捐裝備。"),
    ("donate ring", "你沒辦法讓它離開你的身邊。"),
])
def test_refusals(world, line, want):
    ming = player()
    give(ming, TORCH, None)
    give(ming, BOUND_RING)
    before = list(pit().contains)
    commands.command(ming, line)
    assert text(ming).startswith(want)
    assert pit().contains == before and world == []


def test_worn_gear_has_to_come_off_first(world):
    ming = player()
    sword = give(ming, SWORD)
    commands.command(ming, "wear sword")
    text(ming)
    commands.command(ming, "donate sword")
    assert text(ming).startswith(f"你要先把【{colorless(objects.short(sword))}】脫下來才能捐。")
    assert ming.equipment["wield"] is sword


def test_donate_all_gives_only_what_it_can(world):
    ming = player()
    sword, torch, ring = give(ming, SWORD), give(ming, TORCH, None), give(ming, BOUND_RING)
    commands.command(ming, "donate all")
    assert ming.carrying == [ring, torch] and pit().contains[0] is sword
    assert text(ming).count("捐獻傳送到") == 1
    commands.command(ming, "donate all")
    assert text(ming).startswith("你沒有可以捐的裝備。")


def test_a_full_pit_takes_nothing(world):
    ming = player()
    give(ming, SWORD)
    pit().holds = 0
    commands.command(ming, "donate sword")
    assert text(ming).startswith("它放不進去。")


def test_no_pit(world):
    ming = player()
    give(ming, SWORD)
    zones.world.rooms[ALTAR].contents.remove(pit())
    commands.command(ming, "donate sword")
    assert text(ming).startswith("奉獻箱似乎消失於世界上了。")


def test_imm_can_donate_bound_gear(world):
    # 綁定跟 drop、give 一樣只擋玩家（imm 不擋，inventory.can_let_go）
    ming = player()
    ming.imm = True
    ring = give(ming, BOUND_RING)
    commands.command(ming, "donate ring")
    assert pit().contains[0] is ring
