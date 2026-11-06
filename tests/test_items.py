"""物品指令：get、drop、wear、remove、inventory、equipment、imm 的 oload，還有背包和裝備的存檔。

訊息照 C 版 act_obj.c；一個指令的訊息合成一段（自己一個 prompt、旁邊的人也只一個）。
屬性、戰鬥、技能跟裝備的關係在 tests/test_gear.py。
"""
import asyncio
import json
import re

import pytest

import mud.commands as commands
from area_helpers import make_area, make_mobile, make_object, make_room, write_json
from mud import fight, inventory, objects, save, stats, zones
from mud.characters import Position, characters
from mud.commands import imm, items
from mud.config import ENCODING
from mud.npcs import Npc
from mud.players import Player

# 測試區域的物品：(檔案號碼, 名字, keywords, item_type, wear_flags, extra_flags, values, 重量, affects)
OBJECTS = [
    (1, "藥水", "potion 藥水", 10, "1", 0, [5, "cure light", "", ""], 1, []),
    (2, "長劍", "sword 長劍", 5, "1|8192", 0, [2, 0, 0, 3], 5, [{"location": 1, "modifier": 2}]),     # 力量 +2、重砍
    (3, "盾牌", "shield 盾牌", 9, "1|512", 0, [0, 0, 0, 0], 4, []),
    (4, "匕首", "dagger 匕首", 5, "1|512", 0, [1, 0, 0, 2], 3, []),                                     # 副手武器、戳刺
    (5, "大劍", "greatsword 大劍", 5, "1|8192", 512, [8, 0, 0, 13], 10, []),                            # 雙手武器
    (6, "戒指", "ring 戒指", 9, "1|2", 0, [0, 0, 0, 0], 1, [{"location": 6, "modifier": 5}]),          # HP +5
    (7, "皮甲", "armor 皮甲", 9, "1|8", 0, [0, 0, 0, 0], 8, [{"location": 14, "modifier": 3}]),        # 物理抗性 +3
    (8, "石頭", "rock 石頭", 13, "1", 0, [0, 0, 0, 0], 200, []),
    (9, "雕像", "statue 雕像", 12, "0", 0, [0, 0, 0, 0], 100, []),                                        # 撿不起來
    (10, "重劍", "heavy 重劍", 5, "1|8192", 0, [2, 0, 0, 1], 30, []),                                    # 1 級的力量拿不動
]


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


@pytest.fixture
def world(tmp_path, monkeypatch):
    """世界：房間 101、102 南北相連，102 有一隻野狗；物品 101～110（上面的表）。"""
    monkeypatch.setattr(fight, "TICK_SECONDS", 1000)
    objs = []
    for vnum, short, keywords, item_type, wear, extra, values, weight, affects in OBJECTS:
        o = make_object(vnum)
        o.update(short=short, keywords=keywords, item_type=item_type, wear_flags=wear, extra_flags=extra, values=values,
                 weight=weight, affects=affects, long=f"一個{short}放在這裡。")
        objs.append(o)
    dog = make_mobile(1)
    dog.update(short="野狗", keywords="dog 野狗", level=5, tier="normal", tier_roll=None, attack=None, defense=None,
               archetype=None, act=0, position=7, sex=0, long="", drops=[])
    rooms = [make_room(1, north=2), make_room(2, south=1)]
    reset = [{"cmd": "M", "rare": 0, "mob_vnum": 1, "limit": 1, "room_vnum": 2, "comment": ""}]
    write_json(tmp_path, "a.json", make_area("a.json", rooms, 100, mobiles=[dog], resets=reset, objects=objs))
    zones.load(tmp_path)
    yield tmp_path
    characters.clear()
    zones.stop()


def person(name="Shabu", race=stats.Race.HUMAN, level=1, imm_=False):
    """在線上、有屬性的玩家（人類力量 12：負重 140、武器重量 12），站在房間 102。"""
    p = Player(name, FakeWriter(), zones.world.rooms[102])
    p.race, p.guild = race, stats.Guild.SWORD
    p.primaries = dict(stats.RACE_PRIMARIES[race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.imm = imm_
    stats.set_level(p, level)
    characters.append(p)
    return p


def make(n, level=1, color=None):
    return objects.create(100 + n, level, color)


def give(p, *numbers, level=1):
    for n in numbers:
        p.carrying.insert(0, make(n, level))


def floor(*numbers):
    for n in numbers:
        zones.world.rooms[102].contents.insert(0, make(n))


def the_dog():
    return next(c for c in characters if isinstance(c, Npc))


def plain(p):
    text = re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))
    p.writer.data = b""
    return text


def say(p, line):
    plain(p)
    commands.command(p, line)
    return plain(p)


def prompt_of(p):
    return re.sub(r"\x1b\[[0-9;]*m", "", p.prompt())


def reply(p, *lines):
    """指令的回覆：幾行字，最後空一行、一個 prompt。"""
    return "\r\n".join(lines) + f"\r\n\r\n{prompt_of(p)}"


def names(objs):
    return [o.name for o in objs]


# ---- 縮寫、姿勢 ----

def test_abbreviations():
    assert commands.find("g") is items.do_get
    assert commands.find("dr") is items.do_drop
    assert commands.find("wear") is items.do_wear and commands.find("wea") is not items.do_wear   # wea 還是 weather
    assert commands.find("rem") is items.do_remove
    assert commands.find("i") is items.do_inventory and commands.find("inv") is items.do_inventory
    assert commands.find("eq") is items.do_equipment
    assert commands.find("ol", True) is imm.do_oload and commands.find("ol") is None


@pytest.mark.parametrize("line", ["get potion", "drop potion", "wear sword", "remove sword"])
def test_sleeping_cannot(world, line):
    p = person()
    give(p, 1, 2)
    p.position = Position.SLEEPING
    assert say(p, line).startswith("在你的睡夢中嗎？")


@pytest.mark.parametrize("line", ["inventory", "equipment"])
def test_sleeping_can_look_at_your_things(world, line):
    p = person()
    p.position = Position.SLEEPING
    assert say(p, line).startswith("你")


# ---- get ----

def test_get_from_the_floor(world):
    p, ming = person(), person("Ming")
    floor(1)
    plain(ming)
    assert say(p, "get po") == reply(p, "你拿起了【藥水/potion】。")         # 名字打開頭就行
    assert plain(ming) == f"\r\nShabu拿起了【藥水/potion】。\r\n\r\n{prompt_of(ming)}"
    assert names(p.carrying) == ["藥水"] and zones.world.rooms[102].contents == []


def test_get_the_second_one(world):
    p = person()
    floor(1, 6)                             # 地上：戒指、藥水（新的在前）
    zones.world.rooms[102].contents[1].name = "第二瓶"
    floor(1)                                # 地上：藥水、戒指、第二瓶
    say(p, "get 2.potion")
    assert names(p.carrying) == ["第二瓶"]


@pytest.mark.parametrize("line, want", [
    ("get", "你想拿起什麼東西？"),
    ("get xyz", "這裡找不到【xyz】。"),
    ("get statue", "你不能拿起這樣東西。"),
    ("get all", "我沒看到任何的東西。"),               # 地上只有撿不起來的
    ("get potion box", "這裡沒有【box】。"),
    ("get potion all", "你不能這麼做。"),
])
def test_get_mistakes(world, line, want):
    p = person()
    floor(9)
    assert say(p, line) == reply(p, want)
    assert p.carrying == []


def test_get_all_skips_what_cannot_be_taken(world):
    p, ming = person(), person("Ming")
    floor(9, 1, 6)                          # 地上：戒指、藥水、雕像
    plain(ming)
    assert say(p, "get all") == reply(p, "你拿起了【戒指/ring】。", "你拿起了【藥水/potion】。")
    assert names(p.carrying) == ["藥水", "戒指"] and names(zones.world.rooms[102].contents) == ["雕像"]
    assert plain(ming).count(prompt_of(ming)) == 1             # 旁邊的人也只有一個 prompt


def test_too_heavy_and_too_many(world):
    p = person()
    floor(8)
    assert say(p, "get rock") == reply(p, "【石頭/rock】你不能攜帶這麼重的物品。")
    give(p, *[1] * stats.CARRY_COUNT)
    floor(1)
    assert say(p, "get potion") == reply(p, "【藥水/potion】你不能攜帶這麼多的物品。")
    assert len(p.carrying) == stats.CARRY_COUNT


def test_get_all_stops_at_the_first_one_you_cannot_carry(world):
    p = person()
    give(p, *[1] * (stats.CARRY_COUNT - 1))
    floor(1, 6, 7)                          # 只拿得下一件：說一次就停（照 C 版）
    assert say(p, "get all") == reply(p, "你拿起了【皮甲/armor】。", "【戒指/ring】你不能攜帶這麼多的物品。")


def test_weight_counts_what_you_wear(world):
    p = person()
    give(p, 7)
    say(p, "wear armor")
    p.carrying.append(make(8))              # 背包 200 ＋ 身上 8
    assert inventory.carry_weight(p) == 208


def test_get_from_a_corpse(world):
    p, ming = person(), person("Ming")
    corpse = objects.make_corpse(the_dog())
    corpse.contains = [make(1), make(6)]
    assert say(p, "get corpse") == reply(p, "你不能拿起這樣東西。")          # 屍體撿不起來
    assert say(p, "get xyz corpse") == reply(p, "在【野狗的屍體/corpse】裡面，找不到那樣東西。")
    assert say(p, "get x potion") == reply(p, "這裡沒有【potion】。")
    give(p, 1)
    assert say(p, "get x potion") == reply(p, "這不是個容器。")              # 容器也可以在背包裡
    p.carrying.clear()
    assert say(p, "get ring corp") == reply(p, "你把【戒指/ring】從【野狗的屍體/corpse】拿出來。")   # 只打開頭也可以
    plain(ming)
    assert say(p, "get all corpse") == reply(p, "你把【藥水/potion】從【野狗的屍體/corpse】拿出來。")
    assert "Shabu把【藥水/potion】從【野狗的屍體/corpse】拿出來。" in plain(ming)
    assert say(p, "get all corpse") == reply(p, "在【野狗的屍體/corpse】裡面沒有東西。")
    assert names(p.carrying) == ["藥水", "戒指"]


# ---- drop ----

def test_drop(world):
    p, ming = person(), person("Ming")
    give(p, 1, 6)
    plain(ming)
    assert say(p, "drop ring") == reply(p, "你丟下了【戒指/ring】。")
    assert "Shabu丟下了【戒指/ring】。" in plain(ming)
    assert say(p, "drop all") == reply(p, "你丟下了【藥水/potion】。")
    assert names(zones.world.rooms[102].contents) == ["藥水", "戒指"] and p.carrying == []


@pytest.mark.parametrize("line, want", [
    ("drop", "你想丟掉什麼物品？"), ("drop xyz", "你沒有這樣東西。"), ("drop all", "你沒有攜帶任何東西。"),
])
def test_drop_mistakes(world, line, want):
    p = person()
    assert say(p, line) == reply(p, want)


def test_npcs_can_get_and_drop(world):
    dog = the_dog()
    floor(8)                                # 很重：生物不檢查負重
    commands.command(dog, "get rock")
    assert names(dog.carrying) == ["石頭"]
    commands.command(dog, "drop all")
    assert dog.carrying == []


# ---- inventory、equipment ----

def test_inventory(world):
    p = person()
    assert say(p, "i") == reply(p, "你目前所攜帶的東西有：", "     空無一物。", "（0/35 件，負重 0/140）")
    give(p, 1, 7)
    say(p, "wear armor")
    assert say(p, "inv") == reply(p, "你目前所攜帶的東西有：", "     藥水/potion", "（1/35 件，負重 9/140）")


def test_orcs_carry_more(world):
    p = person(race=stats.Race.ORC)         # 力量 14：170 × 1.25
    assert stats.carry_limit(p) == 212.5
    assert say(p, "i").endswith(f"（0/35 件，負重 0/213）\r\n\r\n{prompt_of(p)}")


def test_equipment(world):
    p = person(level=5)
    assert say(p, "eq") == reply(p, "你現在正在使用：", "", "沒有裝備。")
    give(p, 2, 4, 6, 6, 7)
    say(p, "wear all")
    assert say(p, "eq") == reply(p, "你現在正在使用：", "",
                                 " 【 左手手指 】 戒指/ring", " 【 右手手指 】 戒指/ring", " 【 穿在身上 】 皮甲/armor",
                                 " 【 左手武器 】 匕首/dagger", " 【 右手武器 】 長劍/sword")
    say(p, "remove all")
    give(p, 5)
    say(p, "wear greatsword")
    assert " 【 雙手武器 】 大劍/greatsword" in say(p, "eq")


# ---- wear ----

def test_wear_a_weapon(world):
    p, ming = person(), person("Ming")
    give(p, 2)
    plain(ming)
    assert say(p, "wear sword") == reply(p, "你把【長劍/sword】握為手中的武器。")
    assert "Shabu把【長劍/sword】握為手中的武器。" in plain(ming)
    assert p.equipment["wield"].name == "長劍" and p.carrying == []


@pytest.mark.parametrize("n, want", [
    (1, "這項物品你沒有辦法裝備，舉起或握到手裡。"),
    (10, "這把武器太重了，你力量(Str)過小，沒有辦法拿來當武器使用。"),
    (4, "你要先拿主手的武器，才能雙持。"),
])
def test_wear_mistakes(world, n, want):
    p = person()
    give(p, n)
    assert say(p, f"wear {p.carrying[0].keywords[0]}") == reply(p, want)
    assert p.equipment == {}


def test_wear_needs_the_level(world):
    p, ming = person(), person("Ming")
    give(p, 7, level=10)
    plain(ming)
    assert say(p, "wear armor") == reply(p, "你至少等級(Level)要達到【10】級以上才能使用這項物品。")
    assert "Shabu想嘗試裝備上【皮甲/armor】，卻因為自己的等級(Level)不足而苦惱。" in plain(ming)
    assert p.equipment == {}


@pytest.mark.parametrize("line, want", [("wear", "你想要裝備些什麼？"), ("wear xyz", "你沒有攜帶這項物品。"),
                                        ("wear all", "你沒有可以裝備的東西。")])
def test_wear_nothing(world, line, want):
    p = person()
    give(p, 1)
    assert say(p, line) == reply(p, want)


def test_wear_replaces(world):
    p = person()
    give(p, 7, 7)
    p.carrying[0].name = "新皮甲"
    say(p, "wear 2.armor")
    assert say(p, "wear armor") == reply(p, "你卸下了【皮甲/armor】。", "你把【新皮甲/armor】穿在身上。")
    assert p.equipment["body"].name == "新皮甲" and names(p.carrying) == ["皮甲"]


def test_rings(world):
    p = person()
    give(p, 6, 6, 6)
    for o, name in zip(p.carrying, ("一", "二", "三")):
        o.name = name
    assert say(p, "wear ring") == reply(p, "你把【一/ring】套上左手手指。")
    assert say(p, "wear ring") == reply(p, "你把【二/ring】套上右手手指。")
    assert say(p, "wear ring") == reply(p, "你卸下了【一/ring】。", "你把【三/ring】套上左手手指。")   # 兩隻都有就換左手


def test_wear_all_does_not_replace(world):
    p = person()
    give(p, 7)
    say(p, "wear armor")
    give(p, 4, 2, 7)                        # 背包：皮甲、長劍、匕首（匕首比長劍新，但要等長劍先拿）
    assert say(p, "wear all") == reply(p, "你把【長劍/sword】握為手中的武器。", "你把【匕首/dagger】握為手中的武器。")
    assert names(p.carrying) == ["皮甲"]


def test_two_handed(world):
    p = person(level=5)
    give(p, 2, 3)
    say(p, "wear all")                      # 長劍、盾牌
    give(p, 5)
    assert say(p, "wear greatsword") == reply(p, "你卸下了【盾牌/shield】。", "你卸下了【長劍/sword】。",
                                              "你把【大劍/greatsword】握為手中的武器。")
    assert set(p.equipment) == {"wield"}
    assert say(p, "wear shield") == reply(p, "你卸下了【大劍/greatsword】。", "你把【盾牌/shield】做為盾牌。")
    give(p, 4)
    say(p, "remove shield")
    say(p, "wear greatsword")
    assert say(p, "wear dagger") == reply(p, "你要先拿主手的武器，才能雙持。")   # 雙手武器不能再拿副手武器


def test_npcs_do_not_wear(world):
    dog = the_dog()
    sent = []
    dog.send = sent.append
    dog.carrying.append(make(2))
    commands.command(dog, "wear sword")
    commands.command(dog, "remove all")
    assert [s for s in sent if "\n> " not in s and s != "> "] == ["你沒有辦法使用這項物品。\n"] * 2   # 生物也會收到 prompt，不算
    assert dog.equipment == {}


def test_wear_while_fighting(world):
    p = person()
    give(p, 2)

    async def main():
        fight.start_fight(p, the_dog())
        return say(p, "wear sword")

    assert asyncio.run(main()).startswith("你把【長劍/sword】握為手中的武器。")


# ---- remove ----

def test_remove(world):
    p, ming = person(), person("Ming")
    give(p, 2)
    say(p, "wear sword")
    plain(ming)
    assert say(p, "rem sword") == reply(p, "你卸下了【長劍/sword】。")
    assert "Shabu卸下了【長劍/sword】。" in plain(ming)
    assert p.equipment == {} and names(p.carrying) == ["長劍"]


@pytest.mark.parametrize("line, want", [("remove", "你想要卸下什麼東西？"), ("remove xyz", "你身上沒有這項物品。"),
                                        ("remove all", "你身上沒有穿任何裝備。")])
def test_remove_nothing(world, line, want):
    p = person()
    assert say(p, line) == reply(p, want)


def test_remove_the_main_weapon_while_dual_wielding(world):
    p = person()
    give(p, 4, 2)
    say(p, "wear all")
    assert say(p, "remove sword") == reply(p, "你要先卸下左手的武器。")
    assert say(p, "remove all") == reply(p, "你卸下了【匕首/dagger】。", "你卸下了【長劍/sword】。")    # 副手先卸


def test_remove_with_a_full_pack(world):
    p = person()
    give(p, 7)
    say(p, "wear armor")
    give(p, *[1] * stats.CARRY_COUNT)
    assert say(p, "remove armor") == reply(p, "【皮甲/armor】你不能攜帶這麼多的物品。")
    assert "body" in p.equipment


# ---- oload ----

def test_oload(world):
    p, ming = person("Admin", level=20, imm_=True), person("Ming")
    plain(ming)
    assert say(p, "oload 102") == reply(p, "你創造了【長劍/sword】！")
    assert p.carrying[0].level == 20 and p.carrying[0].color is None          # 等級沒寫是自己的
    assert plain(ming) == ""                                                   # 放進自己背包，別人不知道（照 C 版）
    say(p, "oload 107 3 white")
    armor = p.carrying[0]
    assert (armor.level, armor.color) == (3, "white") and armor.affects                       # 白色的隨機裝備有屬性
    assert say(p, "ol 109") == reply(p, "你創造了【雕像/statue】！")                          # 撿不起來的放地上
    assert names(zones.world.rooms[102].contents) == ["雕像"]
    assert "Admin創造了【雕像/statue】！" in plain(ming)


@pytest.mark.parametrize("line, want", [
    ("oload", "用法：oload <號碼> [等級] [顏色]"), ("oload abc", "用法：oload <號碼> [等級] [顏色]"),
    ("oload 999", "沒有這個號碼的物品。"), ("oload 102 0", "等級要寫 1～100。"), ("oload 102 101", "等級要寫 1～100。"),
    ("oload 102 5 red", "顏色要寫 gray、white、blue、purple、orange。"),
])
def test_oload_mistakes(world, line, want):
    p = person("Admin", imm_=True)
    assert say(p, line) == reply(p, want)
    assert p.carrying == []


def test_oload_is_for_imm(world):
    p = person()
    assert say(p, "oload 102") == reply(p, "什麼？")


# ---- 存檔 ----

def test_save_and_load_your_things(world, tmp_path, monkeypatch):
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path / "players")
    p = person(level=5)
    p.password = "x"
    p.carrying = [make(1), make(7, 3, "blue")]
    p.equipment = {"wield": make(2, 5, "white"), "finger_l": make(6)}
    stats.recompute(p)
    save.save_player(p)
    loaded = save.player_from(save.load_data("Shabu"), FakeWriter())
    for mine, theirs in [*zip(p.carrying, loaded.carrying), *((p.equipment[k], loaded.equipment[k]) for k in p.equipment)]:
        assert objects.to_data(mine) == objects.to_data(theirs)
    assert set(loaded.equipment) == {"wield", "finger_l"}
    assert loaded.panel == pytest.approx(p.panel)                              # 裝備的屬性也算回來了
    assert loaded.equipment["wield"].attack == p.equipment["wield"].attack


def test_old_saves_have_nothing(world, tmp_path, monkeypatch):
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path / "players")
    p = person()
    p.password = "x"
    save.save_player(p)
    path = save.path_of("Shabu")
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["carrying"], data["equipment"]
    loaded = save.player_from(data, FakeWriter())
    assert loaded.carrying == [] and loaded.equipment == {}
