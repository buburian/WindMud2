"""淬火石（設計文件 §3.11，temper.py、commands/temper.py）：use 淬火石／use temper 的預覽和確定、每種不能用的訊息、
淬火後的樣子（跟 equipment.temper 一樣、綁住）、掉落（等級、種類、低 10 級、只給打死牠的玩家）、存檔、imm 給淬火石。
算法跟 balance.py 的比對在 test_equipment.py。"""
import pytest

import mud.commands as commands
from mud import combat, equipment, objects, save, stats, temper
from mud.area import MobTier
from mud.commands import temper as temper_command
from mud.commands.items import BOUND_TAG
from test_items import make, person, plain, say, the_dog, world  # noqa: F401（world 是 fixture）


class Rng:
    def __init__(self, x):
        self.x = x

    def random(self):
        return self.x


class Out:
    def __init__(self):
        self.pairs = []

    def tell(self, pairs):
        self.pairs += pairs


def stoned(level=20, stones=1):
    """有淬火石、副手拿著一面 10 級白色盾牌（隨機屬性）的玩家。"""
    p = person(level=level)
    p.temper_stones = stones
    p.equipment["offhand"] = make(3, level=10, color="white")
    return p


def first(text):
    return text.split("\r\n")[0]


# ---- use ----

@pytest.mark.parametrize("word", ["temper", "淬火石", "TEMPER"])
def test_preview_then_use(world, word):
    p = stoned()
    shield = p.equipment["offhand"]
    before = (shield.level, shield.color, list(shield.affects))
    want, _ = temper.result(shield, 20)
    after = "、".join(f"{equipment.STAT_NAMES[a.name.lower()]} {n:+d}" for a, n in want)
    seen = first(say(p, f"use {word} shield"))
    assert seen == f"【{shield.name}/shield】會變成 20 級橘色：{after}。確定的話再打一次。"   # 名字有隨機的詞綴
    assert (shield.level, shield.color, list(shield.affects)) == before and p.temper_stones == 1   # 預覽不扣、不改
    assert first(say(p, f"use {word} shield")) == f"你用掉一顆淬火石，【{shield.name}/shield】變成 20 級橘色：{after} 了。"
    assert p.temper_stones == 0 and (shield.level, shield.color, shield.affects) == (20, "orange", want)
    assert objects.bound(shield)                                     # 淬火過的綁住
    assert shield.base == {"ac": equipment.cap(20, "offhand") * equipment.ARMOR_AC}


def test_using_it_saves(world, tmp_path, monkeypatch):
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path)
    p = stoned(stones=3)
    say(p, "use temper shield")
    say(p, "use temper shield")
    data = save.load_data(p.name)
    assert data["temper_stones"] == 2 and data["equipment"]["offhand"]["color"] == "orange"


def test_changes_in_between_preview_again(world):
    p = stoned(stones=2)
    say(p, "use temper shield")
    stats.set_level(p, 21)                                           # 中間升級了：重新預覽，不扣
    assert "會變成 21 級橘色" in say(p, "use temper shield") and p.temper_stones == 2
    p.equipment["body"] = make(7, level=10, color="white")           # 預覽了別件，再打盾牌：重新預覽
    say(p, "use temper armor")
    assert "會變成" in say(p, "use temper shield") and p.temper_stones == 2


@pytest.mark.parametrize("setup, line, want", [
    (lambda p: setattr(p, "temper_stones", 0), "use temper shield", temper_command.NONE_LEFT),
    (lambda p: None, "use temper", temper_command.WHICH),
    (lambda p: None, "use temper sword", temper_command.NOT_WORN),
    (lambda p: p.carrying.insert(0, make(7, level=10, color="white")), "use temper armor", temper_command.NOT_WORN),   # 背包裡的不算
    (lambda p: p.equipment.update(offhand=make(3, level=30, color="white")), "use temper shield", "【{}/shield】的等級比你高，不能淬火。"),
    (lambda p: p.equipment.update(offhand=make(3, level=20, color="orange")), "use temper shield", "【{}/shield】已經是你這個等級的橘色了。"),
    (lambda p: p.equipment.update(offhand=make(3, level=10, color="gray")), "use temper shield", "【{}/shield】不能淬火。"),
])
def test_refusals(world, setup, line, want):
    p = stoned()
    setup(p)
    assert first(say(p, line)) == want.format(p.equipment["offhand"].name)     # 名字有隨機的詞綴


def test_not_while_fighting(world):
    p = stoned()
    p.fighting = the_dog()
    assert first(say(p, "use temper shield")) == temper_command.FIGHTING
    p.fighting = None


def test_the_name_is_not_abbreviated(world):
    # 要打完整的「淬火石」或「temper」：use t、use temp 照舊是技能（不然會搶走技能的縮寫）
    p = stoned()
    assert first(say(p, "use temp shield")) == "你不會這個技能。" and p.temper_pending is None


def test_bound_tag_shows(world):
    p = stoned()
    say(p, "use temper shield")
    say(p, "use temper shield")
    assert BOUND_TAG in say(p, "equipment")


# ---- 掉落 ----

def mob(level, tier):
    dog = the_dog()
    dog.level, dog.tier = level, tier
    return dog


@pytest.mark.parametrize("level, tier, roll, player_level, dropped", [
    (15, MobTier.NORMAL, 0.0049, 15, True),
    (15, MobTier.NORMAL, 0.0051, 15, False),                         # 一般怪 0.5%
    (20, MobTier.ELITE, 0.0199, 20, True),                           # 菁英 2%
    (20, MobTier.BOSS, 0.0499, 20, True),                            # 首領 5%
    (20, MobTier.BOSS, 0.0501, 20, False),
    (20, MobTier.TRASH, 0.0, 20, False),                             # 垃圾怪不掉
    (14, MobTier.BOSS, 0.0, 14, False),                              # 15 級以下不掉
    (20, MobTier.BOSS, 0.0, 30, False),                              # 比玩家低 10 級（含）不掉
    (20, MobTier.BOSS, 0.0, 29, True),
])
def test_drop(world, monkeypatch, level, tier, roll, player_level, dropped):
    monkeypatch.setattr(temper, "rng", Rng(roll))
    p = person(level=player_level)
    out = Out()
    temper.drop(out, p, mob(level, tier))
    assert p.temper_stones == int(dropped)
    assert ([text for _, text in out.pairs] == [objects.colorize(temper.GOT)]) == dropped


def test_killing_gives_it_after_the_exp(world, monkeypatch):
    monkeypatch.setattr(temper, "rng", Rng(0.0))
    p, dog = person(level=20), mob(20, MobTier.NORMAL)
    out = Out()
    combat.slain(out, p, dog)
    texts = [text for who, text in out.pairs if who is p]
    assert p.temper_stones == 1 and any("經驗" in t for t in texts)
    assert texts.index(objects.colorize(temper.GOT)) > next(i for i, t in enumerate(texts) if "經驗" in t)


# ---- 存檔、imm ----

def test_old_saves_have_none(world, tmp_path, monkeypatch):
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path)
    p = person()
    p.temper_stones = 4
    save.save_player(p)
    data = save.load_data(p.name)
    assert save.player_from(data, None).temper_stones == 4
    del data["temper_stones"]
    assert save.player_from(data, None).temper_stones == 0


def test_givemoney_temper(world, tmp_path, monkeypatch):
    monkeypatch.setattr(save, "PLAYER_DIR", tmp_path)
    boss, ming = person("Boss", imm_=True), person("Ming")
    plain(ming)
    assert first(say(boss, "givemoney ming 3 temper")) == "你給了Ming【3】顆淬火石。"
    assert ming.temper_stones == 3 and ming.gold == 0 and "Boss給你【3】顆淬火石。" in plain(ming)
