// 物品畫面：左欄是物品清單，右邊表單佔滿（沒有地圖）。
// 分頁照使用者的規則：只有一份的欄位全部放「基本資料」（含 values、旗標），可以一直新增的清單（加成、可以細看的東西）各自一個分頁。
import {
  extraList, flagsField, numberField, removeButton, scriptRow, section, selectField, tabBar, textField, textOf,
  vnumField,
} from "./forms.js";
import * as M from "./model.js";
import { placesOf } from "./resets.js";
import * as T from "./tables.js";
import { confirmDialog, field, h, icon, numberText, textInput, toast } from "./ui.js";

const TABS = [["basic", "基本資料"], ["affects", "加成"], ["extra", "可以細看的東西"]];

export function listItems(ctx) {
  const { state } = ctx;
  return M.sortedList(M.listOf(state.data, "objects")).map((o) =>
    h("button", { type: "button", class: "nav-item", "aria-current": o === state.obj ? "page" : null,
      onclick: () => { Object.assign(state, { obj: o, thingDraft: null, thingError: null }); ctx.refresh(); } },
    h("span", { class: "nav-num" }, numberText(o.vnum)),
    h("span", { class: "nav-name" }, textOf(o.short))));
}

export function add(ctx) {
  const obj = M.addThing(ctx.state.data, "objects");
  if (!obj) return toast("物品號碼 1～99 都用完了");
  Object.assign(ctx.state, { obj, objTab: "basic", thingDraft: null, thingError: null });
  ctx.rebuild();
}

async function remove(ctx) {
  const me = ctx.state;
  const obj = me.obj;
  const n = M.resetsGoingWith(me.data, "objects", obj);
  const ok = await confirmDialog({
    title: `刪除物品 ${numberText(obj.vnum)}？`,
    text: `「${textOf(obj.short)}」${n ? `和 ${n} 筆重置` : ""}會一起拿掉。`,
    ok: "刪除", danger: true,
  });
  if (!ok || ctx.state !== me) return;
  M.deleteThing(me.data, "objects", obj);
  Object.assign(me, { obj: M.sortedList(M.listOf(me.data, "objects"))[0] || null, thingDraft: null, thingError: null });
  ctx.rebuild();
}

export function render(ctx) {
  const { state, ui } = ctx;
  const obj = state.obj;
  if (!obj) {
    ui.panel.replaceChildren(h("div", { class: "panel-empty" },
      h("button", { type: "button", class: "btn", onclick: () => add(ctx) }, icon("plus", 18), "新增物品")));
    return;
  }
  const number = M.roomNumber(state.data, obj);
  ui.thingTitle = h("h1", { class: "insp-title" }, textOf(obj.short));
  const tab = { basic: basicTab, affects: affectsTab, extra: extraTab }[state.objTab] || basicTab;
  ui.panel.replaceChildren(
    h("div", { class: "panel-head" },
      h("div", { class: "insp-names" },
        h("span", { class: "eyebrow" }, `物品 ${numberText(obj.vnum)}` + (number !== null ? ` · 遊戲裡 ${number} 號` : "")),
        ui.thingTitle,
        placesOf(ctx, "objects", obj)),
      h("button", { type: "button", class: "btn btn-text btn-danger", onclick: () => remove(ctx) }, "刪除物品")),
    tabBar(TABS, state.objTab, (key) => { state.objTab = key; render(ctx); }),
    h("div", { class: "panel-body", role: "tabpanel" }, h("div", { class: "panel-inner" }, tab(ctx, obj))));
}

function basicTab(ctx, obj) {
  const done = ctx.edited;
  const shortDone = () => { ctx.ui.thingTitle.textContent = textOf(obj.short); done(); };
  return h("div", { class: "stack" },
    h("div", { class: "row row-top" },
      vnumField({ ctx, kind: "objects", item: obj, id: "obj-vnum", label: "物品號碼" }),
      textField({ id: "obj-keywords", label: "名字", code: "keywords", obj, key: "keywords", done })),
    textField({ id: "obj-short", label: "短名稱", code: "short", obj, key: "short", done: shortDone }),
    textField({ id: "obj-long", label: "放在地上的樣子", code: "long", obj, key: "long", done }),
    h("div", { class: "row" },
      selectField({ id: "obj-type", label: "種類", code: "item_type", obj, key: "item_type", options: T.ITEM_TYPES,
        done: ctx.rebuild }),                     // 種類換了，values 的欄位名也要換
      numberField({ id: "obj-weight", label: "重量", code: "weight", obj, key: "weight", style: "flex: 0 0 120px", done }),
      numberField({ id: "obj-cost", label: "價格", code: "cost", obj, key: "cost", style: "flex: 0 0 120px",
        tip: "可以是 0；商店買賣的價格是它乘上店主的 profit_buy、profit_sell", done })),
    section("數值", "values", valuesGrid(ctx, obj)),
    h("div", { class: "stack sep" },
      flagsField({ legend: "特性", code: "extra_flags", obj, key: "extra_flags", table: T.EXTRA_FLAGS, columns: 3, done }),
      flagsField({ legend: "拿起來、穿在哪裡", code: "wear_flags", obj, key: "wear_flags", table: T.WEAR_FLAGS, columns: 3, done })),
    scriptRow(obj.script));
}

// values 的 4 個欄位：名字和寫法看物品種類（tables.js 的 VALUE_FIELDS，照手冊的表）
function valuesGrid(ctx, obj) {
  const done = ctx.edited;
  const kinds = T.VALUE_FIELDS[obj.item_type] || [0, 1, 2, 3].map((i) => [`第 ${i + 1} 個`, "number"]);
  if (!Array.isArray(obj.values)) obj.values = [0, 0, 0, 0];   // 檔案沒寫 values 時才補上（檢查會報少了欄位）
  const values = obj.values;
  const cells = kinds.map(([label, kind, tip], i) => {
    const id = `val-${i}`;
    const code = `values[${i}]`;
    if (kind === "spell") return textField({ id, label, code, obj: values, key: i, tip: tip || "法術名稱，例如 cure light；不用的寫空的", done });
    if (kind === "attack") return selectField({ id, label, code, obj: values, key: i, options: T.ATTACKS, done });
    if (kind === "weapon") return selectField({ id, label, code, tip, obj: values, key: i, options: T.WEAPON_KINDS, done });
    if (kind === "liquid") return selectField({ id, label, code, obj: values, key: i, options: T.LIQUIDS, done });
    if (kind === "auto") {                  // 由裝備等級算，作者不用寫：照原本的值顯示，不能改
      return field({ id, label, code, tip, input: textInput({ id, value: numberText(values[i]), disabled: true }) });
    }
    if (kind === "container") {
      return h("div", { class: "wide" }, flagsField({ legend: label, code, obj: values, key: i, table: T.CONTAINER_FLAGS, columns: 3, done }));
    }
    return numberField({ id, label, code, obj: values, key: i, tip, done });
  });
  return h("div", { class: "values-grid" }, cells);
}

function affectsTab(ctx, obj) {
  const done = ctx.edited;
  const list = Array.isArray(obj.affects) ? obj.affects : [];
  const add = () => {
    if (!Array.isArray(obj.affects)) obj.affects = [];
    obj.affects.push(M.newAffect());
    ctx.rebuild();
    document.getElementById(`aff-${obj.affects.length - 1}-mod`).focus();
  };
  return h("div", { class: "stack", style: "gap: 16px" },
    h("div", { class: "list-head" }, h("span", { class: "code" }, "affects"),
      h("button", { type: "button", class: "btn", onclick: add }, icon("plus", 18), "新增")),
    list.map((a, i) => h("div", { class: "row affect-row" },
      selectField({ id: `aff-${i}-loc`, label: "加在哪裡", code: "location", obj: a, key: "location", options: T.APPLY, done }),
      numberField({ id: `aff-${i}-mod`, label: "加多少", code: "modifier", obj: a, key: "modifier", style: "flex: 0 0 120px", done }),
      removeButton(() => { list.splice(i, 1); ctx.rebuild(); }))));
}

function extraTab(ctx, obj) {
  if (!Array.isArray(obj.extra_descriptions)) obj.extra_descriptions = [];
  return extraList({ list: obj.extra_descriptions, prefix: "oextra", edited: ctx.edited, rebuild: ctx.rebuild });
}
