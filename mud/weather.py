"""天氣：全遊戲共用的遊戲時間、日夜和天空（使用者選的：全遊戲一個天氣）。

世界 tick 每次呼叫 tick()，遊戲時間走 1 小時（照 C 版的 weather_update()）。
天空用氣壓決定，一個 tick 最多走一格：晴天 ⇄ 陰天 ⇄ 下雨 ⇄ 打雷，
不會從晴天直接跳到下雨（使用者要求天氣要漸進）。
變化的通知只送給室外、醒著的玩家；室內看不到，也不能用 weather 指令。
"""
import enum
import random
import time

from .act import notify
from .area import RoomFlag
from .characters import Position
from .config import TICK_SECONDS
from .players import online_players

EPOCH = 650336715                   # 遊戲時間的起點（現實時間的秒數），跟 C 版一樣
HOURS_PER_DAY = 24
DAYS_PER_MONTH = 35
MONTHS_PER_YEAR = 17
MMHG_MIN, MMHG_MAX = 960, 1040      # 氣壓的範圍
CHANGE_LIMIT = 12                   # 每個 tick 氣壓變化量的上限（正負都是）
# 季節：氣壓往這個季節的目標靠。使用者要季節影響小一點：每個月四種天空都會出現，只是雨季多雨、乾季多晴。
# （C 版是往 1015／985 靠、拉力 2：乾季幾乎不下雨，雨季幾乎不放晴）
WET_MONTHS = range(9, 17)           # 雨季：9～16 月，其他月份是乾季
DRY_TARGET, WET_TARGET = 1010, 990  # 乾季、雨季的氣壓往哪裡靠
PULL = 1                            # 往目標拉的力氣：越小氣壓擺得越大，天氣越多變


class Sunlight(enum.IntEnum):
    """日夜。數字照 C 版的 SUN_*。"""
    DARK = 0                                # 天黑
    RISE = 1                                # 日出
    LIGHT = 2                               # 白天
    SET = 3                                 # 日落


class Sky(enum.IntEnum):
    """天空。數字照 C 版的 SKY_*，一個 tick 最多走一格（數字差 1）。"""
    CLOUDLESS = 0                           # 晴天
    CLOUDY = 1                              # 陰天
    RAINING = 2                             # 下雨
    LIGHTNING = 3                           # 打雷


# 走到這幾點時，日夜改變並通知
SUN_CHANGES = {
    6: (Sunlight.RISE, "太陽緩緩地從東邊升起，照亮了整塊世界。"),
    7: (Sunlight.LIGHT, "美好的一天已經開始。"),
    19: (Sunlight.SET, "太陽慢慢地往西邊落下。"),
    20: (Sunlight.DARK, "黑夜的時刻已經開啟。"),
}

# weather 指令看到的天空
SKY_LOOK = {Sky.CLOUDLESS: "晴朗無雲", Sky.CLOUDY: "烏雲密佈", Sky.RAINING: "下著大雨", Sky.LIGHTNING: "打雷閃電"}


def sunlight_at(hour):
    """幾點的日夜：那個小時（含）之前最近的一次變化。0～5 點天黑、6 點日出、7～18 點白天、19 點日落、20 點以後天黑。"""
    passed = [h for h in SUN_CHANGES if h <= hour]
    return SUN_CHANGES[max(passed)][0] if passed else Sunlight.DARK


def dice(rng, number, size):
    """擲 number 顆 size 面的骰子，加起來。"""
    return sum(rng.randint(1, size) for _ in range(number))


def one_in_four(rng):
    return rng.randrange(4) == 0


class Weather:
    """遊戲時間和天氣。"""

    def __init__(self, hour=0, day=0, month=0, year=0, sky=Sky.CLOUDLESS, mmhg=1000, change=0):
        self.hour = hour                    # 0～23
        self.day = day                      # 0～34
        self.month = month                  # 0～16
        self.year = year
        self.sky = sky                      # Sky
        self.mmhg = mmhg                    # 氣壓
        self.change = change                # 氣壓上一次的變化量：正的是在上升（南風）、負的是在下降（北風）

    @property
    def sunlight(self):
        return sunlight_at(self.hour)

    @classmethod
    def from_time(cls, seconds, rng=random):
        """開機時：從現實時間算出遊戲時間（每 TICK_SECONDS 秒是 1 小時），所以重開機後時間接得上。"""
        hours = int(seconds - EPOCH) // TICK_SECONDS
        days, hour = divmod(hours, HOURS_PER_DAY)
        months, day = divmod(days, DAYS_PER_MONTH)
        year, month = divmod(months, MONTHS_PER_YEAR)
        mmhg = MMHG_MIN + (rng.randint(1, 50) if 7 <= month <= 12 else rng.randint(1, 80))
        # 開機時的天空直接照氣壓決定，不通知
        if mmhg <= 980:
            sky = Sky.LIGHTNING
        elif mmhg <= 1000:
            sky = Sky.RAINING
        elif mmhg <= 1020:
            sky = Sky.CLOUDY
        else:
            sky = Sky.CLOUDLESS
        return cls(hour, day, month, year, sky, mmhg)

    def update(self, rng=random):
        """走一個小時。回傳要通知的文字（好幾句用換行接起來），沒有變化就是空字串。"""
        lines = []
        self.hour += 1
        if self.hour >= HOURS_PER_DAY:
            self.hour = 0
            self.day += 1
        if self.day >= DAYS_PER_MONTH:
            self.day = 0
            self.month += 1
        if self.month >= MONTHS_PER_YEAR:
            self.month = 0
            self.year += 1
        if self.hour in SUN_CHANGES:
            lines.append(SUN_CHANGES[self.hour][1])

        # 氣壓：往這個季節的目標靠，再加一點亂數
        target = WET_TARGET if self.month in WET_MONTHS else DRY_TARGET
        diff = -PULL if self.mmhg > target else PULL
        self.change += diff * dice(rng, 1, 4) + dice(rng, 2, 6) - dice(rng, 2, 6)
        self.change = max(-CHANGE_LIMIT, min(CHANGE_LIMIT, self.change))
        self.mmhg = max(MMHG_MIN, min(MMHG_MAX, self.mmhg + self.change))

        step = self.sky_step(rng)
        if step is not None:
            self.sky, text = step
            lines.append(text)
        return "\n".join(lines)

    def sky_step(self, rng):
        """天空這個 tick 要不要走一格：回傳 (新的天空, 通知)，不走是 None。一次只會走到旁邊那一格。"""
        p = self.mmhg
        if self.sky == Sky.CLOUDLESS:
            if p < 990 or (p < 1010 and one_in_four(rng)):
                return Sky.CLOUDY, "天空上面累積著雲層。"
        elif self.sky == Sky.CLOUDY:
            if p < 970 or (p < 990 and one_in_four(rng)):
                return Sky.RAINING, "天空開始下起雨來。"
            if p > 1030 and one_in_four(rng):
                return Sky.CLOUDLESS, "雲層逐漸地消失褪去。"
        elif self.sky == Sky.RAINING:
            if p < 970 and one_in_four(rng):
                return Sky.LIGHTNING, "天空劃下一道閃電。"
            if p > 1030 or (p > 1010 and one_in_four(rng)):
                return Sky.CLOUDY, "雨已經停止了。"
        elif self.sky == Sky.LIGHTNING:
            if p > 1010 or (p > 990 and one_in_four(rng)):
                return Sky.RAINING, "不再閃電打雷了。"
        return None

    def describe(self):
        """weather 指令看到的樣子。"""
        wind = "暖暖的南風徐徐的吹來" if self.change >= 0 else "冷冷的北風颼颼的吹來"
        return f"現在是 {self.hour} 點，天氣{SKY_LOOK[self.sky]}，還有{wind}。"


current = Weather.from_time(time.time())   # 全遊戲共用的那一個


def tick(rng=random):
    """世界 tick 呼叫：走一個小時，有變化就通知室外、醒著的玩家（好幾句合成一段，只補一次 prompt）。"""
    text = current.update(rng)
    if text:
        for p in online_players():
            if outside(p) and p.position > Position.SLEEPING:
                notify(p, text)


def outside(ch):
    """ch 在室外：所在房間沒有 INDOORS（室內）旗標。"""
    return RoomFlag.INDOORS not in ch.room.room_flags
