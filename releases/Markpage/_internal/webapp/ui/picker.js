// 目录浏览器（替代系统文件对话框）：浏览器拿不到磁盘绝对路径，所以路径一律由
// 服务端 /api/browse 提供。好处是能显示 .md 的大小与时间，还能记住上次目录。
import { confirmDialog } from "./confirm.js";

function crumbsFor(p) {
  const isWin = /^[A-Za-z]:/.test(p);
  const parts = p.split(/[\\/]/).filter(Boolean);
  const out = [];
  let acc = isWin ? "" : "/";
  for (const part of parts) {
    if (isWin && /^[A-Za-z]:$/.test(part)) acc = part + "\\";
    else acc = acc + part + (isWin ? "\\" : "/");
    out.push({ name: part, path: acc });
  }
  return out;
}

function fmtSize(n) {
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
  return (n / 1024 / 1024).toFixed(1) + " MB";
}

export class Picker {
  constructor(dlg, get, post, notify) {
    this.dlg = dlg;
    this.get = get;
    this.post = post;
    this.notify = notify || (() => {});
    this.mode = "file";
    this.cur = "";
    this.selected = "";
    this._resolve = null;

    this.list = dlg.querySelector("#pickerList");
    this.crumbs = dlg.querySelector("#pickerCrumbs");
    this.drives = dlg.querySelector("#pickerDrives");
    this.quick = dlg.querySelector("#pickerQuick");
    this.pathInput = dlg.querySelector("#pickerPath");
    this.btnOk = dlg.querySelector("#pickerOk");

    dlg.querySelector("#pickerClose").onclick = () => this._close(null);
    this.btnOk.onclick = () => this._confirm();
    this.pathInput.addEventListener("keydown", (e) => {
      // 中文路径用输入法打字时，Enter 是选词上屏，不能直接当作「确定」
      if (e.isComposing || e.keyCode === 229) return;
      if (e.key !== "Enter") return;
      e.preventDefault();
      const v = this.pathInput.value.trim();
      if (!v) return;
      if (this.mode === "file" && /\.(md|markdown)$/i.test(v)) {
        this.selected = v;
        this._confirm();
      } else {
        this.load(v);
      }
    });
    dlg.addEventListener("cancel", (e) => {
      e.preventDefault();
      this._close(null);
    });
  }

  open(mode = "file", start = "") {
    this.mode = mode;
    this.selected = "";
    this.dlg.querySelector("#pickerTitle").textContent =
      mode === "dir" ? "选择输出目录" : "选择 Markdown 文件";
    this.btnOk.textContent = mode === "dir" ? "用此目录" : "打开";
    this.dlg.showModal();
    return new Promise((res) => {
      this._resolve = res;
      this.load(start);
    });
  }

  _close(val) {
    const r = this._resolve;
    this._resolve = null;
    if (this.dlg.open) this.dlg.close();
    if (r) r(val);
  }

  _confirm() {
    if (this.mode === "dir") this._close(this.cur || null);
    else if (this.selected) this._close(this.selected);
    else this.pathInput.focus();
  }

  async load(path) {
    const d = await this.get("browse", { path: path || "", mode: this.mode });
    if (!d || !d.ok) {
      this.list.innerHTML = `<p class="ph">${d && d.error ? d.error : "无法读取该目录"}</p>`;
      return;
    }
    this.cur = d.path;
    this.selected = "";
    this.pathInput.value = d.path;
    this._renderQuick(d.quick || []);
    this._renderDrives(d.drives || []);
    this._renderCrumbs(d.path);
    this._renderList(d);
  }

  /** 快捷入口：药丸形，右侧 × 悬浮才出现；末尾一个「+」把当前目录加进来 */
  _renderQuick(items) {
    this.quick.innerHTML = "";
    for (const q of items) {
      const wrap = document.createElement("span");
      wrap.className = "qitem";

      const go = document.createElement("button");
      go.className = "qgo";
      go.textContent = q.name;
      go.title = q.path;
      go.onclick = () => this.load(q.path);

      const del = document.createElement("button");
      del.className = "qdel";
      del.textContent = "×";
      del.title = "删除这个快捷入口";
      del.onclick = async (e) => {
        e.stopPropagation();
        const ok = await confirmDialog(
          `删除快捷入口「${q.name}」？\n\n只删这个入口，磁盘上的 ${q.path} 不会有任何改动。`,
          { title: "删除快捷入口", ok: "删除" });
        if (!ok) return;
        const r = await this.post("shortcuts/remove", { path: q.path });
        if (r && r.ok) this._renderQuick(r.quick || []);
      };

      // × 包一层 .qx：默认 max-width:0 被裁掉，悬停时向右展开露出
      const qx = document.createElement("span");
      qx.className = "qx";
      qx.appendChild(del);
      wrap.append(go, qx);
      this.quick.appendChild(wrap);
    }

    const add = document.createElement("button");
    add.className = "qadd";
    add.textContent = "+";
    add.disabled = !this.cur;
    add.title = this.cur ? "把当前目录加为快捷入口：" + this.cur : "先进入一个目录";
    add.onclick = async () => {
      if (!this.cur) return;
      const r = await this.post("shortcuts/add", { path: this.cur, name: "" });
      if (!r || !r.ok) return;
      this._renderQuick(r.quick || []);
      this.notify(r.message || "已添加快捷入口");
    };
    this.quick.appendChild(add);
  }

  _renderDrives(drives) {
    this.drives.innerHTML = "";
    if (drives.length < 2) return;   // 只有一个盘就不占地方
    for (const dr of drives) {
      const b = document.createElement("button");
      b.textContent = dr.replace(/\\$/, "");
      b.onclick = () => this.load(dr);
      this.drives.appendChild(b);
    }
  }

  _renderCrumbs(p) {
    this.crumbs.innerHTML = "";
    const segs = crumbsFor(p);
    segs.forEach((s, i) => {
      const b = document.createElement("button");
      b.textContent = s.name;
      b.title = s.path;
      b.onclick = () => this.load(s.path);
      this.crumbs.appendChild(b);
      if (i < segs.length - 1) {
        const sep = document.createElement("span");
        sep.textContent = "›";
        this.crumbs.appendChild(sep);
      }
    });
  }

  _renderList(d) {
    this.list.innerHTML = "";
    if (d.parent) {
      const up = document.createElement("button");
      up.innerHTML = '<span class="ico">↑</span><span class="nm">上一级</span>';
      up.onclick = () => this.load(d.parent);
      this.list.appendChild(up);
    }
    if (!d.entries.length) {
      const p = document.createElement("p");
      p.className = "ph";
      p.textContent = this.mode === "dir" ? "（没有子目录）" : "（这里没有 .md 文件）";
      this.list.appendChild(p);
      return;
    }
    for (const e of d.entries) {
      const b = document.createElement("button");
      const ico = document.createElement("span");
      ico.className = "ico";
      ico.textContent = e.dir ? "▸" : "·";
      const nm = document.createElement("span");
      nm.className = "nm";
      nm.textContent = e.name;
      b.append(ico, nm);
      if (!e.dir) {
        const sz = document.createElement("span");
        sz.className = "sz";
        sz.textContent = fmtSize(e.size);
        b.appendChild(sz);
      }
      b.onclick = () => {
        if (e.dir) {
          this.load(e.path);
        } else {
          this.selected = e.path;
          for (const x of this.list.querySelectorAll("button.on")) x.classList.remove("on");
          b.classList.add("on");
        }
      };
      b.ondblclick = () => {
        if (!e.dir) { this.selected = e.path; this._confirm(); }
        else this.load(e.path);
      };
      this.list.appendChild(b);
    }
  }
}
