// 區域設定的浮動視窗：改的是整個區域共用的欄位（area、area.header）。
// 「完成」才套用，「取消」不改；只寫回有改過的欄位，沒動到的原樣保留（例如 gem 寫 2）。
import { AREA_RULES, AREA_TYPES, RESET_EMPTY, RESET_PLAYERS } from "./model.js";
import { checkbox, field, h, numberText, openDialog, parseNumber, selectArrow, selectInput, textInput } from "./ui.js";

const textOf = (v) => (typeof v === "string" ? v : numberText(v));

// roomChip(號碼) 是「回城房間」旁邊的房間名；onDone() 在有改東西時呼叫
export function openSettings({ data, roomChip, onDone }) {
  const area = data.area;
  const header = area.header;
  const levels = Array.isArray(header.levels) ? header.levels : [];
  const vnums = Array.isArray(header.vnums) ? header.vnums : [];
  const inputs = {
    title: textInput({ id: "area-title", value: textOf(header.title) }),
    author: textInput({ id: "area-author", value: textOf(header.author) }),
    min: textInput({ id: "area-level-min", value: numberText(levels[0]) }),
    max: textInput({ id: "area-level-max", value: numberText(levels[1]) }),
    vmin: textInput({ id: "area-vnum-min", value: numberText(vnums[0]) }),
    vmax: textInput({ id: "area-vnum-max", value: numberText(vnums[1]) }),
    type: selectInput({ id: "area-type", value: header.type, options: AREA_TYPES }),
    opened: textInput({ id: "area-opened", value: textOf(header.opened), placeholder: "YYYY-MM-DD" }),
    rempty: textInput({ id: "area-reset-empty", value: numberText(header.reset_empty), placeholder: String(RESET_EMPTY) }),
    rplayers: textInput({ id: "area-reset-players", value: numberText(header.reset_players), placeholder: String(RESET_PLAYERS) }),
    recall: textInput({ id: "area-recall", value: numberText(area.recall) }),
  };
  const initial = Object.fromEntries(Object.entries(inputs).map(([k, el]) => [k, el.value]));
  const chipBox = h("div", { style: "min-width: 0; display: flex" });
  const showChip = () => chipBox.replaceChildren(roomChip(parseNumber(inputs.recall.value)) || "");
  showChip();
  inputs.recall.addEventListener("input", showChip);

  const rules = AREA_RULES.map((rule) => {
    const was = rule.on(area[rule.key]);
    const box = checkbox({ label: rule.label, code: rule.key, tip: rule.tip, checked: was });
    return { rule, was, box, input: box.querySelector("input") };
  });

  const apply = () => {
    const changed = (k) => inputs[k].value !== initial[k];
    let any = false;
    const set = (obj, key, value) => { obj[key] = value; any = true; };
    if (changed("title")) set(header, "title", inputs.title.value);
    if (changed("author")) set(header, "author", inputs.author.value);
    if (changed("min") || changed("max")) set(header, "levels", [parseNumber(inputs.min.value), parseNumber(inputs.max.value)]);
    if (changed("vmin") || changed("vmax")) set(header, "vnums", [parseNumber(inputs.vmin.value), parseNumber(inputs.vmax.value)]);
    if (changed("type")) set(header, "type", inputs.type.value);
    if (changed("opened")) set(header, "opened", inputs.opened.value.trim() || null);   // 空著是 null（不標「新」）
    if (changed("rempty")) set(header, "reset_empty", parseNumber(inputs.rempty.value));
    if (changed("rplayers")) set(header, "reset_players", parseNumber(inputs.rplayers.value));
    if (changed("recall")) set(area, "recall", parseNumber(inputs.recall.value));
    for (const r of rules) if (r.input.checked !== r.was) set(area, r.rule.key, r.input.checked ? 1 : null);
    close();
    if (any) onDone();
  };

  const close = openDialog({
    title: "區域設定",
    labelId: "area-settings-title",
    onCancel: () => close(),
    body: [
      h("div", { class: "row" },
        field({ id: "area-title", label: "區域名稱", code: "title", input: inputs.title }),
        field({ id: "area-author", label: "作者", code: "author", input: inputs.author })),
      h("div", { class: "row" },
        h("div", { class: "row", style: "flex: 0 0 auto; gap: 8px" },
          field({ id: "area-level-min", label: "最低等級", input: inputs.min, style: "flex: 0 0 96px" }),
          h("span", { "aria-hidden": "true", style: "color: var(--ink2)" }, "～"),
          field({ id: "area-level-max", label: "最高等級", input: inputs.max, style: "flex: 0 0 96px" }),
          h("span", { class: "code" }, "levels"))),
      h("div", { class: "row" },
        h("div", { class: "row", style: "flex: 0 0 auto; gap: 8px" },
          field({ id: "area-vnum-min", label: "最小號碼", input: inputs.vmin, style: "flex: 0 0 96px" }),
          h("span", { "aria-hidden": "true", style: "color: var(--ink2)" }, "～"),
          field({ id: "area-vnum-max", label: "最大號碼", input: inputs.vmax, style: "flex: 0 0 96px" }),
          h("span", { class: "code" }, "vnums"))),
      h("div", { class: "row" },
        field({ id: "area-type", label: "區域種類", code: "type", input: inputs.type, extra: selectArrow(), style: "flex: 0 0 220px" }),
        field({ id: "area-opened", label: "開放日期", code: "opened", input: inputs.opened, style: "flex: 0 0 180px",
          tip: "寫了日期（例如 2026-11-20），14 天內 area 會標「新」、登入公告會列出；空著是不標" })),
      h("fieldset", null, h("legend", null, "幾分鐘重生一次"),
        h("div", { class: "row" },
          field({ id: "area-reset-empty", label: "沒有玩家時", code: "reset_empty", input: inputs.rempty, style: "flex: 0 0 180px",
            tip: `空著是預設的 ${RESET_EMPTY} 分鐘` }),
          field({ id: "area-reset-players", label: "有玩家時", code: "reset_players", input: inputs.rplayers, style: "flex: 0 0 180px",
            tip: `空著是預設的 ${RESET_PLAYERS} 分鐘` }))),
      h("div", { class: "row", style: "gap: 12px" },
        field({ id: "area-recall", label: "回城房間", code: "recall", input: inputs.recall, style: "flex: 0 0 120px" }),
        chipBox),
      h("fieldset", null, h("legend", null, "特殊規則"), h("div", { class: "checks" }, rules.map((r) => r.box))),
    ],
    footer: [
      h("button", { type: "button", class: "btn btn-text", onclick: () => close() }, "取消"),
      h("button", { type: "button", class: "btn btn-filled", onclick: apply }, "完成"),
    ],
  });
}
