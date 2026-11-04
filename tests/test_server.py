import asyncio
from pathlib import Path

from mud import fight, weather, zones
from mud.characters import SEX_NEUTRAL, characters
from mud.config import ENCODING
from mud.fight import start_fight
from mud.npcs import Npc
from mud.players import online_players
from mud.server import handle
from mud.telnet import BINARY, DO, DONT, IAC, WILL

AREAS = Path(__file__).resolve().parent.parent / "areas"

# 登入後站在房間 101，看到的樣子（不含其他玩家）
ROOM1 = (
    "\x1b[32;1m【\x1b[33;1m測試房間（南）\x1b[32;1m】\x1b[0m\r\n"
    "\x1b[32;1m【出口： \x1b[36;1m北\x1b[32;1m】\x1b[0m\r\n"
    "這是測試區域南邊的房間。\r\n往北可以走到另一個房間。\r\n"
)


async def expect(reader, text):
    # 剛好收到這些 bytes；斷線會丟 IncompleteReadError
    want = text if isinstance(text, bytes) else text.encode(ENCODING)
    assert await reader.readexactly(len(want)) == want


async def quit(reader, writer):
    writer.write(b"quit\r\n")
    await expect(reader, "再見。\r\n")
    assert await reader.read() == b""           # 伺服器關掉連線


async def login_chat_quit():
    zones.load(AREAS)
    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        r1, w1 = await asyncio.open_connection("127.0.0.1", port)
        r2, w2 = await asyncio.open_connection("127.0.0.1", port)
        try:
            # 一連上先請對方用 8-bit 傳（DO BINARY），再問名字
            await expect(r1, bytes([IAC, DO, BINARY]) + "Login: ".encode(ENCODING))
            await expect(r2, bytes([IAC, DO, BINARY]) + "Login: ".encode(ENCODING))

            # 客戶端一連上就問 WILL ECHO：先回 DONT ECHO，再歡迎、再看到所在的房間
            w1.write(bytes([IAC, WILL, 1]) + "小明\r\n".encode(ENCODING))
            await expect(r1, bytes([IAC, DONT, 1]) + f"歡迎，小明。\r\n{ROOM1}HP100> ".encode(ENCODING))
            w2.write("阿華\r\n".encode(ENCODING))
            await expect(r2, f"歡迎，阿華。\r\n{ROOM1}小明站在這裡。\r\nHP100> ")

            w1.write("chat 你好\r\n".encode(ENCODING))
            # chat 是亮紫色（C 版的 MAGENTA），說完回到原本顏色
            await expect(r1, "\x1b[35;1m你聊天：你好\x1b[0m\r\nHP100> ")
            await expect(r2, "\r\n\x1b[35;1m小明 聊天：你好\x1b[0m\r\nHP100> ")

            # 小明 tell 阿華之後離線：阿華身上指著小明的 reply 要被清掉
            w1.write("tell 阿華 掰\r\n".encode(ENCODING))
            await expect(r1, "\x1b[32;1m你告訴阿華：掰\x1b[0m\r\nHP100> ")
            await expect(r2, "\r\n\x1b[32;1m小明告訴你：掰\x1b[0m\r\nHP100> ")
            await quit(r1, w1)
            assert [p.reply for p in online_players()] == [None]
            await quit(r2, w2)
        finally:
            # 坑：Python 3.12 起，離開 async with server 會等所有連線都斷掉。
            # 測試中途失敗時連線還開著，不先關掉就會永遠卡住，連 wait_for 的 timeout 都救不了。
            w1.close()
            w2.close()
    assert characters == []


def test_login_chat_quit():
    asyncio.run(asyncio.wait_for(login_chat_quit(), timeout=5))


async def look_while_loops_run(hits):
    zones.load(AREAS)
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
            await expect(r, bytes([IAC, DO, BINARY]) + "Login: ".encode(ENCODING))
            w.write("小明\r\n".encode(ENCODING))
            await expect(r, f"歡迎，小明。\r\n{ROOM1}HP100> ")
            before = len(hits)
            for _ in range(5):
                await asyncio.sleep(0.02)
                w.write(b"look\r\n")
                await asyncio.wait_for(expect(r, f"{ROOM1}HP100> "), timeout=0.5)   # 照樣馬上回應
            assert len(hits) > before                                                 # 這段時間戰鬥一直在打
            await quit(r, w)
        finally:
            w.close()                       # 坑：同上，不先關掉，測試失敗時會永遠卡住
    characters.clear()
    zones.stop()


def test_loops_do_not_block_players(monkeypatch):
    monkeypatch.setattr(zones, "TICK_SECONDS", 0.01)
    monkeypatch.setattr(zones, "HOUR_TICKS", 1)              # 天氣每個 tick 都走
    monkeypatch.setattr(fight, "TICK_SECONDS", 0.01)
    hits = []
    monkeypatch.setattr(fight, "hit", lambda ch, victim, hand: hits.append(ch.name))
    ticks = []
    monkeypatch.setattr(weather, "tick", lambda: ticks.append(1))   # 天氣訊息會插進 look 的回應，這裡只記次數
    asyncio.run(asyncio.wait_for(look_while_loops_run(hits), timeout=5))
    assert ticks                                                     # 世界 tick 也一直在跑
