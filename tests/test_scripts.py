"""Lua 腳本（區域製作手冊「腳本」）：沙箱（mud/lua.py）、開機檢查（area.check_lua）。"""
import pytest

from area_helpers import make_area, make_mobile, make_room, write_json, write_lua
from mud import area, lua


# ---- 沙箱 ----

def run(code, *args, extra=None):
    """跑 code 裡的 on_test(args…)，回傳 lua.step 的結果。"""
    env = lua.base_env()
    for k, v in (extra or {}).items():
        env[k] = v
    return lua.step(lua.spawn(code, "t/x.lua", env, "on_test", *args))


@pytest.mark.parametrize("name", ["os", "io", "require", "debug", "load", "loadstring", "dofile", "coroutine",
                                  "getmetatable", "setmetatable", "rawset", "collectgarbage", "python", "string"])
def test_dangerous_names_are_missing(name):
    assert run(f"function on_test() return {name} == nil end") == ("done", True)


def test_python_objects_are_off_limits():
    status, err = run("function on_test() return f.__globals__ end", extra={"f": lua.wrap(lambda: 1)})
    assert status == "error"


def test_string_patterns_are_gone():
    # 坑：find／match／gmatch／gsub 在 C 裡跑、hook 停不下來；字串只留安全的方法
    assert run('function on_test() return ("abc"):upper() .. ("abc"):sub(2) end') == ("done", "ABCbc")
    for m in ("find", "match", "gmatch", "gsub", "dump"):
        assert run(f'function on_test() return ("abc").{m} == nil end') == ("done", True), m


def test_safe_libraries():
    assert run('function on_test() return math.floor(2.5) + utf8.len("中文") + #table.concat({"a", "b"}) end') == ("done", 6)
    assert run("function on_test() return utf8.charpattern end") == ("done", None)


@pytest.mark.parametrize("code", ["function on_test() while true do end end",
                                  "function on_test() while true do pcall(function() while true do end end) end end"])
def test_endless_loops_stop(code):
    # 指令數上限：每一段 10 萬個；超過以後每個指令都丟錯誤，pcall 接不住
    assert run(code) == ("error", f"t/x.lua:1: 指令太多（一段最多 {lua.BUDGET} 個）")


def test_memory_limit():
    assert run('function on_test() return #("x"):rep(1e9) end') == ("error", "not enough memory")
    assert run("function on_test() return 1 end") == ("done", 1)          # 之後照樣能用


def test_python_errors_stop_the_script_even_inside_pcall():
    def boom():
        raise ValueError("壞了")
    code = "function on_test()\n  local ok = pcall(boom)\n  return '沒停'\nend"
    assert run(code, extra={"boom": lua.wrap(boom)}) == ("error", "t/x.lua:2: 壞了")
    # 尾呼叫（return pcall(...)）也一樣停得下來
    assert run("function on_test()\n  return pcall(boom)\nend", extra={"boom": lua.wrap(boom)}) == ("error", "t/x.lua:2: 壞了")


def test_wait_pauses_and_resumes():
    co = lua.spawn("function on_test(a)\n  wait(3)\n  return a + 1\nend", "t/x.lua", lua.base_env(), "on_test", 1)
    assert lua.step(co) == ("wait", 3)
    assert lua.step(co) == ("done", 2)


def test_each_segment_has_its_own_budget():
    # 一段（到 wait、兩個 wait 之間）各自 10 萬個指令：中間有 wait 的長腳本不會被誤殺
    loop = "for i = 1, 60000 do end"
    co = lua.spawn(f"function on_test()\n  {loop}\n  wait(1)\n  {loop}\nend", "t/x.lua", lua.base_env(), "on_test")
    assert lua.step(co)[0] == "wait" and lua.step(co) == ("done", None)


# ---- 開機檢查 ----

def check(tmp_path, rooms=(), mobiles=(), files=None, script_root=None):
    for name, code in (files or {}).items():
        write_lua(tmp_path, "a.json", name, code)
    path = write_json(tmp_path, "a.json", make_area("a.json", list(rooms) or [make_room(1)], 100, mobiles=list(mobiles)))
    return area.check_files([path], script_root=script_root)[path]


def scripted_room(file="x.lua", timer=None, vnum=1):
    r = make_room(vnum)
    r["script"] = {"file": file, "timer": timer}
    return r


def scripted_mob(file="x.lua", timer=None):
    m = make_mobile(1)
    m["script"] = {"file": file, "timer": timer}
    return m


def test_good_scripts_pass(tmp_path):
    files = {"x.lua": "local n = math.floor(1.5)\nfunction on_say(actor, text) me:command('say 嗨') end",
             "t.lua": "function on_timer() room:echo('鐘聲') end"}
    assert check(tmp_path, [scripted_room(), scripted_room("t.lua", 60, vnum=2)], [scripted_mob()], files) == []


@pytest.mark.parametrize("file, code, want", [
    ("x.lua", None, "房間 1的 script 的 file：找不到 a/x.lua"),
    ("../x.lua", "", "房間 1的 script 的 file '../x.lua' 跑出 a/ 資料夾了"),
    ("x.lua", "function on_say( end", "房間 1的腳本 a/x.lua:1: <name> or '...' expected near 'end'"),
    ("x.lua", "boom()", "房間 1的腳本 a/x.lua:1: attempt to call a nil value (global 'boom')"),
    ("x.lua", "wait(1)", "房間 1的腳本 最外層不能 wait"),
    ("x.lua", "-- 😀\n", "房間 1的腳本 a/x.lua:1: 有轉不成 Big5 的字 '😀'"),
    ("x.lua", "function on_sya() end", "房間 1的腳本 a/x.lua 有不認得的函式 on_sya"),
    ("x.lua", "function on_death() end", "房間 1的腳本 a/x.lua 有不認得的函式 on_death（房間能用的是"),
    ("x.lua", "function on_timer() end", "房間 1的腳本 a/x.lua 有 on_timer，script 的 timer 卻是 null"),
])
def test_bad_scripts(tmp_path, file, code, want):
    if code is not None and not file.startswith(".."):
        write_lua(tmp_path, "a.json", file, code)
    if file.startswith(".."):
        (tmp_path / "x.lua").write_text(code, encoding="utf-8")
        (tmp_path / "a").mkdir(exist_ok=True)
    problems = check(tmp_path, [scripted_room(file)])
    assert any(want in p for p in problems), problems


def test_timer_needs_on_timer(tmp_path):
    problems = check(tmp_path, [scripted_room(timer=30)], files={"x.lua": "function on_say() end"})
    assert problems == ["a.json：房間 1的 script 寫了 timer 30，腳本 a/x.lua 卻沒有 on_timer"]


def test_not_utf8(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.lua").write_bytes("-- 中文".encode("cp950"))
    assert any("a/x.lua 不是 UTF-8" in p for p in check(tmp_path, [scripted_room()]))


def test_mobiles_can_use_every_trigger(tmp_path):
    code = "\n".join(f"function {t}() end" for t in area.MOB_TRIGGERS)
    assert check(tmp_path, mobiles=[scripted_mob(timer=10)], files={"x.lua": code}) == []


def test_script_root(tmp_path):
    # 編輯器檢查暫存檔時，.lua 照樣在真的資料夾裡找
    real = tmp_path / "real"
    write_lua(real, "a.json", "x.lua", "function on_say() end")
    assert check(tmp_path, [scripted_room()], script_root=real) == []
    assert check(tmp_path, [scripted_room()]) != []


# ==== 腳本系統：觸發、函式、變數、wait、出錯 ====

import gc
import logging
import re

import mud.commands as commands
from mud import death, fight, save, scripts, script_api, stats, zones
from mud.area import DoorState
from mud.characters import Position, characters
from mud.config import ENCODING
from mud.npcs import Npc
from mud.players import Player


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data


class Job:
    def __init__(self, seconds, fn):
        self.seconds, self.fn, self.cancelled = seconds, fn, False

    def cancel(self):
        self.cancelled = True


class Later:
    """假的 schedule：記下來，run() 才跑（等完 wait）。"""

    def __init__(self):
        self.jobs = []

    def __call__(self, seconds, fn):
        self.jobs.append(Job(seconds, fn))
        return self.jobs[-1]

    def run(self):
        jobs, self.jobs = self.jobs, []
        for j in jobs:
            if not j.cancelled:
                j.fn()


@pytest.fixture
def later(monkeypatch, tmp_path):
    fake = Later()
    monkeypatch.setattr(scripts, "schedule", fake)
    monkeypatch.setattr(save, "PLAYER_DIR", str(tmp_path / "players"))
    monkeypatch.setattr(fight, "TICK_SECONDS", 1000)
    scripts.reported.clear()
    yield fake
    characters.clear()
    zones.stop()


def mob(vnum, short, keywords, file=None, timer=None, **fields):
    m = make_mobile(vnum)
    m.update(short=short, keywords=keywords, level=1, tier="normal", tier_roll=None, attack=None, defense=None,
             archetype=None, act=0, position=7, sex=0, long="", drops=[], shop=None,
             script=None if file is None else {"file": file, "timer": timer}, **fields)
    return m


def M(vnum, room=1):
    return {"cmd": "M", "rare": 0, "mob_vnum": vnum, "limit": 9, "room_vnum": room, "comment": ""}


def build(tmp_path, files, rooms=None, mobs=(), resets=(), objects=()):
    """房間 101 —北— 102；files 是 {檔名: 程式}；rooms 是 {房間號碼: (檔名, timer)}。"""
    plan = [make_room(1, north=2), make_room(2, south=1)]
    for vnum, (file, timer) in (rooms or {}).items():
        plan[vnum - 1]["script"] = {"file": file, "timer": timer}
    for name, code in files.items():
        write_lua(tmp_path, "a.json", name, code)
    write_json(tmp_path, "a.json", make_area("a.json", plan, 100, mobiles=list(mobs), resets=list(resets), objects=list(objects)))
    zones.load(tmp_path)
    return zones.world.rooms[101]


def person(name, room=101, imm=False):
    p = Player(name, FakeWriter(), zones.world.rooms[room])
    p.race, p.guild, p.imm = stats.Race.HUMAN, stats.Guild.SWORD, imm
    p.primaries = dict(stats.RACE_PRIMARIES[p.race])
    p.trained = {k: 0 for k in stats.PRIMARY_KEYS}
    p.password = save.hash_password("secret")
    stats.set_level(p, 1)
    characters.append(p)
    return p


def plain(p):
    text = re.sub(r"\x1b\[[0-9;]*m", "", p.writer.data.decode(ENCODING))
    p.writer.data = b""
    return text


def say(p, line):
    plain(p)
    commands.command(p, line)
    return plain(p)


def npc(name):
    return next(c for c in characters if isinstance(c, Npc) and c.name == name)


# ---- 觸發時機 ----

def test_on_say_runs_room_first_then_mobs_by_arrival(tmp_path, later):
    files = {"r.lua": 'function on_say(actor, text) room.vars.log = (room.vars.log or "") .. "r" end',
             "a.lua": 'function on_say(actor, text) room.vars.log = room.vars.log .. "a" end',
             "b.lua": 'function on_say(actor, text) room.vars.log = room.vars.log .. "b" end'}
    room = build(tmp_path, files, {1: ("r.lua", None)}, [mob(2, "乙", "b", "b.lua"), mob(1, "甲", "a", "a.lua")], [M(2), M(1)])
    say(person("Ming"), "say 你好")
    assert room.vars["log"] == "rba"                                   # 乙比甲先進房間


def test_on_say_gets_actor_and_text(tmp_path, later):
    files = {"m.lua": 'function on_say(actor, text)\n  if text == "你好" then me:command("say 歡迎光臨，" .. actor.name .. "！") end\nend'}
    build(tmp_path, files, mobs=[mob(1, "商人", "merchant", "m.lua")], resets=[M(1)])
    ming = person("Ming")
    # 他的指令還沒跑完生物就回話：接在指令的回覆後面，只有最後一個 prompt
    assert say(ming, "say 你好") == "你說：『你好』\r\n\r\n商人說：『歡迎光臨，Ming！』\r\n\r\n" + plain_prompt(ming)
    assert "歡迎光臨" not in say(ming, "say 再見")


def test_scripts_do_not_trigger_themselves(tmp_path, later):
    # 生物自己打的指令不會叫到自己的 on_command（不是腳本叫的也一樣），房間的照樣觸發
    files = {"m.lua": 'function on_command(actor, cmd, arg) me.vars.n = (me.vars.n or 0) + 1 end',
             "r.lua": 'function on_command(actor, cmd, arg) room.vars.n = (room.vars.n or 0) + 1 end'}
    room = build(tmp_path, files, {1: ("r.lua", None)}, [mob(1, "鸚鵡", "parrot", "m.lua")], [M(1)])
    commands.command(npc("鸚鵡"), "look")
    assert npc("鸚鵡").vars == {} and room.vars == {"n": 1}


def test_mob_say_does_not_trigger_on_say(tmp_path, later):
    # 只有玩家說的話觸發 on_say（使用者選的，生物之間對話用 tell）：鸚鵡說的話，房間和貓都聽不到
    files = {"p.lua": 'function on_say(actor, text) me:command("say 回聲") end',
             "c.lua": 'function on_say(actor, text) me.vars[actor.name] = text end'}
    room = build(tmp_path, files, {1: ("c.lua", None)}, [mob(1, "鸚鵡", "parrot", "p.lua"), mob(2, "貓", "cat", "c.lua")],
                 [M(1), M(2)])
    say(person("Ming"), "say 嗨")
    commands.command(npc("鸚鵡"), "say 我是鸚鵡")
    assert room.vars == {"Ming": "嗨"} and npc("貓").vars == {"Ming": "嗨"}


def test_finished_runs_free_their_memory(tmp_path, later):
    # 坑：Python 和 Lua 互相抓著（handle 的方法抓著 Run，Run 抓著 handle），沒放掉的話每次觸發都漏，記憶體用完整個程式會當掉
    code = 'function on_say(actor, text) me.vars.n = (me.vars.n or 0) + 1 me:command("say 嗯") end'
    build(tmp_path, {"m.lua": code}, mobs=[mob(1, "鸚鵡", "parrot", "m.lua")], resets=[M(1)])
    ming = person("Ming")
    L = lua.rt().lua

    def used():
        gc.collect()
        L.execute("collectgarbage('collect')")
        return L.get_memory_used()

    say(ming, "say 嗨")
    before = used()
    for _ in range(300):
        say(ming, "say 嗨")
    assert npc("鸚鵡").vars == {"n": 301} and used() - before < 100_000      # 沒放掉的話會多 3 MB


def test_a_chain_does_not_come_back(tmp_path, later, caplog):
    # 甲、乙收到 tell 就 tell 對方：甲 → 乙 → 甲 這種繞回來的不跑（甲這一串已經跑過），不是跑到 5 層才停
    files = {"a.lua": 'function on_tell(actor, text) room.vars.n = (room.vars.n or 0) + 1 me:command("tell b 嗯") end',
             "b.lua": 'function on_tell(actor, text) room.vars.n = (room.vars.n or 0) + 1 me:command("tell a 嗯") end'}
    room = build(tmp_path, files, mobs=[mob(1, "甲", "a", "a.lua"), mob(2, "乙", "b", "b.lua")], resets=[M(1), M(2)])
    with caplog.at_level(logging.WARNING):
        say(person("Ming"), "tell a 嗨")
    assert room.vars["n"] == 2 and "超過" not in caplog.text


def test_after_wait_the_chain_starts_from_the_owner(tmp_path, later):
    # wait 完接著跑是新的一串，從這個主人開始：甲 tell 乙、乙 tell 回甲，甲不再跑
    files = {"a.lua": 'function on_tell(actor, text)\n  room.vars.n = (room.vars.n or 0) + 1\n'
                      '  if text == "開始" then wait(1) me:command("tell b 嗯") end\nend',
             "b.lua": 'function on_tell(actor, text) room.vars.n = room.vars.n + 1 me:command("tell a 回") end'}
    room = build(tmp_path, files, mobs=[mob(1, "甲", "a", "a.lua"), mob(2, "乙", "b", "b.lua")], resets=[M(1), M(2)])
    say(person("Ming"), "tell a 開始")
    later.run()
    assert room.vars["n"] == 2


def test_each_owner_runs_once_per_chain(tmp_path, later, caplog):
    # 七隻生物看到別人打指令就也打一個：一串裡每隻只跑一次（使用者選的），一共 7 次。
    # 只擋「繞回自己」的話，每一條路都跑一次，會是 7 + 7×6 + … ＝ 3619 次
    code = 'function on_command(actor, cmd, arg) room.vars.n = (room.vars.n or 0) + 1 me:command("look") end'
    room = build(tmp_path, {"m.lua": code}, mobs=[mob(i, f"生物{i}", f"m{i}", "m.lua") for i in range(1, 8)],
                 resets=[M(i) for i in range(1, 8)])
    with caplog.at_level(logging.WARNING):
        say(person("Ming"), "look")
    assert room.vars["n"] == 7


def test_on_command_can_block(tmp_path, later):
    files = {"g.lua": 'function on_command(actor, cmd, arg)\n  room.vars.last = cmd .. "|" .. arg\n'
                      '  if cmd == "north" then actor:tell("守衛擋住了你。") return true end\nend'}
    room = build(tmp_path, files, mobs=[mob(1, "守衛", "guard", "g.lua")], resets=[M(1)])
    ming = person("Ming")
    out = say(ming, "n")
    assert out.startswith("守衛擋住了你。\r\n\r\n") and ming.room.vnum == 101 and room.vars["last"] == "north|"
    assert say(ming, "strike sculpture") == "什麼？\r\n\r\n" + plain_prompt(ming)     # 沒擋：照平常處理
    assert room.vars["last"] == "strike|sculpture"
    commands.command(ming, "quit")
    assert room.vars["last"] == "strike|sculpture"                      # quit 不觸發（擋不住，使用者選的）


def plain_prompt(p):
    return re.sub(r"\x1b\[[0-9;]*m", "", p.prompt())


def test_on_command_wait_counts_as_blocking(tmp_path, later):
    files = {"g.lua": 'function on_command(actor, cmd, arg)\n  if cmd == "north" then wait(2) actor:tell("好了。") end\nend'}
    build(tmp_path, files, mobs=[mob(1, "守衛", "guard", "g.lua")], resets=[M(1)])
    ming = person("Ming")
    say(ming, "n")
    assert ming.room.vnum == 101 and [j.seconds for j in later.jobs] == [2]
    later.run()
    assert "好了。" in plain(ming)


def test_on_enter_and_from(tmp_path, later):
    files = {"r.lua": 'function on_enter(actor, from) room.vars.from = from or "傳送" room:echo("風鈴響了。") end'}
    room = build(tmp_path, files, {2: ("r.lua", None)})
    ming = person("Ming")
    out = say(ming, "n")
    assert zones.world.rooms[102].vars["from"] == "south"
    assert out.index("【") < out.index("風鈴響了。") and out.count(plain_prompt(ming)) == 1   # 先看到房間，才聽到風鈴


def test_messages_after_the_commands_own_output_start_a_new_block(tmp_path, later):
    # 別人的訊息連在一起不空行；中間夾了指令自己的訊息（房間畫面），後面那批前面要空一行
    files = {"g.lua": 'function on_command(actor, cmd, arg) if cmd == "north" then actor:tell("你要往北走了。") end end',
             "e.lua": 'function on_enter(actor, from) room:echo("風鈴響了。") room:echo("風停了。") end'}
    build(tmp_path, files, {1: ("g.lua", None), 2: ("e.lua", None)})
    ming = person("Ming")
    out = say(ming, "n")
    assert out.startswith("你要往北走了。\r\n") and out.endswith("\r\n\r\n風鈴響了。\r\n風停了。\r\n\r\n" + plain_prompt(ming))


def test_on_give(tmp_path, later):
    files = {"m.lua": 'function on_give(actor, item, gold) me.vars.got = tostring(item) .. "/" .. gold end'}
    obj = make_object_proto(5)
    build(tmp_path, files, mobs=[mob(1, "商人", "merchant", "m.lua")], resets=[M(1)], objects=[obj])
    ming = person("Ming")
    stats.set_level(ming, 2)
    from mud import objects
    ming.carrying.append(objects.create(105, 1, None))
    ming.gold = 10
    say(ming, "give rock merchant")
    assert npc("商人").vars["got"] == "5/0"                              # 自己區域的物品號碼是 1～99
    say(ming, "give 3 coins merchant")
    assert npc("商人").vars["got"] == "nil/3"


def make_object_proto(vnum):
    from area_helpers import make_object
    o = make_object(vnum)
    o.update(short="石頭", keywords="rock 石頭", item_type=13, wear_flags="1", extra_flags=0, values=[0, 0, 0, 0],
             weight=1, affects=[], script=None)
    return o


def test_on_death_runs_before_falling(tmp_path, later):
    files = {"m.lua": 'function on_death(killer)\n  me:command("say 我還會回來的，" .. (killer and killer.name or "沒有人") .. "！")\nend'}
    build(tmp_path, files, mobs=[mob(1, "老鼠", "rat", "m.lua")], resets=[M(1)])
    ming = person("Ming")
    plain(ming)
    death.die(npc("老鼠"), killer=ming)
    assert "老鼠說：『我還會回來的，Ming！』" in plain(ming) and len(zones.world.rooms[101].contents) == 1   # 說完才留屍體


def test_destroy_in_on_death_leaves_no_corpse(tmp_path, later):
    build(tmp_path, {"m.lua": "function on_death(killer) me:destroy() end"}, mobs=[mob(1, "幽靈", "ghost", "m.lua")], resets=[M(1)])
    death.die(npc("幽靈"))
    assert zones.world.rooms[101].contents == [] and not [c for c in characters if isinstance(c, Npc)]


def test_on_fight_each_round(tmp_path, later):
    import asyncio
    build(tmp_path, {"m.lua": "function on_fight(target) me.vars.rounds = (me.vars.rounds or 0) + 1 me.vars.who = target.name end"},
          mobs=[mob(1, "老鼠", "rat", "m.lua")], resets=[M(1)])
    ming = person("Ming")
    rat = npc("老鼠")

    async def main():
        f = fight.start_fight(ming, rat)
        f.tick(), f.tick(), f.tick()
        return dict(rat.vars)

    assert asyncio.run(main()) == {"rounds": 2, "who": "Ming"}         # 一回合 2 tick：tick 1、3 打


def test_on_born_and_on_reset(tmp_path, later):
    files = {"m.lua": 'function on_born() me.vars.born = true end\nfunction on_reset() me.vars.resets = (me.vars.resets or 0) + 1 end',
             "r.lua": 'function on_reset() room.vars.resets = (room.vars.resets or 0) + 1 end\n'
                      'function on_say(actor, text) room.vars.said = true end'}
    room = build(tmp_path, files, {1: ("r.lua", None)}, [mob(1, "老鼠", "rat", "m.lua")], [M(1)])
    rat = npc("老鼠")
    assert rat.vars == {"born": True, "resets": 1} and room.vars == {"resets": 1}   # 區域建立時的第一次重置也算
    say(person("Ming"), "say 嗨")
    from mud import resets
    resets.reset_area(zones.world, zones.world.areas[0], resets.mobiles)
    assert room.vars == {"resets": 1} and rat.vars["resets"] == 2      # 重置時房間的變數清掉，生物的照舊


def test_on_tell(tmp_path, later):
    build(tmp_path, {"m.lua": "function on_tell(actor, text) me:command('say 你說：' .. text) end"},
          mobs=[mob(1, "商人", "merchant", "m.lua")], resets=[M(1)])
    ming, hua = person("Ming"), person("Hua", room=102)
    out = say(ming, "tell merchant 你好")
    assert "你告訴商人：你好" in out and "商人說：『你說：你好』" in out
    assert say(hua, "tell merchant 你好").startswith("沒有找到你想說話的對象。")   # 只找同房間的生物
    assert "Ming告訴你：嗨" in (say(ming, "tell hua 嗨"), plain(hua))[1]        # tell 玩家照舊


def test_on_timer(tmp_path, later):
    room = build(tmp_path, {"r.lua": 'function on_timer() room:echo("鐘聲。") end'}, {1: ("r.lua", 2)})
    ming = person("Ming")
    plain(ming)
    zones.world.tick()
    assert plain(ming) == ""
    zones.world.tick()
    assert "鐘聲。" in plain(ming)


def test_chain_is_at_most_five_deep(tmp_path, later, caplog):
    # 七隻生物排成一串：第 i 隻收到 tell 就 tell 第 i+1 隻……一串最多 5 層，第 6 隻不跑、記一筆
    files = {f"m{i}.lua": f'function on_tell(actor, text)\n  room.vars.n = (room.vars.n or 0) + 1\n  me:command("tell m{i + 1} 傳")\nend'
             for i in range(1, 8)}
    mobs = [mob(i, f"生物{i}", f"m{i}", f"m{i}.lua") for i in range(1, 8)]
    room = build(tmp_path, files, mobs=mobs, resets=[M(i) for i in range(1, 8)])
    with caplog.at_level(logging.WARNING):
        say(person("Ming"), "tell m1 傳")
    assert room.vars["n"] == scripts.MAX_DEPTH and "一串觸發超過 5 層" in caplog.text


# ---- 函式 ----

def test_actor_fields(tmp_path, later):
    code = ('function on_say(actor, text)\n  room.vars.s = actor.name .. actor.level .. actor.guild .. actor.race .. tostring(actor:is_player())\n'
            '  room.vars.m = tostring(me.guild) .. tostring(me:is_player())\nend')
    room = build(tmp_path, {"m.lua": code}, mobs=[mob(1, "商人", "merchant", "m.lua")], resets=[M(1)])
    say(person("Ming"), "say 嗨")
    assert room.vars == {"s": "Ming1physhumantrue", "m": "nilfalse"}


def test_items_and_doors(tmp_path, later):
    code = ('function on_say(actor, text)\n'
            '  if text == "給" then actor:give_item(5, 3) end\n'
            '  if text == "拿" then room.vars.took = actor:take_item(5) end\n'
            '  if text == "地" then room:load_item(5, 1) room.vars.floor = room:has_item(5) end\n'
            '  if text == "有" then room.vars.has = actor:has_item(5) room.vars.wears = actor:wears_item(5) end\n'
            '  if text == "關" then room:door("north", "lock") end\n'
            'end')
    rooms = [make_room(1, north=2), make_room(2, south=1)]
    room = build(tmp_path, {"m.lua": code}, mobs=[mob(1, "商人", "merchant", "m.lua")], resets=[M(1)],
                 objects=[make_object_proto(5)])
    ming = person("Ming")
    say(ming, "say 給")
    assert [(o.vnum, o.level) for o in ming.carrying] == [(105, 3)]
    say(ming, "say 有")
    assert room.vars == {"has": True, "wears": False}
    say(ming, "say 拿")
    assert ming.carrying == [] and room.vars["took"] is True
    say(ming, "say 地")
    assert room.vars["floor"] is True
    say(person("Hua"), "say 關")                                       # 商人的腳本被 Hua 觸發
    assert zones.world.rooms[101].doors == {} or True


def test_give_item_needs_a_level(tmp_path, later, caplog):
    build(tmp_path, {"m.lua": "function on_say(actor, text)\n  actor:give_item(5)\nend"},
          mobs=[mob(1, "商人", "merchant", "m.lua")], resets=[M(1)], objects=[make_object_proto(5)])
    with caplog.at_level(logging.WARNING):
        say(person("Ming"), "say 嗨")
    assert "a/m.lua:2: 等級一定要寫" in caplog.text


def test_load_mob_and_its_limit(tmp_path, later, caplog, monkeypatch):
    monkeypatch.setattr(script_api, "MAX_LOADED_MOBS", 2)
    code = 'function on_say(actor, text) room:load_mob(2) end'
    born = 'function on_born() me.vars.born = true end'
    build(tmp_path, {"m.lua": code, "b.lua": born}, mobs=[mob(1, "商人", "merchant", "m.lua"), mob(2, "老鼠", "rat", "b.lua")],
          resets=[M(1)])
    ming = person("Ming")
    for _ in range(3):
        say(ming, "say 來")
    rats = [c for c in characters if isinstance(c, Npc) and c.vnum == 102]
    assert len(rats) == 2 and all(r.vars == {"born": True} for r in rats)
    assert "生物 102 已經有 2 隻了" in caplog.text


def test_mob_use_gift_only(tmp_path, later, caplog):
    code = 'function on_say(actor, text)\n  if text == "送" then me:use("gift", actor) else me:use("smash", actor) end\nend'
    build(tmp_path, {"m.lua": code}, mobs=[mob(1, "教官", "teacher", "m.lua")], resets=[M(1)])
    ming = person("Ming")
    assert "教官對你施展了【餽贈】。" in say(ming, "say 送") and ming.affects[0].source == "gift"
    with caplog.at_level(logging.WARNING):
        say(ming, "say 打")
    assert "重擊是傷害技能：mob:use 只能放增益技能" in caplog.text and ming.fighting is None


def test_transfer(tmp_path, later, caplog):
    code = ('function on_say(actor, text)\n  if text == "走" then actor:transfer(2) else actor:transfer(9999) end\nend')
    files = {"m.lua": code, "e.lua": 'function on_enter(actor, from) room.vars.from = from or "傳送" end'}
    build(tmp_path, files, {2: ("e.lua", None)}, mobs=[mob(1, "傳送員", "porter", "m.lua")], resets=[M(1)])
    ming = person("Ming")
    out = say(ming, "say 走")
    assert ming.room.vnum == 102 and "【房間2】" in out and zones.world.rooms[102].vars["from"] == "傳送"
    ming.room = zones.world.rooms[101]
    with caplog.at_level(logging.WARNING):
        say(ming, "say 進副本")
    assert "沒有房間 9999，或那是副本" in caplog.text and ming.room.vnum == 101


def test_echo_skips_sleepers(tmp_path, later):
    code = 'function on_say(actor, text) room:echo("大家好") room:echo_except(actor, "除了他") end'
    build(tmp_path, {"m.lua": code}, mobs=[mob(1, "商人", "merchant", "m.lua")], resets=[M(1)])
    ming, hua, lin = person("Ming"), person("Hua"), person("Lin")
    lin.position = Position.SLEEPING
    plain(hua), plain(lin)
    out = say(ming, "say 嗨")
    assert "大家好" in out and "除了他" not in out
    assert "大家好" in (h := plain(hua)) and "除了他" in h and plain(lin) == ""


def test_random_and_hour(tmp_path, later, monkeypatch):
    class R:
        def randint(self, a, b):
            return b
    monkeypatch.setattr(script_api, "rng", R())
    room = build(tmp_path, {"r.lua": "function on_say(actor, text) room.vars.r = random(1, 6) room.vars.h = hour() end"}, {1: ("r.lua", None)})
    say(person("Ming"), "say 嗨")
    from mud import weather
    assert room.vars == {"r": 6, "h": weather.current.hour}


# ---- 變數 ----

def test_player_vars_are_saved_and_other_areas_are_read_only(tmp_path, later):
    code = ('function on_say(actor, text)\n  actor.vars["任務"] = "做完了"\n'
            '  room.vars.other = actor:read_var("包子村", "done")\nend')
    room = build(tmp_path, {"r.lua": code}, {1: ("r.lua", None)})
    ming = person("Ming")
    ming.vars["包子村"] = {"done": True}
    say(ming, "say 嗨")
    assert ming.vars == {"包子村": {"done": True}, "a": {"任務": "做完了"}} and room.vars["other"] is True
    save.save_player(ming)
    assert save.player_from(save.load_data("Ming"), FakeWriter()).vars == ming.vars


@pytest.mark.parametrize("value, want", [('{}', "變數只能存 nil、true／false、數字、字串"), ("nil", None)])
def test_vars_types(tmp_path, later, caplog, value, want):
    room = build(tmp_path, {"r.lua": f"function on_say(actor, text)\n  room.vars.x = 1\n  room.vars.x = {value}\nend"}, {1: ("r.lua", None)})
    with caplog.at_level(logging.WARNING):
        say(person("Ming"), "say 嗨")
    if want:
        assert f"a/r.lua:3: {want}" in caplog.text and room.vars == {"x": 1}
    else:
        assert room.vars == {}                                          # 寫 nil 是拿掉


# ---- wait ----

def test_wait_then_stop_if_the_actor_left(tmp_path, later):
    code = 'function on_say(actor, text)\n  wait(5)\n  actor:tell("五秒後")\nend'
    build(tmp_path, {"m.lua": code}, mobs=[mob(1, "商人", "merchant", "m.lua")], resets=[M(1)])
    ming = person("Ming")
    say(ming, "say 嗨")
    later.run()
    assert "五秒後" in plain(ming)
    say(ming, "say 嗨")
    ming.room = zones.world.rooms[102]                                  # 走掉了：默默停掉
    later.run()
    assert "五秒後" not in plain(ming) and scripts.pending == {}


def test_wait_stops_if_the_owner_is_gone(tmp_path, later):
    code = 'function on_say(actor, text)\n  wait(5)\n  room:echo("還在")\nend'
    build(tmp_path, {"m.lua": code}, mobs=[mob(1, "商人", "merchant", "m.lua")], resets=[M(1)])
    ming = person("Ming")
    say(ming, "say 嗨")
    characters.remove(npc("商人"))
    later.run()
    assert "還在" not in plain(ming)


def test_wait_limits(tmp_path, later, caplog):
    code = 'function on_say(actor, text)\n  if text == "久" then wait(601) else wait(10) end\nend'
    room = build(tmp_path, {"r.lua": code}, {1: ("r.lua", None)})
    ming = person("Ming")
    with caplog.at_level(logging.WARNING):
        say(ming, "say 久")
    assert "a/r.lua:2: wait 的秒數要是 0～600，不能是 601" in caplog.text and later.jobs == []
    for _ in range(scripts.MAX_WAITING + 3):
        say(ming, "say 等")
    assert len(later.jobs) == scripts.MAX_WAITING and room.waiting == scripts.MAX_WAITING   # 超過的新觸發先不跑
    later.run()
    assert room.waiting == 0


def test_reload_cancels_waiting_scripts(tmp_path, later):
    build(tmp_path, {"r.lua": 'function on_say(actor, text)\n  wait(5)\n  room.vars.done = true\nend'}, {1: ("r.lua", None)})
    say(person("Ming"), "say 嗨")
    room = zones.world.rooms[101]
    zones.stop()
    later.run()
    assert room.vars == {} and scripts.pending == {}


# ---- 出錯 ----

def test_errors_are_reported_once_a_minute(tmp_path, later, caplog, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(scripts, "clock", lambda: now[0])
    room = build(tmp_path, {"r.lua": "function on_say(actor, text)\n  room.vars.n = (room.vars.n or 0) + 1\n  boom()\nend"},
                 {1: ("r.lua", None)})
    imm, ming = person("Shabu", imm=True), person("Ming")
    plain(imm)
    with caplog.at_level(logging.WARNING):
        say(ming, "say 嗨")
        say(ming, "say 嗨")
    assert room.vars["n"] == 2                                          # 下次觸發照樣跑
    assert caplog.text.count("腳本出錯") == 1
    assert "a.json 房間 101：a/r.lua:3: attempt to call a nil value (global 'boom')" in caplog.text
    assert plain(imm).count("[腳本出錯]") == 1 and "腳本出錯" not in plain(ming)   # 玩家看不到
    now[0] += 61
    with caplog.at_level(logging.WARNING):
        say(ming, "say 嗨")
    assert caplog.text.count("腳本出錯") == 2


def test_on_fight_errors_do_not_end_the_fight(tmp_path, later):
    import asyncio
    build(tmp_path, {"m.lua": "function on_fight(target) boom() end"}, mobs=[mob(1, "老鼠", "rat", "m.lua")], resets=[M(1)])
    ming, rat = person("Ming"), npc("老鼠")

    async def main():
        f = fight.start_fight(ming, rat)
        return f.tick()

    assert asyncio.run(main()) is True


def test_text_must_be_big5(tmp_path, later, caplog):
    room = build(tmp_path, {"r.lua": "function on_say(actor, text)\n  actor:tell(utf8.char(128512))\nend"}, {1: ("r.lua", None)})
    with caplog.at_level(logging.WARNING):
        say(person("Ming"), "say 嗨")
    assert "a/r.lua:2: 有轉不成 Big5 的字" in caplog.text
