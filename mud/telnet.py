"""telnet 協定：把收到的 bytes 切成一行一行的字串，把要送出的文字編成 bytes。"""
from .config import ENCODING, MAX_LINE

# telnet 控制碼
IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240
BINARY = 0                          # telnet 選項：用 8-bit 傳
ECHO = 1                            # telnet 選項：由伺服器回顯（我們說 WILL ECHO，客戶端就不顯示打的字，打密碼用）

# 坑：沒談好 BINARY，有些客戶端（例如 macOS 的 telnet）會把每個 byte 的第 8 bit 拿掉，
# Big5 中文就全壞了。所以一連上就送這個，請對方用 8-bit 傳。
START = bytes((IAC, DO, BINARY))


class Telnet:
    """把收到的 bytes 切成一行一行的字串。狀態跨封包保留。"""

    def __init__(self):
        self.state = "data"         # data / iac / opt / sb / sb_iac
        self.verb = 0
        self.line = bytearray()
        self.last_cr = False
        self.replies = bytearray()  # 要回給客戶端的協商
        self.answered = {(WILL, BINARY)}  # 回過的協商；對方回 WILL BINARY 是答應 START，不能再回 DONT

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
        # 除了 START 請對方開的 BINARY，我們什麼都不開：對方 WILL 回 DONT，對方 DO 回 WONT，同一件事只回一次。
        # 對方說 WONT/DONT 就不回，避免兩邊無限互回。
        if verb in (WILL, DO) and (verb, opt) not in self.answered:
            self.answered.add((verb, opt))
            self.replies += bytes((IAC, DONT if verb == WILL else WONT, opt))

    def echo_off(self):
        """打密碼前送的控制碼：我們說 WILL ECHO，客戶端就不顯示打的字。要直接 writer.write，不能經過 encode()。"""
        # 對方回 DO ECHO 是答應我們，不能再回 WONT（那樣又把回顯打開了）：記成回過，_refuse() 就不會回它
        self.answered.add((DO, ECHO))
        return bytes((IAC, WILL, ECHO))

    def echo_on(self):
        """打完密碼送的控制碼：WONT ECHO，客戶端恢復顯示打的字。對方會回 DONT ECHO，不用回它。"""
        return bytes((IAC, WONT, ECHO))


def encode(text):
    # 坑：送出去的換行要用 \r\n；0xFF 要寫兩次（Big5 不會出現 0xFF，保險用）
    data = text.replace("\n", "\r\n").encode(ENCODING, errors="replace")
    return data.replace(b"\xff", b"\xff\xff")
