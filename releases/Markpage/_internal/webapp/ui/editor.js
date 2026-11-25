// Markpage 编辑器：行号 + Tab 缩进 + 列表自动续行 + Ctrl+S
// 刻意保持「轻量」：原生 textarea，零外部依赖，行高与行号槽严格对齐。

export class Editor {
  constructor(textarea, gutter, handlers = {}) {
    this.ta = textarea;
    this.gutter = gutter;
    this.onChange = handlers.onChange || (() => {});
    this.onSave = handlers.onSave || (() => {});
    this.onScroll = handlers.onScroll || (() => {});
    this.lineHeight = 20;

    this.ta.addEventListener("input", () => {
      this.refreshGutter();
      this.onChange();
    });
    this.ta.addEventListener("scroll", () => {
      this.gutter.scrollTop = this.ta.scrollTop;
      this.onScroll();
    });
    this.ta.addEventListener("keydown", (e) => this._onKey(e));
    this.refreshGutter();
  }

  get value() { return this.ta.value; }

  setValue(text, { keepScroll = false } = {}) {
    const y = this.ta.scrollTop;
    this.ta.value = text;
    this._lines = -1;
    this.refreshGutter();
    this.ta.scrollTop = keepScroll ? y : 0;
    this.gutter.scrollTop = this.ta.scrollTop;
    this.onScroll();
  }

  refreshGutter() {
    const n = (this.ta.value.match(/\n/g) || []).length + 1;
    if (n === this._lines) return;
    this._lines = n;
    const rows = new Array(n);
    for (let i = 1; i <= n; i++) rows[i - 1] = i;
    this.gutter.textContent = rows.join("\n");
    this.gutter.scrollTop = this.ta.scrollTop;
  }

  gotoLine(line) {
    const lines = this.ta.value.split("\n");
    let pos = 0;
    for (let i = 0; i < line - 1 && i < lines.length; i++) pos += lines[i].length + 1;
    this.ta.focus();
    this.ta.setSelectionRange(pos, pos);
    this.ta.scrollTop = Math.max(0, (line - 1) * this.lineHeight - this.ta.clientHeight / 2.4);
    this.gutter.scrollTop = this.ta.scrollTop;
    this.onScroll();
  }

  /** 整行替换（用于点选角色写回行尾标记）。
   *  走 setRangeText，保留撤销栈与光标；不整篇重设，避免光标跳走。 */
  replaceLine(line, text) {
    const lines = this.ta.value.split("\n");
    if (line < 1 || line > lines.length) return false;
    let start = 0;
    for (let i = 0; i < line - 1; i++) start += lines[i].length + 1;
    const end = start + lines[line - 1].length;
    if (this.ta.value.slice(start, end) === text) return false;
    this.ta.setRangeText(text, start, end, "preserve");
    this.refreshGutter();
    this.onChange();
    return true;
  }

  _onKey(e) {
    // 输入法组合期间（拼音选词/联想）一律不接管按键：
    // 此时 Enter 是「上屏选中的候选」而不是换行，接管了就会在列表里凭空插一条 `- `；
    // Tab / 方向键也可能被输入法自己用。keyCode 229 是部分输入法在组合态的兼容信号
    // （个别环境下 isComposing 为 false 但 keyCode 仍是 229）。
    if (e.isComposing || e.keyCode === 229) return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      this.onSave();
      return;
    }
    if (e.key === "Tab") {
      e.preventDefault();
      this._indent(e.shiftKey);
      return;
    }
    if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
      this._continueList(e);
    }
  }

  _indent(outdent) {
    const ta = this.ta;
    const s = ta.selectionStart;
    const en = ta.selectionEnd;
    const lineStart = ta.value.lastIndexOf("\n", s - 1) + 1;
    const multi = ta.value.slice(s, en).includes("\n");
    if (!multi && !outdent) {
      ta.setRangeText("  ", s, en, "end");
    } else {
      const seg = ta.value.slice(lineStart, en)
        .split("\n")
        .map((l) => outdent ? l.replace(/^ {1,2}/, "") : "  " + l)
        .join("\n");
      ta.setRangeText(seg, lineStart, en, "end");
    }
    this.refreshGutter();
    this.onChange();
  }

  _continueList(e) {
    const ta = this.ta;
    const s = ta.selectionStart;
    if (s !== ta.selectionEnd) return;
    const lineStart = ta.value.lastIndexOf("\n", s - 1) + 1;
    const line = ta.value.slice(lineStart, s);
    const m = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/.exec(line);
    if (!m) return;
    e.preventDefault();
    if (m[3].trim() === "") {
      ta.setRangeText("", lineStart, s, "end");
    } else {
      let marker = m[2];
      if (/^\d/.test(marker)) marker = String(parseInt(marker, 10) + 1) + marker.slice(-1);
      ta.setRangeText("\n" + m[1] + marker + " ", s, s, "end");
    }
    this.refreshGutter();
    this.onChange();
  }
}
