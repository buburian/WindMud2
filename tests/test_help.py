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


def topic(d):
    return d["topics"][0]


def topic_caught_by_command(d):
    topic(d)["names"].append("con")


def topic_name_twice(d):
    topic(d)["names"].append("STR")


def topic_named_like_category(d):
    topic(d)["names"].append("戰鬥")


def topic_unknown_category(d):
    topic(d)["category"] = "魔法"


def topic_missing_field(d):
    del topic(d)["summary"]


def topic_no_names(d):
    topic(d)["names"] = []


def topic_not_big5(d):
    topic(d)["text"].append("笑臉 😀")


def no_topics(d):
    del d["topics"]


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
    (topic_caught_by_command, "help con 會先找到指令 consider，這個名字用不到"),
    (topic_name_twice, "名字 STR 已經寫在 topics 第 1 筆了"),
    (topic_named_like_category, "名字 戰鬥 跟分類同名"),
    (topic_unknown_category, "topics 第 1 筆（屬性）：沒有「魔法」這個分類"),
    (topic_missing_field, "topics 第 1 筆 少了欄位：summary"),
    (topic_no_names, "names 不能是空的"),
    (topic_not_big5, "「😀」（U+1F600）轉不成 Big5"),
    (no_topics, "檔案最上層 少了欄位：topics"),
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

SUMMARY = [                                 # 首頁只列分類（使用者 2026-11-20 要的），指令要 help 分類 才看得到
    "說明的分類（help 分類 看這一類有哪些指令）：",
    "  移動", "  資訊", "  溝通", "  角色", "  戰鬥", "  物品", "  門", "  屬性",     # 屬性不是分類：help 屬性 直接看內容
    "知道指令的名字，也可以直接 help 指令，例如 help kill。",
]


def test_help_shows_the_categories():
    assert say("help") == "\r\n".join(SUMMARY) + "\r\n\r\n> "


def test_imm_sees_the_imm_category():
    want = SUMMARY[:-2] + ["  管理員"] + SUMMARY[-2:]
    assert say("help", imm=True) == "\r\n".join(want) + "\r\n\r\n> "
    assert "flee" not in say("help") and "advance" not in say("help", imm=True)    # 首頁不列指令


def test_help_category():
    assert say("help 戰鬥") == ("【戰鬥】\r\n  kill      開打同房間的生物\r\n  use       放技能\r\n  flee      從戰鬥中逃跑\r\n"
                              "  consider  看看打不打得過同房間的生物\r\n\r\n> ")
    assert say("help 戰鬥 kill").startswith("【戰鬥】")          # 只看第一個字


def test_imm_category_is_only_for_imm():
    assert say("help 管理員") == NOT_FOUND
    assert say("help 管理員", imm=True).startswith("【管理員】\r\n  advance    改玩家的等級\r\n")


def test_help_command():
    want = ("kill <名字>（縮寫 k）\r\n打同房間的生物，牠會自動還手。\r\n名字只要打開頭，例如 kill do。同名的用 2.dog 指定畫面上第 2 隻。\r\n"
            "不可以打玩家，自己也不行。安全區裡不能開打。\r\n休息、睡覺時不能用，要先 stand。\r\n\r\n> ")
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


# ---- 不是指令的說明（topics，help 屬性）----

def test_help_attributes():
    text = say("help 屬性")
    assert text.startswith("屬性\r\n主屬性有五項")               # 不是指令：標題沒有縮寫
    assert "CON 體質：HP、物理抗性、MV。" in text and "沒有練習點數" in text
    for line in ("help str", "help STR", "help 力量", "help 主屬性", "help 次要屬性", "help AC", "help mv"):
        assert say(line) == text, line


def test_topics_need_the_whole_name_and_commands_come_first():
    assert say("help 屬") == NOT_FOUND                     # 要打全名
    assert say("help 力") == NOT_FOUND
    assert say("help st").startswith("stand")             # 指令照舊可以縮寫
    assert say("help con").startswith("consider")         # con 是 consider 的縮寫：指令先找
    assert say("help 角色").startswith("【角色】") and "  屬性    每個屬性做什麼" in say("help 角色")


def test_score_and_train_point_to_help_attributes():
    for line in ("help score", "help train"):
        assert "屬性做什麼，看 help 屬性。" in say(line), line


def test_help_use():
    assert say("help us").startswith("use <技能> [名字]（縮寫 us）\r\n放你會的技能")
    assert say("help smash") == NOT_FOUND                    # 技能不是指令：用 skills 看
