// 房間的「重置」分頁：放在這裡的生物（和給牠的物品 G）、物品（和放進去的東西 P）、門一開始的狀態 D、打亂出口 R。
// 新增時編輯器自己決定插在清單的哪裡：M、O、D、R 加在最後；G、P 插在它跟著的那一筆後面（model.js 的 addFollower）。
// 全部的重置（含註解 *、順序）在重置總覽改。
import { addButton, numberField, refField, removeButton, textField } from "./forms.js";
import * as M from "./model.js";
import * as T from "./tables.js";
import { field, h, icon, numberText, selectArrow } from "./ui.js";

const RARE_TIP = "0～10 一定會出現；大於 10 是稀有，機率大約 (rare − 10) ÷ 10000";

function first(data, kind) {
  return (M.sortedList(M.listOf(data, kind))[0] || { vnum: 1 }).vnum;
}

function heading(title, code, ...right) {
  return h("div", { class: "list-head" },
    h("h2", { class: "section-title" }, title, h("span", { class: "code" }, code)), ...right);
}

export function resetsTab(ctx, room) {
  const { state } = ctx;
  const data = state.data;
  const resets = M.listOf(data, "resets");
  const rr = M.roomResets(data, room);
  const done = ctx.edited;
  const add = (entry) => { M.insertReset(data, entry); ctx.rebuild(); };
  const addAfter = (i, entry) => { M.addFollower(data, i, entry); ctx.rebuild(); };
  const drop = (i) => { M.removeReset(data, i); ctx.rebuild(); };

  // 一筆跟著的 G、P：物品號碼和移除
  const followerRow = (j) => {
    const g = resets[j];
    return h("div", { class: "row" },
      refField({ id: `rr-${j}-obj`, label: "物品", code: "obj_vnum", obj: g, key: "obj_vnum", chipOf: (n) => ctx.chipOf("objects", n), done }),
      g.cmd === "G" ? numberField({ id: `rr-${j}-rare`, label: "稀有度", code: "rare", obj: g, key: "rare", tip: RARE_TIP, style: "flex: 0 0 96px", done }) : null,
      removeButton(() => drop(j)));
  };

  const mobCards = rr.mobs.map(({ index, followers }) => {
    const r = resets[index];
    return h("div", { class: "card card-form" },
      h("div", { class: "row" },
        refField({ id: `rr-${index}-mob`, label: "生物", code: "mob_vnum", obj: r, key: "mob_vnum", chipOf: (n) => ctx.chipOf("mobiles", n), done }),
        removeButton(() => drop(index))),
      h("div", { class: "row" },
        numberField({ id: `rr-${index}-limit`, label: "最多", code: "limit", obj: r, key: "limit", style: "flex: 0 0 104px",
          tip: "生物待在原地時算這個房間有幾隻，不然算整個遊戲", done }),
        numberField({ id: `rr-${index}-rare`, label: "稀有度", code: "rare", obj: r, key: "rare", style: "flex: 0 0 104px", tip: RARE_TIP, done }),
        textField({ id: `rr-${index}-comment`, label: "註解", code: "comment", obj: r, key: "comment", done })),
      h("div", { class: "stack sep", style: "gap: 20px" },
        h("span", { class: "sub-title" }, "給牠的物品", h("span", { class: "code" }, "G")),
        followers.map(followerRow),
        addButton("給物品", () => addAfter(index, M.newReset("G", { obj_vnum: first(data, "objects") })))));
  });

  const objCards = rr.objs.map(({ index, followers }) => {
    const r = resets[index];
    return h("div", { class: "card card-form" },
      h("div", { class: "row" },
        refField({ id: `rr-${index}-obj`, label: "物品", code: "obj_vnum", obj: r, key: "obj_vnum", chipOf: (n) => ctx.chipOf("objects", n), done }),
        removeButton(() => drop(index))),
      textField({ id: `rr-${index}-comment`, label: "註解", code: "comment", obj: r, key: "comment", done }),
      h("div", { class: "stack sep", style: "gap: 20px" },
        h("span", { class: "sub-title" }, "放進去的東西", h("span", { class: "code" }, "P")),
        followers.map(followerRow),
        addButton("放東西進去", () => addAfter(index, M.newReset("P", { obj_vnum: first(data, "objects"), container_vnum: r.obj_vnum })))));
  });

  // 門：只列出有門的出口；選「不設定」就是沒有 D 這一筆
  const doors = M.DIRECTIONS.filter((d) => room.exits[d] && room.exits[d].locks !== 0).map((d) => {
    const i = d in rr.doors ? rr.doors[d] : -1;
    const keywords = typeof room.exits[d].keywords === "string" ? room.exits[d].keywords.trim().split(/\s+/)[0] : "";
    const select = h("select", { id: `rr-door-${d}`, class: "field-input",
      onchange: (e) => {
        const v = e.target.value;
        if (v === "") drop(i);
        else if (i >= 0) { resets[i].state = Number(v); done(); }
        else add(M.newReset("D", { room_vnum: room.vnum, direction: d, state: Number(v) }));
      } },
    h("option", { value: "" }, "不設定"),
    T.DOOR_STATES.map(([n, label]) => h("option", { value: String(n) }, `${n} ${label}`)));
    select.value = i >= 0 && T.DOOR_STATES.some(([n]) => n === resets[i].state) ? String(resets[i].state) : "";
    return h("div", { class: "row" },
      h("span", { class: "door-name" }, h("strong", null, M.DIR_NAMES[d]), keywords ? h("span", { class: "muted" }, keywords) : null),
      field({ id: `rr-door-${d}`, label: "狀態", code: "state", input: select, extra: selectArrow(), style: "flex: 0 0 220px" }));
  });

  // 打亂出口：一間房一筆
  const r = rr.random >= 0 ? resets[rr.random] : null;
  const shuffle = r
    ? h("div", { class: "row" },
      field({ id: "rr-shuffle", label: "打亂前幾個方向", code: "exit_count", style: "flex: 0 0 220px", extra: selectArrow(), input: (() => {
        const options = [0, 1, 2, 3, 4, 5, 6].map((n) => h("option", { value: String(n) },
          n < 2 ? `${n} 不打亂` : `${n} ${M.DIRECTIONS.slice(0, n).map((x) => M.DIR_NAMES[x]).join("、")}`));
        const select = h("select", { id: "rr-shuffle", class: "field-input", onchange: (e) => { r.exit_count = Number(e.target.value); done(); } },
          M.isInt(r.exit_count) && r.exit_count >= 0 && r.exit_count <= 6 ? null
            : h("option", { value: "", disabled: true }, `${numberText(r.exit_count) || "沒有寫"}（不對的值）`),
          options);
        select.value = M.isInt(r.exit_count) && r.exit_count >= 0 && r.exit_count <= 6 ? String(r.exit_count) : "";
        return select;
      })() }),
      removeButton(() => drop(rr.random)))
    : null;

  return h("div", { class: "stack", style: "gap: 28px" },
    h("section", { class: "stack", style: "gap: 12px" },
      heading("放在這裡的生物", "M", h("button", { type: "button", class: "btn",
        onclick: () => add(M.newReset("M", { mob_vnum: first(data, "mobiles"), room_vnum: room.vnum })) }, icon("plus", 18), "放生物")),
      mobCards),
    h("section", { class: "stack", style: "gap: 12px" },
      heading("放在這裡的物品", "O", h("button", { type: "button", class: "btn",
        onclick: () => add(M.newReset("O", { obj_vnum: first(data, "objects"), room_vnum: room.vnum })) }, icon("plus", 18), "放物品")),
      objCards),
    doors.length ? h("section", { class: "stack", style: "gap: 20px" }, heading("門一開始的狀態", "D"), doors) : null,
    h("section", { class: "stack", style: "gap: 20px" },
      heading("打亂出口", "R", r ? null : h("button", { type: "button", class: "btn",
        onclick: () => add(M.newReset("R", { room_vnum: room.vnum, exit_count: 2 })) }, icon("plus", 18), "打亂出口")),
      shuffle));
}
