"""技能（玩家角色手冊「技能」，設計文件 §2.6）：技能的資料、消耗、說明的數字、共用的出手函數、冷卻。

新增傷害技能只要在 SKILLS 加一筆：玩家用 use 指令放（commands/skills.py），不用加指令。
資料和消耗照 mud_design 的 balance.py（SKILLS、Model.skill_cost），tests/test_skills.py 直接比對。
現在只有傷害、打一隻；補血、增益、減益、打一群、怪物用技能、怎麼學都還沒定。
技能屬於一個公會，或屬於 imm（只有 imm 會，給管理、測試用，使用者要的）。imm 用任何技能都不扣消耗、不用等冷卻。
坑：combat → death → fight 繞一圈，這裡也用 from . import 模組。
"""
from dataclasses import dataclass

from . import combat, damage, stats
from .players import online_players
from .stats import GUILD_RESOURCE, Guild

RESOURCE_NAMES = {"mv": "MV", "mp": "MP"}   # 訊息裡的資源名稱
IMM = "imm"                                 # 技能的 owner：只有 imm 會（不是公會）


@dataclass(frozen=True)
class Skill:
    """一個技能（設計文件 §2.6 技能的組成）。"""
    id: str                     # 英文指令名
    name: str                   # 名稱，訊息寫「你使用重擊攻擊野狗」
    owner: object               # 誰會：一個 Guild（那個公會的，決定傷害類型和扣 MV 還是 MP），或 IMM（只有 imm 會、沒有消耗）
    kind: str                   # 種類：現在只有 "damage"（傷害），代號跟 balance.py 一樣
    target: str                 # 目標：現在只有 "single"（打一隻）
    hits: int                   # 用一次打幾次（攻速不影響次數）
    ratio: float                # 每一次 ＝ 主手這一下平砍的最終傷害 × ratio
    cooldown: int               # 冷卻幾秒（1 tick ＝ 1 秒），每個技能各自算
    cost: float                 # 消耗比率：乘使用者這個等級的公會標準 MV／MP
    weapon_kinds: tuple = ()    # 限用的武器種類（area.WeaponKind），空的是不限


SKILLS = {s.id: s for s in (
    Skill("smash", "重擊", Guild.SWORD, "damage", "single", 1, 1.2, 6, 0.10),
    Skill("fireball", "火球", Guild.STAFF, "damage", "single", 1, 1.2, 6, 0.10),
    Skill("thunder", "天雷", IMM, "damage", "single", 1, 10.0, 0, 0.0),     # imm 測試用的（數字是我們訂的，不是設計文件的）
)}


def damage_kind(skill, ch):
    """技能那一下的傷害類型（公會的代號就是 phys／spell）：公會的技能是技能的公會（不是角色身上的攻擊類型）；

    imm 的技能是使用的人的公會（固定寫法術的話，劍之公會的法術傷害點數是 0，會打不痛）。
    """
    return str(ch.guild if skill.owner == IMM else skill.owner)


def resource(skill):
    """扣哪一種：劍之公會的技能扣 MV（"mv"），杖之公會的扣 MP（"mp"），imm 的技能沒有（None）。"""
    return None if skill.owner == IMM else GUILD_RESOURCE[skill.owner]


def cost(skill, level):
    """每用一次扣多少（整數，說明顯示的就是扣的）：這個等級的公會標準 MV／MP × 消耗比率，.5 進位，最少 1。

    乘的是公會標準，不是自己的上限：同等級、同公會的人扣的一樣多。imm 的技能是 0。
    """
    if resource(skill) is None:
        return 0
    return max(1, stats.shown(stats.resource_standard(level, skill.owner, resource(skill)) * skill.cost))


def display_range(ch, skill):
    """skills 顯示的傷害 (最低, 最高)：還沒被抗性擋、不含爆擊。

    武器做好前（使用者選的）：傷害點數 × ratio × (1 ∓ 浮動)，跟 damage.strike() 實際的 ±20% 一樣。
    武器做好後改回設計文件的（傷害點數 ＋ 主手武器下限／上限）× ratio。
    """
    points = ch.panel.get(f"dmg_{damage_kind(skill, ch)}", 0.0) * skill.ratio
    return stats.shown(points * (1.0 - damage.DMG_VAR)), stats.shown(points * (1.0 + damage.DMG_VAR))


def known(ch):
    """ch 會的技能。暫定（怎麼學還沒定）：自己公會的技能都會；imm 另外會 imm 的技能。NPC、沒有屬性的角色沒有。"""
    guild = getattr(ch, "guild", None)
    if guild is None or not getattr(ch, "panel", None):
        return []
    imm = getattr(ch, "imm", False)
    return [s for s in SKILLS.values() if s.owner == guild or (imm and s.owner == IMM)]


def find(ch, word):
    """ch 會的技能裡，第一個 id 用 word 開頭的（跟指令一樣可以縮寫，英文不分大小寫）；找不到是 None。"""
    word = word.lower()
    return next((s for s in known(ch) if s.id.startswith(word)), None)


def free(ch):
    """ch 用技能不扣消耗、不用等冷卻：imm（使用者要的，方便測試）。"""
    return getattr(ch, "imm", False)


def affordable(ch, skill):
    """夠不夠付（使用者選的）：現在的 MV／MP 四捨五入後（跟 prompt 顯示的一樣）≥ 消耗就可以。imm 一律夠。"""
    return free(ch) or stats.shown(getattr(ch, resource(skill))) >= cost(skill, ch.level)


def weapon_ok(ch, skill):
    """主手武器的種類符不符合：沒寫 weapon_kinds 是不限。武器還沒做，手上沒有武器，有限制的技能都不能用。"""
    return not skill.weapon_kinds


def use(ch, skill, victim):
    """ch 對 victim 用 skill（能不能用由指令先檢查）：扣消耗、開始冷卻（imm 都不用）、打 hits 次。

    每一次 ＝ 平砍的一下（各自擲命中、浮動、爆擊）× ratio，類型見 damage_kind()；目標死了就不打剩下的。
    打指令當下就打，平砍照打（技能是額外的）。訊息放進那一場，打完馬上送：ch 那段是指令的回覆，別人照舊 notify。
    """
    battle = ch.fight                       # 先記住：打死生物時 die() 會把 ch.fight 清掉
    if not free(ch):
        pool = resource(skill)
        setattr(ch, pool, max(0.0, getattr(ch, pool) - cost(skill, ch.level)))    # 比的是四捨五入，扣完可能小於 0
        ch.cooldowns[skill.id] = skill.cooldown
    try:
        for _ in range(skill.hits):
            dmg, crit = damage.strike(ch, victim, combat.rng, damage_kind(skill, ch))
            if combat.land(battle, ch, victim, dmg * skill.ratio, crit, skill.name):
                break
    finally:
        battle.flush(me=ch)


def tick():
    """世界每個 tick：所有在線玩家的冷卻減 1，到 0 就能再用（掛在角色身上的定時事情放世界 tick、全部角色一起做）。"""
    for p in online_players():
        for sid in list(p.cooldowns):
            p.cooldowns[sid] -= 1
            if p.cooldowns[sid] <= 0:
                del p.cooldowns[sid]
