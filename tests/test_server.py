import asyncio

from mud.config import ENCODING
from mud.players import players
from mud.server import handle
from mud.telnet import DONT, IAC, WILL


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
            await expect(r1, "Login: ")
            await expect(r2, "Login: ")

            # 客戶端一連上就問 WILL ECHO：先回 DONT ECHO，再歡迎
            w1.write(bytes([IAC, WILL, 1]) + "小明\r\n".encode(ENCODING))
            await expect(r1, bytes([IAC, DONT, 1]) + "歡迎，小明。\r\nHP100> ".encode(ENCODING))
            w2.write("阿華\r\n".encode(ENCODING))
            await expect(r2, "歡迎，阿華。\r\nHP100> ")

            w1.write("chat 你好\r\n".encode(ENCODING))
            await expect(r1, "你聊天：你好\r\nHP100> ")
            await expect(r2, "\r\n小明 聊天：你好\r\nHP100> ")

            await quit(r1, w1)
            await quit(r2, w2)
        finally:
            # 坑：Python 3.12 起，離開 async with server 會等所有連線都斷掉。
            # 測試中途失敗時連線還開著，不先關掉就會永遠卡住，連 wait_for 的 timeout 都救不了。
            w1.close()
            w2.close()
    assert players == {}


def test_login_chat_quit():
    asyncio.run(asyncio.wait_for(login_chat_quit(), timeout=5))
