"""顏色代碼：字串裡寫 {M 這種代碼，送出前換成色碼。色碼照抄 C 版 merc.h。"""
import re

CODES = {
    "r": "\x1b[31m",    # RED
    "R": "\x1b[31;1m",  # L_RED
    "g": "\x1b[32m",    # GREEN
    "G": "\x1b[32;1m",  # L_GREEN
    "y": "\x1b[33m",    # BROWN
    "Y": "\x1b[33;1m",  # YELLOW
    "b": "\x1b[34m",    # BLUE
    "B": "\x1b[34;1m",  # L_BLUE
    "m": "\x1b[35m",    # PURPLE
    "M": "\x1b[35;1m",  # MAGENTA
    "c": "\x1b[36m",    # CYAN
    "C": "\x1b[36;1m",  # L_CYAN
    "w": "\x1b[37m",    # GREY
    "W": "\x1b[37;1m",  # WHITE
    "D": "\x1b[30;1m",  # D_GREY
    "x": "\x1b[0m",     # NTEXT：回到原本顏色
    "{": "{",           # {{ 印出 {
}

CODE = re.compile(r"\{(.)")


def colorize(text):
    """把 {M 這種代碼換成色碼；不認得的代碼原樣留著。"""
    return CODE.sub(lambda m: CODES.get(m.group(1), m.group(0)), text)
