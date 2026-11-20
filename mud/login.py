"""登入和建立角色：一問一答，照順序寫（玩家角色手冊「建立角色」）。

名字用英文 3～12 個字母（照 C 版），存成第一個字大寫、其他小寫。
有這個角色就問密碼；沒有就建立：密碼兩次、性別、種族、公會，選完就建好（主屬性先用種族的數字）。
同一個角色已經在線上又用對的密碼登入：踢掉舊連線，新的接手同一個角色（照 C 版）。
連上來先清掉畫面、給他看登入畫面（config.LOGIN_SCREEN，使用者要的：獨立一個檔，不用改程式就能改），再問名字。
"""
import asyncio
import logging
import re
from collections import deque
from pathlib import Path

from . import announce, paths, save, skills, stats, zones
from .characters import SEX_FEMALE, SEX_MALE, characters
from .color import colorize
from .commands.system import look
from .config import ENCODING
from .players import Player, online_players, send
from .telnet import Telnet

log = logging.getLogger(__name__)

NAME = re.compile(r"[A-Za-z]{3,12}")
RESERVED = {"all", "auto", "imm", "immortal", "self", "someone"}   # 不能當名字（照 C 版的 check_parse_name）
MIN_PASSWORD = 5                                                  # 密碼至少幾個字（照 C 版）
TAKEN = object()                                                  # create() 的回傳：名字剛剛被別人建走了
NAME_PROMPT = "請輸入你的英文名字："
SCREEN_WIDTH, SCREEN_HEIGHT = 79, 24        # 登入畫面最寬幾格、最高幾行（使用者定的；高度連最後問名字那一行）
CLEAR = "\x1b[2J\x1b[H"                     # 清掉畫面、游標回到左上角（照 C 版的登入畫面）
ANSI = re.compile(r"\x1b\[[0-9;]*m")

screen = ""                                 # 載入的登入畫面（已經換成色碼）；沒載入是空的，直接問名字


def load_screen(path):
    """讀登入畫面、檢查。有問題就 ValueError（第一個問題加總數），原本載入的不動。開機時呼叫（__main__）。"""
    global screen
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        raise ValueError(f"讀不到登入畫面 {path}") from None
    problems = check_screen(text)
    if problems:
        raise ValueError(f"{path}：{problems[0]}（共 {len(problems)} 個問題）")
    screen = colorize("\n".join(screen_lines(text)) + "\n")


def screen_lines(text):
    """畫面上的每一行：照檔案寫的，只拿掉最後一個換行（最後空一行再問名字，就在檔案最後多一個空行）。"""
    return (text[:-1] if text.endswith("\n") else text).split("\n")


def check_screen(text):
    """登入畫面的問題（空的就是沒問題）：連最後問名字那一行不超過 SCREEN_HEIGHT 行，每行不超過 SCREEN_WIDTH 格，字要轉得成 Big5。
    寬度不算顏色代碼；中文字（Big5 兩個 byte）算兩格。"""
    lines = screen_lines(text)
    problems = []
    if len(lines) + 1 > SCREEN_HEIGHT:
        problems.append(f"太高了：{len(lines)} 行，加上問名字那一行是 {len(lines) + 1} 行，最多 {SCREEN_HEIGHT} 行")
    for i, line in enumerate(lines, 1):
        shown = ANSI.sub("", colorize(line))
        try:
            width = len(shown.encode(ENCODING))
        except UnicodeEncodeError as e:
            problems.append(f"第 {i} 行有轉不成 Big5 的字 {shown[e.start]!r}")
            continue
        if width > SCREEN_WIDTH:
            problems.append(f"第 {i} 行太寬了：{width} 格，最多 {SCREEN_WIDTH} 格")
    return problems


class Connection:
    """一條連線：收到的 bytes 交給 Telnet 切成一行一行，一次給一行。"""

    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer
        self.tn = Telnet()
        self.lines = deque()

    async def readline(self):
        """下一行（去掉前後空白）；對方斷線是 None。"""
        while not self.lines:
            await self.writer.drain()               # 送出去的都寫完了才等下一批
            data = await self.reader.read(4096)
            if not data:
                return None
            self.lines.extend(self.tn.feed(data))
            if self.tn.replies:                     # 協商是控制碼，直接寫 bytes，不能經過 encode()
                self.writer.write(bytes(self.tn.replies))
                self.tn.replies.clear()
        return self.lines.popleft().strip()

    def send(self, text):
        send(self.writer, text)


async def ask(conn, prompt):
    conn.send(prompt)
    return await conn.readline()


async def ask_password(conn, prompt):
    """問密碼：打的時候客戶端不顯示字（WILL ECHO），打完恢復，再補一個換行（使用者按的 Enter 沒有顯示出來）。"""
    conn.send(prompt)
    conn.writer.write(conn.tn.echo_off())
    line = await conn.readline()
    conn.writer.write(conn.tn.echo_on())
    conn.send("\n")
    return line


async def choose(conn, prompt, options):
    """列出選項讓對方打號碼，回傳選到的那個；斷線是 None。打錯就再問。"""
    while True:
        line = await ask(conn, prompt)
        if line is None:
            return None
        if line.isdecimal() and 1 <= int(line) <= len(options):
            return options[int(line) - 1]
        conn.send("請輸入列表裡的號碼。\n")


def valid_name(name):
    return NAME.fullmatch(name) is not None and name.lower() not in RESERVED


async def login(conn):
    """從問名字到進入遊戲。回傳登入的 Player；斷線或密碼錯是 None（呼叫的人關掉連線）。"""
    if screen:                              # 登入畫面只在剛連上時給一次（名字打錯重問不再給）
        conn.send(CLEAR + screen)
    while True:
        line = await ask(conn, NAME_PROMPT)
        if line is None:
            return None
        if not line:
            continue
        if not valid_name(line):
            conn.send("名字只能用 3～12 個英文字母。\n")
            continue
        name = line.capitalize()
        data = save.load_data(name)
        if data is not None:
            return await enter(conn, name, data)
        answer = await ask(conn, f"沒有這個角色，要建立新角色 {name} 嗎？(Y/N) ")
        if answer is None:
            return None
        if answer.lower() not in ("y", "yes"):
            continue
        player = await create(conn, name)
        if player is TAKEN:
            conn.send("這個名字剛剛被別人用了，請換一個。\n")
            continue
        return player


async def enter(conn, name, data):
    """舊角色：密碼對了就進入遊戲（已經在線上就接手）。"""
    password = await ask_password(conn, "請輸入密碼：")
    if password is None:
        return None
    if not await asyncio.to_thread(save.check_password, password, data["password"]):
        conn.send("密碼錯誤。\n")
        log.info(f"{name} 密碼錯誤")
        return None
    old = next((p for p in online_players() if p.name == name), None)
    if old is not None:
        # 接手：舊連線斷掉，角色留在原地（戰鬥照舊）。舊的 handle() 看到 writer 不是自己的，就不會把角色移出遊戲
        send(old.writer, "\n有人從別的地方登入了你的角色。\n")
        old.writer.close()
        old.writer = conn.writer
        old.pages = None                    # 舊連線還沒看完的分頁不接著看（新連線沒看過前面那幾頁）
        log.info(f"{name} 從別的地方重新連上")
        conn.send("重新連上了。\n" + look(old) + "\n" + old.prompt())
        return old
    player = save.player_from(data, conn.writer)
    characters.append(player)
    log.info(f"{name} 登入，目前 {len(online_players())} 人")
    # 等級夠、還不會的公會技能補學（加 Lv5 技能之前就 5 級以上的玩家，paths.catch_up），學會的接在歡迎後面
    learned = "".join(colorize(paths.LEARNED.replace("$t", s.name)) + "\n" for s in paths.catch_up(player))
    text = announce.current()               # 系統公告（announce.py）：每次登入照當天的新區域做；前後空一行
    notice = f"\n{text}\n\n" if text else ""
    conn.send(f"歡迎回來，{name}。\n" + learned + notice + look(player) + "\n" + player.prompt())
    return player


def race_menu():
    lines = ["種族："]
    for i, race in enumerate(stats.Race, 1):
        p = stats.RACE_PRIMARIES[race]
        values = "、".join(f"{stats.STAT_NAMES[k]} {p[k]}" for k in stats.PRIMARY_KEYS)
        lines.append(f"  {i}. {stats.RACE_NAMES[race]}（{stats.RACE_TRAITS[race]}）：{values}")
    return "\n".join(lines) + "\n請選擇種族（輸入號碼）："


def guild_menu():
    lines = ["公會："]
    for i, guild in enumerate(stats.Guild, 1):
        damage = stats.STAT_NAMES[stats.GUILD_DAMAGE[guild]]
        resource = stats.STAT_NAMES[stats.GUILD_RESOURCE[guild]]
        lines.append(f"  {i}. {stats.GUILD_NAMES[guild]}：用{damage}，技能耗 {resource}")
    return "\n".join(lines) + "\n請選擇公會（輸入號碼）："


async def create(conn, name):
    """建立新角色。回傳 Player；斷線是 None；名字剛剛被別人建走了是 TAKEN。"""
    while True:
        password = await ask_password(conn, f"請設定密碼（至少 {MIN_PASSWORD} 個字）：")
        if password is None:
            return None
        if len(password) < MIN_PASSWORD:
            conn.send(f"密碼至少要 {MIN_PASSWORD} 個字。\n")
            continue
        again = await ask_password(conn, "請再輸入一次密碼：")
        if again is None:
            return None
        if again == password:
            break
        conn.send("兩次密碼不一樣。\n")
    sex = await choose(conn, "性別：1 男、2 女：", [SEX_MALE, SEX_FEMALE])
    if sex is None:
        return None
    race = await choose(conn, race_menu(), list(stats.Race))
    if race is None:
        return None
    guild = await choose(conn, guild_menu(), list(stats.Guild))
    if guild is None:
        return None
    hashed = await asyncio.to_thread(save.hash_password, password)
    if save.exists(name):                   # 兩條連線同時建立同一個名字：後面那個不能蓋掉前面的
        return TAKEN
    player = Player(name, conn.writer, zones.start_room(), sex)
    player.password, player.race, player.guild = hashed, race, guild
    player.primaries = dict(stats.RACE_PRIMARIES[race])     # 公會怎麼套在種族上還沒決定，先用種族的數字
    player.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    player.resource_roll = stats.roll_resources()
    player.skills = skills.starter(guild)   # 建立角色就會的技能（存進存檔，之後新增的不會自動補）
    zones.enroll(player)                    # 有教學學院就記成學生，站在自己那一份學院的第一間（使用者要的）
    player.room = zones.home(player)
    stats.recompute(player)
    player.hp, player.mp, player.mv = player.panel["hp"], player.panel["mp"], player.panel["mv"]
    save.save_player(player)
    characters.append(player)
    log.info(f"建立新角色 {name}（{stats.RACE_NAMES[race]}、{stats.GUILD_NAMES[guild]}），目前 {len(online_players())} 人")
    conn.send("角色建立好了。\n" + look(player) + "\n" + player.prompt())
    return player
