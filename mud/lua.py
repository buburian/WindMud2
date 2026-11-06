"""Lua 沙箱（區域製作手冊「腳本」）：全遊戲一個 Lua 5.4（lupa），腳本碰不到檔案、網路、作業系統。

做法（2026-11-06 實驗過，記在記憶 lua-script-sandbox）：
- 每次觸發都重新 load（新的環境 env），在 coroutine 裡跑：wait 就是讓它停下來（yield），之後再接著跑。
  坑：coroutine 一定要用 lupa 的 `函式.coroutine()` 建、從 Python `send()` 接著跑。在 Lua 裡 coroutine.resume 的話，
  腳本呼叫 Python、Python 再回頭讀 Lua（例如 handle 換回角色、腳本觸發別的腳本）時，lupa 會讀錯堆疊（多拿到一個 coroutine）。
  所以 hook 由 coroutine 自己掛：開始跑時、每次 wait 回來時。
- 指令數上限：每一段（開始到第一個 wait、之後每兩個 wait 之間）用 count hook 數。超過、或 Python 判定出錯（wrap 包的函式丟錯）時，
  先記住第一個錯，再掛上「腳本裡每個指令都丟錯誤」的 hook：腳本用 pcall 接住也停得下來。
- 坑：腳本沒有 coroutine（使用者定的）。新開的 coroutine 不會繼承 Lua 的 hook，給了會卡死伺服器。
- 坑：字串的方法不用給 string 也拿得到（("a"):find(...)），find／match／gmatch／gsub 在 C 裡跑、hook 停不下來，會卡死伺服器。
  所以字串身上只留安全的幾個（這個 Lua 只給腳本用，改了不影響別人）。
"""
import weakref

from lupa import lua54
from lupa.lua54 import LuaError, LuaMemoryError

STEP = 1000                                 # count hook 每幾個指令叫一次
BUDGET = 100_000                            # 每一段最多幾個指令（使用者定的）
MAX_MEMORY = 64 * 1024 * 1024               # 整個 Lua 共用的記憶體上限，超過丟 not enough memory
MAX_WAIT = 600                              # 一次 wait 最長幾秒，超過算出錯（使用者定的，不偷偷改成 600）

BOOTSTRAP = r'''
local cocreate, coresume, coyield, costatus, corunning = coroutine.create, coroutine.resume, coroutine.yield, coroutine.status, coroutine.running
local sethook, getinfo, load, pcall, error, tostring, type, pairs, ipairs, next, select, tonumber, assert, setmetatable, rawget =
  debug.sethook, debug.getinfo, load, pcall, error, tostring, type, pairs, ipairs, next, select, tonumber, assert, setmetatable, rawget
local pack, unpack = table.pack, table.unpack
local string, math, table, utf8 = string, math, table, utf8

local safe = {}
for _, k in ipairs({"byte", "char", "len", "lower", "upper", "sub", "format", "rep", "reverse"}) do safe[k] = string[k] end
getmetatable("").__index = safe

local function copy(t, skip)
  local out = {}
  for k, v in pairs(t) do if k ~= skip then out[k] = v end end
  return out
end

local M = {}
local weak = {__mode = "k"}                -- 用 coroutine 當 key：跑完、被丟掉的 coroutine 會被回收，這些表跟著清掉
local names, failed, used, budgets = setmetatable({}, weak), setmetatable({}, weak), setmetatable({}, weak), setmetatable({}, weak)
local handles = setmetatable({}, {__mode = "k"})   -- handle 的表 → Python 那邊的號碼（腳本拿不到，假造不了）

local function place(co)                   -- 「test/鐘聲.lua:12: 」：往上找到腳本那一層的檔名和行號（中間可能隔著 pcall 這種 C 函式）
  local want = names[co]
  for level = 3, 50 do                     -- 1 是這裡、2 是叫這裡的（hook 或 wrap 包的函式）
    local info = getinfo(level, "Sl")
    if not info then break end
    if info.source == want and info.currentline and info.currentline > 0 then
      return want:sub(2) .. ":" .. info.currentline .. ": "
    end
  end
  return ""
end

local function kill(co, msg)               -- 這一次要停：記住第一個錯，之後腳本裡每個指令都丟錯誤（pcall 接不住）
  if failed[co] == nil then failed[co] = msg end
  sethook(co, function()
    local info = getinfo(2, "S")
    if info and info.source == names[co] then error(failed[co], 0) end
  end, "", 1)
end

local function counter(co)
  return function()
    used[co] = used[co] + 1000
    if used[co] > budgets[co] then
      local msg = place(co) .. "指令太多（一段最多 " .. budgets[co] .. " 個）"
      kill(co, msg)
      error(msg, 0)
    end
  end
end

function M.wrap(f)                         -- 包 Python 的函式（f 回傳 成功了沒, 值或錯）：出錯時用腳本那一行的行號，而且這一次停掉
  return function(...)
    local ok, value = f(...)
    if ok then return value end
    local co = corunning()
    local msg = (names[co] and place(co) or "") .. tostring(value)
    if names[co] then kill(co, msg) end
    error(msg, 0)
  end
end

function M.base()                          -- 每次新的一份：Lua 本來就有的安全函式
  return {
    pairs = pairs, ipairs = ipairs, next = next, select = select, type = type, tostring = tostring, tonumber = tonumber,
    pcall = pcall, error = error, assert = assert,
    math = copy(math), table = copy(table), utf8 = copy(utf8, "charpattern"),
    wait = function(seconds)
      local co = corunning()
      if type(seconds) ~= "number" or seconds ~= seconds or seconds < 0 or seconds > M.max_wait then
        local msg = place(co) .. "wait 的秒數要是 0～" .. M.max_wait .. "，不能是 " .. tostring(seconds)
        kill(co, msg)
        error(msg, 0)
      end
      sethook(co)
      local resumed = coyield(seconds)
      used[co] = 0                         -- 新的一段，重新數
      sethook(co, counter(co), "", 1000)
      return resumed
    end,
  }
end

function M.stub()                          -- 開機檢查用的假替身：什麼方法都有、什麼都不做（最外層用到 me、room 也跑得過）
  return setmetatable({vars = {}}, {__index = function() return function() end end})
end

function M.handle(fields, key)             -- 做一個 handle（me、room、actor）：fields 是 Python 給的欄位和方法
  local h = {}
  for k, v in pairs(fields) do h[k] = v end
  handles[h] = key
  return h
end

function M.key_of(h)                       -- handle → Python 那邊的號碼；不是 handle 是 nil
  if type(h) ~= "table" then return nil end
  return handles[h]
end

function M.vars(get, set)                  -- 變數的表：讀寫都走 Python（Python 那邊檢查型別）
  return setmetatable({}, {__index = function(_, k) return get(k) end, __newindex = function(_, k, v) set(k, v) end})
end

function M.compile(code, name)             -- 只看語法
  local chunk, err = load(code, "=" .. name, "t", {})
  if chunk then return true, nil end
  return false, err
end

function M.functions(code, name, env, budget)   -- 開機檢查：跑最外層，回傳定義了哪些 on_ 函式（逗號隔開）；出錯回傳 nil, 錯
  local chunk, err = load(code, "=" .. name, "t", env)
  if not chunk then return nil, err end
  local co = cocreate(chunk)
  names[co], used[co], budgets[co], failed[co] = "=" .. name, 0, budget, nil
  sethook(co, counter(co), "", 1000)
  local ok, e = coresume(co)
  sethook(co)
  local f = failed[co]
  names[co], used[co], budgets[co], failed[co] = nil, nil, nil, nil
  if f then return nil, f end
  if not ok then return nil, tostring(e) end
  if costatus(co) ~= "dead" then return nil, "最外層不能 wait" end
  local found = {}
  for k, v in pairs(env) do
    if type(k) == "string" and k:sub(1, 3) == "on_" and type(v) == "function" then found[#found + 1] = k end
  end
  table.sort(found)
  return table.concat(found, ","), nil
end

function M.spawn(code, name, env, fname, budget)   -- 準備一次觸發：回傳要放進 coroutine 的函式（load、跑最外層、再跑 fname）
  local chunk, err = load(code, "=" .. name, "t", env)
  if not chunk then return nil, err end
  return function(...)
    local co = corunning()
    names[co], used[co], budgets[co] = "=" .. name, 0, budget
    sethook(co, counter(co), "", 1000)
    chunk()
    local f = rawget(env, fname)
    local result
    if type(f) == "function" then result = f(...) end
    sethook(co)
    return result
  end, nil
end

return M
'''


def _deny(obj, name, is_setting):
    raise AttributeError("腳本不能碰 Python 物件的屬性")


class _Runtime:
    """全遊戲共用的一個 Lua（第一次用到才建立）。"""

    def __init__(self):
        self.lua = lua54.LuaRuntime(register_eval=False, register_builtins=False, unpack_returned_tuples=True,
                                    attribute_filter=_deny, max_memory=MAX_MEMORY)
        self.m = self.lua.execute(BOOTSTRAP)
        self.m.max_wait = MAX_WAIT
        self.objects = weakref.WeakValueDictionary()     # handle 的號碼 → 角色或房間
        self.next_key = 0


_rt = None


def rt():
    global _rt
    if _rt is None:
        _rt = _Runtime()
    return _rt


def table(d):
    """Python 的 dict → 新的 Lua 表。"""
    return rt().lua.table_from(d)


def wrap(fn):
    """包 Python 函式給腳本用：丟 ScriptError（或任何錯）時，訊息帶腳本的行號，而且這一次停掉（pcall 接不住）。

    坑：Python 的錯不能穿過 Lua。lupa 存下這個錯時會釋放上一個錯的 traceback，裡面的 Lua 物件在 coroutine 裡面釋放會讓整個程式當掉
    （整套測試跑才碰得到）。所以在這裡就接住，回傳「成功了沒、值或錯」給 Lua，由 Lua 那邊丟錯。
    """
    def safe(*args):
        try:
            return True, fn(*args)
        except Exception as e:
            return False, str(e)
    return rt().m.wrap(safe)


def base_env():
    """每次新的一份環境：Lua 本來就有的安全函式和 wait。"""
    return rt().m.base()


def check_env():
    """開機檢查跑最外層用的環境：跟真的一樣的安全函式，me、room、actor、random、hour 是假的替身。"""
    env = base_env()
    m = rt().m
    for k in ("me", "room", "actor"):
        env[k] = m.stub()
    env["random"] = rt().lua.eval("function(a, b) return a end")
    env["hour"] = rt().lua.eval("function() return 0 end")
    return env


def handle(obj, fields):
    """做一個 handle 給腳本（me、room、actor）。obj 是它代表的角色或房間，之後 obj_of() 換得回來。"""
    r = rt()
    r.next_key += 1
    r.objects[r.next_key] = obj
    return r.m.handle(table(fields), r.next_key)


def obj_of(h):
    """腳本傳回來的 handle → 角色或房間；不是 handle、或那個角色已經不在了是 None。"""
    key = rt().m.key_of(h)
    return None if key is None else rt().objects.get(key)


def vars_table(get, set_):
    """變數的表（me.vars 這種）：讀寫走 get(名字)、set_(名字, 值)。"""
    return rt().m.vars(wrap(get), wrap(set_))


def compile_error(code, name):
    """語法錯就回傳錯（「test/x.lua:3: ...」），沒問題是 None。"""
    ok, err = rt().m.compile(code, name)
    return None if ok else str(err)


def functions(code, name, env):
    """開機檢查：在 env 裡跑最外層，回傳 (定義了哪些 on_ 函式, 錯)。"""
    found, err = rt().m.functions(code, name, env, BUDGET)
    if found is None:
        return None, str(err)
    return set(found.split(",")) if found else set(), None


def spawn(code, name, env, fname, *args):
    """準備一次觸發（fname(args…)），回傳 coroutine（step 才開始跑）；load 失敗丟 ValueError。"""
    body, err = rt().m.spawn(code, name, env, fname, BUDGET)
    if body is None:
        raise ValueError(str(err))
    return body.coroutine(*args)


def step(co):
    """跑一段：("done", 回傳值)、("wait", 秒數)、("error", 錯)。不跑了就把 co 丟掉（Lua 那邊的記錄跟著回收）。"""
    try:
        value = co.send(None)
    except LuaMemoryError:                  # 坑：從 coroutine 丟出來的這個錯沒有訊息
        return "error", "not enough memory"
    except LuaError as e:
        return "error", str(e).split("\nstack traceback:")[0]
    if co:                                  # 還活著：停在 wait
        return "wait", value
    return "done", value[0] if isinstance(value, tuple) else value
