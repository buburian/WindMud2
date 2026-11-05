"""找同房間的角色（characters.find_in_room）：名字只打開頭、n.名字、照 look 的順序（生物在前、玩家在後、自己最後）。

kill、slay、use 和之後要找生物的指令都用它（使用者定的）。
"""
import pytest

from mud.characters import characters, find_in_room, in_room
from mud.npcs import Npc
from mud.players import Player

ROOM, ELSEWHERE = object(), object()        # find_in_room 只比 room 是不是同一個


@pytest.fixture
def room():
    """同一間房：Shabu（自己）、野狗、Ming、野貓、野狗二；隔壁還有一隻野狗。加進 characters 的順序是這樣排的。"""
    me = Player("Shabu", None, ROOM)
    dog, cat, dog2 = mobile("野狗", "dog 野狗"), mobile("野貓", "cat 野貓"), mobile("野狗二", "dog 野狗")
    characters.extend([me, dog, Player("Ming", None, ROOM), cat, dog2, mobile("隔壁的狗", "dog", ELSEWHERE)])
    yield me
    characters.clear()


def mobile(name, keywords, where=ROOM):
    n = Npc(name, 0, where)
    n.keywords = keywords.split()
    return n


def name_of(me, word):
    found = find_in_room(me, word)
    return found.name if found else None


@pytest.mark.parametrize("word, want", [
    ("dog", "野狗"), ("do", "野狗"), ("d", "野狗"), ("DOG", "野狗"), ("Do", "野狗"),     # 開頭就行，英文不分大小寫
    ("野", "野狗"), ("野貓", "野貓"), ("c", "野貓"),
    ("2.dog", "野狗二"), ("2.野", "野貓"), ("3.野", "野狗二"),                          # 第 n 個對得上的（照 look 的順序）
    ("1.dog", "野狗"), ("3.dog", None), ("0.dog", None), ("2.", None), ("x.dog", None), ("dogs", None), ("bird", None),
    ("m", "Ming"), ("ming", "Ming"), ("sh", "Shabu"), ("shabu", "Shabu"),             # 玩家用名字；自己也找得到
])
def test_find_in_room(room, word, want):
    assert name_of(room, word) == want


def test_order_is_what_look_shows(room):
    # 生物在前、玩家在後（各自照 characters 的順序），自己不在裡面；隔壁的不算
    assert [c.name for c in in_room(room)] == ["野狗", "野貓", "野狗二", "Ming"]


def test_yourself_comes_last(room):
    # 自己排在最後：別人的名字對得上就先找到別人
    sherry = Player("Sherry", None, ROOM)
    characters.append(sherry)
    assert find_in_room(room, "sh") is sherry
    assert find_in_room(room, "2.sh") is room
