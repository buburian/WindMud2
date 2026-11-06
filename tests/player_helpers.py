"""測試用：先做好角色的存檔，測試就能直接用密碼登入，不用每次走建立流程。"""
from mud import save, skills, stats, zones
from mud.players import Player

PASSWORD = "secret"


def make_player_file(name, room=101, race=stats.Race.HUMAN, guild=stats.Guild.SWORD):
    """存一個 1 級角色到 save.PLAYER_DIR（測試要先 monkeypatch 成 tmp_path），密碼是 PASSWORD。要先 zones.load()。"""
    p = Player(name, None, zones.world.rooms[room])
    p.password = save.hash_password(PASSWORD)
    p.race, p.guild = race, guild
    p.primaries = dict(stats.RACE_PRIMARIES[race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.skills = skills.starter(guild)            # 跟建立角色一樣：公會一開始就會的技能
    stats.recompute(p)
    p.hp, p.mp, p.mv = p.panel["hp"], p.panel["mp"], p.panel["mv"]
    save.save_player(p)
    return p
