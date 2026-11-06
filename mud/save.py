"""存檔：一個角色一個 JSON 檔（PLAYER_DIR/名字小寫.json），密碼只存雜湊。

存檔也寫一份全部次要屬性（panel，使用者要的：打開檔案就看得到全屬性），
但讀檔時一律用主屬性、等級、公會從頭算，蓋掉檔案裡那一份（設計文件 §8.2），公式改了舊角色也對得上。
"""
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

from . import affects, objects, skills, stats, zones
from .config import PLAYER_DIR
from .players import Player

SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}   # hashlib.scrypt 的參數：一次大約 50 毫秒，要在別的執行緒算（asyncio.to_thread）


def path_of(name):
    return Path(PLAYER_DIR) / f"{name.lower()}.json"


def exists(name):
    return path_of(name).exists()


def hash_password(password):
    """密碼 → "scrypt$鹽$雜湊"（每個角色自己的隨機鹽）。"""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, **SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_password(password, stored):
    """password 跟存的雜湊對不對得上。"""
    _, salt, digest = stored.split("$")
    mine = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt), **SCRYPT)
    return hmac.compare_digest(mine.hex(), digest)


def save_player(player):
    """把玩家寫進存檔。先寫暫存檔再換名字，存到一半斷掉也不會把舊檔弄壞。"""
    data = {
        "name": player.name, "password": player.password, "sex": player.sex,
        "race": player.race, "guild": player.guild, "level": player.level, "exp": player.exp,
        "primaries": player.primaries, "resource_roll": player.resource_roll,
        "points": player.points, "trained": player.trained, "imm": player.imm, "gold": player.gold,
        "skills": player.skills,
        "hp": player.hp, "mp": player.mp, "mv": player.mv,
        "room": player.room.vnum,
        "panel": player.panel,
        # 背包和裝備：整件存（詞綴、基本值都在裡面），區域檔之後改了身上的照舊
        "carrying": [objects.to_data(o) for o in player.carrying],
        "equipment": {pos: objects.to_data(o) for pos, o in player.equipment.items()},
        # 身上的效果：剩下的時間、跳到哪裡都存，登入後接著跑（離線時間停住，使用者定的）
        "affects": [affects.to_data(a) for a in player.affects],
    }
    path = path_of(player.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_data(name):
    """讀存檔，沒有這個角色是 None。"""
    path = path_of(name)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def player_from(data, writer):
    """用存檔的資料做出 Player：次要屬性從頭算，HP、MP、MV 夾在新的上限以內。

    存的房間在世界區域裡就站那裡；動態區域、副本離線就重來，站在起始房間。
    """
    room = zones.world.rooms.get(data["room"]) or zones.start_room()
    player = Player(data["name"], writer, room, data["sex"])
    player.password = data["password"]
    player.race, player.guild = stats.Race(data["race"]), stats.Guild(data["guild"])
    player.level, player.primaries = data["level"], data["primaries"]
    player.resource_roll = data["resource_roll"]
    # 後來才加的欄位：舊存檔沒有，當作 0、不是 imm、沒有金幣、身上沒東西、沒有效果；技能補上一開始就會的
    player.exp = data.get("exp", 0.0)
    player.points = data.get("points", 0)
    player.trained = {k: data.get("trained", {}).get(k, 0) for k in stats.PRIMARY_KEYS}
    player.imm = data.get("imm", False)
    player.gold = data.get("gold", 0)
    player.skills = data["skills"] if "skills" in data else skills.starter(player.guild)   # 舊存檔沒有：補上公會一開始就會的
    player.carrying = [objects.from_data(d) for d in data.get("carrying", [])]
    player.equipment = {pos: objects.from_data(d) for pos, d in data.get("equipment", {}).items()}
    player.affects = [affects.from_data(d) for d in data.get("affects", [])]
    stats.recompute(player)                 # 裝備、效果先放回去，屬性才算得到
    player.hp, player.mp, player.mv = (min(data[k], player.panel[k]) for k in ("hp", "mp", "mv"))
    return player
