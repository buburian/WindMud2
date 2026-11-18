"""看不見的人（玩家角色手冊「看不見的人和光圈」，使用者 2026-11-17 定的）：隱形、藏匿、偵測、粉光、現形。

- 隱形（AffectFlag.INVISIBLE）、藏匿（HIDE）：同房間的人看不到他（light.visible() 問 unseen()），跟很暗一樣：
  look 裡沒有他、找不到他、名字變「某人」、看不到他走進來。
- 看得到的人：imm、有 DETECT_INVIS（看得到隱形）、DETECT_HIDDEN（看得到藏匿）的；身上有 FAERIE_FIRE（粉光）的人隱形、藏匿都沒用。
- 現形（reveal()）：出手或被打（combat.land()、skills.debuff()，使用者選的：C 版只有出手），拿掉隱形、藏匿的效果，
  生物天生的旗標（區域檔的 affected_by）也拿掉，直到牠重生（照 C 版）。
坑：affects 會 import combat → death → fight，在函式裡才 import。
"""
from .area import AffectFlag

# 藏起來的方式 → (看得到它的旗標, 現形時旁人看到的那句)，照 C 版
HIDING = {
    AffectFlag.INVISIBLE: (AffectFlag.DETECT_INVIS, "$n漸漸地現出了自己的身影。"),
    AffectFlag.HIDE: (AffectFlag.DETECT_HIDDEN, "$n現身出來了。"),
}


def unseen(reader, ch):
    """ch 隱形或藏匿，reader 看不到他（imm 都看得到；ch 身上有粉光就藏不住）。不管在不在同一間房，那個由 light.visible() 看。"""
    from . import affects
    if getattr(reader, "imm", False) or affects.has_flag(ch, AffectFlag.FAERIE_FIRE):
        return False
    return any(affects.has_flag(ch, flag) and not affects.has_flag(reader, detect) for flag, (detect, _) in HIDING.items())


def reveal(ch):
    """ch 現形：拿掉身上隱形、藏匿的效果和天生的旗標。回傳要送的 [(讀的人, 文字)]（act.compose() 那種）：
    旁人看到的那句（照 C 版），自己看到那個效果消失時的那句。先全部拿掉才寫訊息，旁人看到的才是名字、不是「某人」。
    """
    from . import affects
    from .act import TO_CHAR, TO_ROOM, compose
    flags = [flag for flag in HIDING if affects.has_flag(ch, flag)]
    if not flags:
        return []
    gone = [a for a in ch.affects if any(flag in a.flags for flag in flags)]
    ch.affects[:] = [a for a in ch.affects if a not in gone]
    for flag in flags:
        if flag in getattr(ch, "affected_by", AffectFlag(0)):
            ch.affected_by &= ~flag
    affects.changed(ch)
    pairs = [pair for flag in flags for pair in compose(HIDING[flag][1], ch, to=TO_ROOM)]
    return pairs + [pair for a in gone for pair in compose(affects.off_message(a), ch, to=TO_CHAR)]
