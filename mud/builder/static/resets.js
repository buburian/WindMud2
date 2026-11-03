// 重置總覽：左欄依指令篩選｜中間照檔案順序的表格（可以拖曳排順序）｜右邊改選到的那一筆。
// 也提供生物、物品標題下「放在哪」的小標籤（placesOf）。
// 重置照順序執行：G 跟著前面最近的 M、P 跟著前面最近的 O（model.js 的 leaderOf、followersOf）。
import { itemLookRow, numberField, refField, removeButton, textField } from "./forms.js";
import * as M from "./model.js";
import * as T from "./tables.js";
import { field, h, icon, numberText, selectArrow } from "./ui.js";

const CMD_NAMES = Object.fromEntries(T.RESET_CMDS);
const RARE_TIP = "0～10 一定會出現；大於 10 不一定會出現，機率大約 (rare − 10) ÷ 10000";
const UNUSED_TIP = "C 版讀了沒用到";

const isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const textOf = (v) => (typeof v === "string" ? v : numberText(v));

// 號碼指到的東西：{ num: 顯示的號碼, name: 名字, missing: 找不到 }。這個檔的寫檔案號碼，別的檔寫完整號碼
function lookup(ctx, kind, number) {
  const { state } = ctx;
  const t = M.gameNumber(state.data, number);
  if (t === null) return { num: number === null || number === undefined ? "?" : textOf(number), name: "號碼不對", missing: true };
  const item = M.findByNumber(state.data, kind, t);
  if (item) return { num: numberText(item.vnum), name: textOf(kind === "rooms" ? item.name : item.short), missing: false, item };
  const others = { rooms: state.elsewhere, mobiles: state.elsewhereMobiles, objects: state.elsewhereObjects }[kind];
  const name = others[t];
  return { num: String(t), name: name === undefined ? "找不到" : name, missing: name === undefined };
}

// 表格裡的「號碼 名字」
function thingCell(ctx, kind, number, prefix = "") {
  const t = lookup(ctx, kind, number);
  return h("span", { class: t.missing ? "missing" : null }, h("span", { class: "num" }, prefix + t.num), " ", t.name);
}

const roomCell = (ctx, number) => thingCell(ctx, "rooms", number, "房間 ");

// 跟著上一筆的 G、P 前面加一個小箭頭
const follow = (...children) => h("span", null, h("span", { class: "follow", "aria-hidden": "true" }, icon("follow", 14)), ...children);

function doorText(ctx, r) {
  const room = M.resetThing(ctx.state.data, r, "room_vnum");
  const exit = room && isObject(room.exits) ? room.exits[r.direction] : null;
  const door = exit && typeof exit.keywords === "string" ? exit.keywords.trim().split(/\s+/)[0] : "";
  const state = T.DOOR_STATES.find(([n]) => n === r.state);
  return `${M.DIR_NAMES[r.direction] || textOf(r.direction)}${door ? ` ${door}` : ""}：${state ? state[1] : textOf(r.state)}`;
}

function shuffleText(n) {
  if (!M.isInt(n) || n < 2) return "不打亂";
  return M.DIRECTIONS.slice(0, n).map((d) => M.DIR_NAMES[d]).join("、");
}

// 表格一列的「內容」「在哪裡」
function describe(ctx, resets, i) {
  const r = resets[i];
  switch (r.cmd) {
    case "M": return [thingCell(ctx, "mobiles", r.mob_vnum), roomCell(ctx, r.room_vnum)];
    case "G": {
      const lead = M.leaderOf(resets, i);
      return [follow(thingCell(ctx, "objects", r.obj_vnum)),
        lead >= 0 ? h("span", { class: "muted" }, "給上面的 ", lookup(ctx, "mobiles", resets[lead].mob_vnum).name)
          : h("span", { class: "missing" }, "前面沒有放生物")];
    }
    case "O": return [thingCell(ctx, "objects", r.obj_vnum), roomCell(ctx, r.room_vnum)];
    case "P": return [follow(thingCell(ctx, "objects", r.obj_vnum)),
      h("span", { class: "muted" }, "放進 ", thingCell(ctx, "objects", r.container_vnum))];
    case "D": return [doorText(ctx, r), roomCell(ctx, r.room_vnum)];
    case "R": return [shuffleText(r.exit_count), roomCell(ctx, r.room_vnum)];
    default: return [h("span", { class: "missing" }, "看不懂的指令"), ""];
  }
}

// ---- 左欄：依指令篩選 ----

export function listItems(ctx) {
  const { state } = ctx;
  const resets = M.listOf(state.data, "resets");
  const count = (cmd) => resets.filter((r) => isObject(r) && r.cmd === cmd).length;
  const item = (key, label, n, code) => h("button", {
    type: "button", class: "nav-item", "aria-current": state.resetFilter === key ? "page" : null,
    onclick: () => { state.resetFilter = key; ctx.refresh(); },
  }, code ? h("span", { class: "nav-code" }, code) : null, h("span", { class: "nav-name nav-grow" }, label), h("span", { class: "nav-count" }, String(n)));
  return [item("all", "全部", resets.length), ...T.RESET_CMDS.map(([cmd, label]) => item(cmd, label, count(cmd), cmd))];
}

// ---- 中間：表格 ----

export function render(ctx) {
  renderTable(ctx);
  renderDetail(ctx);
}

export function renderTable(ctx) {
  const { state, ui } = ctx;
  const resets = M.listOf(state.data, "resets");
  const rows = [];
  resets.forEach((r, i) => {
    if (!isObject(r) || (state.resetFilter !== "all" && r.cmd !== state.resetFilter)) return;
    rows.push(tableRow(ctx, resets, i));
  });
  ui.table.replaceChildren(
    h("div", { class: "table-head" },
      h("div", { class: "table-titles" },
        h("h1", { class: "table-title" }, "重置", h("span", { class: "code" }, "resets")),
        h("span", { class: "muted" }, "由上往下照順序執行")),
      h("button", { type: "button", class: "btn", "aria-haspopup": "menu", onclick: (e) => openAddMenu(ctx, e.currentTarget) },
        icon("plus", 18), "新增")),
    h("div", { class: "table-scroll" },
      h("table", { class: "resets" },
        h("colgroup", null, h("col", { style: "width: 40px" }), h("col", { style: "width: 40px" }), h("col", { style: "width: 136px" }),
          h("col", { style: "width: 30%" }), h("col", { style: "width: 28%" }), h("col")),
        h("thead", null, h("tr", null,
          h("th", null, h("span", { class: "sr-only" }, "順序")), h("th", null, "#"),
          h("th", null, "指令", h("span", { class: "key" }, "cmd")), h("th", null, "內容"), h("th", null, "在哪裡"),
          h("th", null, "註解", h("span", { class: "key" }, "comment")))),
        h("tbody", null, rows))));
}

function tableRow(ctx, resets, i) {
  const { state } = ctx;
  const r = resets[i];
  const select = () => { state.resetIndex = i; renderTable(ctx); renderDetail(ctx); };
  const cells = r.cmd === "*"
    ? [h("td", { colspan: "3" }, textOf(r.comment))]
    : [...describe(ctx, resets, i).map((c) => h("td", null, c)), h("td", null, textOf(r.comment))];
  const row = h("tr", { draggable: "true", "aria-selected": String(state.resetIndex === i), onclick: select },
    h("td", null, h("span", { class: "drag", title: "拖曳調整順序", "aria-hidden": "true" }, icon("grip", 16))),
    h("td", { class: "num" }, String(i + 1)),
    h("td", null, h("span", { class: "cmd-badge" }, textOf(r.cmd)), CMD_NAMES[r.cmd] || ""),
    ...cells);
  // 拖曳排順序：放在一列的上半部是插到它前面，下半部是插到它後面
  row.addEventListener("dragstart", (e) => { e.dataTransfer.setData("text/plain", String(i)); e.dataTransfer.effectAllowed = "move"; });
  row.addEventListener("dragover", (e) => {
    e.preventDefault();
    const box = row.getBoundingClientRect();
    const after = e.clientY > box.top + box.height / 2;
    row.classList.toggle("drop-before", !after);
    row.classList.toggle("drop-after", after);
  });
  row.addEventListener("dragleave", () => row.classList.remove("drop-before", "drop-after"));
  row.addEventListener("drop", (e) => {
    e.preventDefault();
    const after = row.classList.contains("drop-after");
    row.classList.remove("drop-before", "drop-after");
    const from = Number(e.dataTransfer.getData("text/plain"));
    let to = i + (after ? 1 : 0);
    if (from < to) to -= 1;
    if (!M.isInt(from) || from === to) return;
    M.moveReset(state.data, from, to);
    state.resetIndex = to;
    ctx.rebuild();
  });
  return row;
}

// ---- 右邊：改選到的那一筆 ----

// 下拉選單，值是文字（例如方向 north）
function textSelect({ id, label, code, obj, key, options, done }) {
  const known = options.some(([v]) => v === obj[key]);
  const select = h("select", { id, class: "field-input", onchange: (e) => { obj[key] = e.target.value; done(); } },
    known ? null : h("option", { value: "", disabled: true }, `${textOf(obj[key]) || "沒有寫"}（不對的值）`),
    options.map(([v, text]) => h("option", { value: v }, text)));
  select.value = known ? obj[key] : "";
  return field({ id, label, code, input: select, extra: selectArrow() });
}

function title(ctx, resets, i) {
  const r = resets[i];
  if (r.cmd === "M") return lookup(ctx, "mobiles", r.mob_vnum).name;
  if (r.cmd === "G" || r.cmd === "O" || r.cmd === "P") return lookup(ctx, "objects", r.obj_vnum).name;
  if (r.cmd === "D") return doorText(ctx, r);
  if (r.cmd === "R") return `打亂出口：${shuffleText(r.exit_count)}`;
  return textOf(r.comment) || "註解";
}

function fields(ctx, r) {
  const done = ctx.edited;
  const ref = (key, kind, label) => refField({ id: `r-${key}`, label, code: key, obj: r, key, chipOf: (n) => ctx.chipOf(kind, n), done });
  const num = (key, label, tip) => numberField({ id: `r-${key}`, label, code: key, obj: r, key, tip, done });
  const comment = textField({ id: "r-comment", label: "註解", code: "comment", obj: r, key: "comment", done });
  switch (r.cmd) {
    case "M": return [ref("mob_vnum", "mobiles", "生物"), ref("room_vnum", "rooms", "房間"),
      h("div", { class: "row" }, num("limit", "最多幾隻", "生物待在原地時算這個房間有幾隻，不然算整個遊戲"), num("rare", "出現機率", RARE_TIP)), comment];
    case "G": return [ref("obj_vnum", "objects", "物品"), itemLookRow(r, "r", done),
      h("div", { class: "row" }, num("limit", "最多", UNUSED_TIP), num("rare", "出現機率", RARE_TIP)), comment];
    case "O": return [ref("obj_vnum", "objects", "物品"), itemLookRow(r, "r", done), ref("room_vnum", "rooms", "房間"),
      h("div", { class: "row" }, num("limit", "最多", UNUSED_TIP), num("if_flag", "if_flag", UNUSED_TIP)), comment];
    case "P": return [ref("obj_vnum", "objects", "物品"), itemLookRow(r, "r", done), ref("container_vnum", "objects", "放進哪個容器"),
      h("div", { class: "row" }, num("limit", "最多", UNUSED_TIP), num("if_flag", "if_flag", UNUSED_TIP)), comment];
    case "D": return [ref("room_vnum", "rooms", "房間"),
      h("div", { class: "row" },
        textSelect({ id: "r-direction", label: "方向", code: "direction", obj: r, key: "direction", done: ctx.rebuild,
          options: M.DIRECTIONS.map((d) => [d, `${d} ${M.DIR_NAMES[d]}`]) }),
        textSelectNumber({ id: "r-state", label: "狀態", code: "state", obj: r, key: "state", options: T.DOOR_STATES, done })),
      num("if_flag", "if_flag", UNUSED_TIP), comment];
    case "R": return [ref("room_vnum", "rooms", "房間"),
      h("div", { class: "row" },
        textSelectNumber({ id: "r-exit-count", label: "打亂前幾個方向", code: "exit_count", obj: r, key: "exit_count", done,
          options: [0, 1, 2, 3, 4, 5, 6].map((n) => [n, n < 2 ? `${n} 不打亂` : `${n} ${shuffleText(n)}`]) }),
        num("if_flag", "if_flag", UNUSED_TIP)), comment];
    default: return [comment];
  }
}

// 下拉選單，值是數字；options 是 [[數字, 顯示的字], …]（顯示的字自己決定要不要帶數字）
function textSelectNumber({ id, label, code, obj, key, options, done }) {
  const known = options.some(([v]) => v === obj[key]);
  const select = h("select", { id, class: "field-input", onchange: (e) => { obj[key] = Number(e.target.value); done(); } },
    known ? null : h("option", { value: "", disabled: true }, `${textOf(obj[key]) || "沒有寫"}（不對的值）`),
    options.map(([v, text]) => h("option", { value: String(v) }, String(text).startsWith(String(v)) ? text : `${v} ${text}`)));
  select.value = known ? String(obj[key]) : "";
  return field({ id, label, code, input: select, extra: selectArrow() });
}

function renderDetail(ctx) {
  const { state, ui } = ctx;
  const resets = M.listOf(state.data, "resets");
  const i = state.resetIndex;
  const r = resets[i];
  if (!isObject(r)) {
    ui.detail.replaceChildren();
    return;
  }
  const move = (to) => { M.moveReset(state.data, i, to); state.resetIndex = to; ctx.rebuild(); };
  ui.detail.replaceChildren(
    h("div", { class: "insp-head insp-head-line" },
      h("div", { class: "insp-names" },
        h("span", { class: "eyebrow" }, `第 ${i + 1} 筆 · `, h("span", { class: "key" }, textOf(r.cmd)), ` ${CMD_NAMES[r.cmd] || "看不懂的指令"}`),
        h("h2", { class: "insp-title" }, title(ctx, resets, i))),
      removeButton(() => {
        M.removeReset(state.data, i);
        state.resetIndex = Math.min(i, M.listOf(state.data, "resets").length - 1);
        ctx.rebuild();
      })),
    h("div", { class: "insp-body" }, h("div", { class: "stack" },
      fields(ctx, r),
      h("div", { class: "order-row" },
        h("span", { class: "label" }, "順序"),
        h("button", { type: "button", class: "btn", disabled: i === 0, onclick: () => move(i - 1) }, icon("arrowUp", 18), "上移"),
        h("button", { type: "button", class: "btn", disabled: i === resets.length - 1, onclick: () => move(i + 1) }, icon("arrowDown", 18), "下移")))));
}

// ---- 新增 ----

let menu = null;

export function closeAddMenu() {
  if (!menu) return;
  menu.remove();
  menu = null;
  document.removeEventListener("mousedown", outside);
}

function outside(e) {
  if (menu && !menu.contains(e.target)) closeAddMenu();
}

// 選一種指令，加在選到的那一筆後面（沒選就加在最後）；號碼先填這個檔的第一間房、第一隻生物、第一個物品
export function openAddMenu(ctx, anchor) {
  closeAddMenu();
  const { state } = ctx;
  const first = (kind) => (M.sortedList(M.listOf(state.data, kind))[0] || { vnum: 1 }).vnum;
  const add = (cmd) => {
    closeAddMenu();
    const room = state.selected ? state.selected.vnum : first("rooms");
    const entry = M.newReset(cmd, { room_vnum: room, mob_vnum: first("mobiles"), obj_vnum: first("objects"), container_vnum: first("objects") });
    const resets = M.listOf(state.data, "resets");
    const at = state.resetIndex >= 0 && state.resetIndex < resets.length ? state.resetIndex + 1 : resets.length;
    state.resetIndex = M.insertReset(state.data, entry, at);
    if (state.resetFilter !== "all" && state.resetFilter !== cmd) state.resetFilter = "all";
    if (state.mode !== "resets") ctx.setMode("resets");
    ctx.rebuild();
  };
  menu = h("div", { class: "ghost-menu", role: "menu", "aria-label": "新增重置" },
    T.RESET_CMDS.map(([cmd, label]) => h("button", { type: "button", class: "menu-item", role: "menuitem", onclick: () => add(cmd) },
      h("span", { class: "cmd-badge" }, cmd), label)));
  menu.addEventListener("keydown", (e) => { if (e.key === "Escape") { closeAddMenu(); anchor.focus(); } });
  document.body.append(menu);
  const r = anchor.getBoundingClientRect();
  menu.style.left = `${Math.max(8, Math.min(r.left, innerWidth - menu.offsetWidth - 8))}px`;
  menu.style.top = `${r.bottom + 8 + menu.offsetHeight > innerHeight ? r.top - 8 - menu.offsetHeight : r.bottom + 8}px`;
  document.addEventListener("mousedown", outside);
  menu.querySelector("button").focus();
}

// ---- 生物、物品標題下「放在哪」的小標籤 ----

// kind 是 mobiles、objects。點了跳到那間房；找不到房間（例如 P 放進容器）就跳到總覽的那一筆
export function placesOf(ctx, kind, item) {
  const { state } = ctx;
  const data = state.data;
  const resets = M.listOf(data, "resets");
  const toOverview = (index) => () => { Object.assign(state, { resetIndex: index, resetFilter: "all" }); ctx.setMode("resets"); };
  const roomText = (r) => { const t = lookup(ctx, "rooms", r.room_vnum); return `房間 ${t.num} ${t.name}`; };
  const chips = M.resetsPointingAt(data, kind, item).map(({ index, key }) => {
    const r = resets[index];
    let text = "";
    let room = null;
    if (r.cmd === "M" || r.cmd === "O") {
      room = M.resetThing(data, r, "room_vnum");
      text = `放在 ${roomText(r)}` + (r.cmd === "M" && M.isInt(r.limit) ? ` · 最多 ${r.limit} 隻` : "");
    } else if (r.cmd === "G") {
      const lead = M.leaderOf(resets, index);
      text = lead >= 0 ? `給 ${lookup(ctx, "mobiles", resets[lead].mob_vnum).name}` : "給生物（前面沒有放生物）";
      room = lead >= 0 ? M.resetThing(data, resets[lead], "room_vnum") : null;
    } else if (r.cmd === "P") {
      text = key === "container_vnum" ? `裝著 ${lookup(ctx, "objects", r.obj_vnum).name}` : `放進 ${lookup(ctx, "objects", r.container_vnum).name}`;
    }
    return h("button", { type: "button", class: "place", onclick: room ? () => ctx.goRoom(room) : toOverview(index) },
      h("span", { class: "key" }, r.cmd), text);
  });
  return h("div", { class: "places" }, chips.length ? chips : h("span", { class: "place place-none" }, "沒有放在任何地方"));
}
