"""選路和學技能（paths.py，設計文件 §2.6「怎麼學」，規則在玩家角色手冊「選職業」）：
資料跟 mud_design 的 skill_tree.py 一樣、每個結果代號、晚選一次補齊、換路（價錢、扣錢、忘掉舊的、清小路）、
升級自動學和提醒、稱號（score、who）、存檔、advance、skills 列出整條路和還沒選的路。
導師（真的秋風城）在 test_mentors.py。借用 test_skills.py 的區域。
"""
import math
import re

import pytest

import mud.commands as commands
from mud import combat, paths, save, skills, stats
from mud.commands import skills as skill_commands
from skill_tree_loader import load_skill_tree
from test_skills import fighter, prompt_of, say, text_of, world  # noqa: F401（world 是 fixture）

SWORD, STAFF = stats.Guild.SWORD, stats.Guild.STAFF


def knight(level=10, guild=SWORD, name="Shabu", gold=0):
    """一路升上來的玩家：5 級以上已經會公會的技能（猛擊、火焰箭，升級時學的）。"""
    p = fighter(name, level=level, guild=guild)
    p.gold = gold
    paths.learn_upto(p)
    return p


def names(p):
    return [skills.SKILLS[sid].name for sid in p.skills]


# ---- 資料 ----

def test_paths_match_the_skill_tree():
    tree = load_skill_tree()
    if tree is None:
        pytest.skip("找不到 mud_design/sim/skill_tree.py")
    want = {}
    for r in tree.TREE:
        if r["path"] in paths.PATHS:
            want.setdefault(r["path"], []).append((r["lv"], r["key"]))
    assert {name: list(p.skills) for name, p in paths.PATHS.items()} == want
    for name, folder in tree.PATHS.items():                          # 小路的資料夾在大路的資料夾底下
        parent = folder.split("/")[1].split("_")[0] if folder.count("/") == 2 else None
        guild = SWORD if folder.startswith("劍之公會") else STAFF
        assert (paths.PATHS[name].parent, paths.PATHS[name].guild) == (parent, guild), name


def test_every_route_skill_is_on_one_path():
    on_paths = [sid for p in paths.PATHS.values() for _lv, sid in p.skills]
    by_guild = [sid for steps in paths.GUILD_SKILLS.values() for _lv, sid in steps]
    route = [s.id for s in skills.SKILLS.values() if s.guild is not None and not s.starter and s.id not in by_guild]
    assert sorted(on_paths) == sorted(route) and len(on_paths) == 68


def test_guild_skills_match_the_skill_tree():
    # 公會的技能（不用選路）：skill_tree 裡 path 是公會名、不是 Lv1 的（Lv5 的猛擊、火焰箭）
    tree = load_skill_tree()
    if tree is None:
        pytest.skip("找不到 mud_design/sim/skill_tree.py")
    want = {}
    for r in tree.TREE:
        if r["path"] in ("劍之公會", "杖之公會") and r["lv"] > 1:
            want.setdefault(SWORD if r["path"] == "劍之公會" else STAFF, []).append((r["lv"], r["key"]))
    assert {g: list(steps) for g, steps in paths.GUILD_SKILLS.items()} == want


def test_change_cost():
    assert [paths.change_cost(level) for level in (10, 40, 100)] == [247, 2402, 226239]
    assert paths.change_cost(30) == stats.shown(50 * stats.GOLD_BASE * math.exp(30 / stats.GOLD_LEVELS))


# ---- 選路 ----

def test_choose_a_big_path(world):
    p = knight(level=9)
    assert paths.choose(p, "戰士") == ("too_low", [], [])
    p = knight(level=10, name="Ming")
    code, forgot, learned = paths.choose(p, "戰士")
    assert (code, forgot, [s.id for s in learned]) == ("ok", [], ["power_slash"])
    assert p.paths == ["戰士"] and paths.title(p) == "戰士"
    assert paths.choose(p, "戰士")[0] == "already"
    assert paths.choose(p, "元素")[0] == "wrong_guild"
    assert paths.choose(p, "沒有")[0] == "unknown"


def test_late_choosers_catch_up(world):
    p = knight(level=25)
    assert [s.id for s in paths.choose(p, "刺客")[2]] == ["backstab", "light_step"]


def test_choose_a_small_path(world):
    p = knight(level=45)
    assert paths.choose(p, "巨武")[0] == "not_yours"                # 還沒選大路
    paths.choose(p, "刺客")
    assert paths.choose(p, "巨武")[0] == "not_yours"                # 不在你的大路下面
    code, _forgot, learned = paths.choose(p, "暗殺")
    assert code == "ok" and [s.id for s in learned] == ["stun_strike"]
    assert p.paths == ["刺客", "暗殺"] and paths.title(p) == "暗殺"
    q = knight(level=39, name="Ming")
    paths.choose(q, "刺客")
    assert paths.choose(q, "暗殺")[0] == "too_low"


def test_changing_the_small_path_costs_and_forgets_it(world):
    p = knight(level=50, gold=10 ** 6)
    paths.choose(p, "戰士")
    paths.choose(p, "巨武")
    assert paths.price(p, "盾衛") == paths.change_cost(50) and paths.price(p, "巨武") == 0
    code, forgot, learned = paths.choose(p, "盾衛")
    assert code == "changed" and p.gold == 10 ** 6 - paths.change_cost(50)
    assert [s.id for s in forgot] == ["sweep", "heavy_mastery"] and [s.id for s in learned] == ["taunt", "shield_mastery"]
    assert p.paths == ["戰士", "盾衛"] and "power_slash" in p.skills          # 大路的不動


def test_changing_the_big_path_clears_the_small_one(world):
    p = knight(level=40, gold=10 ** 6)
    paths.choose(p, "戰士")
    paths.choose(p, "盾衛")
    code, forgot, learned = paths.choose(p, "刺客")
    assert code == "changed" and p.paths == ["刺客"]
    assert [s.id for s in forgot] == ["power_slash", "war_cry", "iron_body", "taunt"]
    assert [s.id for s in learned] == ["backstab", "light_step", "poison_blade"]
    assert paths.price(p, "暗殺") == 0                                # 小路要再選，第一次不用錢


def test_not_enough_gold(world):
    p = knight(level=20, gold=paths.change_cost(20) - 1)
    paths.choose(p, "戰士")
    assert paths.choose(p, "刺客") == ("poor", [], []) and p.paths == ["戰士"] and p.gold == paths.change_cost(20) - 1


def test_no_price_for_what_you_cannot_choose(world):
    p = knight(level=20, guild=STAFF)
    paths.choose(p, "元素")
    assert paths.price(p, "戰士") == 0 and paths.price(p, "神官") == paths.change_cost(20)


def test_titles(world):
    p = knight(level=45)
    assert paths.title(p) == ""
    paths.choose(p, "戰士")
    assert paths.title(p) == "戰士"                                  # 40 級起還沒選小路：大路名
    paths.choose(p, "盾衛")
    assert paths.title(p) == "盾衛"
    stats.set_level(p, 30)                                            # imm 降到 40 級以下：大路名
    assert paths.title(p) == "戰士"


# ---- 升級 ----

def test_level_ups_learn_and_remind(world):
    p = knight(level=9)
    stats.set_level(p, 10)
    assert paths.level_up_lines(p, 9) == [(paths.REMIND.format("職業", "公會分館"), "")]
    paths.choose(p, "戰士")
    stats.set_level(p, 21)
    assert paths.level_up_lines(p, 10) == [(paths.LEARNED, "調息"), (paths.LEARNED, "戰吼")]     # 公會的（15 級）在前、職業的在後
    stats.set_level(p, 40)
    small = (paths.REMIND.format("進階職業", "戰士公會（大街東口往南）"), "")
    assert paths.level_up_lines(p, 21) == [(paths.LEARNED, "收刀"), (paths.LEARNED, "鋼鐵之軀"), small]
    stats.set_level(p, 41)
    assert paths.level_up_lines(p, 40) == [small]                    # 還沒選小路：每升一級都提醒（使用者 2026-11-20 要的）
    paths.choose(p, "巨武")
    stats.set_level(p, 42)
    assert paths.level_up_lines(p, 41) == []                         # 選好了就不說


def test_no_path_is_reminded_every_level_up_but_not_when_going_down(world):
    p = knight(level=12)
    big = [(paths.REMIND.format("職業", "公會分館"), "")]
    stats.set_level(p, 13)
    assert paths.level_up_lines(p, 12) == big
    stats.set_level(p, 11)
    assert paths.level_up_lines(p, 13) == []                         # 降級不說


@pytest.mark.parametrize("guild, name", [(SWORD, "猛擊"), (STAFF, "火焰箭")])
def test_level_5_learns_the_guild_skill_without_a_path(world, guild, name):
    p = knight(level=4, guild=guild)
    assert [s.name for s in skills.known(p)] == [skills.SKILLS[skills.starter(guild)[0]].name]
    stats.set_level(p, 5)
    assert paths.level_up_lines(p, 4) == [(paths.LEARNED, name)]
    assert name in names(p) and paths.level_up_lines(p, 5) == []     # 學過了不再學
    stats.set_level(p, 3)
    paths.level_up_lines(p, 5)
    assert name in names(p)                                          # 降級不忘（跟路線技能一樣）


def test_skills_lists_the_guild_skill_before_level_5(world):
    p = knight(level=1)
    text = say(p, "skills")
    assert re.search(r"還沒學會（升到那一級自動學會）：\r\n  5 級 +猛擊 pummel +傷害", text)
    assert re.search(r"\r\n  15 級  調息 breath_control +被動：休息、睡覺回復 ×1.5\r\n", text)
    assert re.search(r"\r\n  25 級  收刀 sheathe +被動：整場戰鬥結束回 HP、MP、MV 各 10%\r\n", text)


class Out:
    def __init__(self):
        self.pairs = []

    def tell(self, pairs):
        self.pairs += pairs


def test_killing_your_way_up_learns_the_skill(world, monkeypatch):
    p = knight(level=19)
    paths.choose(p, "戰士")
    monkeypatch.setattr(stats, "kill_exp", lambda *a, **k: 1.5)        # 打一隻剛好升一級
    monkeypatch.setattr(stats, "exp_to_level", lambda *a, **k: 1.0)
    from test_skills import mobile
    out = Out()
    combat.reward(out, p, mobile("野狗"))
    text = "\n".join(t for reader, t in out.pairs if reader is p)
    assert p.level == 20 and "你學會了【戰吼】！" in text and "war_cry" in p.skills


def test_advance_learns_too(world):
    imm, p = knight(name="Boss"), knight(level=10, name="Ming")
    imm.imm = True
    paths.choose(p, "戰士")
    text_of(p)
    commands.command(imm, "advance ming 30")
    seen = text_of(p)
    assert "你學會了【戰吼】！" in seen and "你學會了【鋼鐵之軀】！" in seen


# ---- 畫面、存檔 ----

def test_score_and_who_show_the_title(world):
    p, ming = knight(level=12), knight(level=5, name="Ming")
    plain_who = say(ming, "who")
    assert "劍之公會]" in plain_who                                   # 大家都沒選路：畫面不變
    paths.choose(p, "戰士")
    assert "人類｜劍之公會｜戰士｜男" in say(p, "score")
    who = say(ming, "who")
    assert "劍之公會 戰士] Shabu" in who and "劍之公會     ] Ming" in who


def test_paths_are_saved(world, tmp_path, monkeypatch):
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path)
    p = knight(level=45)
    paths.choose(p, "刺客")
    paths.choose(p, "雙刃")
    save.save_player(p)
    data = save.load_data(p.name)
    assert data["paths"] == ["刺客", "雙刃"]
    assert save.player_from(data, None).paths == ["刺客", "雙刃"]
    del data["paths"]
    assert save.player_from(data, None).paths == []                  # 舊存檔：還沒選路


# ---- skills ----

def listing(p):
    skill_commands.do_skills(p, "")
    return text_of(p)


def test_skills_before_choosing_shows_where_to_go(world):
    text = listing(knight(level=5))
    assert text.endswith("\r\n\r\n10 級可以選職業（到秋風城的公會分館找導師，說出職業的名字）：\r\n"
                         "  戰士：戰士公會（大街東口往南）\r\n  刺客：盜賊公會（暗巷往南）\r\n")
    assert "猛力斬" not in text and "背刺" not in text               # 還沒選的路看不到技能
    staff = listing(knight(level=5, guild=STAFF, name="Ming"))
    assert "  元素：魔法公會（大街西口往南）\r\n  神官：牧師公會（神殿廣場往西）" in staff


def test_skills_shows_the_whole_chosen_path(world):
    p = knight(level=25)
    paths.choose(p, "戰士")
    text = listing(p)
    assert re.search(r"猛力斬 power_slash +傷害", text) and re.search(r"戰吼 war_cry +持續 60 秒", text)
    assert text.index("戰吼") < text.index("還沒學會") < text.index("鋼鐵之軀")
    assert "  30 級  鋼鐵之軀 iron_body  被動：HP +5%\r\n" in text
    assert "40 級可以選進階職業（到秋風城的公會分館找導師，說出職業的名字）：\r\n  巨武：戰士公會（大街東口往南）\r\n  盾衛：" in text
    assert "橫掃" not in text and "挑釁" not in text                  # 小路還沒選：看不到
    assert say(p, "use iron").startswith("你不會這個技能。")          # 還沒學會的不能用
    p = knight(level=40, name="Ming")
    paths.choose(p, "戰士")
    paths.choose(p, "盾衛")
    text = listing(p)
    assert re.search(r"  100 級  不倒之盾 last_stand +持續", text) and "可以選" not in text
    assert all(len(line.encode("cp950")) <= 79 for line in text.split("\r\n"))
