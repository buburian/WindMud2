"""help：說明檔的檢查（helps.check）、讀檔、help 的三種畫面、縮寫、imm 的分類。"""
import json
from pathlib import Path

import pytest

import mud.commands as commands
from mud import helps
from mud.characters import Position
from mud.commands import help_command
from mud.config import ENCODING
from mud.players import Player

HELP_FILE = Path(__file__).resolve().parent.parent / "help" / "help.json"     # 不靠目前在哪個資料夾
NAMES = [c for c, _, _ in commands.COMMANDS]
IMM_NAMES = [c for c, _, _ in commands.IMM_COMMANDS]
NOT_FOUND = "對不起，找不到相對應的說明。\r\n\r\n> "


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


@pytest.fixture(autouse=True)
def loaded():
    helps.load(HELP_FILE)


def data():
    return json.loads(HELP_FILE.read_text(encoding="utf-8"))


def entry(d, command):
    return next(e for e in d["entries"] if command in e["commands"])


def say(line, imm=False, position=Position.STANDING):
    """沒有屬性的玩家（prompt 是 "> "）打一行指令，回傳他看到的。"""
    p = Player("Ming", FakeWriter(), None)
    p.imm, p.position = imm, position
    commands.command(p, line)
    return p.writer.data.decode(ENCODING)


# ---- 說明檔的檢查 ----

def test_the_help_file_has_no_problems():
    # 所以每個指令（含 imm 指令）都剛好有一筆說明，每個字都轉得成 Big5
    assert helps.check(data(), NAMES, IMM_NAMES) == []


def test_every_command_finds_its_own_help():
    # 打全名一定找到自己那一筆（指令名稱不會被前面的指令擋住）
    for name in NAMES + IMM_NAMES:
        assert name in help_command.entry_of(name, True)["commands"], name


def remove_use(d):
    d["entries"].remove(entry(d, "use"))


def kill_twice(d):
    entry(d, "use")["commands"].append("kill")


def unknown_command(d):
    entry(d, "kill")["commands"].append("fly")


def unknown_category(d):
    entry(d, "kill")["category"] = "魔法"


def imm_command_in_normal_category(d):
    entry(d, "advance")["category"] = "戰鬥"


def normal_command_in_imm_category(d):
    entry(d, "kill")["category"] = "管理員"


def missing_field(d):
    del entry(d, "kill")["summary"]


def extra_field(d):
    entry(d, "kill")["level"] = 0


def text_not_a_list(d):
    entry(d, "kill")["text"] = "打同房間的生物"


def imm_not_bool(d):
    d["categories"][0]["imm"] = 0


def not_big5(d):
    entry(d, "kill")["text"].append("笑臉 😀")


def empty_category(d):
    d["categories"].append({"name": "魔法", "imm": False})


def same_category_twice(d):
    d["categories"].append({"name": "戰鬥", "imm": False})


def no_commands(d):
    d["entries"].append({"category": "戰鬥", "commands": [], "usage": "", "summary": "", "text": []})


def not_text_in_commands(d):
    entry(d, "kill")["commands"].append(5)


@pytest.mark.parametrize("change, want", [
    (remove_use, "use 沒有說明"),
    (kill_twice, "kill 已經寫在 entries 第"),
    (unknown_command, "沒有 fly 這個指令"),
    (unknown_category, "沒有「魔法」這個分類"),
    (imm_command_in_normal_category, "advance 是 imm 指令，要放在 imm 的分類"),
    (normal_command_in_imm_category, "kill 是一般指令，不能放在 imm 的分類"),
    (missing_field, "少了欄位：summary"),
    (extra_field, "多了欄位：level"),
    (text_not_a_list, "的 text 要是清單"),
    (imm_not_bool, "的 imm 要寫 true 或 false，現在是 0"),
    (not_big5, "「😀」（U+1F600）轉不成 Big5"),
    (empty_category, "分類「魔法」沒有任何說明"),
    (same_category_twice, "分類「戰鬥」重複了"),
    (no_commands, "commands 是空的"),
    (not_text_in_commands, "commands、text 裡面要都是文字"),
])
def test_check_finds_problems(change, want):
    d = data()
    change(d)
    problems = helps.check(d, NAMES, IMM_NAMES)
    assert any(want in p for p in problems), problems


def test_check_needs_an_object_at_the_top():
    assert helps.check([], NAMES, IMM_NAMES) == ["檔案最上層 要是一個物件（{…}），現在是 []"]


def test_load_problems(tmp_path):
    before = helps.entries
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="不是正確的 JSON：第 1 行"):
        helps.load(broken)
    with pytest.raises(ValueError, match="讀不到說明檔"):
        helps.load(tmp_path / "none.json")
    d = data()
    remove_use(d)
    unknown_command(d)
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match=r"（共 2 個問題）"):
        helps.load(wrong)
    assert helps.entries is before                   # 有問題就不換掉原本的


# ---- help 的畫面 ----

SUMMARY = [
    "說明的分類（help 分類 或 help 指令 看細節）：",
    "  移動  north east south west up down",
    "  資訊  look score who weather skills help",
    "  溝通  chat tell reply say",
    "  角色  train rest sleep stand save quit",
    "  戰鬥  kill use",
    "  物品  get drop wear remove inventory equipment examine",
    "  門    open close lock unlock",
]


def test_help_shows_the_categories():
    assert say("help") == "\r\n".join(SUMMARY) + "\r\n\r\n> "


def test_imm_sees_the_imm_category():
    # 分類名稱照最寬的對齊（管理員 6 格）
    want = [
        "說明的分類（help 分類 或 help 指令 看細節）：",
        "  移動    north east south west up down",
        "  資訊    look score who weather skills help",
        "  溝通    chat tell reply say",
        "  角色    train rest sleep stand save quit",
        "  戰鬥    kill use",
        "  物品    get drop wear remove inventory equipment examine",
        "  門      open close lock unlock",
        "  管理員  advance slay oload ostat mstat",
    ]
    assert say("help", imm=True) == "\r\n".join(want) + "\r\n\r\n> "


def test_help_category():
    assert say("help 戰鬥") == "【戰鬥】\r\n  kill  開打同房間的生物\r\n  use   放技能\r\n\r\n> "
    assert say("help 戰鬥 kill").startswith("【戰鬥】")          # 只看第一個字


def test_imm_category_is_only_for_imm():
    assert say("help 管理員") == NOT_FOUND
    assert say("help 管理員", imm=True).startswith("【管理員】\r\n  advance  改玩家的等級\r\n")


def test_help_command():
    want = ("kill <名字>（縮寫 k）\r\n打同房間的生物，牠會自動還手。\r\n名字只要打開頭，例如 kill do。同名的用 2.dog 指定畫面上第 2 隻。\r\n"
            "不可以打玩家，自己也不行。\r\n休息、睡覺時不能用，要先 stand。\r\n\r\n> ")
    for line in ("help kill", "help k", "help ki", "help K", "help Kill"):
        assert say(line) == want, line


def test_help_with_one_entry_for_several_commands():
    assert say("help n").startswith("north east south west up down（縮寫 n e s w u d）\r\n往那個方向走")
    assert say("help south") == say("help n")


def test_imm_commands_are_only_for_imm():
    assert say("help sla", imm=True).startswith("slay <名字>（縮寫 sla）\r\n")
    assert say("help slay") == NOT_FOUND                     # 跟打 imm 指令一樣：不是 imm 就找不到
    assert say("help advance") == NOT_FOUND
    assert say("help s", imm=True).startswith("north east south")   # s 還是 south


def test_help_not_found():
    assert say("help xyz") == NOT_FOUND
    assert say("help 魔法") == NOT_FOUND


@pytest.mark.parametrize("command, want", [
    ("kill", "k"), ("score", "sc"), ("rest", "res"), ("save", "sav"), ("slay", "sla"), ("use", "us"),
    ("help", "h"), ("look", "l"), ("lock", "loc"), ("weather", "wea"), ("unlock", "un"),
])
def test_shortest_abbreviation(command, want):
    assert help_command.shortest(command, True) == want


def test_help_is_h_and_works_while_sleeping():
    assert commands.find("h") is help_command.do_help
    assert commands.command_name("h") == "help"
    assert say("h", position=Position.SLEEPING) == "\r\n".join(SUMMARY) + "\r\n\r\n> "


def test_help_use():
    assert say("help us").startswith("use <技能> [名字]（縮寫 us）\r\n放你會的技能")
    assert say("help smash") == NOT_FOUND                    # 技能不是指令：用 skills 看
