// 畫面用的小工具：建元素、圖示、輸入框、對話框、提示。
// 區域檔的文字一律用 textContent 放進畫面（h() 的子元素字串會變成純文字），不用 innerHTML。

const SVG_NS = "http://www.w3.org/2000/svg";

// 建一個元素：先放子元素再設屬性（<select> 要先有 <option> 才能設 value）
export function h(tag, props, ...children) {
  const el = document.createElement(tag);
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : String(c));
  }
  for (const [k, v] of Object.entries(props || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style") typeof v === "string" ? (el.style.cssText = v) : Object.assign(el.style, v);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (["value", "checked", "disabled", "title", "type", "id", "rows", "href"].includes(k)) el[k] = v;
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  return el;
}

// 圖示的線條（都是固定的字串，不是區域檔的內容）
const ICONS = {
  plus: '<path d="M12 5v14M5 12h14"></path>',
  close: '<path d="M6 6l12 12M18 6L6 18"></path>',
  ok: '<circle cx="12" cy="12" r="9"></circle><path d="M8 12.5l2.5 2.5L16 9.5"></path>',
  alert: '<circle cx="12" cy="12" r="9"></circle><path d="M12 7.5v5.5M12 16.5h.01"></path>',
  up: '<path d="M6 15l6-6 6 6"></path>',
  down: '<path d="M6 9l6 6 6-6"></path>',
  arrowUp: '<path d="M12 19V5M6 11l6-6 6 6"></path>',
  arrowDown: '<path d="M12 5v14M6 13l6 6 6-6"></path>',
  logo: '<rect x="3" y="3" width="7" height="7" rx="1.5"></rect><rect x="14" y="3" width="7" height="7" rx="1.5"></rect><rect x="14" y="14" width="7" height="7" rx="1.5"></rect><path d="M10 6.5h4M17.5 10v4"></path>',
  gear: '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"></path><circle cx="12" cy="12" r="3"></circle>',
};

export function icon(name, size = 20) {
  const svg = document.createElementNS(SVG_NS, "svg");
  const attrs = { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
    "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" };
  for (const [k, v] of Object.entries(attrs)) svg.setAttribute(k, v);
  svg.innerHTML = ICONS[name];
  return svg;
}

// 左上角的標誌和「區域編輯器」；onclick 有給就是回選檔畫面的按鈕
export function brand(onclick) {
  const inner = [h("span", { class: "brand-mark" }, icon("logo", 18)), h("span", { class: "brand-name" }, "區域編輯器")];
  return onclick ? h("button", { type: "button", class: "brand", "aria-label": "回到區域檔清單", onclick }, inner)
    : h("div", { class: "brand" }, inner);
}

// ---- 數字和文字在畫面和檔案之間的轉換 ----

// 檔案裡的值 → 輸入框顯示的字
export function numberText(v) {
  if (v === null || v === undefined) return "";
  return typeof v === "string" ? v : JSON.stringify(v);
}

// 輸入框的字 → 存進檔案的值：整數就存數字，空的存 null，其他照打的存（讓檢查報錯）
export function parseNumber(text) {
  const t = text.trim();
  if (t === "") return null;
  return /^-?\d+$/.test(t) ? Number(t) : text;
}

// 描述類的文字：顯示時拿掉最後一個換行；存回時不是空的才補一個換行（跟現有檔案一樣）
export function plainText(v) {
  if (typeof v !== "string") return numberText(v);
  return v.endsWith("\n") ? v.slice(0, -1) : v;
}

export function storedText(text) {
  return text === "" ? "" : text + "\n";
}

// ---- 輸入框 ----

// 外框線的輸入框，名字浮在左上角；code 是區域檔裡的英文欄位名
export function field({ id, label, code, input, error, off, extra, style }) {
  const cls = "field" + (error ? " field-bad" : "") + (off ? " field-off" : "");
  return h("div", { class: cls, style },
    h("label", { class: "field-label", for: id }, label, code ? h("span", { class: "key" }, code) : null),
    input, extra,
    error ? h("div", { class: "field-error" }, error) : null);
}

export function textInput(props) {
  return h("input", { type: "text", class: "field-input", autocomplete: "off", spellcheck: "false", ...props });
}

export function textArea(props) {
  return h("textarea", { class: "field-input", spellcheck: "false", ...props });
}

// options 是 [[數字, 名字], …]，選項顯示成「0 室內」。檔案裡的值不在選項裡時，多一個選項照實顯示
export function selectInput({ id, value, options, onchange, disabled }) {
  const known = options.some(([v]) => v === value);
  const items = options.map(([v, label]) => h("option", { value: String(v) }, `${v} ${label}`));
  if (!known) items.unshift(h("option", { value: "", disabled: true }, `${numberText(value) || "沒有寫"}（不對的值）`));
  const select = h("select", { id, class: "field-input", onchange, disabled }, items);
  select.value = known ? String(value) : "";
  return select;
}

export function selectArrow() {
  const svg = icon("down");
  svg.setAttribute("class", "select-arrow");
  return svg;
}

// 一個勾選框：label 後面放區域檔裡寫的值（code），tip 是滑鼠停上去才出現的規則
export function checkbox({ label, code, tip, checked, onchange }) {
  return h("label", { class: "check", title: tip },
    h("input", { type: "checkbox", checked, onchange }),
    h("span", { class: tip ? "tip" : null }, label),
    code === undefined ? null : h("span", { class: "code" }, String(code)));
}

export function chip(kind, text) {
  return h("span", { class: `chip chip-sm chip-room chip-${kind}` }, icon(kind === "ok" ? "ok" : "alert", 16), text);
}

// ---- 浮動視窗 ----

// 開一個浮動視窗；回傳 close()。按 Esc 或點外面的暗色區域等於按 onCancel
export function openDialog({ title, body, footer, small, onCancel, labelId }) {
  const id = labelId || "dialog-title";
  const dialog = h("section", { class: "dialog" + (small ? " dialog-sm" : ""), role: "dialog", "aria-modal": "true", "aria-labelledby": id },
    h("div", { class: "dialog-head" },
      h("h2", { class: "dialog-title", id }, title),
      h("button", { type: "button", class: "icon-btn icon-btn-lg", "aria-label": "關閉", onclick: () => onCancel() }, icon("close"))),
    h("div", { class: "dialog-body" }, body),
    h("div", { class: "dialog-foot" }, footer));
  const scrim = h("div", { class: "scrim", onmousedown: (e) => { if (e.target === scrim) onCancel(); } }, dialog);
  scrim.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.stopPropagation(); onCancel(); } });
  const before = document.activeElement;
  document.body.append(scrim);
  (dialog.querySelector("input, select, textarea") || dialog.querySelector(".dialog-foot button:last-child")).focus();
  return () => { scrim.remove(); if (before && before.isConnected) before.focus(); };
}

// 問一次「確定嗎？」，回傳 Promise<true/false>。不用瀏覽器的 confirm()
export function confirmDialog({ title, text, ok, danger }) {
  return new Promise((resolve) => {
    const done = (answer) => { close(); resolve(answer); };
    const close = openDialog({
      title, small: true, onCancel: () => done(false),
      body: h("p", { class: "dialog-text" }, text),
      footer: [
        h("button", { type: "button", class: "btn btn-text", onclick: () => done(false) }, "取消"),
        h("button", { type: "button", class: "btn btn-filled" + (danger ? " btn-danger" : ""), onclick: () => done(true) }, ok),
      ],
    });
  });
}

// 左下角的短訊息，幾秒後自己消失
let toastTimer = null;
export function toast(text) {
  document.querySelector(".toast")?.remove();
  clearTimeout(toastTimer);
  const el = h("div", { class: "toast", role: "status" }, text);
  document.body.append(el);
  toastTimer = setTimeout(() => el.remove(), 3000);
}
