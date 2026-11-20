"""舊區域轉成我們的區域檔：uv run python -m mud.areaconvert 舊檔.json 新檔.json [--vnums 最小 最大] [--force]

舊檔是 mud_design 的 area2json 轉出來的 JSON（照 .are 原樣存，格式見 mud_design/tools/area_convert/README.md）。
轉出來的是我們的格式（docs/區域製作手冊.md），給區域編輯器接著改（流程：.are → area2json → 這裡 → 編輯器 → 伺服器）。
舊區域只重用敘述（使用者說的）：敘述、房間、出口、商店照搬，我們的格式寫不下的就拿掉，全部寫進報告。

規則（使用者 2026-11-17 定的，計畫裡列過）：
- 號碼照舊（完整號碼），範圍沒給就用檔案裡最小、最大的號碼。
- 旗標一律照名字換成我們的數字（兩邊的數字不一樣，例如 bless），我們沒有的拿掉。
- 通到這個檔以外的出口拿掉（別的區域還沒轉；指到的號碼也可能剛好是別的檔的房間）；門只寫一邊的補上另一邊。
- 生物：tier 先寫 normal、姿勢一律站著（C 版讀了就丟）、等級最少 1、種族照開頭比對手冊的表。
- 重置 E（生物穿裝備）：那件物品變成那隻生物掉落表裡 100% 掉落的白色裝備（不是裝備就不寫顏色），重置拿掉。
- 物品的加成（舊的屬性代號意思不一樣）、生物的 K 行、actions、fight_actions、C 版的腳本都不轉。
- 卷軸、藥水、魔杖、魔棒、藥錠（設計文件 §3.8）：法術照 SPELL_SKILLS 換成技能的 key；有一個換不了、或一個都沒寫，
  整件不轉，放它的重置（G、O、P）、掉落表（E）也拿掉。技能做好再把法術加進 SPELL_SKILLS。
- 食物（設計文件 §3.9）：values 第 1 個（C 版的飽足度）改成可以吃 1 口，第 2 個改成 ""（沒有 buff）。不會餓，毒也不做。
"""
import argparse
import json
from pathlib import Path

from . import area, equipment
from .area import (DEFAULT_ATTACK, MOB_ONLY_ATTACKS, MOB_RACES, REVERSE, SPECIALS, TWO_HANDED_KINDS, ActFlag, AffectFlag,
                   ExtraFlag, Locks, RoomFlag, Sector, WeaponKind, WearFlag)
from .characters import Position
from .specials import NOT_YET

CHANCE_ALWAYS = area.CHANCE_MAX             # E 變成的掉落：100%（使用者要的）
E_COLOR = "white"                           # E 變成的掉落：白色裝備（使用者要的）
LEVELS_ALL = [1, 100]                       # 舊檔頭的等級寫 All（不是數字）時
OBJECT_LEVEL = 1                            # 重置 O、P 的物品等級（舊版沒有，我們一定要寫）
SURE_RARE = 10                              # rare 0～10 一定出現；大於 10 是 (rare − 10) ÷ 10000（同 resets.SURE_RARE）
ARMOR_ITEM_TYPE = 9                         # 護具：values 第 1、3 格由裝備等級算，寫 0
USED_ROOM_FLAGS = RoomFlag.DARK | RoomFlag.NO_MOB | RoomFlag.INDOORS | RoomFlag.SAFE | RoomFlag.NO_RECALL   # 有作用的，其他照留、列進報告
# 武器種類照英文名字（keywords 裡第一個對得上的字），都對不上就是長劍
WEAPON_WORDS = {
    "dagger": WeaponKind.DAGGER, "knife": WeaponKind.DAGGER, "sword": WeaponKind.LONGSWORD,
    "scimitar": WeaponKind.SCIMITAR, "axe": WeaponKind.HANDAXE, "mace": WeaponKind.MACE, "club": WeaponKind.MACE,
    "hammer": WeaponKind.MACE, "whip": WeaponKind.WHIP, "claw": WeaponKind.CLAW, "bardiche": WeaponKind.BATTLEAXE,
    "spear": WeaponKind.SPEAR,
}
FALLBACK_WEAPON = WeaponKind.LONGSWORD
FOOD_BITES = 1                              # 食物轉過來可以吃幾口（設計文件 §3.9：C 版一次吃完）
# C 版的法術 → 我們的技能 key（設計文件 §3.8）：有對應技能的才寫，沒寫的法術那件物品就不轉
SPELL_SKILLS = {"fly": "fly", "breathe water": "breathe"}


class Report:
    """一條一條記：拿掉的（我們的格式寫不下）、轉的時候改過的、照留但遊戲還沒作用的。"""

    def __init__(self):
        self.dropped = []
        self.changed = []
        self.kept = []

    def lines(self):
        out = []
        for title, items in (("寫不進我們的格式，拿掉了", self.dropped), ("轉的時候改過的", self.changed),
                             ("照留，但遊戲裡還沒有作用", self.kept)):
            out += [f"{title}（{len(items)} 條）："] + [f"  - {x}" for x in items]
        return out


def flags(old, cls, where, report):
    """area2json 的旗標 {"value", "names"} 照名字換成我們的數字；我們沒有的名字記進報告。"""
    value = 0
    for name in old["names"]:
        if cls is ActFlag and name == "is_npc":             # C 版自動加的，手冊寫不用寫
            continue
        if name.upper() in cls.__members__:
            value |= cls[name.upper()]
        else:
            report.dropped.append(f"{where}{name}")
    return int(value)


def convert(old, name, vnums=None):
    """area2json 的資料 → (我們的區域檔資料, Report)。name 是新檔名（寫進 "file"）。"""
    report = Report()
    room_vnums = {r["vnum"] for r in old["rooms"]}
    if vnums is None:
        every = [x["vnum"] for k in ("rooms", "mobiles", "objects") for x in old[k]]
        vnums = [min(every), max(every)]
    rooms = {r["vnum"]: convert_room(r, room_vnums, report) for r in old["rooms"]}
    fill_doors(rooms, report)
    mobiles = {m["vnum"]: convert_mobile(m, report) for m in old["mobiles"]}
    objects = {o["vnum"]: convert_object(o, report) for o in old["objects"]}
    gone = {v for v, o in objects.items() if o is None}      # 不轉的物品（法術還沒有技能）：放它的重置、掉落表也拿掉
    objects = {v: o for v, o in objects.items() if o is not None}
    for shop in old["shops"]:
        keeper = mobiles.get(shop["keeper_vnum"])
        if keeper is None:
            report.dropped.append(f"商店的店主 {shop['keeper_vnum']} 不在這個檔")
            continue
        keeper["shop"] = {"buy_types": [t for t in shop["buy_types"] if t], "profit_buy": shop["profit_buy"],
                          "profit_sell": shop["profit_sell"], "open_hour": shop["open_hour"], "close_hour": shop["close_hour"]}
        report.kept.append(f"生物 {keeper['vnum']} {keeper['short']}的商店（商店還沒做）")
    for s in old["specials"]:
        if s["cmd"] != "M":
            continue
        mob = mobiles.get(s["mob_vnum"])
        if mob is None or s["function"] not in SPECIALS:
            report.dropped.append(f"生物 {s['mob_vnum']} 的 special {s['function']}")
            continue
        mob["special"] = s["function"]
        if s["function"] in NOT_YET:
            report.kept.append(f"生物 {mob['vnum']} {mob['short']}的 special {s['function']}（先不做）")
    resets = convert_resets(old["resets"], rooms, mobiles, objects, report, gone)
    header = old["area"]["header"] if old.get("area") else None
    numbered = header and header["level_min"] is not None and header["level_max"] is not None
    levels = [header["level_min"], header["level_max"]] if numbered else list(LEVELS_ALL)
    recall = old["area"]["recall"] if old.get("area") else None
    if recall is not None and recall not in room_vnums:
        report.dropped.append(f"area.recall {recall}（不是這個檔的房間）")
        recall = None
    for r in rooms.values():
        unused = RoomFlag(r["room_flags"]) & ~USED_ROOM_FLAGS
        if unused:
            report.kept.append(f"房間 {r['vnum']} {r['name']}的旗標 {flag_names(unused)}")
    data = {
        "schema_version": 1,
        "file": name,
        "area": {
            "header": {"levels": levels, "author": header["author"] if header else "", "title": header["title"] if header else name,
                       "vnums": list(vnums), "type": area.AreaType.WORLD.value, "reset_empty": None, "reset_players": None,
                       "opened": None},
            "recall": recall,
            "no_teleport": old["area"].get("no_teleport") if old.get("area") else None,
            "clan_recall": old["area"].get("clan_recall") if old.get("area") else None,
            "gem": old["area"].get("gem") if old.get("area") else None,
        },
        "rooms": list(rooms.values()),
        "mobiles": list(mobiles.values()),
        "objects": list(objects.values()),
        "resets": resets,
    }
    return data, report


def flag_names(value):
    return "、".join(f.name.lower() for f in type(value) if f in value)


def convert_room(r, room_vnums, report):
    where = f"房間 {r['vnum']} {r['name']}"
    exits = {}
    for d, e in r["exits"].items():
        if e["to_room"] not in room_vnums:      # 通到別的區域：別的區域還沒轉，先拿掉
            report.dropped.append(f"{where}往 {d} 通到別的區域的出口 {e['to_room']}")
            continue
        exits[d] = {"description": e["description"], "keywords": e["keywords"], "locks": e["locks"], "key": e["key"],
                    "to_room": e["to_room"]}
    if r.get("script"):
        report.dropped.append(f"{where}的 C 版腳本 {r['script']['function']}（觸發 {'、'.join(r['script']['trigger']['names'])}）")
    sector = r["sector"]["value"]
    if sector not in [s.value for s in Sector]:
        report.dropped.append(f"{where}的地形 {sector}（改成 0）")
        sector = 0
    return {"vnum": r["vnum"], "name": r["name"], "description": r["description"],
            "room_flags": flags(r["room_flags"], RoomFlag, f"{where}的旗標 ", report), "sector": sector,
            "exits": exits, "extra_descriptions": [dict(ed) for ed in r["extra_descriptions"]], "script": None}


def fill_doors(rooms, report):
    """門只寫一邊：對面有指回來的出口但沒有門，照有門的那邊補上（名字、種類、鑰匙）。"""
    for room in rooms.values():
        for d, e in room["exits"].items():
            back = rooms[e["to_room"]]["exits"].get(REVERSE[d])
            if e["locks"] != Locks.NO_DOOR and back and back["to_room"] == room["vnum"] and back["locks"] == Locks.NO_DOOR:
                back.update(keywords=e["keywords"], locks=e["locks"], key=e["key"])
                report.changed.append(f"房間 {e['to_room']} 往 {REVERSE[d]} 的門照房間 {room['vnum']} 那邊補上（門兩邊都要寫）")


def convert_mobile(m, report):
    where = f"生物 {m['vnum']} {m['short']}"
    race = next((r for r in MOB_RACES if r.startswith(m["race"].lower())), m["race"]) if m["race"] else m["race"]
    if race not in MOB_RACES:
        report.kept.append(f"{where}的種族 {m['race']}（手冊的表沒有，照寫）")
    elif race != m["race"]:
        report.changed.append(f"{where}的種族 {m['race']} 照開頭比對成 {race}")
    if m["level"] < 1:
        report.changed.append(f"{where}的等級 {m['level']} 改成 1")
    for key, label in (("custom", "K 行"), ("random_drop", "R 行")):
        if m.get(key):
            report.dropped.append(f"{where}的 {label} {m[key]}")
    if m.get("script"):
        report.dropped.append(f"{where}的 C 版腳本 {m['script']['function']}（觸發 {'、'.join(m['script']['trigger']['names'])}）")
    for a in m.get("actions") or []:
        report.dropped.append(f"{where}的平常動作（{a['when']['name']}）{a['text'].strip()}")
    for a in m.get("fight_actions") or []:
        report.dropped.append(f"{where}的戰鬥動作 {a['rate']}% {a['command'].strip()}")
    return {
        "vnum": m["vnum"], "keywords": m["keywords"], "short": m["short"], "long": m["long"], "description": m["description"],
        "level": max(1, m["level"]), "tier": area.MobTier.NORMAL.value, "tier_roll": None, "attack": None, "defense": None,
        "archetype": None, "act": flags(m["act"], ActFlag, f"{where}的 act ", report),
        "affected_by": flags(m["affected_by"], AffectFlag, f"{where}的 affected_by ", report),
        "alignment": m["alignment"], "race": race, "sex": m["sex"]["value"], "position": int(Position.STANDING),   # C 版讀了就丟
        "drops": [], "script": None, "shop": None, "special": None, "special_ratio": None, "poison_ratio": None,
    }


def convert_object(o, report):
    where = f"物品 {o['vnum']} {o['short']}"
    extra = flags(o["extra_flags"], ExtraFlag, f"{where}的 extra_flags ", report)
    wear = flags(o["wear_flags"], WearFlag, f"{where}的 wear_flags ", report)
    item_type, values = o["item_type"]["value"], list(o["values"])
    if item_type in area.SKILL_ITEM_TYPES:
        values = spells_to_skills(where, item_type, values, report)
        if values is None:
            return None
    elif item_type == area.FOOD_ITEM_TYPE:      # 一口吃完（C 版），沒有 buff
        values[0], values[1] = FOOD_BITES, ""
    if item_type not in area.ITEM_TYPE_NAMES:
        report.kept.append(f"{where}的種類 {item_type}（手冊的表沒有，照寫）")
    if item_type == area.WEAPON_ITEM_TYPE:
        kind = next((WEAPON_WORDS[w] for w in o["keywords"].lower().split() if w in WEAPON_WORDS), None)
        if kind is None:
            kind = FALLBACK_WEAPON
            report.changed.append(f"{where}的武器種類看不出來，先寫 {kind.value} {area.WEAPON_KIND_NAMES[kind]}")
        attack = values[3] if isinstance(values[3], int) and values[3] in [a.value for a in area.Attack] else None
        if attack is None or attack in MOB_ONLY_ATTACKS:
            attack = DEFAULT_ATTACK[kind].value
        values = [kind.value, 0, 0, attack]
        if kind in TWO_HANDED_KINDS:
            extra = int(extra | ExtraFlag.TWO_HANDED)
        if not wear & WearFlag.WIELD:
            report.changed.append(f"{where}照轉成武器，可是不能拿在手上（wear_flags 沒有 wield），要不要改種類你再決定")
    elif item_type == ARMOR_ITEM_TYPE:
        values[0] = values[2] = 0               # 防護力由裝備等級算
    if o["affects"]:
        text = "、".join(f"{a['location']['name']} {a['modifier']:+d}" for a in o["affects"])
        report.dropped.append(f"{where}的加成 {text}（舊的屬性代號，改成照等級和顏色抽）")
    if o.get("script"):
        report.dropped.append(f"{where}的 C 版腳本 {o['script']['function']}")
    return {"vnum": o["vnum"], "keywords": o["keywords"], "short": o["short"], "long": o["long"], "item_type": item_type,
            "extra_flags": extra, "wear_flags": wear, "values": values, "weight": o["weight"], "cost": o["cost"],
            "affects": [], "main_affix": None, "extra_descriptions": [dict(ed) for ed in o["extra_descriptions"]], "script": None}


def spells_to_skills(where, item_type, values, report):
    """會放技能的物品：法術換成技能的 key（SPELL_SKILLS）。有一個換不了、或一個都沒寫，回傳 None（整件不轉），寫進報告。"""
    slots = area.skill_slots(item_type)
    spells = [str(values[i]).strip() for i in slots]
    missing = [s for s in spells if s and s not in SPELL_SKILLS]
    if missing or not any(spells):
        why = f"法術 {'、'.join(missing)} 還沒有對應的技能" if missing else "沒有寫法術"
        report.dropped.append(f"{where}（{why}，整件拿掉，連同放它的重置）")
        return None
    for i, spell in zip(slots, spells):
        values[i] = SPELL_SKILLS.get(spell, "")
    report.changed.append(f"{where}的法術 {'、'.join(s for s in spells if s)} 換成技能 "
                          f"{'、'.join(SPELL_SKILLS[s] for s in spells if s)}")
    return values


def convert_resets(old, rooms, mobiles, objects, report, gone=frozenset()):
    """照順序轉。E 變成前面那筆 M 的生物的掉落表；D 指到沒有門的出口就拿掉。放不轉的物品（gone）的 G、O、P、E 也拿掉。"""
    out, last_mob = [], None
    for r in old:
        cmd = r["cmd"]
        if cmd in ("G", "O", "P", "E") and (r.get("obj_vnum") in gone or r.get("container_vnum") in gone):
            continue                        # 物品不轉，報告裡已經寫了
        if cmd == "*":
            out.append({"cmd": "*", "comment": r["comment"]})
        elif cmd == "M":
            last_mob = r["mob_vnum"]
            out.append({"cmd": "M", "rare": r["rare"], "mob_vnum": r["mob_vnum"], "limit": r["limit"],
                        "room_vnum": r["room_vnum"], "comment": r["comment"]})
        elif cmd == "G":
            out.append({"cmd": "G", "rare": r["rare"], "obj_vnum": r["obj_vnum"], "color": None, "level": None,
                        "limit": r["limit"], "comment": r["comment"]})
        elif cmd == "O":
            out.append({"cmd": "O", "if_flag": r["if_flag"], "obj_vnum": r["obj_vnum"], "color": None, "level": OBJECT_LEVEL,
                        "limit": r["limit"], "room_vnum": r["room_vnum"], "comment": r["comment"]})
        elif cmd == "P":
            out.append({"cmd": "P", "if_flag": r["if_flag"], "obj_vnum": r["obj_vnum"], "color": None, "level": OBJECT_LEVEL,
                        "limit": r["limit"], "container_vnum": r["container_vnum"], "comment": r["comment"]})
        elif cmd == "E":
            wear_into_drop(r, mobiles.get(last_mob), objects, report)
        elif cmd == "D":                        # area2json 的方向、狀態是 {"value", "name"}
            direction, state = r["direction"]["name"], r["state"]["value"]
            exit_ = rooms.get(r["room_vnum"], {"exits": {}})["exits"].get(direction)
            if exit_ is None or exit_["locks"] == Locks.NO_DOOR:
                report.dropped.append(f"重置 D：房間 {r['room_vnum']} 往 {direction} 沒有門（出口拿掉了，或沒寫門）")
                continue
            out.append({"cmd": "D", "if_flag": r["if_flag"], "room_vnum": r["room_vnum"], "direction": direction,
                        "state": state, "comment": r["comment"]})
        elif cmd == "R":
            out.append({"cmd": "R", "if_flag": r["if_flag"], "room_vnum": r["room_vnum"], "exit_count": r["exit_count"],
                        "comment": r["comment"]})
    return out


def wear_into_drop(r, mob, objects, report):
    """重置 E：生物穿的那件，變成牠掉落表裡 100% 掉落的白色裝備（使用者要的）。坐騎（wear_loc 100）沒有東西可以轉。"""
    if r.get("wear_loc", {}).get("value") == 100 or mob is None:
        report.dropped.append(f"重置 E {r.get('obj_vnum', r.get('mount_vnum'))}（坐騎，或前面沒有這個檔的生物）")
        return
    if any(d["obj_vnum"] == r["obj_vnum"] for d in mob["drops"]):
        return                                  # 同一隻被好幾筆 M 放、穿一樣的：只加一次
    obj = objects.get(r["obj_vnum"])
    color = E_COLOR if obj and equipment.best_slot(*area.wear_slots(obj)) else None   # 不是裝備就不寫顏色
    chance = CHANCE_ALWAYS if r["rare"] <= SURE_RARE else r["rare"] - SURE_RARE
    mob["drops"].append({"obj_vnum": r["obj_vnum"], "color": color, "chance": chance, "tiers": None})


def main(argv=None):
    p = argparse.ArgumentParser(description="舊區域（area2json 的 JSON）轉成我們的區域檔")
    p.add_argument("old", help="area2json 轉出來的 JSON")
    p.add_argument("new", help="要寫出的區域檔（例如 builder_area/midgaard.json）")
    p.add_argument("--vnums", nargs=2, type=int, metavar=("最小", "最大"), help="號碼範圍，沒給就用檔案裡最小、最大的號碼")
    p.add_argument("--force", action="store_true", help="新檔已經有了也蓋掉（在編輯器改過的會不見）")
    args = p.parse_args(argv)
    new = Path(args.new)
    if new.exists() and not args.force:
        print(f"{new} 已經有了：要蓋掉加 --force（在編輯器改過的會不見）")
        return 1
    old = json.loads(Path(args.old).read_text(encoding="utf-8"))
    data, report = convert(old, new.name, args.vnums)
    new.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")   # 跟編輯器存檔的格式一樣
    print(f"寫好 {new}：房間 {len(data['rooms'])}、生物 {len(data['mobiles'])}、物品 {len(data['objects'])}、重置 {len(data['resets'])}")
    print("\n".join(report.lines()))
    skip = {new.resolve(), Path(args.old).resolve()}     # 舊檔放在同一個資料夾時不能拿來對照（號碼會「重複」）
    others = [p for p in area.area_files(new.parent) if p.resolve() not in skip]
    problems = area.check_files([new], [new, *others])[new]
    print(f"檢查（對照同一個資料夾的其他區域檔）：{len(problems)} 個問題")
    print("\n".join(f"  - {x}" for x in problems))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
