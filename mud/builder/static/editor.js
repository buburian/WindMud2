// 編輯畫面：上方｜左邊房間清單｜中間整層地圖｜右邊分頁。照設計稿第 8 版。
//
// 載入的 JSON 直接改，沒動到的欄位原樣存回去。改了內容就停手半秒自動檢查（不存檔），
// 檢查一律交給後端的 check_files()，這裡不另外寫規則。
import * as api from "./api.js";
import * as M from "./model.js";
import { openSettings } from "./settings.js";
import {
  brand, checkbox, chip, confirmDialog, field, h, icon, numberText, parseNumber, plainText,
  selectArrow, selectInput, storedText, textArea, textInput, toast,
} from "./ui.js";

const PITCH_X = 168;            // 地圖格子的間距：格子 120×48，中間的線 48
const PITCH_Y = 96;
const TABS = [["basic", "基本資料"], ["exits", "出口"], ["flags", "地形和旗標"], ["extra", "可以細看的東西"]];

let state = null;               // 現在打開的檔；選檔畫面時是 null
let ui = {};                    // 畫面上會重畫的幾個區塊

export const currentFile = () => (state ? state.file : null);
export const isDirty = () => !!state && state.version !== state.savedVersion;

export function closeEditor() {
  if (state) clearTimeout(state.checkTimer);
  closeProblems();
  closeGhostMenu();
  state = null;
  ui = {};
}

export async function openEditor(name) {
  const me = state = {
    file: name, data: null, elsewhere: {}, problems: [], checking: false,
    selected: null, tab: "exits", exitDir: null, vnumDraft: null, vnumError: null,   // 設計稿預設是「出口」分頁
    version: 0, savedVersion: 0, checkTimer: null,
    view: { room: null, x: 0, y: 0, zoom: 1 },      // 地圖平面拖拉移動了多少、放大幾倍；room 是那時選到的房間
  };
  document.title = `${name} · 區域編輯器`;
  const app = document.getElementById("app");
  app.replaceChildren(h("div", { class: "screen" }, h("header", { class: "topbar" }, brand(back))));
  let result;
  try {
    result = await api.readArea(name);
  } catch (e) {
    if (state === me) showNotice(e.message, []);
    return;
  }
  if (state !== me) return;                     // 載入時已經換到別的畫面
  Object.assign(me, { data: result.data, problems: result.problems, elsewhere: result.elsewhere });
  const shape = M.shapeProblem(me.data);
  if (shape) {
    showNotice(`編輯器打不開這個檔：${shape}。請先照下面的問題手改。`, result.problems);
    return;
  }
  me.selected = M.sortedRooms(me.data)[0] || null;
  buildLayout();
}

function back() {
  location.hash = "";                           // app.js 會在離開前問要不要存
}

function showNotice(title, lines) {
  document.getElementById("app").replaceChildren(h("div", { class: "screen" },
    h("header", { class: "topbar" }, brand(back), h("span", { class: "divider-v", "aria-hidden": "true" }),
      h("div", { class: "doc" }, h("span", { class: "doc-title" }, state.file))),
    h("main", { class: "files" }, h("section", { class: "notice" },
      h("p", { style: "margin: 0" }, title),
      lines.length ? h("ul", null, lines.map((line) => h("li", null, shortProblem(line)))) : null))));
}

// ---- 外框 ----

function buildLayout() {
  ui.docTitle = h("span", { class: "doc-title" });
  ui.status = h("div");
  ui.saveButton = h("button", { type: "button", class: "btn btn-filled", onclick: save }, "儲存");
  ui.topbar = h("header", { class: "topbar" },
    brand(back),
    h("span", { class: "divider-v", "aria-hidden": "true" }),
    h("div", { class: "doc" }, h("span", { class: "doc-file" }, state.file), ui.docTitle),
    h("div", { class: "actions" }, ui.status,
      h("button", { type: "button", class: "btn", onclick: () => scheduleCheck(0) }, "檢查"),
      ui.saveButton));
  ui.list = h("nav", { class: "rooms-nav", "aria-label": "房間" });
  ui.map = h("section", { class: "map", "aria-label": "區域地圖" });
  ui.inspector = h("section", { class: "inspector", "aria-label": "房間設定" });
  document.getElementById("app").replaceChildren(h("div", { class: "screen" },
    ui.topbar,
    h("div", { class: "body" },
      h("aside", { class: "rooms" }, ui.list,
        h("div", { class: "rooms-foot" },
          h("button", { type: "button", class: "nav-item", "aria-haspopup": "dialog", onclick: settings },
            icon("gear"), "區域設定"))),
      h("main", { class: "map-wrap" }, ui.map),
      ui.inspector)));
  renderAll();
}

function renderAll() {
  renderTitle();
  renderStatus();
  renderList();
  renderMap();
  renderInspector();
}

function renderTitle() {
  ui.docTitle.textContent = textOf(state.data.area.header.title);
}

// 改了欄位的字：重畫不含輸入框的區塊（輸入框不能重畫，不然打字打到一半會跳掉）
function edited() {
  state.version++;
  renderTitle();
  renderList();
  renderMap();
  scheduleCheck();
}

// 加減房間、出口這類改動：全部重畫
function rebuild() {
  state.version++;
  renderAll();
  scheduleCheck();
}

function select(room) {
  Object.assign(state, { selected: room, exitDir: null, vnumDraft: null, vnumError: null });
  renderList();
  renderMap();
  renderInspector();
}

const textOf = (v) => (typeof v === "string" ? v : numberText(v));
const shortProblem = (p) => (p.startsWith(`${state.file}：`) ? p.slice(state.file.length + 1) : p);

// ---- 檢查、存檔 ----

function scheduleCheck(delay = 500) {
  const me = state;
  clearTimeout(me.checkTimer);
  me.checking = true;
  renderStatus();
  me.checkTimer = setTimeout(async () => {
    const version = me.version;
    try {
      const result = await api.checkArea(me.file, me.data);
      if (state !== me || me.version !== version) return;     // 檢查時又改了，等下一次的結果
      me.problems = result.problems;
    } catch (e) {
      if (state !== me) return;
      toast(e.message);
    }
    me.checking = false;
    renderStatus();
  }, delay);
}

async function save() {
  const me = state;
  const version = me.version;
  ui.saveButton.disabled = true;
  try {
    const result = await api.saveArea(me.file, me.data);
    if (state !== me) return;
    me.savedVersion = version;
    if (me.version === version) {                // 存的時候沒有再改，結果就是現在的問題
      clearTimeout(me.checkTimer);
      me.problems = result.problems;
      me.checking = false;
      renderStatus();
    }
    toast(result.problems.length ? `已儲存，有 ${result.problems.length} 個問題` : "已儲存");
  } catch (e) {
    if (state === me) toast(`沒有存到：${e.message}`);
  } finally {
    if (state === me) ui.saveButton.disabled = false;
  }
}

function renderStatus() {
  const n = state.problems.length;
  let el;
  if (state.checking) {
    el = h("span", { class: "chip chip-wait status-chip" }, "檢查中");
  } else if (!n) {
    el = h("span", { class: "chip chip-ok status-chip" }, icon("ok", 18), "沒有問題");
  } else {
    el = h("button", { type: "button", class: "chip chip-bad status-chip", "aria-expanded": String(!!ui.popover), onclick: toggleProblems },
      icon("alert", 18), `${n} 個問題`);
  }
  ui.status.replaceChildren(el);
  if (ui.popover) {
    if (state.checking || !n) closeProblems();
    else ui.popover.replaceChildren(...state.problems.map((p) => h("li", null, shortProblem(p))));
  }
}

function toggleProblems() {
  if (ui.popover) {
    closeProblems();
  } else {
    ui.popover = h("ul", { class: "popover", "aria-label": "問題" });
    ui.topbar.append(ui.popover);
    document.addEventListener("mousedown", outsideProblems);
  }
  renderStatus();
}

function closeProblems() {
  if (!ui.popover) return;
  ui.popover.remove();
  ui.popover = null;
  document.removeEventListener("mousedown", outsideProblems);
}

function outsideProblems(e) {
  if (ui.popover && !ui.popover.contains(e.target) && !ui.status.contains(e.target)) {
    closeProblems();
    renderStatus();
  }
}

// ---- 左邊：房間清單 ----

// 房間照「接在一起的算一塊」分組，塊跟塊中間用「沒連在一起」的線隔開
function renderList() {
  const rows = [];
  M.pieces(state.data).forEach((piece, i) => {
    if (i > 0) rows.push(h("div", { class: "nav-split" }, "沒連在一起"));
    for (const room of piece) {
      rows.push(h("button", { type: "button", class: "nav-item", "aria-current": room === state.selected ? "page" : null, onclick: () => select(room) },
        h("span", { class: "nav-num" }, numberText(room.vnum)),
        h("span", { class: "nav-name" }, textOf(room.name))));
    }
  });
  ui.list.replaceChildren(
    h("div", { class: "rooms-head" }, h("span", null, "房間"),
      h("button", { type: "button", class: "icon-btn", "aria-label": "新增房間", onclick: addRoom }, icon("plus"))),
    ...rows);
}

function addRoom() {
  const room = M.addRoom(state.data);
  if (!room) return toast("房間號碼 1～99 都用完了");
  Object.assign(state, { selected: room, exitDir: null, vnumDraft: null, vnumError: null });
  rebuild();
}

// 從選到的房間往 dir 加一間新房（兩邊接好），並選它
function grow(dir) {
  const room = M.addRoomTowards(state.data, state.selected, dir);
  if (!room) return toast("房間號碼 1～99 都用完了");
  Object.assign(state, { selected: room, exitDir: null, vnumDraft: null, vnumError: null });
  rebuild();
}

// 地圖虛線格的小選單：加一間新房間，或填「通到」的號碼只加出口（例如通到別的區域）
function openGhostMenu(anchor, dir) {
  closeGhostMenu();
  const input = textInput({ id: "ghost-to" });
  const addExit = () => {
    const to = parseNumber(input.value);
    if (to === null) return input.focus();
    state.selected.exits[dir] = M.newExit(to);
    state.exitDir = dir;
    closeGhostMenu();
    rebuild();
  };
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") addExit(); });
  const menu = h("div", { class: "ghost-menu", role: "dialog", "aria-label": `往${M.DIR_NAMES[dir]}新增` },
    h("button", { type: "button", class: "menu-item", onclick: () => { closeGhostMenu(); grow(dir); } }, icon("plus", 18), "新房間"),
    h("div", { class: "ghost-menu-to" },
      field({ id: "ghost-to", label: "通到", code: "to_room", input }),
      h("button", { type: "button", class: "btn btn-filled", onclick: addExit }, "好")));
  menu.addEventListener("keydown", (e) => { if (e.key === "Escape") { closeGhostMenu(); anchor.focus(); } });
  document.body.append(menu);
  const r = anchor.getBoundingClientRect();             // 放在虛線格下面；下面放不下就放上面，也不超出右邊
  menu.style.left = `${Math.max(8, Math.min(r.left, innerWidth - menu.offsetWidth - 8))}px`;
  menu.style.top = `${r.bottom + 8 + menu.offsetHeight > innerHeight ? r.top - 8 - menu.offsetHeight : r.bottom + 8}px`;
  ui.ghostMenu = menu;
  document.addEventListener("mousedown", outsideGhostMenu);
  input.focus();
}

function closeGhostMenu() {
  if (!ui.ghostMenu) return;
  ui.ghostMenu.remove();
  ui.ghostMenu = null;
  document.removeEventListener("mousedown", outsideGhostMenu);
}

function outsideGhostMenu(e) {
  if (!ui.ghostMenu.contains(e.target)) closeGhostMenu();
}

function settings() {
  openSettings({ data: state.data, roomChip, onDone: rebuild });
}

// ---- 中間：地圖 ----

// 格子 (x, y) 的位置：選到的房間在 (0, 0)，放在地圖左邊那塊的正中間
const at = (x, y, dx, dy) => ({ left: `calc(50% + ${x * PITCH_X + dx}px)`, top: `calc(50% + ${y * PITCH_Y + dy}px)` });
const cellStyle = (p) => at(p.x, p.y, -60, -24);

const GAP = 48;                  // 格子跟隔壁格中間的空隙（橫的直的都是 48）
const STUB = 28;                 // 通到不在旁邊的房間：線只畫這麼長，不碰到隔壁格
const BORDER = { north: [0, -24], south: [0, 24], east: [60, 0], west: [-60, 0] };   // 格子中心到邊的位置
const SIDE = { north: -8, south: 8, east: -8, west: 8 };   // 一段空隙有兩條線時各走一邊：往北走左邊、往東走上面

// 從 p 那格的邊往 d 畫一條線，回傳 { items, end }。offset 是往旁邊挪幾 px；end 是線的終點（相對 p 的中心）
function lane(p, d, { offset = 0, length = GAP, arrow = false, on = false, dashed = false } = {}) {
  const [ux, uy] = M.STEP[d];
  const vertical = ux === 0;
  const sx = BORDER[d][0] + (vertical ? offset : 0);
  const sy = BORDER[d][1] + (vertical ? 0 : offset);
  const ex = sx + ux * length;
  const ey = sy + uy * length;
  const style = vertical ? { ...at(p.x, p.y, sx - 1, Math.min(sy, ey)), width: "2px", height: `${length}px` }
    : { ...at(p.x, p.y, Math.min(sx, ex), sy - 1), width: `${length}px`, height: "2px" };
  if (dashed) Object.assign(style, vertical ? { width: "0", borderLeft: "2px dashed var(--off)" } : { height: "0", borderTop: "2px dashed var(--off)" });
  const items = [h("div", { class: dashed ? "link-dash" : "link" + (on ? " link-on" : ""), style, "aria-hidden": "true" })];
  if (arrow) {                                  // 箭頭的尖端在終點
    const box = { north: [-5, 0], south: [-5, -7], east: [-7, -5], west: [0, -5] }[d];
    items.push(h("div", { class: `arrow arrow-${d}` + (on ? " arrow-on" : ""), style: at(p.x, p.y, ex + box[0], ey + box[1]), "aria-hidden": "true" }));
  }
  return { items, end: [ex, ey] };
}

// 線旁邊的號碼：通到這個檔的房間（點了就選它），或別的區域、找不到的號碼
function laneLabel(p, d, offset, exit, [ex, ey]) {
  const vertical = M.STEP[d][0] === 0;
  const style = vertical
    ? { ...at(p.x, p.y, ex + (offset < 0 ? -6 : 6), ey), transform: offset < 0 ? "translate(-100%, -50%)" : "translate(0, -50%)" }
    : { ...at(p.x, p.y, ex, ey + (offset > 0 ? 6 : -6)), transform: offset > 0 ? "translate(-50%, 0)" : "translate(-50%, -100%)" };
  const room = M.exitRoom(state.data, exit);
  if (room) return h("button", { type: "button", class: "lane-label", style, onclick: () => select(room) }, numberText(room.vnum));
  const t = M.target(state.data, exit);
  const missing = t === null || state.elsewhere[t] === undefined;
  return h("span", { class: "lane-label" + (missing ? " lane-missing" : ""), style }, t === null ? "?" : String(t));
}

// 房間 room 往 d 的出口，通到的不是旁邊那格：短線、箭頭、號碼
function stub(room, p, d, offset) {
  const exit = room.exits[d];
  const on = room === state.selected || M.exitRoom(state.data, exit) === state.selected;
  const { items, end } = lane(p, d, { offset, length: STUB, arrow: true, on });
  return [...items, laneLabel(p, d, offset, exit, end)];
}

// p 的 room 跟往 d 隔壁的 neighbor 中間那段空隙。互相走得回來：一條沒有箭頭的線；
// 不然兩邊的出口各畫一條（通到隔壁的畫箭頭，通到別處的畫短線加號碼）；選到的房間這邊還沒出口就畫虛線＋
function gap(room, p, d, neighbor) {
  const { data, selected } = state;
  const back = M.REVERSE[d];
  const q = { x: p.x + M.STEP[d][0], y: p.y + M.STEP[d][1] };
  const toNeighbor = !!room.exits[d] && M.exitRoom(data, room.exits[d]) === neighbor;
  const toRoom = !!neighbor.exits[back] && M.exitRoom(data, neighbor.exits[back]) === room;
  if (toNeighbor && toRoom) return lane(p, d, { on: room === selected || neighbor === selected }).items;
  const sides = [[room, p, d, neighbor, toNeighbor], [neighbor, q, back, room, toRoom]];
  const count = sides.filter(([r, , dir]) => r.exits[dir] || r === selected).length;
  const items = [];
  for (const [r, from, dir, other, adjacent] of sides) {
    const offset = count > 1 ? SIDE[dir] : 0;
    if (r.exits[dir] && adjacent) items.push(...lane(from, dir, { offset, arrow: true, on: r === selected || other === selected }).items);
    else if (r.exits[dir]) items.push(...stub(r, from, dir, offset));
    else if (r === selected) {
      items.push(...lane(from, dir, { offset, dashed: true }).items);
      const [ux, uy] = M.STEP[dir];
      const vertical = ux === 0;
      const cx = BORDER[dir][0] + ux * GAP / 2 + (vertical ? offset : 0);
      const cy = BORDER[dir][1] + uy * GAP / 2 + (vertical ? 0 : offset);
      items.push(h("button", { type: "button", class: "connect", style: at(from.x, from.y, cx - 10, cy - 10),
        "aria-label": `往${M.DIR_NAMES[dir]}接到房間 ${numberText(other.vnum)}`,
        onclick: () => { M.connect(data, r, dir, other); rebuild(); } }, icon("plus", 14)));
    }
  }
  return items;
}

function roomTile(room, style, current, wide) {
  return h("button", {
    type: "button", class: "tile" + (wide ? " tile-wide" : ""), style,
    "aria-current": current ? "true" : null, onclick: current ? null : () => select(room),
  }, h("span", { class: "tile-num" }, numberText(room.vnum)), h("span", { class: "tile-name" }, textOf(room.name)));
}

// 通到別的區域（寫完整號碼和房間名），或號碼不對、找不到的出口
function farTile(exit, style, wide) {
  const t = M.target(state.data, exit);
  const name = t === null ? undefined : state.elsewhere[t];
  return h("div", { class: "tile tile-far" + (name === undefined ? " tile-missing" : "") + (wide ? " tile-wide" : ""), style },
    h("span", { class: "tile-num" }, t === null ? "?" : String(t)),
    h("span", { class: "tile-name" }, name !== undefined ? name : t === null ? "號碼不對" : "找不到"));
}

function renderMap() {
  const { data, selected } = state;
  const plan = h("div", { class: "plan-layer" });   // 房間都放這層，拖拉、縮放時整層一起動
  const box = h("div", { class: "floor-plan" }, plan);
  const side = h("div", { class: "updown" });
  closeGhostMenu();                             // 地圖重畫了，選單對著的虛線格已經不在
  ui.map.replaceChildren(box, side);
  panZoom(box, plan);
  if (!selected) {
    plan.append(h("button", { type: "button", class: "ghost", style: cellStyle({ x: 0, y: 0 }), "aria-label": "新增房間", onclick: addRoom }, icon("plus")));
    return;
  }
  const pos = M.layout(data, selected);
  const cells = new Map([...pos].map(([room, p]) => [`${p.x},${p.y}`, room]));   // 格子 → 畫在那裡的房間
  const taken = new Set(cells.keys());
  const done = new Set();                       // 畫過的空隙（兩間房中間那段只畫一次）
  const far = [];
  for (const [room, p] of pos) {
    for (const d of M.FLAT) {
      const [dx, dy] = M.STEP[d];
      const next = { x: p.x + dx, y: p.y + dy };
      const neighbor = cells.get(`${next.x},${next.y}`);
      if (neighbor) {
        const key = [`${p.x},${p.y}`, `${next.x},${next.y}`].sort().join("|");
        if (!done.has(key)) plan.append(...gap(room, p, d, neighbor));
        done.add(key);
        continue;
      }
      const exit = room.exits[d];
      if (!exit) continue;
      if (M.exitRoom(data, exit) || taken.has(`${next.x},${next.y}`)) {   // 這個檔的房間但不在旁邊，或那格已經有東西
        plan.append(...stub(room, p, d, 0));
        continue;
      }
      taken.add(`${next.x},${next.y}`);         // 通到別的區域、找不到的：旁邊畫一格灰色的
      plan.append(...lane(p, d, { on: room === selected }).items);
      far.push(farTile(exit, cellStyle(next)));
    }
  }
  plan.append(...far);
  for (const [room, p] of pos) plan.append(roomTile(room, cellStyle(p), room === selected));
  for (const d of M.FLAT) {                     // 選到的房間四周空的方向：虛線格，點了就加一間房
    const [dx, dy] = M.STEP[d];
    if (d in selected.exits || taken.has(`${dx},${dy}`)) continue;
    plan.append(...lane({ x: 0, y: 0 }, d, { dashed: true }).items,
      h("button", { type: "button", class: "ghost", style: cellStyle({ x: dx, y: dy }), "aria-label": `往${M.DIR_NAMES[d]}新增`, "aria-haspopup": "dialog",
        onclick: (e) => openGhostMenu(e.currentTarget, d) }, icon("plus")));
  }
  box.append(floorPill(selected));              // 樓層標籤放在外面，不跟著動
  side.append(...upDown(selected));
}

// ---- 地圖平面的拖拉和縮放（右邊往上往下那欄不動）----

const ZOOM_MIN = 0.25;
const ZOOM_MAX = 2;
const DRAG_START = 4;           // 滑鼠移動超過幾 px 才算拖拉，不然算點一下

// 把 state.view 套到畫面上：房間那層移動、縮放，格線跟著一起動
function showView() {
  const { x, y, zoom } = state.view;
  ui.plan.style.transform = `translate(${x}px, ${y}px) scale(${zoom})`;
  const grid = 24 * zoom;
  // 格線對齊平面的中心：CSS 的 50% 會先減掉半格，所以補回 grid / 2
  ui.planBox.style.backgroundSize = `${grid}px ${grid}px`;
  ui.planBox.style.backgroundPosition = `calc(50% + ${x + grid / 2}px) calc(50% + ${y + grid / 2}px)`;
}

function panZoom(box, plan) {
  Object.assign(ui, { planBox: box, plan });
  const view = state.view;
  if (view.room !== state.selected) Object.assign(view, { room: state.selected, x: 0, y: 0 });   // 換了房間就把它移回中間，倍率不變
  showView();

  // 滾輪縮放，滑鼠底下那一點不動。Mac 觸控板雙指捏合也是 wheel（ctrlKey），一定要擋掉，不然整頁網頁會跟著放大
  box.addEventListener("wheel", (e) => {
    e.preventDefault();
    closeGhostMenu();                           // 地圖動了，選單會對不到虛線格
    const delta = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;   // Firefox 的滑鼠滾輪是用「行」算
    const zoom = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, view.zoom * Math.exp(-delta * (e.ctrlKey ? 0.01 : 0.002))));
    const r = ui.planBox.getBoundingClientRect();
    const mx = e.clientX - r.left - r.width / 2;    // 滑鼠離平面中心多遠
    const my = e.clientY - r.top - r.height / 2;
    const k = zoom / view.zoom;
    Object.assign(view, { x: mx - k * (mx - view.x), y: my - k * (my - view.y), zoom });
    showView();
  }, { passive: false });

  box.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || e.target.closest(".floor")) return;
    const start = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y };
    let dragging = false;
    const move = (ev) => {
      const dx = ev.clientX - start.x;
      const dy = ev.clientY - start.y;
      if (!dragging && Math.hypot(dx, dy) < DRAG_START) return;
      dragging = true;
      ui.planBox.classList.add("dragging");
      Object.assign(view, { x: start.vx + dx, y: start.vy + dy });
      showView();
    };
    const end = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", end);
      ui.planBox.classList.remove("dragging");
      if (!dragging) return;
      // 拖完放開不能算點到房間或「＋」：擋掉緊接著的那一次 click（放開時就會送出，等不到下一輪）
      const swallow = (ev) => ev.stopPropagation();
      window.addEventListener("click", swallow, true);
      setTimeout(() => window.removeEventListener("click", swallow, true), 0);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
  });
}

function floorPill(room) {
  const z = M.floors(state.data).get(room) || 0;
  const up = M.exitRoom(state.data, room.exits.up);
  const down = M.exitRoom(state.data, room.exits.down);
  return h("div", { class: "floor" },
    h("button", { type: "button", class: "icon-btn", "aria-label": "上一層", disabled: !up, onclick: () => select(up) }, icon("up", 18)),
    h("span", { class: "floor-name" }, M.floorName(z)),
    h("button", { type: "button", class: "icon-btn", "aria-label": "下一層", disabled: !down, onclick: () => select(down) }, icon("down", 18)));
}

// 右邊一欄：往上、這間房、往下
function upDown(room) {
  const items = [];
  for (const [d, top, lineTop, label, arrow] of [["up", -120, -72, "往上", "arrowUp"], ["down", 72, 14, "往下", "arrowDown"]]) {
    const exit = room.exits[d];
    const style = { left: "16px", top: `calc(50% + ${top}px)` };
    const line = { left: "81px", top: `calc(50% + ${lineTop}px)`, height: "58px" };
    if (!exit) {
      items.push(h("div", { class: "link-dash", style: { ...line, width: "0", borderLeft: "2px dashed var(--off)" }, "aria-hidden": "true" }),
        h("button", { type: "button", class: "ghost tile-wide", style, "aria-label": `${label}新增`, "aria-haspopup": "dialog",
          onclick: (e) => openGhostMenu(e.currentTarget, d) }, icon(arrow, 18), label));
      continue;
    }
    const other = M.exitRoom(state.data, exit);
    items.push(h("div", { class: "link link-on", style: { ...line, width: "2px" }, "aria-hidden": "true" }),
      other ? roomTile(other, style, false, true) : farTile(exit, style, true));
    if (other && !M.comesBack(state.data, room, d)) {     // 走過去回不來：箭頭指向要去的房間
      items.push(h("div", { class: `arrow arrow-${d === "up" ? "north" : "south"} arrow-on`,
        style: { left: "77px", top: `calc(50% + ${d === "up" ? -72 : 65}px)` }, "aria-hidden": "true" }));
    }
  }
  items.push(h("div", { class: "here", style: { top: "calc(50% - 14px)" } }, h("span", null, "這間房")));
  return items;
}

// ---- 右邊：分頁 ----

function renderInspector() {
  const room = state.selected;
  if (!room) {
    ui.inspector.replaceChildren();
    return;
  }
  const number = M.roomNumber(state.data, room);
  ui.title = h("h1", { class: "insp-title" }, textOf(room.name));
  const render = { basic: basicTab, exits: exitsTab, flags: flagsTab, extra: extraTab }[state.tab];
  ui.inspector.replaceChildren(
    h("div", { class: "insp-head" },
      h("div", { class: "insp-names" },
        h("span", { class: "eyebrow" }, `房間 ${numberText(room.vnum)}` + (number !== null ? ` · 遊戲裡 ${number} 號` : "")),
        ui.title),
      h("button", { type: "button", class: "btn btn-text btn-danger", onclick: removeRoom }, "刪除房間")),
    h("div", { class: "tabs", role: "tablist" }, TABS.map(([key, label]) =>
      h("button", { type: "button", class: "tab", role: "tab", "aria-selected": String(state.tab === key),
        onclick: () => { state.tab = key; renderInspector(); } }, label))),
    h("div", { class: "insp-body", role: "tabpanel" }, render(room)));
}

async function removeRoom() {
  const me = state;
  const room = me.selected;
  const ok = await confirmDialog({
    title: `刪除房間 ${numberText(room.vnum)}？`,
    text: `「${textOf(room.name)}」和指到它的出口會一起拿掉。`,
    ok: "刪除", danger: true,
  });
  if (!ok || state !== me) return;
  M.deleteRoom(me.data, room);
  Object.assign(me, { selected: M.sortedRooms(me.data)[0] || null, exitDir: null, vnumDraft: null, vnumError: null });
  rebuild();
}

function basicTab(room) {
  const vnumInput = textInput({
    id: "room-vnum", value: state.vnumDraft !== null ? state.vnumDraft : numberText(room.vnum),
    onchange: (e) => {                          // 打完（離開欄位或按 Enter）才套用，打到一半不改
      const vnum = parseNumber(e.target.value);
      const same = vnum === room.vnum;          // 要在 renumber 之前比，改完 room.vnum 就是新的了
      const error = same ? null : M.renumber(state.data, room, vnum);
      state.vnumDraft = error ? e.target.value : null;
      state.vnumError = error;
      if (error || same) renderInspector();
      else rebuild();
      if (error) document.getElementById("room-vnum").focus();
    },
  });
  return h("div", { class: "stack" },
    h("div", { class: "row row-top" },
      field({ id: "room-vnum", label: "房間號碼", code: "vnum", input: vnumInput, error: state.vnumError, style: "flex: 0 0 120px" }),
      field({ id: "room-name", label: "名稱", code: "name", input: textInput({
        id: "room-name", value: textOf(room.name),
        oninput: (e) => { room.name = e.target.value; ui.title.textContent = room.name; edited(); },
      }) })),
    field({ id: "room-desc", label: "描述", code: "description", input: textArea({
      id: "room-desc", rows: 5, value: plainText(room.description),
      oninput: (e) => { room.description = storedText(e.target.value); edited(); },
    }) }),
    h("div", { class: "info-row" },
      h("span", { class: "label" }, "觸發程式", h("span", { class: "code", style: "margin-left: 6px" }, "script")),
      h("span", null, scriptText(room.script))));
}

function scriptText(script) {
  if (script === null || script === undefined) return "沒有";
  return script && typeof script.function === "string" && script.function ? script.function : "有";
}

// 「通到」「回城房間」旁邊的房間名：找得到是綠色，找不到是紅色
function roomChip(number) {
  if (number === null || number === undefined || number === "") return null;
  const t = M.gameNumber(state.data, number);
  if (t === null) return chip("bad", "號碼不對");
  const room = M.roomByNumber(state.data, t);
  const name = room ? textOf(room.name) : state.elsewhere[t];
  return name === undefined ? chip("bad", `找不到房間 ${t}`) : chip("ok", name || `房間 ${t}`);
}

function exitLabel(exit) {
  const other = M.exitRoom(state.data, exit);
  if (other) return `房間 ${numberText(other.vnum)}`;
  const t = M.target(state.data, exit);
  return t === null ? "?" : String(t);
}

function exitsTab(room) {
  const exits = room.exits;
  const dir = state.exitDir in exits ? state.exitDir : M.DIRECTIONS.find((d) => d in exits) || null;
  state.exitDir = dir;
  const dirs = h("div", { class: "dirs" });
  const renderDirs = () => dirs.replaceChildren(...M.DIRECTIONS.map((d) => (d in exits
    ? h("button", { type: "button", class: "dir", "aria-pressed": String(d === dir), onclick: () => { state.exitDir = d; renderInspector(); } },
      h("span", { class: "dir-name" }, M.DIR_NAMES[d]), h("span", { class: "dir-to" }, exitLabel(exits[d])))
    : h("div", { class: "dir dir-empty" },               // 沒有出口：灰色、不能點（出口從地圖的虛線格加）
      h("span", { class: "dir-name" }, M.DIR_NAMES[d])))));
  renderDirs();
  if (!dir) return h("div", { class: "stack" }, dirs);

  const e = exits[dir];
  const chipBox = h("div", { style: "min-width: 0; display: flex" });
  const showChip = () => chipBox.replaceChildren(roomChip(e.to_room) || "");
  showChip();
  const doorOff = e.locks === 0;
  return h("div", { class: "stack", style: "gap: 20px" }, dirs,
    h("div", { class: "card" },
      h("div", { class: "card-head" },
        h("h2", { class: "card-title" }, `往${M.DIR_NAMES[dir]}`, h("span", { class: "code" }, dir)),
        h("button", { type: "button", class: "btn btn-text btn-danger",
          onclick: () => { M.removeExit(state.data, room, dir); state.exitDir = null; rebuild(); } }, "移除")),
      h("div", { class: "row", style: "gap: 12px" },
        field({ id: "exit-to", label: "通到", code: "to_room", style: "flex: 0 0 120px", input: textInput({
          id: "exit-to", value: numberText(e.to_room),
          oninput: (ev) => { e.to_room = parseNumber(ev.target.value); showChip(); renderDirs(); edited(); },
        }) }),
        chipBox),
      field({ id: "exit-desc", label: "看到的樣子", code: "description", input: textArea({
        id: "exit-desc", rows: 2, value: plainText(e.description),
        oninput: (ev) => { e.description = storedText(ev.target.value); edited(); },
      }) }),
      h("div", { class: "stack sep" },
        field({ id: "exit-locks", label: "門的種類", code: "locks", extra: selectArrow(), input: selectInput({
          id: "exit-locks", value: e.locks, options: M.LOCKS,
          onchange: (ev) => { e.locks = Number(ev.target.value); rebuild(); },
        }) }),
        h("div", { class: "row" },
          field({ id: "exit-keywords", label: "門的名字", code: "keywords", off: doorOff, input: textInput({
            id: "exit-keywords", value: textOf(e.keywords), disabled: doorOff,
            oninput: (ev) => { e.keywords = ev.target.value; edited(); },
          }) }),
          field({ id: "exit-key", label: "鑰匙", code: "key", off: doorOff, input: textInput({
            id: "exit-key", value: numberText(e.key), disabled: doorOff,
            oninput: (ev) => { e.key = parseNumber(ev.target.value); edited(); },
          }) })))));
}

function flagsTab(room) {
  const value = M.parseFlags(room.room_flags);
  return h("div", { class: "stack" },
    field({ id: "room-sector", label: "地形", code: "sector", extra: selectArrow(), input: selectInput({
      id: "room-sector", value: room.sector, options: M.SECTORS,
      onchange: (e) => { room.sector = Number(e.target.value); edited(); },
    }) }),
    h("fieldset", null,
      h("legend", null, "房間旗標", h("span", { class: "code" }, "room_flags")),
      h("div", { class: "flags" }, M.FLAGS.map(([bit, label, tip]) => checkbox({
        label, code: bit, tip, checked: value !== null && (value & bit) !== 0,
        onchange: (e) => {                      // 勾了才把 room_flags 改成數字；沒動過的 "1|4" 寫法原樣保留
          const now = M.parseFlags(room.room_flags) || 0;
          room.room_flags = e.target.checked ? now | bit : now & ~bit;
          edited();
        },
      })))));
}

function firstWord(keywords) {
  return typeof keywords === "string" ? keywords.trim().split(/\s+/)[0] : "";
}

function extraTab(room) {
  const list = room.extra_descriptions;
  const cards = list.map((ed, i) => {
    const title = h("h2", { class: "card-title" }, firstWord(ed.keywords));
    return h("div", { class: "card" },
      h("div", { class: "card-head" }, title,
        h("button", { type: "button", class: "btn btn-text btn-danger", onclick: () => { list.splice(i, 1); rebuild(); } }, "移除")),
      field({ id: `extra-${i}-keywords`, label: "名字", code: "keywords", input: textInput({
        id: `extra-${i}-keywords`, value: textOf(ed.keywords),
        oninput: (e) => { ed.keywords = e.target.value; title.textContent = firstWord(ed.keywords); edited(); },
      }) }),
      field({ id: `extra-${i}-desc`, label: "看到的文字", code: "description", input: textArea({
        id: `extra-${i}-desc`, rows: 3, value: plainText(ed.description),
        oninput: (e) => { ed.description = storedText(e.target.value); edited(); },
      }) }));
  });
  return h("div", { class: "stack", style: "gap: 16px" }, cards,
    h("div", null, h("button", { type: "button", class: "btn",
      onclick: () => {
        list.push({ keywords: "", description: "" });
        rebuild();
        document.getElementById(`extra-${list.length - 1}-keywords`).focus();
      } }, icon("plus", 18), "新增")));
}
