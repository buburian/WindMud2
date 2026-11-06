"""送訊息給一群人，並代換 $ 碼（名字、代名詞、帶進來的文字）。"""
import contextlib
import logging
import re

from .characters import Position, characters
from .color import colorize

log = logging.getLogger(__name__)

TO_CHAR, TO_VICT, TO_ROOM, TO_NOTVICT = 0, 1, 2, 3
# 正在收訊息的一段（戰鬥的一回合、技能那幾下、效果的一個 tick：有 tell([(讀的人, 文字)]) 的）。
# 有的話 notify() 不馬上送、放進最上面那一段，那一段結束時每個人一起送（使用者要的：打死生物時腳本說的話在「斷氣」後面、只有一個 prompt）
blocks = []

HE_SHE = ("它", "他", "她")             # 照 SEX_NEUTRAL、SEX_MALE、SEX_FEMALE 的順序
HIS_HER = ("它的", "他的", "她的")

CODE = re.compile(r"\$(.)")


def act(fmt, ch, vch=None, t=None, T=None, to=TO_ROOM):
    """把 fmt 代換後送出去。ch 是做這件事的角色，vch 是對象，兩個都是角色（玩家或 NPC）。

    to：TO_CHAR 自己、TO_VICT 對象、TO_ROOM 同房間自己以外的人、TO_NOTVICT 同房間自己和對象以外的人。
    送給 NPC 等於沒送：NPC 沒有連線，它的 send() 什麼都不做。
    同房間的事（TO_ROOM、TO_NOTVICT）不送給睡著的人（照 C 版）；TO_VICT 照送，chat、tell 睡著也收得到。
    """
    for reader, text in compose(fmt, ch, vch, t, T, to):
        if reader is ch:
            reader.send(text + "\n")            # prompt 由 command() 補
        else:
            notify(reader, text)


def compose(fmt, ch, vch=None, t=None, T=None, to=TO_ROOM):
    """跟 act() 一樣算出誰收到什麼，但不送：回傳 [(讀的人, 代換好的文字)]。

    要把好幾句合成一段再送的地方用（戰鬥的一回合：combat.py 的訊息放進 Fight.messages，回合結束才送）。
    """
    if to == TO_CHAR:
        readers = [ch]
    elif to == TO_VICT:
        readers = [vch] if vch is not None and vch is not ch else []
    else:
        readers = [c for c in characters
                   if c.room == ch.room and c is not ch and (to == TO_ROOM or c is not vch)
                   and c.position > Position.SLEEPING]
    return [(reader, fill(fmt, ch, vch, t, T, reader)) for reader in readers]


def notify(ch, text, apart=False):
    """主動送給 ch 的訊息（不是 ch 自己下指令引起的，例如別人說話、天氣變化）。

    先換行，才不會接在 ch 的 prompt 後面；說完空一行再補回 prompt（跟指令的訊息一樣）。
    text 不轉顏色代碼：act() 傳進來的已經轉過，再轉一次會讓玩家打的 {R 變成顏色。
    ch 自己的指令還沒跑完（例如他說話，生物的腳本馬上回話）：當作那個指令的回覆、不補 prompt，指令跑完 command() 會補，才不會有兩個 prompt。
    這時好幾句連在一起送（使用者要的）：跟指令自己的訊息之間空一行，句子之間不空行；apart 是另起一段、前面一定空一行（例如傳送到新房間的畫面）。
    """
    from . import scripts                   # 坑：scripts 會用到這裡，在函式裡才 import
    if blocks and not (isinstance(blocks[-1], Block) and ch in scripts.commanding):
        blocks[-1].tell([(ch, "\n" + text if apart else text)])     # 正在收的一段：放進去，那一段結束時一起送
        return
    if ch in scripts.commanding:
        ch.send(("\n" if ch.sent and (apart or not ch.notified) else "") + text + "\n")
        ch.notified = True
        return
    ch.send(f"\n{text}\n\n{ch.prompt()}")      # 有訊息：prompt 前空一行


class Block:
    """一個指令、一串腳本送給別人的訊息先收起來，最後每個人送一次、一個 prompt（使用者要的：旁邊的人也只有一個 prompt）。

    下指令的那個人不收在這裡（notify() 照「他自己的指令還沒跑完」送，prompt 由 command() 補）。
    """

    def __init__(self):
        self.by = {}

    def tell(self, pairs):
        for reader, text in pairs:
            self.by.setdefault(reader, []).append(text)

    def flush(self):
        for reader, lines in self.by.items():
            notify(reader, "\n".join(lines))


@contextlib.contextmanager
def gathering():
    """開始收一段（command()、一串腳本 scripts.one_chain() 用）。已經在收了（例如戰鬥的一回合、外面的指令）就併進外面那段。"""
    if blocks:
        yield
        return
    block = Block()
    blocks.append(block)
    try:
        yield
    finally:
        blocks.remove(block)
        block.flush()


def fill(fmt, ch, vch, t, T, reader):
    """先把 fmt 的顏色代碼換成色碼，再代換 $ 碼。

    小寫是自己（ch），大寫是對象（vch）；$t、$T 是帶進來的文字。
    顏色要先換：玩家的字是代換時才放進去的，這樣他們打的 {R 才會原樣顯示、不會變色。
    """

    def one(m):
        code = m.group(1)
        who = ch if code.islower() else vch
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
            log.warning(f"act：無法代換 {m.group(0)}，訊息：{fmt}")
            return m.group(0)
        return value

    return CODE.sub(one, colorize(fmt))
