"""角色：玩家和 NPC 共同的部分，以及遊戲裡所有角色的名單。"""
import enum

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

    def send(self, text):
        """送文字給這個角色看。NPC 沒有連線，所以什麼都不做；玩家（Player）會改成寫到連線。"""

    def prompt(self):
        """每次送完訊息後補的提示。玩家（Player）有屬性時改成顯示 HP、MP、MV。"""
        return PROMPT


characters = []  # 遊戲裡所有的角色（玩家和 NPC，所有區域物件裡的都在這），找同房間的人都從這裡找
