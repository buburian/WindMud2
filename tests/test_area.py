from pathlib import Path

import pytest

from area_helpers import make_area, make_room, write_area, write_json
from mud import area, zones
from mud.characters import Position

AREAS = Path(__file__).resolve().parent.parent / "areas"
MANUAL = Path(__file__).resolve().parent.parent / "docs" / "區域製作手冊.md"


def write(folder, name, rooms, area_number=100):
    write_area(folder, name, rooms, area_number)


def room(vnum, room_flags=0, sector=0, **exits):
    r = make_room(vnum, **exits)
    r["room_flags"], r["sector"] = room_flags, sector
    return r


def test_test_area_numbers_are_area_number_plus_vnum():
    # 測試區域的 area_number 是 100：房間 1、2 在遊戲裡是 101、102
    zones.load(AREAS)
    assert set(zones.world.rooms) == {101, 102}
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
    r = room(1)
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
    write(tmp_path, "a.json", [room(1, room_flags="1|4", sector=3)])
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
])
def test_definitions_match_manual(marker, cls):
    # 手冊表格的「數字、C 版名稱」跟程式裡的定義要一模一樣（中文意思寫在註解，測試看不到）
    want = [(int(number), name.upper()) for number, name, _ in manual_table(marker)]
    assert [(m.value, m.name) for m in cls] == want


def test_area_types_match_manual():
    # 手冊「三種區域」表的第一欄就是區域檔裡寫的 type
    assert [row[0] for row in manual_table("## 三種區域")] == [t.value for t in area.AreaType]


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
    write(tmp_path, "a.json", [room(1, room_flags="1|x")])
    with pytest.raises(ValueError, match="room_flags"):
        zones.load(tmp_path)


@pytest.mark.parametrize("sector", ["0", "1|2", -1, True, 1.5, None])
def test_sector_must_be_one_integer(tmp_path, sector):
    write(tmp_path, "a.json", [room(1, sector=sector)])
    with pytest.raises(ValueError, match="sector"):
        zones.load(tmp_path)


def test_exit_100_or_more_is_a_full_number(tmp_path):
    # 出口寫 100 以上就是完整號碼，可以通到別的區域
    write(tmp_path, "a.json", [room(1, north=201)], area_number=100)
    write(tmp_path, "b.json", [room(1, south=101)], area_number=200)
    zones.load(tmp_path)
    assert zones.world.rooms[101].exits == {"north": 201}
    assert zones.world.rooms[201].exits == {"south": 101}


@pytest.mark.parametrize("vnum", [0, 100])
def test_room_number_must_be_1_to_99(tmp_path, vnum):
    write(tmp_path, "a.json", [room(vnum)])
    with pytest.raises(ValueError, match="1～99"):
        zones.load(tmp_path)


@pytest.mark.parametrize("area_number", [0, 50])
def test_game_numbers_1_to_99_are_reserved(tmp_path, area_number):
    # area_number 0 → 房間 1 變 1；area_number 50 → 房間 1 變 51：都落在保留的 1～99
    write(tmp_path, "a.json", [room(1)], area_number=area_number)
    with pytest.raises(ValueError, match="保留"):
        zones.load(tmp_path)


def test_missing_area_number_is_an_error(tmp_path):
    data = make_area("a.json", [room(1)])
    del data["area"]["header"]["area_number"]
    write_json(tmp_path, "a.json", data)
    with pytest.raises(ValueError, match="area_number"):
        zones.load(tmp_path)


def test_load_reports_first_problem_and_how_many(tmp_path):
    # 有好幾個問題時，開機訊息是第一個問題，再加上總數和查看全部的指令
    write(tmp_path, "a.json", [room(1, sector=99, north=9)])
    with pytest.raises(ValueError, match="sector.*共 2 個問題.*mud.areacheck"):
        zones.load(tmp_path)


def test_exit_number_below_1_is_an_error(tmp_path):
    write(tmp_path, "a.json", [room(1, north=0)])
    with pytest.raises(ValueError, match="出口號碼"):
        zones.load(tmp_path)


def test_duplicate_game_number_is_an_error(tmp_path):
    # 兩個區域的 area_number 一樣，房間 1 都會變成 101
    write(tmp_path, "a.json", [room(1)])
    write(tmp_path, "b.json", [room(1)])
    with pytest.raises(ValueError, match="重複"):
        zones.load(tmp_path)


def test_exit_to_missing_room_is_an_error(tmp_path):
    write(tmp_path, "a.json", [room(1, north=9)])
    with pytest.raises(ValueError, match="不存在"):
        zones.load(tmp_path)


def test_failed_load_keeps_old_rooms(tmp_path):
    zones.load(AREAS)
    write(tmp_path, "a.json", [room(1, north=9)])
    with pytest.raises(ValueError):
        zones.load(tmp_path)
    assert set(zones.world.rooms) == {101, 102}
