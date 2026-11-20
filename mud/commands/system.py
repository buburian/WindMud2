"""系統類指令。每個指令都長 do_xxx(ch, arg)：ch 是下指令的角色，回傳 False 代表要斷線。"""
import logging
import re

from .. import affects, light, meals, objects, paths, save, scripts, socials, stats, summons, terrain, weather, zones
from ..act import TO_CHAR, TO_NOTVICT, TO_ROOM, TO_VICT, act, compose, notify
from ..area import DIRECTIONS, PASSPROOF_LOCKS, REVERSE, AffectFlag, AreaType, MobTier, RoomFlag
from ..characters import SEX_FEMALE, SEX_MALE, Position, arrive, characters, find_in_room, in_room
from ..color import colorize
from ..config import ENCODING, PAGE_LINES, PAGE_LINES_MAX, PAGE_LINES_MIN
from ..npcs import Npc
from ..players import online_players

log = logging.getLogger(__name__)


def do_look(ch, arg):
    if not arg or not light.can_see_room(ch):    # 很暗：look 什麼都只看到那一句（照 C 版，在看要看什麼之前）
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
        # 方向以後才找房間裡的角色、物品（C 版最先找）：名字只比開頭，放在方向前面的話 look d、look n 會變成看 d、n 開頭的生物
        victim = find_in_room(ch, words[0])
        if victim is not None:
            look_at(ch, victim)
            return
        ch.send(look_object(ch, words[0]) or "在這裡找不到你要看的東西。\n")
        return
    text = room.exit_descriptions.get(direction)
    ch.send(block(text) if text else "那裡沒有什麼特別的東西。\n")    # 沒寫描述，或那個方向沒有出口
    door = room.doors.get(direction)
    if door is not None:                    # 照 C 版接著說門的狀態；C 版沒寫名字就不說，我們叫它「門」
        ch.send(f"{door.name}是{'關著' if door.closed else '開著'}的。\n")


def look_object(ch, word):
    """look 物品（照 C 版 do_look）：背包、身上、地上（照這個順序）的物品；找不到是 None。
    先找物品可以細看的東西（名字要整個字一樣，跟房間的一樣），再找物品的名字（跟 get 一樣：開頭就行、2.x），看它放在地上的那一句。
    """
    objs = ch.carrying + list(ch.equipment.values()) + light.floor(ch)
    target = word.lower()
    for obj in objs:
        for keywords, text in objects.extra_descriptions(obj):
            if target in keywords:
                return block(text)
    obj = objects.find(objs, word)
    return obj.long.rstrip("\n") + "\n" if obj is not None else None


def look_in(ch, name):
    """look in 東西：看地上或背包裡的容器、屍體裡有什麼（照 C 版 act_info.c 的訊息）。"""
    if not name:
        ch.send("你想看些什麼東西？\n")
        return
    obj = objects.find(light.floor(ch) + ch.carrying, name)
    if obj is None:
        ch.send("這裡沒有你想看的東西。\n")
        return
    if not obj.is_container():
        ch.send("這不是一個容器。\n")
        return
    if obj.closed():
        ch.send("它是蓋起來的。\n")             # 照 C 版
        return
    ch.send(objects.inside(obj))


# look 角色的受傷狀態（照 C 版 show_char_to_char_1）：(HP 剩幾 % 以上, 接在名字後面的那句)；都不到是 DYING
CONDITIONS = [
    (100, "十分的健康，完整。"), (90, "有少許的瘀青。"), (80, "帶著一些瘀青。"), (70, "有一些小傷口。"),
    (60, "有幾處明顯的傷口。"), (50, "佈滿很多明顯的傷口。"), (40, "開始大量的出血，不止。"),
    (30, "身上都是鮮紅的血液。"), (20, "腸子流了出來。"), (10, "快要死了。"),
]
DYING = "瀕臨死亡。"
POSSIBLE_DROPS = "可能掉落："                  # look 生物：受傷狀態後面（設計文件 §4.10，只給名字）；太長換行，接在名字那裡對齊


def condition(c):
    """c 的受傷狀態那句（不含名字）：HP 剩幾 %（100 × HP ÷ HP 上限）照 CONDITIONS 查。"""
    top = c.panel["hp"]
    percent = 100 * c.hp / top if top > 0 else -1     # 照 C 版：上限是 0 當作 -1
    return next((text for floor, text in CONDITIONS if percent >= floor), DYING)


def look_at(ch, victim):
    """look 角色（照 C 版 show_char_to_char_1，使用者選的三樣）：對方和旁邊的人看到打量、描述、受傷狀態。

    看自己不送打量。沒寫描述（玩家都沒有）照 C 版說看不出來；生物的描述可以用顏色代碼（跟房間描述一樣，使用者定的）。
    沒有屬性的角色（測試直接建的）沒有受傷狀態那行。
    """
    if victim is not ch:
        act("$n對你仔細地上下打量了一番。", ch, victim, to=TO_VICT)
        act("$n對$N仔細地上下打量了一番。", ch, victim, to=TO_NOTVICT)
    text = getattr(victim, "description", "")
    if text:
        ch.send(block(text))
    else:
        act("你看不出來$M有任何特殊的地方。", ch, victim, to=TO_CHAR)
    if getattr(victim, "panel", None):
        act("$N" + condition(victim), ch, victim, to=TO_CHAR)
    drops = objects.possible_drops(victim) if isinstance(victim, Npc) else []
    if drops:                               # 可能掉落（設計文件 §4.10）：名字是區域作者寫的，照寫、不轉顏色代碼（跟物品名字一樣）
        indent = width(POSSIBLE_DROPS)
        lines = wrap(drops[:-1] + [drops[-1] + "。"], SCORE_WIDTH - indent)
        ch.send(POSSIBLE_DROPS + ("\n" + " " * indent).join(lines) + "\n")


def block(text):
    """區域作者寫的一段文字：轉顏色代碼，最後補上換行。"""
    text = colorize(text)
    return text if text.endswith("\n") else text + "\n"


def look(ch):
    """ch 所在房間的樣子：名稱、出口、描述，空一行再列房間裡的東西。登入時也用這個。

    順序（使用者定的）：先生物（NPC），再玩家，最後是地上的物品（新的在前）。
    生物、玩家、地上的物品都是亮白。名字不經過 colorize()：玩家名字只有英文字母，之後 NPC 用區域作者寫的描述時再看要不要轉顏色代碼。
    很暗、看不到房間：只有「這裡黑漆漆的一片」那一句（light.darkness()，照 C 版）。
    """
    if not light.can_see_room(ch):
        return light.darkness(ch)
    room = ch.room
    # 關著的門是紫色的 *北（照 C 版），其他出口亮青色
    exits = "".join((" {M*" if d in room.doors and room.doors[d].closed else " {C") + DIRECTIONS[d]
                    for d in DIRECTIONS if d in room.exits) or " 沒有"
    # 房間的文字是區域作者寫的，可以用顏色代碼；角色名字是後面才接上去的，不會被轉
    text = colorize("{G【{Y" + room.name + "{G】{x\n{G【出口：" + exits + "{G】{x\n" + room.description)
    if not text.endswith("\n"):
        text += "\n"
    # 看不到的人（隱形、藏匿）不列：跟 find_in_room() 用同一個 light.visible()，「畫面上第 n 隻」才對得上
    lines = [f"{tagged(c)}\n" for c in in_room(ch) if light.visible(ch, c)] + [f"{objects.on_floor(o)}\n" for o in room.contents]
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
# 光圈（使用者 2026-11-17 定的，順序、顏色照 C 版）：身上有這個旗標 → (文字, 顏色代碼)
AURAS = (
    (AffectFlag.INVISIBLE, "隱形", "{y"),   # C 版的 BROWN
    (AffectFlag.HIDE, "藏匿", "{y"),
    (AffectFlag.PASS_DOOR, "通透", "{g"),
    (AffectFlag.FAERIE_FIRE, "粉光", "{M"),
    (AffectFlag.SANCTUARY, "聖光", "{W"),
)


def tags(c):
    """c 名字前面要加的標記 [(文字, 顏色代碼)]，照順序：生物的種類（菁英亮綠、首領亮紅，使用者選的），再來是光圈（AURAS）。
    看不到的人（隱形、藏匿）不會列在 look 裡，所以 (隱形)、(藏匿) 只有看得到他的人（imm、有偵測的）會看到。
    """
    tier = TIER_TAGS.get(getattr(c, "tier", None))
    return ([tier] if tier else []) + [(word, code) for flag, word, code in AURAS if affects.has_flag(c, flag)]


def tagged(c):
    """look 裡 c 的那一行：標記各自上色、接在前面，後面的字亮白（「(菁英)一位測試商人/merchant/站在櫃檯後面。」）。"""
    return "".join(colorize(f"{code}({word})") for word, code in tags(c)) + WHITE + appearance(c) + RESET


LOOK_POSITIONS = {
    Position.STANDING: "站在這裡", Position.RESTING: "坐在這裡休息",
    Position.SLEEPING: "躺在這裡睡覺", Position.FIGHTING: "正在這裡戰鬥",
}


HELD = "你現在動彈不得。"                     # 暈、凍住的時候走路、逃跑、用技能


def move(ch, direction, leave=terrain.WALK_AWAY):
    """往 direction 走。leave 是原本房間的人看到的那句（flee 換成「逃竄了」；從水裡到水裡照常走路換成游泳，terrain.leave_text()）。

    地形走不過去（現在的或要去的房間要飛、要船、要會潛水）就停在原地（terrain.blocked()，只限制玩家）。
    走進去的房間：有飛行是「飛了過來」、可游泳的水是「游了過來」；很暗看不到他的人收不到（照 C 版）。
    門關著過不去；有通透（穿牆術）的穿得過，法術穿不過的門除外（照 C 版）。
    """
    if affects.controlled(ch, affects.HELD):     # 暈、凍住：不能走（設計文件 §2.6）
        ch.send(HELD + "\n")
        return
    vnum = ch.room.exits.get(direction)
    door = ch.room.doors.get(direction)
    if door is not None and door.closed:
        # 手冊定的：有名字是「【木門】關起來了。」，沒寫名字用方向「北方關起來了。」
        name = f"【{door.keywords[0]}】" if door.keywords else f"{DIRECTIONS[direction]}方"
        if not affects.has_flag(ch, AffectFlag.PASS_DOOR):
            ch.send(f"{name}關起來了。\n")
            return
        if door.locks in PASSPROOF_LOCKS:   # 通透（照 C 版）：關著、鎖著的都穿得過，法術穿不過的門不行
            ch.send(f"啊!!你沒有辦法通過{name}。\n")
            return
    # 在副本、動態區域裡走會留在同一份；走進還沒建立的動態區域時，room_at 會建立它
    to = zones.room_at(ch.room, vnum) if vnum is not None else None
    if to is None:
        ch.send("那裡不能走。\n")
        return
    refused = terrain.blocked(ch, ch.room, to)
    if refused:
        ch.send(refused + "\n")
        return
    act(terrain.leave_text(ch.room, to, leave), ch, t=DIRECTIONS[direction], to=TO_ROOM)    # 看不到的人是「某人」
    ch.room = to
    arrive(ch)
    for reader, text in compose(terrain.arrive_text(ch, to), ch, t=DIRECTIONS[REVERSE[direction]], to=TO_ROOM):
        if light.visible(reader, ch):
            notify(reader, text)
    ch.send(look(ch))
    scripts.fire(to, "on_enter", ch, ch, REVERSE[direction])   # 腳本的 on_enter(actor, from)：from 是從哪個方向進來
    if not isinstance(ch, Npc):
        summons.follow(ch, direction)       # 召喚物跟著走


def walk(direction):
    """做出「往 direction 走」的指令。"""

    def do_walk(ch, arg):
        move(ch, direction)

    return do_walk


RECALL_PRAY = "$n向天神祈求【傳送】"          # recall 的訊息照 C 版 do_recall
RECALL_REFUSED = "天神遺棄了你。"
RECALL_STUDENT = "你還沒從教學學院畢業，不能用 recall。"
RECALL_LOST = "你完全地迷失了。"
RECALL_LEAVE = "$n消失不見了。"
RECALL_ARRIVE = "$n突然在這個房間裡面出現。"


def do_recall(ch, arg):
    """recall（`/`）：回到返回點（使用者定的，zones.recall_room()：區域檔寫的 recall，沒寫是自己的返回點）。

    不能用：no_recall 的房間（照 C 版）、還沒畢業的學生（不然可以跳過學院）；打架中、休息、睡覺不能用（指令表的最低姿勢 STANDING）。
    不扣 MV（C 版扣一半，使用者選不扣）。已經在那裡就什麼都不做（照 C 版）。到了跟腳本的 transfer 一樣觸發 on_enter(actor, nil)。
    """
    act(RECALL_PRAY, ch, to=TO_ROOM)
    if RoomFlag.NO_RECALL in ch.room.room_flags:
        ch.send(RECALL_REFUSED + "\n")
        return
    if zones.is_student(ch):
        ch.send(RECALL_STUDENT + "\n")
        return
    to = zones.recall_room(ch)
    if to is None:
        ch.send(RECALL_LOST + "\n")
        return
    if to is ch.room:
        return
    act(RECALL_LEAVE, ch, to=TO_ROOM)
    ch.room = to
    arrive(ch)
    act(RECALL_ARRIVE, ch, to=TO_ROOM)
    ch.send(look(ch))
    scripts.fire(to, "on_enter", ch, ch, None)


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
        how = socials.adverb(arg)           # 結尾的表情：「愉快地聊天」（照 C 版，表在 socials.json）
        act("{M你" + how + "聊天：$t{x", ch, t=arg, to=TO_CHAR)
        for other in online_players():     # chat 是全服頻道，自己走訪在線的玩家，有房間後也不受影響
            if other is not ch:
                act("{M$n " + how + "聊天：$t{x", ch, vch=other, t=arg, to=TO_VICT)


def do_tell(ch, arg):
    target, _, msg = arg.partition(" ")
    msg = msg.strip()
    if not target or not msg:
        ch.send("你想要告訴誰些什麼呢？\n")
        return
    # 玩家下 tell：先找線上的玩家，找不到才找同房間的生物（使用者選的）。
    # 生物下 tell：先找同一間房（使用者定的：生物的名字是英文，可能跟線上的玩家同名），找不到才找線上的玩家
    victim = find_in_room(ch, target) if isinstance(ch, Npc) else None
    if victim is None:
        victim = next((p for p in online_players() if p.name.lower() == target.lower()), None)
    if victim is None:
        victim = find_in_room(ch, target)
        if not isinstance(victim, Npc):
            ch.send("沒有找到你想說話的對象。\n")
            return
    if isinstance(victim, Npc):             # tell 生物：觸發牠的 on_tell
        act("{G你" + socials.adverb(msg) + "告訴$N：$t{x", ch, vch=victim, t=msg, to=TO_CHAR)
        scripts.fire_owner(victim, "on_tell", ch, ch, msg)
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
    """tell 和 reply 共用：雙方各看到一句，對方之後可以用 reply 回你。結尾的表情：「愉快地告訴」（照 C 版）。"""
    how = socials.adverb(msg)
    act("{G你" + how + "告訴$N：$t{x", ch, vch=victim, t=msg, to=TO_CHAR)
    act("{G$n" + how + "告訴你：$t{x", ch, vch=victim, t=msg, to=TO_VICT)
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


SCORE_WIDTH = 79                            # score 的寬度：跟 C 版 do_score 的分隔線一樣（使用者要的）
SCORE_BAR = 20                              # score 的 HP／MP／MV 條有幾格
AFFECT_TEXT_WIDTH = 44                      # score 最下面效果那段「做什麼」的寬度（後面接「還有 N 秒」，整行不超過 SCORE_WIDTH）
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


def wrap(parts, n, sep="、"):
    """把 parts 用 sep 連起來，每行最多 n 格（畫面寬度），在 sep 後面換行；一段本身比 n 長就自己一行。至少回傳一行。"""
    lines, line = [], ""
    for i, part in enumerate(parts):
        piece = part + (sep if i < len(parts) - 1 else "")
        if line and width(line + piece) > n:
            lines.append(line)
            line = piece
        else:
            line += piece
    return lines + [line] if line or not lines else lines


def cell(text, n):
    """有顏色代碼的 text 補空白到畫面上 n 格（顏色代碼不佔格）。"""
    return text + " " * max(0, n - width(plain(text)))


def plain(text):
    """拿掉顏色代碼，算寬度用。"""
    return re.sub(r"\{.", "", text)


def bar(now, top, color):
    full = min(SCORE_BAR, stats.shown(now / top * SCORE_BAR)) if top > 0 else 0
    return "[" + color + "=" * full + "{D" + "-" * (SCORE_BAR - full) + "{x]"


def do_score(ch, arg):
    """看自己的全部屬性（使用者選的樣子）：寬 SCORE_WIDTH 跟 C 版一樣，每個數字的位置固定，數字變長也不會把整個畫面撐寬。

    數字留的位置：經驗 7 位數、HP／MP／MV 7 位數、屬性 8 位數；金幣放在行尾，再長也只往右。
    公會用不到的傷害變暗。身上有效果時，最下面照 C 版列出來。
    """
    panel = getattr(ch, "panel", None)
    if not panel:                           # NPC、還沒有屬性的角色
        ch.send("你沒有屬性可以看。\n")
        return
    names = stats.STAT_NAMES
    sex = {SEX_MALE: "男", SEX_FEMALE: "女"}.get(ch.sex, "無")
    unused = stats.GUILD_DAMAGE[stats.Guild.STAFF if ch.guild == stats.Guild.SWORD else stats.Guild.SWORD]
    gear = stats.extra_primaries(ch)        # 主屬性顯示角色 ＋ 裝備、效果加的總和（設計文件 §8.2，只是參考；戰鬥、負重不用這個總和）
    heavy, thin = "{D" + "=" * SCORE_WIDTH + "{x", "{D" + "-" * SCORE_WIDTH + "{x"
    # 名字只有英文字母（login.py 檢查過），不會有顏色代碼混進來
    lines = [
        heavy,
        " {G【{Y" + ch.name + "{G】{x {W" + stats.RACE_NAMES[ch.race] + "{D｜{C" + stats.GUILD_NAMES[ch.guild]
        + ("{D｜{C" + paths.title(ch) if paths.title(ch) else "")      # 稱號：走的路（使用者要的）
        + "{D｜{x" + sex + ("{D｜{Mimm{x" if ch.imm else ""),
        thin,
        " " + cell("等級 {Y" + str(ch.level) + "{x", 12) + cell(exp_text(ch), 36) + "金幣 {Y" + str(ch.gold) + "{x",
        " " + "   ".join(names[k] + " {W" + rpad(str(stats.shown(ch.primaries[k] + gear[k])), 3) + "{x" for k in stats.PRIMARY_KEYS)
        + (f"     {{Y可分配 {ch.points}{{x" if ch.points else ""),
        thin,
    ]
    for k in ("hp", "mp", "mv"):
        now, top = getattr(ch, k), panel[k]
        lines.append(" " + pad(names[k], 4) + bar(now, top, BAR_COLORS[k])
                     + "  {W" + rpad(str(stats.shown(now)), 7) + "{x / " + str(stats.shown(top)))
    lines.append(thin)
    for title, keys in SCORE_ROWS:
        cells = []
        for k in keys:
            name, value = pad(names[k], 9), rpad(str(stats.shown(panel[k])), 8)
            cells.append("{D" + name + value + "{x" if k == unused else name + "{W" + value + "{x")
        lines.append(" " + ("{C" + pad(title, 4) + "{x" if title else "    ") + "  "
                     + "".join(cell(c, 24) for c in cells[:-1]) + cells[-1])
    lines.append(heavy)
    lines += affect_lines(ch)
    ch.send(colorize("\n".join(lines)) + "\n")


def exp_text(ch):
    """score 等級那行的「經驗 35 / 139」：這一級累積的經驗 / 升級需求（取整）。滿等不顯示。"""
    if ch.level >= stats.MAX_LEVEL:
        return ""
    return "經驗 {W" + str(stats.shown(ch.exp)) + "{x / " + str(stats.shown(stats.exp_to_level(ch.level)))


def affect_lines(ch):
    """score 最下面：身上的效果，一個一行（照 C 版 do_score；沒有效果就沒有這一段）。

    【名字】靠右、做什麼（affects.parts()，太長就換行，接在下一行對齊，不超過 SCORE_WIDTH）、還有幾秒（實際還要等的：矮人的毒減得快）。
    """
    if not ch.affects:
        return []
    lines = [" {C你受到下列效果的影響：{x"]
    for a in ch.affects:
        what = wrap(affects.parts(a), AFFECT_TEXT_WIDTH)
        lines.append(" 【{W" + rpad(a.name, 12) + "{x】 " + pad(what[0], AFFECT_TEXT_WIDTH)
                     + "還有 {W" + rpad(f"{affects.seconds_left(ch, a):g}", 5) + "{x 秒")
        lines += [" " * 18 + more for more in what[1:]]          # 18 ＝ 「 【」＋ 名字 12 格 ＋「】 」
    return lines


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
    if not amount.isdecimal() or int(amount) < 1:
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
        meals.cancel(ch)                    # 站起來：吃喝的效果沒了（設計文件 §3.9）
        ch.send("你醒過來，站了起來。\n")
        act("$n醒過來，站了起來。", ch, to=TO_ROOM)
    else:
        ch.position = Position.STANDING
        meals.cancel(ch)
        ch.send("你站了起來。\n")
        act("$n站了起來。", ch, to=TO_ROOM)


def do_say(ch, arg):
    """說話：同房間醒著的人聽得到（亮白色，照 C 版）。玩家打的字用 $t 帶進去，不會被當成顏色代碼。
    結尾的表情（:) 這種）照 C 版變成「你愉快地說」（socials.adverb()，表在 socials.json，使用者要的）。
    """
    if not arg:
        ch.send("你想說些什麼呢？\n")
        return
    how = socials.adverb(arg)
    act("{W你" + how + "說：『$t』{x", ch, t=arg, to=TO_CHAR)
    act("{W$n" + how + "說：『$t』{x", ch, t=arg, to=TO_ROOM)
    if not isinstance(ch, Npc):             # 腳本的 on_say(actor, text)：只有玩家說的會觸發（使用者選的，生物之間對話用 tell）
        scripts.fire(ch.room, "on_say", ch, ch, arg)


def do_who(ch, arg):
    """線上玩家：等級高的在前面。顏色跟 score 一致；名字只有英文字母（login.py 檢查過），不會混進顏色代碼。"""
    players = sorted(online_players(), key=lambda p: (-p.level, p.name))
    titled = any(p.panel and paths.title(p) for p in players)    # 有人有稱號才多一格（大家都沒選路時畫面不變）
    lines = ["{G【{Y線上玩家{G】{x"]
    for p in players:
        if p.panel:
            info = ("{Y" + rpad(str(p.level), 3) + "{x " + pad(stats.RACE_NAMES[p.race], 6)
                    + " " + pad(stats.GUILD_NAMES[p.guild], 8) + (" " + pad(paths.title(p), 4) if titled else ""))
        else:                               # 沒有屬性（只有測試直接建的玩家）
            info = pad("－", 3 + 1 + 6 + 1 + 8 + (1 + 4 if titled else 0))
        lines.append(" [" + info + "] {W" + p.name + "{x" + ("{M（imm）{x" if p.imm else ""))
    lines.append(f"共 {len(players)} 人。")
    ch.send(colorize("\n".join(lines)) + "\n")


# ---- config：設定（玩家角色手冊「設定」，訊息照 C 版 do_config、do_pagelen）----

# 開關：(名稱, Player 的欄位, 開的說明, 關的說明)。之後加開關只要加一筆（使用者要的）
CONFIG_TOGGLES = [
    ("autoloot", "autoloot", "你將會自動搜刮屍體物品。", "你放棄自動搜刮屍體物品。"),
    ("showbuff", "showbuff", "戰鬥中你會看到效果加減資源的訊息。", "戰鬥中你不會看到效果加減資源的訊息。"),
]
CONFIG_NAME_WIDTH = 9                       # 「[+AUTOLOOT ]」名稱那格的寬度（照 C 版）


def do_config(ch, arg):
    """config：列出設定；config +名稱、-名稱：開、關；config lines 數字：分頁每頁幾行。什麼姿勢都能用（照 C 版）。"""
    if not hasattr(ch, "page_lines"):       # 生物沒有設定
        ch.send("你沒有可以設定的東西。\n")
        return
    words = arg.split()
    if not words:
        ch.send(config_list(ch))
    elif words[0].lower() == "lines":
        set_page_lines(ch, words[1:])
    elif words[0][0] not in "+-":
        ch.send("想要開啟或關閉什麼選項?\n")
    else:
        on, name = words[0][0] == "+", words[0][1:].lower()
        toggle = next((t for t in CONFIG_TOGGLES if t[0] == name), None)
        if toggle is None:
            ch.send("有這個選項嗎？\n")
            return
        setattr(ch, toggle[1], on)
        ch.send(f"{name.capitalize()} 已設定成{'開啟' if on else '關閉'}。\n")


def config_list(ch):
    """照 C 版：標題亮紫；開的亮青、名稱大寫帶 +，關的暗青、小寫帶 -；最後一行是分頁。"""
    lines = ["{M[ 關鍵字   ] 選項說明{x"]
    for name, field, on, off in CONFIG_TOGGLES:
        if getattr(ch, field):
            lines.append("{C[+" + name.upper().ljust(CONFIG_NAME_WIDTH) + "] " + on + "{x")
        else:
            lines.append("{c[-" + name.ljust(CONFIG_NAME_WIDTH) + "] " + off + "{x")
    lines.append("{C[ LINES " + str(ch.page_lines).ljust(2) + " ] 每頁 " + str(ch.page_lines)
                 + f" 行暫停一次（config lines 數字，{PAGE_LINES_MIN}～{PAGE_LINES_MAX}）。" + "{x")
    return colorize("\n".join(lines) + "\n")


def set_page_lines(ch, words):
    """config lines [數字]：不打數字是預設的 PAGE_LINES（照 C 版 pagelength）；太少不改、太多設成最多。"""
    if not words:
        n = PAGE_LINES
    elif not words[0].isdecimal():          # 坑：不能用 isdigit()，「①」這種它認得、int() 卻不認得，會丟錯讓玩家斷線
        ch.send("要打數字，例如 config lines 30。\n")
        return
    else:
        n = int(words[0])
    if n < PAGE_LINES_MIN:
        ch.send(f"一頁不允許少於【{PAGE_LINES_MIN}】行。\n")
    elif n > PAGE_LINES_MAX:
        ch.page_lines = PAGE_LINES_MAX
        ch.send(f"現在應該沒有螢幕有超過【{PAGE_LINES_MAX}】行的吧!!\n")
    else:
        ch.page_lines = n
        ch.send(f"每頁每【{n}】行暫停一次。\n")


def do_again(ch, arg):
    """「!」：重複上一個指令。command() 會先把「!」換成上一個指令，會跑到這裡只有還沒打過指令的時候。"""
    ch.send("你還沒有打過指令。\n")


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



AREA_KINDS = {AreaType.WORLD: "世界", AreaType.DYNAMIC: "動態", AreaType.INSTANCE: "副本"}   # area 指令寫的區域種類
AREA_HEAD = ("區域", "等級", "種類", "入口", "作者")
AREA_TITLE = "遊戲裡的區域（入口：從神殿大廳出發怎麼走，3s 是往南走 3 步）："
AREA_HERE, AREA_NO_ENTRANCE = "就在這裡", "-----"   # 走不到、副本的入口（enter）還沒做：使用者 2026-11-20 要的，不寫字


def do_area(ch, arg):
    """area：遊戲裡有哪些區域（使用者 2026-11-20 要的，照 C 版 areas）：名稱、適合的等級、種類（世界、動態、副本）、
    入口（從神殿大廳怎麼走，zones.routes，開機時算好；文字遊戲沒有地圖，使用者要的；沒有入口的寫 -----）、作者，照等級排。

    資料是區域檔的 header（title、levels、type、author）：世界的在 zones.world.areas，動態、副本的在 zones.templates。
    """
    found = [(a.name, a.data) for a in (zones.world.areas if zones.world else [])]
    found += [(name, data) for name, (_kind, data) in zones.templates.items()]
    rows = []
    for name, data in found:
        h = data["area"]["header"]
        low, high = h["levels"]
        route = zones.routes.get(name)
        if AreaType(h["type"]) == AreaType.INSTANCE or route is None:
            way = AREA_NO_ENTRANCE
        else:
            way = route or AREA_HERE
        rows.append(((low, high, h["title"]), (h["title"], f"{low}～{high} 級", AREA_KINDS[AreaType(h["type"])], way, h["author"])))
    table = [AREA_HEAD] + [cells for _key, cells in sorted(rows)]
    widths = [max(width(r[i]) for r in table) for i in range(len(AREA_HEAD))]
    lines = ["  " + "  ".join(pad(c, w) for c, w in zip(r, widths)).rstrip() for r in table]
    ch.send(AREA_TITLE + "\n" + "\n".join(lines) + "\n")
