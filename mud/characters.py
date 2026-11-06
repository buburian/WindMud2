"""角色：玩家和 NPC 共同的部分，以及遊戲裡所有角色的名單。"""
import enum

from . import names
from .config import PROMPT

SEX_NEUTRAL, SEX_MALE, SEX_FEMALE = 0, 1, 2


class Position(enum.IntEnum):
    """角色現在的姿勢：遊戲用它判斷角色是在休息、站著走動，還是在戰鬥。

    就是手冊生物那章的 position 表，名字是手冊的 C 版名稱，要跟手冊一模一樣（tests/test_area.py 會比對）。
    """
    DEAD = 0                                # 死了
    MORTAL = 1                              # 快死了
    INCAP = 2                               # 不能動
    STUNNED = 3                             # 昏迷
    SLEEPING = 4                            # 睡覺
    RESTING = 5                             # 休息
    FIGHTING = 6                            # 戰鬥中
    STANDING = 7                            # 站著


class Character:
    """角色：玩家和 NPC 共同的部分。"""

    def __init__(self, name, sex, room):
        self.name = name
        self.sex = sex
        self.room = room                    # 所在的房間（Room）：兩份副本的同號房間是不同的 Room，所以看不到彼此
        self.position = Position.STANDING   # 現在的姿勢
        self.fighting = None                # 正在打誰（角色）
        self.fight = None                   # 在哪一場戰鬥裡（fight.Fight）
        self.sent = False                   # 這個指令有沒有送出訊息：有的話 prompt 前空一行（使用者要的，command() 用）
        self.carrying = []                  # 背包裡的物品（objects.Obj），新的在前（照 C 版）；身上穿的不在這裡
        self.equipment = {}                 # 穿在身上的：部位（inventory.SLOTS 的代號）→ Obj。生物不穿裝備（使用者說的）
        self.affects = []                   # 身上的效果（affects.Affect），放上去的順序

    def send(self, text):
        """送文字給這個角色看。NPC 沒有連線，所以什麼都不做；玩家（Player）會改成寫到連線。"""

    def prompt(self):
        """每次送完訊息後補的提示。玩家（Player）有屬性時改成顯示 HP、MP、MV。"""
        return PROMPT

    def names(self):
        """別人用來指定這個角色的名字（小寫）：玩家是名字，生物（Npc）是區域檔的 keywords。"""
        return [self.name.lower()]


def in_room(ch):
    """ch 所在房間裡的其他角色，照 look 畫面的順序：生物在前、玩家在後（各自照 characters 的順序）。

    look 和 find_in_room() 都用它，「畫面上第 n 隻」才對得上。
    """
    from .npcs import Npc                   # 坑：npcs 會 import 這個模組，在函式裡才 import
    others = [c for c in characters if c is not ch and c.room is ch.room]
    return [c for c in others if isinstance(c, Npc)] + [c for c in others if not isinstance(c, Npc)]


def find_in_room(ch, name):
    """ch 所在房間裡叫做 name 的角色，找不到是 None（使用者定的，**要找生物的指令都用它**：kill、slay、use…）。

    名字的規則在 names.py（開頭就行、3.dog 是第 3 隻）。順序照 look 畫面（in_room()），自己排最後（look 看不到自己；自己也找得到，照 C 版）。
    """
    return names.pick(in_room(ch) + [ch], name, lambda c: c.names())


characters = []  # 遊戲裡所有的角色（玩家和 NPC，所有區域物件裡的都在這），找同房間的人都從這裡找
