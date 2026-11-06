"""系統類指令。每個指令都長 do_xxx(ch, arg)：ch 是下指令的角色，回傳 False 代表要斷線。"""
import logging
import re

from .. import affects, objects, save, stats, weather, zones
from ..act import TO_CHAR, TO_ROOM, TO_VICT, act
from ..area import DIRECTIONS, REVERSE, MobTier
from ..characters import SEX_FEMALE, SEX_MALE, Position, characters, in_room
from ..color import colorize
from ..config import ENCODING
from ..npcs import Npc
from ..players import online_players

log = logging.getLogger(__name__)


def do_look(ch, arg):
    if not arg:
        ch.send(look(ch))
        return
    room = ch.room
    words = arg.split()
    target = words[0].lower()
    if "in".startswith(target):             # look in 東西（照 C 版：i、in 都算，比細看先找）
        look_in(ch, words[1] if len(words) > 1 else "")
        return
    # 照 C 版的順序：先找房間裡可以細看的東西（名字要整個字一樣），再把它當成方向（n、no、north 都算北）
    for keywords, text in room.extra_descriptions:
        if target in keywords:
            ch.send(block(text))
            return
    direction = next((d for d in DIRECTIONS if d.startswith(target)), None)
    if direction is None:
        ch.send("在這裡找不到你要看的東西。\n")
        return
    text = room.exit_descriptions.get(direction)
    ch.send(block(text) if text else "那裡沒有什麼特別的東西。\n")    # 沒寫描述，或那個方向沒有出口
    door = room.doors.get(direction)
    if door is not None:                    # 照 C 版接著說門的狀態；C 版沒寫名字就不說，我們叫它「門」
        ch.send(f"{door.name}是{'關著' if door.closed else '開著'}的。\n")


def look_in(ch, name):
    """look in 東西：看地上或背包裡的容器、屍體裡有什麼（照 C 版 act_info.c 的訊息）。"""
    if not name:
        ch.send("你想看些什麼東西？\n")
        return
    obj = objects.find(ch.room.contents + ch.carrying, name)
    if obj is None:
        ch.send("這裡沒有你想看的東西。\n")
        return
    if not obj.is_container():
        ch.send("這不是一個容器。\n")
        return
    if obj.closed():
        ch.send("它是蓋起來的。\n")             # 照 C 版
        return
    # 每件一行、前面空 5 格（照 C 版；C 版會把一樣的合成「( 2) 」，先不做）
    inside = "".join(f"     {objects.short(o)}\n" for o in obj.contains) or "     空無一物。\n"
    ch.send(f"{obj.name}裝著：\n{inside}")


def block(text):
    """區域作者寫的一段文字：轉顏色代碼，最後補上換行。"""
    text = colorize(text)
    return text if text.endswith("\n") else text + "\n"


def look(ch):
    """ch 所在房間的樣子：名稱、出口、描述，空一行再列房間裡的東西。登入時也用這個。

    順序（使用者定的）：先生物（NPC），再玩家，最後是地上的物品（新的在前）。
    生物、玩家、地上的物品都是亮白。名字不經過 colorize()：玩家名字只有英文字母，之後 NPC 用區域作者寫的描述時再看要不要轉顏色代碼。
    """
    room = ch.room
    # 關著的門是紫色的 *北（照 C 版），其他出口亮青色
    exits = "".join((" {M*" if d in room.doors and room.doors[d].closed else " {C") + DIRECTIONS[d]
                    for d in DIRECTIONS if d in room.exits) or " 沒有"
    # 房間的文字是區域作者寫的，可以用顏色代碼；角色名字是後面才接上去的，不會被轉
    text = colorize("{G【{Y" + room.name + "{G】{x\n{G【出口：" + exits + "{G】{x\n" + room.description)
    if not text.endswith("\n"):
        text += "\n"
    lines = [f"{tagged(c)}\n" for c in in_room(ch)] + [f"{objects.on_floor(o)}\n" for o in room.contents]
    if lines:
        text += "\n" + "".join(lines)
    return text


def appearance(c):
    """房間裡看到 c 的那一行：站著的生物有 long 就顯示 long（照 C 版），其他照姿勢寫「名字站在這裡。」…"""
    if isinstance(c, Npc) and c.position == Position.STANDING and c.long:
        return c.long.rstrip("\n")
    return f"{c.name}{LOOK_POSITIONS.get(c.position, '在這裡')}。"


WHITE, RESET = colorize("{W"), colorize("{x")

# 名字前面的標記（使用者要的，照 C 版 show_char_to_char 的「(菁英)」）：種類 → (文字, 顏色代碼)。一般、雜魚沒有
TIER_TAGS = {MobTier.ELITE: ("菁英", "{G"), MobTier.BOSS: ("首領", "{R")}


def tags(c):
    """c 名字前面要加的標記 [(文字, 顏色代碼)]，照順序：生物的種類（菁英亮綠、首領亮紅，使用者選的）。

    之後做 buff／debuff：重要的效果的光圈（像 C 版的 (聖光)、(火燄)）也從這裡回傳，就會出現在 look 那一行前面。
    """
    tier = TIER_TAGS.get(getattr(c, "tier", None))
    return [tier] if tier else []


def tagged(c):
    """look 裡 c 的那一行：標記各自上色、接在前面，後面的字亮白（「(菁英)一位測試商人/merchant/站在櫃檯後面。」）。"""
    return "".join(colorize(f"{code}({word})") for word, code in tags(c)) + WHITE + appearance(c) + RESET


LOOK_POSITIONS = {
    Position.STANDING: "站在這裡", Position.RESTING: "坐在這裡休息",
    Position.SLEEPING: "躺在這裡睡覺", Position.FIGHTING: "正在這裡戰鬥",
}


def move(ch, direction, leave="$n朝$t離開。"):
    """往 direction 走。leave 是原本房間的人看到的那句（flee 換成「逃竄了」）。"""
    vnum = ch.room.exits.get(direction)
    door = ch.room.doors.get(direction)
    if door is not None and door.closed:
        # 手冊定的：有名字是「【木門】關起來了。」，沒寫名字用方向「北方關起來了。」
        ch.send(f"【{door.keywords[0]}】關起來了。\n" if door.keywords else f"{DIRECTIONS[direction]}方關起來了。\n")
        return
    # 在副本、動態區域裡走會留在同一份；走進還沒建立的動態區域時，room_at 會建立它
    to = zones.room_at(ch.room, vnum) if vnum is not None else None
    if to is None:
        ch.send("那裡不能走。\n")
        return
    act(leave, ch, t=DIRECTIONS[direction], to=TO_ROOM)
    ch.room = to
    act("$n從$t邊走了過來。", ch, t=DIRECTIONS[REVERSE[direction]], to=TO_ROOM)
    ch.send(look(ch))


def walk(direction):
    """做出「往 direction 走」的指令。"""

    def do_walk(ch, arg):
        move(ch, direction)

    return do_walk


do_north = walk("north")
do_east = walk("east")
do_south = walk("south")
do_west = walk("west")
do_up = walk("up")
do_down = walk("down")


def do_chat(ch, arg):
    if not arg:
        ch.send("要說什麼？\n")
    else:
        act("{M你聊天：$t{x", ch, t=arg, to=TO_CHAR)
        for other in online_players():     # chat 是全服頻道，自己走訪在線的玩家，有房間後也不受影響
            if other is not ch:
                act("{M$n 聊天：$t{x", ch, vch=other, t=arg, to=TO_VICT)


def do_tell(ch, arg):
    target, _, msg = arg.partition(" ")
    msg = msg.strip()
    if not target or not msg:
        ch.send("你想要告訴誰些什麼呢？\n")
        return
    victim = next((p for p in online_players() if p.name.lower() == target.lower()), None)
    if victim is None:
        ch.send("沒有找到你想說話的對象。\n")
        return
    tell(ch, victim, msg)


def do_reply(ch, arg):
    victim = ch.reply
    if victim not in characters:            # 沒人 tell 過你，或對方已經離線
        ch.send("找不到你想回答的對象。\n")
        return
    if not arg:
        ch.send("你想回答些什麼呢？\n")
        return
    tell(ch, victim, arg)


def tell(ch, victim, msg):
    """tell 和 reply 共用：雙方各看到一句，對方之後可以用 reply 回你。"""
    act("{G你告訴$N：$t{x", ch, vch=victim, t=msg, to=TO_CHAR)
    act("{G$n告訴你：$t{x", ch, vch=victim, t=msg, to=TO_VICT)
    victim.reply = ch


def do_weather(ch, arg):
    if not weather.outside(ch):
        ch.send("你現在在室內是看不到天氣的。\n")
        return
    ch.send(weather.current.describe() + "\n")


def do_quit(ch, arg):
    ch.send("再見。\n")
    # 存檔、移出角色名單、關連線都在 server.handle() 的 finally（直接斷線也走那裡），這裡不重複做
    return False


SCORE_BAR = 20                              # score 的 HP／MP／MV 條有幾格
SCORE_ROWS = [                              # score 下半部：(標題, 一列裡的屬性)，一列最多三格
    ("攻擊", ("dmg_phys", "dmg_spell", "hit")),
    ("", ("crit", "critdmg", "speed")),
    ("防禦", ("dodge", "res_phys", "res_spell")),
    ("", ("res_dragon", "ac")),
]
BAR_COLORS = {"hp": "{R", "mp": "{B", "mv": "{G"}


def width(text):
    """畫面上佔幾格：Big5 中文字 2 bytes 也佔 2 格，所以就是 cp950 的 byte 數。text 不能有顏色代碼。"""
    return len(text.encode(ENCODING))


def pad(text, n):
    return text + " " * max(0, n - width(text))


def rpad(text, n):
    """靠右：數字用。"""
    return " " * max(0, n - width(text)) + text


def plain(text):
    """拿掉顏色代碼，算寬度用。"""
    return re.sub(r"\{.", "", text)


def bar(now, top, color):
    full = min(SCORE_BAR, stats.shown(now / top * SCORE_BAR)) if top > 0 else 0
    return "[" + color + "=" * full + "{D" + "-" * (SCORE_BAR - full) + "{x]"


def do_score(ch, arg):
    """看自己的全部屬性（有框、有 HP／MP／MV 條，使用者選的樣子）。公會用不到的傷害變暗。"""
    panel = getattr(ch, "panel", None)
    if not panel:                           # NPC、還沒有屬性的角色
        ch.send("你沒有屬性可以看。\n")
        return
    names = stats.STAT_NAMES
    sex = {SEX_MALE: "男", SEX_FEMALE: "女"}.get(ch.sex, "無")
    unused = stats.GUILD_DAMAGE[stats.Guild.STAFF if ch.guild == stats.Guild.SWORD else stats.Guild.SWORD]
    gear = stats.gear_primaries(ch)         # 主屬性顯示角色 ＋ 裝備的總和（設計文件 §8.2，只是參考；戰鬥、負重不用這個總和）
    # 名字只有英文字母（login.py 檢查過），不會有顏色代碼混進來
    lines = [
        " {G【{Y" + ch.name + "{G】{x {W" + stats.RACE_NAMES[ch.race] + "{D｜{C" + stats.GUILD_NAMES[ch.guild]
        + "{D｜{x等級 {Y" + str(ch.level) + exp_text(ch) + "{D｜{x" + sex + ("{D｜{Mimm{x" if ch.imm else ""),
        None,                               # 框線
        " {C主屬性{x  " + "  ".join(names[k] + " {W" + rpad(str(ch.primaries[k] + gear[k]), 2) + "{x" for k in stats.PRIMARY_KEYS)
        + (f"  {{Y可分配 {ch.points}{{x" if ch.points else ""),
        "",
    ]
    for k in ("hp", "mp", "mv"):
        now, top = getattr(ch, k), panel[k]
        lines.append(" " + pad(names[k], 4) + bar(now, top, BAR_COLORS[k])
                     + "  {W" + rpad(str(stats.shown(now)), 5) + "{x / " + str(stats.shown(top)))   # 100 級穿裝備的 HP 會到 5 位數
    lines.append("")
    for title, keys in SCORE_ROWS:
        cells = []
        for k in keys:
            name, value = pad(names[k], 8), rpad(str(stats.shown(panel[k])), 4)
            cells.append("{D" + name + value + "{x" if k == unused else name + "{W" + value + "{x")
        lines.append(" " + ("{C" + pad(title, 4) + "{x" if title else "    ") + "  " + "   ".join(cells))
    rule = "{D" + "=" * max(width(plain(line)) for line in lines if line) + "{x"
    lines[1] = rule
    ch.send(colorize("\n".join([rule, *lines, rule])) + "\n")


def exp_text(ch):
    """score 抬頭等級後面的「｜經驗 35/139」：這一級累積的經驗 / 升級需求（取整）。滿等不顯示。"""
    if ch.level >= stats.MAX_LEVEL:
        return ""
    return "{D｜{x經驗 {W" + str(stats.shown(ch.exp)) + "{x/" + str(stats.shown(stats.exp_to_level(ch.level)))


PRIMARY_WORDS = {**{k: k for k in stats.PRIMARY_KEYS}, **{stats.STAT_NAMES[k]: k for k in stats.PRIMARY_KEYS}}


def do_train(ch, arg):
    """train <屬性> [點數]：把升級得到的主屬性點數加上去（每項最高 PRIMARY_CAP）。只打 train 是看點數和用法。"""
    if not getattr(ch, "panel", None):      # NPC、還沒有屬性的角色
        ch.send("你沒有屬性可以分配。\n")
        return
    names = stats.STAT_NAMES
    if not arg:
        ch.send("  ".join(f"{names[k]} {ch.primaries[k]}" for k in stats.PRIMARY_KEYS)
                + f"\n還沒分配的點數：{ch.points}\n用法：train <屬性> [點數]，例如 train str 5\n")
        return
    if not ch.points:
        ch.send("你沒有可以分配的點數。\n")
        return
    word, _, amount = arg.partition(" ")
    key = PRIMARY_WORDS.get(word.lower())
    if key is None:
        ch.send("要加哪一項？str int wis con dex（或力量、智慧、知識、體質、敏捷）\n")
        return
    amount = amount.strip() or "1"
    if not amount.isdigit() or int(amount) < 1:
        ch.send("點數要寫 1 以上的整數。\n")
        return
    n, room = int(amount), stats.PRIMARY_CAP - ch.primaries[key]
    if n > ch.points:
        ch.send(f"你只有 {ch.points} 點。\n")
        return
    if room <= 0:
        ch.send(f"{names[key]}已經是最高的 {stats.PRIMARY_CAP} 了。\n")
        return
    if n > room:
        ch.send(f"{names[key]}最多 {stats.PRIMARY_CAP}，現在 {ch.primaries[key]}，最多再加 {room} 點。\n")
        return
    stats.train(ch, key, n)
    ch.send(f"你把 {n} 點加到{names[key]}，現在{names[key]} {ch.primaries[key]}，還剩 {ch.points} 點。\n")


# ---- 姿勢：rest、sleep、stand（訊息照 C 版 act_move.c）----

def do_rest(ch, arg):
    if ch.position == Position.FIGHTING:
        ch.send("你正處於戰鬥狀態之中了!!\n")
    elif ch.position == Position.RESTING:
        ch.send("你已經在休息了啊。\n")
    elif ch.position == Position.SLEEPING:   # C 版沒有這條路：醒過來坐著休息
        ch.position = Position.RESTING
        ch.send("你醒過來，坐著休息。\n")
        act("$n醒過來，坐著休息。", ch, to=TO_ROOM)
    else:
        ch.position = Position.RESTING
        ch.send("你坐下來休息。\n")
        act("$n坐下來休息。", ch, to=TO_ROOM)


def do_sleep(ch, arg):
    if ch.position == Position.FIGHTING:
        ch.send("你正處於戰鬥狀態之中了!!\n")
    elif ch.position == Position.SLEEPING:
        ch.send("你已經睡得很熟了。\n")
    else:
        ch.position = Position.SLEEPING
        ch.send("你一躺下就睡著了。\n")
        act("$n一躺下就睡著了。", ch, to=TO_ROOM)


def do_stand(ch, arg):
    if ch.position == Position.FIGHTING:
        ch.send("你正處於戰鬥狀態之中了!!\n")
    elif ch.position == Position.STANDING:
        ch.send("你不是已經站起來了嗎？\n")
    elif ch.position == Position.SLEEPING:
        ch.position = Position.STANDING
        ch.send("你醒過來，站了起來。\n")
        act("$n醒過來，站了起來。", ch, to=TO_ROOM)
    else:
        ch.position = Position.STANDING
        ch.send("你站了起來。\n")
        act("$n站了起來。", ch, to=TO_ROOM)


def do_say(ch, arg):
    """說話：同房間醒著的人聽得到（亮白色，照 C 版）。玩家打的字用 $t 帶進去，不會被當成顏色代碼。"""
    if not arg:
        ch.send("你想說些什麼呢？\n")
        return
    act("{W你說：『$t』{x", ch, t=arg, to=TO_CHAR)
    act("{W$n說：『$t』{x", ch, t=arg, to=TO_ROOM)


def do_who(ch, arg):
    """線上玩家：等級高的在前面。顏色跟 score 一致；名字只有英文字母（login.py 檢查過），不會混進顏色代碼。"""
    players = sorted(online_players(), key=lambda p: (-p.level, p.name))
    lines = ["{G【{Y線上玩家{G】{x"]
    for p in players:
        if p.panel:
            info = ("{Y" + rpad(str(p.level), 3) + "{x " + pad(stats.RACE_NAMES[p.race], 6)
                    + " " + pad(stats.GUILD_NAMES[p.guild], 8))
        else:                               # 沒有屬性（只有測試直接建的玩家）
            info = pad("－", 3 + 1 + 6 + 1 + 8)
        lines.append(" [" + info + "] {W" + p.name + "{x" + ("{M（imm）{x" if p.imm else ""))
    lines.append(f"共 {len(players)} 人。")
    ch.send(colorize("\n".join(lines)) + "\n")


def do_save(ch, arg):
    """手動存檔（離線時也會自動存）。什麼姿勢都能用（照 C 版）。"""
    if not getattr(ch, "panel", None):      # NPC、還沒有屬性的角色
        ch.send("你沒有可以存的資料。\n")
        return
    try:
        save.save_player(ch)
    except OSError:
        log.exception(f"{ch.name} 存檔失敗")
        ch.send("存檔失敗了，請告訴管理員。\n")
        return
    ch.send("存檔好了。\n")


def do_affects(ch, arg):
    """看自己身上的效果：每個一行，名字、還有幾秒、作用。什麼姿勢都能看。"""
    if not ch.affects:
        ch.send("你身上沒有任何效果。\n")
        return
    ch.send("你身上的效果：\n" + "\n".join(affects.describe(ch, a) for a in ch.affects) + "\n")
