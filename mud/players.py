"""玩家：有連線的角色，以及送文字到連線。"""
from .characters import SEX_MALE, Character, characters
from .telnet import encode


class Player(Character):
    """已登入的玩家。"""

    def __init__(self, name, writer, room, sex=SEX_MALE):  # 還沒有建立角色，性別先都當男生
        super().__init__(name, sex, room)
        self.writer = writer                 # 這個玩家的連線
        self.reply = None                    # 最後一個 tell 我的玩家（Player），reply 指令用

    def send(self, text):
        send(self.writer, text)              # 下面那個 send()：寫到連線


def online_players():
    """在線的玩家：characters 裡的 Player。"""
    return [c for c in characters if isinstance(c, Player)]


def send(writer, text):
    writer.write(encode(text))
