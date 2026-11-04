from pathlib import Path

import pytest

from area_helpers import make_area, make_exit, make_mobile, make_object, make_resets, make_room, write_area, write_json
from mud import area, areacheck

ROOT = Path(__file__).resolve().parent.parent


def good_area():
    # 兩間房南北相連、一隻生物、一個物品、每種重置指令各一筆，每個欄位都有，而且都寫對
    return make_area("a.json", [make_room(1, north=2), make_room(2, south=1)], mobiles=[make_mobile(1)],
                     objects=[make_object(1)], resets=make_resets())


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


def mob(d):
    return d["mobiles"][0]


def obj(d):
    return d["objects"][0]


def reset(d, cmd):
    """第一筆是 cmd 的重置。"""
    return next(r for r in d["resets"] if r["cmd"] == cmd)


# 每條規則：怎麼改壞、問題裡要出現的字
RULES = [
    pytest.param(lambda d: d.update(schema_version=2), "schema_version", id="schema_version"),
    pytest.param(lambda d: d.update(file="b.json"), "file 要寫實際的檔名", id="file"),
    pytest.param(lambda d: d.pop("rooms"), "少了欄位 rooms", id="少了最上層欄位"),
    pytest.param(lambda d: d.update(helps=[]), "多了不認得的欄位 helps", id="多了最上層欄位"),
    pytest.param(lambda d: d["area"]["header"].update(levels=[5, 1]), "levels", id="levels 反了"),
    pytest.param(lambda d: d["area"]["header"].update(levels="1  5"), "levels", id="levels 是字串"),
    pytest.param(lambda d: d["area"]["header"].pop("type"), "少了欄位 type", id="少了 type"),
    pytest.param(lambda d: d["area"]["header"].update(type="town"),
                 "area.header.type 要寫 world、dynamic、instance 其中一個，不能是 'town'", id="type 寫錯"),
    pytest.param(lambda d: d["area"]["header"].update(type=[]), "area.header.type 要寫", id="type 是清單"),
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
    # 生物：這次只檢查寫法，數字代表什麼還不檢查
    pytest.param(lambda d: d.pop("mobiles"), "少了欄位 mobiles", id="少了 mobiles"),
    pytest.param(lambda d: d.update(mobiles={}), "mobiles 要寫成 […]", id="mobiles 不是清單"),
    pytest.param(lambda d: mob(d).update(vnum=100), "生物號碼 100 不在 1～99", id="生物 vnum 太大"),
    pytest.param(lambda d: d["mobiles"].append(make_mobile(1)), "生物 1 在這個檔案裡重複", id="生物 vnum 重複"),
    pytest.param(lambda d: mob(d).update(size=1), "生物 1 多了不認得的欄位 size", id="生物多欄位"),
    pytest.param(lambda d: mob(d).pop("special"), "生物 1 少了欄位 special", id="生物少欄位"),
    pytest.param(lambda d: mob(d).update(hitroll=0), "多了不認得的欄位 hitroll", id="生物舊欄位"),   # 使用者刪掉的欄位
    pytest.param(lambda d: mob(d).update(keywords=" "), "keywords 不能是空的", id="生物 keywords"),
    pytest.param(lambda d: mob(d).update(short=""), "short 不能是空的", id="生物 short"),
    pytest.param(lambda d: mob(d).update(race=3), "race 要是字串", id="生物 race"),
    pytest.param(lambda d: mob(d).update(level="5"), "level 要是整數", id="生物 level"),
    pytest.param(lambda d: mob(d).update(act="2|x"), "act 看不懂", id="生物 act"),
    pytest.param(lambda d: mob(d).update(affected_by=-1), "affected_by 不能是負數", id="生物 affected_by"),
    pytest.param(lambda d: mob(d).update(custom=None), "多了不認得的欄位 custom", id="生物舊欄位 custom"),
    pytest.param(lambda d: mob(d).update(exp=1), "多了不認得的欄位 exp", id="生物舊欄位 exp"),   # 經驗值照設計文件 §4.7 算
    pytest.param(lambda d: mob(d).pop("tier"), "生物 1 少了欄位 tier", id="生物少 tier"),
    pytest.param(lambda d: mob(d).update(tier="mob"),
                 "tier 要寫 trash、normal、elite、boss 其中一個，不能是 'mob'", id="生物 tier 寫錯"),
    pytest.param(lambda d: mob(d).update(tier=None), "tier 要寫", id="生物 tier 是 null"),   # 種類一定要寫
    pytest.param(lambda d: mob(d).update(attack="fire"), "attack 要是 null、phys、spell、dragon 其中一個", id="生物 attack 寫錯"),
    pytest.param(lambda d: mob(d).update(attack="phys/phys"), "不能是 'phys/phys'", id="生物 attack 主次一樣"),
    pytest.param(lambda d: mob(d).update(attack="phys/spell/dragon"), "attack 要是", id="生物 attack 三種"),
    pytest.param(lambda d: mob(d).update(defense="both"), "defense 要是 null 或 phys、spell 其中一個", id="生物 defense"),
    pytest.param(lambda d: mob(d).update(archetype=[]), "archetype 要是 null 或 tank", id="生物 archetype"),
    pytest.param(lambda d: mob(d).update(random_drop=None), "多了不認得的欄位 random_drop", id="生物舊欄位 random_drop"),  # 改用 drops
    pytest.param(lambda d: mob(d).update(tier_roll={"elite": 9000, "boss": 2000}),
                 "tier_roll 加起來是 9000 ＋ 2000 ＝ 11000，不能超過 10000（100%）", id="生物 tier_roll 超過 100%"),
    pytest.param(lambda d: mob(d).update(tier_roll={"normal": 100}), "tier_roll 不用寫基本種類 normal", id="生物 tier_roll 寫到自己"),
    pytest.param(lambda d: mob(d).update(tier_roll={"king": 100}), "tier_roll 的種類要是", id="生物 tier_roll 種類寫錯"),
    pytest.param(lambda d: mob(d).update(tier_roll={"boss": 0.5}), "tier_roll 的 boss 要是 1～10000 的整數", id="生物 tier_roll 小數"),
    pytest.param(lambda d: mob(d).update(tier_roll=[]), "tier_roll 要是 null 或", id="生物 tier_roll 清單"),
    pytest.param(lambda d: mob(d).update(drops=None), "drops 要寫成 […]", id="生物 drops 是 null"),
    pytest.param(lambda d: mob(d)["drops"][0].update(obj_vnum=0), "drops 第 1 行的 obj_vnum 要是物品號碼", id="生物 drops 物品"),
    pytest.param(lambda d: mob(d)["drops"][0].update(color="gold"), "drops 第 1 行的 color 要是 null", id="生物 drops 顏色"),
    pytest.param(lambda d: mob(d)["drops"][0].update(chance=0), "drops 第 1 行的 chance 要是 1～10000", id="生物 drops 機率 0"),
    pytest.param(lambda d: mob(d)["drops"][0].update(chance=10001), "chance 要是 1～10000", id="生物 drops 機率太大"),
    pytest.param(lambda d: mob(d)["drops"][0].update(tiers=[]), "drops 第 1 行的 tiers 要是 null", id="生物 drops tiers 空的"),
    pytest.param(lambda d: mob(d)["drops"][0].update(tiers=["boss", "boss"]), "tiers 要是 null", id="生物 drops tiers 重複"),
    pytest.param(lambda d: mob(d)["drops"][0].pop("tiers"), "drops 第 1 行 少了欄位 tiers", id="生物 drops 少欄位"),
    pytest.param(lambda d: mob(d)["script"].update(function=""), "function 不能是空的", id="生物 script"),
    pytest.param(lambda d: mob(d).update(actions={}), "actions 要寫成 […]", id="生物 actions 不是清單"),
    pytest.param(lambda d: mob(d)["actions"][0].pop("text"), "actions 第 1 項少了欄位 text", id="生物 actions 少欄位"),
    pytest.param(lambda d: mob(d)["fight_actions"][0].update(rate="10"), "rate 要是整數", id="生物 fight_actions"),
    pytest.param(lambda d: mob(d)["shop"].update(buy_types="8"), "buy_types 要是整數的清單", id="生物 shop buy_types"),
    pytest.param(lambda d: mob(d)["shop"].update(open_hour=None), "open_hour 要是整數", id="生物 shop 時間"),
    pytest.param(lambda d: mob(d).update(special=""), "special 要是 null 或函式名稱", id="生物 special"),
    # 物品：這次只檢查寫法
    pytest.param(lambda d: d.pop("objects"), "少了欄位 objects", id="少了 objects"),
    pytest.param(lambda d: d.update(objects={}), "objects 要寫成 […]", id="objects 不是清單"),
    pytest.param(lambda d: obj(d).update(vnum=0), "物品號碼 0 不在 1～99", id="物品 vnum 0"),
    pytest.param(lambda d: d["objects"].append(make_object(1)), "物品 1 在這個檔案裡重複", id="物品 vnum 重複"),
    pytest.param(lambda d: obj(d).update(values_raw=[]), "物品 1 多了不認得的欄位 values_raw", id="物品多欄位"),
    pytest.param(lambda d: obj(d).update(cost_per_day=0), "多了不認得的欄位 cost_per_day", id="物品舊欄位"),   # 使用者刪掉的欄位
    pytest.param(lambda d: obj(d).update(cost="0"), "cost 要是整數", id="物品 cost"),
    pytest.param(lambda d: obj(d).update(keywords=""), "keywords 不能是空的", id="物品 keywords"),
    pytest.param(lambda d: obj(d).update(item_type="5"), "item_type 要是整數", id="物品 item_type"),
    pytest.param(lambda d: obj(d).update(wear_flags="1|x"), "wear_flags 看不懂", id="物品 wear_flags"),
    pytest.param(lambda d: obj(d).update(values=[0, 1, 4]), "values 要寫 4 個", id="物品 values 3 個"),
    pytest.param(lambda d: obj(d).update(values=[0, 1, 4, {}]), "values 要寫 4 個", id="物品 values 放 {}"),
    pytest.param(lambda d: obj(d)["affects"][0].pop("modifier"), "affects 第 1 項少了欄位 modifier", id="物品 affects"),
    pytest.param(lambda d: obj(d)["extra_descriptions"][0].update(keywords=" "), "keywords 不能是空的",
                 id="物品 extra 名字空的"),
    pytest.param(lambda d: obj(d)["script"].update(function=""), "function 不能是空的", id="物品 script"),
    # 重置：這次只檢查寫法
    pytest.param(lambda d: d.pop("resets"), "少了欄位 resets", id="少了 resets"),
    pytest.param(lambda d: d.update(resets={}), "resets 要寫成 […]", id="resets 不是清單"),
    pytest.param(lambda d: d["resets"].append({"cmd": "X", "comment": ""}), "cmd 要是", id="不認得的 cmd"),
    pytest.param(lambda d: d["resets"].append(["M"]), "cmd 要是", id="重置不是 {…}"),
    pytest.param(lambda d: reset(d, "M").pop("limit"), "（M）少了欄位 limit", id="M 少欄位"),
    pytest.param(lambda d: reset(d, "M").update(room_vnum=0), "room_vnum 號碼 0 不對", id="M 房間號碼"),
    pytest.param(lambda d: reset(d, "G").update(rare="0"), "rare 要是整數", id="G rare"),
    pytest.param(lambda d: d["resets"].append({"cmd": "E", "rare": 0, "obj_vnum": 2, "limit": 0, "wear_loc": 16, "comment": ""}),
                 "cmd 要是", id="E 拿掉了"),   # 使用者說生物不穿裝備
    pytest.param(lambda d: reset(d, "P").update(container_vnum=-1), "container_vnum 號碼 -1 不對", id="P 容器號碼"),
    pytest.param(lambda d: reset(d, "G").update(color="gold"), "（G）的 color 要是 null（不是裝備）或 gray", id="G 顏色"),
    pytest.param(lambda d: reset(d, "O").update(color=3), "（O）的 color 要是 null", id="O 顏色"),
    pytest.param(lambda d: reset(d, "P").pop("color"), "（P）少了欄位 color", id="P 少顏色"),
    pytest.param(lambda d: reset(d, "G").update(level="5"),
                 "（G）的 level 是物品的等級，要是 null（用前面那筆 M 的怪物等級）或整數，不能是 '5'", id="G 等級"),
    pytest.param(lambda d: reset(d, "O").update(level=None),
                 "（O）的 level 是物品的等級，要是 整數（O、P 沒有怪物帶著，一定要寫）", id="O 等級沒寫"),
    pytest.param(lambda d: reset(d, "P").update(level=1.5), "（P）的 level 是物品的等級", id="P 等級小數"),
    pytest.param(lambda d: reset(d, "O").pop("level"), "（O）少了欄位 level", id="O 少等級"),
    pytest.param(lambda d: reset(d, "D").update(direction="northeast"), "direction 'northeast' 不對", id="D 方向"),
    pytest.param(lambda d: reset(d, "R").update(exit_count="4"), "exit_count 要是整數", id="R exit_count"),
    pytest.param(lambda d: reset(d, "*").update(comment=None), "comment 要是字串", id="註解不是字串"),
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


def test_exit_into_instance_is_an_error(tmp_path):
    # 副本只能用 enter 進去：世界區域的出口不能通到副本裡
    a = write_area(tmp_path, "a.json", [make_room(1, north=201)], area_number=100)
    b = write_area(tmp_path, "b.json", [make_room(1)], area_number=200, kind="instance")
    found = area.check_files([a, b], [a, b])
    assert found[a] == ["a.json：房間 1 往 north 的出口通到副本 b.json 的房間 201，副本不能走進去（要用 enter）"]
    assert found[b] == []


def test_exit_out_of_instance_is_an_error(tmp_path):
    # 副本只能用 recall 出來：副本的出口不能通到別的區域
    a = write_area(tmp_path, "a.json", [make_room(1)], area_number=100)
    b = write_area(tmp_path, "b.json", [make_room(1, south=101)], area_number=200, kind="instance")
    found = area.check_files([a, b], [a, b])
    assert found[a] == []
    assert found[b] == ["b.json：房間 1 往 south 的出口通到 a.json 的房間 101，副本的出口不能通到別的區域（要用 recall 出來）"]


def test_exits_inside_instance_and_into_dynamic_are_fine(tmp_path):
    # 副本裡自己的房間可以互通；動態區域可以從世界走進去、再走回來
    a = write_area(tmp_path, "a.json", [make_room(1, north=201)], area_number=100)
    b = write_area(tmp_path, "b.json", [make_room(1, south=101)], area_number=200, kind="dynamic")
    c = write_area(tmp_path, "c.json", [make_room(1, north=2), make_room(2, south=301)], area_number=300, kind="instance")
    assert all(found == [] for found in area.check_files([a, b, c], [a, b, c]).values())


def test_reference_instance_is_known(tmp_path):
    # 只檢查 a.json 時，也要從對照的檔案知道 b.json 是副本
    a = write_area(tmp_path, "a.json", [make_room(1, north=201)], area_number=100)
    b = write_area(tmp_path, "b.json", [make_room(1)], area_number=200, kind="instance")
    assert "副本不能走進去" in area.check_files([a], [a, b])[a][0]


def test_mobile_parts_can_be_null(tmp_path):
    data = good_area()
    mob(data).update(script=None, shop=None, special=None, actions=[], fight_actions=[], drops=[],
                     tier_roll=None, attack=None, defense=None, archetype=None)
    assert problems_of(tmp_path, data) == []


def test_mobile_drops_color_and_tiers_can_be_null(tmp_path):
    # 不是裝備的物品不寫顏色；tiers 寫 null 是所有種類都會掉；一隻怪可以有好幾行
    data = good_area()
    mob(data)["drops"].append({"obj_vnum": 2, "color": None, "chance": 10000, "tiers": None})
    assert problems_of(tmp_path, data) == []


@pytest.mark.parametrize("attack", ["phys", "spell", "dragon", "dragon/phys", "phys/spell", "spell/dragon"])
def test_mobile_attack_one_or_main_and_sub(tmp_path, attack):
    data = good_area()
    mob(data).update(attack=attack)
    assert problems_of(tmp_path, data) == []


def test_mobile_game_number_below_100(tmp_path):
    data = make_area("a.json", [make_room(50, north=51), make_room(51, south=50)], area_number=50,
                     mobiles=[make_mobile(1)])
    assert problems_of(tmp_path, data) == [
        "a.json：生物 1 的遊戲號碼是 area_number 50 ＋ 1 ＝ 51，不能小於 100（1～99 是保留的）"]


def test_cross_file_mobile_duplicate(tmp_path):
    # 生物跟房間分開算：a.json 的房間 101 和生物 101 可以同時存在；生物 160 兩個檔都有就算重複
    a = write_area(tmp_path, "a.json", [make_room(1)], area_number=100, mobiles=[make_mobile(1), make_mobile(60)])
    b = write_area(tmp_path, "b.json", [make_room(1)], area_number=150, mobiles=[make_mobile(10)])
    found = area.check_files([a, b], [a, b])
    assert found[a] == []
    assert found[b] == ["b.json：生物 160 跟 a.json 重複"]


def test_cross_file_object_duplicate(tmp_path):
    # 物品也是自己算：a.json 的房間 101、物品 101 可以同時存在；物品 160 兩個檔都有就算重複
    a = write_area(tmp_path, "a.json", [make_room(1)], area_number=100, objects=[make_object(1), make_object(60)])
    b = write_area(tmp_path, "b.json", [make_room(1)], area_number=150, objects=[make_object(10)])
    found = area.check_files([a, b], [a, b])
    assert found[a] == []
    assert found[b] == ["b.json：物品 160 跟 a.json 重複"]


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


# ---- 固定裝備（物品寫了 affects）的點數上限，設計文件 §3.3 ----

def fixed_area(objects, resets=(), mobiles=()):
    return make_area("a.json", [make_room(1)], mobiles=list(mobiles), objects=list(objects), resets=list(resets))


def armed(vnum, affects, wear="1|8192", extra=0):
    o = make_object(vnum)
    o.update(wear_flags=wear, extra_flags=extra, affects=affects)
    return o


M1 = {"cmd": "M", "rare": 0, "mob_vnum": 1, "limit": 1, "room_vnum": 1, "comment": ""}


def give(obj_vnum, color="white", level=None):
    return {"cmd": "G", "rare": 0, "obj_vnum": obj_vnum, "color": color, "level": level, "limit": 0, "comment": ""}


def test_fixed_item_over_cap_shows_the_math(tmp_path):
    # 1 級雙手武器：上限是主手＋副手；G 沒寫等級就用 M 那隻生物的等級（make_mobile 是 1 級）
    sword = armed(1, [{"location": 1, "modifier": 2}, {"location": 13, "modifier": 18}], extra=512)
    data = fixed_area([sword], [M1, give(1)], [make_mobile(1)])
    assert problems_of(tmp_path, data) == [
        "a.json：resets 第 2 筆（G）放出物品 101「物品1」：加成點數 力量 +2 × 3.741 ＋ 攻速 +18 × 1 ＝ 25.482，"
        "超過 1 級主手＋副手（雙手）、白色的上限 20.058 × 1 ＝ 20.058（設計文件 §3.3）"]


def test_fixed_item_level_written_on_g_wins(tmp_path):
    # 同一把武器，G 寫 50 級：上限大很多，就沒問題
    sword = armed(1, [{"location": 13, "modifier": 18}])
    assert problems_of(tmp_path, fixed_area([sword], [M1, give(1, level=50)], [make_mobile(1)])) == []
    assert problems_of(tmp_path, fixed_area([sword], [M1, give(1)], [make_mobile(1)])) != []


def test_fixed_item_color_bonus(tmp_path):
    # 1 級主手上限 14.33：攻速 +16 白色超過，橘色（×1.4）就夠
    sword = armed(1, [{"location": 13, "modifier": 16}])
    assert problems_of(tmp_path, fixed_area([sword], [M1, give(1, "white")], [make_mobile(1)])) != []
    assert problems_of(tmp_path, fixed_area([sword], [M1, give(1, "orange")], [make_mobile(1)])) == []


@pytest.mark.parametrize("color, text", [(None, "沒寫顏色（null）的上限"), ("gray", "灰色的上限")])
def test_fixed_item_gray_or_null_has_no_points(tmp_path, color, text):
    sword = armed(1, [{"location": 6, "modifier": 1}])
    found = problems_of(tmp_path, fixed_area([sword], [M1, give(1, color)], [make_mobile(1)]))
    assert len(found) == 1 and text in found[0] and "× 0 ＝ 0" in found[0]


def test_dragon_resistance_is_free(tmp_path):
    # 只給龍焰抗性的獎勵（設計文件 §5.5）：不算點數，灰色、null 也可以
    ring = armed(1, [{"location": 16, "modifier": 500}], wear="1|2")
    o = {"cmd": "O", "if_flag": 0, "obj_vnum": 1, "color": None, "level": 1, "limit": 0, "room_vnum": 1, "comment": ""}
    assert problems_of(tmp_path, fixed_area([ring], [o])) == []


def test_fixed_item_in_drops_uses_mob_level(tmp_path):
    helm = armed(1, [{"location": 6, "modifier": 10}], wear="1|16")    # 頭：1 級上限 5.73、20 級 13.9
    weak, strong = make_mobile(1), make_mobile(2)
    strong["level"] = 20
    for m in (weak, strong):
        m["drops"] = [{"obj_vnum": 1, "color": "white", "chance": 100, "tiers": None}]
    found = problems_of(tmp_path, fixed_area([helm], mobiles=[weak, strong]))
    assert len(found) == 1 and found[0].startswith("a.json：生物 1 的 drops 第 1 行放出物品 101")


def test_two_handed_needs_wield(tmp_path):
    # 512 雙手只對有主手位置的物品有用：頭盔勾了也還是頭的上限
    helm = armed(1, [{"location": 6, "modifier": 10}], wear="1|16", extra=512)
    o = {"cmd": "O", "if_flag": 0, "obj_vnum": 1, "color": "white", "level": 1, "limit": 0, "room_vnum": 1, "comment": ""}
    assert "1 級頭、白色的上限 5.73" in problems_of(tmp_path, fixed_area([helm], [o]))[0]


def test_unplaced_fixed_item_is_not_checked(tmp_path):
    # 沒有地方放它，就不知道等級和顏色
    sword = armed(1, [{"location": 13, "modifier": 999}])
    assert problems_of(tmp_path, fixed_area([sword])) == []


def test_fixed_item_from_another_file(tmp_path):
    # G 給的是 b.json 的物品（寫完整號碼 201）：用 b.json 的物品算，錯誤報在放它的 a.json
    sword = armed(1, [{"location": 13, "modifier": 18}])
    a = write_json(tmp_path, "a.json", fixed_area([], [M1, give(201)], [make_mobile(1)]))
    b = write_area(tmp_path, "b.json", [make_room(1)], area_number=200, objects=[sword])
    found = area.check_files([a, b], [a, b])
    assert found[b] == [] and "放出物品 201「物品1」" in found[a][0]
