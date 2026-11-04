import asyncio
import random
from collections import Counter

import pytest

import mud.commands as commands
from area_helpers import make_room, write_area
from mud import weather, zones
from mud.characters import Position, characters
from mud.commands import system
from mud.config import ENCODING
from mud.players import Player
from mud.weather import EPOCH, Sky, Sunlight, Weather


class FakeRng:
    """假的亂數：randint 一律回傳最小（high=True 是最大）值；randrange 回傳 roll（0 就是 1/4 機率成立）。"""

    def __init__(self, roll=1, high=False):
        self.roll, self.high = roll, high

    def randint(self, a, b):
        return b if self.high else a

    def randrange(self, n):
        return self.roll


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


def test_time_at_boot_comes_from_real_time():
    # 第 3 年 5 月 10 日 14 點：每 30 秒是遊戲裡的 1 小時
    hours = ((3 * 17 + 5) * 35 + 10) * 24 + 14
    w = Weather.from_time(EPOCH + hours * 30 + 29, FakeRng())
    assert (w.year, w.month, w.day, w.hour) == (3, 5, 10, 14)
    assert w.sunlight == Sunlight.LIGHT
    assert (w.mmhg, w.sky, w.change) == (961, Sky.LIGHTNING, 0)     # 960 ＋ 最小的亂數 1：氣壓很低，打雷
    assert Weather.from_time(EPOCH, FakeRng(high=True)).sky == Sky.CLOUDLESS   # 960 ＋ 80：晴天


@pytest.mark.parametrize("hour, want", [(0, Sunlight.DARK), (5, Sunlight.DARK), (6, Sunlight.RISE), (7, Sunlight.LIGHT),
                                        (18, Sunlight.LIGHT), (19, Sunlight.SET), (20, Sunlight.DARK), (23, Sunlight.DARK)])
def test_sunlight_by_hour(hour, want):
    assert Weather(hour=hour).sunlight == want


@pytest.mark.parametrize("hour, want, text", [
    (5, Sunlight.RISE, "太陽緩緩地從東邊升起，照亮了整塊世界。"),
    (6, Sunlight.LIGHT, "美好的一天已經開始。"),
    (18, Sunlight.SET, "太陽慢慢地往西邊落下。"),
    (19, Sunlight.DARK, "黑夜的時刻已經開啟。"),
])
def test_sun_changes_are_announced(hour, want, text):
    w = Weather(hour=hour, sky=Sky.CLOUDY, mmhg=1000)   # 陰天、氣壓 1000：這個 tick 天空不會變
    assert w.update(FakeRng()) == text
    assert (w.hour, w.sunlight) == (hour + 1, want)


def test_quiet_hour_says_nothing():
    w = Weather(hour=10, sky=Sky.CLOUDY, mmhg=1000)
    assert w.update(FakeRng()) == ""


@pytest.mark.parametrize("start, want", [
    ((23, 0, 0, 0), (0, 1, 0, 0)),          # 換日
    ((23, 34, 0, 0), (0, 0, 1, 0)),         # 換月：一個月 35 天
    ((23, 34, 16, 0), (0, 0, 0, 1)),        # 換年：一年 17 個月
])
def test_calendar(start, want):
    hour, day, month, year = start
    w = Weather(hour=hour, day=day, month=month, year=year, sky=Sky.CLOUDY, mmhg=1000)
    w.update(FakeRng())
    assert (w.hour, w.day, w.month, w.year) == want


# 假亂數的骰子都是 1，所以氣壓這個 tick 只變 ±1（0 月是乾季：高於 1010 就降、不然就升）
@pytest.mark.parametrize("sky, mmhg, roll, want, text", [
    (Sky.CLOUDLESS, 985, 1, Sky.CLOUDY, "天空上面累積著雲層。"),       # 986 < 990
    (Sky.CLOUDLESS, 1000, 0, Sky.CLOUDY, "天空上面累積著雲層。"),      # 1001 < 1010，1/4 機率成立
    (Sky.CLOUDLESS, 1000, 1, Sky.CLOUDLESS, ""),                       # 1/4 機率沒成立
    (Sky.CLOUDY, 960, 1, Sky.RAINING, "天空開始下起雨來。"),           # 961 < 970
    (Sky.CLOUDY, 1040, 0, Sky.CLOUDLESS, "雲層逐漸地消失褪去。"),      # 1039 > 1030，1/4 機率成立
    (Sky.RAINING, 960, 0, Sky.LIGHTNING, "天空劃下一道閃電。"),        # 961 < 970，1/4 機率成立
    (Sky.RAINING, 1040, 1, Sky.CLOUDY, "雨已經停止了。"),              # 1039 > 1030
    (Sky.LIGHTNING, 1040, 1, Sky.RAINING, "不再閃電打雷了。"),         # 1039 > 1010
])
def test_sky_steps(sky, mmhg, roll, want, text):
    w = Weather(hour=10, sky=sky, mmhg=mmhg)
    assert w.update(FakeRng(roll)) == text
    assert w.sky == want


def test_pressure_and_change_stay_in_range():
    w = Weather(hour=10, sky=Sky.CLOUDY, mmhg=1038, change=12)
    w.update(FakeRng())                     # 變化量 12 − 1 ＝ 11，1038 ＋ 11 超過上限
    assert (w.change, w.mmhg) == (11, 1040)
    w = Weather(hour=10, sky=Sky.CLOUDY, mmhg=962, change=-12)
    w.update(FakeRng())                     # 變化量 −12 ＋ 1 ＝ −11，962 − 11 低於下限
    assert (w.change, w.mmhg) == (-11, 960)
    w = Weather(hour=10, sky=Sky.CLOUDY, mmhg=960, change=12)
    w.update(FakeRng())                     # 變化量 12 ＋ 1 超過上限
    assert w.change == 12


def test_sky_changes_one_step_at_a_time():
    # 使用者要求天氣要漸進：用真的亂數跑很多個 tick，天空每次最多走一格（晴天不會直接變下雨）
    rng = random.Random(1)
    w = Weather.from_time(EPOCH, rng)
    seen = {w.sky}
    for _ in range(20000):
        before = w.sky
        w.update(rng)
        assert abs(w.sky - before) <= 1, (before, w.sky)
        seen.add(w.sky)
    assert seen == set(Sky)                 # 四種天空都出現過，這個測試才有意義


def test_every_season_has_all_four_skies():
    # 使用者要隨機、季節影響小：乾季、雨季都會出現四種天空，只是雨季比較常下雨、乾季比較常放晴
    rng = random.Random(3)
    w = Weather.from_time(EPOCH, rng)
    dry, wet = Counter(), Counter()
    for _ in range(17 * 35 * 24 * 3):       # 3 個遊戲年
        w.update(rng)
        (wet if w.month in weather.WET_MONTHS else dry)[w.sky] += 1
    for season in (dry, wet):
        assert all(season[s] > sum(season.values()) * 0.03 for s in Sky), season
    assert wet[Sky.RAINING] > dry[Sky.RAINING] and dry[Sky.CLOUDLESS] > wet[Sky.CLOUDLESS]


@pytest.fixture
def world(tmp_path):
    # 房間 101 在室外、102 在室內（room_flags 8 是 INDOORS）
    indoor = make_room(2, south=1)
    indoor["room_flags"] = 8
    write_area(tmp_path, "a.json", [make_room(1, north=2), indoor])
    zones.load(tmp_path)
    yield zones.world
    characters.clear()
    zones.stop()


def player(name, room, position=Position.STANDING):
    p = Player(name, FakeWriter(), room)
    p.position = position
    characters.append(p)
    return p


def test_only_awake_players_outside_are_told(world, monkeypatch):
    # 5→6 點日出，同時晴天變陰天：兩句合成一段，只補一次 prompt
    monkeypatch.setattr(weather, "current", Weather(hour=5, sky=Sky.CLOUDLESS, mmhg=985))
    out = player("小明", world.rooms[101])
    resting = player("阿華", world.rooms[101], Position.RESTING)
    sleeping = player("小美", world.rooms[101], Position.SLEEPING)
    inside = player("Bob", world.rooms[102])
    weather.tick(FakeRng())
    want = "\r\n太陽緩緩地從東邊升起，照亮了整塊世界。\r\n天空上面累積著雲層。\r\nHP100> ".encode(ENCODING)
    assert out.writer.data == want and resting.writer.data == want
    assert sleeping.writer.data == b"" and inside.writer.data == b""


def test_weather_command_outside(world, monkeypatch):
    ming = player("小明", world.rooms[101])
    monkeypatch.setattr(weather, "current", Weather(hour=14, sky=Sky.CLOUDLESS, change=3))
    commands.command(ming, "weather")
    assert ming.writer.data == "現在是 14 點，天氣晴朗無雲，還有暖暖的南風徐徐的吹來。\r\nHP100> ".encode(ENCODING)
    ming.writer.data = b""
    monkeypatch.setattr(weather, "current", Weather(hour=2, sky=Sky.RAINING, change=-1))
    commands.command(ming, "wea")
    assert ming.writer.data == "現在是 2 點，天氣下著大雨，還有冷冷的北風颼颼的吹來。\r\nHP100> ".encode(ENCODING)


def test_weather_command_inside(world):
    bob = player("Bob", world.rooms[102])
    commands.command(bob, "weather")
    assert bob.writer.data == "你現在在室內是看不到天氣的。\r\nHP100> ".encode(ENCODING)


def test_w_is_still_west():
    assert commands.find("w") is system.do_west
    assert commands.find("wea") is system.do_weather


def test_only_the_world_tick_moves_the_weather(tmp_path, monkeypatch):
    # 全遊戲一個天氣：世界的 tick 走時間，動態區域、副本的 tick 不動它
    write_area(tmp_path, "world.json", [make_room(1, north=201)], area_number=100)
    write_area(tmp_path, "dyn.json", [make_room(1, south=101)], area_number=200, kind="dynamic")
    write_area(tmp_path, "inst.json", [make_room(1)], area_number=300, kind="instance")
    zones.load(tmp_path)
    monkeypatch.setattr(zones, "HOUR_TICKS", 1)     # 每個 tick 都是一小時，一次就看得出來
    ticks = []
    monkeypatch.setattr(weather, "tick", lambda: ticks.append(1))

    async def main():
        dyn = zones.room_at(zones.world.rooms[101], 201).zone
        inst = zones.instance("inst.json", "小明")
        zones.world.tick()
        dyn.tick()
        inst.tick()

    asyncio.run(main())
    zones.stop()
    assert ticks == [1]
