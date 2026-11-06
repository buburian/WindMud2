"""物品類指令：get、drop、wear、remove、inventory、equipment（玩家角色手冊「物品和裝備」，訊息照 C 版 act_obj.c）。

名字照 objects.find()（開頭就行、2.sword 是第 2 件），all 是全部（all 不分大小寫）。
一個指令的訊息合成一段送（inventory.Lines）：get all 撿好幾件，旁邊的人也只看到一個 prompt。
"""
from .. import inventory, objects, stats
from ..act import TO_ROOM
from ..area import ATTACK_NAMES, CONTAINER_ITEM_TYPE, CORPSE_NPC_ITEM_TYPE, ITEM_TYPE_NAMES, WEAPON_KIND_NAMES
from ..equipment import COLOR_NAMES, SLOT_NAMES, STAT_NAMES, TWO_HANDED

CONTAINERS = (CONTAINER_ITEM_TYPE, CORPSE_NPC_ITEM_TYPE)     # get 東西 容器：可以從裡面拿的物品種類


def is_all(word):
    return word.lower() == "all"


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
    floor = ch.room.contents
    if is_all(name):
        take_all(ch, floor, None, out, "我沒看到任何的東西。")
        return
    obj = objects.find(floor, name)
    if obj is None:
        out.add("這裡找不到【$t】。", t=name)
    elif not obj.take:
        out.add("你不能拿起這樣東西。")
    elif inventory.room_for(ch, obj, out):
        pick_up(ch, obj, floor, None, out)


def get_from_container(ch, name, where, out):
    if is_all(where):
        out.add("你不能這麼做。")
        return
    container = objects.find(ch.room.contents + ch.carrying, where)
    if container is None:
        out.add("這裡沒有【$t】。", t=where)
        return
    if container.item_type not in CONTAINERS:
        out.add("這不是個容器。")
        return
    if is_all(name):
        take_all(ch, container.contains, container, out, "在【$t】裡面沒有東西。")
        return
    obj = objects.find(container.contains, name)
    if obj is None:
        out.add("在【$t】裡面，找不到那樣東西。", t=objects.short(container))
    elif not obj.take:
        out.add("你不能拿起這樣東西。")
    elif inventory.room_for(ch, obj, out):
        pick_up(ch, obj, container.contains, container, out)


def take_all(ch, source, container, out, nothing):
    """全部拿：撿不起來的（屍體）靜靜跳過；拿不動了說一次就停（照 C 版，不然訊息一直重複）。"""
    found = False
    for obj in list(source):
        if not obj.take:
            continue
        found = True
        if not inventory.room_for(ch, obj, out):
            break
        pick_up(ch, obj, source, container, out)
    if not found:
        out.add(nothing, t=objects.short(container) if container else None)


def pick_up(ch, obj, source, container, out):
    source.remove(obj)
    ch.carrying.insert(0, obj)
    if container is None:
        out.add("你拿起了【$t】。", t=objects.short(obj))
        out.add("$n拿起了【$t】。", TO_ROOM, t=objects.short(obj))
    else:
        out.add("你把【$t】從【$T】拿出來。", t=objects.short(obj), T=objects.short(container))
        out.add("$n把【$t】從【$T】拿出來。", TO_ROOM, t=objects.short(obj), T=objects.short(container))


def do_drop(ch, arg):
    """drop <東西>、drop all：放到地上（新的在前；不會消失，區域物件釋放時跟著不見）。"""
    words = arg.split()
    if not words:
        ch.send("你想丟掉什麼物品？\n")
        return
    out = inventory.Lines(ch)
    if is_all(words[0]):
        if not ch.carrying:
            out.add("你沒有攜帶任何東西。")
        for obj in list(ch.carrying):
            put_down(ch, obj, out)
    else:
        obj = objects.find(ch.carrying, words[0])
        if obj is None:
            out.add("你沒有這樣東西。")
        else:
            put_down(ch, obj, out)
    out.send()


def put_down(ch, obj, out):
    ch.carrying.remove(obj)
    ch.room.contents.insert(0, obj)
    out.add("你丟下了【$t】。", t=objects.short(obj))
    out.add("$n丟下了【$t】。", TO_ROOM, t=objects.short(obj))


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
    lines = ["你目前所攜帶的東西有："] + ([f"     {objects.short(o)}" for o in ch.carrying] or ["     空無一物。"])
    if inventory.is_player(ch):
        lines.append(f"（{len(ch.carrying)}/{stats.CARRY_COUNT} 件，"
                     f"負重 {stats.shown(inventory.carry_weight(ch))}/{stats.shown(stats.carry_limit(ch))}）")
    ch.send("\n".join(lines) + "\n")


def do_equipment(ch, arg):
    """equipment（eq）：穿在身上的，照部位的順序（照 C 版 where_name），空的不列。"""
    rows = [f" 【 {inventory.label(pos, ch.equipment[pos])} 】 {objects.short(ch.equipment[pos])}"
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
    return lines
