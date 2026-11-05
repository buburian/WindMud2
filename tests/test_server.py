import asyncio
from pathlib import Path

from mud import fight, save, weather, zones
from mud.characters import SEX_NEUTRAL, characters
from mud.config import ENCODING
from mud.fight import start_fight
from mud.npcs import Npc
from mud.players import online_players
from mud.server import handle
from mud.telnet import BINARY, DO, DONT, ECHO, IAC, WILL, WONT
from player_helpers import PASSWORD, make_player_file

AREAS = Path(__file__).resolve().parent.parent / "areas"

# 登入後站在房間 101，看到的樣子（不含其他玩家）
ROOM1 = (
    "\x1b[32;1m【\x1b[33;1m測試房間（南）\x1b[32;1m】\x1b[0m\r\n"
    "\x1b[32;1m【出口： \x1b[36;1m北\x1b[32;1m】\x1b[0m\r\n"
    "這是測試區域南邊的房間。\r\n往北可以走到另一個房間。\r\n"
)
# 房間描述後空一行，先列生物：areas/test.json 的 M 把測試商人放在 101，站著就顯示 long（亮白）
MERCHANT = "\r\n\x1b[37;1m一位測試商人/merchant/站在櫃檯後面。\x1b[0m\r\n"


async def expect(reader, text):
    # 剛好收到這些 bytes；斷線會丟 IncompleteReadError
    want = text if isinstance(text, bytes) else text.encode(ENCODING)
    assert await reader.readexactly(len(want)) == want


async def log_in(reader, writer, name, prompt, others=""):
    """一連上：DO BINARY、問名字；用 PASSWORD 登入存好的角色（打密碼時關掉回顯），看到歡迎和房間。"""
    await expect(reader, bytes([IAC, DO, BINARY]) + "請輸入你的英文名字：".encode(ENCODING))
    writer.write(f"{name}\r\n".encode(ENCODING))
    await expect(reader, "請輸入密碼：".encode(ENCODING) + bytes([IAC, WILL, ECHO]))
    writer.write(f"{PASSWORD}\r\n".encode(ENCODING))
    await expect(reader, bytes([IAC, WONT, ECHO]) + f"\r\n歡迎回來，{name}。\r\n{ROOM1}{MERCHANT}{others}\r\n{prompt}".encode(ENCODING))


async def quit(reader, writer):
    writer.write(b"quit\r\n")
    await expect(reader, "再見。\r\n")
    assert await reader.read() == b""           # 伺服器關掉連線


async def login_chat_quit():
    zones.load(AREAS)
    p = make_player_file("Ming").prompt()   # 兩個都是 1 級人類劍之公會、HP／MP／MV 全滿：prompt 一樣
    make_player_file("Hua")
    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        r1, w1 = await asyncio.open_connection("127.0.0.1", port)
        r2, w2 = await asyncio.open_connection("127.0.0.1", port)
        try:
            # 一連上先請對方用 8-bit 傳（DO BINARY），再問名字
            await expect(r1, bytes([IAC, DO, BINARY]) + "請輸入你的英文名字：".encode(ENCODING))
            # 客戶端一連上就問 WILL ECHO：先回 DONT ECHO（不要客戶端幫我們回顯），再問密碼
            w1.write(bytes([IAC, WILL, ECHO]) + "Ming\r\n".encode(ENCODING))
            await expect(r1, bytes([IAC, DONT, ECHO]) + "請輸入密碼：".encode(ENCODING) + bytes([IAC, WILL, ECHO]))
            # 客戶端答應 DO ECHO：是答應我們關掉回顯，不能再回 WONT
            w1.write(bytes([IAC, DO, ECHO]) + f"{PASSWORD}\r\n".encode(ENCODING))
            await expect(r1, bytes([IAC, WONT, ECHO]) + f"\r\n歡迎回來，Ming。\r\n{ROOM1}{MERCHANT}\r\n{p}".encode(ENCODING))
            await log_in(r2, w2, "Hua", p, "\x1b[37;1mMing站在這裡。\x1b[0m\r\n")

            w1.write("chat 你好\r\n".encode(ENCODING))
            # chat 是亮紫色（C 版的 MAGENTA），說完回到原本顏色
            await expect(r1, "\x1b[35;1m你聊天：你好\x1b[0m\r\n\r\n" + p)
            await expect(r2, "\r\n\x1b[35;1mMing 聊天：你好\x1b[0m\r\n\r\n" + p)

            # Ming tell Hua（名字不分大小寫）之後離線：Hua 身上指著 Ming 的 reply 要被清掉
            w1.write("tell hua 掰\r\n".encode(ENCODING))
            await expect(r1, "\x1b[32;1m你告訴Hua：掰\x1b[0m\r\n\r\n" + p)
            await expect(r2, "\r\n\x1b[32;1mMing告訴你：掰\x1b[0m\r\n\r\n" + p)
            await quit(r1, w1)
            assert [p.reply for p in online_players()] == [None]
            await quit(r2, w2)
        finally:
            # 坑：Python 3.12 起，離開 async with server 會等所有連線都斷掉。
            # 測試中途失敗時連線還開著，不先關掉就會永遠卡住，連 wait_for 的 timeout 都救不了。
            w1.close()
            w2.close()
    assert online_players() == []          # 測試商人（生物）還在


def test_login_chat_quit(monkeypatch, tmp_path):
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path)
    asyncio.run(asyncio.wait_for(login_chat_quit(), timeout=5))


async def look_while_loops_run(hits):
    zones.load(AREAS)
    p = make_player_file("Ming").prompt()
    zones.start()
    # 隔壁 102 號房有三場戰鬥一直在打（NPC 互打），世界 tick 也一直在跑
    npcs = [Npc(name, SEX_NEUTRAL, zones.world.rooms[102]) for name in "甲乙丙丁戊己"]
    characters.extend(npcs)
    for a, b in zip(npcs[::2], npcs[1::2]):
        start_fight(a, b)
    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        r, w = await asyncio.open_connection("127.0.0.1", port)
        try:
            await log_in(r, w, "Ming", p)
            before = len(hits)
            for _ in range(5):
                await asyncio.sleep(0.02)
                w.write(b"look\r\n")
                await asyncio.wait_for(expect(r, f"{ROOM1}{MERCHANT}\r\n{p}"), timeout=0.5)   # 照樣馬上回應
            assert len(hits) > before                                                 # 這段時間戰鬥一直在打
            await quit(r, w)
        finally:
            w.close()                       # 坑：同上，不先關掉，測試失敗時會永遠卡住
    characters.clear()
    zones.stop()


def test_loops_do_not_block_players(monkeypatch, tmp_path):
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path)
    monkeypatch.setattr(zones, "TICK_SECONDS", 0.01)
    monkeypatch.setattr(zones, "HOUR_TICKS", 1)              # 天氣每個 tick 都走
    monkeypatch.setattr(fight, "TICK_SECONDS", 0.01)
    hits = []
    monkeypatch.setattr(fight, "hit", lambda ch, victim, hand: hits.append(ch.name))
    ticks = []
    monkeypatch.setattr(weather, "tick", lambda: ticks.append(1))   # 天氣訊息會插進 look 的回應，這裡只記次數
    asyncio.run(asyncio.wait_for(look_while_loops_run(hits), timeout=5))
    assert ticks                                                     # 世界 tick 也一直在跑
