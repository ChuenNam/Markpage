// 统一确认弹窗：替代 window.confirm —— 样式与界面一致，支持 Esc 取消，返回 Promise<boolean>。
// 单独成模块是为了让 picker.js 和 app.js 都能用，避免两者互相 import 造成循环依赖。

let dlg = null;
let titleEl = null;
let msgEl = null;
let okBtn = null;
let cancelBtn = null;
let resolver = null;

function settle(value) {
  const r = resolver;
  resolver = null;
  if (dlg && dlg.open) dlg.close();
  if (r) r(value);
}

function ensure() {
  if (dlg) return;
  dlg = document.getElementById("dlgConfirm");
  titleEl = document.getElementById("confirmTitle");
  msgEl = document.getElementById("confirmMsg");
  okBtn = document.getElementById("confirmOk");
  cancelBtn = document.getElementById("confirmCancel");
  okBtn.onclick = () => settle(true);
  cancelBtn.onclick = () => settle(false);
  // Esc 关闭时 dialog 会触发 cancel 事件，必须接住，否则 Promise 永远不 resolve
  dlg.addEventListener("cancel", (e) => {
    e.preventDefault();
    settle(false);
  });
}

export function confirmDialog(message, { title = "请确认", ok = "确定" } = {}) {
  ensure();
  titleEl.textContent = title;
  msgEl.textContent = message;
  okBtn.textContent = ok;
  dlg.showModal();
  return new Promise((res) => {
    resolver = res;
  });
}
