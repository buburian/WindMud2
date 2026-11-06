"""技能（玩家角色手冊「技能」，設計文件 §2.6）：技能的資料、消耗、說明的數字、共用的出手函數、冷卻。

新增技能只要在 SKILLS 加一筆：玩家用 use 指令放（commands/skills.py），不用加指令。
傷害技能的資料和消耗照 mud_design 的 balance.py（SKILLS、Model.skill_cost），tests/test_skills.py 直接比對。
現在有傷害（打一隻）和增益（把 affect 放在自己或同房間的玩家身上，不開打）；補血、減益、打一群、怪物用技能都還沒定。
誰會（使用者定的，技能自己設計）：starter 寫的公會建立角色就會；其他的要用程式加（learn：之後的學習、技能書，現在是 imm 的 sset）。
會的技能存在角色的 skills（存檔）。imm_only 的只有 imm 會（imm 自動會，不能給別人）。imm 用任何技能都不扣消耗、不用等冷卻。
坑：combat → death → fight 繞一圈，這裡也用 from . import 模組。
"""
import copy
from dataclasses import dataclass, field

from . import affects, combat, damage, stats
from .act import TO_CHAR, TO_NOTVICT, TO_ROOM, TO_VICT, act
from .players import online_players
from .stats import GUILD_RESOURCE, Guild

RESOURCE_NAMES = {"mv": "MV", "mp": "MP"}   # 訊息裡的資源名稱


@dataclass(frozen=True)
class Skill:
    """一個技能（設計文件 §2.6 技能的組成）。"""
    id: str                     # 英文指令名
    name: str                   # 名稱，訊息寫「你使用重擊攻擊野狗」
    guild: object               # 哪個公會的路數（Guild）：決定傷害類型、扣 MV 還是 MP、消耗用哪個公會標準；不是誰會。
                                # None：傷害類型照使用的人的公會、沒有消耗（imm 的技能）
    kind: str                   # 種類："damage"（傷害，代號跟 balance.py 一樣）、"buff"（增益：放 affect）
    target: str                 # 目標："single"（打一隻）、"ally"（自己或同房間的玩家）
    hits: int                   # 用一次打幾次（攻速不影響次數）
    ratio: float                # 每一次 ＝ 主手這一下平砍的最終傷害 × ratio
    cooldown: int               # 冷卻幾秒（1 tick ＝ 1 秒），每個技能各自算
    cost: float                 # 消耗比率：乘使用者這個等級的公會標準 MV／MP
    weapon_kinds: tuple = ()    # 限用的武器種類（area.WeaponKind），空的是不限
    starter: tuple = ()         # 建立角色就會的公會；空的是要用程式加（learn）
    imm_only: bool = False      # 只有 imm 會：imm 自動會，不能給別人
    affect: dict = field(default=None, hash=False)  # 增益技能放上去的效果：affects.Affect 的欄位


SKILLS = {s.id: s for s in (
    Skill("smash", "重擊", Guild.SWORD, "damage", "single", 1, 1.2, 6, 0.10, starter=(Guild.SWORD,)),
    Skill("fireball", "火球", Guild.STAFF, "damage", "single", 1, 1.2, 6, 0.10, starter=(Guild.STAFF,)),
    Skill("thunder", "天雷", None, "damage", "single", 1, 10.0, 0, 0.0, imm_only=True),   # imm 測試用的（數字是我們訂的，不是設計文件的）
    # 增益：之後教學區的 NPC 放在玩家身上的（使用者定的，數字是使用者給的）：每 3 秒補 HP 上限的 10%、主屬性各 +3，3600 秒，死掉後還在
    Skill("gift", "餽贈", None, "buff", "ally", 0, 0.0, 0, 0.0, affect=dict(
        source="gift", name="餽贈", duration=3600, periodic_pct={"hp": 0.10},
        applies={k: 3.0 for k in stats.PRIMARY_KEYS}, keep_on_death=True, off_message="你身上的【餽贈】消失了。")),
)}


def damage_kind(skill, ch):
    """技能那一下的傷害類型（公會的代號就是 phys／spell）：技能的公會（不是使用的人的公會，也不是角色身上的攻擊類型）；

    沒有公會的（imm 的技能）是使用的人的公會（固定寫法術的話，劍之公會的法術傷害點數是 0，會打不痛）。
    """
    return str(ch.guild if skill.guild is None else skill.guild)


def resource(skill):
    """扣哪一種：劍之公會的技能扣 MV（"mv"），杖之公會的扣 MP（"mp"），沒有公會的（imm 的技能）沒有（None）。"""
    return None if skill.guild is None else GUILD_RESOURCE[skill.guild]


def cost(skill, level):
    """每用一次扣多少（整數，說明顯示的就是扣的）：這個等級的公會標準 MV／MP × 消耗比率，.5 進位，最少 1。

    乘的是技能的公會的標準，不是自己的上限：同等級的人扣的一樣多。imm 的技能是 0。
    """
    if resource(skill) is None:
        return 0
    return max(1, stats.shown(stats.resource_standard(level, skill.guild, resource(skill)) * skill.cost))


def display_range(ch, skill):
    """skills 顯示的傷害 (最低, 最高)：還沒被抗性擋、不含爆擊。

    拿主手武器：設計文件的（傷害點數 ＋ 主手武器下限／上限）× ratio。
    空手（使用者選的）：傷害點數 × ratio × (1 ∓ 浮動)，跟 damage.strike() 實際的 ±20% 一樣。
    """
    points = ch.panel.get(f"dmg_{damage_kind(skill, ch)}", 0.0)
    weapon = damage.weapon_in(ch, 0)
    if weapon is not None:
        return (stats.shown((points + weapon.base["dmg_min"]) * skill.ratio),
                stats.shown((points + weapon.base["dmg_max"]) * skill.ratio))
    points *= skill.ratio
    return stats.shown(points * (1.0 - damage.DMG_VAR)), stats.shown(points * (1.0 + damage.DMG_VAR))


def known(ch):
    """ch 會的技能，照 SKILLS 的順序：ch.skills 裡有的，imm 另外會 imm_only 的。NPC、沒有屬性的角色沒有。

    存檔裡有、SKILLS 已經拿掉的技能 id 不算（留在 ch.skills 裡不管）。
    """
    if not getattr(ch, "panel", None):
        return []
    mine, imm = getattr(ch, "skills", []), getattr(ch, "imm", False)
    return [s for s in SKILLS.values() if (imm if s.imm_only else s.id in mine)]


def starter(guild):
    """這個公會建立角色就會的技能 id（建立角色、舊存檔補上用）。"""
    return [s.id for s in SKILLS.values() if guild in s.starter]


def learn(ch, skill):
    """ch 學會 skill（之後的學習、技能書、imm 的 sset 都呼叫它）。回傳學了沒：已經會、imm_only 的不加。"""
    if skill.imm_only or skill.id in ch.skills:
        return False
    ch.skills.append(skill.id)
    return True


def forget(ch, skill):
    """ch 忘掉 skill。回傳本來會不會。"""
    if skill.id not in ch.skills:
        return False
    ch.skills.remove(skill.id)
    return True


def find(ch, word):
    """ch 會的技能裡，第一個 id 用 word 開頭的（跟指令一樣可以縮寫，英文不分大小寫）；找不到是 None。"""
    word = word.lower()
    return next((s for s in known(ch) if s.id.startswith(word)), None)


def free(ch):
    """ch 用技能不扣消耗、不用等冷卻：imm（使用者要的，方便測試）。"""
    return getattr(ch, "imm", False)


def affordable(ch, skill):
    """夠不夠付（使用者選的）：現在的 MV／MP 四捨五入後（跟 prompt 顯示的一樣）≥ 消耗就可以。imm、沒有消耗的技能一律夠。"""
    return free(ch) or resource(skill) is None or stats.shown(getattr(ch, resource(skill))) >= cost(skill, ch.level)


def weapon_ok(ch, skill):
    """主手武器的種類符不符合：沒寫 weapon_kinds 是不限；有寫的話主手要拿那種武器（空手不行）。"""
    if not skill.weapon_kinds:
        return True
    weapon = damage.weapon_in(ch, 0)
    return weapon is not None and weapon.weapon_kind in skill.weapon_kinds


def pay(ch, skill):
    """扣消耗、開始冷卻（imm 都不用）。沒有消耗的不扣、冷卻 0 的不設（所以生物也能用這種技能）。"""
    if free(ch):
        return
    pool = resource(skill)
    if pool is not None:
        setattr(ch, pool, max(0.0, getattr(ch, pool) - cost(skill, ch.level)))    # 比的是四捨五入，扣完可能小於 0
    if skill.cooldown:
        ch.cooldowns[skill.id] = skill.cooldown


def use(ch, skill, victim):
    """ch 對 victim 用 skill（能不能用由指令先檢查）：扣消耗、開始冷卻，增益技能放效果（buff()），傷害技能打 hits 次。

    每一次 ＝ 平砍的一下（各自擲命中、浮動、爆擊）× ratio，類型見 damage_kind()；目標死了就不打剩下的。
    打指令當下就打，平砍照打（技能是額外的）。訊息放進那一場，打完馬上送：ch 那段是指令的回覆，別人照舊 notify。
    """
    pay(ch, skill)
    if skill.kind == "buff":
        buff(ch, skill, victim)
        return
    battle = ch.fight                       # 先記住：打死生物時 die() 會把 ch.fight 清掉
    try:
        for _ in range(skill.hits):
            dmg, crit = damage.strike(ch, victim, combat.rng, damage_kind(skill, ch))
            if combat.land(battle, ch, victim, dmg * skill.ratio, crit, skill.name):
                break
    finally:
        battle.flush(me=ch)


def buff(ch, skill, target):
    """增益技能：把 skill.affect 放到 target 身上（同一個來源是覆蓋：時間回到滿的），送訊息。

    不用打架、不開打：NPC 也能直接呼叫 use(npc, 技能, 玩家)（之後教學區的 NPC 用）。
    """
    affects.add(target, affects.Affect(**copy.deepcopy(skill.affect)))   # 每次一份新的：dict 不跟技能的資料共用
    if target is ch:
        act("你對自己施展了【$t】。", ch, t=skill.name, to=TO_CHAR)
        act("$n對自己施展了【$t】。", ch, t=skill.name, to=TO_ROOM)
    else:
        act("你對$N施展了【$t】。", ch, target, t=skill.name, to=TO_CHAR)
        act("$n對你施展了【$t】。", ch, target, t=skill.name, to=TO_VICT)
        act("$n對$N施展了【$t】。", ch, target, t=skill.name, to=TO_NOTVICT)


def tick():
    """世界每個 tick：所有在線玩家的冷卻減 1，到 0 就能再用（掛在角色身上的定時事情放世界 tick、全部角色一起做）。"""
    for p in online_players():
        for sid in list(p.cooldowns):
            p.cooldowns[sid] -= 1
            if p.cooldowns[sid] <= 0:
                del p.cooldowns[sid]
