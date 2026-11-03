// 生物畫面：左欄是生物清單，右邊表單佔滿（沒有地圖）。
// 分頁照使用者的規則：只有一份的欄位全部放「基本資料」，可以一直新增的清單（兩種動作）各自一個分頁。
import {
  addButton, areaField, flagsField, numberField, refField, removeButton, scriptRow, selectField, tabBar, textField,
  textOf, vnumField,
} from "./forms.js";
import * as M from "./model.js";
import { placesOf } from "./resets.js";
import * as T from "./tables.js";
import { checkbox, confirmDialog, field, h, icon, numberText, selectArrow, toast } from "./ui.js";

const TABS = [["basic", "基本資料"], ["actions", "平常的動作"], ["fight", "戰鬥中的動作"]];

export function listItems(ctx) {
  const { state } = ctx;
  return M.sortedList(M.listOf(state.data, "mobiles")).map((m) =>
    h("button", { type: "button", class: "nav-item", "aria-current": m === state.mob ? "page" : null,
      onclick: () => { Object.assign(state, { mob: m, thingDraft: null, thingError: null }); ctx.refresh(); } },
    h("span", { class: "nav-num" }, numberText(m.vnum)),
    h("span", { class: "nav-name" }, textOf(m.short))));
}

export function add(ctx) {
  const mob = M.addThing(ctx.state.data, "mobiles");
  if (!mob) return toast("生物號碼 1～99 都用完了");
  Object.assign(ctx.state, { mob, mobTab: "basic", thingDraft: null, thingError: null });
  ctx.rebuild();
}

async function remove(ctx) {
  const me = ctx.state;
  const mob = me.mob;
  const n = M.resetsGoingWith(me.data, "mobiles", mob);
  const ok = await confirmDialog({
    title: `刪除生物 ${numberText(mob.vnum)}？`,
    text: `「${textOf(mob.short)}」${n ? `和 ${n} 筆重置` : ""}會一起拿掉。`,
    ok: "刪除", danger: true,
  });
  if (!ok || ctx.state !== me) return;
  M.deleteThing(me.data, "mobiles", mob);
  Object.assign(me, { mob: M.sortedList(M.listOf(me.data, "mobiles"))[0] || null, thingDraft: null, thingError: null });
  ctx.rebuild();
}

export function render(ctx) {
  const { state, ui } = ctx;
  const mob = state.mob;
  if (!mob) {
    ui.panel.replaceChildren(h("div", { class: "panel-empty" }, addButton("新增生物", () => add(ctx))));
    return;
  }
  const number = M.roomNumber(state.data, mob);
  ui.thingTitle = h("h1", { class: "insp-title" }, textOf(mob.short));
  const tab = { basic: basicTab, actions: actionsTab, fight: fightTab }[state.mobTab] || basicTab;
  ui.panel.replaceChildren(
    h("div", { class: "panel-head" },
      h("div", { class: "insp-names" },
        h("span", { class: "eyebrow" }, `生物 ${numberText(mob.vnum)}` + (number !== null ? ` · 遊戲裡 ${number} 號` : "")),
        ui.thingTitle,
        placesOf(ctx, "mobiles", mob)),
      h("button", { type: "button", class: "btn btn-text btn-danger", onclick: () => remove(ctx) }, "刪除生物")),
    tabBar(TABS, state.mobTab, (key) => { state.mobTab = key; render(ctx); }),
    h("div", { class: "panel-body", role: "tabpanel" }, h("div", { class: "panel-inner" }, tab(ctx, mob))));
}

function basicTab(ctx, mob) {
  const done = ctx.edited;
  const shortDone = () => { ctx.ui.thingTitle.textContent = textOf(mob.short); done(); };
  return h("div", { class: "stack" },
    h("div", { class: "row row-top" },
      vnumField({ ctx, kind: "mobiles", item: mob, id: "mob-vnum", label: "生物號碼" }),
      textField({ id: "mob-keywords", label: "名字", code: "keywords", obj: mob, key: "keywords", done })),
    textField({ id: "mob-short", label: "短名稱", code: "short", obj: mob, key: "short", done: shortDone }),
    textField({ id: "mob-long", label: "在房間裡看到的樣子", code: "long", obj: mob, key: "long", done }),
    areaField({ id: "mob-desc", label: "描述", code: "description", obj: mob, key: "description", done }),
    h("div", { class: "row" },
      numberField({ id: "mob-level", label: "等級", code: "level", obj: mob, key: "level", done }),
      numberField({ id: "mob-align", label: "陣營", code: "alignment", obj: mob, key: "alignment", tip: "-1000（邪惡）～1000（善良）", done }),
      numberField({ id: "mob-exp", label: "經驗倍數", code: "exp", obj: mob, key: "exp", decimal: true,
        tip: "1 正常、0 不給、1.5 多給 50%", done })),
    h("div", { class: "row" },
      raceField(mob, done),
      selectField({ id: "mob-sex", label: "性別", code: "sex", obj: mob, key: "sex", options: T.SEXES, style: "flex: 0 0 120px", done }),
      selectField({ id: "mob-position", label: "姿勢", code: "position", obj: mob, key: "position", options: T.POSITIONS,
        style: "flex: 0 0 140px", done })),
    h("div", { class: "stack sep" },
      flagsField({ legend: "行為旗標", code: "act", obj: mob, key: "act", table: T.ACT, done }),
      flagsField({ legend: "身上的效果", code: "affected_by", obj: mob, key: "affected_by", table: T.AFFECTED, done }),
      specialField(mob, done)),
    shopSection(ctx, mob),
    dropSection(ctx, mob),
    scriptRow(mob.script));
}

// 種族：檔案裡寫名稱，C 版比對時不分大小寫，所以 "Human" 也算 human；沒改就照原本的寫法存回去
function raceField(mob, done) {
  const current = typeof mob.race === "string" ? mob.race.toLowerCase() : null;
  const known = T.RACES.some(([name]) => name === current);
  const select = h("select", { id: "mob-race", class: "field-input", onchange: (e) => { mob.race = e.target.value; done(); } },
    known ? null : h("option", { value: "", disabled: true }, `${numberText(mob.race) || "沒有寫"}（不對的值）`),
    T.RACES.map(([name, zh]) => h("option", { value: name }, `${name} ${zh}`)));
  select.value = known ? current : "";
  return field({ id: "mob-race", label: "種族", code: "race", input: select, extra: selectArrow() });
}

// 寫在程式裡的行為：分「平常就會動作」「戰鬥中才動作」兩組；選「沒有」存成 null
function specialField(mob, done) {
  const value = mob.special === undefined ? null : mob.special;
  const known = value === null || T.SPECIALS.some(([name]) => name === value);
  const groups = [["平常就會動作", "平常"], ["戰鬥中才動作", "戰鬥"]].map(([label, kind]) =>
    h("optgroup", { label }, T.SPECIALS.filter((s) => s[2] === kind).map(([name, zh]) => h("option", { value: name }, `${name} ${zh}`))));
  const select = h("select", { id: "mob-special", class: "field-input", onchange: (e) => { mob.special = e.target.value || null; done(); } },
    known ? null : h("option", { value: "?", disabled: true }, `${numberText(value)}（不對的值）`),
    h("option", { value: "" }, "沒有"), groups);
  select.value = value === null ? "" : known ? value : "?";
  return field({ id: "mob-special", label: "寫在程式裡的行為", code: "special", input: select, extra: selectArrow() });
}

// 商店：勾「牠是店主」才有內容，取消勾選存成 null
function shopSection(ctx, mob) {
  const shop = mob.shop;
  const toggle = checkbox({ label: "牠是店主", code: "shop", checked: !!shop,
    onchange: (e) => { mob.shop = e.target.checked ? M.newShop() : null; ctx.rebuild(); } });
  if (!shop) return h("div", { class: "stack sep" }, toggle);
  const done = ctx.edited;
  const types = Array.isArray(shop.buy_types) ? shop.buy_types : [];
  return h("div", { class: "stack sep" }, toggle,
    h("div", { class: "row" },
      numberField({ id: "shop-buy", label: "玩家買的價格 %", code: "profit_buy", obj: shop, key: "profit_buy", done }),
      numberField({ id: "shop-sell", label: "玩家賣的價格 %", code: "profit_sell", obj: shop, key: "profit_sell", done })),
    h("div", { class: "row" },
      numberField({ id: "shop-open", label: "開店", code: "open_hour", obj: shop, key: "open_hour", done }),
      numberField({ id: "shop-close", label: "關店", code: "close_hour", obj: shop, key: "close_hour", done })),
    h("fieldset", null,
      h("legend", null, "會收購的物品", h("span", { class: "code" }, "buy_types")),
      h("div", { class: "flags flags-3" }, T.ITEM_TYPES.map(([n, label]) => checkbox({
        label, code: n, checked: types.includes(n),
        onchange: (e) => {
          const now = Array.isArray(shop.buy_types) ? shop.buy_types.filter((t) => t !== n) : [];
          shop.buy_types = e.target.checked ? [...now, n] : now;
          done();
        },
      })))));
}

const percent = (chance) => (M.isInt(chance) ? `${chance / 100}%` : "");

// 掉寶：勾「死掉時可能掉東西」才有內容，取消勾選存成 null
function dropSection(ctx, mob) {
  const drop = mob.random_drop;
  const toggle = checkbox({ label: "死掉時可能掉東西", code: "random_drop", checked: !!drop,
    onchange: (e) => { mob.random_drop = e.target.checked ? M.newDrop() : null; ctx.rebuild(); } });
  if (!drop) return h("div", { class: "stack sep" }, toggle);
  const shown = h("span", { class: "muted" }, percent(drop.chance));
  return h("div", { class: "stack sep" }, toggle,
    h("div", { class: "row" },
      numberField({ id: "drop-chance", label: "機率", code: "chance", obj: drop, key: "chance", style: "flex: 0 0 140px",
        tip: "以萬分之一為單位：5000 是 50%", done: () => { shown.textContent = percent(drop.chance); ctx.edited(); } }),
      shown),
    refField({ id: "drop-obj", label: "物品", code: "obj_vnum", obj: drop, key: "obj_vnum",
      chipOf: (n) => ctx.chipOf("objects", n), done: ctx.edited }));
}

// 清單分頁的開頭：檔案裡的欄位名，右邊是新增
function listHead(code, onAdd) {
  return h("div", { class: "list-head" }, h("span", { class: "code" }, code),
    h("button", { type: "button", class: "btn", onclick: onAdd }, icon("plus", 18), "新增"));
}

// 新增一筆到 mob[key]（檔案原本沒有這個清單就補上），重畫後游標放到 focusId(新的第幾筆)
function addTo(ctx, mob, key, item, focusId) {
  if (!Array.isArray(mob[key])) mob[key] = [];
  mob[key].push(item);
  ctx.rebuild();
  document.getElementById(focusId(mob[key].length - 1)).focus();
}

function actionsTab(ctx, mob) {
  const done = ctx.edited;
  const list = Array.isArray(mob.actions) ? mob.actions : [];
  return h("div", { class: "stack", style: "gap: 16px" },
    listHead("actions", () => addTo(ctx, mob, "actions", M.newAction(), (i) => `act-${i}-text`)),
    list.map((a, i) => h("div", { class: "card card-form" },
      h("div", { class: "row" },
        selectField({ id: `act-${i}-when`, label: "什麼時候", code: "when", obj: a, key: "when", options: T.ACTION_WHEN, done }),
        selectField({ id: `act-${i}-mode`, label: "怎麼做", code: "mode", obj: a, key: "mode", options: T.ACTION_MODE, done }),
        removeButton(() => { list.splice(i, 1); ctx.rebuild(); })),
      textField({ id: `act-${i}-text`, label: "指令或文字", code: "text", obj: a, key: "text", done }))));
}

function fightTab(ctx, mob) {
  const done = ctx.edited;
  const list = Array.isArray(mob.fight_actions) ? mob.fight_actions : [];
  return h("div", { class: "stack", style: "gap: 16px" },
    listHead("fight_actions", () => addTo(ctx, mob, "fight_actions", M.newFightAction(), (i) => `fa-${i}-command`)),
    list.map((a, i) => h("div", { class: "card card-form" },
      h("div", { class: "row" },
        numberField({ id: `fa-${i}-rate`, label: "機率 %", code: "rate", obj: a, key: "rate", style: "flex: 0 0 120px",
          tip: "寫負數時，對象改成自己或主人", done }),
        textField({ id: `fa-${i}-command`, label: "指令", code: "command", obj: a, key: "command", tip: "%s 會換成對象", done }),
        removeButton(() => { list.splice(i, 1); ctx.rebuild(); })),
      textField({ id: `fa-${i}-message`, label: "顯示的文字", code: "message", obj: a, key: "message", tip: "%s 會換成對象的名字", done }))));
}
