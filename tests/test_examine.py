"""exam（看背包和身上的物品，照 C 版 identify 的句型）、imm 的 ostat、mstat，名稱表跟手冊比對，地上那一行。

借用 tests/test_items.py 的區域和輔助函式。
"""
import re
from pathlib import Path

import pytest

import mud.commands as commands
from mud import equipment, objects, stats, zones
from mud.area import ITEM_TYPE_NAMES, WEAPON_KIND_NAMES, WeaponKind
from mud.characters import Position
from mud.commands import imm, items, system
from test_items import give, make, person, reply, say, the_dog, world  # noqa: F401（world 是 fixture）

AREA_MANUAL = Path(__file__).resolve().parent.parent / "docs" / "區域製作手冊.md"


def section(text, title):
    start = text.index(title)
    end = text.find("\n### ", start + len(title))
    return text[start:end]


def test_item_type_names_match_the_manual():
    part = section(AREA_MANUAL.read_text(encoding="utf-8"), "### item_type")
    rows = {int(n): meaning.split("。")[0] for n, meaning in re.findall(r"\| (\d+) \| \w+ \| ([^|]+) \|", part)}
    assert rows == ITEM_TYPE_NAMES


def test_weapon_kind_names_match_the_manual():
    part = section(AREA_MANUAL.read_text(encoding="utf-8"), "### 武器種類")
    rows = {int(n): name for n, name in re.findall(r"\| (\d+) \| \w+ \| (\S+) \| [單雙]手 \|", part)}
    assert rows == {int(k): v for k, v in WEAPON_KIND_NAMES.items()}
    assert set(WEAPON_KIND_NAMES) == set(WeaponKind)


# ---- 地上那一行 ----

def test_floor_line_ends_with_the_english_name(world):
    p = person()
    zones.world.rooms[102].contents.insert(0, make(2))
    objects.make_corpse(the_dog())
    text = re.sub(r"\x1b\[[0-9;]*m", "", system.look(p))
    assert text.endswith("野狗的屍體橫躺在地上。/corpse\n一個長劍放在這裡。/sword\n")
    sword = zones.world.rooms[102].contents[1]
    assert objects.on_floor(sword).endswith("一個長劍放在這裡。/" + objects.ENGLISH + "sword" + objects.RESET)   # 英文亮青


def test_floor_line_without_english(world):
    obj = make(2)
    obj.keywords = ["長劍"]
    assert objects.on_floor(obj) == objects.FLOOR + "一個長劍放在這裡。" + objects.RESET


# ---- exam ----

def test_exam_a_weapon(world):
    p = person(level=10)
    give(p, 2, level=10)
    sword = p.carrying[0]
    low, high = sword.base["dmg_min"], sword.base["dmg_max"]
    assert say(p, "ex sword") == reply(
        p, "物品名稱：【長劍/sword】，型式：【武器】", "重量：【5】，使用等級：【10】", "穿戴部位：【主手】",
        "武器：【長劍】，攻擊方式：【重砍】",
        f"攻擊力範圍：【{stats.shown(low)} - {stats.shown(high)}】（平均【{stats.shown((low + high) / 2)}】）",
        "加成：力量 +2")


def test_exam_armor_with_a_color(world):
    p = person(level=5)
    p.carrying.insert(0, make(7, 5, "blue"))
    armor = p.carrying[0]
    say(p, "wear armor")                    # 身上穿的也看得到
    bonus = "、".join(f"{stats.STAT_NAMES[a.name.lower()]} +{n}" for a, n in armor.affects)
    assert say(p, "examine armor") == reply(
        p, "物品名稱：【皮甲/armor】，型式：【護具】", "重量：【8】，使用等級：【5】，稀有度：【藍色】", "穿戴部位：【身體】",
        f"防護力：【{stats.shown(armor.base['ac'])}】", "加成：" + bonus)


@pytest.mark.parametrize("n, want", [
    (1, ["物品名稱：【藥水/potion】，型式：【藥水】", "重量：【1】，使用等級：【1】"]),               # 不是裝備：只有兩行
    (6, ["物品名稱：【戒指/ring】，型式：【護具】", "重量：【1】，使用等級：【1】", "穿戴部位：【戒指】",
         "加成：HP +5"]),                                                                              # 戒指沒有防護力
])
def test_exam_other_things(world, n, want):
    p = person()
    give(p, n)
    assert say(p, f"exam {p.carrying[0].keywords[0]}") == reply(p, *want)


def test_exam_two_handed(world):
    p = person(level=5)
    give(p, 5)
    assert "穿戴部位：【雙手】\r\n武器：【大劍】，攻擊方式：【橫劈】" in say(p, "exam great")


def test_exam_negative_bonus(world):
    p = person()
    give(p, 2)
    p.carrying[0].affects = [(p.carrying[0].affects[0][0], -1)]
    assert "加成：力量 -1" in say(p, "exam sword")


@pytest.mark.parametrize("line, want", [("exam", "你想要檢查些什麼？"), ("exam sword", "你身上沒有這樣東西。")])
def test_exam_only_your_own_things(world, line, want):
    p = person()
    zones.world.rooms[102].contents.insert(0, make(2))       # 地上的不算（使用者要的）
    assert say(p, line) == reply(p, want)


def test_exam_needs_you_awake(world):
    p = person()
    give(p, 2)
    p.position = Position.SLEEPING
    assert say(p, "exam sword").startswith("在你的睡夢中嗎？")
    assert commands.find("ex") is items.do_examine and commands.find("e") is commands.find("east")


# ---- ostat ----

def test_ostat_finds_things_everywhere(world):
    p = person("Admin", level=20, imm_=True)
    give(p, 1)
    p.equipment["finger_l"] = make(6)
    zones.world.rooms[102].contents.insert(0, make(3))
    corpse = objects.make_corpse(the_dog())
    corpse.contains = [make(7)]
    for word, name in [("potion", "藥水"), ("ring", "戒指"), ("shield", "盾牌"), ("armor", "皮甲"), ("corpse", "野狗的屍體")]:
        assert f"名字 {name}" in say(p, f"ostat {word}"), word
    assert say(p, "ostat xyz") == reply(p, "找不到這件物品。")
    assert say(p, "ostat") == reply(p, "用法：ostat <名字或號碼>")


def test_ostat_shows_everything(world):
    p = person("Admin", level=20, imm_=True)
    p.carrying.insert(0, make(2, 10, "blue"))
    sword = p.carrying[0]
    text = say(p, "os sword")
    assert "號碼 102  名字 長劍  keywords sword 長劍" in text
    assert "種類 5 武器  等級 10  顏色 blue  重量 5  撿得起來 是" in text
    assert "部位 wield（主手）  武器種類 2 長劍  攻擊方式 3 重砍" in text
    assert f"基本值 dmg_min {sword.base['dmg_min']:.2f}  dmg_max {sword.base['dmg_max']:.2f}" in text
    assert "加成 STR(1) +2" in text
    points = 2 * equipment.price("str", 10)
    cap = equipment.cap(10, "wield") * 1.2
    assert f"點數 {points:.1f} / 上限 {cap:.1f}（blue ×1.2）" in text
    assert "地上那一行 一個長劍放在這裡。" in text and "timer 無  裡面 0 件" in text


def test_ostat_a_number(world):
    p = person("Admin", imm_=True)
    text = say(p, "ostat 102")
    assert text.startswith("號碼 102（區域檔的寫法）  short 長劍  keywords sword 長劍\r\n")
    assert "item_type 5 武器  wear_flags 1|8192  extra_flags 0  weight 5" in text
    assert "values [2, 0, 0, 3]" in text and "affects STR(1) +2" in text
    assert say(p, "ostat 999") == reply(p, "沒有這個號碼的物品。")


# ---- mstat ----

def test_mstat_a_mobile(world):
    p = person("Admin", level=20, imm_=True)
    dog = the_dog()
    text = say(p, "m dog")
    assert "號碼 101  名字 野狗  keywords dog 野狗" in text
    assert "等級 5  種類 normal  攻擊 phys 100%  攻防 標準  原型 標準" in text
    assert "act 0  姿勢 STANDING  房間 102  正在打 無" in text
    assert f"HP {dog.hp:.1f}/{dog.panel['hp']:.1f}" in text
    assert f"物理傷害 {dog.panel['dmg_phys']:.2f}" in text and f"武器基本傷害 {dog.panel['wpn']:.2f}" in text
    assert "掉落表 沒有" in text


def test_mstat_a_player(world):
    admin, p = person("Admin", level=20, imm_=True), person("Shabu", level=3)
    give(p, 2, 1)
    say(p, "wear sword")
    text = say(admin, "mstat sha")
    assert "名字 Shabu  imm 否  種族 人類  公會 劍之公會  等級 3" in text
    assert "力量 14（12＋2）" in text and "可分配 2" in text
    assert "背包 1 件  裝備 1 件  冷卻 無" in text
    assert f"命中 {p.panel['hit']:.2f}" in text


def test_mstat_mistakes(world):
    p = person("Admin", imm_=True)
    assert say(p, "mstat") == reply(p, "用法：mstat <名字>")
    assert say(p, "mstat bird") == reply(p, "找不到這個角色。")


def test_stat_commands_are_for_imm(world):
    p = person()
    assert say(p, "ostat sword") == reply(p, "什麼？")
    assert say(p, "mstat dog") == reply(p, "什麼？")
    assert commands.find("os", True) is imm.do_ostat and commands.find("m", True) is imm.do_mstat


def test_ostat_looks_in_your_pack_first(world):
    # 順序：背包、身上、地上、地上屍體裡
    p = person("Admin", imm_=True)
    zones.world.rooms[102].contents.insert(0, make(1))
    give(p, 1)
    p.carrying[0].name = "背包的藥水"
    assert "名字 背包的藥水" in say(p, "ostat potion")
    assert "名字 藥水" in say(p, "ostat 2.potion")
