"""已登入的玩家，以及送文字給玩家。"""
from .telnet import encode

players = {}  # writer → 名字（已登入的人）


def send(writer, text):
    writer.write(encode(text))
