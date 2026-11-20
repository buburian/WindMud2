"""旅具（物品的 travel_effect，設計文件 §3.12，使用者 2026-11-20 定的，區域製作手冊「travel_effect」、玩家角色手冊「旅具」）：
區域檔的寫法和檢查（代號、只有光源和持握、魔杖魔棒不行）、手冊的表跟程式的定義一樣、test.json 的範例；
遊戲裡的效果（每種的量、打架中沒有、一樣的加起來、灰色和 null 沒有）、不燒完、examine 的詩、score 的數字、價錢、存檔、淬火石、母狼的掉落。
"""
import json
import re
from pathlib import Path

import pytest

import mud.commands as commands
from area_helpers import make_object, make_room, write_area
from mud import affects, area, behavior, death, inventory, light, objects, save, stats, travel, zones
from mud.area import TravelEffect
from mud.characters import Position, characters
from mud.color import colorize
from mud.config import ENCODING, TRAVEL_TICKS
from mud.players import Player

ROOT = Path(__file__).resolve().parent.parent
MANUAL = ROOT / "docs" / "區域製作手冊.md"
AREAS = ROOT / "areas"
LAMP = 115                                  # test.json 的測試油燈（照明用具、rest_res）


def item(item_type, wear_flags, effect="rest_res", affects=()):
    o = make_object(101)
    o.update(item_type=item_type, wear_flags=wear_flags, values=[0, 0, 0, 0], affects=list(affects), travel_effect=effect)
    o["script"] = None
    return o


@pytest.mark.parametrize("o, want", [
    (item(1, 1), None),                                         # 照明用具：一定放光源的位置
    (item(1, "1|16384"), None),                                 # 燈籠寫了持握也是光源
    (item(8, "1|16384"), None),                                 # 持握的寶藏
    (item(9, "1|16384", "carry"), None),                        # 持握的護具，每種代號都可以
    (item(8, "1|16384", None), None),                           # null：普通的持握
    (item(8, "1|16384", "heal"), "travel_effect 要寫 regen、rest_hp"),     # 不認得的代號
    (item(8, "1|16384", ""), "travel_effect 要寫"),
    (item(9, "1|2"), "穿在戒指：只有照明用具"),                 # 戒指不行
    (item(9, "1|16|16384"), "穿在頭：只有照明用具"),            # 好幾個部位：照上限最大的那個（跟穿上去一樣），不是持握
    (item(8, 1), "沒有穿戴部位：只有照明用具"),                 # 不能穿的東西
    (item(3, "1|16384"), "是魔杖，會用掉、用完就不見了"),       # 會用掉的東西不行（mud_design 2026-11-20 從魔杖、魔棒擴大的）
    (item(4, "1|16384"), "是魔棒，會用掉"),
    (item(2, "1|16384"), "是卷軸，會用掉"),
    (item(10, "1|16384"), "是藥水，會用掉"),
    (item(26, "1|16384"), "是藥錠，會用掉"),
    (item(19, "1|16384"), "是食物，會用掉"),
    (item(17, "1|16384"), None),                                # 液體容器喝完還在（空的），可以
])
def test_area_check(o, want):
    if o["item_type"] in area.CHARGED_ITEM_TYPES:
        o["values"] = [0, 3, 3, "fly"]                          # 寫好技能、口數、液體，只剩旅具的問題
    elif o["item_type"] in area.SKILL_ITEM_TYPES:
        o["values"] = [0, "fly", "", ""]
    elif o["item_type"] == area.FOOD_ITEM_TYPE:
        o["values"] = [1, "", 0, 0]
    elif o["item_type"] == area.DRINK_CON_ITEM_TYPE:
        o["values"] = [5, 5, 0, 0]
    problems = []
    area.check_object("物品 101", o, problems)
    if want is None:
        assert problems == []
    else:
        assert len(problems) == 1 and want in problems[0], problems


def test_every_object_needs_the_field():
    o = make_object(101)
    del o["travel_effect"]
    problems = []
    area.check_objects("x.json", {"objects": [o]}, (100, 199), problems)
    assert any("travel_effect" in p for p in problems), problems


def manual_codes():
    rows, text = [], MANUAL.read_text(encoding="utf-8").split("### travel_effect（旅具效果）", 1)[1]
    for line in text.splitlines():
        if line.startswith("|"):
            rows.append(line.strip("|").split("|")[0].strip())
        elif rows:
            break
    return rows[2:]


def test_manual_table_matches_the_codes():
    assert manual_codes() == [c.value for c in TravelEffect]


def test_test_area_has_an_example():
    # test.json 的物品 115「測試油燈」：照明用具、rest_res（給 oload 試，不在重置裡）
    data =json.loads((ROOT / "areas" / "test.json").read_text(encoding="utf-8"))
    lamp = next(o for o in data["objects"] if o["vnum"] == 115)
    assert lamp["item_type"] == area.LIGHT_ITEM_TYPE and lamp["travel_effect"] == TravelEffect.REST_RES
    assert all("travel_effect" in o for o in data["objects"])


# ---- 遊戲裡的效果（用真的 areas/：test.json 的物品 115 測試油燈、城西森林的獵戶的舊油燈）----

class Never:
    """生物行為的骰子：永遠不中（不走動、不撿東西）。"""

    def random(self):
        return 0.99

    def choice(self, seq):
        return seq[0]


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path)
    zones.load(AREAS)
    yield
    characters.clear()
    zones.stop()


def player(level=10, guild=stats.Guild.SWORD, race=stats.Race.HUMAN):
    p = Player("Ming", FakeWriter(), zones.world.rooms[101])
    p.race, p.guild = race, guild
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    stats.set_level(p, level)
    characters.append(p)
    return p


def lamp(level=10, color="white", effect="rest_res"):
    obj = objects.create(LAMP, level, color)
    obj.travel_effect = effect
    return obj


def say(p, line):
    p.writer.data = b""
    commands.command(p, line)
    return p.writer.data.decode(ENCODING).rsplit("\r\n\r\n", 1)[0]


def plain(text):
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.mark.parametrize("effect, base, want", [
    # mud_design 給的 Lv10 白色的量（設計文件 §3.12 的表）
    ("regen", None, 1), ("rest_hp", None, 11), ("rest_res", None, 6),
    ("meal", "hp", 17), ("meal", "res", 9), ("carry", None, 20), ("revive", None, 57),
])
def test_amounts_at_level_10_white(world, effect, base, want):
    p = player()
    assert travel.amount(p, lamp(10, "white", effect), effect, base) == want


def test_amounts_follow_level_and_color(world):
    p = player(30)
    assert travel.amount(p, lamp(5, "white"), "rest_res") == 5                  # 5 級白色：資源(5) 大約 45 × 10%
    assert travel.amount(p, lamp(10, "orange", "rest_hp"), "rest_hp") == 16     # 114.3 × 10% × 1.4
    assert travel.amount(p, lamp(10, "blue", "carry"), "carry") == 24           # L × 2 × 顏色加成
    assert travel.amount(p, lamp(1, "white", "regen"), "regen") == 1            # 最少 1
    staff = player(10, stats.Guild.STAFF)
    assert travel.amount(staff, lamp(10, "white", "regen"), "regen") == 1       # 杖之公會的資源（MP）一樣多


@pytest.mark.parametrize("color", [None, "gray"])
def test_gray_or_no_color_has_no_effect(world, color):
    obj = lamp(10, color)
    assert travel.effect_of(obj) is None and travel.poem(obj) is None
    p = player()
    p.equipment["light"] = obj
    assert travel.worn(p) == [] and travel.carry(p) == 0


def test_regen_every_10_seconds_when_not_fighting(world):
    p = player()
    p.equipment["light"] = lamp(10, "white", "regen")
    p.mv = 0.0
    travel.tick()
    assert p.mv == 1
    p.fighting = object()                   # 打架中沒有作用
    travel.tick()
    assert p.mv == 1
    p.fighting = None
    p.mv = p.panel["mv"] - 0.5              # 不超過上限
    travel.tick()
    assert p.mv == p.panel["mv"]

def test_world_tick_runs_it(world, monkeypatch):
    monkeypatch.setattr(behavior, "rng", Never())          # 坑：世界的 tick 會跑生物的行為，不讓牠們走動、撿東西
    p = player()
    p.equipment["light"] = lamp(10, "white", "regen")
    p.mv, zones.world.ticks = 0.0, TRAVEL_TICKS - 1         # 世界的 tick 每 TRAVEL_TICKS 叫它一次
    zones.world.tick()
    assert p.mv == 1
    zones.world.tick()
    assert p.mv == 1


def regen_gain(p, key, position, worn=None, meal=None):
    p.equipment = {"light": worn} if worn else {}
    p.position, p.meal_bonus = position, dict(meal or {})
    setattr(p, key, 0.0)
    stats.regen(p)
    return getattr(p, key)


@pytest.mark.parametrize("position", [Position.RESTING, Position.SLEEPING])
def test_rest_effects_add_to_regen(world, position):
    p = player()
    assert regen_gain(p, "mv", position, lamp(10, "white", "rest_res")) - regen_gain(p, "mv", position) == pytest.approx(6)
    assert regen_gain(p, "hp", position, lamp(10, "white", "rest_hp")) - regen_gain(p, "hp", position) == pytest.approx(11)
    assert regen_gain(p, "hp", position, lamp(10, "white", "rest_res")) == regen_gain(p, "hp", position)   # 只回自己那一項


def test_rest_effects_only_when_resting(world):
    p = player()
    assert regen_gain(p, "mv", Position.STANDING, lamp(10, "white", "rest_res")) == regen_gain(p, "mv", Position.STANDING)


def test_meal_effect_when_eating_or_drinking_works(world):
    p = player()
    meal = lamp(10, "white", "meal")
    r = Position.RESTING
    assert regen_gain(p, "hp", r, meal, {"hp": 2}) - regen_gain(p, "hp", r, None, {"hp": 2}) == pytest.approx(17)   # 吃的：HP
    assert regen_gain(p, "mv", r, meal, {"mv": 2}) - regen_gain(p, "mv", r, None, {"mv": 2}) == pytest.approx(9)    # 喝的：自己公會的資源
    assert regen_gain(p, "hp", r, meal) == regen_gain(p, "hp", r)                                                 # 沒吃喝：沒有


def test_two_of_the_same_add_up(world):
    p = player()
    p.equipment = {"light": lamp(10, "white", "carry"), "hold": lamp(10, "blue", "carry")}
    assert travel.carry(p) == 20 + 24


def test_carry_raises_the_weight_limit(world):
    p = player()
    before = stats.carry_limit(p)
    p.equipment["light"] = lamp(10, "white", "carry")
    assert stats.carry_limit(p) == before + 20


def poison():
    return affects.Affect(source="spec_poison", name="劇毒", duration=30, periodic={"hp": -1})


def test_cure_makes_poison_wear_off_faster(world):
    p = player()
    a = poison()
    assert affects.step(p, a) == 1
    p.equipment["light"] = lamp(10, "white", "cure")
    assert affects.step(p, a) == 2
    assert affects.seconds_left(p, a) == 15                     # 30 秒的毒，看到的剩下時間也跟著減半
    p.equipment["hold"] = lamp(1, "gray", "cure")               # 灰色的沒有作用
    assert affects.step(p, a) == 2
    p.equipment["hold"] = lamp(1, "white", "cure")              # 兩件都是：每 tick 多減 2（不看等級）
    assert affects.step(p, a) == 3
    p.fighting = object()                                       # 打架中沒有作用
    assert affects.step(p, a) == 1
    p.fighting = None
    regen = affects.Affect(source="gift", name="餽贈", duration=30, periodic_pct={"hp": 0.1})
    assert affects.step(p, regen) == 1                          # 不是扣血的不管


def test_cure_stacks_with_dwarf_toughness(world):
    p = player(race=stats.Race.DWARF)
    p.equipment["light"] = lamp(10, "white", "cure")
    assert affects.step(p, poison()) == affects.TOUGH_STEP + 1


def test_revive_after_death(world):
    p = player()
    p.hp = 0.0
    death.player_dies(p)
    assert p.hp == 1                                            # 沒有旅具：剩 1
    p.equipment["light"] = lamp(10, "white", "revive")
    death.player_dies(p)
    assert p.hp == 57
    p.equipment["light"] = lamp(80, "orange", "revive")        # 不超過自己的上限
    death.player_dies(p)
    assert p.hp == p.panel["hp"]


def test_travel_lights_do_not_burn_out(world):
    p = player()
    p.equipment["light"] = obj = lamp()
    obj.hours = 1
    light.burn()
    assert p.equipment["light"] is obj and obj.hours == 1      # 旅具不燒
    p.equipment["light"] = gray = lamp(10, "gray")              # 沒有效果的照普通照明用具燒完
    gray.hours = 1
    light.burn()
    assert "light" not in p.equipment


def test_examine_shows_only_the_poem(world):
    p = player()
    p.carrying = [lamp(10, "blue")]
    raw = say(p, "exam lamp")
    assert "旅具：" + colorize("{B靜坐閉目聽夜雨，一宵養足滿懷神。{x") in raw                 # 顏色照稀有度（藍）
    assert not re.search(r"旅具.*\d", plain(raw))                                             # 不寫數字
    p.carrying = [lamp(10, "gray")]
    assert "旅具" not in say(p, "exam lamp")


@pytest.mark.parametrize("guild, res", [(stats.Guild.SWORD, "MV"), (stats.Guild.STAFF, "MP")])
def test_score_shows_the_numbers(world, guild, res):
    p = player(10, guild)
    assert "旅具效果" not in plain(say(p, "score"))                                           # 沒穿就沒有這一段
    p.equipment["light"] = objects.create(10108, 5, "white")                                 # 母狼掉的：5 級白色
    lines = plain(say(p, "score")).split("\r\n")
    i = lines.index(" 旅具效果：")
    assert lines[i + 1] == f" 【照明用具】多回 {res}：休息、睡覺時每 30 秒 +5"


def test_score_lines_fit(world):
    p = player()
    for effect in TravelEffect:
        line = " " + travel.score_line(p, "手中握著", lamp(100, "orange", effect), effect)
        assert len(line.encode(ENCODING)) <= 79, line


def test_texts_are_big5():
    for name_and_text in travel.EFFECTS.values():
        for text in name_and_text[2:]:
            text.encode(ENCODING)


def test_price_is_a_ring_of_the_same_level_and_color(world):
    assert stats.shown(objects.base_price(lamp(5, "white"))) == 4          # mud_design 算的：5 級白色 4 枚
    assert stats.shown(objects.base_price(lamp(10, "white"))) == 6
    assert stats.shown(objects.base_price(lamp(50, "orange"))) == 180
    assert objects.base_price(lamp(50, "gray")) == 1                       # 沒有效果：照舊
    unrolled = objects.create(LAMP, 5, "white", for_sale=True)             # 店裡還沒抽的
    assert stats.shown(objects.full_price(unrolled, 5)) == 4


def test_saved_and_old_saves(world):
    data = objects.to_data(lamp(10, "white", "carry"))
    assert objects.from_data(data).travel_effect == "carry"
    del data["travel_effect"]                                              # 舊存檔沒有：不是旅具
    assert objects.from_data(data).travel_effect is None


def test_cannot_temper(world):
    p = player(20)
    p.temper_stones = 1
    p.carrying = [lamp(10, "white")]
    say(p, "wear lamp")
    assert plain(say(p, "use temper lamp")).endswith("不能淬火。")
    assert p.temper_stones == 1


def test_a_real_hold_item(tmp_path, monkeypatch):
    # 真的持握物品（wear_flags 16384）：做出來是持握、wear 穿到手中握著、score 寫【手中握著】、跟光源一樣的加起來
    held = dict(make_object(150), keywords="charm", short="護身符", item_type=8, wear_flags="1|16384", values=[0, 0, 0, 0],
                affects=[], travel_effect="carry", extra_descriptions=[], script=None)
    light_obj = dict(make_object(151), keywords="lamp", short="燈", item_type=1, wear_flags=1, values=[0, 0, -1, 0],
                     affects=[], travel_effect="carry", extra_descriptions=[], script=None)
    write_area(tmp_path, "a.json", [make_room(101)], objects=[held, light_obj])
    monkeypatch.setattr(zones, "START_ROOM", 101)
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path)
    zones.load(tmp_path)
    try:
        p = player()
        p.carrying = [objects.create(150, 10, "white"), objects.create(151, 10, "blue")]
        say(p, "wear charm")
        say(p, "wear lamp")
        assert p.equipment["hold"].vnum == 150 and p.equipment["light"].vnum == 151
        assert travel.carry(p) == 20 + 24
        lines = plain(say(p, "score")).split("\r\n")
        assert lines[-2:] == [" 【照明用具】背得多：負重上限 +24", " 【手中握著】背得多：負重上限 +20"]
    finally:
        characters.clear()
        zones.stop()


def test_slot_names_match_equipment():
    assert all(dict(inventory.SLOTS)[pos] == label for pos, label in travel.SLOTS)


def test_wear_it_and_it_is_not_an_affect(world):
    p = player()
    p.carrying = [lamp(10, "white", "carry")]
    say(p, "wear lamp")
    assert travel.carry(p) == 20 and p.affects == []


def test_the_hunters_lamp_drops_from_the_she_wolf(world):
    from mud import resets
    assert {"obj_vnum": 10108, "color": "white", "chance": 9000, "tiers": None} in resets.mobiles[10101]["drops"]
    proto = objects.protos[10108]
    assert (proto["item_type"], proto["travel_effect"], proto["values"][2]) == (area.LIGHT_ITEM_TYPE, "rest_res", -1)
    for text in (proto["short"], proto["long"], proto["extra_descriptions"][0]["description"]):
        text.encode(ENCODING)
