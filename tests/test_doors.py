import asyncio
import logging
import re

import pytest

from area_helpers import make_area, make_exit, make_room, write_json
from mud import area, doors, resets, zones
from mud.area import DoorState, Locks
from mud.characters import Position, characters
from mud.commands import command, doors as door_commands, find, system
from mud.config import ENCODING
from mud.players import Player


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


@pytest.fixture
def folder(tmp_path):
    yield tmp_path
    characters.clear()
    zones.stop()


def door_exit(to, keywords="木門 door", locks=1, key=-1):
    e = make_exit(to)
    e.update(keywords=keywords, locks=locks, key=key)
    return e


def two_rooms(keywords="木門 door", key=-1):
    """房間 1 往北、房間 2 往南，中間是同一扇門（兩邊都寫）。"""
    r1, r2 = make_room(1), make_room(2)
    r1["exits"]["north"] = door_exit(2, keywords, key=key)
    r2["exits"]["south"] = door_exit(1, keywords, key=key)
    return [r1, r2]


def D(room, direction, state):
    return {"cmd": "D", "if_flag": 0, "room_vnum": room, "direction": direction, "state": state, "comment": ""}


def load(folder, rooms, resets_=(), name="a.json", area_number=100, kind="world"):
    write_json(folder, name, make_area(name, rooms, area_number, resets=resets_, kind=kind))


def player(name, room, position=Position.STANDING):
    p = Player(name, FakeWriter(), room)
    p.position = position
    characters.append(p)
    return p


def text_of(p):
    """收到的字（拿掉顏色），看完就清掉。"""
    text = re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))
    p.writer.data = b""
    return text


def world_door(vnum, direction):
    return zones.world.rooms[vnum].doors[direction]


# ---- 門的資料 ----

def test_build_room_makes_doors():
    r1 = two_rooms(key=5)[0]
    r1["exits"]["east"] = make_exit(3)                          # 沒有門的出口
    r1["exits"]["up"] = door_exit(150, keywords="", locks=8, key=0)
    r1["exits"]["down"] = door_exit(160, key=150)
    room = area.build_room(100, r1)
    assert set(room.doors) == {"north", "up", "down"}
    north = room.doors["north"]
    assert (north.keywords, north.locks, north.key, north.closed, north.locked) == (["木門", "door"], Locks.DOOR, 105, False, False)
    assert north.name == "木門" and room.doors["up"].name == "門"        # 沒寫名字就叫「門」
    assert room.doors["up"].key is None                         # 0、-1 是不用鑰匙
    assert room.doors["down"].key == 150                        # 100 以上照寫的號碼


# ---- 檢查：門兩邊都要寫 ----

def check(folder, *files):
    """files 是 (檔名, rooms, area_number)；全部一起檢查，回傳 {檔名: 問題}。"""
    paths = [write_json(folder, n, make_area(n, rooms, base)) for n, rooms, base in files]
    return {p.name: found for p, found in area.check_files(paths, paths).items()}


def test_door_on_one_side_is_a_problem(folder):
    rooms = two_rooms()
    rooms[1]["exits"]["south"]["locks"] = 0
    assert check(folder, ("a.json", rooms, 100))["a.json"] == [
        "a.json：房間 101 往 north 的出口有門（locks 1），房間 102 往 south 的出口指回來，也要有門（現在 locks 是 0）：門兩邊都要寫"]


def test_door_on_both_sides_is_fine(folder):
    assert check(folder, ("a.json", two_rooms(), 100))["a.json"] == []


@pytest.mark.parametrize("back", [None, 3], ids=["單向出口", "往回指到別間"])
def test_not_the_same_door(folder, back):
    rooms = two_rooms() + [make_room(3)]
    del rooms[1]["exits"]["south"]
    if back is not None:
        rooms[1]["exits"]["south"] = make_exit(back)
    assert check(folder, ("a.json", rooms, 100))["a.json"] == []


def test_door_in_another_file(folder):
    # a.json 有門、b.json 沒寫門：兩個檔各自報（只檢查 b.json 時，作者才看得到）
    a, b = make_room(1), make_room(1)
    a["exits"]["north"] = door_exit(201)
    b["exits"]["south"] = make_exit(101)
    found = check(folder, ("a.json", [a], 100), ("b.json", [b], 200))
    assert found["a.json"] == ["a.json：房間 101 往 north 的出口有門（locks 1），房間 201 往 south 的出口指回來，也要有門（現在 locks 是 0）：門兩邊都要寫"]
    assert found["b.json"] == ["b.json：房間 201 往 south 的出口沒有門（locks 0），但 a.json 的房間 101 往 north 的出口有門（locks 1）指到這裡：門兩邊都要寫"]


# ---- 走路 ----

@pytest.mark.parametrize("keywords, want", [("木門 door", "【木門】關起來了。"), ("", "北方關起來了。")])
def test_closed_door_blocks_walking(folder, keywords, want):
    load(folder, two_rooms(keywords), [D(1, "north", DoorState.CLOSED)])
    zones.load(folder)
    ming = player("Ming", zones.world.rooms[101])
    command(ming, "north")
    assert text_of(ming) == f"{want}\r\n\r\n> " and ming.room.vnum == 101
    command(ming, "open north")
    command(ming, "north")
    assert ming.room.vnum == 102


# ---- open、close ----

def test_open_and_close_change_both_sides(folder):
    load(folder, two_rooms(), [D(1, "north", DoorState.CLOSED)])
    zones.load(folder)
    ming, hua = player("Ming", zones.world.rooms[101]), player("Hua", zones.world.rooms[101])
    bob = player("Bob", zones.world.rooms[102])
    sleeper = player("Zed", zones.world.rooms[102], Position.SLEEPING)
    command(ming, "open 木門")
    assert not world_door(101, "north").closed and not world_door(102, "south").closed
    assert text_of(ming) == "你打開了木門。\r\n\r\n> "
    assert text_of(hua) == "\r\nMing打開了木門。\r\n\r\n> "
    assert text_of(bob) == "\r\n南方的木門被打開了。\r\n\r\n> "        # 對面房間：方向和名字照那一邊寫的
    command(ming, "close door")
    assert world_door(101, "north").closed and world_door(102, "south").closed
    assert text_of(ming) == "你關上了木門。\r\n\r\n> "
    assert text_of(hua) == "\r\nMing關上了木門。\r\n\r\n> "
    assert text_of(bob) == "\r\n南方的木門被關起來了。\r\n\r\n> "
    assert sleeper.writer.data == b""                           # 睡著的人看不到


def test_dark_room_does_not_see_the_door(folder):
    # 對面房間很暗、又沒有光源（光源是物品，還沒做）：看不到門被打開
    rooms = two_rooms()
    rooms[1]["room_flags"] = 1
    load(folder, rooms, [D(1, "north", DoorState.CLOSED)])
    zones.load(folder)
    ming, bob = player("Ming", zones.world.rooms[101]), player("Bob", zones.world.rooms[102])
    command(ming, "open 木門")
    assert not world_door(102, "south").closed and bob.writer.data == b""


@pytest.mark.parametrize("line, want", [
    ("open", "你想打開什麼呢？"),
    ("open 木門", "它已經是開著的。"),
    ("close", "你想關上什麼呢？"),
])
def test_open_close_refusals(folder, line, want):
    load(folder, two_rooms())                                   # 沒有 D：門一開始開著
    zones.load(folder)
    ming = player("Ming", zones.world.rooms[101])
    command(ming, line)
    assert text_of(ming) == f"{want}\r\n\r\n> "


def test_close_twice_and_open_locked(folder):
    load(folder, two_rooms(), [D(1, "north", DoorState.LOCKED)])
    zones.load(folder)
    ming = player("Ming", zones.world.rooms[101])
    command(ming, "close 木門")
    assert text_of(ming) == "它已經關起來了。\r\n\r\n> "
    command(ming, "open 木門")
    assert text_of(ming) == "它被鎖住了。\r\n\r\n> "


# ---- lock、unlock ----

@pytest.mark.parametrize("key, state, line, want", [
    (-1, DoorState.CLOSED, "lock 木門", "它沒有辦法鎖起來。"),
    (-1, DoorState.LOCKED, "unlock 木門", "沒辦法打開這個鎖。"),
    (5, DoorState.CLOSED, "lock 木門", "你沒有鑰匙，怎麼上鎖呢？"),     # 物品還沒做，沒有人有鑰匙
    (5, DoorState.LOCKED, "unlock 木門", "你沒有這個門的鑰匙。"),
    (5, DoorState.OPEN, "lock 木門", "要先關起來才能上鎖。"),
    (5, DoorState.OPEN, "unlock 木門", "它沒關起來。"),
    (5, DoorState.OPEN, "lock", "你想鎖住什麼呢？"),
    (5, DoorState.OPEN, "unlock", "你想打開哪裡的鎖呢？"),
])
def test_lock_refusals(folder, key, state, line, want):
    load(folder, two_rooms(key=key), [D(1, "north", state)])
    zones.load(folder)
    ming = player("Ming", zones.world.rooms[101])
    command(ming, line)
    assert text_of(ming) == f"{want}\r\n\r\n> "


def test_lock_and_unlock_with_key(folder, monkeypatch):
    # 有鑰匙（物品還沒做，先假裝有）：兩邊一起鎖、一起開鎖；對面不會知道（照 C 版）
    monkeypatch.setattr(door_commands, "has_key", lambda ch, vnum: vnum == 105)
    load(folder, two_rooms(key=5), [D(1, "north", DoorState.CLOSED)])
    zones.load(folder)
    ming, hua = player("Ming", zones.world.rooms[101]), player("Hua", zones.world.rooms[101])
    bob = player("Bob", zones.world.rooms[102])
    command(ming, "lock 木門")
    assert world_door(101, "north").locked and world_door(102, "south").locked
    assert text_of(ming) == "你鎖上了木門。\r\n\r\n> " and text_of(hua) == "\r\nMing鎖上了木門。\r\n\r\n> "
    command(ming, "lock 木門")
    assert text_of(ming) == "它已經被鎖起來了。\r\n\r\n> "
    command(ming, "unlock 木門")
    assert not world_door(101, "north").locked and not world_door(102, "south").locked
    assert world_door(101, "north").closed                      # 開鎖後還是關著
    assert text_of(ming) == "你打開了木門的鎖。\r\n\r\n> " and text_of(hua) == "\r\nMing打開了木門的鎖。\r\n\r\n> "
    command(ming, "unlock 木門")
    assert text_of(ming) == "它沒有上鎖。\r\n\r\n> "
    assert bob.writer.data == b""


# ---- 指定門 ----

@pytest.mark.parametrize("line, want", [
    ("close DOOR", "你關上了木門。"),                           # 英文名字不分大小寫
    ("close no", "你關上了木門。"),                             # 方向
    ("close 木", "這裡沒有叫做「木」的門。"),                   # 名字要整個字一樣
    ("close s", "南方沒有出口。"),
    ("close e", "東方的出口沒有門。"),
])
def test_find_door(folder, line, want):
    rooms = two_rooms() + [make_room(3)]
    rooms[0]["exits"]["east"] = make_exit(3)
    load(folder, rooms)
    zones.load(folder)
    ming = player("Ming", zones.world.rooms[101])
    command(ming, line)
    assert text_of(ming) == f"{want}\r\n\r\n> "


def test_door_name_comes_before_direction(folder):
    # 照 CLAUDE.md 定的順序：先找門的名字，再當方向。北邊的門叫 east，close east 關的是北邊的門
    rooms = two_rooms("east 東門") + [make_room(3)]
    rooms[0]["exits"]["east"] = make_exit(3)
    load(folder, rooms)
    zones.load(folder)
    ming = player("Ming", zones.world.rooms[101])
    command(ming, "close east")
    assert world_door(101, "north").closed


def test_door_commands_need_to_be_awake(folder):
    load(folder, two_rooms())
    zones.load(folder)
    ming = player("Ming", zones.world.rooms[101], Position.SLEEPING)
    command(ming, "close 木門")
    assert text_of(ming) == "在你的睡夢中嗎？\r\n\r\n> " and not world_door(101, "north").closed
    ming.position = Position.RESTING                            # 休息時可以（照 C 版）
    command(ming, "close 木門")
    assert world_door(101, "north").closed


def test_abbreviations():
    # 新指令加在表的最後，原本的縮寫不變
    assert find("o") is door_commands.do_open
    assert find("cl") is door_commands.do_close and find("c") is system.do_chat
    assert find("loc") is door_commands.do_lock and find("lo") is system.do_look
    assert find("un") is door_commands.do_unlock and find("u") is system.do_up


# ---- look ----

def test_look_shows_closed_doors(folder):
    load(folder, two_rooms(), [D(1, "north", DoorState.CLOSED)])
    zones.load(folder)
    ming = player("Ming", zones.world.rooms[101])
    command(ming, "look")
    raw = ming.writer.data.decode(ENCODING)
    assert "【出口： \x1b[35;1m*北" in raw                      # 關著的門是紫色的 *北（照 C 版）
    ming.writer.data = b""
    command(ming, "look n")
    assert text_of(ming) == "那裡沒有什麼特別的東西。\r\n木門是關著的。\r\n\r\n> "
    command(ming, "open 木門")
    text_of(ming)
    command(ming, "look")
    assert "\x1b[36;1m北" in ming.writer.data.decode(ENCODING)
    ming.writer.data = b""
    command(ming, "look n")
    assert text_of(ming) == "那裡沒有什麼特別的東西。\r\n木門是開著的。\r\n\r\n> "


# ---- 重置 D ----

def test_reset_sets_both_sides_and_closes_opened_doors(folder):
    load(folder, two_rooms(), [D(1, "north", DoorState.LOCKED)])     # 一筆 D 設兩邊
    zones.load(folder)
    assert world_door(101, "north").locked and world_door(102, "south").locked
    doors.set_state(zones.world.rooms[101], "north", DoorState.OPEN)  # 玩家打開了
    resets.reset_area(zones.world, zones.world.areas[0], resets.mobiles)
    assert world_door(101, "north").locked and world_door(102, "south").locked


def test_reset_door_without_door_is_skipped(folder, caplog):
    rooms = two_rooms() + [make_room(3)]
    rooms[0]["exits"]["east"] = make_exit(3)
    load(folder, rooms, [D(1, "east", DoorState.CLOSED)])
    with caplog.at_level(logging.WARNING):
        zones.load(folder)
    assert "a.json 的 D 設不了：房間 101 不在世界裡，或往 east 沒有門" in caplog.text


def test_instances_have_their_own_doors(folder):
    write_json(folder, "world.json", make_area("world.json", [make_room(1)], 100))
    load(folder, two_rooms(), [D(1, "north", DoorState.OPEN)], name="inst.json", area_number=300, kind="instance")
    zones.load(folder)

    async def main():
        return zones.instance("inst.json", "小明"), zones.instance("inst.json", "阿華")

    a, b = asyncio.run(main())
    doors.set_state(a.rooms[301], "north", DoorState.CLOSED)
    assert a.rooms[302].doors["south"].closed                   # 同一份的對面跟著關
    assert not b.rooms[301].doors["north"].closed and not b.rooms[302].doors["south"].closed


def test_other_side_does_not_build_dynamic_area(folder):
    # 門的對面在還沒人去過的動態區域：只改這一邊，不會因為關門就把動態區域建起來
    w, dyn = make_room(1), make_room(1)
    w["exits"]["north"] = door_exit(201)
    dyn["exits"]["south"] = door_exit(101)
    load(folder, [w], name="world.json")
    load(folder, [dyn], name="dyn.json", area_number=200, kind="dynamic")
    zones.load(folder)
    ming = player("Ming", zones.world.rooms[101])
    command(ming, "close 木門")
    assert world_door(101, "north").closed and zones.dynamic == {}
