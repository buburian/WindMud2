"""送訊息給一群人，並代換 $ 碼（名字、代名詞、帶進來的文字）。"""
import re

from .config import PROMPT
from .players import players, send

TO_CHAR, TO_VICT, TO_ROOM, TO_NOTVICT = 0, 1, 2, 3

HE_SHE = ("它", "他", "她")             # 照 SEX_NEUTRAL、SEX_MALE、SEX_FEMALE 的順序
HIS_HER = ("它的", "他的", "她的")

CODE = re.compile(r"\$(.)")


def act(fmt, ch, vch=None, t=None, T=None, to=TO_ROOM):
    """把 fmt 代換後送出去。ch 是做這件事的人，vch 是對象，兩個都是 writer。

    to：TO_CHAR 自己、TO_VICT 對象、TO_ROOM 自己以外的人、TO_NOTVICT 自己和對象以外的人。
    現在沒有房間，「同房間」先等於所有在線的人。
    """
    if to == TO_CHAR:
        readers = [ch]
    elif to == TO_VICT:
        readers = [vch] if vch is not None and vch is not ch else []
    elif to == TO_ROOM:
        readers = [w for w in players if w is not ch]
    else:
        readers = [w for w in players if w is not ch and w is not vch]
    for reader in readers:
        text = fill(fmt, ch, vch, t, T, reader)
        if reader is ch:
            send(reader, text + "\n")           # prompt 由 command() 補
        else:
            # 先換行，才不會接在對方的 prompt 後面；說完再補回對方的 prompt
            send(reader, f"\n{text}\n{PROMPT}")


def fill(fmt, ch, vch, t, T, reader):
    """代換 $ 碼。小寫是自己（ch），大寫是對象（vch）；$t、$T 是帶進來的文字。"""

    def one(m):
        code = m.group(1)
        who = players.get(ch if code.islower() else vch)
        value = None
        if code == "t":
            value = t
        elif code == "T":
            value = T
        elif who is not None:
            if code == "n" and reader is ch:
                value = "你"
            elif code in "nN":
                value = who.name
            elif code in "eEmM":
                value = HE_SHE[who.sex]
            elif code in "sS":
                value = HIS_HER[who.sex]
        if value is None:
            # 寫錯的碼、或沒給對象：原樣留著，在伺服器視窗提醒，不讓連線掛掉
            print(f"act：無法代換 {m.group(0)}，訊息：{fmt}", flush=True)
            return m.group(0)
        return value

    return CODE.sub(one, fmt)
