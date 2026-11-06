"""身上的效果（affects.py，玩家角色手冊「身上的效果」）：覆蓋和疊加、暫時加減屬性、持續加減 HP／MP／MV（每 3 tick、矮人的堅韌、扣死）、
時間到消失、死掉、存檔，score 最下面那段、imm 的 affect、mstat 那一行，旗標的中文跟手冊比對。

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


# ---- 上限的幾成（periodic_pct） ----

def test_pct_follows_the_top_at_each_jump(world):
    p = person("Ming")
    top = p.panel["hp"]
    p.hp = 10.0
    affects.add(p, Affect("r", "回", 60, periodic_pct={"hp": 0.10}))
    ticks(2)
    assert p.hp == 10.0                                             # 放下去那一刻、第 1、2 tick 不跳
    ticks(1)
    assert p.hp == pytest.approx(10.0 + top * 0.10)
    affects.add(p, Affect("big", "大", 60, applies={"hp": 100.0}))  # 上限變了：下一跳照新的上限算
    ticks(3)
    assert p.hp == pytest.approx(10.0 + top * 0.10 + (top + 100) * 0.10)


def test_pct_stops_at_the_top_and_can_kill(world):
    p, npc = person("Ming"), creature()
    p.hp = p.panel["hp"] - 1
    affects.add(p, Affect("r", "回", 60, periodic_pct={"hp": 0.10}))
    npc.hp = 5
    affects.add(npc, Affect("rot", "爛", 60, periodic_pct={"hp": -0.10}))
    ticks(3)
    assert p.hp == p.panel["hp"] and npc not in characters          # 補不超過上限；扣的一樣會扣死


def test_pct_and_dwarves(world):
    p = person("Ming", race=stats.Race.DWARF)
    affects.add(p, Affect("rot", "爛", 60, periodic_pct={"hp": -0.01}))
    affects.add(p, Affect("r", "回", 60, periodic_pct={"hp": 0.10}))
    ticks(1)
    assert [a.ticks for a in p.affects] == [58, 59]                 # 扣 HP 的（幾成也算）矮人減 2


def test_pct_text_and_save():
    a = Affect("x", "混", 60, periodic_pct={"hp": 0.10, "mp": -0.05})
    assert affects.parts(a) == ["每 3 秒 HP +上限的 10%", "每 3 秒 MP -上限的 5%"]
    assert affects.from_data(affects.to_data(a)) == a
    old = affects.to_data(Affect("x", "舊", 60))
    del old["periodic_pct"]                                         # 加這個欄位以前存的
    assert affects.from_data(old).periodic_pct == {}


# ---- 加主屬性（換算用被放的人自己的等級） ----

def test_primary_applies_use_your_own_level(world):
    p = person("Ming")
    stats.set_level(p, 30)
    before, carry, mp = dict(p.panel), stats.carry_limit(p), p.panel["mp"]
    affects.add(p, Affect("s", "力", 60, applies={"str": 3.0}))
    bundle = stats.primary_bundle(p.guild, "str", 30)
    assert bundle != stats.primary_bundle(p.guild, "str", 1)
    for k, v in p.panel.items():
        assert v == pytest.approx(before[k] + 3 * bundle.get(k, 0.0)), k
    assert p.primaries["str"] == 14 - 2 and stats.carry_limit(p) == carry and p.panel["mp"] == mp   # 負重、MP 不變
    assert " 力量  15   智慧  12 " in say(p, "score")               # score 的主屬性算進去（整數，不是 15.0）
    p.imm = True
    assert "主屬性 力量 15（12＋3）" in say(p, "mstat ming")                 # mstat 也是（括號裡是自己的＋加的）
    affects.remove(p, "s")
    assert p.panel == pytest.approx(before)


def test_creatures_ignore_primary_applies(world):
    npc = creature()
    affects.add(npc, Affect("s", "力", 60, applies={"str": 3.0}))
    assert npc.panel == npc.base_panel


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
    affects.add(ming, Affect("c", "丙", 3))                         # 沒寫 off_message：用共用的那句（使用者要的）
    plain(ming)
    ticks(3)
    text = plain(ming)
    assert ming.affects == [] and text.startswith("\r\n甲沒了。\r\n乙沒了。\r\n你身上的【丙】消失了。\r\n\r\n<HP ")
    assert text.count("<HP") == 1


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

def score_tail(p):
    """score 最下面那條粗線之後的每一行（沒有效果就是空的）。"""
    lines = say(p, "score").split("\r\n")
    return lines[lines.index("=" * 79, 1) + 1:]


def test_score_lists_affects(world):
    # 照 C 版放在 score 最下面：【名字】、做什麼、還有幾秒
    ming = person("Ming")
    assert score_tail(ming) == []                                   # 沒有效果：沒有這一段
    for which in ("poison", "bless", "blind"):
        affects.add(ming, Affect(**commands.imm.TEST_EFFECTS[which]))
    affects.add(ming, Affect("mix", "混合", 30, applies={"hit": 5.0}, periodic={"mv": -2.0}))
    ticks(1)
    assert score_tail(ming) == [
        " 你受到下列效果的影響：",
        " 【      測試毒】 每 3 秒 HP -10                              還有    59 秒",
        " 【    測試祝福】 命中 +10                                    還有    59 秒",
        " 【    測試失明】 失明                                        還有    29 秒",
        " 【        混合】 每 3 秒 MV -2、命中 +5                      還有    29 秒",
    ]


def test_score_shows_real_seconds_for_dwarves(world):
    ming = person("Ming", race=stats.Race.DWARF)
    affects.add(ming, drip(duration=11))
    assert score_tail(ming)[1] == " 【          滴】 每 3 秒 HP -1                               還有     6 秒"


def test_no_affects_command(world):
    assert say(person("Ming"), "affects") == "什麼？"                # 看 score 就好（使用者要的）


USAGE = "用法：affect <名字> <poison、regen、bless、blind、shield、clear>"


@pytest.mark.parametrize("line", ["affect", "affect ming", "affect ming xyz"])
def test_affect_usage(world, line):
    assert say(person("Ming", imm=True), line) == USAGE


def test_affect_on_yourself(world):
    ming = person("Ming", imm=True)
    assert say(ming, "af ming poison") == "你身上多了【測試毒】（60 秒）。"
    assert say(ming, "af ming blind") == "你身上多了【測試失明】（30 秒）。"
    assert [a.name for a in ming.affects] == ["測試毒", "測試失明"]
    assert say(ming, "affect ming clear") == "你清掉了身上全部的效果。" and ming.affects == []


def test_affect_on_others(world):
    ming, hua = person("Ming", imm=True), person("Hua", room=102)   # 不在同房間：找線上的玩家
    plain(hua)
    assert say(ming, "affect hua bless") == "你讓Hua身上多了【測試祝福】（60 秒）。"
    assert "Ming讓你身上多了【測試祝福】（60 秒）。" in plain(hua)
    assert hua.affects[0].keep_on_death
    assert say(ming, "affect hua clear") == "你清掉了Hua身上全部的效果。"
    assert "Ming清掉了你身上全部的效果。" in plain(hua) and hua.affects == []


def test_affect_on_a_creature(world):
    ming, npc = person("Ming", imm=True), creature()
    assert say(ming, "affect mob1 regen") == "你讓生物1身上多了【測試回復】（60 秒）。"
    assert npc.affects[0].periodic == {"hp": 10.0}


def test_affect_not_found_and_not_imm(world):
    assert say(person("Ming", imm=True), "affect zzz poison") == "他們不在這兒。"
    assert say(person("Hua"), "affect hua poison") == "什麼？"


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


# ---- 護盾（使用者 2026-11-06 定的）：HP 上限的幾 %，受到的傷害先扣它，扣光就破 ----

class Out:
    """收 combat.land() 的訊息（代替那一場的 Fight）。"""

    def __init__(self):
        self.pairs = []

    def tell(self, pairs):
        self.pairs += pairs

    def text_for(self, reader):
        return "\n".join(re.sub(r"\x1b\[[0-9;]*m", "", t) for r, t in self.pairs if r is reader)


def shield(source="shield", pct=1.2, duration=10):
    return Affect(source, "盾", duration, shield_pct=pct, off_message="盾沒了。")


def test_shield_points_come_from_the_hp_top_when_cast(world):
    ming = person("Ming")
    top = ming.panel["hp"]
    affects.add(ming, shield())
    assert ming.affects[0].shield == pytest.approx(top * 1.2)       # 100 HP、120% 是 120 點


def test_damage_hits_the_shield_first(world):
    ming, mob = person("Ming"), creature()
    top = ming.panel["hp"]
    affects.add(ming, shield())
    out = Out()
    assert combat.land(out, mob, ming, 50.0, False) is False
    assert ming.hp == top and ming.affects[0].shield == pytest.approx(top * 1.2 - 50)   # HP 不動
    assert "（吸收 50）" in out.text_for(ming)
    out = Out()
    combat.land(out, mob, ming, top * 1.2 - 50 + 30, False)         # 盾剩下的 ＋ 30：盾破了，HP 扣 30
    assert ming.hp == pytest.approx(top - 30) and ming.affects == []
    assert out.text_for(ming).endswith("你的【盾】被打破了。")
    out = Out()
    combat.land(out, mob, ming, 5.0, False)                          # 沒有盾了：照舊
    assert ming.hp == pytest.approx(top - 35) and "吸收" not in out.text_for(ming)


def test_absorbed_is_in_all_three_messages(world):
    ming, mob = person("Ming"), creature()
    hua = person("Hua")
    affects.add(ming, shield())
    out = Out()
    combat.land(out, mob, ming, 5.0, False)
    assert out.text_for(ming).endswith(".(5)（吸收 5）") and out.text_for(hua).endswith(".(5)（吸收 5）")
    out = Out()
    combat.land(out, ming, mob, 5.0, False)                          # 打沒有盾的：照舊
    assert out.text_for(ming).endswith(".(5)")


def test_casting_again_refills_the_shield(world):
    ming = person("Ming")
    top = ming.panel["hp"]
    affects.add(ming, shield())
    affects.absorb(ming, 100.0)
    ticks(4)
    affects.add(ming, shield())                                      # 再放一次：回到滿的、10 秒
    assert len(ming.affects) == 1 and ming.affects[0].shield == pytest.approx(top * 1.2) and ming.affects[0].ticks == 10


def test_shield_wears_off(world):
    ming = person("Ming")
    affects.add(ming, shield())
    plain(ming)
    ticks(10)
    assert ming.affects == [] and "盾沒了。" in plain(ming)


def test_older_shields_go_first(world):
    ming = person("Ming")
    top = ming.panel["hp"]
    affects.add(ming, shield("a", 0.1))
    affects.add(ming, shield("b", 0.1))
    taken, broken = affects.absorb(ming, top * 0.1 + 3)              # 先放的扣光、破掉，後放的扣 3
    assert taken == pytest.approx(top * 0.1 + 3) and [a.source for a in broken] == ["a"]
    assert [a.source for a in ming.affects] == ["b"] and ming.affects[0].shield == pytest.approx(top * 0.1 - 3)


def test_hp_loss_over_time_hits_the_shield_first(world):
    ming = person("Ming")
    top = ming.panel["hp"]
    affects.add(ming, shield(pct=4 / top))                           # 4 點的盾
    affects.add(ming, drip(hp=-10.0))
    plain(ming)
    ticks(3)                                                         # 毒跳一次 -10：盾吸收 4、破掉，HP 扣 6
    assert ming.hp == pytest.approx(top - 6) and [a.source for a in ming.affects] == ["drip"]
    assert "你的【盾】被打破了。" in plain(ming)
    ticks(3)
    assert ming.hp == pytest.approx(top - 16)


def test_shield_shows_how_much_is_left(world):
    ming = person("Ming", imm=True)
    affects.add(ming, shield())
    affects.absorb(ming, 10.0)
    left = stats.shown(ming.panel["hp"] * 1.2 - 10)
    assert f"護盾還剩 {left} 點" in say(ming, "score")
    assert f"盾：還有 10 秒，護盾還剩 {left} 點" in say(ming, "mstat ming")


def test_shield_is_saved(world):
    a = shield()
    a.shield = 37.5
    back = affects.from_data(affects.to_data(a))
    assert (back.shield_pct, back.shield) == (1.2, 37.5)
    old = {k: v for k, v in affects.to_data(drip()).items() if k not in ("shield_pct", "shield")}   # 舊存檔沒有這兩個欄位
    assert affects.from_data(old).shield == 0.0


def test_affect_shield(world):
    ming = person("Ming", imm=True)
    assert say(ming, "af ming shield") == "你身上多了【測試護盾】（10 秒）。"
    assert ming.affects[0].shield == pytest.approx(ming.panel["hp"] * 1.2)
