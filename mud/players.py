"""玩家：有連線的角色，以及送文字到連線。"""
from .characters import SEX_MALE, Character, characters
from .color import colorize
from .stats import shown
from .telnet import encode


class Player(Character):
    """已登入的玩家。"""

    def __init__(self, name, writer, room, sex=SEX_MALE):
        super().__init__(name, sex, room)
        self.writer = writer                 # 這個玩家的連線；重複登入時換成新的連線
        self.reply = None                    # 最後一個 tell 我的玩家（Player），reply 指令用
        # 建立角色或讀檔時才填（login.py、save.py）；直接建出來的（測試）沒有屬性
        self.password = None                 # 密碼的雜湊（save.hash_password），不存明碼
        self.race = None                     # stats.Race
        self.guild = None                    # stats.Guild
        self.level = 1
        self.exp = 0.0                       # 這一級累積的經驗（小數，顯示時取整），滿了升級（stats.gain_exp）
        self.primaries = {}                # 角色自己的主屬性（不含裝備加的）："str"、"int"、"wis"、"con"、"dex"
        self.resource_roll = 1.0             # 創角時骰的 MP、MV 倍率（0.95～1.05）
        self.points = 0                      # 還沒分配的主屬性點數（每升一級 1 點，用 train 分配）
        self.trained = {}                    # 每項主屬性靠升級加了幾點（降級時扣回用）；points ＋ Σ trained ＝ 等級 − 1
        self.imm = False                     # 管理員：找得到 IMM_COMMANDS（存檔的 imm）
        self.panel = {}                      # 全部次要屬性的快取，用 stats.recompute() 從頭算
        self.hp = self.mp = self.mv = 0.0    # 現在的 HP、MP、MV（上限在 panel）
        self.vars = {}                       # 腳本的變數（存檔）：{區域檔名（不含 .json）: {名字: 值}}
        self.skills = []                     # 會的技能 id（學會的順序，存檔）：建立角色時是公會一開始就會的（skills.starter）
        self.cooldowns = {}                  # 技能 id（還有 flee 失敗的等待 "flee"）→ 還要等幾個 tick 才能再用（skills.tick() 數），不存檔

    def send(self, text):
        send(self.writer, text)              # 下面那個 send()：寫到連線
        self.sent = True
        self.notified = False                # notify() 送完會再設回 True

    def prompt(self):
        """<HP 62/62 MP 25/25 MV 38/38>：現在的值照剩多少變色（多綠、一半左右黃、很少紅），上限是一般顏色。"""
        if not self.panel:                   # 沒有屬性（測試直接建的玩家）
            return super().prompt()
        parts = []
        for key in ("hp", "mp", "mv"):
            now, top = getattr(self, key), self.panel[key]
            parts.append(f"{key.upper()} {level_color(now, top)}{shown(now)}{{x/{shown(top)}")
        return colorize("<" + " ".join(parts) + "> ")


def level_color(now, top):
    """剩多少的顏色代碼：超過 2/3 綠、超過 1/3 黃、其他紅（上限是 0 的當作滿的）。"""
    ratio = now / top if top > 0 else 1
    return "{G" if ratio > 2 / 3 else "{Y" if ratio > 1 / 3 else "{R"


def online_players():
    """在線的玩家：characters 裡的 Player。"""
    return [c for c in characters if isinstance(c, Player)]


def send(writer, text):
    writer.write(encode(text))
