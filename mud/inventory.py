"""角色身上的物品：背包（ch.carrying）、裝備欄（ch.equipment）、件數和負重、穿上和卸下（玩家角色手冊「物品和裝備」）。

指令在 commands/items.py；訊息照 C 版 act_obj.c。所有訊息都放進 Lines，指令最後一次送：
自己那段是指令的回覆，別人每人只 notify 一次（一件一個 act() 的話，get all 會讓旁邊的人看到好幾個 prompt）。
生物不穿裝備（使用者說的）；生物撿東西不檢查負重、件數（生物沒有主屬性）。
"""
from . import objects, stats
from .act import TO_CHAR, TO_ROOM, compose, notify
from .equipment import TWO_HANDED

# 裝備欄的部位，照 C 版 where_name 的順序和名稱（eq 照這個順序列）。戒指兩個；頸、手腕各一件（手冊：手腕當作一雙）
SLOTS = (
    ("light", "照明用具"), ("finger_l", "左手手指"), ("finger_r", "右手手指"), ("neck", "脖子上的"), ("body", "穿在身上"),
    ("head", "戴在頭上"), ("legs", "綁在腿上"), ("feet", "穿在腳上"), ("hands", "穿在手上"), ("arms", "雙手手臂"),
    ("offhand", "左手盾牌"), ("about", "披在身上"), ("waist", "圍在腰上"), ("wrist", "雙手手腕"), ("wield", "右手武器"),
    ("hold", "手中握著"),
)
OFFHAND_WEAPON_LABEL, TWO_HANDED_LABEL = "左手武器", "雙手武器"

# 穿上的句子（自己, 同房間的人），照 C 版 wear_obj；$t 是物品的名字
WEAPON_WORDS = ("你把【$t】握為手中的武器。", "$n把【$t】握為手中的武器。")
WEAR_WORDS = {
    "light": ("你點燃【$t】並且把它高高舉起。", "$n點燃【$t】並且把它高高舉起。"),
    "finger_l": ("你把【$t】套上左手手指。", "$n把【$t】套上$s左手手指。"),
    "finger_r": ("你把【$t】套上右手手指。", "$n把【$t】套上$s右手手指。"),
    "neck": ("你把【$t】戴在脖子上。", "$n把【$t】戴在$s脖子上。"),
    "body": ("你把【$t】穿在身上。", "$n把【$t】穿在$s身上。"),
    "head": ("你把【$t】戴在頭上。", "$n把【$t】戴在$s頭上。"),
    "legs": ("你把【$t】綁在腿上。", "$n把【$t】綁在$s腿上。"),
    "feet": ("你把【$t】穿在腳上。", "$n把【$t】穿在$s腳上。"),
    "hands": ("你把【$t】戴在手上。", "$n把【$t】戴在$s手上。"),
    "arms": ("你把【$t】裝在手臂上。", "$n把【$t】裝在$s手臂上。"),
    "offhand": ("你把【$t】做為盾牌。", "$n把【$t】做為盾牌。"),
    "about": ("你把【$t】披在身上。", "$n把【$t】披在$s身上。"),
    "waist": ("你把【$t】圍在腰上。", "$n把【$t】圍在$s腰上。"),
    "wrist": ("你把【$t】裝在手腕上。", "$n把【$t】裝在$s手腕上。"),
    "wield": WEAPON_WORDS,
    "hold": ("你把【$t】握到手裡。", "$n把【$t】握到$s手裡。"),
}
TOO_MANY = "【$t】你不能攜帶這麼多的物品。"       # 照 C 版
TOO_HEAVY = "【$t】你不能攜帶這麼重的物品。"


class Lines:
    """一個指令的訊息先收起來，最後一次送（send()）：ch 那段當作指令的回覆，別人每人 notify 一次。"""

    def __init__(self, ch):
        self.ch, self.by = ch, {}

    def add(self, fmt, to=TO_CHAR, t=None, T=None, vch=None):
        for reader, text in compose(fmt, self.ch, vch, t=t, T=T, to=to):
            self.by.setdefault(reader, []).append(text)

    def pairs(self):
        """收起來的訊息，寫成 act.compose() 那種 [(讀的人, 文字)]：要放進別的一段一起送時用（例如戰鬥那一回合的 Fight.tell）。"""
        return [(reader, text) for reader, lines in self.by.items() for text in lines]

    def send(self):
        for reader, lines in self.by.items():
            text = "\n".join(lines)
            if reader is self.ch:
                reader.send(text + "\n")    # prompt 由 command() 補
            else:
                notify(reader, text)


def is_player(ch):
    """有屬性的玩家（有主屬性才算得出負重）。生物、測試直接建的角色不是。"""
    return bool(getattr(ch, "primaries", None))


def worn(ch):
    """身上穿的物品（雙手武器只算一次）。"""
    return list(ch.equipment.values())


def carry_weight(ch):
    """背包加身上穿的重量（手冊：身上穿的裝備也算重量）。"""
    return sum(objects.weight(o) for o in ch.carrying + worn(ch))


def over_limit(ch, obj):
    """ch 再拿 obj 會超過哪一個：件數是 "count"、負重是 "weight"，都沒超過是 None。生物不檢查。"""
    if not is_player(ch):
        return None
    if len(ch.carrying) + 1 > stats.CARRY_COUNT:
        return "count"
    if carry_weight(ch) + objects.weight(obj) > stats.carry_limit(ch):
        return "weight"
    return None


def room_for(ch, obj, out):
    """ch 能不能再拿 obj（件數、負重）：不能就把訊息放進 out，回傳 False。生物不檢查。"""
    reason = over_limit(ch, obj)
    if reason is not None:
        out.add(TOO_MANY if reason == "count" else TOO_HEAVY, t=objects.short(obj))
    return reason is None


def where(ch, obj):
    """obj 穿在 ch 的哪個部位（雙手武器是 wield），沒穿是 None。"""
    return next((pos for pos, o in ch.equipment.items() if o is obj), None)


def label(pos, obj):
    """eq 裡這個部位的名稱：副手放武器是【左手武器】，主手放雙手武器是【雙手武器】。"""
    if pos == "offhand" and obj.is_weapon():
        return OFFHAND_WEAPON_LABEL
    if pos == "wield" and obj.slot == TWO_HANDED:
        return TWO_HANDED_LABEL
    return dict(SLOTS)[pos]


def blocker(ch, pos):
    """pos 被什麼佔住：那裡穿的東西；副手被雙手武器佔住時是那把雙手武器。空的是 None。"""
    if pos == "offhand" and "offhand" not in ch.equipment:
        main = ch.equipment.get("wield")
        return main if main is not None and main.slot == TWO_HANDED else None
    return ch.equipment.get(pos)


def targets(ch, obj):
    """obj 要穿到哪些部位：戒指先放空的那隻手（都有就是左手，wear xxx 會換下來）；雙手武器佔主手和副手。"""
    if obj.slot == "finger":
        free = [p for p in ("finger_l", "finger_r") if p not in ch.equipment]
        return free[:1] or ["finger_l"]
    if obj.slot == TWO_HANDED:
        return ["wield", "offhand"]
    return [obj.slot]


def wear(ch, obj, replace, out):
    """ch 把背包裡的 obj 穿上（照 C 版 wear_obj）。replace：部位有東西就先換下來（wear xxx）；不換（wear all）就跳過。

    回傳有沒有穿上。訊息放進 out；穿上之後要 refresh（指令最後做一次）。
    """
    if not is_player(ch):
        out.add("你沒有辦法使用這項物品。")
        return False
    if obj.slot is None:
        if replace:
            out.add("這項物品你沒有辦法裝備，舉起或握到手裡。")
        return False
    if ch.level < obj.level:
        out.add(f"你至少等級(Level)要達到【{obj.level}】級以上才能使用這項物品。")
        out.add("$n想嘗試裝備上【$t】，卻因為自己的等級(Level)不足而苦惱。", TO_ROOM, t=objects.short(obj))
        return False
    if obj.is_weapon() and objects.weight(obj) > stats.wield_limit(ch):
        out.add("這把武器太重了，你力量(Str)過小，沒有辦法拿來當武器使用。")
        return False
    offhand_weapon = obj.slot == "offhand" and obj.is_weapon()
    if offhand_weapon:
        main = ch.equipment.get("wield")
        if main is None or not main.is_weapon() or main.slot == TWO_HANDED:
            out.add("你要先拿主手的武器，才能雙持。")
            return False
    positions = targets(ch, obj)
    old = []                                # 要換下來的（雙手武器只算一次）
    for pos in positions:
        o = blocker(ch, pos)
        if o is not None and o not in old:
            old.append(o)
    if old and not replace:
        return False
    if is_player(ch) and len(ch.carrying) - 1 + len(old) > stats.CARRY_COUNT:
        out.add(TOO_MANY, t=objects.short(old[-1]))
        return False
    # 換主手武器時副手的武器留著（主手還是有武器）；換成雙手武器時副手的也一起換下來（positions 有 offhand）
    for o in sorted(old, key=lambda o: where(ch, o) != "offhand"):    # 先卸副手，主手才卸得下來
        take_off(ch, o, out, check=False)
    ch.carrying.remove(obj)
    ch.equipment[positions[0]] = obj
    mine, theirs = WEAPON_WORDS if offhand_weapon or obj.slot == TWO_HANDED else WEAR_WORDS[positions[0]]
    out.add(mine, t=objects.short(obj))
    out.add(theirs, TO_ROOM, t=objects.short(obj))
    return True


def take_off(ch, obj, out, check=True):
    """ch 把穿著的 obj 卸下來放回背包（照 C 版 remove_obj）。回傳有沒有卸下。

    check：背包滿了不能卸；有副手武器時不能先卸主手的武器（副手武器要主手有武器）。
    """
    pos = where(ch, obj)
    if check:
        if pos == "wield" and ch.equipment.get("offhand") is not None and ch.equipment["offhand"].is_weapon():
            out.add("你要先卸下左手的武器。")
            return False
        if is_player(ch) and len(ch.carrying) + 1 > stats.CARRY_COUNT:
            out.add(TOO_MANY, t=objects.short(obj))
            return False
    del ch.equipment[pos]
    ch.carrying.insert(0, obj)
    out.add("你卸下了【$t】。", t=objects.short(obj))
    out.add("$n卸下了【$t】。", TO_ROOM, t=objects.short(obj))
    return True


def changed(ch):
    """穿脫之後：從頭算屬性（HP、MP、MV 夾在新上限），打架中換了武器就重排出手（fight.Fight.arm）。"""
    if is_player(ch) and getattr(ch, "panel", None):
        stats.refresh(ch)
    if ch.fight is not None:
        ch.fight.arm(ch)
