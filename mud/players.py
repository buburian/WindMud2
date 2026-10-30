"""已登入的玩家，以及送文字給玩家。"""
from .telnet import encode

SEX_NEUTRAL, SEX_MALE, SEX_FEMALE = 0, 1, 2


class Player:
    """已登入的玩家。"""

    def __init__(self, name, sex=SEX_MALE):  # 還沒有建立角色，性別先都當男生
        self.name = name
        self.sex = sex
        self.reply = None                    # 最後一個 tell 我的人（writer），reply 指令用


players = {}  # writer → Player（已登入的人）


def send(writer, text):
    writer.write(encode(text))
