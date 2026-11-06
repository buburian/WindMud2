"""身上的效果（affects.py，玩家角色手冊「身上的效果」）：覆蓋和疊加、暫時加減屬性、持續加減 HP／MP／MV（每 3 tick、矮人的堅韌、扣死）、
時間到消失、死掉、存檔，affects 指令、imm 的 effect、mstat 那一行，旗標的中文跟手冊比對。

一個 tick 一個 tick 看：自己呼叫 affects.tick()（世界 tick 也測一次）。
"""
import asyncio
import random
import re
from pathlib import Path

import pytest

import mud.commands as commands
from area_helpers import make_area, make_mobile, make_room, write_json
from player_helpers import make_player_file
from mud import affects, combat, fight, npcs, save, stats, zones
from mud.affects import Affect
from mud.area import AFFECT_FLAG_NAMES, CORPSE_NPC_ITEM_TYPE, AffectFlag
from mud.characters import characters
from mud.config import ENCODING
from mud.players import Player

AREA_MANUAL = Path(__file__).resolve().parent.parent / "docs" / "區域製作手冊.md"


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


class Always:
    def __init__(self, x):
        self.x = x

    def random(self):
        return self.x


@pytest.fixture
def world(tmp_path, monkeypatch):
    """房間 101、102（南北相連），房間 101 有一隻 1 級的一般怪「生物1」。"""
    monkeypatch.setattr(fight, "TICK_SECONDS", 1000)        # 戰鬥的 loop 不會自己跑
    monkeypatch.setattr(combat, "rng", Always(0.5))
    monkeypatch.setattr(save, "PLAYER_DIR", str(tmp_path / "players"))
    write_json(tmp_path, "a.json", make_area("a.json", [make_room(1, north=2), make_room(2, south=1)], 100))
    zones.load(tmp_path)
    yield zones.world
    characters.clear()
    zones.stop()


def person(name, room=101, race=stats.Race.HUMAN, imm=False):
    """在線上、有屬性的 1 級玩家，HP、MP、MV 是滿的。"""
    p = Player(name, FakeWriter(), zones.world.rooms[room])
    p.race, p.guild, p.imm = race, stats.Guild.SWORD, imm
    p.primaries = dict(stats.RACE_PRIMARIES[race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    stats.recompute(p)
    p.hp, p.mp, p.mv = p.panel["hp"], p.panel["mp"], p.panel["mv"]
    characters.append(p)
    return p


def creature(room=101):
    proto = make_mobile(1)
    proto.update(tier_roll=None, position=7, attack=None, defense=None, archetype=None, drops=[], shop=None)
    return npcs.spawn(101, proto, zones.world.rooms[room], random.Random(0), 100)


def plain(p):
    text = re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))
    p.writer.data = b""
    return text


def say(p, line):
    """打一行指令，回傳回覆（不含最後的空行和 prompt）。"""
    plain(p)
    commands.command(p, line)
    return plain(p).rsplit("\r\n\r\n", 1)[0]


def ticks(n):
    for _ in range(n):
        affects.tick()


def drip(source="drip", duration=60, **periodic):
    """測試用的持續效果：每 3 tick 加減 periodic（預設 HP -1）。"""
    return Affect(source, "滴", duration, periodic=periodic or {"hp": -1.0})


# ---- 放上去、覆蓋、疊加、拿掉 ----

def test_add_overwrites_the_same_source(world):
    p = person("Ming")
    affects.add(p, drip(duration=10))
    ticks(2)
    assert (p.affects[0].ticks, p.affects[0].elapsed) == (8, 2)
    affects.add(p, drip(duration=10, hp=-5.0))                      # 同一個來源：整個換掉，時間回到滿的、跳的時間從頭數
    [a] = p.affects
    assert (a.ticks, a.elapsed, a.periodic) == (10, 0, {"hp": -5.0})
    top = p.hp
    ticks(2)
    assert p.hp == top                                              # 從頭數：第 1、2 tick 不跳
    ticks(1)
    assert p.hp == top - 5


def test_different_sources_stack(world):
    p = person("Ming")
    affects.add(p, drip("a"))
    affects.add(p, drip("b"))
    assert [a.source for a in p.affects] == ["a", "b"]
    affects.remove(p, "a")
    assert [a.source for a in p.affects] == ["b"]
    affects.clear(p)
    assert p.affects == []


# ---- 暫時加減屬性 ----

def test_applies_change_player_stats(world):
    p = person("Ming")
    hit = p.panel["hit"]
    affects.add(p, Affect("bless", "祝福", 60, applies={"hit": 10.0}))
    assert p.panel["hit"] == hit + 10
    stats.recompute(p)                                              # 從頭算（升級、穿脫裝備）也算得到
    assert p.panel["hit"] == hit + 10
    affects.remove(p, "bless")
    assert p.panel["hit"] == hit


def test_stats_go_back_when_it_wears_off(world):
    p = person("Ming")
    hit = p.panel["hit"]
    affects.add(p, Affect("bless", "祝福", 3, applies={"hit": 10.0}))
    ticks(3)
    assert p.affects == [] and p.panel["hit"] == hit


def test_hp_max_up_does_not_refill_and_down_clamps(world):
    p = person("Ming")
    top = p.panel["hp"]
    affects.add(p, Affect("big", "大", 60, applies={"hp": 100.0}))
    assert (p.panel["hp"], p.hp) == (top + 100, top)               # 上限變高不補
    p.hp = top + 100
    affects.remove(p, "big")
    assert (p.panel["hp"], p.hp) == (top, top)                     # 拿掉：夾在新上限


def test_applies_on_a_creature(world):
    npc = creature()
    base = dict(npc.base_panel)
    assert npc.panel == base
    affects.add(npc, Affect("weak", "弱", 60, applies={"res_phys": -5.0}))
    assert npc.panel["res_phys"] == base["res_phys"] - 5 and npc.base_panel == base
    affects.remove(npc, "weak")
    assert npc.panel == base


def test_has_flag(world):
    p = person("Ming")
    assert not affects.has_flag(p, AffectFlag.BLIND)
    affects.add(p, Affect("blind", "瞎", 30, flags=AffectFlag.BLIND))
    assert affects.has_flag(p, AffectFlag.BLIND) and not affects.has_flag(p, AffectFlag.INVISIBLE)


# ---- 持續加減 ----

def test_first_jump_is_on_the_third_tick(world):
    # 10 不是 3 的倍數：用「剩下的 tick」決定跳的話，第 1 tick 就會跳
    p = person("Ming")
    top = p.hp
    affects.add(p, drip(duration=10))
    ticks(2)
    assert p.hp == top
    ticks(1)
    assert p.hp == top - 1
    ticks(7)                                                        # 10 tick：跳 10 ÷ 3 ＝ 3 次，時間到拿掉
    assert p.hp == top - 3 and p.affects == []


@pytest.mark.parametrize("duration, jumps", [(60, 20), (3, 1), (2, 0)])
def test_number_of_jumps(world, duration, jumps):
    p = person("Ming")
    top = p.hp
    affects.add(p, drip(duration=duration))
    ticks(duration)
    assert (top - p.hp, p.affects) == (jumps, [])                  # 最後一 tick 跳完才拿掉


def test_dwarves_shake_off_hp_loss_twice_as_fast(world):
    p = person("Ming", race=stats.Race.DWARF)
    top = p.hp
    affects.add(p, drip(duration=10))
    ticks(2)
    assert (p.hp, p.affects[0].ticks) == (top, 6)                  # 每 tick 減 2，可是第 2 tick 照樣不跳（看放下去多久）
    ticks(1)
    assert p.hp == top - 1
    ticks(2)
    assert p.affects == [] and p.hp == top - 1                     # 5 tick 就沒了：只跳 1 次
    affects.add(p, drip(duration=60))
    ticks(30)
    assert (top - 1 - p.hp, p.affects) == (10, [])                  # 60 秒的毒只跳 10 次


def test_dwarves_are_normal_for_other_effects(world):
    p = person("Ming", race=stats.Race.DWARF)
    p.hp -= 50
    affects.add(p, drip("heal", hp=1.0))
    affects.add(p, drip("tired", mv=-1.0))
    ticks(2)
    assert [a.ticks for a in p.affects] == [58, 58]


def test_healing_stops_at_the_top_and_mp_mv_stop_at_zero(world):
    p = person("Ming")
    p.hp = p.panel["hp"] - 3
    affects.add(p, drip("heal", hp=10.0))
    affects.add(p, drip("drain", mp=-1000.0, mv=5.0))
    ticks(3)
    assert (p.hp, p.mp, p.mv) == (p.panel["hp"], 0.0, p.panel["mv"])


# ---- 扣死 ----

def test_hp_loss_kills_a_creature_out_of_a_fight(world):
    ming, npc = person("Ming"), creature()
    npc.hp = 5
    affects.add(npc, drip(hp=-10.0))
    ticks(3)
    assert npc not in characters
    [corpse] = world.rooms[101].contents
    assert corpse.item_type == CORPSE_NPC_ITEM_TYPE
    text = plain(ming)
    assert "生物1已經斷氣，倒在地上死亡了!!" in text and "經驗" not in text and ming.exp == 0   # 沒在打架：誰都不給經驗


def test_hp_loss_in_a_fight_counts_as_the_opponent_killing_it(world):
    ming, npc = person("Ming"), creature()

    async def run():
        fight.start_fight(ming, npc)
        npc.hp = 5
        affects.add(npc, drip(hp=-10.0))
        ticks(3)

    asyncio.run(run())
    amount = stats.kill_exp(ming.level, npc.level, npc.tier)
    assert npc not in characters and ming.exp == pytest.approx(amount)
    assert f"你共獲得了【{stats.shown(amount)}】點的經驗點數。" in plain(ming)
    assert ming.fighting is None


def test_hp_loss_kills_a_player(world):
    ming = person("Ming", room=102)
    ming.hp = 5
    affects.add(ming, drip("poison", hp=-10.0))
    affects.add(ming, Affect("bless", "祝福", 60, applies={"hit": 10.0}, keep_on_death=True))
    ticks(3)
    assert (ming.room.vnum, ming.hp) == (101, 1.0)                 # 照一般的死亡：回起始房間、HP 1
    assert [a.source for a in ming.affects] == ["bless"]           # 死掉後不在的拿掉，設定還在的留著
    assert "你已經含恨死去了" in plain(ming)


# ---- 時間到、世界 tick ----

def test_wearing_off_is_one_message(world):
    ming = person("Ming")
    affects.add(ming, Affect("a", "甲", 3, off_message="甲沒了。"))
    affects.add(ming, Affect("b", "乙", 3, off_message="乙沒了。"))
    affects.add(ming, Affect("c", "丙", 3))                         # 沒寫 off_message：不說
    plain(ming)
    ticks(3)
    text = plain(ming)
    assert ming.affects == [] and text.startswith("\r\n甲沒了。\r\n乙沒了。\r\n\r\n<HP ") and text.count("<HP") == 1


def test_world_tick_moves_everyone_once(world):
    ming, npc = person("Ming"), creature()
    affects.add(ming, drip())
    affects.add(npc, drip())
    world.tick()
    assert (ming.affects[0].ticks, npc.affects[0].ticks) == (59, 59)


def test_offline_players_stand_still(world):
    ming = person("Ming")
    affects.add(ming, drip())
    characters.remove(ming)                                         # 離線：不在 characters 裡
    ticks(5)
    assert ming.affects[0].ticks == 60


# ---- 死掉、存檔 ----

def test_on_death(world):
    ming = person("Ming")
    affects.add(ming, Affect("a", "甲", 60, applies={"hit": 1.0}))
    affects.add(ming, Affect("b", "乙", 60, applies={"hit": 2.0}, keep_on_death=True))
    hit = ming.panel["hit"]
    affects.on_death(ming)
    assert [a.source for a in ming.affects] == ["b"] and ming.panel["hit"] == hit - 1


def test_saved_and_continued_after_login(world):
    p = make_player_file("Ming")
    affects.add(p, drip("poison", hp=-1.0))
    affects.add(p, Affect("bless", "祝福", 60, applies={"hit": 10.0}, flags=AffectFlag.BLIND, keep_on_death=True))
    characters.append(p)
    ticks(2)
    characters.remove(p)
    save.save_player(p)
    q = save.player_from(save.load_data("Ming"), FakeWriter())
    assert q.affects == p.affects and q.panel["hit"] == p.panel["hit"]
    assert (q.affects[0].ticks, q.affects[0].elapsed, q.affects[1].flags) == (58, 2, AffectFlag.BLIND)
    characters.append(q)
    top = q.hp
    ticks(1)                                                        # 接著跑：第 3 tick 跳
    assert q.hp == top - 1


def test_old_saves_have_no_affects(world):
    make_player_file("Ming")
    data = save.load_data("Ming")
    del data["affects"]
    assert save.player_from(data, FakeWriter()).affects == []


# ---- 指令 ----

def test_affects_command(world):
    ming = person("Ming")
    assert say(ming, "affects") == "你身上沒有任何效果。"
    for which in ("poison", "bless", "blind"):
        affects.add(ming, Affect(**commands.imm.TEST_EFFECTS[which]))
    ticks(1)
    assert say(ming, "a") == ("你身上的效果：\r\n測試毒：還有 59 秒，每 3 秒 HP -10\r\n"
                              "測試祝福：還有 59 秒，命中 +10\r\n測試失明：還有 29 秒，失明")


def test_affects_shows_real_seconds_for_dwarves(world):
    ming = person("Ming", race=stats.Race.DWARF)
    affects.add(ming, drip(duration=11))
    assert say(ming, "affects") == "你身上的效果：\r\n滴：還有 6 秒，每 3 秒 HP -1"


def test_affects_while_asleep(world):
    ming = person("Ming")
    say(ming, "sleep")
    assert say(ming, "affects") == "你身上沒有任何效果。"


USAGE = "用法：effect <名字> <poison、regen、bless、blind、clear>"


@pytest.mark.parametrize("line", ["effect", "effect ming", "effect ming xyz"])
def test_effect_usage(world, line):
    assert say(person("Ming", imm=True), line) == USAGE


def test_effect_on_yourself(world):
    ming = person("Ming", imm=True)
    assert say(ming, "ef ming poison") == "你身上多了【測試毒】（60 秒）。"
    assert say(ming, "ef ming blind") == "你身上多了【測試失明】（30 秒）。"
    assert [a.name for a in ming.affects] == ["測試毒", "測試失明"]
    assert say(ming, "effect ming clear") == "你清掉了身上全部的效果。" and ming.affects == []


def test_effect_on_others(world):
    ming, hua = person("Ming", imm=True), person("Hua", room=102)   # 不在同房間：找線上的玩家
    plain(hua)
    assert say(ming, "effect hua bless") == "你讓Hua身上多了【測試祝福】（60 秒）。"
    assert "Ming讓你身上多了【測試祝福】（60 秒）。" in plain(hua)
    assert hua.affects[0].keep_on_death
    assert say(ming, "effect hua clear") == "你清掉了Hua身上全部的效果。"
    assert "Ming清掉了你身上全部的效果。" in plain(hua) and hua.affects == []


def test_effect_on_a_creature(world):
    ming, npc = person("Ming", imm=True), creature()
    assert say(ming, "effect mob1 regen") == "你讓生物1身上多了【測試回復】（60 秒）。"
    assert npc.affects[0].periodic == {"hp": 10.0}


def test_effect_not_found_and_not_imm(world):
    assert say(person("Ming", imm=True), "effect zzz poison") == "他們不在這兒。"
    assert say(person("Hua"), "effect hua poison") == "什麼？"


def test_mstat_lists_affects(world):
    ming = person("Ming", imm=True)
    npc = creature()
    assert say(ming, "mstat mob1").endswith("\r\n效果 無")
    affects.add(npc, Affect(**commands.imm.TEST_EFFECTS["poison"]))
    affects.add(npc, Affect(**commands.imm.TEST_EFFECTS["blind"]))
    assert say(ming, "mstat mob1").endswith("\r\n效果 測試毒：還有 60 秒，每 3 秒 HP -10；測試失明：還有 30 秒，失明")
    assert say(ming, "mstat ming").endswith("\r\n效果 無")


# ---- 手冊 ----

def test_flag_names_match_the_manual():
    text = AREA_MANUAL.read_text(encoding="utf-8")
    part = text[text.index("### affected_by（身上的效果）"):text.index("### race（種族）")]
    rows = {int(n): meaning for n, _, meaning in re.findall(r"\| (\d+) \| (\w+) \| (\S+) \|", part)}
    assert rows == {int(f): AFFECT_FLAG_NAMES[f] for f in AffectFlag}
