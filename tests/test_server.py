import asyncio

from mud.config import ENCODING
from mud.players import players
from mud.server import handle
from mud.telnet import BINARY, DO, DONT, IAC, WILL


async def expect(reader, text):
    # 剛好收到這些 bytes；斷線會丟 IncompleteReadError
    want = text if isinstance(text, bytes) else text.encode(ENCODING)
    assert await reader.readexactly(len(want)) == want


async def quit(reader, writer):
    writer.write(b"quit\r\n")
    await expect(reader, "再見。\r\n")
    assert await reader.read() == b""           # 伺服器關掉連線


async def login_chat_quit():
    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        r1, w1 = await asyncio.open_connection("127.0.0.1", port)
        r2, w2 = await asyncio.open_connection("127.0.0.1", port)
        try:
            # 一連上先請對方用 8-bit 傳（DO BINARY），再問名字
            await expect(r1, bytes([IAC, DO, BINARY]) + "Login: ".encode(ENCODING))
            await expect(r2, bytes([IAC, DO, BINARY]) + "Login: ".encode(ENCODING))

            # 客戶端一連上就問 WILL ECHO：先回 DONT ECHO，再歡迎
            w1.write(bytes([IAC, WILL, 1]) + "小明\r\n".encode(ENCODING))
            await expect(r1, bytes([IAC, DONT, 1]) + "歡迎，小明。\r\nHP100> ".encode(ENCODING))
            w2.write("阿華\r\n".encode(ENCODING))
            await expect(r2, "歡迎，阿華。\r\nHP100> ")

            w1.write("chat 你好\r\n".encode(ENCODING))
            # chat 是亮紫色（C 版的 MAGENTA），說完回到原本顏色
            await expect(r1, "\x1b[35;1m你聊天：你好\x1b[0m\r\nHP100> ")
            await expect(r2, "\r\n\x1b[35;1m小明 聊天：你好\x1b[0m\r\nHP100> ")

            # 小明 tell 阿華之後離線：阿華身上指著小明的 reply 要被清掉
            w1.write("tell 阿華 掰\r\n".encode(ENCODING))
            await expect(r1, "\x1b[32;1m你告訴阿華：掰\x1b[0m\r\nHP100> ")
            await expect(r2, "\r\n\x1b[32;1m小明告訴你：掰\x1b[0m\r\nHP100> ")
            await quit(r1, w1)
            assert [p.reply for p in players.values()] == [None]
            await quit(r2, w2)
        finally:
            # 坑：Python 3.12 起，離開 async with server 會等所有連線都斷掉。
            # 測試中途失敗時連線還開著，不先關掉就會永遠卡住，連 wait_for 的 timeout 都救不了。
            w1.close()
            w2.close()
    assert players == {}


def test_login_chat_quit():
    asyncio.run(asyncio.wait_for(login_chat_quit(), timeout=5))
