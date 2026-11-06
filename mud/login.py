"""登入和建立角色：一問一答，照順序寫（玩家角色手冊「建立角色」）。

名字用英文 3～12 個字母（照 C 版），存成第一個字大寫、其他小寫。
有這個角色就問密碼；沒有就建立：密碼兩次、性別、種族、公會，選完就建好（主屬性先用種族的數字）。
同一個角色已經在線上又用對的密碼登入：踢掉舊連線，新的接手同一個角色（照 C 版）。
"""
import asyncio
import logging
import re
from collections import deque

from . import save, skills, stats, zones
from .characters import SEX_FEMALE, SEX_MALE, characters
from .commands.system import look
from .players import Player, online_players, send
from .telnet import Telnet

log = logging.getLogger(__name__)

NAME = re.compile(r"[A-Za-z]{3,12}")
RESERVED = {"all", "auto", "imm", "immortal", "self", "someone"}   # 不能當名字（照 C 版的 check_parse_name）
MIN_PASSWORD = 5                                                  # 密碼至少幾個字（照 C 版）
TAKEN = object()                                                  # create() 的回傳：名字剛剛被別人建走了


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
        if line.isdigit() and 1 <= int(line) <= len(options):
            return options[int(line) - 1]
        conn.send("請輸入列表裡的號碼。\n")


def valid_name(name):
    return NAME.fullmatch(name) is not None and name.lower() not in RESERVED


async def login(conn):
    """從問名字到進入遊戲。回傳登入的 Player；斷線或密碼錯是 None（呼叫的人關掉連線）。"""
    while True:
        line = await ask(conn, "請輸入你的英文名字：")
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
        log.info(f"{name} 從別的地方重新連上")
        conn.send("重新連上了。\n" + look(old) + "\n" + old.prompt())
        return old
    player = save.player_from(data, conn.writer)
    characters.append(player)
    log.info(f"{name} 登入，目前 {len(online_players())} 人")
    conn.send(f"歡迎回來，{name}。\n" + look(player) + "\n" + player.prompt())
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
