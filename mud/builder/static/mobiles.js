// 生物畫面：左欄是生物清單，右邊表單佔滿（沒有地圖）。
// 分頁照使用者的規則：只有一份的欄位全部放「基本資料」，可以一直新增的清單（兩種動作）各自一個分頁。
import {
  addButton, areaField, codeField, colorField, flagsField, numberField, refField, removeButton, scriptRow, selectField, tabBar, textField,
  textOf, vnumField,
} from "./forms.js";
import * as M from "./model.js";
import { placesOf } from "./resets.js";
import * as T from "./tables.js";
import {
  checkbox, confirmDialog, field, h, icon, numberText, parseNumber, selectArrow, textInput, toast,
} from "./ui.js";

const TABS = [["basic", "基本資料"], ["actions", "平常的動作"], ["fight", "戰鬥中的動作"], ["drops", "掉落表"]];

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
  const tab = { basic: basicTab, actions: actionsTab, fight: fightTab, drops: dropsTab }[state.mobTab] || basicTab;
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
      numberField({ id: "mob-align", label: "陣營", code: "alignment", obj: mob, key: "alignment", tip: "-1000（邪惡）～1000（善良）", done })),
    h("div", { class: "row" },
      codeField({ id: "mob-tier", label: "種類", code: "tier", obj: mob, key: "tier", options: T.MOB_TIERS,
        style: "flex: 0 0 140px", done: () => { dropBaseFromRoll(mob); ctx.rebuild(); } }),
      codeField({ id: "mob-attack", label: "攻擊類型", code: "attack", obj: mob, key: "attack", options: attackOptions(), done }),
      codeField({ id: "mob-defense", label: "攻防傾向", code: "defense", obj: mob, key: "defense",
        options: [[null, "標準"], ...T.DEFENSES], style: "flex: 0 0 140px", done }),
      codeField({ id: "mob-archetype", label: "原型", code: "archetype", obj: mob, key: "archetype",
        options: [[null, "標準"], ...T.ARCHETYPES], style: "flex: 0 0 160px", done })),
    tierRollField(ctx, mob),
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
    scriptRow(mob.script));
}

// 攻擊類型的選項：null 純物理、只用一種、「主/次」兩種不一樣的（主 70%、次 30%）
function attackOptions() {
  const pairs = T.ATTACK_TYPES.flatMap(([main, mainName]) => T.ATTACK_TYPES.filter(([sub]) => sub !== main)
    .map(([sub, subName]) => [`${main}/${sub}`, `主${mainName}、次${subName}`]));
  return [[null, "純物理"], ...T.ATTACK_TYPES, ...pairs];
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
const CHANCE_TIP = "萬分之一：100 是 1%、10000 是 100%";

// 重生時骰種類：基本種類以外的每一種一格（萬分之一）；全部空著存成 null，就是固定是基本種類
function tierRollField(ctx, mob) {
  const roll = () => (M.isObject(mob.tier_roll) ? mob.tier_roll : {});
  const base = T.MOB_TIERS.find(([t]) => t === mob.tier);
  const rest = h("span", { class: "muted" });
  const showRest = () => {
    const sum = Object.values(roll()).filter(M.isInt).reduce((a, b) => a + b, 0);
    rest.textContent = base ? `${base[1]} ${(10000 - sum) / 100}%` : "";
  };
  showRest();
  const inputs = T.MOB_TIERS.filter(([t]) => t !== mob.tier).map(([t, name]) => field({
    id: `mob-roll-${t}`, label: `變成${name}`, code: t, style: "flex: 0 0 130px", tip: CHANCE_TIP,
    input: textInput({ id: `mob-roll-${t}`, value: numberText(roll()[t]), oninput: (e) => {
      const next = { ...roll() };
      const v = parseNumber(e.target.value);
      if (v === null) delete next[t]; else next[t] = v;
      mob.tier_roll = Object.keys(next).length ? next : null;
      showRest();
      ctx.edited();
    } }),
  }));
  return h("fieldset", null,
    h("legend", null, "重生時變成其他種類", h("span", { class: "code" }, "tier_roll")),
    h("div", { class: "row" }, inputs, rest));
}

// 換了基本種類：tier_roll 裡不用再寫它（剩下的機率就是它）
function dropBaseFromRoll(mob) {
  if (!M.isObject(mob.tier_roll) || !(mob.tier in mob.tier_roll)) return;
  const next = { ...mob.tier_roll };
  delete next[mob.tier];
  mob.tier_roll = Object.keys(next).length ? next : null;
}

// 掉落表：一行一件，每一行各自骰
function dropsTab(ctx, mob) {
  const done = ctx.edited;
  const list = Array.isArray(mob.drops) ? mob.drops : [];
  return h("div", { class: "stack", style: "gap: 16px" },
    listHead("drops", () => addTo(ctx, mob, "drops", M.newDrop(), (i) => `drop-${i}-obj`)),
    list.map((d, i) => {
      const shown = h("span", { class: "muted" }, percent(d.chance));
      return h("div", { class: "card card-form" },
        h("div", { class: "row" },
          refField({ id: `drop-${i}-obj`, label: "物品", code: "obj_vnum", obj: d, key: "obj_vnum",
            chipOf: (n) => ctx.chipOf("objects", n), done }),
          removeButton(() => { list.splice(i, 1); ctx.rebuild(); })),
        h("div", { class: "row" },
          colorField({ id: `drop-${i}-color`, obj: d, done }),
          numberField({ id: `drop-${i}-chance`, label: "機率", code: "chance", obj: d, key: "chance", style: "flex: 0 0 140px",
            tip: CHANCE_TIP, done: () => { shown.textContent = percent(d.chance); done(); } }),
          shown),
        tiersField(d, i, done));
    }));
}

// 限定種類：都沒勾存成 null，就是所有種類都會掉
function tiersField(d, i, done) {
  const now = () => (Array.isArray(d.tiers) ? d.tiers : []);
  const note = h("span", { class: "muted" });
  const showNote = () => { note.textContent = d.tiers === null ? "null 所有種類都會掉" : ""; };
  showNote();
  return h("fieldset", null,
    h("legend", null, "只有這些種類會掉", h("span", { class: "code" }, "tiers")),
    h("div", { class: "checks" },
      T.MOB_TIERS.map(([t, name]) => checkbox({
        label: name, code: t, checked: now().includes(t),
        onchange: (e) => {
          const next = now().filter((x) => x !== t);
          if (e.target.checked) next.push(t);
          d.tiers = next.length ? T.MOB_TIERS.map(([x]) => x).filter((x) => next.includes(x)) : null;
          showNote();
          done();
        },
      })),
      note));
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
