"""書商的地圖（mud/maps.py，使用者 2026-11-20 要的）：程式照區域檔的房間和出口自己畫。

真的 areas/：5 張都畫得出來（沒有撞在一起、線不穿過房間、79 格、Big5）、迷宮和樓上樓下和建築物裡面不畫、字母和說明、
look map、書商只賣這 5 張。小的假區域：線拉長、單向的出口不畫、迷宮那一片比較大也畫走得進來的那一片、建築物只畫門口。
"""
import re

import pytest

import mud.commands as commands
from area_helpers import make_area, make_room, write_json
from mud import maps, objects, stats, weather, zones
from mud.area import RoomFlag
from mud.characters import characters
from mud.config import AREA_DIR, ENCODING
from mud.players import Player

WIDTH = 79


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


@pytest.fixture
def real(monkeypatch):
    monkeypatch.setattr(weather, "current", weather.Weather(hour=12))     # 書商照開店時間賣
    zones.load(AREA_DIR)
    yield
    characters.clear()
    zones.stop()


def area_rooms(name):
    return {v: r for v, r in zones.world.rooms.items() if r.area.name == name}


def lines(name):
    return maps.draw(name).rstrip("\n").split("\n")


def person(room):
    p = Player("Ming", FakeWriter(), zones.world.rooms[room])
    p.race, p.guild = stats.Race.ELF, stats.Guild.SWORD
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    stats.set_level(p, 5)
    characters.append(p)
    return p


def say(p, line):
    p.writer.data = b""
    commands.command(p, line)
    return re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING)).rsplit("\r\n\r\n", 1)[0]


# ---- 真的區域 ----

@pytest.mark.parametrize("name", sorted(maps.MAPS.values()))
def test_every_map_draws_cleanly(real, name):
    rooms = area_rooms(name)
    drawn, edges, _doors = maps.rooms_to_draw(rooms)
    pos = maps.layout(drawn, edges)
    assert [kind for kind, _key, _ways in maps.clashes(pos, edges, set()) if kind != "cross"] == []   # 交叉可以（畫成＋）
    text = lines(name)
    header = next(iter(rooms.values())).area.data["area"]["header"]
    assert text[0] == f"{header['title']}（{header['levels'][0]}～{header['levels'][1]} 級）" and text[-1] == maps.FOOTER
    for line in text:
        assert len(line.encode(ENCODING)) <= WIDTH, line             # Big5 轉不過去會丟錯
    grid = [line for line in text if set(line) <= set(maps.ROOM + maps.BLANK + maps.ACROSS + maps.DOWN + maps.CROSS + "".join(maps.LETTERS))]
    assert sum(line.count(maps.ROOM) for line in grid) + len(maps.labels(rooms, drawn, _doors, pos, zones)) == len(drawn)   # 每間都畫了


def test_the_maze_upstairs_and_buildings_are_not_drawn(real):
    forest, _e, _d = maps.rooms_to_draw(area_rooms("forest.json"))
    assert 10119 in forest and not {10143, 10148, 10149, 10195} & forest          # 夢幻草原的迷霧不畫
    city, _e, doors = maps.rooms_to_draw(area_rooms("midgaard.json"))
    assert 3008 not in city                                                        # 野豬酒吧樓上的錢莊
    assert 3068 in doors and not {3069, 3070, 3071} & city                         # 英雄公會：只畫大廳（門口）
    river, _e, _d = maps.rooms_to_draw(area_rooms("river.json"))
    assert 14605 in river and 14621 not in river                                   # 急流（走過去回不來）


def test_letters_and_what_they_mean(real):
    assert lines("forest.json")[-2] == "Ａ 往秋風城　Ｂ 往牛頭人要塞"
    legend = "　".join(lines("midgaard.json"))
    for place in ("魔法店", "地圖店", "往城西森林草原區", "往棕仙巷", "往邪龍教派", "往河流區"):    # 棕仙巷是動態區域
        assert re.search(rf"[Ａ-Ｚａ-ｚ] {place}(　|$)", legend), place


def test_drawn_once_until_the_areas_reload(real):
    first = maps.draw("river.json")
    assert maps.draw("river.json") is first
    zones.load(AREA_DIR)
    assert maps.draw("river.json") is not first and maps.draw("river.json") == first


def test_map_items_are_in_the_city(real):
    for vnum, name in maps.MAPS.items():
        assert objects.protos[vnum]["item_type"] == 12 and objects.protos[vnum]["extra_descriptions"] == []
        assert area_rooms(name)


def test_look_map(real):
    p = person(3005)
    p.carrying.append(objects.create(3394, 5, None))
    assert say(p, "look map").split("\r\n")[0] == "城西森林草原區（1～8 級）"
    assert say(p, "look 地圖") == say(p, "look westforest") == say(p, "look map")
    assert say(p, "look citymap") == "在這裡找不到你要看的東西。"                  # 市民手冊沒了
    p.room = zones.world.rooms[3065]                                               # 地圖店：房間自己的「地圖」（架上的地圖）先找到（照 C 版）
    assert say(p, "look 地圖") != say(p, "look map") == say(p, "look westforest")


def test_other_items_look_the_same(real):
    wand = objects.create(3170, 5, None)
    assert maps.text(wand) is None and objects.extra_descriptions(wand) == []


def test_the_bookseller_sells_only_the_five_maps(real):
    p = person(3065)
    shown = say(p, "list").split("\r\n")[1:]
    assert [re.search(r"】 (\S+)/", line)[1] for line in shown] == ["秋風城地圖", "城西森林地圖", "城東森林地圖", "城北平原地圖", "河流區地圖"]


# ---- 假的區域 ----

def build(tmp_path, rooms, extra=()):
    write_json(tmp_path, "a.json", make_area("a.json", rooms, (100, 199)))
    for name, data in extra:
        write_json(tmp_path, name, data)
    zones.load(tmp_path)


@pytest.fixture
def folder(tmp_path):
    yield tmp_path
    characters.clear()
    zones.stop()


def test_lines_stretch_when_a_row_has_more_rooms(folder):
    # 上面 2 間、下面 3 間（城西森林的林心那裡）：上面那排的線拉長
    build(folder, [make_room(101, east=102, south=103), make_room(102, west=101, south=105),
                   make_room(103, north=101, east=104), make_room(104, west=103, east=105), make_room(105, west=104, north=102)])
    assert lines("a.json")[1:4] == ["口－－－口", "｜　　　｜", "口－口－口"]


def test_one_way_exits_and_a_bigger_maze(folder):
    # 101～102 通到別的區域；102 往東單向進 103～106（四間互通、比較大、但不通外面）：只畫 101～102
    maze = [make_room(103, east=104, south=105), make_room(104, west=103, south=106),
            make_room(105, north=103, east=106), make_room(106, west=105, north=104)]
    other = make_area("b.json", [make_room(201, east=101)], (200, 299))
    build(folder, [make_room(101, west=201, east=102), make_room(102, west=101, east=103), *maze], [("b.json", other)])
    drawn, _edges, _doors = maps.rooms_to_draw(area_rooms("a.json"))
    assert drawn == {101, 102}
    assert lines("a.json")[1:3] == ["Ａ－口", "Ａ 往測試"]


def test_only_the_door_of_a_building(folder):
    rooms = [make_room(101, north=102), make_room(102, south=101, north=103), make_room(103, south=102)]
    for r in rooms[1:]:
        r["room_flags"] = int(RoomFlag.INDOORS)
    build(folder, rooms)
    assert lines("a.json")[1:5] == ["Ａ", "｜", "口", "Ａ 房間102"]
