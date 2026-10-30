# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""最小的 MUD telnet 原型：Big5、Login:、HP100> prompt、chat 廣播。

用法：uv run server.py [--port 4000] [--host 0.0.0.0]
指令：chat <話>、quit

原則：收進來的一律當 bytes 處理，收滿一行才 decode。
「坑」標記的地方，就是 Python 寫 telnet 常出錯的點。
"""
import argparse
import asyncio

ENCODING = "cp950"   # Big5（微軟版，字比標準 Big5 多）
MAX_LINE = 1000      # 一行最多幾個 byte，跟 Diku 的 MAX_INPUT_LENGTH 一樣
PROMPT = "HP100> "

# telnet 控制碼
IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240


class Telnet:
    """把收到的 bytes 切成一行一行的字串。狀態跨封包保留。"""

    def __init__(self):
        self.state = "data"         # data / iac / opt / sb / sb_iac
        self.verb = 0
        self.line = bytearray()
        self.last_cr = False
        self.replies = bytearray()  # 要回給客戶端的協商
        self.refused = set()

    def feed(self, data):
        # 坑：一次 read 可能只收到半行，也可能收到好幾行；IAC 序列也可能被切成兩半。
        # 所以一個 byte 一個 byte 跑狀態機，狀態留到下一次 read。
        lines = []
        for b in data:
            st = self.state
            if st == "data":
                if b == IAC:
                    self.state = "iac"
                else:
                    self._byte(b, lines)
            elif st == "iac":
                if b == IAC:                        # 坑：IAC IAC 代表一個真正的 0xFF
                    self.state = "data"
                    self._byte(b, lines)
                elif b in (WILL, WONT, DO, DONT):
                    self.verb = b
                    self.state = "opt"
                elif b == SB:
                    self.state = "sb"
                else:                               # NOP、GA 這類兩 byte 指令，丟掉
                    self.state = "data"
            elif st == "opt":
                self._refuse(self.verb, b)
                self.state = "data"
            elif st == "sb":                        # 子協商（IAC SB … IAC SE）整段丟掉
                if b == IAC:
                    self.state = "sb_iac"
            elif st == "sb_iac":
                self.state = "data" if b == SE else "sb"
        return lines

    def _byte(self, b, lines):
        if self.last_cr:
            self.last_cr = False
            if b in (0x0A, 0x00):                   # 坑：\r\n、\r\0 都只算一次換行
                return
        if b in (0x0D, 0x0A):                       # 坑：各家客戶端換行不同，\r、\n、\r\n 都要認
            self.last_cr = b == 0x0D
            # 坑：收滿一行才 decode。中文字被切在兩個封包也沒事。
            # Big5 的第二碼不會是 \r \n \0，所以用 byte 切行是安全的。
            lines.append(self.line.decode(ENCODING, errors="replace"))
            self.line.clear()
        elif b in (0x08, 0x7F):                     # 退格
            self._backspace()
        elif b < 0x20:                              # 其他控制字元丟掉
            pass
        elif len(self.line) < MAX_LINE:             # 坑：一行太長就丟掉多的，記憶體才不會一直長
            self.line.append(b)

    def _backspace(self):
        # 坑：Big5 一個中文字兩個 byte，退格要整個字退掉，不能只退一半
        i = last = 0
        while i < len(self.line):
            last = i
            i += 2 if self.line[i] >= 0x81 else 1
        del self.line[last:]

    def _refuse(self, verb, opt):
        # 坑：有些客戶端一連上就問「要不要開某功能」，不回它會一直等。
        # 我們什麼都不開：對方 WILL 回 DONT，對方 DO 回 WONT，同一件事只回一次。
        # 對方說 WONT/DONT 就不回，避免兩邊無限互回。
        if verb in (WILL, DO) and (verb, opt) not in self.refused:
            self.refused.add((verb, opt))
            self.replies += bytes((IAC, DONT if verb == WILL else WONT, opt))


def encode(text):
    # 坑：送出去的換行要用 \r\n；0xFF 要寫兩次（Big5 不會出現 0xFF，保險用）
    data = text.replace("\n", "\r\n").encode(ENCODING, errors="replace")
    return data.replace(b"\xff", b"\xff\xff")


players = {}  # writer → 名字（已登入的人）


def send(writer, text):
    writer.write(encode(text))


def command(writer, name, line):
    """處理一行指令。回傳 False 代表要斷線。"""
    verb, _, arg = line.partition(" ")
    verb, arg = verb.lower(), arg.strip()
    if not line:
        pass
    elif verb == "chat":
        if not arg:
            send(writer, "要說什麼？\n")
        else:
            send(writer, f"你聊天：{arg}\n")
            for other in players:
                if other is not writer:
                    # 先換行，才不會接在對方的 prompt 後面；說完再補回對方的 prompt
                    send(other, f"\n{name} 聊天：{arg}\n{PROMPT}")
    elif verb == "quit":
        send(writer, "再見。\n")
        return False
    else:
        send(writer, "什麼？\n")
    send(writer, PROMPT)
    return True


async def handle(reader, writer):
    tn = Telnet()
    name = None
    send(writer, "Login: ")
    try:
        while True:
            data = await reader.read(4096)
            if not data:                            # 對方斷線
                break
            lines = tn.feed(data)
            if tn.replies:
                writer.write(bytes(tn.replies))
                tn.replies.clear()
            for line in lines:
                line = line.strip()
                if name is None:
                    if line:
                        name = line
                        players[writer] = name
                        print(f"{name} 登入，目前 {len(players)} 人", flush=True)
                        send(writer, f"歡迎，{name}。\n{PROMPT}")
                    else:
                        send(writer, "Login: ")
                elif not command(writer, name, line):
                    return
            await writer.drain()
    except OSError:                                 # 坑：對方直接關掉連線，不要讓整台伺服器掛掉
        pass
    finally:
        if players.pop(writer, None) is not None:
            print(f"{name} 離線，目前 {len(players)} 人", flush=True)
        writer.close()


async def main():
    p = argparse.ArgumentParser(description="最小的 MUD telnet 原型")
    p.add_argument("--host", default="127.0.0.1", help="給別台電腦連就用 0.0.0.0")
    p.add_argument("--port", type=int, default=4000)
    args = p.parse_args()
    server = await asyncio.start_server(handle, args.host, args.port)
    print(f"伺服器開在 {args.host}:{args.port}，編碼 {ENCODING}。按 Ctrl+C 結束。", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
