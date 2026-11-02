// 選檔畫面：列出 builder_area/ 的區域檔，點一列就打開；也可以新增區域檔。
import * as api from "./api.js";
import { brand, field, h, icon, openDialog, parseNumber, textInput } from "./ui.js";

export async function showFiles() {
  document.title = "區域編輯器";
  const list = h("div", { class: "files-list" });
  document.getElementById("app").replaceChildren(
    h("div", { class: "screen" },
      h("header", { class: "topbar" }, brand()),
      h("main", { class: "files" },
        h("section", { class: "files-card", "aria-labelledby": "files-title" },
          h("div", { class: "files-head" },
            h("h1", { class: "files-title", id: "files-title" }, "區域檔"),
            h("button", { type: "button", class: "btn btn-filled", onclick: newFileDialog }, "新增區域檔")),
          list))));

  let items;
  try {
    items = await api.listAreas();
  } catch (e) {
    list.append(h("div", { class: "file-row file-bad" }, e.message));
    return;
  }
  list.append(h("div", { class: "file-row file-row-head", "aria-hidden": "true" },
    h("span", null, "區域名稱"), h("span", null, "檔名"), h("span", null, "區域號碼"), h("span", null, "房間")));
  for (const item of items) {
    if (item.error) {
      list.append(h("div", { class: "file-row" },
        h("span", { class: "file-title file-bad" }, item.error), h("span", { class: "file-name" }, item.file), h("span"), h("span")));
    } else {
      list.append(h("a", { class: "file-row", href: "#" + encodeURIComponent(item.file) },
        h("span", { class: "file-title" }, String(item.title ?? "")),
        h("span", { class: "file-name" }, item.file),
        h("span", null, String(item.area_number ?? "")),
        h("span", null, String(item.rooms))));
    }
  }
  if (!items.length) {
    list.append(h("button", { type: "button", class: "file-new", onclick: newFileDialog }, icon("plus"), "新增區域檔"));
  }
}

function newFileDialog() {
  const fileInput = textInput({ id: "new-file" });
  const titleInput = textInput({ id: "new-title" });
  const numberInput = textInput({ id: "new-number" });
  const fileField = h("div", { style: "flex: 1 1 0; min-width: 0" });
  const showFileField = (error) => fileField.replaceChildren(
    field({ id: "new-file", label: "檔名", code: "file", input: fileInput, error }));
  showFileField(null);

  const create = async () => {
    let name = fileInput.value.trim();
    if (name && !name.endsWith(".json")) name += ".json";
    try {
      await api.createArea(name, titleInput.value, parseNumber(numberInput.value));
    } catch (e) {
      showFileField(e.message);
      fileInput.focus();
      return;
    }
    close();
    location.hash = "#" + encodeURIComponent(name);
  };
  const close = openDialog({
    title: "新增區域檔",
    labelId: "new-file-title",
    onCancel: () => close(),
    body: [
      fileField,
      h("div", { class: "row" },
        field({ id: "new-title", label: "區域名稱", code: "title", input: titleInput }),
        field({ id: "new-number", label: "區域號碼", code: "area_number", input: numberInput, style: "flex: 0 0 160px" })),
    ],
    footer: [
      h("button", { type: "button", class: "btn btn-text", onclick: () => close() }, "取消"),
      h("button", { type: "button", class: "btn btn-filled", onclick: create }, "建立"),
    ],
  });
  for (const input of [fileInput, titleInput, numberInput]) {
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") create(); });
  }
}
