"""套裝（sets.py、area.check_sets()，使用者 2026-11-20 定的，設計文件 §3.4 第 7 條）。

區域檔檢查用自己做的資料夾（寫 sets.json）；做出來、特效、淬火石、examine、存檔用真的 areas/：
測試套裝（test.json 的 113 頭盔、114 靴子，5 級，加 HP）和紅布獵手（城北平原 99806、99807，12 級，加命中）。
"""
import json
import math
import re
from pathlib import Path

import pytest

import mud.commands as commands
from area_helpers import make_area, make_mobile, make_object, make_room, write_json
from mud import area, equipment, objects, save, sets, stats, zones
from mud.area import ExtraFlag
from mud.characters import characters
from mud.config import ENCODING
from mud.players import Player

AREAS = Path(__file__).resolve().parent.parent / "areas"
HELM, BOOTS = 113, 114                      # 測試套裝


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


# ---- 區域檔檢查 ----

def piece(vnum, wear="1|16"):
    return dict(make_object(vnum), item_type=9, wear_flags=wear, values=[0, 0, 0, 0], affects=[], extra_descriptions=[], script=None)


def folder_with(tmp_path, set_list, objs=None, mobiles=(), resets=()):
    """一個區域檔（物品 101 頭盔、102 靴子、103 藥水）加 sets.json，回傳 (區域檔, sets.json) 的問題。"""
    objs = objs if objs is not None else [piece(101), piece(102, "1|64"), dict(make_object(103), item_type=10, wear_flags="1",
                                                                              values=[0, "fly", "", ""], affects=[])]
    path = write_json(tmp_path, "a.json", make_area("a.json", [make_room(101)], objects=objs, mobiles=list(mobiles), resets=list(resets)))
    write_json(tmp_path, area.SET_FILE, {"sets": set_list})
    found = area.check_files([path], area.area_files(tmp_path))
    return found[path], found[tmp_path / area.SET_FILE]


GOOD = {"name": "測試", "level": 5, "items": [101, 102], "bonus": "hp"}


def test_a_good_set(tmp_path):
    assert folder_with(tmp_path, [GOOD]) == ([], [])
    assert area.area_files(tmp_path) == [tmp_path / "a.json"]                      # sets.json 不是區域檔


@pytest.mark.parametrize("change, want", [
    (dict(name=" "), "第 1 套的 name 不能是空的"),
    (dict(name="龍🐉"), "的 name 有轉不成 Big5 的字"),
    (dict(level=0), "套裝「測試」的 level 要是 1 以上的整數，不能是 0"),
    (dict(bonus="luck"), "套裝「測試」的 bonus 要寫屬性的代號"),
    (dict(items=[101]), "套裝「測試」的 items 要寫至少 2 件"),
    (dict(items=[101, 101]), "套裝「測試」的 items 要寫至少 2 件、不重複的物品號碼"),
    (dict(items=[101, 199]), "套裝「測試」的物品 199 不存在"),
    (dict(items=[101, 103]), "套裝「測試」的物品 103「物品103」不是裝備"),
    (dict(extra=1), "第 1 套 多了不認得的欄位 extra"),
])
def test_set_table_rules(tmp_path, change, want):
    _area, found = folder_with(tmp_path, [dict(GOOD, **change)])
    assert any(want in p for p in found), found


def test_one_piece_one_set_and_names_once(tmp_path):
    _area, found = folder_with(tmp_path, [GOOD, dict(GOOD, items=[102, 101])])
    assert any("套裝「測試」重複了" in p for p in found)
    assert any("物品 102 已經在套裝「測試」裡了：一件物品只能在一套裡" in p for p in found)


def test_bind_on_equip_is_not_allowed(tmp_path):
    objs = [dict(piece(101), extra_flags=int(ExtraFlag.BIND_EQUIP)), piece(102, "1|64")]
    _area, found = folder_with(tmp_path, [GOOD], objs)
    assert any("勾了 2048 裝備後綁定：套裝一律拾取後綁定" in p for p in found)


def drop(vnum, color):
    return {"obj_vnum": vnum, "color": color, "chance": 1000, "tiers": None}


@pytest.mark.parametrize("level, color, want", [
    (5, "green", None),
    (5, "purple", "物品 101 是套裝「測試」的，color 要寫 green，不能是 'purple'"),
    (4, "green", "掉套裝「測試」的物品 101：生物是 4 級，要至少套裝的 5 級"),
])
def test_where_set_pieces_drop(tmp_path, level, color, want):
    mob = dict(make_mobile(101), level=level, drops=[drop(101, color)], shop=None, special=None)
    found, _sets = folder_with(tmp_path, [GOOD], mobiles=[mob])
    if want is None:
        assert [p for p in found if "套裝" in p] == [], found
    else:
        assert any(want in p for p in found), found


def test_green_is_only_for_sets(tmp_path):
    reset = {"cmd": "O", "if_flag": 0, "obj_vnum": 103, "color": "green", "level": 1, "limit": 0, "room_vnum": 101, "comment": ""}
    found, _sets = folder_with(tmp_path, [GOOD], resets=[reset])
    assert any("color 寫了 green，但物品 103 不在套裝表裡：green 只給套裝用" in p for p in found)


def test_no_set_table_means_no_sets(tmp_path):
    mob = dict(make_mobile(101), drops=[drop(101, "green")], shop=None, special=None)
    path = write_json(tmp_path, "a.json", make_area("a.json", [make_room(101)], objects=[piece(101)], mobiles=[mob]))
    found = area.check_files([path], [path])
    assert any("green 只給套裝用" in p for p in found[path]) and set(found) == {path}


# ---- 真的區域：做出來、特效、淬火石、examine、存檔 ----

@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path)
    zones.load(AREAS)
    yield
    characters.clear()
    zones.stop()


def player(level=10):
    p = Player("Ming", FakeWriter(), zones.world.rooms[101])
    p.race, p.guild = stats.Race.HUMAN, stats.Guild.SWORD
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    stats.set_level(p, level)
    characters.append(p)
    return p


def say(p, line):
    p.writer.data = b""
    commands.command(p, line)
    return re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING)).rsplit("\r\n\r\n", 1)[0]


def test_set_pieces_are_green_bound_and_named(world):
    helm = objects.create(HELM, 40, "white")                                     # 放出它的地方寫什麼都一樣
    assert (helm.level, helm.color, objects.bound(helm)) == (5, "green", True)
    assert helm.name.startswith("〔測試套裝〕") and helm.name.endswith("測試套裝頭盔")
    assert objects.short(helm).startswith("\x1b[32m")                            # 暗綠
    plain = objects.create(108, 5, "purple")                                     # 不是套裝的照舊
    assert plain.color == "purple" and not plain.name.startswith("〔")


def test_red_cloth_hunter_is_hit_plus_6(world):
    s = sets.set_of(99806)
    assert (s.name, s.level, s.items, s.bonus) == ("紅布獵手", 12, (99806, 99807), "hit") and sets.set_of(99807) is s
    assert sets.strength(s) == 6                                                 # 12 級戒指 5.04 × 1.3 ＝ 6.55，兩件 × 50% 捨去
    ring = objects.protos[99806]
    budget = equipment.cap(12, equipment.best_slot(*area.wear_slots(ring))) * equipment.COLOR_BONUS["green"]
    assert sets.piece_points(ring, 12) == pytest.approx(budget * 1.3)
    for _ in range(20):                                                          # 綠色跟橘色一樣：必出主詞綴多 30%，一共 6 點
        made = objects.create(99806, 1, "green")
        assert dict((a.name.lower(), n) for a, n in made.affects)["crit"] >= 4
        assert sum(n * equipment.price(a.name.lower(), 12) for a, n in made.affects) == 6


def test_drops_on_the_north_plains(world):
    mobs = {m["vnum"]: m for m in json.loads((AREAS / "north_plains.json").read_text(encoding="utf-8"))["mobiles"]}
    assert {"obj_vnum": 99806, "color": "green", "chance": 1000, "tiers": None} in mobs[99806]["drops"]    # 禿鷹
    assert {"obj_vnum": 99807, "color": "green", "chance": 1000, "tiers": None} in mobs[99803]["drops"]    # 兇猛的獅子


def hp_without_sets(p):
    return stats.naked(p.level, p.primaries, p.guild)["hp"] + sum(stats.gear_bonus(p.guild, o).get("hp", 0.0) for o in p.equipment.values())


@pytest.mark.parametrize("level, wears, active", [
    (10, [HELM], False),                                                         # 只穿一件
    (10, [HELM, BOOTS], True),
    (15, [HELM, BOOTS], True),                                                   # 套裝 5 級：15 級還有
    (16, [HELM, BOOTS], False),                                                  # 16 級沒有
])
def test_effect_needs_every_piece_and_expires(world, level, wears, active):
    p = player(level)
    for v in wears:
        p.carrying.insert(0, objects.create(v, 1, None))
    say(p, "wear all")
    bonus = sets.strength(sets.set_of(HELM))
    assert bonus > 0 and p.panel["hp"] == pytest.approx(hp_without_sets(p) + (bonus if active else 0))


def test_two_of_the_same_piece_are_not_a_set(world):
    p = player()
    p.equipment = {"finger_l": objects.create(99806, 1, None), "finger_r": objects.create(99806, 1, None)}
    assert sets.active(p) == []


def test_temper_refuses_sets(world):
    p = player(20)
    p.temper_stones = 1
    p.carrying.insert(0, objects.create(HELM, 1, None))
    say(p, "wear helm")
    assert re.fullmatch(r"【〔測試套裝〕.*測試套裝頭盔/helm】是套裝，不能淬火。", say(p, "use temper helm"))
    assert p.temper_stones == 1


def test_examine_says_which_set(world):
    p = player()
    p.carrying.insert(0, objects.create(HELM, 1, None))
    p.carrying.insert(0, objects.create(BOOTS, 1, None))
    say(p, "wear helm")
    rows = say(p, "exam boots").split("\r\n")
    bonus = sets.strength(sets.set_of(HELM))
    assert rows[-2:] == ["套裝：【測試套裝】，身上穿了 1/2 件（測試套裝頭盔、測試套裝靴子）",
                         f"套裝特效：HP +{bonus}（16 級後失效）"]


def score_tail(p):
    p.writer.data = b""
    commands.command(p, "score")
    lines = p.writer.data.decode(ENCODING).rsplit("\r\n\r\n", 1)[0].split("\r\n")
    start = next(i for i, line in enumerate(lines) if "套裝效果" in line)
    return [(re.sub(r"\x1b\[[0-9;]*m", "", line), "\x1b[30;1m【" in line) for line in lines[start:start + 3]]   # (字, 灰色)


def test_score_shows_sets(world):
    # 使用者 2026-11-20 要的：穿了至少一件就列；沒穿齊、等級超過了（已失效）整行灰色
    p = player(15)
    p.carrying[:0] = [objects.create(99806, 1, None), objects.create(HELM, 1, None)]
    say(p, "wear all")
    rows = score_tail(p)
    assert rows[0] == (" 套裝效果：", False)
    assert rows[1][1] and rows[1][0].endswith("測試套裝】 1/2 件  HP +" + str(sets.strength(sets.set_of(HELM))))
    assert rows[2] == (" 【    紅布獵手】 1/2 件  命中 +6", True)
    p.carrying.insert(0, objects.create(99807, 1, None))
    say(p, "wear lion")
    assert score_tail(p)[2] == (" 【    紅布獵手】 2/2 件  命中 +6", False)
    stats.set_level(p, 23)
    assert score_tail(p)[2] == (" 【    紅布獵手】 2/2 件  命中 +6（已失效）", True)


def test_score_without_sets(world):
    p = player()
    commands.command(p, "score")
    assert "套裝效果" not in p.writer.data.decode(ENCODING)


def test_saved_pieces_stay_a_set(world):
    p = player()
    for v in (HELM, BOOTS):
        p.carrying.insert(0, objects.create(v, 1, None))
    say(p, "wear all")
    save.save_player(p)
    again = save.player_from(save.load_data("Ming"), FakeWriter())
    assert [o.name for o in again.equipment.values()] == [o.name for o in p.equipment.values()]
    assert sets.active(again) == [sets.set_of(HELM)] and again.panel["hp"] == pytest.approx(p.panel["hp"])


def test_a_folder_without_a_set_table_has_no_sets(tmp_path):
    write_json(tmp_path, "a.json", make_area("a.json", [make_room(101)]))
    zones.load(tmp_path)
    assert sets.table == [] and sets.set_of(HELM) is None
    zones.stop()


def test_strength_formula():
    s = sets.Set("x", 12, (1, 2), "hit")
    assert math.floor(sets.SHARE * 13.1 / 1.0) == 6 and sets.EXPIRE_LEVELS == 10 and s.level + sets.EXPIRE_LEVELS + 1 == 23
