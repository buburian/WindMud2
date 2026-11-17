"""區域編輯器的網頁伺服器：用 port 0 開真的伺服器（資料夾是暫存的），用 urllib 打 API。"""
import json
import re
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from area_helpers import make_area, make_mobile, make_object, make_room, write_area, write_json
from mud.area import (
    Apply, Archetype, AreaType, AttackType, Defense, ExtraFlag, ItemColor, Locks, MobTier, RoomFlag, Sector, WearFlag,
)
from mud import area, specials
from mud.builder.server import make_server

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "mud" / "builder" / "static"


@pytest.fixture
def builder(tmp_path):
    """回傳 (網址開頭, 資料夾)。"""
    server = make_server("127.0.0.1", 0, tmp_path)
    # poll_interval 調短：shutdown() 要等它醒來，預設 0.5 秒會讓每個測試都慢半秒
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", tmp_path
    finally:
        server.shutdown()
        server.server_close()


def call(url, method="GET", body=None):
    """回傳 (狀態碼, 解開的 JSON, headers)。"""
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request) as r:
            return r.status, json.loads(r.read()), r.headers
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read()), e.headers


def test_new_area_has_no_problems(builder):
    base, folder = builder
    status, result, _ = call(f"{base}/api/areas", "POST", {"file": "new.json", "title": "新區域", "vnums": [3000, 3399]})
    assert status == 201 and result == {"file": "new.json"}
    status, result, _ = call(f"{base}/api/areas/new.json")
    assert status == 200
    assert result["problems"] == []
    assert result["data"]["file"] == "new.json"
    assert result["data"]["area"]["header"]["vnums"] == [3000, 3399]
    assert result["data"]["area"]["header"]["type"] == "world"
    assert [(r["vnum"], r["name"]) for r in result["data"]["rooms"]] == [(3000, "新房間")]   # 第一間是範圍的最小值
    _, listing, _ = call(f"{base}/api/areas")
    assert listing == [{"file": "new.json", "title": "新區域", "vnums": [3000, 3399], "rooms": 1}]


def test_new_area_with_bad_range_still_saves(builder):
    # 範圍寫錯也照存，讓檢查報錯（跟其他欄位一樣）
    base, folder = builder
    status, _, _ = call(f"{base}/api/areas", "POST", {"file": "new.json", "title": "", "vnums": [50, 10]})
    assert status == 201
    _, result, _ = call(f"{base}/api/areas/new.json")
    assert any("area.header.vnums 要寫 [最小, 最大]" in p for p in result["problems"])


def test_create_existing_file_is_refused(builder):
    base, folder = builder
    write_area(folder, "a.json", [make_room(101)])
    before = (folder / "a.json").read_bytes()
    status, result, _ = call(f"{base}/api/areas", "POST", {"file": "a.json", "title": "x", "vnums": [300, 399]})
    assert status == 409 and "已經有了" in result["error"]
    assert (folder / "a.json").read_bytes() == before


def test_save_keeps_test_json_byte_for_byte(builder):
    base, folder = builder
    shutil.copytree(ROOT / "areas" / "test", folder / "test")       # 腳本的 .lua 也在編輯器的資料夾裡找
    raw = (ROOT / "areas" / "test.json").read_bytes()
    status, result, _ = call(f"{base}/api/areas/test.json", "PUT", json.loads(raw))
    assert status == 200 and result["problems"] == []
    assert (folder / "test.json").read_bytes() == raw          # 沒改的東西（例如 "0" 這種寫法）原樣存回去
    assert not list(folder.glob(".*.tmp"))                      # 暫存檔有換名掉


def test_save_with_problems_still_saves(builder):
    base, folder = builder
    data = make_area("a.json", [make_room(101, north=107)])
    status, result, _ = call(f"{base}/api/areas/a.json", "PUT", data)
    assert status == 200
    assert result["problems"] == ["a.json：房間 101 往 north 的出口指到不存在的房間 107"]
    assert json.loads((folder / "a.json").read_text(encoding="utf-8")) == data


def test_check_does_not_write(builder):
    base, folder = builder
    status, result, _ = call(f"{base}/api/areas/a.json/check", "POST", make_area("a.json", [make_room(101, north=107)]))
    assert status == 200 and len(result["problems"]) == 1
    assert not (folder / "a.json").exists()


def test_check_ignores_saved_copy_of_same_file(builder):
    # 硬碟上的舊版不能拿來對照，不然每間房都會跟它「重複」
    base, folder = builder
    write_area(folder, "a.json", [make_room(101, north=102), make_room(102, south=101)])
    data = make_area("a.json", [make_room(101, north=102), make_room(102, south=101)])
    assert call(f"{base}/api/areas/a.json/check", "POST", data)[1]["problems"] == []


def test_check_uses_other_files(builder):
    base, folder = builder
    write_area(folder, "b.json", [make_room(201)], vnums=(200, 299))
    ok = make_area("a.json", [make_room(101, north=201)])
    assert call(f"{base}/api/areas/a.json/check", "POST", ok)[1]["problems"] == []
    bad = make_area("a.json", [make_room(101, north=202)])
    assert call(f"{base}/api/areas/a.json/check", "POST", bad)[1]["problems"] == [
        "a.json：房間 101 往 north 的出口指到不存在的房間 202"]
    overlap = make_area("a.json", [make_room(101)], vnums=(100, 250))      # 別的檔的範圍也拿來對照
    assert call(f"{base}/api/areas/a.json/check", "POST", overlap)[1]["problems"] == [
        "a.json：area.header.vnums 的範圍 100～250 跟 b.json 的 200～299 重疊"]


def test_read_gives_room_names_of_other_files(builder):
    base, folder = builder
    write_area(folder, "a.json", [make_room(101)])
    write_area(folder, "b.json", [make_room(201), make_room(202)], vnums=(200, 299),
               mobiles=[make_mobile(205)], objects=[make_object(207)])
    write_json(folder, "broken.json", {"rooms": "壞掉"})        # 看不懂的檔略過，不會讓整個讀取失敗
    _, result, _ = call(f"{base}/api/areas/a.json")
    assert result["elsewhere"] == {"201": "房間201", "202": "房間202"}
    assert result["elsewhere_mobiles"] == {"205": "生物205"}
    assert result["elsewhere_objects"] == {"207": "物品207"}


def test_listing_marks_unreadable_files(builder):
    base, folder = builder
    (folder / "bad.json").write_text("{", encoding="utf-8")
    (folder / "bad name.json").write_text("{}", encoding="utf-8")
    _, listing, _ = call(f"{base}/api/areas")
    assert [item["file"] for item in listing] == ["bad name.json", "bad.json"]
    assert all("讀不到" in item["error"] for item in listing)


@pytest.mark.parametrize("name", ["a.txt", "..%2Fa.json", "%2E%2E%2Fa.json", "a%20b.json"])
def test_bad_file_names_are_refused(builder, name):
    base, folder = builder
    for method, url, body in [("GET", f"/api/areas/{name}", None), ("PUT", f"/api/areas/{name}", {}),
                              ("POST", f"/api/areas/{name}/check", {})]:
        status, result, _ = call(base + url, method, body)
        assert status == 400 and "檔名" in result["error"], (method, url)
    status, result, _ = call(f"{base}/api/areas", "POST", {"file": name.replace("%2F", "/"), "title": "", "vnums": [100, 199]})
    assert status == 400


def test_missing_file_and_bad_json(builder):
    base, folder = builder
    assert call(f"{base}/api/areas/nothing.json")[0] == 404
    request = urllib.request.Request(f"{base}/api/areas/a.json", data=b"{", method="PUT")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(request)
    assert e.value.code == 400
    assert not (folder / "a.json").exists()


def test_responses_are_not_cached(builder):
    base, folder = builder
    assert call(f"{base}/api/areas")[2]["Cache-Control"] == "no-store"


def get_raw(url):
    """回傳 (狀態碼, 內容 bytes, Content-Type)。"""
    try:
        with urllib.request.urlopen(url) as r:
            return r.status, r.read(), r.headers["Content-Type"]
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers["Content-Type"]


def test_serves_page_files(builder):
    base, folder = builder
    status, body, kind = get_raw(f"{base}/")
    assert status == 200 and kind.startswith("text/html") and b"/static/app.js" in body
    status, body, kind = get_raw(f"{base}/static/model.js")
    assert status == 200 and kind.startswith("text/javascript")
    assert body == (STATIC / "model.js").read_bytes()


@pytest.mark.parametrize("path", ["/static/..%2Fserver.py", "/static/%2E%2E/server.py", "/static/nothing.js", "/static/"])
def test_page_files_stay_in_static(builder, path):
    base, folder = builder
    assert get_raw(base + path)[0] == 404


def js_table(name):
    """model.js 裡 export const NAME = [[數字, …], …] 的數字。"""
    text = (STATIC / "model.js").read_text(encoding="utf-8")
    block = re.search(rf"export const {name} = \[(.*?)\n\];", text, re.S)[1]
    return [int(n) for n in re.findall(r"^\s*\[(\d+),", block, re.M)]


def test_page_tables_match_area_definitions():
    # 網頁的旗標、地形、門的數字要跟 area.py 一樣；改手冊的表時這裡會提醒要一起改
    assert js_table("FLAGS") == [f.value for f in RoomFlag]
    assert js_table("SECTORS") == [s.value for s in Sector]
    assert js_table("LOCKS") == [lock.value for lock in Locks]


def test_object_tables_match_area_definitions():
    # 物品的加成、特性、穿戴位置：編輯器的表跟 area.py 的定義要一樣（點數上限的檢查用 area.py 的）
    assert tables_js("APPLY") == [a.value for a in Apply]
    assert tables_js("EXTRA_FLAGS") == [f.value for f in ExtraFlag]
    assert tables_js("WEAR_FLAGS") == [f.value for f in WearFlag]


def test_area_type_options_match_area_definitions():
    # 區域設定的「區域種類」選單，值是字串，要跟 AreaType 一樣
    text = (STATIC / "model.js").read_text(encoding="utf-8")
    block = re.search(r"export const AREA_TYPES = \[(.*?)\n\];", text, re.S)[1]
    assert re.findall(r'^\s*\["(\w+)",', block, re.M) == [t.value for t in AreaType]


MANUAL = ROOT / "docs" / "區域製作手冊.md"


def manual_rows(marker):
    """手冊裡 marker 這個標題下面的第一個表格，不含表頭：[[欄, 欄, …], …]。"""
    rows = []
    for line in MANUAL.read_text(encoding="utf-8").split(marker, 1)[1].splitlines():
        if line.startswith("|"):
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
        elif rows:
            break
    return rows[2:]                                     # 拿掉表頭和 |---|


def tables_js(name):
    """tables.js 裡 export const NAME = [[數字或名稱, …], …] 的第一欄。"""
    text = (STATIC / "tables.js").read_text(encoding="utf-8")
    block = re.search(rf"export const {name} = \[(.*?)\n\];", text, re.S)[1]
    return [json.loads(key) for key in re.findall(r'^\s*\[(\d+|"[^"]*"),', block, re.M)]


@pytest.mark.parametrize("name, marker", [
    ("ACT", "### act（行為旗標）"),
    ("AFFECTED", "### affected_by（身上的效果）"),
    ("POSITIONS", "### position（姿勢）"),
    ("ITEM_TYPES", "### item_type（物品種類）"),
    ("EXTRA_FLAGS", "### extra_flags（特性旗標）"),
    ("WEAR_FLAGS", "### wear_flags（拿起來、穿在哪裡）"),
    ("APPLY", "### affects（加成）"),
    ("CONTAINER_FLAGS", "### 容器旗標"),
])
def test_page_tables_match_manual(name, marker):
    # 編輯器的數字表照手冊抄的；改手冊的表時這裡會提醒要一起改 tables.js
    assert tables_js(name) == [int(row[0]) for row in manual_rows(marker)]


@pytest.mark.parametrize("name, marker, cls", [
    ("MOB_TIERS", "### tier（種類）", MobTier),
    ("ATTACK_TYPES", "### attack（攻擊類型）", AttackType),
    ("DEFENSES", "### defense（攻防傾向）", Defense),
    ("ARCHETYPES", "### archetype（原型）", Archetype),
    ("ITEM_COLORS", "乘上顏色的加成。", ItemColor),                   # drops 那一節最後的顏色表
])
def test_page_codes_match_manual_and_area(name, marker, cls):
    # 生物的代號表：編輯器、手冊、area.py 的定義三邊要一樣
    assert tables_js(name) == [row[0] for row in manual_rows(marker)] == [c.value for c in cls]


def test_door_states_match_manual_and_area():
    # 重置 D 的門狀態：編輯器的選單、手冊的 state 表、area.DoorState 三邊要一樣
    rows = manual_rows("`D` 的 `state`：")
    assert tables_js("DOOR_STATES") == [int(row[0]) for row in rows] == [s.value for s in area.DoorState]
    text = (STATIC / "tables.js").read_text(encoding="utf-8")
    block = re.search(r"export const DOOR_STATES = \[(.*?)\n\];", text, re.S)[1]
    assert re.findall(r'\[\d+, "([^"]*)"\]', block) == [row[1] for row in rows]     # 中文意思也一樣


def test_weapon_kinds_match_area():
    # 編輯器的武器種類選單跟 area.WeaponKind 一樣，名字後面的（單手）（雙手）跟拿法一樣
    text = (STATIC / "tables.js").read_text(encoding="utf-8")
    block = re.search(r"export const WEAPON_KINDS = \[(.*?)\n\];", text, re.S)[1]
    rows = [(int(n), name) for n, name in re.findall(r'\[(\d+), "([^"]*)"\]', block)]
    assert rows == [(k.value, f"{area.WEAPON_KIND_NAMES[k]}（{'雙手' if k in area.TWO_HANDED_KINDS else '單手'}）")
                    for k in area.WeaponKind]


def test_page_tables_with_several_columns_match_manual():
    # 這幾張表在手冊裡一列放好幾組（數字、名字、數字、名字…）
    attacks = [int(row[i]) for row in manual_rows("### 武器的攻擊方式") for i in (0, 2) if row[i]]
    assert tables_js("ATTACKS") == sorted(attacks)
    liquids = [int(row[i]) for row in manual_rows("### 液體種類") for i in (0, 3) if row[i]]
    assert tables_js("LIQUIDS") == sorted(liquids)
    races = [row[i].lower() for row in manual_rows("### race（種族）") for i in (0, 2, 4) if row[i]]
    assert tables_js("RACES") == races


def test_page_specials_match_manual():
    section = MANUAL.read_text(encoding="utf-8").split("### special（特殊程式）", 1)[1].split("\n## ", 1)[0]
    assert sorted(tables_js("SPECIALS")) == sorted(set(re.findall(r"spec_\w+", section)))


def test_page_special_groups_match_server():
    # 選單的兩組跟伺服器的分法一樣：「戰鬥」是 specials.FIGHTING，「平常」是平常的加上先不做的
    text = (STATIC / "tables.js").read_text(encoding="utf-8")
    block = re.search(r"export const SPECIALS = \[(.*?)\n\];", text, re.S)[1]
    kinds = re.findall(r'\["(spec_\w+)", "[^"]*", "([^"]*)"\]', block)
    assert len(kinds) == len(area.SPECIALS)
    assert {name for name, kind in kinds if kind == "戰鬥"} == set(specials.FIGHTING)
    assert {name for name, kind in kinds if kind == "平常"} == set(specials.IDLE) | set(specials.NOT_YET)
