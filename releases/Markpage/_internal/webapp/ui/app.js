// Markpage 界面控制器：状态、接口调用、实时预览、构建流。
import { Editor } from "./editor.js";
import { parseOutline, buildTree, renderOutlineInto } from "./outline.js";
import { Picker } from "./picker.js";
import { confirmDialog } from "./confirm.js";

const TOKEN = (location.pathname.split("/").filter(Boolean)[1]) || "";
const BASE = `/s/${TOKEN}`;
const $ = (id) => document.getElementById(id);

const S = {
  path: "",
  mtime: 0,
  title: "",
  outBase: "",      // 输出位置（父目录）
  subdir: true,     // 是否生成到子目录
  subdirName: "site",
  opts: { overview_links: false, group_pages: false, alias: {}, route_text: "", alias_text: "" },
  pages: [],
  stats: null,
  stamp: 0,
  page: "index.html",
  source: "preview",     // preview = 编辑缓冲区；out = 已生成的真实产物
  dirty: false,
  building: false,
  previewing: false,
  theme: "light",
  width: "desktop",
  lastDir: "",
  recent: [],
  projects: {},
  collapsed: new Set(),
  aliasDismissed: new Set(),
  engineOk: true,
};

// ---------- 接口 ----------
async function req(name, { method = "GET", body = null, query = null } = {}) {
  let url = `${BASE}/api/${name}`;
  if (query) {
    const qs = new URLSearchParams(query).toString();
    if (qs) url += "?" + qs;
  }
  const opt = { method, cache: "no-store" };
  if (method !== "GET") {
    opt.headers = { "Content-Type": "application/json" };
    opt.body = JSON.stringify(body || {});
  }
  const r = await fetch(url, opt);
  const txt = await r.text();
  let data;
  try {
    data = txt ? JSON.parse(txt) : {};
  } catch {
    throw new Error(`接口 ${name} 返回了非 JSON 内容（HTTP ${r.status}）`);
  }
  data.__status = r.status;
  return data;
}
const get = (name, query) => req(name, { method: "GET", query });
const post = (name, body) => req(name, { method: "POST", body });

// ---------- 小工具 ----------
let toastTimer = 0;
function toast(msg, ms = 2800) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.add("on");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("on"), ms);
}

const logEl = $("log");
function log(msg, cls = "l") {
  const d = document.createElement("div");
  d.className = cls;
  d.textContent = msg;
  logEl.appendChild(d);
  while (logEl.childElementCount > 2000) logEl.removeChild(logEl.firstChild);
  logEl.scrollTop = logEl.scrollHeight;
}
function clearLog() {
  logEl.innerHTML = "";
}

function shortPath(p) {
  const parts = p.split(/[\\/]/);
  return parts.length > 3 ? "…/" + parts.slice(-2).join("/") : p;
}

function setDirty(on) {
  S.dirty = on;
  $("dirty").hidden = !on;
}

function setBusy(on) {
  S.building = on;
  const b = $("btnBuild");
  b.disabled = on || !S.engineOk;
  b.textContent = on ? "生成中…" : "生成站点";
  $("btnCancel").hidden = !on;
}

// ---------- 编辑器 ----------
const editor = new Editor($("editor"), $("gutter"), {
  onChange: () => {
    setDirty(true);
    if (S.source === "out") S.source = "preview";
    schedulePreview();
  },
  onSave: () => saveNow(),
  onScroll: () => syncHlScroll(),
});

// ---------- 预览 ----------
let previewTimer = 0;
let previewQueued = false;

function schedulePreview(delay = 450) {
  if (!S.path) return;
  clearTimeout(previewTimer);
  previewTimer = setTimeout(doPreview, delay);
}

async function doPreview() {
  if (!S.path) return;
  if (S.previewing) {
    previewQueued = true;
    return;
  }
  S.previewing = true;
  try {
    const r = await post("preview", {
      path: S.path,
      text: editor.value,
      title: S.title,
      out: effectiveOut(),
      opts: S.opts,
    });
    if (!r.ok) {
      $("previewMeta").textContent = "预览失败";
      log("预览失败：" + (r.error || "未知原因"), "warn");
      hideFrame(true);
      drawHighlights([]);
      return;
    }
    S.stamp = r.stamp;
    S.pages = r.pages || [];
    if (!S.pages.some((p) => p.file === S.page)) S.page = "index.html";
    if (S.source === "out") S.source = "preview";
    loadFrame();
    renderPages();
    drawHighlights(pageSpans(S.page));
    renderOutline();
    renderRoles();
    $("previewMeta").textContent = `${Math.round(r.ms)} ms`;
    scheduleLint(1200);
  } catch (e) {
    log("预览异常：" + e.message, "err");
    hideFrame(true);
  } finally {
    S.previewing = false;
    if (previewQueued) {
      previewQueued = false;
      schedulePreview(120);
    }
  }
}

function hideFrame(empty) {
  $("frame").hidden = empty;
  $("frameEmpty").hidden = !empty;
}

function frameBase() {
  return S.source === "out" ? `${BASE}/out/` : `${BASE}/preview/`;
}

let restoreY = null;

function loadFrame() {
  const f = $("frame");
  if (!S.path) return;
  try {
    restoreY = f.contentWindow ? f.contentWindow.scrollY || 0 : 0;
  } catch {
    restoreY = 0;   // 跨文档访问失败就不恢复滚动
  }
  f.hidden = false;
  $("frameEmpty").hidden = true;
  f.src = `${frameBase()}${S.page}?v=${S.stamp}`;
}

/** 预览 iframe 里点链接会自己跳页 —— 把界面同步到那一页。
 *  只认本站产物里的文件名；认不出来就当作没发生。 */
function frameFile() {
  try {
    const p = $("frame").contentWindow.location.pathname || "";
    return decodeURIComponent(p.split("/").pop() || "");
  } catch {
    return "";
  }
}

function syncFromFrame() {
  const file = frameFile();
  if (!file || file === S.page) return;
  if (!S.pages.some((x) => x.file === file)) return;
  S.page = file;
  const sel = $("pageSel");
  if (!sel.hidden) sel.value = file;
  renderPages();
  renderOutline();
  const spans = pageSpans(file);
  drawHighlights(spans);
  if (spans.length) scrollEditorToLine(spans[0][0], false);
}

function onFrameLoad() {
  const f = $("frame");
  try {
    if (restoreY !== null && f.contentWindow) f.contentWindow.scrollTo(0, restoreY);
    if (f.contentDocument) f.contentDocument.documentElement.dataset.theme = S.theme;
  } catch { /* ignore */ }
  restoreY = null;
  syncFromFrame();      // 可能是 iframe 内部跳转，同步左栏 / 产物 / 编辑器
}

function applyFrameTheme() {
  const f = $("frame");
  try {
    if (f.contentDocument) f.contentDocument.documentElement.dataset.theme = S.theme;
  } catch { /* ignore */ }
}

function setTheme(t) {
  S.theme = t;
  document.documentElement.dataset.theme = t;
  try {
    localStorage.setItem("markpage-theme", t);
    localStorage.setItem("doc-theme", t);   // 生成站点自己认这个键，连带一起设
  } catch { /* ignore */ }
  $("btnTheme").textContent = t === "dark" ? "浅色" : "深色";
  applyFrameTheme();
}

function setWidth(w) {
  S.width = w;
  $("stage").classList.toggle("mobile", w === "mobile");
  for (const b of document.querySelectorAll("[data-width]")) {
    b.classList.toggle("on", b.dataset.width === w);
  }
}

function navTo(file, { scroll = true } = {}) {
  if (!file) {
    toast("这一节在站点里没有独立页面");
    return;
  }
  const same = file === S.page && frameFile() === file;   // 已在看这一页就别再刷新
  S.page = file;
  const sel = $("pageSel");
  if (!sel.hidden) sel.value = file;
  if (!same) loadFrame();
  const spans = pageSpans(file);
  drawHighlights(spans);
  if (scroll && spans.length) scrollEditorToLine(spans[0][0], false);
  renderPages();
  renderOutline();
}

// ---------- 源行底纹（预览页 ↔ 源文档行） ----------
const LINE_H = 20;
const PAD_TOP = 12;

function pageSpans(file) {
  const p = S.pages.find((x) => x.file === file);
  return (p && p.ranges) || [];
}

function bandStyle(el, start, end) {
  el.style.top = (PAD_TOP + (start - 1) * LINE_H) + "px";
  el.style.height = Math.max(LINE_H, (end - start + 1) * LINE_H) + "px";
}

function drawHighlights(spans) {
  const inner = $("hlInner");
  inner.innerHTML = "";
  for (const [s, e] of spans || []) {
    const b = document.createElement("div");
    b.className = "hl-band";
    bandStyle(b, s, e);
    inner.appendChild(b);
  }
  syncHlScroll();
}

function syncHlScroll() {
  const y = $("editor").scrollTop || 0;
  $("hlInner").style.transform = `translateY(${-y}px)`;
}

function flashRange(start, end) {
  const b = document.createElement("div");
  b.className = "hl-band flash";
  bandStyle(b, start, end);
  $("hlInner").appendChild(b);
  syncHlScroll();
  setTimeout(() => b.remove(), 900);
}

function scrollEditorToLine(line, focus = true) {
  const ta = $("editor");
  const y = PAD_TOP + (line - 1) * LINE_H;
  if (y < ta.scrollTop + 40 || y > ta.scrollTop + ta.clientHeight - 60) {
    ta.scrollTop = Math.max(0, y - ta.clientHeight / 2.6);
  }
  if (focus) ta.focus();
  $("gutter").scrollTop = ta.scrollTop;
  syncHlScroll();
}

/** 某个标题在源文档里占的行区间（到下一个同级或更高级标题之前）。 */
function blockRange(item) {
  const items = parseOutline(editor.value);
  const i = items.findIndex((x) => x.line === item.line);
  if (i < 0) return [item.line, item.line];
  let end = editor.value.split("\n").length;
  for (let k = i + 1; k < items.length; k++) {
    if (items[k].level <= item.level) {
      end = items[k].line - 1;
      break;
    }
  }
  return [item.line, Math.max(item.line, end)];
}

// ---------- 列表 ----------
function renderPages() {
  const sel = $("pageSel");
  const box = $("files");
  sel.innerHTML = "";
  box.innerHTML = "";
  if (!S.pages.length) {
    sel.hidden = true;
    box.innerHTML = '<p class="ph">生成后在这里列出所有页面，点一下即可在左侧预览打开。</p>';
    return;
  }
  for (const p of S.pages) {
    const o = document.createElement("option");
    o.value = p.file;
    o.textContent = p.title;
    sel.appendChild(o);
  }
  sel.value = S.page;
  sel.hidden = S.pages.length < 2;

  for (const p of S.pages) {
    const b = document.createElement("button");
    if (p.file === S.page) b.classList.add("on");
    const kind = document.createElement("span");
    kind.className = "kind";
    kind.textContent = p.kind === "index" ? "首页"
      : p.kind === "appendix" ? "附录"
      : p.kind === "group" ? "分组" : "模块";
    const nm = document.createElement("span");
    nm.className = "nm";
    nm.textContent = p.title;
    nm.title = p.file;
    b.append(kind, nm);
    b.onclick = () => navTo(p.file);
    box.appendChild(b);
  }
}

function renderStats(st) {
  const el = $("stats");
  if (!st) {
    el.hidden = true;
    return;
  }
  el.hidden = false;
  el.innerHTML = "";
  const cells = [
    ["页面", st.pages],
    ["模块", st.modules],
    ["分组", st.groups],
    ["索引KB", st.index_kb],
    ["缺失", st.assets_missing, st.assets_missing ? "bad" : ""],
  ];
  for (const [k, n, cls] of cells) {
    const box = document.createElement("div");
    box.className = "st";
    const num = document.createElement("div");
    num.className = "n" + (cls ? " " + cls : "");
    num.textContent = n == null ? "-" : String(n);
    const key = document.createElement("div");
    key.className = "k";
    key.textContent = k;
    box.append(num, key);
    el.appendChild(box);
  }
}

// ---------- 大纲 ----------
let outlineSig = "";

function renderOutline() {
  const items = parseOutline(editor.value);
  const tree = buildTree(items);
  const sig = JSON.stringify(items.map((i) => [i.level, i.title, i.line, i.role])) +
    "|" + S.page + "|" + S.pages.map((p) => p.file + ":" + p.title).join(",") +
    "|" + [...S.collapsed].sort().join(",");
  if (sig === outlineSig) return;
  outlineSig = sig;
  renderOutlineInto($("outlineBody"), tree, {
    pages: S.pages,
    activePage: S.page,
    collapsed: S.collapsed,
    onToggle: (title) => {
      if (S.collapsed.has(title)) S.collapsed.delete(title);
      else S.collapsed.add(title);
      renderOutline();
    },
    onPick: onOutlinePick,
  });
}

function onOutlinePick(item) {
  if (item.home) {                     // 首页不是某个标题，直接切页面
    navTo("index.html", { scroll: false });
    if (item.line) flashRange(item.line, item.line);
    return;
  }
  if (!item.line) return;
  editor.gotoLine(item.line);
  if (item.title && item.level === 1) {
    const gp = S.pages.find((x) => x.kind === "group" && x.title === item.title);
    if (gp) navTo(gp.file, { scroll: false });
  }
  if (item.title && item.level === 2) {
    let file = null;
    if (item.role === "overview") file = "index.html";
    else if (item.role === "appendix") file = "appendix.html";
    else {
      const p = S.pages.find((x) => x.title === item.title);
      file = p ? p.file : null;
    }
    if (file) navTo(file, { scroll: false });
    else toast("这个模块还没有生成页面（先看预览）");
  }
  // 闪在最后：navTo 会重画底纹层，先闪会被清掉
  const [s, e] = blockRange(item);
  flashRange(s, e);
}

// ---------- 结构角色（点选，写回源文档） ----------
const ROLE_LABEL = { module: "模块页", overview: "总览", appendix: "附录" };
let roleSig = "";

function moduleTitles() {
  return parseOutline(editor.value)
    .filter((i) => i.level === 2 && i.role === "module")
    .map((i) => i.title);
}

function roleRow(item) {
  const row = document.createElement("div");
  row.className = "role-row";
  const nm = document.createElement("span");
  nm.className = "nm";
  nm.textContent = item.title || "(无标题)";
  nm.title = "点击定位到源文档这一行";
  nm.onclick = () => editor.gotoLine(item.line);
  const sel = document.createElement("select");
  sel.className = "mini";
  for (const [v, t] of [["module", "模块页"], ["overview", "总览"], ["appendix", "附录"]]) {
    const o = document.createElement("option");
    o.value = v;
    o.textContent = t;
    sel.appendChild(o);
  }
  sel.value = item.role;
  sel.title = "模块页=单独一页；总览=并入首页不单独成页；附录=并入附录页";
  sel.onchange = () => setHeadingRole(item.line, sel.value);
  row.append(nm, sel);
  return row;
}

function renderRoles(force = false) {
  const box = $("roles");
  if (!box) return;
  const items = parseOutline(editor.value);
  const h2s = items.filter((i) => i.level === 2);
  const sig = h2s.map((i) => i.line + ":" + i.role + ":" + i.title).join("|") + "|" + editor.value.length;
  if (!force && sig === roleSig) return;
  roleSig = sig;

  if (!editor.value.trim()) {
    box.innerHTML = '<p class="ph">打开一份 md 后，这里列出它的每个二级标题，以及各自在站点里的角色。</p>';
    return;
  }
  if (!h2s.length) {
    box.innerHTML = '<p class="ph">这份文档没有二级标题（<code>##</code>），所以不会生成模块页。</p>';
    return;
  }
  box.innerHTML = "";

  const n = { module: 0, overview: 0, appendix: 0 };
  for (const h of h2s) n[h.role] = (n[h.role] || 0) + 1;
  const sum = document.createElement("div");
  sum.className = "role-sum";
  sum.textContent = `${n.module} 个模块页 · ${n.overview} 个总览节 · ${n.appendix} 个附录节` +
    (S.opts.route_text.trim() ? "（另有规则表生效）" : "");
  box.appendChild(sum);

  const firstH1 = items.find((i) => i.level === 1);
  for (const it of items) {
    if (it.level === 1) {
      if (it === firstH1) continue;
      const g = document.createElement("div");
      g.className = "role-group";
      g.textContent = "▾ " + (it.title || "(未命名分组)");
      box.appendChild(g);
    } else if (it.level === 2) {
      box.appendChild(roleRow(it));
    }
  }

  const tip = document.createElement("p");
  tip.className = "role-tip";
  tip.textContent = "改动会直接记进源文档，并立刻反映到预览；记得保存（Ctrl+S）。";
  box.appendChild(tip);
}

function setHeadingRole(line, role) {
  const lines = editor.value.split("\n");
  const i = line - 1;
  if (i < 0 || i >= lines.length) return;
  const src = lines[i];
  const m = /\s*\{([^{}]*)\}\s*$/.exec(src);
  let block = m ? m[1] : "";
  block = block.replace(/\.(overview|appendix)\b/g, " ").replace(/\s+/g, " ").trim();
  if (role === "overview" || role === "appendix") block = (block + " ." + role).trim();
  const head = (m ? src.slice(0, m.index) : src).replace(/\s+$/, "");
  const next = block ? `${head} {${block}}` : head;
  if (next === src) return;
  editor.replaceLine(line, next);        // 内部触发 onChange → 置脏 + 重新预览
  renderRoles(true);
  log(`「${head.replace(/^#+\s*/, "")}」已设为${ROLE_LABEL[role] || role}`, "info");
}

// ---------- 别名配对（图形化，替代 `显示名=模块标题` 文本） ----------
function parseAliasText(text) {
  const out = {};
  for (const raw of (text || "").split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#") || line.startsWith("//")) continue;
    const i = line.indexOf("=");
    if (i <= 0) continue;
    const k = line.slice(0, i).trim();
    const v = line.slice(i + 1).trim();
    if (k && v) out[k] = v;
  }
  return out;
}

function cleanCell(s) {
  return s
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/[`*_]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** 扫出文档里所有表格单元格（跳过围栏代码块与分隔行）。 */
function scanTableCells(text) {
  const lines = (text || "").split("\n");
  const seen = new Map();
  let fence = null;
  for (let i = 0; i < lines.length; i++) {
    const s = lines[i].trim();
    if (/^(```|~~~)/.test(s)) {
      fence = fence ? null : 1;
      continue;
    }
    if (fence || !s.startsWith("|")) continue;
    if (/^\|[\s:|-]+\|?$/.test(s)) continue;
    for (const raw of s.replace(/^\|/, "").replace(/\|$/, "").split("|")) {
      const t = cleanCell(raw);
      if (t && !seen.has(t)) seen.set(t, i + 1);
    }
  }
  return seen;
}

/** 比对用的归一化键：去掉空白与各种括号标点，全小写。
 *  这样「StoryView（TMP）」才能对上「StoryView（TMP 表现层，可选程序集）」。 */
function normKey(s) {
  return (s || "").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");
}

/** 表格里「差一点就对上」的名字：归一化后与恰好一个模块标题互为前缀。 */
function suggestAliases() {
  const mods = moduleTitles();
  if (!mods.length) return [];
  const normed = mods.map((m) => ({ m, k: normKey(m) }));
  const modSet = new Set(mods);
  const out = [];
  for (const cell of scanTableCells(editor.value).keys()) {
    if (modSet.has(cell) || S.aliasDismissed.has(cell)) continue;
    const ck = normKey(cell);
    if (ck.length < 3) continue;          // 太短的格子（「部件」「职责」）不猜
    const hits = normed.filter(({ k }) => k !== ck && (k.startsWith(ck) || ck.startsWith(k)));
    if (hits.length === 1) out.push({ cell, target: hits[0].m });
    if (out.length >= 12) break;
  }
  return out;
}

function aliasRow(cell, target, mods) {
  const row = document.createElement("div");
  row.className = "alias-row";
  const input = document.createElement("input");
  input.type = "text";
  input.value = cell;
  input.placeholder = "表格里写的名字";
  const arrow = document.createElement("span");
  arrow.className = "arrow";
  arrow.textContent = "→";
  const sel = document.createElement("select");
  for (const m of mods) {
    const o = document.createElement("option");
    o.value = m;
    o.textContent = m;
    sel.appendChild(o);
  }
  if (target && !mods.includes(target)) {
    const o = document.createElement("option");
    o.value = target;
    o.textContent = target;
    sel.appendChild(o);
  }
  sel.value = target || mods[0] || "";
  const del = document.createElement("button");
  del.className = "btn tiny";
  del.textContent = "×";
  del.title = "删除这一行";

  const commit = () => {
    S.opts.alias = S.opts.alias || {};
    const k = input.value.trim();
    if (cell && cell !== k) delete S.opts.alias[cell];
    if (k && sel.value) S.opts.alias[k] = sel.value;
    schedulePreview(700);
  };
  input.addEventListener("change", commit);
  sel.addEventListener("change", commit);
  del.onclick = () => {
    if (cell) S.aliasDismissed.add(cell);
    delete S.opts.alias[cell];
    delete S.opts.alias[input.value.trim()];
    row.remove();
    schedulePreview(700);
  };
  row.append(input, arrow, sel, del);
  return row;
}

function renderAliasRows() {
  const box = $("aliasRows");
  if (!box) return;
  const mods = moduleTitles();
  S.opts.alias = S.opts.alias || {};
  // 建议项直接生效（够精确才给建议），用户删掉就记进「已忽略」，不再反复冒出来
  for (const s of suggestAliases()) {
    if (!(s.cell in S.opts.alias)) S.opts.alias[s.cell] = s.target;
  }
  box.innerHTML = "";
  const entries = Object.entries(S.opts.alias);
  if (!entries.length) {
    const p = document.createElement("div");
    p.className = "alias-empty";
    p.textContent = mods.length
      ? "没有需要配对的名字 —— 表格里写的和模块标题一致时会自动链接。"
      : "当前文档里还没有可链接的模块页。";
    box.appendChild(p);
    return;
  }
  for (const [cell, target] of entries) box.appendChild(aliasRow(cell, target, mods));
}

// ---------- 打开 / 保存 ----------
async function openPath(p) {
  let r;
  try {
    r = await post("md/read", { path: p });
  } catch (e) {
    toast("打开失败：" + e.message);
    return false;
  }
  if (!r.ok) {
    toast(r.error || "打开失败");
    return false;
  }
  S.path = r.path;
  S.mtime = r.mtime;
  S.lastDir = r.path.replace(/[\\/][^\\/]+$/, "");
  const proj = r.project || {};
  const po = proj.opts || {};
  const mdDir = r.path.replace(/[\\/][^\\/]+$/, "");
  const stem = r.path.replace(/^.*[\\/]/, "").replace(/\.(md|markdown)$/i, "");
  const sep = r.path.includes("\\") ? "\\" : "/";
  const norm = (x) => (x || "").replace(/[\\/]+$/, "").toLowerCase();
  const oldAuto = mdDir + sep + stem;      // 旧版自动推导的默认目录
  if (proj.out_base) {
    S.outBase = proj.out_base;
    S.subdir = proj.subdir !== false;
    S.subdirName = proj.subdir_name || "site";
  } else if (proj.out && norm(proj.out) !== norm(oldAuto)) {
    // 用户明确选过的目录：原样保留，不再套子目录
    S.outBase = proj.out;
    S.subdir = false;
    S.subdirName = "site";
  } else {
    // 没记录，或记录的就是旧的自动默认 → 走新默认：md 同级 / site
    S.outBase = mdDir;
    S.subdir = true;
    S.subdirName = "site";
  }
  S.title = proj.title || "";
  S.opts = {
    overview_links: !!po.overview_links,
    group_pages: !!po.group_pages,
    alias: (po.alias && typeof po.alias === "object") ? { ...po.alias } : parseAliasText(po.alias_text || ""),
    route_text: po.route_text || "",
    alias_text: po.alias_text || "",
  };
  S.aliasDismissed = new Set();
  S.source = "preview";
  S.page = "index.html";
  S.pages = [];
  S.stamp = 0;
  editor.setValue(r.text);
  setDirty(false);
  $("srcName").textContent = shortPath(r.path);
  $("srcName").title = r.path;
  $("editorMeta").textContent = `${r.text.split("\n").length} 行 · UTF-8`;
  syncOptionsUI();
  outlineSig = "";
  roleSig = "";
  renderOutline();
  renderRoles();
  renderPages();
  renderStats(null);
  hideFrame(true);
  drawHighlights([]);
  schedulePreview(0);
  log(`打开 ${r.path}`, "info");
  pushRecent(r.path);
  post("remember", { path: r.path }).then((d) => {
    if (d && d.ok && d.state) {
      S.recent = d.state.recent;
      renderRecent();
    }
  }).catch(() => {});
  return true;
}

async function saveNow() {
  if (!S.path) {
    toast("还没有打开文件");
    return false;
  }
  let r = await post("md/write", { path: S.path, text: editor.value, mtime: S.mtime });
  if (r.ok) {
    S.mtime = r.mtime;
    setDirty(false);
    toast("已保存");
    return true;
  }
  if (r.conflict) {
    const ok = await confirmDialog(
      "磁盘上的文件已被外部修改。\n\n继续保存会覆盖它，这个操作不可撤销。",
      { title: "文件已被外部修改", ok: "覆盖保存" });
    if (!ok) return false;
    r = await post("md/write", { path: S.path, text: editor.value, mtime: 0 });
    if (r.ok) {
      S.mtime = r.mtime;
      setDirty(false);
      toast("已覆盖保存");
      return true;
    }
  }
  toast(r.error || "保存失败");
  return false;
}

// ---------- 构建 ----------
async function buildNow() {
  if (!S.path) {
    toast("先选一份 Markdown 文件");
    return;
  }
  if (S.building) return;
  switchTab("build");
  setBusy(true);
  clearLog();
  log("开始生成…", "info");
  const t0 = performance.now();
  try {
    const r = await fetch(`${BASE}/api/build`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        path: S.path,
        out: effectiveOut(),
        out_base: S.outBase,
        subdir: S.subdir,
        subdir_name: S.subdirName,
        title: S.title,
        opts: S.opts,
        text: editor.value,
        save: true,
      }),
    });
    if (r.status === 409) {
      log("已有构建在进行中", "warn");
      return;
    }
    if (!r.ok || !r.body) {
      log(`构建请求失败（HTTP ${r.status}）`, "err");
      return;
    }
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const chunk = buf.slice(0, i);
        buf = buf.slice(i + 2);
        for (const ln of chunk.split("\n")) {
          if (!ln.startsWith("data:")) continue;
          let ev;
          try { ev = JSON.parse(ln.slice(5).trim()); } catch { continue; }
          onBuildEvent(ev);
        }
      }
    }
  } catch (e) {
    log("构建异常：" + e.message, "err");
  } finally {
    setBusy(false);
    log(`总耗时 ${((performance.now() - t0) / 1000).toFixed(2)} s`, "l");
  }
}

function onBuildEvent(ev) {
  if (ev.t === "start") {
    log(`源: ${ev.path}`, "l");
    log(`输出: ${ev.out}`, "l");
    return;
  }
  if (ev.t === "log") {
    const cls = /^!!|⚠|错误|失败/.test(ev.m) ? "err"
      : /^⚠|缺失|警告/.test(ev.m) ? "warn"
      : /^>/.test(ev.m) ? "l" : "info";
    log(ev.m, cls);
    return;
  }
  if (ev.t === "done") {
    if (ev.ok) {
      S.pages = ev.pages || [];
      S.stats = ev.stats;
      if (ev.mtime) S.mtime = ev.mtime;
      setDirty(false);
      S.source = "out";
      S.stamp += 1;
      if (!S.pages.some((p) => p.file === S.page)) S.page = "index.html";
      renderPages();
      renderStats(S.stats);
      drawHighlights(pageSpans(S.page));
      loadFrame();
      renderOutline();
      renderRoles(true);
      scheduleLint(300);
      switchTab("files");
      const st = ev.stats || {};
      log(`> 分组 ${st.groups} · 模块 ${st.modules} · 页面 ${st.pages}` +
        (st.appendix ? ` · 附录 ${st.appendix_sections} 节` : ""), "info");
      log(`> 搜索索引 ${st.index_kb} KB · 资源 拷贝 ${st.assets_copied} / 缺失 ${st.assets_missing}`,
        st.assets_missing ? "warn" : "info");
      if (st.strict) {
        log(`> 栏目角色严格模式：总览节 ${st.overview_sections} · 附录节 ${st.appendix_sections}`, "info");
      }
      log(`生成完成 ✔  输出 ${ev.out}`, "ok");
    } else if (ev.cancelled) {
      log("已取消", "warn");
    } else {
      log("生成失败：" + (ev.error || "未知原因"), "err");
    }
  }
}

// ---------- 结构检查 ----------
let lintTimer = 0;
let lintSeq = 0;

function scheduleLint(delay = 1200) {
  clearTimeout(lintTimer);
  if (!S.path) return;
  lintTimer = setTimeout(runLint, delay);
}

async function runLint() {
  if (!S.path) return;
  const seq = ++lintSeq;
  let res;
  try {
    res = await post("lint", { path: S.path, text: editor.value, opts: S.opts });
  } catch {
    return;
  }
  if (seq !== lintSeq) return;
  renderLint(res);
}

function renderLint(res) {
  const box = $("lintItems");
  const badge = $("lintBadge");
  box.innerHTML = "";
  if (!res || !res.ok) {
    const p = document.createElement("p");
    p.className = "ph";
    p.textContent = (res && res.error) || "检查失败";
    box.appendChild(p);
    return;
  }
  const counts = res.counts || {};
  const items = res.items || [];
  const total = (counts.error || 0) + (counts.warn || 0);
  badge.hidden = !total;
  badge.textContent = total > 99 ? "99+" : String(total);
  badge.classList.toggle("err", (counts.error || 0) > 0);
  $("lintSum").textContent = items.length
    ? `${counts.error || 0} 错误 · ${counts.warn || 0} 提醒 · ${counts.info || 0} 提示`
    : "没问题";

  if (!items.length) {
    const p = document.createElement("p");
    p.className = "ph";
    p.textContent = "没发现问题，可以生成了。";
    box.appendChild(p);
    return;
  }
  for (const it of items) {
    const row = document.createElement("div");
    row.className = "lint-item " + it.level;
    const dot = document.createElement("span");
    dot.className = "dot";
    const msg = document.createElement("span");
    msg.className = "msg";
    msg.textContent = it.msg;
    const ln = document.createElement("span");
    ln.className = "ln";
    ln.textContent = it.line ? "L" + it.line : "";
    row.append(dot, msg, ln);
    if (it.line) {
      row.title = `点击跳到第 ${it.line} 行`;
      row.onclick = () => {
        editor.gotoLine(it.line);
        flashRange(it.line, it.line);
      };
    }
    box.appendChild(row);
  }
}

// ---------- 选项 ----------
function syncOptionsUI() {
  $("optOutBase").value = S.outBase;
  $("optSubdir").checked = !!S.subdir;
  $("optSubdirName").value = S.subdirName || "site";
  $("optTitle").value = S.title;
  $("optOvLinks").checked = !!S.opts.overview_links;
  $("optGroupPages").checked = !!S.opts.group_pages;
  $("optRoute").value = S.opts.route_text || "";
  $("optAlias").value = S.opts.alias_text || "";
  syncSubdirRow();
  renderAliasRows();
}

/** 勾选「生成到子目录」才显示子目录名；否则整行隐藏 */
function syncSubdirRow() {
  $("optSubdirRow").hidden = !S.subdir;
  const out = effectiveOut();
  $("optOutPreview").textContent = out ? "将输出到 " + out : "";
}

/** 最终输出目录：父目录 [+ 子目录名] */
function effectiveOut() {
  const base = (S.outBase || "").trim().replace(/[\\/]+$/, "");
  if (!base) return "";
  if (!S.subdir) return base;
  const sep = base.includes("\\") ? "\\" : "/";
  const name = (S.subdirName || "").trim().replace(/[\\/:*?"<>|]/g, "") || "site";
  return base + sep + name;
}

function readOptionsUI() {
  S.outBase = $("optOutBase").value.trim();
  S.subdir = $("optSubdir").checked;
  S.subdirName = $("optSubdirName").value.trim() || "site";
  S.title = $("optTitle").value.trim();
  // 只更新本控件负责的字段，保留 alias 对象（它由配对表单独维护）
  S.opts.overview_links = $("optOvLinks").checked;
  S.opts.group_pages = $("optGroupPages").checked;
  S.opts.route_text = $("optRoute").value;
  S.opts.alias_text = $("optAlias").value;
  syncSubdirRow();
  schedulePreview(500);
}

// ---------- 最近文件 ----------
function pushRecent(p) {
  S.recent = S.recent.filter((r) => r.path !== p);
  S.recent.unshift({ path: p, name: p.split(/[\\/]/).pop(), dir: p.replace(/[\\/][^\\/]+$/, "") });
  S.recent = S.recent.slice(0, 12);
  renderRecent();
}

function renderRecent() {
  const m = $("recentMenu");
  m.innerHTML = "";
  if (!S.recent.length) {
    m.innerHTML = '<div class="empty">还没有打开过文档。</div>';
    return;
  }
  for (const r of S.recent) {
    const b = document.createElement("button");
    const n = document.createElement("span");
    n.className = "mname";
    n.textContent = r.name;
    const d = document.createElement("span");
    d.className = "mdir";
    d.textContent = r.dir;
    b.append(n, d);
    b.onclick = () => {
      m.hidden = true;
      openPath(r.path);
    };
    m.appendChild(b);
  }
}

// ---------- 标签页 ----------
function switchTab(name) {
  for (const t of document.querySelectorAll(".tab")) t.classList.toggle("on", t.dataset.tab === name);
  for (const b of document.querySelectorAll(".tabbody")) b.hidden = b.dataset.body !== name;
}

// ---------- 分栏拖拽 ----------
function initSplitter() {
  const sp = $("splitter");
  const pane = $("editorPane");
  const saved = localStorage.getItem("markpage-split");
  if (saved) pane.style.flexBasis = saved;
  let dragging = false;
  sp.addEventListener("mousedown", (e) => {
    dragging = true;
    e.preventDefault();
    document.body.style.cursor = "col-resize";
  });
  window.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    const box = $("center").getBoundingClientRect();
    const pct = Math.min(82, Math.max(18, ((e.clientX - box.left) / box.width) * 100));
    pane.style.flexBasis = pct + "%";
  });
  window.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false;
    document.body.style.cursor = "";
    localStorage.setItem("markpage-split", pane.style.flexBasis);
  });
}

// ---------- 事件绑定 ----------
const picker = new Picker($("dlgPicker"), get, post, toast);

function bindUI() {
  $("btnSource").onclick = async () => {
    const p = await picker.open("file", S.lastDir || "");
    if (p) openPath(p);
  };

  $("btnRecent").onclick = (e) => {
    e.stopPropagation();
    const m = $("recentMenu");
    m.hidden = !m.hidden;
  };
  document.addEventListener("click", (e) => {
    const m = $("recentMenu");
    if (!m.hidden && !m.contains(e.target)) m.hidden = true;
  });

  $("btnOptions").onclick = () => {
    syncOptionsUI();
    $("dlgOptions").showModal();
  };  $("optClose").onclick = () => $("dlgOptions").close();
  $("optDone").onclick = () => $("dlgOptions").close();
  $("optPickOut").onclick = async () => {
    const p = await picker.open("dir", $("optOutBase").value.trim() || S.lastDir || "");
    if (p) {
      $("optOutBase").value = p;
      readOptionsUI();
    }
  };
  $("btnAliasAdd").onclick = () => {
    const mods = moduleTitles();
    if (!mods.length) {
      toast("当前文档还没有可链接的模块页");
      return;
    }
    $("aliasRows").querySelector(".alias-empty")?.remove();
    $("aliasRows").appendChild(aliasRow("", mods[0], mods));
    $("aliasRows").lastElementChild.querySelector("input").focus();
  };
  for (const id of ["optOutBase", "optSubdirName", "optTitle", "optRoute", "optAlias"]) {
    $(id).addEventListener("change", readOptionsUI);
    $(id).addEventListener("blur", readOptionsUI);
  }
  $("optOvLinks").addEventListener("change", readOptionsUI);
  $("optGroupPages").addEventListener("change", readOptionsUI);
  $("optSubdir").addEventListener("change", readOptionsUI);
  $("optSubdirName").addEventListener("input", () => {
    S.subdirName = $("optSubdirName").value.trim() || "site";
    syncSubdirRow();
  });

  $("btnBuild").onclick = () => buildNow();
  $("btnCancel").onclick = async () => {
    await post("cancel", {}).catch(() => {});
    log("已请求取消…", "warn");
  };
  $("btnOpenDir").onclick = async () => {
    const r = await post("open", { what: "dir" }).catch((e) => ({ ok: false, error: e.message }));
    if (!r.ok) toast(r.error || "打开失败");
  };
  $("btnOpenSite").onclick = async () => {
    const r = await post("open", { what: "site", page: S.page })
      .catch((e) => ({ ok: false, error: e.message }));
    if (!r.ok) toast(r.error || "打开失败");
  };
  $("btnZip").onclick = async () => {
    const r = await post("zip", {}).catch((e) => ({ ok: false, error: e.message }));
    if (!r.ok) {
      toast(r.error || "打包失败");
      return;
    }
    log(`已打包：${r.path}（${Math.round(r.size / 1024)} KB）`, "ok");
    toast("已打包到 " + r.path, 4200);
  };
  $("btnClean").onclick = async () => {
    const ok = await confirmDialog(
      "会删掉输出目录里本站生成的文件：\n*.html、site.css、site.js、search-index.js、assets/\n\n" +
      "目录里的其他文件不受影响。", { title: "清理输出目录", ok: "清理" });
    if (!ok) return;
    const r = await post("clean", { confirm: true }).catch((e) => ({ ok: false, error: e.message }));
    if (!r.ok) {
      toast(r.error || "清理失败");
      return;
    }
    S.pages = [];
    S.stats = null;
    S.source = "preview";
    renderPages();
    renderStats(null);
    hideFrame(true);
    drawHighlights([]);
    log(`已清理 ${r.removed} 项：${r.dir}`, "warn");
    toast("已清理");
  };
  $("btnLint").onclick = () => runLint();
  $("frame").addEventListener("load", onFrameLoad);
  $("btnSave").onclick = () => saveNow();
  $("btnTheme").onclick = () => setTheme(S.theme === "dark" ? "light" : "dark");
  $("btnPop").onclick = () => {
    if (!S.path) return;
    window.open(`${frameBase()}${S.page}?v=${S.stamp}`, "_blank");
  };
  for (const b of document.querySelectorAll("[data-width]")) {
    b.onclick = () => setWidth(b.dataset.width);
  }
  for (const t of document.querySelectorAll(".tab")) {
    t.onclick = () => {
      switchTab(t.dataset.tab);
      if (t.dataset.tab === "lint") scheduleLint(0);
    };
  }
  $("pageSel").onchange = (e) => navTo(e.target.value);

  window.addEventListener("keydown", (e) => {
    if (e.isComposing || e.keyCode === 229) return;   // 输入法组合态不接管
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      buildNow();
    }
  });

  window.addEventListener("beforeunload", (e) => {
    if (S.dirty) {
      e.preventDefault();
      e.returnValue = "";
    }
  });

  // 拖入 .md：浏览器出于安全不给绝对路径，只能用「上次目录 + 同名 + 内容一致」来认它
  document.addEventListener("dragover", (e) => e.preventDefault());
  document.addEventListener("drop", async (e) => {
    e.preventDefault();
    const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (!f) return;
    if (!/\.(md|markdown)$/i.test(f.name)) {
      toast("只支持拖入 .md 文件");
      return;
    }
    const text = await f.text();
    const sep = (S.lastDir || "").includes("\\") ? "\\" : "/";
    const cand = (S.lastDir || "") + sep + f.name;
    const r = await post("md/read", { path: cand }).catch(() => null);
    if (r && r.ok && r.text === text) {
      openPath(cand);
    } else {
      toast(`浏览器不提供拖入文件的磁盘路径。已在上次目录查找同名文件：${
        r && r.ok ? "内容不同，可能不是同一个文件" : "没找到"}。请用「选择文件」按钮打开。`, 5200);
    }
  });

  initSplitter();
}

// ---------- 启动 ----------
async function boot() {
  try {
    const t = localStorage.getItem("markpage-theme");
    setTheme(t === "dark" ? "dark" : "light");
  } catch { /* ignore */ }

  bindUI();

  let env;
  try {
    env = await get("env");
  } catch (e) {
    log("无法连接本地服务：" + e.message, "err");
    return;
  }
  S.lastDir = env.state.last_dir || env.home;
  S.recent = env.state.recent || [];
  S.projects = env.state.projects || {};
  renderRecent();

  const eng = env.engine || {};
  S.engineOk = !!eng.ok;
  if (!S.engineOk) {
    log("引擎不可用：未找到带 markdown + pygments 的 Python。", "err");
    log("可用环境变量 WORKBUDDY_VENV_PY 指定解释器路径。", "warn");
  } else {
    log(`引擎就绪（${eng.mode === "embed" ? "内嵌" : "子进程"} · Python ${eng.python}）`, "ok");
  }
  setBusy(false);

  if (env.state.last_path) {
    const ok = await openPath(env.state.last_path);
    if (!ok) log("上次打开的文档已不可用，请重新选择。", "warn");
  }

  setInterval(() => {
    post("ping", {}).catch(() => {});
  }, 5000);
}

boot();
