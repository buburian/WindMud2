"""管理員（imm）的指令：只有存檔 imm 是 true 的玩家找得到（commands.find 的 is_imm）。

不是 imm 打這些指令，跟打不存在的指令一樣是「什麼？」（照 C 版）。
"""
import json
import logging
from collections import Counter

from .. import affects, death, equipment, inventory, names, objects, skills, stats
from ..act import TO_CHAR, TO_NOTVICT, TO_ROOM, TO_VICT, act, notify
from ..area import ATTACK_NAMES, ITEM_TYPE_NAMES, WEAPON_KIND_NAMES, AffectFlag, Apply, ItemColor
from ..characters import Position, find_in_room
from ..config import TICK_SECONDS
from ..equipment import SLOT_NAMES, TWO_HANDED
from . import items
from ..npcs import Npc
from ..players import online_players

log = logging.getLogger(__name__)


def do_advance(ch, arg):
    """advance <名字> <等級>：把在線上的玩家升到（或降到）那個等級。"""
    name, _, level = arg.partition(" ")
    level = level.strip()
    if not name or not level:
        ch.send("用法：advance <名字> <等級>\n")
        return
    victim = next((p for p in online_players() if p.name.lower() == name.lower()), None)
    if victim is None:
        ch.send("沒有找到這個玩家。\n")
        return
    if not victim.panel:                    # 沒有屬性（測試直接建的玩家）
        ch.send("這個玩家沒有屬性，不能改等級。\n")
        return
    if not level.isdecimal() or not 1 <= int(level) <= stats.MAX_LEVEL:
        ch.send(f"等級要是 1～{stats.MAX_LEVEL}。\n")
        return
    level, old = int(level), victim.level
    if level == old:
        ch.send(f"{victim.name} 已經是 {level} 級了。\n")
        return
    taken = Counter(stats.set_level(victim, level))
    victim.exp = 0.0                        # 這一級的經驗從 0 開始（不然降級後可能已經超過需求）
    log.info(f"{ch.name} 把 {victim.name} 從 {old} 級改成 {level} 級")
    if level > old:
        msg = f"你升到 {level} 級了！多了 {level - old} 點主屬性點數，用 train 分配。"
    else:
        msg = f"你降到 {level} 級了。"
        if taken:
            names = stats.STAT_NAMES
            msg += "扣回的主屬性：" + "、".join(f"{names[k]} -{taken[k]}" for k in stats.PRIMARY_KEYS if taken[k]) + "。"
    if victim is ch:
        ch.send(msg + "\n")
        return
    ch.send(f"{victim.name} {'升' if level > old else '降'}到 {level} 級了。\n")
    notify(victim, msg)


def do_slay(ch, arg):
    """slay <名字>：直接殺死同房間的生物（照 C 版），原地留下屍體。玩家的死亡還沒做，不能殺玩家。"""
    words = arg.split()
    if not words:
        ch.send("你想要屠殺(Slay)誰？\n")
        return
    victim = find_in_room(ch, words[0])
    if victim is None:
        ch.send("找不到你想要屠殺的人。\n")
        return
    if victim is ch:
        ch.send("屠殺(Slay)無法對自己使用。\n")
        return
    if not isinstance(victim, Npc):
        ch.send("玩家的死亡還沒做，現在只能屠殺生物。\n")
        return
    act("你相當殘酷地屠殺(Slay)$N，$E變成一堆的肉塊與血水!!", ch, victim, to=TO_CHAR)
    act("$n相當殘酷地屠殺(Slay)$N，$E變成一堆的肉塊與血水!!", ch, victim, to=TO_NOTVICT)
    log.info(f"{ch.name} 屠殺了 {victim.name}（房間 {victim.room.vnum}）")
    death.die(victim)


def do_oload(ch, arg):
    """oload <號碼> [等級] [顏色]：照區域檔做一件物品（照 C 版 act_wiz.c，給測試拿裝備）。

    號碼是遊戲號碼（測試長劍是 102）；等級沒寫是自己的等級，顏色沒寫是沒有顏色（沒有隨機屬性）。
    撿得起來放進自己的背包，撿不起來放地上（同房間的人看得到）。不檢查負重、件數。
    """
    words = arg.split()
    if not words or not words[0].isdecimal():
        ch.send("用法：oload <號碼> [等級] [顏色]\n")
        return
    vnum = int(words[0])
    if vnum not in objects.protos:
        ch.send("沒有這個號碼的物品。\n")
        return
    level = ch.level
    if len(words) > 1:
        if not words[1].isdecimal() or not 1 <= int(words[1]) <= stats.MAX_LEVEL:
            ch.send(f"等級要寫 1～{stats.MAX_LEVEL}。\n")
            return
        level = int(words[1])
    color = None
    if len(words) > 2:
        if words[2].lower() not in set(ItemColor):
            ch.send(f"顏色要寫 {'、'.join(ItemColor)}。\n")
            return
        color = ItemColor(words[2].lower())
    obj = objects.create(vnum, level, color)
    if obj.take:
        ch.carrying.insert(0, obj)
    else:
        ch.room.contents.insert(0, obj)
        act("$n創造了【$t】！", ch, t=objects.short(obj), to=TO_ROOM)
    act("你創造了【$t】！", ch, t=objects.short(obj), to=TO_CHAR)
    log.info(f"{ch.name} 創造了 {obj.name}（{vnum}，{level} 級，{color}）")


def do_ostat(ch, arg):
    """ostat <名字>：看物品的全部資料（找自己的背包、身上、地上、地上屍體裡的，照這個順序）。ostat <號碼>：區域檔的原本寫法。"""
    words = arg.split()
    if not words:
        ch.send("用法：ostat <名字或號碼>\n")
        return
    if words[0].isdecimal():
        proto = objects.protos.get(int(words[0]))
        ch.send(proto_text(int(words[0]), proto) if proto else "沒有這個號碼的物品。\n")
        return
    worn = [ch.equipment[pos] for pos, _ in inventory.SLOTS if pos in ch.equipment]
    floor = ch.room.contents
    inside = [o for c in floor if c.item_type in items.CONTAINERS for o in c.contains]
    obj = objects.find(ch.carrying + worn + floor + inside, words[0])
    ch.send(obj_text(obj) if obj else "找不到這件物品。\n")


def apply_text(location, n):
    return f"{Apply(location).name}({int(location)}) {n:+}"


def obj_text(obj):
    """ostat 的內容：全部欄位，數字留小數（imm 看的，不四捨五入成整數）。"""
    kind = f"{obj.item_type} {ITEM_TYPE_NAMES.get(obj.item_type, '？')}"
    lines = [f"號碼 {obj.vnum if obj.vnum is not None else '無'}  名字 {obj.name}  keywords {' '.join(obj.keywords)}",
             f"種類 {kind}  等級 {obj.level}  顏色 {obj.color or '無'}  重量 {obj.weight}  撿得起來 {'是' if obj.take else '否'}"]
    if obj.slot is not None:
        where = "主手＋副手（雙手）" if obj.slot == TWO_HANDED else SLOT_NAMES[obj.slot]
        line = f"部位 {obj.slot}（{where}）"
        if obj.is_weapon():
            line += (f"  武器種類 {int(obj.weapon_kind)} {WEAPON_KIND_NAMES[obj.weapon_kind]}"
                     f"  攻擊方式 {int(obj.attack)} {ATTACK_NAMES[obj.attack]}")
        lines.append(line)
    if obj.base:
        lines.append("基本值 " + "  ".join(f"{k} {v:.2f}" for k, v in obj.base.items()))
    if obj.affects:
        lines.append("加成 " + "、".join(apply_text(a, n) for a, n in obj.affects))
    if obj.slot is not None:
        points = sum(n * equipment.price(a.name.lower(), obj.level) for a, n in obj.affects if a != Apply.NONE)
        bonus = equipment.COLOR_BONUS.get(obj.color, 0.0)
        lines.append(f"點數 {points:.1f} / 上限 {equipment.cap(obj.level, obj.slot) * bonus:.1f}（{obj.color or '沒有顏色'} ×{bonus:g}）")
    lines.append(f"地上那一行 {obj.long}")
    lines.append(f"timer {obj.timer if obj.timer is not None else '無'}  裡面 {len(obj.contains)} 件")
    return "\n".join(lines) + "\n"


def proto_text(vnum, proto):
    """ostat <號碼>：區域檔裡那件物品的原本寫法。"""
    affects = "、".join(apply_text(a["location"], a["modifier"]) for a in proto["affects"]) or "無"
    lines = [f"號碼 {vnum}（區域檔的寫法）  short {proto['short']}  keywords {proto['keywords']}",
             f"item_type {proto['item_type']} {ITEM_TYPE_NAMES.get(proto['item_type'], '？')}  wear_flags {proto['wear_flags']}"
             f"  extra_flags {proto['extra_flags']}  weight {proto['weight']}",
             f"values {json.dumps(proto['values'], ensure_ascii=False)}",
             f"affects {affects}",
             f"long {proto['long']}"]
    return "\n".join(lines) + "\n"


PANEL_NAMES = {**stats.STAT_NAMES, "dmg_dragon": "龍焰傷害", "wpn": "武器基本傷害"}
PANEL_ORDER = ("dmg_phys", "dmg_spell", "dmg_dragon", "hit", "dodge", "crit", "critdmg", "speed",
               "res_phys", "res_spell", "res_dragon", "wpn", "ac")


def panel_lines(panel):
    """全部屬性，小數 2 位，一行三個（HP 在上面那行；panel 裡沒有的不列：玩家沒有龍焰傷害、武器基本傷害）。"""
    cells = [f"{PANEL_NAMES[k]} {panel[k]:.2f}" for k in PANEL_ORDER if k in panel]
    return ["  ".join(cells[i:i + 3]) for i in range(0, len(cells), 3)]


def do_mstat(ch, arg):
    """mstat <名字>：看同房間的生物或玩家的全部資料（名字的找法跟 kill 一樣）。"""
    words = arg.split()
    if not words:
        ch.send("用法：mstat <名字>\n")
        return
    victim = find_in_room(ch, words[0])
    if victim is None:
        ch.send("找不到這個角色。\n")
        return
    lines = npc_lines(victim) if isinstance(victim, Npc) else player_lines(victim)
    lines.append("效果 " + ("；".join(affects.describe(victim, a) for a in victim.affects) or "無"))
    ch.send("\n".join(lines) + "\n")


def where_lines(c):
    fighting = c.fighting.name if c.fighting is not None else "無"
    return f"姿勢 {Position(c.position).name}  房間 {c.room.vnum}  正在打 {fighting}"


def npc_lines(npc):
    mix = "、".join(f"{k} {v * 100:g}%" for k, v in (npc.mix or {}).items()) or "無"
    drops = "；".join(f"{d['obj_vnum']} {d['color'] or '無'} {d['chance'] / 100:.2f}%"
                      f"（{'、'.join(d['tiers']) if d['tiers'] else '全部種類'}）" for d in npc.drops) or "沒有"
    lines = [f"號碼 {npc.vnum}  名字 {npc.name}  keywords {' '.join(npc.keywords)}",
             f"等級 {npc.level}  種類 {npc.tier}  攻擊 {mix}  攻防 {npc.defense or '標準'}  原型 {npc.archetype or '標準'}",
             f"act {int(npc.act)}  " + where_lines(npc)]
    if npc.panel:
        lines.append(f"HP {npc.hp:.1f}/{npc.panel['hp']:.1f}  MP {npc.panel.get('mp', 0):.1f}  MV {npc.panel.get('mv', 0):.1f}")
        lines += panel_lines(npc.panel)
    lines.append(f"掉落表 {drops}")
    return lines


def player_lines(p):
    lines = [f"名字 {p.name}  imm {'是' if p.imm else '否'}"]
    if not p.panel:                         # 沒有屬性（測試直接建的）
        return lines + [where_lines(p)]
    gear = stats.extra_primaries(p)         # 裝備 ＋ 效果加的
    lines[0] += (f"  種族 {stats.RACE_NAMES[p.race]}  公會 {stats.GUILD_NAMES[p.guild]}  等級 {p.level}"
                 f"  經驗 {p.exp:.1f}/{stats.exp_to_level(p.level):.1f}")
    lines.append("主屬性 " + "  ".join(f"{stats.STAT_NAMES[k]} {p.primaries[k] + gear[k]:g}（{p.primaries[k]}＋{gear[k]:g}）"
                                    for k in stats.PRIMARY_KEYS) + f"  可分配 {p.points}")
    lines.append(f"HP {p.hp:.1f}/{p.panel['hp']:.1f}  MP {p.mp:.1f}/{p.panel['mp']:.1f}  MV {p.mv:.1f}/{p.panel['mv']:.1f}")
    lines += panel_lines(p.panel)
    cooldowns = "、".join(f"{k} {v}" for k, v in p.cooldowns.items()) or "無"
    lines.append(where_lines(p) + f"  背包 {len(p.carrying)} 件  裝備 {len(p.equipment)} 件  冷卻 {cooldowns}")
    return lines


def do_restore(ch, arg):
    """restore <名字>、restore all：HP、MP、MV 補滿，技能冷卻清掉（照 C 版 act_wiz.c；清冷卻是使用者要的，方便測試）。

    名字先找同房間的（find_in_room：開頭就行、2.dog，生物也可以），找不到再找線上的玩家（名字開頭）。all 是所有在線的玩家。
    """
    words = arg.split()
    if not words:
        ch.send("恢復誰?\n")
        return
    if words[0].lower() == "all":
        for p in online_players():
            refill(p)
            if p is not ch:
                act("$n恢復了你身上的全滿狀態。", ch, p, to=TO_VICT)
        ch.send("啊 ... 所有指數全滿囉!!\n")
        return
    victim = find_in_room(ch, words[0]) or names.pick(online_players(), words[0], lambda c: c.names())
    if victim is None:
        ch.send("他們不在這兒。\n")
        return
    refill(victim)
    if victim is ch:
        ch.send("你身上的狀態全滿了。\n")
        return
    act("$n恢復了你身上全滿的狀態。", ch, victim, to=TO_VICT)
    act("你恢復了$N身上全滿的狀態。", ch, victim, to=TO_CHAR)
    log.info(f"{ch.name} 恢復了 {victim.name}")


def refill(c):
    """HP、MP、MV 補到上限（生物的 MP、MV 上限是 0），技能冷卻清掉。沒有屬性的（測試直接建的）只清冷卻。"""
    if c.panel:
        c.hp = c.panel["hp"]
        c.mp, c.mv = c.panel.get("mp", 0.0), c.panel.get("mv", 0.0)
    if hasattr(c, "cooldowns"):
        c.cooldowns.clear()


# affect 指令的測試效果（數字只是測試用，不是設計；真的效果之後由技能放）：名稱 → Affect 的欄位
TEST_EFFECTS = {
    "poison": dict(source="test_poison", name="測試毒", duration=60, periodic={"hp": -10.0},
                   off_message="你身上的【測試毒】退了。"),
    "regen": dict(source="test_regen", name="測試回復", duration=60, periodic={"hp": 10.0},
                  off_message="你身上的【測試回復】沒了。"),
    "bless": dict(source="test_bless", name="測試祝福", duration=60, applies={"hit": 10.0}, keep_on_death=True,
                  off_message="你身上的【測試祝福】沒了。"),
    "blind": dict(source="test_blind", name="測試失明", duration=30, flags=AffectFlag.BLIND,
                  off_message="你又看得見了。"),
    "shield": dict(source="test_shield", name="測試護盾", duration=10, shield_pct=1.2),
}
AFFECT_USAGE = f"用法：affect <名字> <{'、'.join([*TEST_EFFECTS, 'clear'])}>"


def do_affect(ch, arg):
    """affect <名字> <測試效果>：給角色放一個測試用的效果（poison、regen、bless、blind），clear 清掉全部的效果。

    名字跟 restore 一樣：先找同房間的（生物也可以），找不到再找線上的玩家。
    """
    words = arg.split()
    if len(words) < 2 or (words[1].lower() not in TEST_EFFECTS and words[1].lower() != "clear"):
        ch.send(AFFECT_USAGE + "\n")
        return
    victim = find_in_room(ch, words[0]) or names.pick(online_players(), words[0], lambda c: c.names())
    if victim is None:
        ch.send("他們不在這兒。\n")
        return
    which = words[1].lower()
    if which == "clear":
        affects.clear(victim)
        mine, theirs, own = "你清掉了$N身上全部的效果。", "$n清掉了你身上全部的效果。", "你清掉了身上全部的效果。"
        log.info(f"{ch.name} 清掉了 {victim.name} 身上全部的效果")
    else:
        a = affects.Affect(**TEST_EFFECTS[which])
        affects.add(victim, a)
        how_long = f"【{a.name}】（{a.duration * TICK_SECONDS:g} 秒）"
        mine, theirs, own = "你讓$N身上多了" + how_long + "。", "$n讓你身上多了" + how_long + "。", "你身上多了" + how_long + "。"
        log.info(f"{ch.name} 讓 {victim.name} 身上多了 {a.name}")
    if victim is ch:
        ch.send(own + "\n")
        return
    act(theirs, ch, victim, to=TO_VICT)
    act(mine, ch, victim, to=TO_CHAR)


def do_sset(ch, arg):
    """sset <名字> <技能> [off]：讓線上的玩家學會（off 是忘掉）一個技能（照 C 版的名字）。

    名字是線上的玩家（開頭就行）；技能名稱可以縮寫，全部的技能裡找。imm_only 的（天雷）不能給別人。
    """
    words = arg.split()
    if len(words) < 2 or len(words) > 3 or (len(words) == 3 and words[2].lower() != "off"):
        ch.send("用法：sset <名字> <技能> [off]\n")
        return
    victim = names.pick(online_players(), words[0], lambda c: c.names())
    if victim is None:
        ch.send("沒有找到這個玩家。\n")
        return
    word = words[1].lower()
    skill = next((s for s in skills.SKILLS.values() if s.id.startswith(word)), None)
    if skill is None:
        ch.send("沒有這個技能。\n")
        return
    if skill.imm_only:
        ch.send(f"{skill.name}只有 imm 會，不能給別人。\n")
        return
    if len(words) == 3:
        if not skills.forget(victim, skill):
            ch.send(f"{victim.name} 本來就不會{skill.name}。\n")
            return
        mine, theirs = f"{victim.name} 忘掉了{skill.name}。", f"你忘掉了{skill.name}。"
    else:
        if not skills.learn(victim, skill):
            ch.send(f"{victim.name} 已經會{skill.name}了。\n")
            return
        mine, theirs = f"{victim.name} 學會了{skill.name}。", f"你學會了{skill.name}！"
    log.info(f"{ch.name}：{mine}")
    if victim is ch:
        ch.send(theirs + "\n")
        return
    ch.send(mine + "\n")
    notify(victim, theirs)
