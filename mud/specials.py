"""生物的 special（設計文件 §4.11，規則在區域製作手冊 special）：區域作者只能挑一個名字，要做什麼寫在這裡。

打架用的（吐息、施法、咬人下毒）當成生物的傷害技能：開打後先等 SPECIAL_TICKS，之後每 SPECIAL_TICKS 對正在打的對手放一下
（Fight.join() 記時間、Fight.tick() 呼叫 fight()）。平常的（janitor、fido）跟走動一樣每 MOBILE_TICKS 做（behavior.idle() 呼叫 idle()）。
guard、executioner、cast_adept、thief、mayor、repairman 先不做（NOT_YET）：寫了沒作用，要靠還沒有的系統。
坑：fight → specials → combat → death → fight 繞一圈，所以都用 from . import 模組。
"""
import random

from . import affects, combat, damage, objects, skills
from .act import TO_CHAR, TO_ROOM, act, compose
from .area import ATTACK_NAMES, CORPSE_NPC_ITEM_TYPE, DRINK_CON_ITEM_TYPE, SPECIALS, TRASH_ITEM_TYPE, Attack
from .characters import characters
from .config import SPECIAL_TICKS

rng = random                                # spec_breath_any 挑哪一種（測試換掉）；傷害的亂數用 combat.rng，跟平砍、技能一樣

SPECIAL_RATIO = 1.8                         # special_ratio 寫 null：跟重擊一樣（設計文件 §4.11）
POISON_RATIO = 0.3                          # poison_ratio 寫 null：跟火球的燃燒一樣

# 吐息的招式名稱（C 版技能表的 noun_damage），都算龍焰傷害
BREATHS = {
    "spec_breath_acid": "酸液龍燄", "spec_breath_fire": "灼熱龍燄", "spec_breath_frost": "冰冷龍燄",
    "spec_breath_gas": "毒氣龍燄", "spec_breath_lightning": "閃電龍燄",
}
SPELL = "法術"                              # 施法的招式名稱（使用者選的：C 版的法術表不用，每個 cast 都是一下法術傷害）
BITE = ATTACK_NAMES[Attack.BITE]            # 咬人的招式名稱「利牙」（使用者選的）
CASTS = ("spec_cast_mage", "spec_cast_cleric", "spec_cast_undead", "spec_cast_psionicist", "spec_cast_judge", "spec_cast_ghost")
# 打架用的：名字 → (傷害類型 damage.TYPES, 招式名稱)。spec_breath_any 每次從 BREATHS 挑一個名稱（只差在訊息）；
# ghost 的詛咒、怕陽光先不做
FIGHTING = {
    **{name: ("dragon", noun) for name, noun in BREATHS.items()},
    "spec_breath_any": ("dragon", None),
    **{name: ("spell", SPELL) for name in CASTS},
    "spec_poison": ("spell", BITE),
}
# spec_poison 咬中、對方沒死就中毒，跟火球的燃燒一樣（skills.dot_affect）：每跳 ＝ 咬的那一下 × poison_ratio。訊息照 C 版
POISON = dict(name="劇毒", jumps=3, hurt="毒傷", off="你覺得你的病好多了。")
POISONED = "你突然覺得自己得病了。"          # 中毒的人看到（C 版 spell_poison）
IDLE = ("spec_janitor", "spec_fido")        # 平常就動作的
NOT_YET = tuple(name for name in SPECIALS if name not in FIGHTING and name not in IDLE)    # 先不做的
JANITOR_PRICE = 10                          # janitor 撿基本價格小於 10 的東西（使用者選的：裝備照點數算，不看 cost）


def in_fights(npc):
    """npc 有沒有打架用的 special（Fight.join() 看它要不要記時間）。"""
    return getattr(npc, "special", None) in FIGHTING


def fight(battle):
    """這一場的每個 tick（Fight.tick）：時間到了的生物放 special，下一次是 SPECIAL_TICKS 以後。"""
    for npc in list(battle.members):
        due = battle.special_at.get(npc)
        if due is None or battle.ticks < due or npc.fight is not battle:
            continue
        battle.special_at[npc] = battle.ticks + SPECIAL_TICKS
        if not affects.controlled(npc, affects.MUTED):     # 暈、凍住、沉默：不能放 special，時間照排（設計文件 §2.6）
            use(battle, npc)


def use(battle, npc):
    """對牠正在打的對手放一下，規則跟玩家的傷害技能一樣（設計文件 §4.11）：跟平砍一下一樣算、換傷害類型、乘 special_ratio，
    打中最低 MIN_SKILL_DAMAGE、沒打中是 0。spec_poison 咬中、對方沒死就中毒。

    「跟平砍一樣算、換傷害類型」：傷害點數用牠平常攻擊的那一種（生物有的攻擊類型點數都一樣），減傷照 special 的類型。
    不能直接用 special 那一種的點數：只會物理攻擊的生物，龍焰、法術的點數是 0，吐息會打 0。
    """
    victim = npc.fighting
    if victim is None or victim not in characters or victim.room is not npc.room or not npc.panel or not victim.panel:
        return                              # 對手跑了、死了：回合那邊會讓牠停手
    kind, noun = FIGHTING[npc.special]
    if noun is None:
        noun = rng.choice(list(BREATHS.values()))
    source = next(iter(npc.mix), "phys")    # 牠平常攻擊的類型（主的那一種）
    dmg, crit = damage.strike(npc, victim, combat.rng, kind, source=source)
    dmg *= SPECIAL_RATIO if npc.special_ratio is None else npc.special_ratio
    if dmg > 0:
        dmg = max(skills.MIN_SKILL_DAMAGE, dmg)
    if combat.land(battle, npc, victim, dmg, crit, noun, named=True) or dmg <= 0 or npc.special != "spec_poison":
        return                              # 打死了、沒咬中、不是下毒的：到此為止
    ratio = POISON_RATIO if npc.poison_ratio is None else npc.poison_ratio
    affects.add(victim, skills.dot_affect(npc.special, {**POISON, "ratio": ratio}, dmg))
    battle.tell(compose(POISONED, victim, to=TO_CHAR))


def idle(npc):
    """平常就動作的 special（behavior.idle() 每 MOBILE_TICKS 呼叫，站著、沒在打架的才會叫）。"""
    if npc.special == "spec_janitor":
        janitor(npc)
    elif npc.special == "spec_fido":
        fido(npc)


def janitor(npc):
    """撿地上第一件拿得起來的：垃圾、液體容器，或基本價格小於 JANITOR_PRICE 的東西，放進背包（訊息照 C 版 spec_janitor）。"""
    from .commands import items             # 坑：commands 會 import 戰鬥的模組，在函式裡才 import
    room = npc.room
    for obj in room.contents:
        if obj.take and not items.sealed(obj) and (obj.item_type in (TRASH_ITEM_TYPE, DRINK_CON_ITEM_TYPE)
                                                   or objects.base_price(obj) < JANITOR_PRICE):
            room.contents.remove(obj)
            npc.carrying.insert(0, obj)
            act("$n拾起了一些垃圾。", npc, to=TO_ROOM)
            return


def fido(npc):
    """吃掉地上第一具生物屍體，裡面的東西掉在地上（照 C 版 spec_fido：只有吃的那句）。"""
    room = npc.room
    corpse = next((o for o in room.contents if o.item_type == CORPSE_NPC_ITEM_TYPE), None)
    if corpse is None:
        return
    room.contents.remove(corpse)
    room.contents[0:0] = corpse.contains
    corpse.contains = []
    act("$n很兇惡地吞食了一具屍體。", npc, to=TO_ROOM)
