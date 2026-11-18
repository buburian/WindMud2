"""物品類指令：get、drop、put、give、wear、remove、inventory、equipment（玩家角色手冊「物品和裝備」，訊息照 C 版 act_obj.c）。

名字照 objects.find()（開頭就行、2.sword 是第 2 件），all 是全部（all 不分大小寫）。
一個指令的訊息合成一段送（inventory.Lines）：get all 撿好幾件，旁邊的人也只看到一個 prompt。
"""
import logging
import re

from .. import inventory, light, objects, save, scripts, stats
from ..act import TO_NOTVICT, TO_ROOM, TO_VICT
from ..characters import find_in_room
from ..npcs import Npc
from ..area import (ATTACK_NAMES, CONTAINER_ITEM_TYPE, CORPSE_NPC_ITEM_TYPE, ITEM_TYPE_NAMES, MONEY_ITEM_TYPE, WEAPON_KIND_NAMES,
                    ContainerFlag)
from ..equipment import COLOR_NAMES, SLOT_NAMES, STAT_NAMES, TWO_HANDED

CONTAINERS = (CONTAINER_ITEM_TYPE, CORPSE_NPC_ITEM_TYPE)     # get 東西 容器：可以從裡面拿的物品種類
GOLD_LOG = 1_000_000                        # give 這麼多金幣以上記 log（照 C 版）

log = logging.getLogger(__name__)


def is_all(word):
    return word.lower() == "all"


def sealed(obj):
    """封印著的容器撿不起來（照 C 版）。"""
    return obj.container is not None and ContainerFlag.SEALED in obj.container


def is_money(obj):
    """金錢：拿起來就變成身上的金幣，不進背包，所以不看件數、負重（照 C 版 get_obj）。"""
    return obj.item_type == MONEY_ITEM_TYPE


def do_get(ch, arg):
    """get <東西>、get all：撿地上的。get <東西> <容器>、get all <容器>：從屍體（容器）拿，容器在地上或背包裡。"""
    words = arg.split()
    if not words:
        ch.send("你想拿起什麼東西？\n")
        return
    out = inventory.Lines(ch)
    if len(words) == 1:
        get_from_floor(ch, words[0], out)
    else:
        get_from_container(ch, words[0], words[1], out)
    out.send()


def get_from_floor(ch, name, out):
    floor = light.floor(ch)                 # 很暗：看不到地上的東西（照 C 版）
    if is_all(name):
        take_all(ch, floor, None, out, "我沒看到任何的東西。")
        return
    obj = objects.find(floor, name)
    if obj is None:
        out.add("這裡找不到【$t】。", t=name)
    elif not obj.take:
        out.add("你不能拿起這樣東西。")
    elif sealed(obj):
        out.add("你無法拿起被封印的東西...")
    elif is_money(obj) or inventory.room_for(ch, obj, out):
        pick_up(ch, obj, floor, None, out)


def get_from_container(ch, name, where, out):
    if is_all(where):
        out.add("你不能這麼做。")
        return
    container = objects.find(light.floor(ch) + ch.carrying, where)
    if container is None:
        out.add("這裡沒有【$t】。", t=where)
        return
    if container.item_type not in CONTAINERS:
        out.add("這不是個容器。")
        return
    if container.closed():
        out.add("【$t】關起來了。", t=objects.short(container))       # 照 C 版
        return
    if is_all(name):
        take_all(ch, container.contains, container, out, EMPTY_CONTAINER)
        return
    obj = objects.find(container.contains, name)
    if obj is None:
        out.add("在【$t】裡面，找不到那樣東西。", t=objects.short(container))
    elif not obj.take:
        out.add("你不能拿起這樣東西。")
    elif container in ch.carrying or is_money(obj) or inventory.room_for(ch, obj, out):
        pick_up(ch, obj, container.contains, container, out)


EMPTY_CONTAINER = "在【$t】裡面沒有東西。"   # get all 容器：沒有拿得起來的（自動拾取也用）


def take_all(ch, source, container, out, nothing):
    """全部拿：撿不起來的（屍體、封印著的容器）靜靜跳過；拿不動了說一次，之後只再拿金幣（照 C 版會整個停，
    我們讓金幣照樣拿：不然金幣卡在屍體裡）。從自己背包裡的容器拿：件數、負重都沒變，不檢查（C 版會擋，我們修掉）。
    """
    found = full = False
    mine = container is not None and container in ch.carrying
    for obj in list(source):
        if not obj.take or sealed(obj):
            continue
        found = True
        if not (mine or is_money(obj)):
            if full:
                continue
            if not inventory.room_for(ch, obj, out):
                full = True
                continue
        pick_up(ch, obj, source, container, out)
    if not found:
        out.add(nothing, t=objects.short(container) if container else None)


def pick_up(ch, obj, source, container, out):
    """get、get all、自動拾取都從這裡拿：金錢變成身上的金幣（照 C 版 get_obj：2 枚以上說估算有幾枚，100 萬枚以上記 log），其他放進背包。"""
    source.remove(obj)
    if not is_money(obj):
        ch.carrying.insert(0, obj)
    if container is None:
        out.add("你拿起了【$t】。", t=objects.short(obj))
        out.add("$n拿起了【$t】。", TO_ROOM, t=objects.short(obj))
    else:
        out.add("你把【$t】從【$T】拿出來。", t=objects.short(obj), T=objects.short(container))
        out.add("$n把【$t】從【$T】拿出來。", TO_ROOM, t=objects.short(obj), T=objects.short(container))
    if is_money(obj):
        if obj.coins > 1:
            out.add("你估算一下裡面共有【$t】枚金幣。", t=str(obj.coins))
        ch.gold += obj.coins
        if obj.coins >= GOLD_LOG:
            log.info(f"{ch.name} 拿到 {obj.coins} 枚金幣" + (f"（從 {container.name}）" if container else ""))


def do_drop(ch, arg):
    """drop <東西>、drop all：放到地上（新的在前；不會消失，區域物件釋放時跟著不見）。
    綁住的東西丟不掉（照 C 版 nodrop：drop all 靜靜跳過，一件都沒丟就是「你沒有攜帶任何東西。」）。
    """
    words = arg.split()
    if not words:
        ch.send("你想丟掉什麼物品？\n")
        return
    out = inventory.Lines(ch)
    if is_all(words[0]):
        dropping = [o for o in ch.carrying if inventory.can_let_go(ch, o)]
        if not dropping:
            out.add("你沒有攜帶任何東西。")
        for obj in dropping:
            put_down(ch, obj, out)
    else:
        obj = objects.find(ch.carrying, words[0])
        if obj is None:
            out.add("你沒有這樣東西。")
        elif not inventory.can_let_go(ch, obj):
            out.add(CANT_DROP)
        else:
            put_down(ch, obj, out)
    out.send()


def do_put(ch, arg):
    """put <東西> <容器>、put all <容器>：把背包裡的東西放進地上或背包裡的容器（照 C 版 do_put，訊息照 C 版）。

    綁住的（裝著綁住的東西的容器也是）放不進去（設計文件 §3.10）；裡面的重量加這件超過容量（holds）放不進去。
    put all 不行的靜靜跳過（照 C 版），一件都沒放是「你沒有可以放進去的東西。」（新加的）。放完存檔（照 C 版）。
    """
    words = arg.split()
    if len(words) < 2:
        ch.send("你想把什麼東西放進容器裡？\n")
        return
    name, where = words[0], words[1]
    if is_all(where):
        ch.send("你不能這樣作。\n")
        return
    out, moved = inventory.Lines(ch), []
    container = objects.find(light.floor(ch) + ch.carrying, where)
    if container is None:
        out.add("這兒沒有【$t】。", t=where)
    elif container.item_type != CONTAINER_ITEM_TYPE:   # 屍體也不行（照 C 版）
        out.add("那不是個容器。")
    elif container.closed():
        out.add("【$t】關起來了。", t=objects.short(container))
    elif is_all(name):
        for obj in list(ch.carrying):
            if cannot_put(ch, obj, container) is None:     # 一件一件看：前面放進去的會佔掉容量
                put_in(ch, obj, container, out)
                moved.append(obj)
        if not moved:
            out.add("你沒有可以放進去的東西。")
    else:
        obj = objects.find(ch.carrying, name)
        reason = "你沒有這個物品。" if obj is None else cannot_put(ch, obj, container)
        if reason is not None:
            out.add(reason)
        else:
            put_in(ch, obj, container, out)
            moved.append(obj)
    out.send()
    if moved:
        keep(ch)


def cannot_put(ch, obj, container):
    """obj 放不進 container 的原因（照 C 版的順序），放得進去是 None。"""
    if obj is container:
        return "你不能把物品塞進它自己裡面。"
    if not inventory.can_let_go(ch, obj):
        return "你無法把它放進去。"
    if objects.weight(obj) + sum(objects.weight(o) for o in container.contains) > (container.holds or 0):
        return "它塞不進去。"
    return None


def put_in(ch, obj, container, out):
    """放進去（新的在前，照 C 版）。"""
    ch.carrying.remove(obj)
    container.contains.insert(0, obj)
    out.add("你把【$t】放進【$T】裡面。", t=objects.short(obj), T=objects.short(container))
    out.add("$n把【$t】放進【$T】裡面。", TO_ROOM, t=objects.short(obj), T=objects.short(container))


CANT_DROP = "你無法丟掉這樣東西。"          # 綁住的東西（照 C 版 nodrop 的那句）
CANT_GIVE = "你無法讓它離開你。"


def put_down(ch, obj, out):
    ch.carrying.remove(obj)
    ch.room.contents.insert(0, obj)
    out.add("你丟下了【$t】。", t=objects.short(obj))
    out.add("$n丟下了【$t】。", TO_ROOM, t=objects.short(obj))


def do_give(ch, arg):
    """give <東西> <名字>：把背包裡的東西給同房間的人（玩家或生物）。give <數量> coins <名字>：給金幣。

    照 C 版 act_obj.c 的 do_give（使用者定的）：綁住的給不出去（照 C 版 nodrop）；店主不收東西；對方是玩家要放得下（件數、負重）；
    給完幫給的人存檔（C 版是 do_save，防止當機時東西變兩份；我們不印 do_save 的「Ok.」）。看不看得到、任務物品還沒做。
    """
    words = arg.split()
    if len(words) < 2:
        ch.send("你想把什麼物品給誰？\n")
        return
    if re.fullmatch(r"[+-]?\d+", words[0]):  # C 版的 is_number：give 100 coins ming
        give_gold(ch, words)
        return
    obj = objects.find(ch.carrying, words[0])
    if obj is None:
        ch.send("你沒有這樣東西。\n")
        return
    victim = find_in_room(ch, words[1])
    if victim is None:
        ch.send("他們不在這裡。\n")
        return
    if not inventory.can_let_go(ch, obj):
        ch.send(CANT_GIVE + "\n")
        return
    out, name = inventory.Lines(ch), objects.short(obj)
    if getattr(victim, "shopkeeper", False):          # 店主不收（C 版：沒有腳本的店主）
        out.add("$N拒絕拿【$t】。", t=name, vch=victim)
        out.add("$n想要拿【$t】給$N，但是$E拒絕了。", TO_NOTVICT, t=name, vch=victim)
        out.add("你拒絕拿$n的【$t】。", TO_VICT, t=name, vch=victim)
        out.send()
        return
    reason = inventory.over_limit(victim, obj)
    if reason is not None:
        out.add("$N沒辦法攜帶這麼多的物品。" if reason == "count" else "$N沒辦法攜帶這麼重的物品。", vch=victim)
        out.send()
        return
    ch.carrying.remove(obj)
    victim.carrying.insert(0, obj)
    out.add(GIVEN_SEEN, TO_NOTVICT, t=name, vch=victim)
    out.add(GIVEN_TO_YOU, TO_VICT, t=name, vch=victim)
    out.add("你把【$t】拿給$N。", t=name, vch=victim)
    out.send()
    keep(ch)
    if isinstance(victim, Npc):             # 腳本的 on_give(actor, item, gold)：給完以後
        scripts.fire_owner(victim, "on_give", ch, ch, obj.vnum, 0)


GIVEN_TO_YOU = "$n把【$t】拿給你。"           # 給東西：收到的人看到的（照 C 版；腳本的 give_item 也用，使用者要的）
GIVEN_SEEN = "$n將【$t】拿給$N。"           # 給東西：旁邊的人看到的


def give_gold(ch, words):
    """give <數量> coins <名字>（照 C 版）：1 級不能給；給這麼多以上記 log。"""
    amount = int(words[0])
    if amount <= 0 or not "coins".startswith(words[1].lower()):
        ch.send("抱歉，你不能這樣做。\n")
        return
    if len(words) < 3:
        ch.send("你想把什麼物品給誰？\n")
        return
    victim = find_in_room(ch, words[2])
    if victim is None:
        ch.send("他們不在這裡。\n")
        return
    if ch.gold < amount:
        ch.send("你沒有這麼多金幣。\n")
        return
    if getattr(ch, "level", 1) <= 1:
        ch.send("你的等級不足以給人金幣。\n")
        return
    if amount >= GOLD_LOG:
        log.info(f"{ch.name} 給了 {victim.name} {amount} 枚金幣")
    ch.gold -= amount
    victim.gold += amount
    out = inventory.Lines(ch)
    out.add("你給$N一些金幣。", vch=victim)
    out.add("$n給你【$t】枚金幣。", TO_VICT, t=str(amount), vch=victim)
    out.add("$n給$N一些金幣。", TO_NOTVICT, vch=victim)
    out.send()
    keep(ch)
    if isinstance(victim, Npc):
        scripts.fire_owner(victim, "on_give", ch, ch, None, amount)


def keep(ch):
    """給完幫給的人存檔（照 C 版）：生物、沒有屬性的角色不存；存檔失敗記 log。"""
    if not inventory.is_player(ch):
        return
    try:
        save.save_player(ch)
    except OSError:
        log.exception(f"{ch.name} 給完東西存檔失敗")


def do_wear(ch, arg):
    """wear <東西>：穿上，部位有東西就先換下來（照 C 版）。wear all：背包裡能穿的穿到空的部位（不換下東西）。"""
    words = arg.split()
    if not words:
        ch.send("你想要裝備些什麼？\n")
        return
    if not inventory.is_player(ch):         # 使用者說生物不穿裝備
        ch.send("你沒有辦法使用這項物品。\n")
        return
    out = inventory.Lines(ch)
    if is_all(words[0]):
        # 副手武器放最後：主手的武器先穿上，副手才能雙持
        wearable = sorted((o for o in ch.carrying if o.slot is not None), key=lambda o: o.slot == "offhand" and o.is_weapon())
        if not wearable:
            out.add("你沒有可以裝備的東西。")
        for obj in wearable:
            inventory.wear(ch, obj, False, out)
    else:
        obj = objects.find(ch.carrying, words[0])
        if obj is None:
            out.add("你沒有攜帶這項物品。")
        else:
            inventory.wear(ch, obj, True, out)
    inventory.changed(ch)
    out.send()


def do_remove(ch, arg):
    """remove <東西>、remove all：卸下來放回背包（remove all 照 eq 的順序，副手在主手前面）。"""
    words = arg.split()
    if not words:
        ch.send("你想要卸下什麼東西？\n")
        return
    if not inventory.is_player(ch):
        ch.send("你沒有辦法使用這項物品。\n")
        return
    out = inventory.Lines(ch)
    worn = [ch.equipment[pos] for pos, _ in inventory.SLOTS if pos in ch.equipment]
    if is_all(words[0]):
        if not worn:
            out.add("你身上沒有穿任何裝備。")
        for obj in worn:
            inventory.take_off(ch, obj, out)
    else:
        obj = objects.find(worn, words[0])
        if obj is None:
            out.add("你身上沒有這項物品。")
        else:
            inventory.take_off(ch, obj, out)
    inventory.changed(ch)
    out.send()


def do_inventory(ch, arg):
    """inventory（i、inv）：背包裡的東西，每件一行前面空 5 格（照 C 版），最後是件數和負重（使用者選的）。"""
    lines = ["你目前所攜帶的東西有："] + ([f"     {objects.short(o)}{bound_tag(o)}" for o in ch.carrying] or ["     空無一物。"])
    if inventory.is_player(ch):
        lines.append(f"（{inventory.carry_count(ch)}/{stats.CARRY_COUNT} 件，"
                     f"負重 {stats.shown(inventory.carry_weight(ch))}/{stats.shown(stats.carry_limit(ch))}）")
    ch.send("\n".join(lines) + "\n")


def bound_tag(obj):
    """inventory、equipment 裡綁住的東西名字後面加「（綁定）」（設計文件 §3.10）；別的地方的名字不加。"""
    return BOUND_TAG if objects.bound(obj) else ""


BOUND_TAG = "（綁定）"


def do_equipment(ch, arg):
    """equipment（eq）：穿在身上的，照部位的順序（照 C 版 where_name），空的不列。"""
    rows = [f" 【 {inventory.label(pos, ch.equipment[pos])} 】 {objects.short(ch.equipment[pos])}{bound_tag(ch.equipment[pos])}"
            for pos, _ in inventory.SLOTS if pos in ch.equipment]
    ch.send("\n".join(["你現在正在使用：", "", *(rows or ["沒有裝備。"])]) + "\n")


def do_examine(ch, arg):
    """examine（ex）：看背包裡或身上穿的物品的基本屬性（使用者要的：只看這兩個地方）。句型照 C 版的 identify。"""
    words = arg.split()
    if not words:
        ch.send("你想要檢查些什麼？\n")
        return
    worn = [ch.equipment[pos] for pos, _ in inventory.SLOTS if pos in ch.equipment]
    obj = objects.find(ch.carrying + worn, words[0])
    if obj is None:
        ch.send("你身上沒有這樣東西。\n")
        return
    ch.send("\n".join(identify(obj)) + "\n")


def identify(obj):
    """exam 的每一行：名稱和種類、重量和等級（有顏色才寫稀有度），裝備才有部位，武器、護具、加成有才列。"""
    kind = ITEM_TYPE_NAMES.get(obj.item_type, str(obj.item_type))
    lines = [f"物品名稱：【{objects.short(obj)}】，型式：【{kind}】",
             f"重量：【{obj.weight}】，使用等級：【{obj.level}】" + (f"，稀有度：【{COLOR_NAMES[obj.color]}】" if obj.color else "")]
    if obj.slot is not None:
        lines.append(f"穿戴部位：【{'雙手' if obj.slot == TWO_HANDED else SLOT_NAMES[obj.slot]}】")
    if obj.is_weapon():
        lines.append(f"武器：【{WEAPON_KIND_NAMES[obj.weapon_kind]}】，攻擊方式：【{ATTACK_NAMES[obj.attack]}】")
        if "dmg_min" in obj.base:
            low, high = obj.base["dmg_min"], obj.base["dmg_max"]
            lines.append(f"攻擊力範圍：【{stats.shown(low)} - {stats.shown(high)}】（平均【{stats.shown((low + high) / 2)}】）")
    if "ac" in obj.base:
        lines.append(f"防護力：【{stats.shown(obj.base['ac'])}】")
    if obj.affects:
        lines.append("加成：" + "、".join(f"{STAT_NAMES[a.name.lower()]} {n:+}" for a, n in obj.affects))
    if obj.bind is not None:
        lines.append(f"綁定：【{objects.BIND_NAMES[obj.bind]}】，{'已經綁住了' if objects.bound(obj) else '還沒綁住'}。")
    return lines
