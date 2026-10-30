import json
from pathlib import Path

import pytest

from mud import area

AREAS = Path(__file__).resolve().parent.parent / "areas"


def write(folder, name, rooms):
    (folder / name).write_text(json.dumps({"schema_version": 1, "rooms": rooms}), encoding="utf-8")


def room(vnum, **exits):
    return {"vnum": vnum, "name": f"房間{vnum}", "description": "",
            "exits": {d: {"to_room": to} for d, to in exits.items()}}


def test_test_area_has_two_rooms_linked_north_south():
    area.load(AREAS)
    assert set(area.rooms) == {1, 2}
    assert area.rooms[1].exits == {"north": 2}
    assert area.rooms[2].exits == {"south": 1}


def test_duplicate_vnum_is_an_error(tmp_path):
    write(tmp_path, "a.json", [room(1)])
    write(tmp_path, "b.json", [room(1)])
    with pytest.raises(ValueError, match="重複"):
        area.load(tmp_path)


def test_exit_to_missing_room_is_an_error(tmp_path):
    write(tmp_path, "a.json", [room(1, north=9)])
    with pytest.raises(ValueError, match="不存在"):
        area.load(tmp_path)


def test_failed_load_keeps_old_rooms(tmp_path):
    area.load(AREAS)
    write(tmp_path, "a.json", [room(1, north=9)])
    with pytest.raises(ValueError):
        area.load(tmp_path)
    assert set(area.rooms) == {1, 2}
