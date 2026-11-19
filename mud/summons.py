"""召喚物（召喚類技能：喚骨術、死亡騎士，設計文件 §2.6）：叫出一隻生物幫主人打。

- 多強：跟一般的怪一樣給等級和種類（stats.mob_stats），等級比主人低 below 級（最低 1），種類看技能。不放進區域檔，這裡做出來。
- 牠自動打主人正在打的怪（世界每個 tick 看一次，tick()），不能指揮；怪打誰照原本的規則（還沒在打架的就打牠）。
- 跟著主人走（system.move 走完叫 follow()；recall、goto 這種被送走的，下一個 tick 跟過去）。不會自己走、不會主動攻擊。
- 同一個技能只能有一隻，再放就換掉舊的；不同技能叫的可以同時在。
- 時間到、主人死掉（death.player_dies）、主人離線就消失；被打死不留屍體、不給經驗、不掉東西（death.die）。
- 牠打死的怪：經驗、掉落算主人的（combat.slain）。打一群、群體治療不算牠，玩家也不能打牠（commands.combat.attackable）。
坑：death → summons → fight → combat → death 繞一圈，都用 from . import 模組。
"""
from . import fight, npcs, stats
from .act import TO_CHAR, TO_ROOM, act
from .area import ActFlag, MobTier
from .characters import arrive, characters
from .npcs import Npc

TYPES = {                                   # 技能 id → 這隻長什麼樣子（名字、英文名字、look 看到的那一行、描述、叫出來、消失的那句）
    "raise_skeleton": dict(name="骷髏", keywords=["skeleton"],
                           long="骷髏/skeleton/喀啦喀啦地站在主人身邊，眼窩裡沒有光。",
                           description="一具被法術喚醒的骷髏，骨頭上還黏著泥土，關節一動就喀啦作響。",
                           arrive="地面裂開，一具骷髏喀啦喀啦地爬了出來。", gone="$n散成一堆白骨。"),
    "death_knight": dict(name="死亡騎士", keywords=["knight"],
                         long="死亡騎士/knight/披著殘破的黑甲，一動也不動地守在主人身後。",
                         description="一名被法術召回的騎士，盔甲裡只剩一團冰冷的黑霧，手上的長劍鏽跡斑斑。",
                         arrive="一陣冷風颳過，一名死亡騎士從黑霧裡走了出來。", gone="$n化成一團黑霧，消散了。"),
}


def of(owner):
    """owner 叫出來、還在的召喚物。"""
    return [c for c in characters if isinstance(c, Npc) and c.master is owner]


def is_summon(ch):
    return isinstance(ch, Npc) and ch.master is not None


def summon(owner, skill):
    """owner 用 skill 叫出一隻（skill.summon：tier、below、duration）：同一個技能的舊的先消失。"""
    for old in of(owner):
        if old.summon_source == skill.id:
            dismiss(old)
    look, info = TYPES[skill.id], skill.summon
    npc = Npc(look["name"], 0, owner.room)
    npc.keywords, npc.long, npc.description = list(look["keywords"]), look["long"], look["description"]
    npc.level, npc.tier = max(1, owner.level - info["below"]), MobTier(info["tier"])
    npc.base_panel, npc.mix = stats.mob_stats(npc.level, info["tier"], None, None, None)
    npcs.recompute(npc)
    npc.hp = npc.panel["hp"]
    npc.act = ActFlag.SENTINEL               # 不會自己走
    npc.master, npc.summon_source, npc.summon_ticks = owner, skill.id, info["duration"]
    characters.append(npc)
    arrive(npc)
    act(look["arrive"], owner, to=TO_CHAR)
    act(look["arrive"], owner, to=TO_ROOM)
    return npc


def dismiss(npc):
    """牠消失（換掉、時間到、主人死掉或離線）：停手、從遊戲裡拿掉，同一間房的人看到 gone 那句。"""
    from . import death                     # 坑：death 會 import 這個模組，在函式裡才 import
    act(TYPES[npc.summon_source]["gone"], npc, to=TO_ROOM)
    death.stop_all(npc)
    characters.remove(npc)


def release(owner):
    """主人死掉：他的召喚物全部消失。"""
    for npc in of(owner):
        dismiss(npc)


def follow(owner, direction):
    """主人走了一步（system.move 走完）：同一間房（原本那間）的召喚物跟著走。"""
    from .commands import system            # 坑：commands 會 import 戰鬥的模組，在函式裡才 import
    for npc in of(owner):
        if npc.room is not owner.room and npc.room.exits.get(direction) == owner.room.vnum:
            system.move(npc, direction)


def tick():
    """世界每個 tick（skills.tick 呼叫）：每隻召喚物時間減 1；主人離線、時間到就消失；
    不在主人的房間（主人被送走了）就過去；主人在打架、牠沒在打就打主人的對手（還沒在打架的怪就打牠）。
    """
    for npc in [c for c in characters if is_summon(c)]:
        npc.summon_ticks -= 1
        owner = npc.master
        if owner not in characters or npc.summon_ticks <= 0:
            dismiss(npc)
            continue
        if npc.room is not owner.room:
            fight.stop_fighting(npc)
            npc.room = owner.room
            arrive(npc)
        foe = owner.fighting
        if foe is not None and npc.fighting is None and foe in characters and foe.room is npc.room:
            fight.start_fight(npc, foe)
