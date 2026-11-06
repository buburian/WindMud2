"""容器：open、close、lock、unlock（照 C 版 act_move.c 的訊息），找的順序（門的名字 → 方向 → 東西），鑰匙，
關著不能拿、look in、封印、存檔。容器旗標跟手冊的表比對。
"""
import re
from pathlib import Path

import pytest

import mud.commands as commands
from area_helpers import make_area, make_object, make_room, write_json
from mud import objects, zones
from mud.area import ContainerFlag
from mud.characters import characters
from mud.config import ENCODING
from mud.players import Player

AREA_MANUAL = Path(__file__).resolve().parent.parent / "docs" / "區域製作手冊.md"


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


def obj(vnum, short, keywords, item_type, values=(0, 0, 0, 0), wear="1"):
    o = make_object(vnum)
    o.update(short=short, keywords=keywords, item_type=item_type, values=list(values), wear_flags=wear, affects=[], weight=1,
             extra_descriptions=[])
    return o


OBJECTS = [
    obj(1, "寶箱", "chest 寶箱", 15, (50, 1 + 4 + 8, 4, 0)),          # 可以關、關著、鎖著，鑰匙是物品 4
    obj(2, "袋子", "bag 袋子", 15, (50, 1, -1, 0)),                    # 可以關、開著、沒有鎖
    obj(3, "木盒", "crate 木盒", 15, (50, 0, -1, 0)),                  # 關不起來
    obj(4, "鑰匙", "key 鑰匙", 18),
    obj(5, "藥水", "potion 藥水", 10, (5, "cure light", "", "")),
    obj(6, "項鍊", "necklace 項鍊", 9, wear="1|4"),
    obj(7, "封箱", "sealed 封箱", 15, (50, 16 + 4 + 1, -1, 1234)),     # 可以封印、有密碼、關著
    obj(8, "封印盒", "seal 封印盒", 15, (50, 32, -1, 0)),               # 封印著：撿不起來
]


@pytest.fixture
def room(tmp_path):
    """房間 101 往北是木門（鑰匙是物品 104，一開始開著），通到 102。"""
    rooms = [make_room(1, north=2), make_room(2, south=1)]
    for r, d in ((rooms[0], "north"), (rooms[1], "south")):
        r["exits"][d].update(locks=1, keywords="木門 door", key=4)
    write_json(tmp_path, "a.json", make_area("a.json", rooms, 100, objects=OBJECTS))
    zones.load(tmp_path)
    yield zones.world.rooms[101]
    characters.clear()
    zones.stop()


def make(n):
    return objects.create(100 + n, 1, None)


def put(room, *numbers):
    for n in numbers:
        room.contents.insert(0, make(n))
    return room.contents[0]


def person(name, room):
    p = Player(name, FakeWriter(), room)
    characters.append(p)
    return p


def plain(p):
    text = re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))
    p.writer.data = b""
    return text


def say(p, line):
    plain(p)
    commands.command(p, line)
    return plain(p).removesuffix("\r\n\r\n> ")


def test_container_flags_match_the_manual():
    text = AREA_MANUAL.read_text(encoding="utf-8")
    part = text[text.index("### 容器旗標"):text.index("## resets")]
    rows = {int(n): name for n, name in re.findall(r"\| (\d+) \| (\w+) \|", part)}
    assert rows == {int(f): f.name.lower() for f in ContainerFlag}


def test_created_containers_start_as_written(room):
    chest, bag = make(1), make(2)
    assert chest.container == ContainerFlag.CLOSEABLE | ContainerFlag.CLOSED | ContainerFlag.LOCKED and chest.key == 104
    assert bag.container == ContainerFlag.CLOSEABLE and bag.key is None and not bag.closed()
    assert make(5).container is None                                      # 不是容器


def test_open_and_close(room):
    ming, hua = person("Ming", room), person("Hua", room)
    put(room, 2)
    assert say(ming, "open bag") == "它已經打開了。"
    plain(hua)
    assert say(ming, "close bag") == "你關起了【袋子/bag】。"
    assert "Ming關起了【袋子/bag】。" in plain(hua)
    assert say(ming, "close bag") == "它已經關起來了。"
    assert say(ming, "open bag") == "你打開了【袋子/bag】。"
    assert "Ming打開了【袋子/bag】。" in plain(hua)


def test_not_closeable(room):
    ming = person("Ming", room)
    put(room, 3)
    assert say(ming, "close crate") == "你不能這樣作。"
    crate = room.contents[0]
    crate.container |= ContainerFlag.CLOSED
    assert say(ming, "open crate") == "你不能這樣作。"


@pytest.mark.parametrize("line, want", [("open potion", "這不是個容器。"), ("close potion", "這不是容器。"),
                                        ("lock potion", "這不是容器。"), ("unlock potion", "那不是容器。")])
def test_not_a_container(room, line, want):
    ming = person("Ming", room)
    put(room, 5)
    assert say(ming, line) == want


def test_lock_and_unlock_with_the_key(room):
    ming, hua = person("Ming", room), person("Hua", room)
    put(room, 1)
    assert say(ming, "open chest") == "它被鎖住了。"
    assert say(ming, "unlock chest") == "你沒有這個鎖的鑰匙。"
    ming.carrying.append(make(4))
    plain(hua)
    assert say(ming, "unlock chest") == "【清脆的喀啦一聲】"
    assert "Ming打開【寶箱/chest】的鎖。" in plain(hua)
    assert say(ming, "unlock chest") == "它的鎖已被打開了。"
    assert say(ming, "open chest") == "你打開了【寶箱/chest】。"
    assert say(ming, "lock chest") == "它沒有關起來，怎麼上鎖？"
    assert say(ming, "unlock chest") == "它沒關起來。"
    say(ming, "close chest")
    assert say(ming, "lock chest") == "【清脆的喀啦一聲】"
    assert "Ming鎖上了【寶箱/chest】。" in plain(hua)
    assert say(ming, "lock chest") == "它被已經鎖起來了。"
    ming.carrying.clear()                                                 # 照 C 版：先看有沒有鑰匙，再看鎖了沒
    assert say(ming, "lock chest") == "你沒有鑰匙，所以不能上鎖。" and say(ming, "unlock chest") == "你沒有這個鎖的鑰匙。"


def test_no_lock(room):
    ming = person("Ming", room)
    put(room, 2)
    say(ming, "close bag")
    assert say(ming, "lock bag") == "沒辦法鎖起來。"
    assert say(ming, "unlock bag") == "沒辦法打開這個鎖。"


def test_a_key_you_hold_counts(room):
    ming = person("Ming", room)
    put(room, 1)
    ming.equipment["hold"] = make(4)                                     # 身上的也算（照 C 版 has_key 看身上全部）
    assert say(ming, "unlock chest") == "【清脆的喀啦一聲】"


def test_sealed(room):
    ming = person("Ming", room)
    put(room, 7)
    assert say(ming, "open sealed") == "它被封印住了。"                   # 封印、解開的指令還沒做
    put(room, 8)
    assert say(ming, "get seal") == "你無法拿起被封印的東西..."
    # get all 跳過封印著的（封印盒）；封箱只是可以封印、還沒封印，撿得起來
    assert say(ming, "get all") == "你拿起了【封箱/sealed】。"
    assert [o.name for o in ming.carrying] == ["封箱"] and [o.name for o in room.contents] == ["封印盒"]


def test_closed_containers_hide_what_is_inside(room):
    ming = person("Ming", room)
    chest = put(room, 1)
    chest.contains = [make(5)]
    assert say(ming, "get potion chest") == "【寶箱/chest】關起來了。"
    assert say(ming, "get all chest") == "【寶箱/chest】關起來了。"
    assert say(ming, "look in chest") == "它是蓋起來的。"
    chest.container = ContainerFlag.CLOSEABLE                             # 打開了
    assert say(ming, "look in chest") == "寶箱裝著：\r\n     藥水/potion"
    assert say(ming, "get potion chest") == "你把【藥水/potion】從【寶箱/chest】拿出來。"


def test_containers_you_carry(room):
    ming = person("Ming", room)
    ming.carrying.append(make(2))
    assert say(ming, "close bag") == "你關起了【袋子/bag】。"
    assert say(ming, "look in bag") == "它是蓋起來的。"


def test_doors_come_before_things(room):
    # 使用者選的順序：門的名字 → 方向 → 東西。open n 一定是北邊的門，就算地上有 n 開頭的東西
    ming = person("Ming", room)
    put(room, 6)
    assert say(ming, "close n") == "你關上了木門。"
    assert say(ming, "open door") == "你打開了木門。"
    assert say(ming, "open neck") == "這不是個容器。"                    # 不是方向：才找東西
    assert say(ming, "open xyz") == "這裡沒有叫做「xyz」的門。"


def test_doors_use_real_keys(room):
    ming = person("Ming", room)
    say(ming, "close door")
    assert say(ming, "lock door") == "你沒有鑰匙，怎麼上鎖呢？"
    ming.carrying.append(make(4))
    assert say(ming, "lock door") == "你鎖上了木門。"
    assert say(ming, "unlock door") == "你打開了木門的鎖。"


def test_save_keeps_the_container_state(room):
    chest = make(1)
    chest.container &= ~ContainerFlag.LOCKED
    back = objects.from_data(objects.to_data(chest))
    assert (back.container, back.key, back.seal) == (chest.container, 104, 0)
    old = objects.to_data(make(5))
    for k in ("container", "key", "seal"):
        del old[k]
    assert objects.from_data(old).container is None                       # 舊存檔沒有這幾個欄位
