"""商店的指令：list、buy、sell、value（設計文件 §3.7，規則在玩家角色手冊「商店」）。找店主、價格在 shops.py。

訊息照 C 版（act_obj.c 的 do_list、do_buy、do_sell、do_value）；店主說的是「$n告訴你：」（TO_VICT）。
不照 C 版的（使用者定的或我們統一的）：
- 買的時候不看等級（穿、用的時候本來就會擋，使用者選的）。
- 賣掉的東西直接消失（使用者選的），所以沒有 C 版「店裡同一種越多收購價越低」。
- buy_types 沒有的種類就不收（C 版會用 1 枚金幣收，是 bug）；value 跟 sell 做一樣的檢查。
- 容器裡還有東西不能賣（不然裡面的東西會跟著消失）。
"""
from .. import inventory, objects, shops, stats
from ..act import TO_CHAR, TO_ROOM, TO_VICT, act
from . import items, system


def told(keeper, ch, fmt, t=None, T=None):
    """店主告訴 ch 一句（照 C 版的「$n告訴你：」）。"""
    act("$n告訴你：" + fmt, keeper, ch, t=t, T=T, to=TO_VICT)


def opened(ch, name):
    """找店主、看有沒有開：不行就說那句、回傳 None。沒開時店主自己說（照 C 版 do_say）。"""
    keeper = shops.find_keeper(ch, name)
    if keeper is None:
        ch.send(shops.NO_SHOP + "\n")
        return None
    why = shops.closed(keeper)
    if why is not None:
        system.do_say(keeper, why)
        return None
    return keeper


def word(words, i):
    return words[i] if len(words) > i else ""


def do_list(ch, arg):
    """list [東西] [店主]：店裡賣的東西、等級、你買要付多少。東西寫 all 是全部（照 C 版：list all boy 看第二個店主的）。"""
    words = arg.split()
    keeper = opened(ch, word(words, 1))
    if keeper is None:
        return
    goods = shops.stock(keeper)
    if words and words[0].lower() != "all":
        w = words[0].lower()
        goods = [o for o in goods if any(k.startswith(w) for k in o.keywords)]
    if not goods:
        ch.send(("這裡沒有賣你想買的東西。" if words else "你不能夠在這裡買任何東西。") + "\n")
        return
    lines = ["【 Lv    價格】 物品："]
    lines += [f"【{o.level:>3} {shops.buy_price(ch, keeper, o):>7}】 {objects.short(o)}" for o in goods]
    ch.send("\n".join(lines) + "\n")


def do_buy(ch, arg):
    """buy [數量] 東西 [店主]：買的是展示那件的複製品（賣不完），扣金幣、存檔。"""
    words = arg.split()
    if not words:
        ch.send("你想買什麼東西呢？\n")
        return
    count = 1
    if words[0].isdecimal():                # 坑：用 isdecimal，isdigit 認得「①」但 int() 不認得
        count, words = int(words[0]), words[1:]
    keeper = opened(ch, word(words, 1))
    if keeper is None:
        return
    obj = objects.find(shops.stock(keeper), words[0]) if words else None
    if obj is None:
        told(keeper, ch, "我不賣那樣東西 -- 試試看【list】這個指令。")
        return
    if count < 1:
        ch.send("你想要買多少樣？數字必須大於【0】。\n")
        return
    name, each = objects.short(obj), shops.buy_price(ch, keeper, obj)
    if ch.gold < each * count:
        if count == 1:
            told(keeper, ch, "你沒有足夠的金幣買下【$t】。", t=name)
        elif ch.gold // each > 0:
            told(keeper, ch, "你只能夠買下【$t】個!!", t=str(ch.gold // each))
        else:
            told(keeper, ch, "好可憐，你連一個都買不起。")
        return
    # 件數每個人都算（防止買太多個卡住）；負重只算玩家（生物沒有主屬性）
    if inventory.carry_count(ch) + count * objects.count(obj) > stats.CARRY_COUNT:
        ch.send("你沒有辦法攜帶這麼多的物品。\n")
        return
    if inventory.is_player(ch) and inventory.carry_weight(ch) + count * objects.weight(obj) > stats.carry_limit(ch):
        ch.send("你沒有辦法攜帶這麼重的物品。\n")
        return
    ch.gold -= each * count
    for _ in range(count):
        ch.carrying.insert(0, objects.from_data(objects.to_data(obj)))   # 複製品：不是 for_sale（不存檔的欄位）
    out = inventory.Lines(ch)
    if count == 1:
        out.add("你買下了【$t】。", t=name)
        out.add("$n買下了【$t】。", TO_ROOM, t=name)
    else:
        out.add("你一次買下了【$T】個【$t】。", t=name, T=str(count))
        out.add("$n一次買下了【$T】個【$t】。", TO_ROOM, t=name, T=str(count))
    out.send()
    items.keep(ch)


def offer(ch, keeper, obj):
    """keeper 收 obj 要付多少（sell、value 共用）：不收就說那句、回傳 None。"""
    name = objects.short(obj)
    if not shops.buys(keeper, obj):
        act("$n絲毫沒有買下【$t】的興趣。", keeper, ch, t=name, to=TO_VICT)
        return None
    if obj.level > keeper.level:
        told(keeper, ch, "你這東西的等級太高了，我買不起..!!")
        return None
    if obj.contains:
        act("你要先把【$t】裡面的東西拿出來。", ch, t=name, to=TO_CHAR)
        return None
    return shops.sell_price(ch, keeper, obj)


def do_sell(ch, arg):
    """sell 東西 [店主]：賣背包裡的東西，東西消失（使用者選的），拿金幣、存檔。"""
    words = arg.split()
    if not words:
        ch.send("你想要賣掉些什麼？\n")
        return
    keeper = opened(ch, word(words, 1))
    if keeper is None:
        return
    obj = objects.find(ch.carrying, words[0])
    if obj is None:
        told(keeper, ch, "你沒有你所要賣的東西。")
        return
    gold = offer(ch, keeper, obj)
    if gold is None:
        return
    ch.carrying.remove(obj)
    ch.gold += gold
    out, name = inventory.Lines(ch), objects.short(obj)
    out.add("你賣掉【$t】，老闆給了你【$T】枚金幣。", t=name, T=str(gold))
    out.add("$n賣掉【$t】。", TO_ROOM, t=name)
    out.send()
    items.keep(ch)


def do_value(ch, arg):
    """value 東西 [店主]：問店主收這件東西給多少（跟 sell 一樣的檢查）。"""
    words = arg.split()
    if not words:
        ch.send("你想評估什麼物品的價錢？\n")
        return
    keeper = opened(ch, word(words, 1))
    if keeper is None:
        return
    obj = objects.find(ch.carrying, words[0])
    if obj is None:
        told(keeper, ch, "你有這樣東西嗎？")
        return
    gold = offer(ch, keeper, obj)
    if gold is not None:
        told(keeper, ch, "我可以以【$T】枚金幣的價錢買下【$t】。", t=objects.short(obj), T=str(gold))
