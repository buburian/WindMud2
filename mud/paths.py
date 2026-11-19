"""選路和學技能（設計文件 §2.6「怎麼學」，使用者 2026-11-19 定的，規則在玩家角色手冊「選路」）。

- Lv10 在自己公會的分館找導師選大路（戰士、刺客、元素、神官），選了馬上學會這條路到現在等級的技能（晚選的一次補齊）。
- Lv40 回同一間分館選這條大路下面的一條小路。
- 選好路以後，升級自動學會那一級的技能（combat.reward、imm 的 advance 呼叫 level_up_lines()、learn_upto()）。
- 換路要花金幣（change_cost()：打 50 隻同級一般怪的錢，使用者選的）；舊路的技能全部忘掉，新路的照現在的等級補齊。
- 稱號是走的路（title()）：Lv10～39 是大路名，Lv40 起是小路名（還沒選小路就是大路名）。
選路是跟導師說話（areas/midgaard/ 的四個導師腳本），腳本用 script_api 的 path()、subpath()、path_price()、choose_path()。
選了的路存在 Player.paths（[大路] 或 [大路, 小路]，存檔）。技能資料照 mud_design 的 sim/skill_tree.py（tests/test_paths.py 比對）。
"""
import math
from dataclasses import dataclass

from . import skills, stats
from .area import MobTier
from .stats import Guild

BIG_LEVEL, SMALL_LEVEL = 10, 40             # 幾級可以選大路、小路
CHANGE_KILLS = 50                           # 換路的價錢：打幾隻同級一般怪的金幣（使用者選的）


@dataclass(frozen=True)
class Path:
    name: str                               # 路名（也是稱號、跟導師說的那個字）
    guild: Guild                            # 哪個公會的
    parent: str                             # 小路接在哪條大路下面；大路是 None
    hall: int                               # 導師站的房間（分館的入口）
    where: str                              # skills 寫的分館在哪
    skills: tuple                           # ((等級, 技能 id), ...)


_HALLS = {                                  # 大路 → (分館的入口, 在哪)：小路跟著大路的分館
    "戰士": (3021, "戰士公會（大街東口往南）"), "刺客": (3027, "盜賊公會（暗巷往南）"),
    "元素": (3017, "魔法公會（大街西口往南）"), "神官": (3004, "牧師公會（神殿廣場往西）"),
}


def _path(name, guild, parent, *skill_ids):
    hall, where = _HALLS[parent or name]
    first = SMALL_LEVEL if parent else BIG_LEVEL
    return Path(name, guild, parent, hall, where, tuple((first + 10 * i, sid) for i, sid in enumerate(skill_ids)))


S, M = Guild.SWORD, Guild.STAFF
PATHS = {p.name: p for p in (
    _path("戰士", S, None, "power_slash", "war_cry", "iron_body"),
    _path("巨武", S, "戰士", "sweep", "heavy_mastery", "whirlwind", "berserk", "quake", "sky_rend", "cataclysm"),
    _path("盾衛", S, "戰士", "taunt", "shield_mastery", "guard", "shield_bash", "challenge", "bulwark", "last_stand"),
    _path("刺客", S, None, "backstab", "light_step", "poison_blade"),
    _path("雙刃", S, "刺客", "twin_slash", "dual_mastery", "flurry", "blade_spin", "lethal_rhythm", "hundred_cuts", "blade_dance"),
    _path("暗殺", S, "刺客", "stun_strike", "expose_weakness", "garrote", "deathblow", "smoke_bomb", "cripple", "shadow_bind"),
    _path("元素", M, None, "lightning_bolt", "erosion", "slow"),
    _path("烈焰", M, "元素", "flame_wave", "ignite", "fire_rain", "blast", "embers", "fire_pillar", "inferno"),
    _path("寒冰", M, "元素", "ice_shard", "freeze", "chill", "frost_ring", "blizzard", "glacier_crash", "absolute_zero"),
    _path("神官", M, None, "heal", "bless", "renew"),
    _path("治療", M, "神官", "flash_heal", "holy_shield", "mass_heal", "greater_heal", "divine_favor", "wellspring", "miracle"),
    _path("詛咒", M, "神官", "weaken", "corrode", "raise_skeleton", "curse", "drain_life", "plague", "death_knight"),
)}


def big(p):
    """p 選的大路名，沒選是 None。"""
    return p.paths[0] if getattr(p, "paths", None) else None


def small(p):
    """p 選的小路名，沒選是 None。"""
    return p.paths[1] if len(getattr(p, "paths", [])) > 1 else None


def title(p):
    """稱號：Lv40 起是小路名，Lv10 起是大路名（還沒選小路就是大路名）；沒選路是空的。"""
    if small(p) and p.level >= SMALL_LEVEL:
        return small(p)
    return big(p) if big(p) and p.level >= BIG_LEVEL else ""


def chosen_skills(p):
    """p 選的路上全部的技能：[(等級, Skill)]，大路在前、小路在後（skills 列出來用）。"""
    return [(lv, skills.SKILLS[sid]) for name in getattr(p, "paths", []) for lv, sid in PATHS[name].skills]


def learn_upto(p):
    """學會選的路上等級夠的技能（晚選的一次補齊、升級自動學）。回傳新學會的 [Skill]。"""
    return [s for lv, s in chosen_skills(p) if lv <= p.level and skills.learn(p, s)]


def forget_path(p, name):
    """忘掉 name 這條路的技能。回傳忘掉的 [Skill]。"""
    return [skills.SKILLS[sid] for _lv, sid in PATHS[name].skills if skills.forget(p, skills.SKILLS[sid])]


def change_cost(level):
    """換路的價錢：這個等級的一般怪平均掉的金幣 × CHANGE_KILLS（10 級約 250、40 級約 2400、100 級約 22 萬）。"""
    return stats.shown(CHANGE_KILLS * stats.GOLD_BASE * math.exp(level / stats.GOLD_LEVELS) * stats.gold_ratio(MobTier.NORMAL))


def is_change(p, name):
    """選 name 是不是換路（已經選了同一層的另一條）。"""
    path = PATHS[name]
    mine = big(p) if path.parent is None else small(p)
    return mine is not None and mine != name


def refused(p, name):
    """p 不能選 name 的原因（結果代號，見 choose()），可以選是 None。不看錢。"""
    path = PATHS.get(name)
    if path is None:
        return "unknown"
    if path.guild != p.guild:
        return "wrong_guild"
    if p.level < (BIG_LEVEL if path.parent is None else SMALL_LEVEL):
        return "too_low"
    if path.parent is not None and big(p) != path.parent:
        return "not_yours"
    if name in getattr(p, "paths", []):
        return "already"
    return None


def price(p, name):
    """選 name 要多少金幣：換路是 change_cost()；第一次選、或根本不能選（refused）是 0。"""
    return change_cost(p.level) if refused(p, name) is None and is_change(p, name) else 0


def choose(p, name):
    """p 選 name 這條路（導師的腳本呼叫）。回傳 (結果代號, 忘掉的 [Skill], 學會的 [Skill])：
    ok 選好了、changed 換好了、too_low 等級不夠、wrong_guild 不是你公會的路、not_yours 小路不在你的大路下面（或還沒選大路）、
    already 已經是這條、poor 換路的錢不夠、unknown 沒有這條路。
    換大路：舊的大路、小路都忘掉，小路清掉要再選。換小路：只忘掉舊的小路。
    """
    code = refused(p, name)
    if code:
        return code, [], []
    cost = price(p, name)
    if p.gold < cost:
        return "poor", [], []
    p.gold -= cost
    forgot = []
    if cost:
        parent = PATHS[name].parent
        for old in (p.paths if parent is None else p.paths[1:]):
            forgot += forget_path(p, old)
    p.paths = [name] if PATHS[name].parent is None else [p.paths[0], name]
    return ("changed" if cost else "ok"), forgot, learn_upto(p)


LEARNED = "{Y你學會了【$t】！{x"
FORGOT = "你忘掉了【$t】。"
REMIND = "你可以選{}了：到秋風城的{}找導師（打 skills 看）。"


def level_up_lines(p, old_level):
    """升級之後（combat.reward、advance）：自動學會的技能，和剛到 10 級、40 級還沒選路的提醒。回傳 [(格式, $t)]。"""
    lines = [(LEARNED, s.name) for s in learn_upto(p)]
    if old_level < BIG_LEVEL <= p.level and big(p) is None:
        lines.append((REMIND.format("路", "公會分館"), ""))
    elif old_level < SMALL_LEVEL <= p.level and big(p) and small(p) is None:
        lines.append((REMIND.format("小路", PATHS[big(p)].where), ""))
    return lines


def hint_lines(p):
    """skills 最下面：還沒選大路，寫可以選的兩條大路和分館；選了大路還沒選小路，寫兩條小路。都選了是空的（看不到沒選的路的技能，使用者要的）。"""
    guild = getattr(p, "guild", None)
    if guild is None:
        return []
    if big(p) is None:
        options, head = [q for q in PATHS.values() if q.parent is None and q.guild == guild], f"{BIG_LEVEL} 級可以選路"
    elif small(p) is None:
        options, head = [q for q in PATHS.values() if q.parent == big(p)], f"{SMALL_LEVEL} 級可以選小路"
    else:
        return []
    return [head + "（到秋風城的公會分館找導師，跟他說路名）："] + [f"  {q.name}：{q.where}" for q in options]
