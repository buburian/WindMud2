// 表單的小工具：欄位直接綁在區域檔的物件上，改了就寫回 obj[key] 再呼叫 done()。
// 生物、物品、重置的畫面和房間的「可以細看的東西」共用。done 通常是 ctx.edited（只重畫不含輸入框的地方）。
import * as M from "./model.js";
import * as T from "./tables.js";
import {
  checkbox, field, h, icon, numberText, parseNumber, plainText, selectArrow, selectInput, storedText,
  textArea, textInput,
} from "./ui.js";

export const textOf = (v) => (typeof v === "string" ? v : numberText(v));

// 一行文字
export function textField({ id, label, code, obj, key, style, tip, done }) {
  return field({ id, label, code, style, tip, input: textInput({
    id, value: textOf(obj[key]), oninput: (e) => { obj[key] = e.target.value; done(); },
  }) });
}

// 多行的描述：顯示時拿掉最後一個換行，存回時不是空的才補一個
export function areaField({ id, label, code, obj, key, rows = 3, done }) {
  return field({ id, label, code, input: textArea({
    id, rows, value: plainText(obj[key]), oninput: (e) => { obj[key] = storedText(e.target.value); done(); },
  }) });
}

// 數字：打的不是整數就照打的存，讓檢查報錯
export function numberField({ id, label, code, obj, key, style, tip, done }) {
  return field({ id, label, code, style, tip, input: textInput({
    id, value: numberText(obj[key]), oninput: (e) => { obj[key] = parseNumber(e.target.value); done(); },
  }) });
}

// 下拉選單：options 是 [[數字, 名字], …]
export function selectField({ id, label, code, obj, key, options, style, done }) {
  return field({ id, label, code, style, extra: selectArrow(), input: selectInput({
    id, value: obj[key], options, onchange: (e) => { obj[key] = Number(e.target.value); done(); },
  }) });
}

// 代號的下拉選單：options 是 [[代號或 null, 名字], …]，選了就存回那個代號（null 也照存）
export function codeField({ id, label, code, obj, key, options, style, done }) {
  return field({ id, label, code, style, extra: selectArrow(), input: selectInput({
    id, value: obj[key], options,
    onchange: (e) => { obj[key] = options.find(([v]) => String(v) === e.target.value)[0]; done(); },
  }) });
}

// 裝備的顏色（掉落表、重置 G O P 的 color）：不是裝備存成 null
export function colorField({ id, obj, done }) {
  return codeField({ id, label: "顏色", code: "color", obj, key: "color",
    options: [[null, "不是裝備"], ...T.ITEM_COLORS], style: "flex: 0 0 160px", done });
}

// 重置放出的物品（G、O、P）：顏色和等級。G 的等級空著（null）是前面那筆 M 的怪物等級；O、P 一定要寫
export function itemLookRow(r, idPrefix, done) {
  const tip = r.cmd === "G" ? "空著是前面那筆 M 的怪物等級；商店要賣低等裝備就自己寫" : "O、P 沒有怪物帶著，一定要寫";
  return h("div", { class: "row" },
    colorField({ id: `${idPrefix}-color`, obj: r, done }),
    numberField({ id: `${idPrefix}-level`, label: "等級", code: "level", obj: r, key: "level", tip, style: "flex: 0 0 120px", done }));
}

// 旗標的勾選：table 是 [[位元, 名字, 說明], …]。勾了才把值改成數字，沒動過的 "2|64" 寫法原樣保留
export function flagsField({ legend, code, obj, key, table, columns = 2, done }) {
  const value = M.parseFlags(obj[key]);
  return h("fieldset", null,
    h("legend", null, legend, h("span", { class: "code" }, code)),
    h("div", { class: columns === 3 ? "flags flags-3" : "flags" }, table.map(([bit, label, tip]) => checkbox({
      label, code: bit, tip, checked: value !== null && (value & bit) !== 0,
      onchange: (e) => {
        const now = M.parseFlags(obj[key]) || 0;
        obj[key] = e.target.checked ? now | bit : now & ~bit;
        done();
      },
    }))));
}

// 號碼欄位，旁邊顯示它指到誰：chipOf(號碼) 回傳綠色（找得到）或紅色（找不到）的標籤
export function refField({ id, label, code, obj, key, chipOf, style = "flex: 0 0 120px", done }) {
  const box = h("div", { class: "ref-chip" });
  const show = () => box.replaceChildren(chipOf(obj[key]) || "");
  show();
  return h("div", { class: "row", style: "gap: 12px" },
    field({ id, label, code, style, input: textInput({
      id, value: numberText(obj[key]), oninput: (e) => { obj[key] = parseNumber(e.target.value); show(); done(); },
    }) }),
    box);
}

// 生物、物品的號碼（kind 是 mobiles、objects）：打完才套用，這個檔裡指到它的地方一起改；
// 號碼不對（不在 1～99、重複）就不套用，留著打的字並在欄位下面寫錯誤
export function vnumField({ ctx, kind, item, id, label }) {
  const { state } = ctx;
  const input = textInput({
    id, value: state.thingDraft !== null ? state.thingDraft : numberText(item.vnum),
    onchange: (e) => {
      const vnum = parseNumber(e.target.value);
      const same = vnum === item.vnum;           // 要在 renumberThing 之前比，改完 item.vnum 就是新的了
      const error = same ? null : M.renumberThing(state.data, kind, item, vnum);
      state.thingDraft = error ? e.target.value : null;
      state.thingError = error;
      if (error || same) ctx.refresh();
      else ctx.rebuild();
      if (error) document.getElementById(id).focus();
    },
  });
  return field({ id, label, code: "vnum", input, error: state.thingError, style: "flex: 0 0 120px" });
}

// 分頁列：tabs 是 [[名稱, 顯示的字], …]，pick(名稱) 換分頁
export function tabBar(tabs, current, pick) {
  return h("div", { class: "tabs", role: "tablist" }, tabs.map(([key, label]) =>
    h("button", { type: "button", class: "tab", role: "tab", "aria-selected": String(current === key), onclick: () => pick(key) }, label)));
}

// 一段：標題（後面是檔案裡的欄位名）加內容，跟上一段之間有一條線
export function section(title, code, ...children) {
  return h("section", { class: "form-section" },
    h("h2", { class: "section-title" }, title, code ? h("span", { class: "code" }, code) : null), ...children);
}

export function addButton(label, onclick) {
  return h("div", null, h("button", { type: "button", class: "btn", onclick }, icon("plus", 18), label));
}

export function removeButton(onclick, label = "移除") {
  return h("button", { type: "button", class: "btn btn-text btn-danger", onclick }, label);
}

// 觸發程式：只顯示，不能改
export function scriptRow(script) {
  let text = "有";
  if (script === null || script === undefined) text = "沒有";
  else if (script && typeof script.function === "string" && script.function) text = script.function;
  return h("div", { class: "info-row" },
    h("span", { class: "label" }, "觸發程式", h("span", { class: "code", style: "margin-left: 6px" }, "script")),
    h("span", null, text));
}

function firstWord(keywords) {
  return typeof keywords === "string" ? keywords.trim().split(/\s+/)[0] : "";
}

// 可以細看的東西（房間、物品都有）：每項一張卡片，可以新增、移除
export function extraList({ list, prefix, edited, rebuild }) {
  const cards = list.map((ed, i) => {
    const title = h("h2", { class: "card-title" }, firstWord(ed.keywords));
    return h("div", { class: "card" },
      h("div", { class: "card-head" }, title, removeButton(() => { list.splice(i, 1); rebuild(); })),
      field({ id: `${prefix}-${i}-keywords`, label: "名字", code: "keywords", input: textInput({
        id: `${prefix}-${i}-keywords`, value: textOf(ed.keywords),
        oninput: (e) => { ed.keywords = e.target.value; title.textContent = firstWord(ed.keywords); edited(); },
      }) }),
      areaField({ id: `${prefix}-${i}-desc`, label: "看到的文字", code: "description", obj: ed, key: "description", done: edited }));
  });
  return h("div", { class: "stack", style: "gap: 16px" }, cards,
    addButton("新增", () => {
      list.push({ keywords: "", description: "" });
      rebuild();
      document.getElementById(`${prefix}-${list.length - 1}-keywords`).focus();
    }));
}
