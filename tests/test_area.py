from pathlib import Path

import pytest

from area_helpers import make_area, make_room, write_area, write_json
from mud import area, zones
from mud.characters import Position

AREAS = Path(__file__).resolve().parent.parent / "areas"
MANUAL = Path(__file__).resolve().parent.parent / "docs" / "區域製作手冊.md"


def write(folder, name, rooms, vnums=(100, 199)):
    write_area(folder, name, rooms, vnums)


def room(vnum, room_flags=0, sector=0, **exits):
    r = make_room(vnum, **exits)
    r["room_flags"], r["sector"] = room_flags, sector
    return r


def test_test_area_numbers_are_full_game_numbers():
    # 測試區域的範圍是 100～199，房間直接寫遊戲號碼 101、102（世界裡還有秋風城）
    zones.load(AREAS)
    assert {r for r in zones.world.rooms if 100 <= r <= 199} == {101, 102}     # 測試區域自己的範圍（300～399 是棕仙巷）
    assert zones.world.rooms[101].exits == {"north": 102}
    assert zones.world.rooms[102].exits == {"south": 101}


def test_test_area_descriptions():
    zones.load(AREAS)
    assert zones.world.rooms[101].exit_descriptions == {"north": "往北看，是測試區域北邊的房間。\n"}
    # 名字存成小寫、拆成一個一個字
    assert zones.world.rooms[101].extra_descriptions == [
        (["牌子", "sign"], "牌子上寫著：這裡是測試區域。牆上有一行{R紅色{x的字。\n")]
    assert zones.world.rooms[102].extra_descriptions == []


def test_missing_field_is_a_clear_error(tmp_path):
    r = room(101)
    del r["extra_descriptions"]
    write(tmp_path, "a.json", [r])
    with pytest.raises(ValueError, match="少了欄位 extra_descriptions"):
        zones.load(tmp_path)


def test_test_area_flags_and_sector():
    # room_flags：房間 1 寫成數字 0，房間 2 寫成字串 "0"；sector 都是整數 0
    zones.load(AREAS)
    for vnum in (101, 102):
        assert (zones.world.rooms[vnum].room_flags, zones.world.rooms[vnum].sector) == (0, 0)


def test_flags_and_sector_are_stored_with_names(tmp_path):
    # 記憶體裡存的不只是數字，印出來看得到名字
    write(tmp_path, "a.json", [room(101, room_flags="1|4", sector=3)])
    zones.load(tmp_path)
    assert repr(zones.world.rooms[101].room_flags) == "<RoomFlag.DARK|NO_MOB: 5>"
    assert zones.world.rooms[101].sector is area.Sector.FOREST


def manual_table(marker):
    """手冊裡 marker 後面的第一個表格，不含表頭：[[第一欄, 第二欄, …], …]。"""
    lines = MANUAL.read_text(encoding="utf-8").split(marker, 1)[1].splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("|"))
    rows = []
    for line in lines[start + 2:]:              # 跳過表頭和 |---|
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows


@pytest.mark.parametrize("marker, cls", [
    pytest.param("### room_flags（房間旗標）", area.RoomFlag, id="room_flags"),
    pytest.param("### sector（地形）", area.Sector, id="sector"),
    pytest.param("### position（姿勢）", Position, id="position"),   # 也是角色現在姿勢的定義
    pytest.param("### affects（加成）", area.Apply, id="affects"),
    pytest.param("### wear_flags（拿起來、穿在哪裡）", area.WearFlag, id="wear_flags"),
    pytest.param("### extra_flags（特性旗標）", area.ExtraFlag, id="extra_flags"),
    pytest.param("### act（行為旗標）", area.ActFlag, id="act"),
    pytest.param("### affected_by（身上的效果）", area.AffectFlag, id="affected_by"),
])
def test_definitions_match_manual(marker, cls):
    # 手冊表格的「數字、C 版名稱」跟程式裡的定義要一模一樣（中文意思寫在註解，測試看不到；有的表後面多一欄「新系統」）
    want = [(int(number), name.upper()) for number, name, *_ in manual_table(marker)]
    assert [(m.value, m.name) for m in cls] == want


def test_weapon_kinds_match_manual():
    # 手冊「武器種類」的表：數字、名稱、種類、拿法、預設攻擊方式（數字和中文）
    want = [[str(k.value), k.name.lower(), area.WEAPON_KIND_NAMES[k], "雙手" if k in area.TWO_HANDED_KINDS else "單手",
             f"{area.DEFAULT_ATTACK[k].value} {area.ATTACK_NAMES[area.DEFAULT_ATTACK[k]]}"] for k in area.WeaponKind]
    assert manual_table("### 武器種類") == want


def test_attacks_match_manual():
    # 手冊的攻擊方式表一列放兩組（數字、意思、數字、意思）；名字是 Merc 的，手冊沒有，只比數字和中文
    rows = manual_table("### 武器的攻擊方式")
    pairs = sorted((int(row[i]), row[i + 1]) for row in rows for i in (0, 2) if row[i])
    assert pairs == [(a.value, area.ATTACK_NAMES[a]) for a in area.Attack]


def test_mob_races_match_manual():
    # 手冊的種族表一列放三組（名稱、中文）
    rows = manual_table("### race（種族）")
    assert list(area.MOB_RACES) == [row[i].lower() for row in rows for i in (0, 2, 4) if row[i]]


def test_area_types_match_manual():
    # 手冊「區域的種類」表的第一欄就是區域檔裡寫的 type
    assert [row[0] for row in manual_table("## 區域的種類")] == [t.value for t in area.AreaType]


def test_locks_match_manual():
    # 手冊的 locks 表只有數字和意思，名字是照 C 版的門旗標取的，所以只比數字
    want = [int(locks) for locks, _ in manual_table("`locks` 的值：")]
    assert [m.value for m in area.Locks] == want


@pytest.mark.parametrize("value, want", [
    (0, 0), (1, 1), (3, 3), (5, 5),
    ("0", 0), ("1", 1), ("1|2", 3), ("1|4", 5), (" 1 | 4 ", 5),
    ("1|3", 3),                             # 是合起來（位元 OR），不是加起來（那會變 4）
])
def test_parse_flags_accepts_numbers_and_strings(value, want):
    assert area.parse_flags(value) == want


@pytest.mark.parametrize("value", ["", "a", "1|", "1||4", "-1", -1, "１", 1.5, True, None, {"value": 0}, [1]])
def test_parse_flags_rejects_everything_else(value):
    with pytest.raises(ValueError):
        area.parse_flags(value)


def test_bad_room_flags_in_file_is_an_error(tmp_path):
    write(tmp_path, "a.json", [room(101, room_flags="1|x")])
    with pytest.raises(ValueError, match="room_flags"):
        zones.load(tmp_path)


@pytest.mark.parametrize("sector", ["0", "1|2", -1, True, 1.5, None])
def test_sector_must_be_one_integer(tmp_path, sector):
    write(tmp_path, "a.json", [room(101, sector=sector)])
    with pytest.raises(ValueError, match="sector"):
        zones.load(tmp_path)


def test_exit_outside_the_range_links_to_another_file(tmp_path):
    # 號碼在自己的範圍外就是外連：通到別的區域檔
    write(tmp_path, "a.json", [room(101, north=201)], vnums=(100, 199))
    write(tmp_path, "b.json", [room(201, south=101)], vnums=(200, 299))
    zones.load(tmp_path)
    assert zones.world.rooms[101].exits == {"north": 201}
    assert zones.world.rooms[201].exits == {"south": 101}


def test_room_number_must_be_in_the_range(tmp_path):
    write(tmp_path, "a.json", [room(250)])
    with pytest.raises(ValueError, match="房間 250 的號碼 250 不在這個檔的範圍 100～199"):
        zones.load(tmp_path)


@pytest.mark.parametrize("vnum", [0, 50, 99])
def test_game_numbers_1_to_99_are_reserved(tmp_path, vnum):
    write(tmp_path, "a.json", [room(vnum)])
    with pytest.raises(ValueError, match=f"房間號碼要寫完整的遊戲號碼（100 以上，1～99 是系統區域檔用的），不能是 {vnum}"):
        zones.load(tmp_path)


def test_more_than_99_rooms_in_one_file(tmp_path):
    # 跟 C 版一樣，一個檔可以放超過 99 間（舊版的秋風城有 179 間）
    rooms = [room(v, north=v + 1) for v in range(1000, 1149)] + [room(1149, north=1000)]
    write(tmp_path, "a.json", rooms, vnums=(1000, 1199))
    zones.load(tmp_path)
    assert len(zones.world.rooms) == 150


def test_missing_vnums_is_an_error(tmp_path):
    data = make_area("a.json", [room(101)])
    del data["area"]["header"]["vnums"]
    write_json(tmp_path, "a.json", data)
    with pytest.raises(ValueError, match="area.header 少了欄位 vnums"):
        zones.load(tmp_path)


@pytest.mark.parametrize("vnums", [[100], [199, 100], [50, 150], [100, 199, 300], "100-199", [100.0, 199], None])
def test_vnums_must_be_a_range(tmp_path, vnums):
    data = make_area("a.json", [room(101)])
    data["area"]["header"]["vnums"] = vnums
    write_json(tmp_path, "a.json", data)
    with pytest.raises(ValueError, match="area.header.vnums 要寫 \\[最小, 最大\\] 兩個整數，最小不能小於 100"):
        zones.load(tmp_path)


def test_ranges_must_not_overlap(tmp_path):
    write(tmp_path, "a.json", [room(101)], vnums=(100, 199))
    write(tmp_path, "b.json", [room(201)], vnums=(150, 250))
    with pytest.raises(ValueError, match="b.json：area.header.vnums 的範圍 150～250 跟 a.json 的 100～199 重疊"):
        zones.load(tmp_path)


def test_load_reports_first_problem_and_how_many(tmp_path):
    # 有好幾個問題時，開機訊息是第一個問題，再加上總數和查看全部的指令
    write(tmp_path, "a.json", [room(101, sector=99, north=109)])
    with pytest.raises(ValueError, match="sector.*共 2 個問題.*mud.areacheck"):
        zones.load(tmp_path)


@pytest.mark.parametrize("to_room", [0, 9])
def test_exit_to_reserved_number_is_an_error(tmp_path, to_room):
    write(tmp_path, "a.json", [room(101, north=to_room)])
    with pytest.raises(ValueError, match=f"往 north 的出口的 to_room 要寫完整的遊戲號碼（100 以上，1～99 是系統區域檔用的），不能是 {to_room}"):
        zones.load(tmp_path)


def test_same_numbers_in_overlapping_files(tmp_path):
    # 兩個檔的範圍一樣：範圍重疊，房間 101 也重複
    write(tmp_path, "a.json", [room(101)])
    write(tmp_path, "b.json", [room(101)])
    problems = area.check_files(sorted(tmp_path.glob("*.json")))
    assert problems[tmp_path / "b.json"] == ["b.json：area.header.vnums 的範圍 100～199 跟 a.json 的 100～199 重疊",
                                             "b.json：房間 101 跟 a.json 重複"]


@pytest.mark.parametrize("to_room", [109, 5000])
def test_exit_to_missing_room_is_an_error(tmp_path, to_room):
    # 範圍裡（109）、範圍外（5000，外連）都要真的有那間房
    write(tmp_path, "a.json", [room(101, north=to_room)])
    with pytest.raises(ValueError, match=f"房間 101 往 north 的出口指到不存在的房間 {to_room}"):
        zones.load(tmp_path)


def test_failed_load_keeps_old_rooms(tmp_path):
    zones.load(AREAS)
    before = set(zones.world.rooms)
    write(tmp_path, "a.json", [room(101, north=109)])
    with pytest.raises(ValueError):
        zones.load(tmp_path)
    assert set(zones.world.rooms) == before and {101, 102, 3001} <= before
