// 區域設定的浮動視窗：改的是整個區域共用的欄位（area、area.header）。
// 「完成」才套用，「取消」不改；只寫回有改過的欄位，沒動到的原樣保留（例如 gem 寫 2）。
import { AREA_RULES } from "./model.js";
import { checkbox, field, h, numberText, openDialog, parseNumber, textInput } from "./ui.js";

const textOf = (v) => (typeof v === "string" ? v : numberText(v));

// roomChip(號碼) 是「回城房間」旁邊的房間名；onDone() 在有改東西時呼叫
export function openSettings({ data, roomChip, onDone }) {
  const area = data.area;
  const header = area.header;
  const levels = Array.isArray(header.levels) ? header.levels : [];
  const inputs = {
    title: textInput({ id: "area-title", value: textOf(header.title) }),
    author: textInput({ id: "area-author", value: textOf(header.author) }),
    min: textInput({ id: "area-level-min", value: numberText(levels[0]) }),
    max: textInput({ id: "area-level-max", value: numberText(levels[1]) }),
    number: textInput({ id: "area-number", value: numberText(header.area_number) }),
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
    if (changed("number")) set(header, "area_number", parseNumber(inputs.number.value));
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
          h("span", { class: "code" }, "levels")),
        field({ id: "area-number", label: "區域號碼", code: "area_number", input: inputs.number })),
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
