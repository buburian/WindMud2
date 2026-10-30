from pathlib import Path

import pytest

from area_helpers import make_area, make_exit, make_room, write_area, write_json
from mud import area, areacheck

ROOT = Path(__file__).resolve().parent.parent


def good_area():
    # 兩間房南北相連，每個欄位都有，而且都寫對
    return make_area("a.json", [make_room(1, north=2), make_room(2, south=1)])


def problems_of(tmp_path, data):
    path = write_json(tmp_path, "a.json", data)
    return area.check_files([path], [path])[path]


def test_real_areas_have_no_problems():
    paths = sorted((ROOT / "areas").glob("*.json"))
    assert paths
    assert all(found == [] for found in area.check_files(paths, paths).values())


def test_good_area_has_no_problems(tmp_path):
    assert problems_of(tmp_path, good_area()) == []


def room(d, i=0):
    return d["rooms"][i]


def north(d):
    return d["rooms"][0]["exits"]["north"]


# 每條規則：怎麼改壞、問題裡要出現的字
RULES = [
    pytest.param(lambda d: d.update(schema_version=2), "schema_version", id="schema_version"),
    pytest.param(lambda d: d.update(file="b.json"), "file 要寫實際的檔名", id="file"),
    pytest.param(lambda d: d.pop("rooms"), "少了欄位 rooms", id="少了最上層欄位"),
    pytest.param(lambda d: d.update(mobiles=[]), "多了不認得的欄位 mobiles", id="多了最上層欄位"),
    pytest.param(lambda d: d["area"]["header"].update(levels=[5, 1]), "levels", id="levels 反了"),
    pytest.param(lambda d: d["area"]["header"].update(levels="1  5"), "levels", id="levels 是字串"),
    pytest.param(lambda d: d["area"]["header"].update(author=3), "author", id="author"),
    pytest.param(lambda d: d["area"]["header"].update(area_number=0), "保留", id="area_number 0"),
    pytest.param(lambda d: d["area"].update(recall=9), "area.recall 指到不存在的房間 109", id="recall 不存在"),
    pytest.param(lambda d: d["area"].update(recall="1"), "area.recall", id="recall 格式"),
    pytest.param(lambda d: d["area"].update(no_teleport=2), "no_teleport", id="no_teleport"),
    pytest.param(lambda d: d["area"].update(clan_recall=-1), "clan_recall", id="clan_recall"),
    pytest.param(lambda d: d["area"].update(gem=True), "gem", id="gem 不能是 true"),
    pytest.param(lambda d: room(d).update(vnum=100), "1～99", id="vnum 太大"),
    pytest.param(lambda d: room(d, 1).update(vnum=1), "在這個檔案裡重複", id="vnum 重複"),
    pytest.param(lambda d: room(d).update(name=" "), "name 不能是空的", id="name"),
    pytest.param(lambda d: room(d).update(description=None), "description", id="description"),
    pytest.param(lambda d: room(d).update(room_flags=2), "沒有的旗標 [2]", id="room_flags 沒有的旗標"),
    pytest.param(lambda d: room(d).update(room_flags="1|x"), "room_flags", id="room_flags 格式"),
    pytest.param(lambda d: room(d).update(sector=11), "sector", id="sector 太大"),
    pytest.param(lambda d: room(d).update(door_flags=[]), "多了不認得的欄位 door_flags", id="舊欄位"),
    pytest.param(lambda d: room(d)["exits"].update(northeast=make_exit(2)), "出口方向", id="方向"),
    pytest.param(lambda d: north(d).update(locks=9), "locks", id="locks"),
    pytest.param(lambda d: north(d).update(key=-2), "key", id="key"),
    pytest.param(lambda d: north(d).update(keywords=None), "keywords", id="門的名字"),
    pytest.param(lambda d: north(d).pop("description"), "少了欄位 description", id="出口少欄位"),
    pytest.param(lambda d: north(d).update(to_room=0), "出口號碼", id="to_room 0"),
    pytest.param(lambda d: north(d).update(to_room=9), "不存在的房間 109", id="to_room 不存在"),
    pytest.param(lambda d: room(d).update(extra_descriptions=[{"keywords": " ", "description": ""}]),
                 "keywords 不能是空的", id="extra 名字空的"),
    pytest.param(lambda d: room(d).update(extra_descriptions=[{"keywords": "牌子"}]),
                 "少了欄位 description", id="extra 少欄位"),
    pytest.param(lambda d: room(d).update(script={"trigger": {"value": 64}, "function": "rs_x"}),
                 "少了欄位 names", id="script trigger"),
    pytest.param(lambda d: room(d).update(script={"trigger": {"value": 64, "names": ["say"]}, "function": ""}),
                 "function 不能是空的", id="script function"),
]


@pytest.mark.parametrize("break_it, want", RULES)
def test_each_rule(tmp_path, break_it, want):
    data = good_area()
    break_it(data)
    found = problems_of(tmp_path, data)
    assert any(want in p for p in found), found


def test_all_problems_are_listed(tmp_path):
    data = good_area()
    room(data).update(sector=99, room_flags="x")
    north(data).update(locks=9)
    assert len(problems_of(tmp_path, data)) == 3


def test_not_json(tmp_path):
    path = tmp_path / "a.json"
    path.write_text("{這不是 JSON", encoding="utf-8")
    assert "不是正確的 JSON" in area.check_files([path])[path][0]


def test_cross_file_exit_and_duplicate(tmp_path):
    a = write_area(tmp_path, "a.json", [make_room(1, north=201)], area_number=100)
    b = write_area(tmp_path, "b.json", [make_room(1, south=101)], area_number=200)
    c = write_area(tmp_path, "c.json", [make_room(1)], area_number=200)     # 201 跟 b.json 重複
    found = area.check_files([a, b, c], [a, b, c])
    assert found[a] == [] and found[b] == []
    assert found[c] == ["c.json：房間 201 跟 b.json 重複"]


def test_cli_one_file_looks_in_same_folder(tmp_path, capsys):
    a = write_area(tmp_path, "a.json", [make_room(1, north=201)], area_number=100)
    write_area(tmp_path, "b.json", [make_room(1)], area_number=200)
    assert areacheck.main([str(a)]) == 0                  # 201 在 b.json 裡，找得到
    out = capsys.readouterr().out
    assert "✓" in out and "b.json" not in out             # 只報 a.json


def test_cli_reports_problems(tmp_path, capsys):
    data = good_area()
    room(data).update(sector=99)
    path = write_json(tmp_path, "a.json", data)
    assert areacheck.main([str(path)]) == 1
    out = capsys.readouterr().out
    assert "✗" in out and "sector" in out and "共 1 個問題" in out


def test_cli_all_checks_areas_folder(monkeypatch, capsys):
    monkeypatch.chdir(ROOT)
    assert areacheck.main([]) == 0
    assert "areas/test.json：沒問題" in capsys.readouterr().out
