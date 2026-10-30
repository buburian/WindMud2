"""角色：玩家和 NPC 共同的部分，以及遊戲裡所有角色的名單。"""

SEX_NEUTRAL, SEX_MALE, SEX_FEMALE = 0, 1, 2


class Character:
    """角色：玩家和 NPC 共同的部分。"""

    def __init__(self, name, sex, room):
        self.name = name
        self.sex = sex
        self.room = room                    # 所在房間的 vnum

    def send(self, text):
        """送文字給這個角色看。NPC 沒有連線，所以什麼都不做；玩家（Player）會改成寫到連線。"""


characters = []  # 遊戲裡所有的角色（玩家和 NPC），找同房間的人都從這裡找
