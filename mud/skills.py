"""技能（玩家角色手冊「技能」，設計文件 §2.6）：技能的資料、消耗、說明的數字、共用的出手函數、冷卻。

新增技能只要在 SKILLS 加一筆：玩家用 use 指令放（commands/skills.py），不用加指令。
傷害技能的資料和消耗照 mud_design 的 balance.py（SKILLS、Model.skill_cost），tests/test_skills.py 直接比對。
技能的種類（設計文件 §2.6，mud_design 2026-11-19 的技能草案，數字在 mud_design 的 sim/skill_tree.py，tests/test_skill_tree.py 比對）：
傷害（打一隻）、補血（自己或同房間的玩家，不開打）、增益（把 affect 放在自己或同房間的玩家身上，不開打）、
減益（把 affect 放在一隻生物身上，會開打；持續扣血的要擲命中）、控制（擲命中，打中才放：暈、凍住、沉默、變慢，apply_effect）、
保護（挑釁：怪改打你；守護：替人擋，protect.py）、被動（學了就一直有效，stats.passives）。打一群見 share()。召喚、連動之後做；怪物用技能還沒定。
誰會（使用者定的，技能自己設計）：starter 寫的公會建立角色就會；其他的要用程式加（learn：之後的學習、技能書，現在是 imm 的 sset）。
會的技能存在角色的 skills（存檔）。imm_only 的只有 imm 會（imm 自動會，不能給別人）。imm 用任何技能都不扣消耗、不用等冷卻。
坑：combat → death → fight 繞一圈，這裡也用 from . import 模組。
"""
import copy
import math
from dataclasses import dataclass, field

from . import affects, combat, combos, damage, light, protect, stats, stealth, summons
from .act import TO_CHAR, TO_NOTVICT, TO_ROOM, TO_VICT, act, compose
from .area import TWO_HANDED_KINDS, AffectFlag, MobTier, WeaponKind
from .characters import characters, in_room
from .config import AFFECT_PULSE_TICKS
from .npcs import Npc
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
    kind: str                   # 種類（KIND_NAMES）："damage"（傷害，代號跟 balance.py 一樣）、"heal"（補血）、"buff"（增益：放 affect）、
                                # "debuff"（減益：放 affect 在生物身上，會開打）、"control"（控制：擲命中才放；hits 不是 0 的先打再放 onhit）、
                                # "protect"（保護：挑釁、守護）、"summon"（召喚：叫一隻生物幫你打）、"passive"（被動：學了就有，不用放）
    target: str                 # 目標："single"（一隻生物）、"ally"（自己或同房間的玩家）、"self"（只有自己）
    hits: int                   # 用一次打幾次（攻速不影響次數）
    ratio: float                # 傷害：每一次 ＝ 主手這一下平砍的最終傷害 × ratio；持續扣血的減益：每跳 ＝ 這一下 × ratio；
                                # 補血：（法術傷害點數 ＋ 主手武器基本傷害）× ratio（heal_amount），持續補血是每跳
    cooldown: int               # 冷卻幾秒（1 tick ＝ 1 秒），每個技能各自算
    cost: float                 # 消耗比率：乘使用者這個等級的公會標準 MV／MP
    weapon_kinds: tuple = ()    # 限用的武器種類（area.WeaponKind），空的是不限
    starter: tuple = ()         # 建立角色就會的公會；空的是要用程式加（learn）
    imm_only: bool = False      # 只有 imm 會：imm 自動會，不能給別人
    affect: dict = field(default=None, hash=False)  # 增益技能放上去的效果：affects.Affect 的欄位；source、name 沒寫就用技能的 id、名稱（make_affect）
    dot: dict = field(default=None, hash=False)     # 打中後留在目標身上的持續傷害（dot_affect）：name、ratio（每跳 ＝ 第一發 × ratio）、jumps（跳幾次）、hurt（訊息的動詞）
    cast_text: tuple = ()       # 減益放上去時的訊息（照 C 版）：(對象看到的, 同房間的人看到的)，$n 是對象；沒寫用 CAST_LINES
    offhand: str = None         # 副手的條件（OFFHAND_NEEDS）：None 不限、"shield" 要拿盾、"dual" 要雙持
    tag: str = None             # 效果種類（連動用，設計文件 §2.6）：放出去的效果帶著它；None 是技能名稱
    lifesteal: float = 0.0      # 吸血：打中的那一下，傷害的幾成補回自己（補到上限）
    opener: bool = False        # 只能開打前用：自己和目標都還沒在打架才能用
    onhit: dict = field(default=None, hash=False)   # 傷害技能打中、目標沒死時放在牠身上的效果（Affect 的欄位，冰錐的變慢）
    hot: dict = field(default=None, hash=False)     # 持續補血：jumps（跳幾次）；每跳 ＝ 補血的量（放的時候算好、擲一次爆擊）
    passive: dict = field(default=None, hash=False)  # 被動：倍率（stats.multiply 的代號 → 倍數，"shield_ac" 是盾的 AC）
    guard: dict = field(default=None, hash=False)   # 替人擋（protect.py）：share（幾成改由你承受）、duration（幾個 tick）
    summon: dict = field(default=None, hash=False)  # 召喚（summons.py）：tier（種類）、below（比主人低幾級）、duration（幾個 tick）
    sure: bool = False          # 必中、必定爆擊（設計文件 §2.6，2026-11-20 使用者定的）：不擲命中、一定爆擊，比率降到平均傷害不變
    # 不是打架用的被動（設計文件 §2.6 的 Lv15、Lv25 公會被動，2026-11-20 使用者定的：讓玩家少休息）；passive 是空的
    rest_regen: float = 1.0     # 休息、睡覺時的回復 × 這個（stats.regen，跟吃喝的加倍疊在一起）
    fight_end: float = 0.0      # 整場戰鬥結束時 HP、MP、MV 各回上限的幾成（fight_ended）


SKILLS = {s.id: s for s in (
    # 重擊、火球必中、必定爆擊（2026-11-20 使用者定，玩家反映重擊常 miss）：比率從 1.8／1.2 降到打同級一般怪的平均傷害不變（balance.py）
    Skill("smash", "重擊", Guild.SWORD, "damage", "single", 1, 0.95, 6, 0.10, starter=(Guild.SWORD,), sure=True),
    Skill("fireball", "火球", Guild.STAFF, "damage", "single", 1, 0.63, 6, 0.10, starter=(Guild.STAFF,), tag="燃燒",
          dot=dict(name="燃燒", ratio=0.3, jumps=3, hurt="燒傷"), sure=True),   # 燃燒：使用者定的，每 3 秒一次、共 3 次，每次第一發的 30%
    Skill("thunder", "天雷", None, "damage", "single", 1, 10.0, 0, 0.0, imm_only=True),   # imm 測試用的（數字是我們訂的，不是設計文件的）
    # 增益：之後教學區的 NPC 放在玩家身上的（使用者定的，數字是使用者給的）：每 3 秒補 HP 上限的 10%、主屬性各 +3，3600 秒，死掉後還在
    Skill("gift", "餽贈", None, "buff", "ally", 0, 0.0, 0, 0.0, affect=dict(
        duration=3600, periodic_pct={"hp": 0.10},
        applies={k: 3.0 for k in stats.PRIMARY_KEYS}, keep_on_death=True)),
    # 增益：護盾（使用者定的，數字是使用者給的）：HP 上限 120% 的護盾、10 秒；要用程式加，不扣消耗、沒有冷卻
    Skill("aegis", "天護", None, "buff", "ally", 0, 0.0, 0, 0.0, affect=dict(duration=10, shield_pct=1.2)),
    # 增益：帶旗標的（使用者定的：30 分鐘；用程式加，不扣消耗、沒有冷卻）：進得去空中、要船的水、水底（terrain.py）。消失的訊息照 C 版
    Skill("fly", "飛翔術", None, "buff", "ally", 0, 0.0, 0, 0.0, affect=dict(
        duration=1800, flags=AffectFlag.FLYING, off_message="你的腳緩慢的降回地面。")),
    Skill("breathe", "水中呼吸術", None, "buff", "ally", 0, 0.0, 0, 0.0, affect=dict(
        duration=1800, flags=AffectFlag.GILLS, off_message="你不能在水下呼吸了。")),
    # 看不見的人和光圈（使用者 2026-11-17 定的：跟飛翔術一樣，用程式加、不扣消耗、沒有冷卻、30 分鐘）。名字、消失的訊息照 C 版。
    # 加在最後：use 找第一個用打的字開頭的技能，原本的縮寫才不會變
    Skill("invis", "隱身術", None, "buff", "ally", 0, 0.0, 0, 0.0, affect=dict(
        duration=1800, flags=AffectFlag.INVISIBLE, off_message="你不再隱形了。")),
    Skill("hide", "藏匿技巧", None, "buff", "self", 0, 0.0, 0, 0.0, affect=dict(
        duration=1800, flags=AffectFlag.HIDE, off_message="你藏匿的效果消失了!!")),
    Skill("pass_door", "穿牆術", None, "buff", "self", 0, 0.0, 0, 0.0, affect=dict(
        duration=1800, flags=AffectFlag.PASS_DOOR, off_message="你覺得你的身體無法再穿透物品了。")),
    Skill("sanctuary", "聖光術", None, "buff", "ally", 0, 0.0, 0, 0.0, affect=dict(
        duration=1800, flags=AffectFlag.SANCTUARY, off_message="環繞你的神聖光圈從身上消失。")),
    # 偵查隱形、偵查藏匿：10 分鐘（使用者 2026-11-20 改的，原本 30 分鐘；棕仙巷的小魔杖、粉紅藥劑放這兩個）
    Skill("detect_invis", "偵查隱形", None, "buff", "self", 0, 0.0, 0, 0.0, affect=dict(
        duration=600, flags=AffectFlag.DETECT_INVIS, off_message="你不再看到隱形的物體。")),
    Skill("detect_hidden", "偵查藏匿", None, "buff", "self", 0, 0.0, 0, 0.0, affect=dict(
        duration=600, flags=AffectFlag.DETECT_HIDDEN, off_message="你對四週的觀察力下降了。")),
    # 減益：粉光讓隱形、藏匿都沒用，閃躲、AC ×0.9（stats.add_affects() 看旗標）
    Skill("faerie_fire", "灼熱火燄", None, "debuff", "single", 0, 0.0, 0, 0.0, affect=dict(
        duration=1800, flags=AffectFlag.FAERIE_FIRE, off_message="粉紅色的光圈從你身上消失。"),
        cast_text=("粉紅色的光圈將你團團圍住了。", "粉紅色的光圈將$n團團圍住了。")),
    # ---- mud_design 2026-11-19 的技能草案（design/技能/，數字照 sim/skill_tree.py 的 MECH）：要用程式加（sset），還沒有學的方法 ----
    # 劍之公會．戰士（Lv10～30）
    Skill("power_slash", "猛力斬", Guild.SWORD, "damage", "single", 1, 4.35, 6, 0.19),
    Skill("war_cry", "戰吼", Guild.SWORD, "buff", "ally", 0, 0.0, 6, 0.19, affect=dict(duration=60, applies={"str": 2.0})),
    Skill("iron_body", "鋼鐵之軀", Guild.SWORD, "passive", "self", 0, 0.0, 0, 0.0, passive={"hp": 1.05}),
    # 巨武（戰士的小路）
    Skill("sweep", "橫掃", Guild.SWORD, "damage", "group", 1, 1.8, 6, 0.19, weapon_kinds=tuple(sorted(TWO_HANDED_KINDS))),
    Skill("heavy_mastery", "重武精通", Guild.SWORD, "passive", "self", 0, 0.0, 0, 0.0,
          weapon_kinds=tuple(sorted(TWO_HANDED_KINDS)), passive={"dmg_out": 1.05}),
    Skill("whirlwind", "旋風斬", Guild.SWORD, "damage", "group", 2, 0.9, 6, 0.19, weapon_kinds=tuple(sorted(TWO_HANDED_KINDS))),
    Skill("berserk", "狂暴", Guild.SWORD, "buff", "self", 0, 0.0, 6, 0.19,
          affect=dict(duration=30, applies={"str": 3.0}, mult={"ac": 0.92})),
    Skill("quake", "震地", Guild.SWORD, "damage", "group", 1, 1.8, 6, 0.19, weapon_kinds=tuple(sorted(TWO_HANDED_KINDS)), tag="站不穩"),
    Skill("sky_rend", "裂空斬", Guild.SWORD, "damage", "group", 1, 1.8, 6, 0.19, weapon_kinds=tuple(sorted(TWO_HANDED_KINDS))),
    Skill("cataclysm", "天崩地裂", Guild.SWORD, "damage", "group", 3, 0.6, 6, 0.19, weapon_kinds=tuple(sorted(TWO_HANDED_KINDS))),
    # 盾衛（戰士的小路）
    Skill("taunt", "挑釁", Guild.SWORD, "protect", "single", 0, 0.0, 6, 0.19, tag="被挑釁", affect=dict(duration=6)),
    Skill("shield_mastery", "盾牌精通", Guild.SWORD, "passive", "self", 0, 0.0, 0, 0.0, offhand="shield",
          passive={"shield_ac": 1.05}),
    Skill("guard", "守護", Guild.SWORD, "protect", "ally", 0, 0.0, 6, 0.19, guard=dict(share=0.3, duration=30)),
    Skill("shield_bash", "盾擊", Guild.SWORD, "control", "single", 1, 0.8, 6, 0.19, offhand="shield", tag="暈",
          onhit=dict(duration=4, control="stun")),
    Skill("challenge", "群體挑釁", Guild.SWORD, "protect", "group", 0, 0.0, 6, 0.19, tag="被挑釁", affect=dict(duration=6)),
    Skill("bulwark", "鐵壁", Guild.SWORD, "buff", "self", 0, 0.0, 6, 0.19, affect=dict(duration=15, shield_pct=0.1)),
    Skill("last_stand", "不倒之盾", Guild.SWORD, "protect", "allies", 0, 0.0, 6, 0.19, guard=dict(share=0.5, duration=10)),
    # 刺客（Lv10～30）
    Skill("backstab", "背刺", Guild.SWORD, "damage", "single", 1, 4.3, 6, 0.19, weapon_kinds=(WeaponKind.DAGGER,)),
    Skill("light_step", "身輕如燕", Guild.SWORD, "passive", "self", 0, 0.0, 0, 0.0, passive={"dodge": 1.05}),
    Skill("poison_blade", "毒刃", Guild.SWORD, "debuff", "single", 1, 0.3, 6, 0.19, tag="中毒",
          dot=dict(name="中毒", jumps=10, hurt="毒傷")),
    # 雙刃（刺客的小路）
    Skill("twin_slash", "雙刃斬", Guild.SWORD, "damage", "single", 3, 1.3, 6, 0.19, offhand="dual"),
    Skill("dual_mastery", "雙持精通", Guild.SWORD, "passive", "self", 0, 0.0, 0, 0.0, offhand="dual",
          passive={"off_attacks": 1.05}),
    Skill("flurry", "疾風連刺", Guild.SWORD, "damage", "single", 6, 0.4, 6, 0.19, offhand="dual"),
    Skill("blade_spin", "迴旋刃", Guild.SWORD, "damage", "group", 2, 0.9, 6, 0.19, offhand="dual"),
    Skill("lethal_rhythm", "致命節奏", Guild.SWORD, "passive", "self", 0, 0.0, 0, 0.0, offhand="dual", passive={"crit": 1.05}),
    Skill("hundred_cuts", "百裂刃", Guild.SWORD, "damage", "single", 10, 0.3, 6, 0.19, offhand="dual"),
    Skill("blade_dance", "刃舞", Guild.SWORD, "damage", "group", 6, 0.45, 6, 0.19, offhand="dual"),
    # 暗殺（刺客的小路）
    Skill("stun_strike", "擊暈", Guild.SWORD, "control", "single", 0, 0.0, 6, 0.19, tag="暈", affect=dict(duration=4, control="stun")),
    Skill("expose_weakness", "弱點標記", Guild.SWORD, "debuff", "single", 0, 0.0, 6, 0.19, affect=dict(duration=30, mult={"ac": 0.5})),
    Skill("garrote", "封喉", Guild.SWORD, "control", "single", 0, 0.0, 6, 0.19, tag="沉默",
          affect=dict(duration=6, control="silence")),
    Skill("deathblow", "絕命刺", Guild.SWORD, "damage", "single", 1, 4.3, 6, 0.19, weapon_kinds=(WeaponKind.DAGGER,), opener=True),
    Skill("smoke_bomb", "煙霧彈", Guild.SWORD, "control", "group", 0, 0.0, 6, 0.19, tag="失明",
          affect=dict(duration=12, mult={"hit_mult": 0.5}, control="blind")),
    Skill("cripple", "致殘", Guild.SWORD, "debuff", "single", 0, 0.0, 6, 0.19,
          affect=dict(duration=30, mult={"hit": 0.5, "dodge": 0.5})),
    Skill("shadow_bind", "影縛", Guild.SWORD, "control", "single", 0, 0.0, 6, 0.19, tag="暈", affect=dict(duration=8, control="stun")),
    # 杖之公會．元素（Lv10～30）
    Skill("lightning_bolt", "閃電箭", Guild.STAFF, "damage", "single", 1, 4.25, 6, 0.19),
    Skill("erosion", "元素侵蝕", Guild.STAFF, "debuff", "single", 0, 0.0, 6, 0.19, affect=dict(duration=30, mult={"res_spell": 0.65})),
    Skill("slow", "緩速術", Guild.STAFF, "control", "single", 0, 0.0, 6, 0.19, tag="變慢",
          affect=dict(duration=30, mult={"aspd": 0.85}, control="slow")),
    # 烈焰（元素的小路）
    Skill("flame_wave", "火焰衝擊", Guild.STAFF, "damage", "group", 1, 1.4, 6, 0.19, tag="燃燒", dot=dict(name="燃燒", ratio=0.3, jumps=3, hurt="燒傷")),
    Skill("ignite", "引燃", Guild.STAFF, "debuff", "single", 1, 0.75, 6, 0.19, tag="燃燒",
          dot=dict(name="引燃", jumps=6, hurt="燒傷")),
    Skill("fire_rain", "火雨", Guild.STAFF, "damage", "group", 3, 0.85, 6, 0.19),
    Skill("blast", "爆炎", Guild.STAFF, "damage", "group", 1, 2.3, 6, 0.19),
    Skill("embers", "餘燼", Guild.STAFF, "debuff", "group", 1, 0.6, 6, 0.19, tag="燃燒", dot=dict(name="餘燼", jumps=6, hurt="燒傷")),
    Skill("fire_pillar", "炎柱", Guild.STAFF, "damage", "group", 1, 1.85, 6, 0.19, tag="燃燒", dot=dict(name="燃燒", ratio=0.3, jumps=3, hurt="燒傷")),
    Skill("inferno", "焚天", Guild.STAFF, "damage", "group", 3, 0.7, 6, 0.19, tag="燃燒", dot=dict(name="燃燒", ratio=0.3, jumps=3, hurt="燒傷")),
    # 寒冰（元素的小路）
    Skill("ice_shard", "冰錐", Guild.STAFF, "damage", "single", 1, 2.7, 6, 0.19, tag="變慢",
          onhit=dict(duration=6, mult={"aspd": 0.9}, control="slow")),
    Skill("freeze", "冰凍術", Guild.STAFF, "control", "single", 0, 0.0, 6, 0.19, tag="凍住", affect=dict(duration=4, control="freeze")),
    Skill("chill", "寒氣", Guild.STAFF, "debuff", "single", 0, 0.0, 6, 0.19, affect=dict(duration=30, mult={"dodge": 0.5})),
    Skill("frost_ring", "冰環", Guild.STAFF, "control", "group", 0, 0.0, 6, 0.19, tag="凍住", affect=dict(duration=4, control="freeze")),
    Skill("blizzard", "暴風雪", Guild.STAFF, "control", "group", 0, 0.0, 6, 0.19, tag="變慢",
          affect=dict(duration=18, mult={"aspd": 0.5}, control="slow")),
    Skill("glacier_crash", "冰河衝擊", Guild.STAFF, "damage", "group", 1, 2.8, 6, 0.19),
    Skill("absolute_zero", "絕對零度", Guild.STAFF, "control", "single", 0, 0.0, 6, 0.19, tag="凍住",
          affect=dict(duration=8, control="freeze")),
    # 神官（Lv10～30）
    Skill("heal", "治療術", Guild.STAFF, "heal", "ally", 0, 1.2, 6, 0.19),
    Skill("bless", "祝福", Guild.STAFF, "buff", "ally", 0, 0.0, 6, 0.19,
          affect=dict(duration=300, mult={"res_phys": 1.1, "res_spell": 1.1})),
    Skill("renew", "回春術", Guild.STAFF, "heal", "ally", 0, 0.1, 6, 0.19, hot=dict(jumps=10)),
    # 治療（神官的小路）
    Skill("flash_heal", "快速治療", Guild.STAFF, "heal", "ally", 0, 1.0, 3, 0.19),
    Skill("holy_shield", "神聖護盾", Guild.STAFF, "buff", "ally", 0, 0.0, 6, 0.19, affect=dict(duration=30, shield_pct=0.1)),
    Skill("mass_heal", "群體治療", Guild.STAFF, "heal", "allies", 0, 3.95, 6, 0.19),
    Skill("greater_heal", "強效治療", Guild.STAFF, "heal", "ally", 0, 5.6, 6, 0.19),
    Skill("divine_favor", "神佑", Guild.STAFF, "buff", "ally", 0, 0.0, 6, 0.19, affect=dict(duration=300, mult={"hp": 1.1})),
    Skill("wellspring", "生命之泉", Guild.STAFF, "heal", "allies", 0, 0.1, 6, 0.19, hot=dict(jumps=10)),
    Skill("miracle", "神蹟", Guild.STAFF, "heal", "allies", 0, 3.95, 6, 0.19),
    # 詛咒（神官的小路）
    Skill("weaken", "衰弱術", Guild.STAFF, "debuff", "single", 0, 0.0, 6, 0.19, affect=dict(duration=30, mult={"dmg": 0.9})),
    Skill("corrode", "腐蝕術", Guild.STAFF, "debuff", "single", 1, 0.65, 6, 0.19, dot=dict(name="腐蝕術", jumps=10, hurt="侵蝕")),
    Skill("raise_skeleton", "喚骨術", Guild.STAFF, "summon", "self", 0, 0.0, 6, 0.19,
          summon=dict(tier="normal", below=10, duration=120)),
    Skill("curse", "詛咒術", Guild.STAFF, "debuff", "single", 0, 0.0, 6, 0.19,
          affect=dict(duration=60, mult={"res_phys": 0.9, "res_spell": 0.9})),
    Skill("drain_life", "吸取生命", Guild.STAFF, "damage", "single", 1, 2.3, 6, 0.19, lifesteal=0.5),
    Skill("plague", "瘟疫", Guild.STAFF, "debuff", "group", 1, 0.45, 6, 0.19, dot=dict(name="瘟疫", jumps=10, hurt="侵蝕")),
    Skill("death_knight", "死亡騎士", Guild.STAFF, "summon", "self", 0, 0.0, 6, 0.19,
          summon=dict(tier="elite", below=10, duration=120)),
    # Lv5 各公會多一個（2026-11-20 使用者定的）：強度跟重擊、火球一樣，但連打兩下（比率減半；火焰箭的燃燒比率加倍，總共跟火球一樣）；
    # 升到 5 級自動學會（paths.GUILD_SKILLS），不用選路。
    # 放在最後面：技能名稱的縮寫照這個順序找，原本的縮寫（use p 是猛力斬、use fla 是火焰衝擊）才不會變
    Skill("pummel", "猛擊", Guild.SWORD, "damage", "single", 2, 0.475, 6, 0.10, sure=True),
    Skill("flame_arrow", "火焰箭", Guild.STAFF, "damage", "single", 2, 0.315, 6, 0.10, tag="燃燒",
          dot=dict(name="燃燒", ratio=0.6, jumps=3, hurt="燒傷"), sure=True),
    # Lv15、Lv25 的公會被動（設計文件 §2.6，2026-11-20 使用者定的）：不是打架用的，讓玩家少休息；兩個公會效果一樣、名字不同。
    # 升到那一級自動學會（paths.GUILD_SKILLS），不用選路。passive 是空的（不改屬性），效果在 rest_regen、fight_end
    Skill("breath_control", "調息", Guild.SWORD, "passive", "self", 0, 0.0, 0, 0.0, passive={}, rest_regen=1.5),
    Skill("meditate", "冥想", Guild.STAFF, "passive", "self", 0, 0.0, 0, 0.0, passive={}, rest_regen=1.5),
    Skill("sheathe", "收刀", Guild.SWORD, "passive", "self", 0, 0.0, 0, 0.0, passive={}, fight_end=0.10),
    Skill("recollect", "回神", Guild.STAFF, "passive", "self", 0, 0.0, 0, 0.0, passive={}, fight_end=0.10),
)}
KIND_NAMES = {"damage": "傷害", "heal": "治療", "buff": "增強", "debuff": "減弱", "control": "控制", "protect": "保護",
              "summon": "召喚", "passive": "被動"}   # 種類的中文（設計文件 §2.6 的 9 類）
OFFHAND_NEEDS = {"shield": "你要拿盾才能用{}。", "dual": "你要兩手各拿一把武器才能用{}。"}     # 副手的條件不合（use 那句）
OFFHAND_NAMES = {"shield": "要拿盾", "dual": "要雙持"}                                        # skills 列出來的條件
SELF_ONLY = "這個技能只能放在自己身上。"      # target 是 "self" 的技能指定了別人（use、物品）


MIN_SKILL_DAMAGE = 1                        # 技能（不是平砍）打中最低幾點，燃燒每跳也是（使用者定的；失手還是 0）


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

    乘的是技能的公會的標準，不是自己的上限：同等級的人扣的一樣多。imm 的技能、被動技能（消耗比率 0）是 0。
    """
    if resource(skill) is None or not skill.cost:
        return 0
    return max(1, stats.shown(stats.resource_standard(level, skill.guild, resource(skill)) * skill.cost))


GIFT = "gift"                               # 餽贈的技能 id：身上有它，技能只扣一半（spend）
GIFT_COST = 0.5


def gifted(ch):
    """ch 身上有沒有餽贈（看 Affect.source）。"""
    return any(a.source == GIFT for a in getattr(ch, "affects", []))


def spend(ch, skill):
    """ch 用一次 skill 扣多少（pay、affordable、skills 的消耗那欄都用它）：cost()，身上有餽贈時是一半（設計文件 §2.6「打架中更順」，使用者 2026-11-21 定的）。

    一半是拿整數的消耗再減半、四捨五入、最少 1（3 → 2、5 → 3；skills 顯示的就是扣的）；消耗 0 的照樣 0。
    """
    full = cost(skill, ch.level)
    return max(1, stats.shown(full * GIFT_COST)) if full and gifted(ch) else full


def display_range(ch, skill):
    """skills 顯示的傷害 (最低, 最高)：還沒被抗性擋、不含爆擊（必定爆擊的 sure 一定爆擊，所以乘上自己的爆擊倍率，balance.py 的 skill_display_range）。

    拿主手武器：設計文件的（傷害點數 ＋ 主手武器下限／上限）× ratio。
    空手（使用者選的）：傷害點數 × ratio × (1 ∓ 浮動)，跟 damage.strike() 實際的 ±20% 一樣。
    """
    points = ch.panel.get(f"dmg_{damage_kind(skill, ch)}", 0.0)
    ratio = skill.ratio * (damage.crit_mult(ch) if skill.sure else 1.0)
    weapon = damage.weapon_in(ch, 0)
    if weapon is not None:
        return (stats.shown((points + weapon.base["dmg_min"]) * ratio),
                stats.shown((points + weapon.base["dmg_max"]) * ratio))
    points *= ratio
    return stats.shown(points * (1.0 - damage.DMG_VAR)), stats.shown(points * (1.0 + damage.DMG_VAR))


def heal_range(ch, skill):
    """skills 顯示的補血 (最低, 最高)：（法術傷害點數 ＋ 主手武器下限／上限）× ratio，不含爆擊；空手的不浮動。"""
    points = ch.panel.get("dmg_spell", 0.0)
    weapon = damage.weapon_in(ch, 0)
    low, high = (points + weapon.base["dmg_min"], points + weapon.base["dmg_max"]) if weapon is not None else (points, points)
    return stats.shown(low * skill.ratio), stats.shown(high * skill.ratio)


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
    """ch 學會 skill（之後的學習、技能書、imm 的 sset 都呼叫它）。回傳學了沒：已經會、imm_only 的不加。
    被動技能學了馬上有效：從頭算屬性（affects.changed）。"""
    if skill.imm_only or skill.id in ch.skills:
        return False
    ch.skills.append(skill.id)
    affects.changed(ch)
    return True


def forget(ch, skill):
    """ch 忘掉 skill。回傳本來會不會。被動技能忘了馬上沒有。"""
    if skill.id not in ch.skills:
        return False
    ch.skills.remove(skill.id)
    affects.changed(ch)
    return True


def rest_regen(ch):
    """休息、睡覺時回復的倍率：學會的被動（調息、冥想 ×1.5）乘起來，沒有是 1（stats.regen 用）。"""
    return math.prod(s.rest_regen for s in passives(ch))


def fight_ended(ch):
    """ch 整場戰鬥結束了（death.die 看的：他在打的最後一隻死了，身邊也沒有別的生物在打他）：
    學會收刀、回神的，HP、MP、MV 各回上限的 fight_end（10%），超過上限停在上限。沒有訊息（prompt 看得到）。逃跑、回城、對方逃走不算。
    """
    share = sum(s.fight_end for s in passives(ch))
    if share and getattr(ch, "panel", None):
        for key in ("hp", "mp", "mv"):
            setattr(ch, key, min(ch.panel[key], getattr(ch, key) + ch.panel[key] * share))


def passives(ch):
    """ch 學會、條件也合的被動技能（stats.passives 用）：限定武器、副手不合就沒有效果（設計文件 §2.6）。

    不看 known()：第一次算屬性時（讀檔）還沒有 panel。
    """
    mine = getattr(ch, "skills", [])
    return [s for s in SKILLS.values() if s.kind == "passive" and s.id in mine and weapon_ok(ch, s) and offhand_ok(ch, s)]


def enemies(ch):
    """打一群的對象（設計文件 §2.6）：同一間房裡 ch 看得到的生物，照 look 的順序；不打玩家、召喚物。"""
    return [c for c in in_room(ch) if isinstance(c, Npc) and c.master is None and light.visible(ch, c)]


def allies(ch):
    """放在一群自己人上的對象（群體治療…）：自己和同房間看得到的玩家。"""
    return [ch] + [c for c in in_room(ch) if not isinstance(c, Npc) and light.visible(ch, c)]


def friendly(skill):
    """放在自己人身上的（補血、增益、守護）：對象是自己或同房間的玩家，不開打。"""
    return skill.kind in ("heal", "buff") or (skill.kind == "protect" and skill.guard is not None)


def find(ch, word):
    """ch 會的技能裡，第一個 id 用 word 開頭的（跟指令一樣可以縮寫，英文不分大小寫）；找不到是 None。"""
    word = word.lower()
    return next((s for s in known(ch) if s.id.startswith(word)), None)


def free(ch):
    """ch 用技能不扣消耗、不用等冷卻：imm（使用者要的，方便測試）。"""
    return getattr(ch, "imm", False)


def affordable(ch, skill):
    """夠不夠付（使用者選的）：現在的 MV／MP 四捨五入後（跟 prompt 顯示的一樣）≥ 消耗就可以。imm、沒有消耗的技能一律夠。"""
    return free(ch) or resource(skill) is None or stats.shown(getattr(ch, resource(skill))) >= spend(ch, skill)


def weapon_ok(ch, skill):
    """主手武器的種類符不符合：沒寫 weapon_kinds 是不限；有寫的話主手要拿那種武器（空手不行）。"""
    if not skill.weapon_kinds:
        return True
    weapon = damage.weapon_in(ch, 0)
    return weapon is not None and weapon.weapon_kind in skill.weapon_kinds


def offhand_ok(ch, skill):
    """副手的條件（設計文件 §2.6）：要拿盾是副手放護具（盾牌），要雙持是副手放武器；拿雙手武器時副手是空的，兩種都不算。"""
    if skill.offhand == "shield":
        obj = ch.equipment.get("offhand")
        return obj is not None and not obj.is_weapon()
    if skill.offhand == "dual":
        return damage.dual_wielding(ch)
    return True


def pay(ch, skill):
    """扣消耗（spend：有餽贈扣一半）、開始冷卻（imm 都不用）。沒有消耗的不扣、冷卻 0 的不設（所以生物也能用這種技能）。"""
    if free(ch):
        return
    pool = resource(skill)
    if pool is not None:
        setattr(ch, pool, max(0.0, getattr(ch, pool) - spend(ch, skill)))     # 比的是四捨五入，扣完可能小於 0
    if skill.cooldown:
        ch.cooldowns[skill.id] = skill.cooldown


GROUP_BONUS = 0.5                           # 打一群：每多一隻總量多 50%，再平分（設计文件 §2.6）
GROUP_TARGETS = ("group", "allies")         # 打一群（房間裡能打的生物）、放在一群自己人上（自己和同房間的玩家）


def share(n):
    """打一群、放在一群上的扣血、補血，每一隻乘多少：(1 ＋ 0.5 × (n − 1)) ÷ n（1 隻 1、2 隻 0.75、3 隻 0.67…，不會低於 0.5）。"""
    return (1.0 + GROUP_BONUS * (n - 1)) / n


def use(ch, skill, victim, pay_cost=True):
    """ch 對 victim 用 skill（能不能用由指令先檢查）：扣消耗、開始冷卻，再照種類放（buff()、heal()、debuff()、control()、strike()）。
    victim 可以是一個角色，或打一群、放在一群上時的名單（放的時候是幾隻就是幾隻，扣血、補血照 share() 分）。
    物品放的技能（藥水、卷軸、魔杖、魔棒，設計文件 §3.8）pay_cost 是 False：不扣消耗、沒有冷卻。
    打指令當下就放，平砍照打（技能是額外的）。訊息放進那一場，打完馬上送：ch 那段是指令的回覆，別人照舊 notify。
    """
    if pay_cost:
        pay(ch, skill)
    victims = victim if isinstance(victim, list) else [victim]
    part = share(len(victims)) if skill.target in GROUP_TARGETS else 1.0
    if skill.kind == "buff":
        for target in victims:
            buff(ch, skill, target)
    elif skill.kind == "heal":
        heal(ch, skill, victims, part)
    elif skill.kind == "debuff":
        debuff(ch, skill, victims, part)
    elif skill.kind == "control" and not skill.hits:
        control(ch, skill, victims)
    elif skill.kind == "protect":
        (shield if skill.guard else taunt)(ch, skill, victims)
    elif skill.kind == "summon":
        summons.summon(ch, skill)
    else:
        battle = ch.fight                   # 先記住：打死生物時 die() 會把 ch.fight 清掉
        with battle.collecting(me=ch):      # 技能那幾下、打死時腳本說的話合成一段
            hit = [target for target in victims
                   if target in characters and target.room is ch.room       # 前面打的時候發生的事（腳本）可能讓牠不在了
                   and strike(battle, ch, skill, target, part)]
            if skill.id == "blade_spin":    # 連動「毒刃擴散」
                combos.spread_poison([v for v in hit if v in characters])


def strike(battle, ch, skill, victim, part=1.0):
    """傷害技能打 victim hits 次：每一次 ＝ 平砍的一下（各自擲命中、浮動、爆擊；sure 的不擲命中、一定爆擊）× ratio × part × 連動，類型見 damage_kind()，
    打中最低 1 點；目標死了就不打剩下的。打中過、沒死：留下持續傷害（燃燒）、打中後的效果。回傳打中過沒。
    連動（combos.py）在打之前看一次：比率、多打幾下、控制多幾回合、牠在不在燒、閃電箭要不要跳。
    """
    times = skill.ratio * part * combos.ratio(ch, skill, victim)
    longer = combos.control_ticks(ch, skill, victim)
    burning = bool(combos.burns(victim))
    chain = skill.id == "lightning_bolt" and affects.has_tag(victim, "元素侵蝕")    # 連動「侵蝕連鎖」
    first, dead = None, False               # 第一發打中的傷害（持續傷害用）
    for _ in range(skill.hits + combos.extra_hits(ch, skill)):
        dmg, crit = damage.strike(ch, victim, combat.rng, damage_kind(skill, ch), sure=skill.sure)
        dmg *= times
        if dmg > 0:
            dmg = max(MIN_SKILL_DAMAGE, dmg)         # 打中最低 1 點（使用者定的）
            first = dmg if first is None else first
        dead = combat.land(battle, ch, victim, dmg, crit, skill.name)
        if skill.lifesteal and dmg > 0:
            drain(battle, ch, dmg * skill.lifesteal)
        if dead:
            break                           # 打死了：不留持續傷害、打中後的效果
        if dmg > 0:
            combos.on_hit(ch, skill, victim)
    if first is not None and not dead:
        if skill.dot:
            affects.add(victim, dot_affect(skill.id, skill.dot, first, tag(skill), ch))
        if skill.onhit:                     # 打中後放的減弱、控制（冰錐的變慢、盾擊的暈）：不用再擲命中，控制的規則照算（設計文件 §2.6）
            effect = affects.Affect(source=skill.id, name=skill.name, tag=tag(skill), by=ch, **copy.deepcopy(skill.onhit))
            effect.duration = effect.ticks = effect.duration + longer
            apply_effect(battle, victim, effect)
        combos.after_hits(battle, ch, skill, victim, burning)
    if chain:
        jump(battle, ch, skill, victim)
    return first is not None


CHAIN_RATIO = 0.5                           # 侵蝕連鎖：跳到另一隻的比率減半


def jump(battle, ch, skill, victim):
    """侵蝕連鎖：閃電箭打有元素侵蝕的怪，再跳到同房間另一隻怪（照 look 的順序第一隻），比率減半，打一下；牠還沒在打架就開打。"""
    from . import fight                     # 坑：fight → specials → skills 繞一圈，在函式裡才 import
    other = next((c for c in enemies(ch) if c is not victim), None)
    if other is None:
        return
    if other.fighting is None:
        fight.start_fight(other, ch)
    dmg, crit = damage.strike(ch, other, combat.rng, damage_kind(skill, ch))
    dmg *= skill.ratio * CHAIN_RATIO
    combat.land(battle, ch, other, max(MIN_SKILL_DAMAGE, dmg) if dmg > 0 else 0.0, crit, skill.name)


LIFESTEAL = "{G你吸取了 $t 點 HP。{x"         # 吸血補回來的（補到上限，0 點不說）


def drain(battle, ch, amount):
    """吸血（設計文件 §2.6）：補回 amount，補到上限就停；不另外擲爆擊（那一下的爆擊已經算在傷害裡）。"""
    before = ch.hp
    ch.hp = min(ch.panel["hp"], ch.hp + amount)
    if stats.shown(ch.hp - before) > 0:
        battle.tell(compose(LIFESTEAL, ch, t=str(stats.shown(ch.hp - before)), to=TO_CHAR))


def tag(skill):
    """技能放出去的效果的種類（連動用）：有寫 tag 用它，沒寫是技能名稱（設計文件 §2.6）。"""
    return skill.tag or skill.name


def dot_affect(source, d, first, kind="", by=None):
    """留在目標身上的持續傷害（火球的燃燒、毒刃、生物 spec_poison 的劇毒）：每 AFFECT_PULSE_TICKS 跳一次、共 jumps 次，
    每跳 ＝ first × ratio（沒寫 ratio 是 1：毒刃這種 first 已經乘過比率），放下去時算好（最低 MIN_SKILL_DAMAGE）。
    來源是技能的 id（special 是名字）：再中一次就重新算。kind 是效果種類、by 是誰放的（連動用）。
    d 是 name、ratio、jumps、hurt，可以再寫 off（消失時的那句，沒寫用共用的）。
    """
    return affects.Affect(source=source, name=d["name"], duration=d["jumps"] * AFFECT_PULSE_TICKS,
                          periodic={"hp": -max(MIN_SKILL_DAMAGE, first * d.get("ratio", 1.0))}, hurt=d["hurt"],
                          off_message=d.get("off", ""), tag=kind, by=by)


def heal_amount(ch, skill):
    """補多少（設計文件 §2.6）：（法術傷害點數 ＋ 主手武器基本傷害）× ratio，回傳 (量, 有沒有爆擊)。
    不擲命中；武器跟平砍一樣在下限～上限取值，不另外浮動（mud_design 定的）；爆擊照放的人的爆擊率、爆擊傷害。
    """
    weapon = damage.weapon_in(ch, 0)
    points = ch.panel.get("dmg_spell", 0.0)
    if weapon is not None:
        low, high = weapon.base["dmg_min"], weapon.base["dmg_max"]
        points += low + (high - low) * combat.rng.random()
    crit = combat.rng.random() < damage.crit_chance(ch)
    return points * skill.ratio * (damage.crit_mult(ch) if crit else 1.0), crit


def heal(ch, skill, targets, part=1.0):
    """補血技能：一次補完（補到上限就停），或持續補血（hot：放的時候算好每跳多少、擲一次爆擊，用 periodic 的 HP ＋）。不開打。
    放在一群上（群體治療）：每個人各自擲（武器、爆擊），量 × part；訊息先說施展了，再一個人一句補了多少。
    """
    if skill.target == "allies":
        act("你施展了【$t】。", ch, t=skill.name, to=TO_CHAR)
        act("$n施展了【$t】。", ch, t=skill.name, to=TO_ROOM)
    for target in targets:
        amount, crit = heal_amount(ch, skill)
        amount *= part * combos.heal_ratio(skill, target)     # 連動「回春加護」
        crit_text = combat.CRIT if crit else ""
        if skill.hot:
            if skill.target != "allies":
                cast(ch, skill, target, crit)
            affects.add(target, affects.Affect(source=skill.id, name=skill.name, tag=tag(skill),
                                               duration=skill.hot["jumps"] * AFFECT_PULSE_TICKS, periodic={"hp": amount}))
            continue
        before = target.hp
        target.hp = min(target.panel["hp"], target.hp + amount)
        combos.after_heal(skill, target)    # 連動「群體回春」
        healed = f"恢復了 {stats.shown(target.hp - before)} 點 HP"
        if skill.target == "allies":
            if target is ch:
                act(crit_text + "你" + healed + "。", ch, to=TO_CHAR)
            else:
                act(crit_text + "$N" + healed + "。", ch, target, to=TO_CHAR)
                act(crit_text + "你" + healed + "。", ch, target, to=TO_VICT)
        elif target is ch:
            act("你對自己施展了【$t】，" + crit_text + healed + "。", ch, t=skill.name, to=TO_CHAR)
            act("$n對自己施展了【$t】。", ch, t=skill.name, to=TO_ROOM)
        else:
            act("你對$N施展了【$t】，" + crit_text + "$E" + healed + "。", ch, target, t=skill.name, to=TO_CHAR)
            act("$n對你施展了【$t】，" + crit_text + "你" + healed + "。", ch, target, t=skill.name, to=TO_VICT)
            act("$n對$N施展了【$t】。", ch, target, t=skill.name, to=TO_NOTVICT)


def make_affect(skill, by=None):
    """增益技能放上去的效果，每次一份新的（dict 不跟技能的資料共用）。source、name 沒寫就用技能的 id、名稱（使用者定的）：
    再放一次是同一個來源（覆蓋），score 和「消失了」寫的是技能的名字。需要不一樣時才寫（例如火球留下「燃燒」）。by 是誰放的（連動用）。
    """
    return affects.Affect(**{"source": skill.id, "name": skill.name, "tag": tag(skill), "by": by, **copy.deepcopy(skill.affect)})


def buff(ch, skill, target):
    """增益技能：把 skill.affect 放到 target 身上（同一個來源是覆蓋：時間回到滿的），送訊息。

    不用打架、不開打：NPC 也能直接呼叫 use(npc, 技能, 玩家)（之後教學區的 NPC 用）。
    先說再放：放了隱身術的人看不到了，先放的話訊息會寫成「你對某人施展了」。
    """
    cast(ch, skill, target)
    effect = make_affect(skill, ch)
    effect.shield_pct *= combos.shield_ratio(skill, target)    # 連動「神佑護盾」
    affects.add(target, effect)


def cast(ch, skill, target, crit=False):
    """「你對自己施展了【戰吼】。」「$n對你施展了【戰吼】。」：增益、持續補血共用。爆擊了（持續補血）自己、對象那句是「，爆擊！」結尾。"""
    end = "，" + combat.CRIT if crit else "。"
    if target is ch:
        act("你對自己施展了【$t】" + end, ch, t=skill.name, to=TO_CHAR)
        act("$n對自己施展了【$t】。", ch, t=skill.name, to=TO_ROOM)
    else:
        act("你對$N施展了【$t】" + end, ch, target, t=skill.name, to=TO_CHAR)
        act("$n對你施展了【$t】" + end, ch, target, t=skill.name, to=TO_VICT)
        act("$n對$N施展了【$t】。", ch, target, t=skill.name, to=TO_NOTVICT)


CAST_LINES = ((TO_CHAR, "你對$N施展了【$t】。"), (TO_VICT, "$n對你施展了【$t】。"), (TO_NOTVICT, "$n對$N施展了【$t】。"))
MISSED_LINES = ((TO_CHAR, "你對$N施展【$t】，但是失手了。"), (TO_VICT, "$n對你施展【$t】，但是失手了。"),
                (TO_NOTVICT, "$n對$N施展【$t】，但是失手了。"))


def debuff(ch, skill, victims, part=1.0):
    """減益技能（要先開打，跟傷害技能一樣）：把效果放到每一隻身上（同一個來源覆蓋），送訊息。
    只減屬性的一定放得上去；持續扣血的（dot：毒刃）跟傷害技能一樣擲一下，打中才有，每跳 ＝ 這一下 × ratio × part（設計文件 §2.6）。
    訊息：寫了 cast_text 的（灼熱火燄，照 C 版）送那兩句，其他是 CAST_LINES。
    放減益也算出手：兩邊都現形（使用者選的）。訊息放進那一場，打完馬上送（ch 那段是指令的回覆）。
    """
    battle = ch.fight
    with battle.collecting(me=ch):
        for victim in victims:
            battle.tell(stealth.reveal(ch) + stealth.reveal(victim))
            if skill.dot:
                dmg, _crit = damage.strike(ch, victim, combat.rng, damage_kind(skill, ch))
                if dmg <= 0:
                    for to, fmt in MISSED_LINES:
                        battle.tell(compose(fmt, ch, victim, t=skill.name, to=to))
                    continue
                affects.add(victim, dot_affect(skill.id, skill.dot, dmg * skill.ratio * part, tag(skill), ch))
            else:
                affects.add(victim, make_affect(skill, ch))
            if skill.cast_text:
                mine, theirs = skill.cast_text
                battle.tell(compose(mine, victim, to=TO_CHAR))
                battle.tell(compose(theirs, victim, to=TO_ROOM))
                continue
            for to, fmt in CAST_LINES:
                battle.tell(compose(fmt, ch, victim, t=skill.name, to=to))


CONTROL_TEXT = {"stun": "$n被打暈了！", "freeze": "$n被凍住了！", "silence": "$n發不出聲音了！",
                "slow": "$n的動作變慢了。", "blind": "$n什麼都看不見了！"}       # 控制放上去時，牠和旁邊的人看到的
UNAFFECTED = "$n沒有受到影響。"              # 已經暈著、凍住，或剛結束還在抵抗


def control(ch, skill, victims):
    """控制技能（擊暈、冰凍術、封喉、緩速術…，要先開打，跟傷害技能一樣）：每一隻各自擲命中（只擲命中），打中才放（設計文件 §2.6）。
    控制不分：打一群的每一隻都是完整的。訊息放進那一場，打完馬上送（ch 那段是指令的回覆）。
    """
    battle = ch.fight
    with battle.collecting(me=ch):
        for victim in victims:
            battle.tell(stealth.reveal(ch) + stealth.reveal(victim))
            if combat.rng.random() >= damage.hit_chance(ch, victim):
                for to, fmt in MISSED_LINES:
                    battle.tell(compose(fmt, ch, victim, t=skill.name, to=to))
                continue
            for to, fmt in CAST_LINES:
                battle.tell(compose(fmt, ch, victim, t=skill.name, to=to))
            effect = make_affect(skill, ch)
            effect.duration = effect.ticks = effect.duration + combos.control_ticks(ch, skill, victim)   # 連動「慢了就凍」
            apply_effect(battle, victim, effect)


PROVOKED = "$n被激怒了！"                    # 挑釁：牠和旁邊的人看到的


def taunt(ch, skill, victims):
    """挑釁（設計文件 §2.6）：每一隻馬上改打你（還沒在打架的也開打），不擲命中、一定成功，首領也有效；身上放「被挑釁」6 秒（連動用）。
    之後照原本的規則一直打你。訊息放進那一場，打完馬上送（ch 那段是指令的回覆）。
    """
    from . import fight                     # 坑：fight → specials → skills 繞一圈，在函式裡才 import
    battle = ch.fight
    with battle.collecting(me=ch):
        for victim in victims:
            battle.tell(stealth.reveal(ch) + stealth.reveal(victim))
            for to, fmt in CAST_LINES:
                battle.tell(compose(fmt, ch, victim, t=skill.name, to=to))
            fight.start_fight(victim, ch)   # 改打你：在別場就併進來
            affects.add(victim, make_affect(skill, ch))
            battle.tell(compose(PROVOKED, victim, to=TO_CHAR) + compose(PROVOKED, victim, to=TO_ROOM))


def shield(ch, skill, targets):
    """守護、不倒之盾（設計文件 §2.6）：每個人（不是自己）被打的傷害 share 成改由你承受，duration 個 tick（protect.py）。不開打。"""
    for target in targets:
        if target is not ch:
            cast(ch, skill, target)
            protect.add(ch, target, skill.id, skill.guard["share"], skill.guard["duration"])


def apply_effect(battle, victim, affect):
    """把技能的效果放到 victim 身上（控制技能、傷害技能打中後的）。是控制的話照控制的規則（設計文件 §2.6）：
    暈、凍住：已經暈著或凍住、或剛結束 6 秒內（抵抗），沒有作用；首領的控制時間都減半。放上去了說 CONTROL_TEXT 那句。
    """
    if affect.control:
        if affect.control in affects.HELD and affects.resisting(victim):
            battle.tell(compose(UNAFFECTED, victim, to=TO_ROOM))
            return
        if getattr(victim, "tier", None) == MobTier.BOSS:
            affect.duration = affect.ticks = affect.duration // 2
    affects.add(victim, affect)
    if affect.control:
        battle.tell(compose(CONTROL_TEXT[affect.control], victim, to=TO_CHAR) + compose(CONTROL_TEXT[affect.control], victim, to=TO_ROOM))


def tick():
    """世界每個 tick：所有在線玩家的冷卻減 1，到 0 就能再用（掛在角色身上的定時事情放世界 tick、全部角色一起做）；守護的時間也減 1。"""
    protect.tick()
    summons.tick()
    for p in online_players():
        for sid in list(p.cooldowns):
            p.cooldowns[sid] -= 1
            if p.cooldowns[sid] <= 0:
                del p.cooldowns[sid]
