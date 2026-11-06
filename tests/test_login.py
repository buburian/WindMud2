import asyncio
import json
import re
from pathlib import Path

import pytest

from mud import pager, save, stats, zones
from mud.characters import characters
from mud.config import ACADEMY_START, ENCODING
from mud.players import online_players
from mud.server import handle
from mud.stats import Race
from mud.telnet import ECHO, IAC, WILL, WONT
from player_helpers import PASSWORD, make_player_file

AREAS = Path(__file__).resolve().parent.parent / "areas"
SOUTH, NORTH = "測試房間（南）", "測試房間（北）"      # 房間 101、102 的名字


@pytest.fixture
def folder(monkeypatch, tmp_path):
    # 存檔放 tmp_path
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path)
    zones.load(AREAS)
    yield tmp_path
    characters.clear()
    zones.stop()


class Client:
    def __init__(self, reader, writer):
        self.r, self.w = reader, writer
        self.buf = b""

    async def until(self, text):
        """一直讀到收到 text（文字或 bytes），回傳到 text 為止收到的 bytes。"""
        want = text.encode(ENCODING) if isinstance(text, str) else text
        while want not in self.buf:
            data = await self.r.read(4096)
            assert data, f"斷線了，還沒收到 {text!r}；收到 {self.buf.decode(ENCODING, 'replace')!r}"
            self.buf += data
        end = self.buf.index(want) + len(want)
        got, self.buf = self.buf[:end], self.buf[end:]
        return got

    def say(self, line):
        self.w.write(f"{line}\r\n".encode(ENCODING))

    async def closed(self):
        """等到伺服器關掉連線。"""
        while await self.r.read(4096):
            pass


def run(main):
    """開真的伺服器（port 0），main(connect) 用 connect() 連上去。連線一定在 finally 關掉（不然測試失敗會卡住）。"""
    async def go():
        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        clients = []

        async def connect():
            c = Client(*await asyncio.open_connection("127.0.0.1", port))
            clients.append(c)
            return c

        async with server:
            try:
                await main(connect)
            finally:
                for c in clients:
                    c.w.close()

    asyncio.run(asyncio.wait_for(go(), timeout=10))


async def until(cond, timeout=2):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not cond():
        assert loop.time() < end, "等太久"
        await asyncio.sleep(0.005)


async def log_in(connect, name):
    c = await connect()
    await c.until("請輸入你的英文名字：")
    c.say(name)
    await c.until("請輸入密碼：")
    c.say(PASSWORD)
    await c.until("> ")
    return c


async def create_until_guild(c, name):
    """建立新角色走到選公會：密碼 secret1、女、精靈。"""
    await c.until("請輸入你的英文名字：")
    c.say(name)
    await c.until(f"沒有這個角色，要建立新角色 {name.capitalize()} 嗎？(Y/N) ")
    c.say("y")
    await c.until("請設定密碼（至少 5 個字）：".encode(ENCODING) + bytes([IAC, WILL, ECHO]))   # 打密碼時客戶端不顯示字
    c.say("abc")
    await c.until("密碼至少要 5 個字。\r\n請設定密碼（至少 5 個字）：")
    c.say("secret1")
    await c.until("請再輸入一次密碼：")
    c.say("secret2")
    await c.until("兩次密碼不一樣。\r\n請設定密碼（至少 5 個字）：")
    c.say("secret1")
    await c.until("請再輸入一次密碼：")
    c.say("secret1")
    await c.until(bytes([IAC, WONT, ECHO]) + "\r\n性別：1 男、2 女：".encode(ENCODING))      # 打完恢復顯示，補換行
    c.say("3")
    await c.until("請輸入列表裡的號碼。\r\n性別：1 男、2 女：")
    c.say("①")                              # 特殊的數字字元：不會斷線，照樣再問
    await c.until("請輸入列表裡的號碼。\r\n性別：1 男、2 女：")
    c.say("2")
    menu = await c.until("請選擇種族（輸入號碼）：")
    assert "2. 精靈（聰明、靈巧、體弱）：力量 10、智慧 14、知識 12、體質 11、敏捷 13".encode(ENCODING) in menu
    c.say("2")
    menu = await c.until("請選擇公會（輸入號碼）：")
    assert "2. 杖之公會：用法術傷害，技能耗 MP".encode(ENCODING) in menu


def test_create_character_and_save(folder):
    async def main(connect):
        c = await connect()
        await create_until_guild(c, "vCX")
        c.say("2")
        got = await c.until("> ")
        assert "角色建立好了。".encode(ENCODING) in got and "學院大門".encode(ENCODING) in got      # 新角色先進教學學院
        c.say("sc")
        text = re.sub(r"\x1b\[[0-9;]*m", "", (await c.until("> ")).decode(ENCODING))     # 拿掉顏色
        assert " 【Vcx】 精靈｜杖之公會｜女\r\n" in text and " 等級 1      經驗 0 / 100" in text
        assert " 力量  10   智慧  14   知識  12   體質  11   敏捷  13\r\n" in text
        c.say("quit")
        await c.until("再見。")
        await c.closed()
        await until(lambda: online_players() == [])

    run(main)
    data = json.loads((folder / "vcx.json").read_text(encoding="utf-8"))
    assert (data["name"], data["sex"], data["race"], data["guild"], data["level"]) == ("Vcx", 2, "elf", "spell", 1)
    assert data["primaries"] == stats.RACE_PRIMARIES[Race.ELF]
    assert data["password"].startswith("scrypt$") and "secret1" not in data["password"]   # 不存明碼
    assert save.check_password("secret1", data["password"])
    assert set(data["panel"]) == {*stats.SECONDARY_KEYS, "mp", "mv", "ac"}             # 存檔也有全部次要屬性
    assert data["hp"] == data["panel"]["hp"] and data["mp"] == data["panel"]["mp"] > 0   # 建好時補滿
    assert 0.95 <= data["resource_roll"] <= 1.05 and data["room"] == ACADEMY_START
    assert data["vars"] == {"academy": {"student": True}}                              # 還沒畢業的記號
    assert data["exp"] == 0.0
    assert data["skills"] == ["fireball"]                                               # 杖之公會一開始就會的技能存進存檔


def test_bad_names_ask_again(folder):
    async def main(connect):
        c = await connect()
        await c.until("請輸入你的英文名字：")
        for bad in ("ab", "abc1", "小明", "self", "abcdefghijklm"):
            c.say(bad)
            await c.until("名字只能用 3～12 個英文字母。\r\n請輸入你的英文名字：")
        c.say("")
        await c.until("請輸入你的英文名字：")
        c.say("Vcx")
        await c.until("(Y/N) ")
        c.say("n")                          # 不建立：回去問名字
        await c.until("請輸入你的英文名字：")

    run(main)
    assert list(folder.iterdir()) == []


def test_old_character_logs_in_where_it_left(folder):
    make_player_file("Ming", room=102)

    async def main(connect):
        c = await connect()
        await c.until("請輸入你的英文名字：")
        c.say("ming")                       # 大小寫不拘
        await c.until("請輸入密碼：")
        c.say(PASSWORD)
        got = await c.until("> ")
        assert "歡迎回來，Ming。".encode(ENCODING) in got and NORTH.encode(ENCODING) in got

    run(main)


def test_wrong_password_disconnects(folder):
    make_player_file("Ming")

    async def main(connect):
        c = await connect()
        await c.until("請輸入你的英文名字：")
        c.say("Ming")
        await c.until("請輸入密碼：")
        c.say("wrong")
        await c.until("密碼錯誤。\r\n")
        await c.closed()
        assert online_players() == []

    run(main)


def test_dropping_the_line_also_saves(folder):
    make_player_file("Ming")

    async def main(connect):
        c = await log_in(connect, "Ming")
        c.say("n")                          # 走到 102 號房，然後直接斷線（沒打 quit）
        await c.until("> ")
        c.w.close()
        await until(lambda: online_players() == [])

    run(main)
    assert json.loads((folder / "ming.json").read_text(encoding="utf-8"))["room"] == 102


def test_second_login_takes_over(folder):
    make_player_file("Ming")

    async def main(connect):
        a = await log_in(connect, "Ming")
        a.say("n")
        await a.until("> ")
        online_players()[0].pages = pager.Pages(["舊連線還沒看完的"] * 30, 20)   # 舊連線在分頁中：新連線不接著分頁
        b = await connect()
        await b.until("請輸入你的英文名字：")
        b.say("Ming")
        await b.until("請輸入密碼：")
        b.say(PASSWORD)
        await a.until("有人從別的地方登入了你的角色。")
        await a.closed()
        got = await b.until("> ")
        assert "重新連上了。".encode(ENCODING) in got and NORTH.encode(ENCODING) in got    # 站在原本的地方
        assert online_players()[0].pages is None and pager.PROMPT.encode(ENCODING) not in got
        for _ in range(2):                  # 舊連線的 handle() 收尾以後，角色還在遊戲裡、只有一個
            b.say("look")
            await b.until("> ")
        assert [p.name for p in online_players()] == ["Ming"]
        b.say("quit")
        await b.until("再見。")
        await b.closed()
        await until(lambda: online_players() == [])

    run(main)


def test_name_taken_while_creating(folder):
    async def main(connect):
        c = await connect()
        await create_until_guild(c, "Vcx")
        make_player_file("Vcx")             # 另一條連線剛好先建好了同一個名字
        c.say("1")
        await c.until("這個名字剛剛被別人用了，請換一個。\r\n請輸入你的英文名字：")

    run(main)
    data = json.loads((folder / "vcx.json").read_text(encoding="utf-8"))
    assert save.check_password(PASSWORD, data["password"])     # 先建好的沒有被蓋掉
