// 區域檔的資料操作（不碰畫面）。規則照 docs/區域製作手冊.md；檢查一律交給後端的 check_files()。
//
// 出口一律比「算出來的遊戲號碼」：to_room 寫 1～99 是同一個區域（加上 area_number），
// 100 以上照寫。同一區域的出口也可能寫完整號碼（101 指到房間 1），所以不能只比 to_room == vnum。

export const DIRECTIONS = ["north", "east", "south", "west", "up", "down"];
export const FLAT = ["north", "east", "south", "west"];            // 畫在同一層地圖上的方向
export const DIR_NAMES = { north: "北", east: "東", south: "南", west: "西", up: "上", down: "下" };
export const REVERSE = { north: "south", east: "west", south: "north", west: "east", up: "down", down: "up" };
export const STEP = { north: [0, -1], east: [1, 0], south: [0, 1], west: [-1, 0] };

// 手冊的三張數字表，數字要跟 mud/area.py 的 RoomFlag、Sector、Locks 一樣（tests/test_builder.py 會比對）。
// 名字是畫面上的短名字；有第三項的是滑鼠停上去才出現的規則。
export const FLAGS = [
  [1, "很暗"],
  [4, "怪物進不來"],
  [8, "室內"],
  [16, "地底", "吸血鬼白天在這裡不怕陽光"],
  [32, "幫派休息室 1 級"],
  [64, "幫派休息室 2 級"],
  [128, "幫派休息室 3 級"],
  [256, "幫派房間", "只有這個幫派的人能進來"],
  [512, "私人房間（最多 2 人）"],
  [1024, "安全區", "不能戰鬥"],
  [2048, "單人房（最多 1 人）"],
  [4096, "寵物店"],
  [8192, "不能回城"],
  [16384, "不能說話", "頻道和 tell 都不能用"],
  [32768, "不能殺玩家"],
  [65536, "沼氣", "不會飛的人會中毒"],
  [131072, "不能召喚"],
  [262144, "回復減半"],
  [524288, "傳送術落不到這裡"],
  [1048576, "死亡陷阱", "走進來就會死（神族除外）"],
  [2097152, "銀行"],
  [4194304, "傷害陷阱", "每個 tick 扣一半的生命、法力和體力"],
  [8388608, "裝備銀行"],
];

export const SECTORS = [
  [0, "室內"],
  [1, "城市"],
  [2, "原野"],
  [3, "森林"],
  [4, "丘陵"],
  [5, "山地"],
  [6, "可以游泳過去的水"],
  [7, "要有船才能過去的水"],
  [8, "水底，要會在水裡呼吸"],
  [9, "空中，要會飛"],
  [10, "沙漠"],
];

export const LOCKS = [
  [0, "沒有門"],
  [1, "門"],
  [2, "門，撬不開"],
  [3, "門，撞不開"],
  [4, "門，撬不開也撞不開"],
  [5, "門，法術穿不過去"],
  [6, "門，撬不開、法術穿不過去"],
  [7, "門，撞不開、法術穿不過去"],
  [8, "門，撬不開、撞不開、法術穿不過去"],
];

// 區域的種類（header.type），值是字串
export const AREA_TYPES = [
  ["world", "世界區域"],
  ["dynamic", "動態區域"],
  ["instance", "副本區域"],
];

// 區域設定的三個特殊規則：勾＝1，不勾＝null。on() 照手冊判斷檔案裡的值算不算有勾
export const AREA_RULES = [
  { key: "no_teleport", label: "傳送術不會傳到這個區域", tip: "傳送術隨機挑落點時，不會挑到這個區域", on: (v) => v === 1 },
  { key: "clan_recall", label: "不能用幫派回城", tip: "在這個區域裡不能用幫派回城（crecall）", on: (v) => isInt(v) && v > 0 },
  { key: "gem", label: "用特殊寶石掉落表", tip: "怪物死掉時，用另一張特殊的寶石掉落表", on: (v) => v === 1 },
];

export const isInt = Number.isInteger;
const isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

// 清單欄位沒寫或不是 […] 時當成空的（少了欄位交給檢查報出來）；值是 {…} 的清單
const objectList = (v) => v === undefined || (Array.isArray(v) && v.every(isObject));

// 編輯器要能改，至少要有這些形狀；其他不對的地方交給檢查報出來
export function shapeProblem(data) {
  if (!isObject(data) || !isObject(data.area) || !isObject(data.area.header) || !Array.isArray(data.rooms)) {
    return "檔案最上層、area、area.header 或 rooms 的形狀不對";
  }
  for (const r of data.rooms) {
    if (!isObject(r) || !isObject(r.exits) || !Object.values(r.exits).every(isObject)
        || !Array.isArray(r.extra_descriptions) || !r.extra_descriptions.every(isObject)) {
      return "有房間的形狀不對（房間、exits、extra_descriptions）";
    }
  }
  if (!objectList(data.mobiles) || !objectList(data.objects) || !objectList(data.resets)) {
    return "mobiles、objects 或 resets 的形狀不對";
  }
  for (const m of data.mobiles || []) {
    if (!objectList(m.actions) || !objectList(m.fight_actions)
        || ![undefined, null].includes(m.shop) && !isObject(m.shop)
        || ![undefined, null].includes(m.random_drop) && !isObject(m.random_drop)) {
      return "有生物的形狀不對（actions、fight_actions、shop、random_drop）";
    }
  }
  for (const o of data.objects || []) {
    if (!objectList(o.affects) || !objectList(o.extra_descriptions) || o.values !== undefined && !Array.isArray(o.values)) {
      return "有物品的形狀不對（affects、extra_descriptions、values）";
    }
  }
  return null;
}

// data[key] 是清單就回傳它，沒寫就是空的（rooms、mobiles、objects、resets）
export function listOf(data, key) {
  return Array.isArray(data[key]) ? data[key] : [];
}

// 要加東西時才補上清單（檔案原本沒有這個欄位時）
function ensureList(data, key) {
  if (!Array.isArray(data[key])) data[key] = [];
  return data[key];
}

export function base(data) {
  const n = data.area.header.area_number;
  return isInt(n) && n >= 1 ? n : null;
}

// 號碼規則（同 area.resolve）：1～99 是同一個區域，100 以上照寫
export function resolve(areaNumber, number) {
  return number <= 99 ? areaNumber + number : number;
}

// 一個號碼（to_room、recall）算出來的遊戲號碼；算不出來是 null
export function gameNumber(data, number) {
  const b = base(data);
  return b !== null && isInt(number) && number >= 1 ? resolve(b, number) : null;
}

// 房間、生物、物品的遊戲號碼（area_number ＋ vnum）
export function roomNumber(data, room) {
  const b = base(data);
  return b !== null && isInt(room.vnum) ? b + room.vnum : null;
}

export function target(data, exit) {
  return exit ? gameNumber(data, exit.to_room) : null;
}

// kind 是 "rooms"、"mobiles"、"objects"：在那張清單裡找遊戲號碼是 number 的
export function findByNumber(data, kind, number) {
  if (number === null) return null;
  return listOf(data, kind).find((x) => roomNumber(data, x) === number) || null;
}

export function roomByNumber(data, number) {
  return findByNumber(data, "rooms", number);
}

export function exitRoom(data, exit) {
  return roomByNumber(data, target(data, exit));
}

// room_flags 的寫法同 area.parse_flags：數字，或 "1|4" 這種字串。看不懂是 null
export function parseFlags(value) {
  if (isInt(value)) return value >= 0 ? value : null;
  if (typeof value !== "string") return null;
  let result = 0;
  for (const part of value.split("|").map((p) => p.trim())) {
    if (!/^\d+$/.test(part)) return null;
    result |= Number(part);
  }
  return result;
}

// 照檔案號碼排（號碼不對的放最後）
export function sortedList(list) {
  const key = (r) => (isInt(r.vnum) ? r.vnum : Infinity);
  return [...list].sort((a, b) => key(a) - key(b));
}

export function sortedRooms(data) {
  return sortedList(data.rooms);
}

// 照出口接在一起的房間算一塊（六個方向都算，單向的出口也算接著；通到別的區域的不算）。
// 回傳 [[房間…], …]：每塊照號碼排，塊照它最小的號碼排
export function pieces(data) {
  const links = new Map(data.rooms.map((r) => [r, []]));
  for (const room of data.rooms) {
    for (const d of DIRECTIONS) {
      const other = exitRoom(data, room.exits[d]);
      if (other) { links.get(room).push(other); links.get(other).push(room); }
    }
  }
  const order = sortedRooms(data);
  const pieceOf = new Map();
  let count = 0;
  for (const start of order) {
    if (pieceOf.has(start)) continue;
    pieceOf.set(start, count);
    const queue = [start];
    while (queue.length) {
      for (const other of links.get(queue.shift())) {
        if (!pieceOf.has(other)) { pieceOf.set(other, count); queue.push(other); }
      }
    }
    count++;
  }
  return Array.from({ length: count }, (_, i) => order.filter((r) => pieceOf.get(r) === i));
}

// list（房間、生物或物品）裡最小沒用過的檔案號碼；1～99 都用完了是 null
export function freeVnum(list) {
  const used = new Set(list.map((r) => r.vnum));
  for (let v = 1; v <= 99; v++) if (!used.has(v)) return v;
  return null;
}

export function newRoom(vnum) {
  return { vnum, name: "新房間", description: "", room_flags: 0, sector: 0, exits: {}, extra_descriptions: [], script: null };
}

export function newExit(toRoom) {
  return { description: "", keywords: "", locks: 0, key: -1, to_room: toRoom };
}

// 加一間房（號碼用最小沒用過的）；號碼用完了回傳 null
export function addRoom(data) {
  const vnum = freeVnum(data.rooms);
  if (vnum === null) return null;
  const room = newRoom(vnum);
  data.rooms.push(room);
  return room;
}

// 從 room 往 dir 加一間新房，兩邊都接好
export function addRoomTowards(data, room, dir) {
  const next = addRoom(data);
  if (next === null) return null;
  room.exits[dir] = newExit(next.vnum);
  next.exits[REVERSE[dir]] = newExit(room.vnum);
  return next;
}

// room 往 dir 走過去，再往反方向走，會不會回到 room（迷宮的出口會回不來）
export function comesBack(data, room, dir) {
  const other = exitRoom(data, room.exits[dir]);
  return !!other && exitRoom(data, other.exits[REVERSE[dir]]) === room;
}

// 把 room 往 dir 接到已經有的房間 other；other 的反方向還空著才一起接回來
export function connect(data, room, dir, other) {
  room.exits[dir] = newExit(other.vnum);
  if (!other.exits[REVERSE[dir]]) other.exits[REVERSE[dir]] = newExit(room.vnum);
}

// 拿掉 room 往 dir 的出口；對面的反方向出口真的指回 room 才一起拿掉
export function removeExit(data, room, dir) {
  const other = exitRoom(data, room.exits[dir]);
  delete room.exits[dir];
  const me = roomNumber(data, room);
  const back = other && other.exits[REVERSE[dir]];
  if (back && me !== null && target(data, back) === me) delete other.exits[REVERSE[dir]];
}

// 刪掉一間房，連這個檔裡指到它的出口、重置一起拿掉
export function deleteRoom(data, room) {
  const me = roomNumber(data, room);
  data.rooms.splice(data.rooms.indexOf(room), 1);
  if (me === null) return;
  for (const r of data.rooms) {
    for (const d of Object.keys(r.exits)) if (target(data, r.exits[d]) === me) delete r.exits[d];
  }
  dropResets(data, "rooms", me);
}

// 刪掉一隻生物或一個物品（kind 是 "mobiles"、"objects"），連指到它的重置一起拿掉
export function deleteThing(data, kind, item) {
  const me = roomNumber(data, item);
  const list = listOf(data, kind);
  list.splice(list.indexOf(item), 1);
  if (me !== null) dropResets(data, kind, me);
}

const KIND_NAMES = { rooms: "房間", mobiles: "生物", objects: "物品" };

// 改房間號碼：號碼不對回傳錯誤訊息，對就改好（這個檔裡指到它的出口、recall、重置一起改）回傳 null
export function renumber(data, room, vnum) {
  return renumberThing(data, "rooms", room, vnum);
}

// 改房間、生物或物品的號碼，這個檔裡指到它的地方一起改：
// 房間：出口、recall、重置的 room_vnum；生物：重置的 mob_vnum；
// 物品：重置的 obj_vnum、container_vnum，生物的 random_drop，出口的 key
export function renumberThing(data, kind, item, vnum) {
  if (vnum === item.vnum) return null;
  if (!isInt(vnum) || vnum < 1 || vnum > 99) return "號碼要是 1～99 的整數";
  if (listOf(data, kind).some((x) => x !== item && x.vnum === vnum)) return `${KIND_NAMES[kind]} ${vnum} 已經有了`;
  const b = base(data);
  const old = roomNumber(data, item);
  if (b !== null && old !== null) {
    // 原本寫 1～99 的改成新的檔案號碼，原本寫完整號碼的改成新的完整號碼
    const fix = (obj, key) => {
      if (isObject(obj) && gameNumber(data, obj[key]) === old) obj[key] = obj[key] <= 99 ? vnum : b + vnum;
    };
    for (const r of listOf(data, "resets")) {
      for (const [key, k] of Object.entries(RESET_REFS)) if (k === kind && isObject(r) && key in r) fix(r, key);
    }
    if (kind === "rooms") {
      for (const r of data.rooms) for (const e of Object.values(r.exits)) fix(e, "to_room");
      fix(data.area, "recall");
    }
    if (kind === "objects") {
      for (const m of listOf(data, "mobiles")) fix(m.random_drop, "obj_vnum");
      for (const r of data.rooms) for (const e of Object.values(r.exits)) fix(e, "key");   // -1、0 算不出號碼，不會被改
    }
  }
  item.vnum = vnum;
  return null;
}

// ---- 生物、物品 ----

export function newMobile(vnum) {
  return {
    vnum, keywords: "新生物", short: "新生物", long: "", description: "", level: 1, act: 0, affected_by: 0,
    alignment: 0, race: "human", sex: 0, exp: 1, position: 7, random_drop: null, script: null,
    actions: [], fight_actions: [], shop: null, special: null,
  };
}

export function newObject(vnum) {
  return {
    vnum, keywords: "新物品", short: "新物品", long: "", item_type: 8, extra_flags: 0, wear_flags: 1,
    values: [0, 0, 0, 0], weight: 1, cost: 0, affects: [], extra_descriptions: [], script: null,
  };
}

// 勾「牠是店主」「死掉時可能掉東西」時先填的值
export const newShop = () => ({ buy_types: [], profit_buy: 100, profit_sell: 100, open_hour: 0, close_hour: 23 });
export const newDrop = () => ({ chance: 10000, obj_vnum: 1 });
export const newAction = () => ({ when: 0, mode: 0, text: "" });
export const newFightAction = () => ({ rate: 10, message: "", command: "" });
export const newAffect = () => ({ location: 1, modifier: 0 });

// 加一隻生物或一個物品（號碼用最小沒用過的）；號碼用完了回傳 null
export function addThing(data, kind) {
  const list = ensureList(data, kind);
  const vnum = freeVnum(list);
  if (vnum === null) return null;
  const item = kind === "mobiles" ? newMobile(vnum) : newObject(vnum);
  list.push(item);
  return item;
}

// ---- 重置 ----

// 重置裡寫號碼的欄位 → 指到哪一種東西
export const RESET_REFS = { room_vnum: "rooms", mob_vnum: "mobiles", obj_vnum: "objects", container_vnum: "objects" };

// 重置 r 的 key 欄位指到的東西（找不到是 null）
export function resetThing(data, r, key) {
  return findByNumber(data, RESET_REFS[key], gameNumber(data, r[key]));
}

// 新的一筆重置，各欄位先填的值
export function newReset(cmd, fields = {}) {
  const made = {
    M: { cmd, rare: 0, mob_vnum: 1, limit: 1, room_vnum: 1, comment: "" },
    G: { cmd, rare: 0, obj_vnum: 1, limit: 0, comment: "" },
    O: { cmd, if_flag: 0, obj_vnum: 1, limit: 0, room_vnum: 1, comment: "" },
    P: { cmd, if_flag: 0, obj_vnum: 1, limit: 0, container_vnum: 1, comment: "" },
    D: { cmd, if_flag: 0, room_vnum: 1, direction: "north", state: 0, comment: "" },
    R: { cmd, if_flag: 0, room_vnum: 1, exit_count: 2, comment: "" },
    "*": { cmd, comment: "" },
  }[cmd];
  for (const k of Object.keys(fields)) if (k in made) made[k] = fields[k];
  return made;
}

// 緊接在第 i 筆 M 後面的 G、O 後面的 P（它們是跟著這一筆的）
export function followersOf(resets, i) {
  const lead = resets[i];
  const kind = isObject(lead) && lead.cmd === "M" ? "G" : isObject(lead) && lead.cmd === "O" ? "P" : null;
  const out = [];
  for (let j = i + 1; kind && j < resets.length && isObject(resets[j]) && resets[j].cmd === kind; j++) out.push(j);
  return out;
}

// 第 j 筆 G、P 跟著哪一筆 M、O（中間只隔著同一種）；沒有是 -1
export function leaderOf(resets, j) {
  const r = resets[j];
  const lead = r.cmd === "G" ? "M" : r.cmd === "P" ? "O" : null;
  if (!lead) return -1;
  let i = j - 1;
  while (i >= 0 && isObject(resets[i]) && resets[i].cmd === r.cmd) i--;
  return i >= 0 && isObject(resets[i]) && resets[i].cmd === lead ? i : -1;
}

// 這間房的重置：放進來的生物（和跟著的 G）、物品（和跟著的 P）、門的狀態（方向 → 第幾筆）、打亂出口（第幾筆，沒有是 -1）
export function roomResets(data, room) {
  const me = roomNumber(data, room);
  const resets = listOf(data, "resets");
  const result = { mobs: [], objs: [], doors: {}, random: -1 };
  resets.forEach((r, i) => {
    if (!isObject(r) || me === null || gameNumber(data, r.room_vnum) !== me) return;
    if (r.cmd === "M") result.mobs.push({ index: i, followers: followersOf(resets, i) });
    else if (r.cmd === "O") result.objs.push({ index: i, followers: followersOf(resets, i) });
    else if (r.cmd === "D" && typeof r.direction === "string" && !(r.direction in result.doors)) result.doors[r.direction] = i;
    else if (r.cmd === "R" && result.random < 0) result.random = i;
  });
  return result;
}

// 指到 item（kind 的東西）的重置：[{ index, key }]，key 是指到它的欄位
export function resetsPointingAt(data, kind, item) {
  const me = roomNumber(data, item);
  const out = [];
  if (me === null) return out;
  listOf(data, "resets").forEach((r, i) => {
    if (!isObject(r)) return;
    for (const [key, k] of Object.entries(RESET_REFS)) {
      if (k === kind && key in r && gameNumber(data, r[key]) === me) out.push({ index: i, key });
    }
  });
  return out;
}

// 會被一起刪掉的重置：指到 number（kind 的遊戲號碼）的，加上 M、O 跟著的 G、P
function doomedResets(data, kind, number) {
  const resets = listOf(data, "resets");
  const doomed = new Set();
  resets.forEach((r, i) => {
    if (!isObject(r)) return;
    for (const [key, k] of Object.entries(RESET_REFS)) {
      if (k === kind && key in r && gameNumber(data, r[key]) === number) {
        doomed.add(i);
        for (const j of followersOf(resets, i)) doomed.add(j);
      }
    }
  });
  return doomed;
}

// 刪 item 時會一起刪掉幾筆重置（給確認視窗用）
export function resetsGoingWith(data, kind, item) {
  const me = roomNumber(data, item);
  return me === null ? 0 : doomedResets(data, kind, me).size;
}

function dropResets(data, kind, number) {
  const doomed = doomedResets(data, kind, number);
  if (doomed.size) data.resets = data.resets.filter((_, i) => !doomed.has(i));
}

// 加一筆重置到第 at 筆（沒給就加在最後），回傳它在第幾筆
export function insertReset(data, entry, at) {
  const resets = ensureList(data, "resets");
  const i = at === undefined ? resets.length : at;
  resets.splice(i, 0, entry);
  return i;
}

// 在第 i 筆 M、O 和它已經跟著的 G、P 後面加一筆（新的 G、P 就會跟著它）
export function addFollower(data, i, entry) {
  return insertReset(data, entry, i + 1 + followersOf(data.resets, i).length);
}

// 刪第 i 筆；是 M、O 的話，跟著的 G、P 一起刪
export function removeReset(data, i) {
  const doomed = new Set([i, ...followersOf(data.resets, i)]);
  data.resets = data.resets.filter((_, j) => !doomed.has(j));
}

// 把第 from 筆移到第 to 筆（只移這一筆）
export function moveReset(data, from, to) {
  const [r] = data.resets.splice(from, 1);
  data.resets.splice(to, 0, r);
}

// 整層地圖：從 start 出發沿東南西北走，回傳 Map(房間 → {x, y})。格子被佔了的房間就不畫
export function layout(data, start) {
  const pos = new Map([[start, { x: 0, y: 0 }]]);
  const taken = new Set(["0,0"]);
  const queue = [start];
  while (queue.length) {
    const room = queue.shift();
    const { x, y } = pos.get(room);
    for (const d of FLAT) {
      const next = exitRoom(data, room.exits[d]);
      if (!next || pos.has(next)) continue;
      const [dx, dy] = STEP[d];
      const cell = `${x + dx},${y + dy}`;
      if (taken.has(cell)) continue;
      taken.add(cell);
      pos.set(next, { x: x + dx, y: y + dy });
      queue.push(next);
    }
  }
  return pos;
}

// 每間房在第幾層：從第一間房算起是 0，往上 +1、往下 -1。連不到的房間從它自己重新算起
export function floors(data) {
  const z = new Map();
  for (const start of data.rooms) {
    if (z.has(start)) continue;
    z.set(start, 0);
    const queue = [start];
    while (queue.length) {
      const room = queue.shift();
      for (const d of DIRECTIONS) {
        const next = exitRoom(data, room.exits[d]);
        if (!next || z.has(next)) continue;
        z.set(next, z.get(room) + (d === "up" ? 1 : d === "down" ? -1 : 0));
        queue.push(next);
      }
    }
  }
  return z;
}

export function floorName(z) {
  return z >= 0 ? `${z + 1} 樓` : `地下 ${-z} 樓`;
}
