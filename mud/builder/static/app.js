// 換畫面：網址沒有 # 是選檔畫面，#test.json 是編輯那個檔（重新整理也不會跳回選檔畫面）。
import { closeEditor, currentFile, isDirty, openEditor } from "./editor.js";
import { showFiles } from "./files.js";
import { confirmDialog } from "./ui.js";

async function route() {
  const name = decodeURIComponent(location.hash.slice(1));
  if (name && name === currentFile()) return;
  if (isDirty()) {
    const leave = await confirmDialog({ title: "還沒儲存", text: "離開的話，這次改的會不見。", ok: "離開", danger: true });
    if (!leave) {
      location.hash = "#" + encodeURIComponent(currentFile());   // 換回來，route() 看到同一個檔就不動
      return;
    }
  }
  closeEditor();
  if (name) openEditor(name);
  else showFiles();
}

window.addEventListener("hashchange", route);
window.addEventListener("beforeunload", (e) => {
  if (isDirty()) e.preventDefault();          // 重新整理、關分頁時，瀏覽器會自己問一次
});
route();
