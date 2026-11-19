"""技能的資料跟 mud_design 的技能草案（sim/skill_tree.py，design/技能/ 的 md 檔從它產生）一樣。

TREE 是給人看的欄位（名字、種類、目標、消耗、冷卻、武器、副手），MECH 是數字，TAG 是效果種類（連動用）。
還沒做的技能列在 NOT_YET（現在全部做好了）：做好一種就從這裡拿掉，這個測試就會開始比對它。
"""
import pytest

from mud import skills
from mud.area import TWO_HANDED_KINDS, WeaponKind
from mud.config import ROUND_TICKS, TICK_SECONDS
from mud.stats import Guild
from skill_tree_loader import load_skill_tree

KINDS = {"傷害": "damage", "治療": "heal", "增強": "buff", "減弱": "debuff", "控制": "control", "保護": "protect", "召喚": "summon",
         "被動": "passive"}
CONTROLS = {"暈": "stun", "凍住": "freeze", "沉默": "silence", "變慢": "slow", "失明": "blind"}   # 效果種類 → Affect.control
TARGETS = {"打一隻": "single", "一隻生物": "single", "自己人": "ally", "自己": "self", "打一群": "group", "同房間所有自己人": "allies"}
SWORD_PATHS = {"劍之公會", "戰士", "巨武", "盾衛", "刺客", "雙刃", "暗殺"}
WEAPONS = {"沒有": (), "匕首（種類 1，主手）": (WeaponKind.DAGGER,),
           "雙手武器（大劍、戰斧、戰鎚、長槍，種類 8～11）": tuple(sorted(TWO_HANDED_KINDS))}
OFFHANDS = {"不限": None, "要拿盾": "shield", "要雙持": "dual"}
NOT_YET = set()


@pytest.fixture(scope="module")
def tree():
    module = load_skill_tree()
    if module is None:
        pytest.skip("找不到 mud_design/sim/skill_tree.py")
    return module


def rows(tree):
    return [r for r in tree.TREE if r["key"] not in NOT_YET]


def test_every_skill_in_the_tree_is_here_or_not_yet(tree):
    keys = {r["key"] for r in tree.TREE}
    assert NOT_YET <= keys                                           # 拼錯的、mud_design 拿掉的
    assert {r["key"] for r in rows(tree)} <= set(skills.SKILLS)


def test_names_kinds_targets_cost_cooldown(tree):
    for r in rows(tree):
        s = skills.SKILLS[r["key"]]
        assert s.name == r["name"], r["key"]
        assert s.guild == (Guild.SWORD if r["path"] in SWORD_PATHS else Guild.STAFF), r["key"]
        assert (s.kind, s.target) == (KINDS[r["kind"]], TARGETS[r["target"]]), r["key"]
        assert (s.cost, s.cooldown) == (r["cost"] or 0.0, r["cd"] or 0), r["key"]      # 被動沒有消耗、冷卻
        assert (tuple(s.weapon_kinds), s.offhand) == (WEAPONS[r["weapon"]], OFFHANDS[r["offhand"]]), r["key"]
        assert s.starter == ((s.guild,) if r.get("fixed") else ()), r["key"]          # Lv1 的建立角色就會，其他要用程式加
        assert skills.tag(s) == tree.TAG.get(r["key"], r["name"]), r["key"]           # 效果種類（連動用）


def seconds(ticks):
    return ticks * TICK_SECONDS


def test_numbers_match_mech(tree):
    for r in rows(tree):
        s, m = skills.SKILLS[r["key"]], tree.MECH[r["key"]]
        if "dmg" in m:                                               # 傷害：比率、打幾次
            assert (s.ratio, s.hits) == (m["dmg"], m.get("hits", 1)), r["key"]
        if m.get("aoe"):                                             # 打一群、放在一群自己人上
            assert s.target in skills.GROUP_TARGETS, r["key"]
        if s.target == "group":
            assert m.get("aoe"), r["key"]
        if "taunt" in m:                                             # 挑釁：被挑釁幾秒
            assert seconds(s.affect["duration"]) == m["taunt"]["secs"], r["key"]
        if "guard" in m:                                             # 守護：幾成、幾秒
            assert (s.guard["share"], seconds(s.guard["duration"])) == (m["guard"]["pct"], m["guard"]["secs"]), r["key"]
        else:
            assert s.guard is None, r["key"]
        if "summon" in m:                                            # 召喚：種類、幾秒、比主人低幾級
            want = m["summon"]
            assert (s.summon["tier"], seconds(s.summon["duration"]), s.summon["below"]) == (
                want["tier"], want["secs"], want["lv_off"]), r["key"]
        else:
            assert s.summon is None, r["key"]
        if "silence" in m:                                           # 沉默幾秒
            assert (s.affect["control"], seconds(s.affect["duration"])) == ("silence", m["silence"]["secs"]), r["key"]
        if "burn" in m:                                              # 打中後燃燒：第一發 × ratio、跳幾次
            assert (s.dot["ratio"], s.dot["jumps"]) == (m["burn"]["ratio"], m["burn"]["jumps"]), r["key"]
        if "dot" in m:                                               # 持續扣血的減益：每跳 ＝ 這一下 × ratio
            assert (s.kind, s.ratio, s.dot["jumps"]) == ("debuff", m["dot"]["ratio"], m["dot"]["jumps"]), r["key"]
        for key in ("buff", "debuff"):                               # 加減屬性、倍率、持續多久
            if key in m:
                a = skills.make_affect(s)
                assert a.applies == {k: float(v) for k, v in m[key].get("add", {}).items()}, r["key"]
                assert a.mult == m[key].get("mult", {}), r["key"]
                assert seconds(a.duration) == m[key]["secs"], r["key"]
        if "shield" in m:
            a = skills.make_affect(s)
            assert (a.shield_pct, seconds(a.duration)) == (m["shield"]["pct"], m["shield"]["secs"]), r["key"]
        if "heal" in m:
            assert (s.ratio, s.hot) == (m["heal"], None), r["key"]
        if "hot" in m:
            assert (s.ratio, s.hot["jumps"]) == (m["hot"]["ratio"], m["hot"]["jumps"]), r["key"]
        assert s.passive == m.get("passive"), r["key"]
        assert s.lifesteal == m.get("lifesteal", 0.0), r["key"]
        assert s.opener == m.get("opener", False), r["key"]
        if "onhit" in m:                                             # 打中後的減弱（冰錐的變慢）
            assert (s.onhit["mult"], seconds(s.onhit["duration"])) == (m["onhit"]["mult"], m["onhit"]["secs"]), r["key"]
        if "stun" in m:                                              # 暈、凍住幾回合：打中後的（盾擊）或技能本身
            a = s.onhit if "dmg" in m else s.affect
            assert a["duration"] == m["stun"] * ROUND_TICKS, r["key"]
        if "onhit" not in m and "stun" not in m:
            assert s.onhit is None, r["key"]


def test_controls_carry_their_kind(tree):
    # 控制類（和打中後放控制的）：效果的 control 照效果種類（暈、凍住、沉默、變慢、失明）
    for r in rows(tree):
        s = skills.SKILLS[r["key"]]
        effect = s.onhit if s.onhit else s.affect
        if r["kind"] == "控制" or s.onhit:
            assert effect["control"] == CONTROLS[skills.tag(s)], r["key"]


def test_every_combo_is_in_the_manual(tree):
    # 連動（COMBOS）：每一個的名字都在玩家角色手冊「連動」那張表裡（combos.py 照它做，test_skill_combos.py 一個一個測）
    from pathlib import Path
    manual = (Path(__file__).resolve().parent.parent / "docs" / "玩家角色手冊.md").read_text(encoding="utf-8")
    part = manual[manual.index("### 連動"):]
    assert len(tree.COMBOS) == 21
    for path, name, _keys, _text in tree.COMBOS:
        assert f"| {path} | {name} |" in part, name
