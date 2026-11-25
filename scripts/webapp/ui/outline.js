// 结构大纲：从 md 文本里扫标题骨架（跳过围栏代码块），按引擎同一套规则推导
// 分组 / 模块 / 角色，再渲染成可点选的树。
//
// 只做「读」，不改文本；栏目角色仍以行尾 {.overview}/{.appendix} 为准，
// 与 md_site_builder.scan_headings 的判定保持一致。

const FENCE = /^\s*(```|~~~)/;

function cleanTitle(v) {
  return v.replace(/\[([^\]]+)\]\([^)]*\)/g, "$1").replace(/[`*_]/g, "").trim();
}

export function parseOutline(text) {
  const lines = (text || "").split("\n");
  const items = [];
  let fence = null;
  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const s = raw.trim();
    if (FENCE.test(s)) {
      fence = fence ? null : s.slice(0, 3);
      continue;
    }
    if (fence) continue;
    const m = /^(#{1,3})\s+(.*)$/.exec(raw);
    if (!m) continue;
    let title = m[2].trim();
    let role = "module";
    const am = /\s+\{([^{}]*)\}$/.exec(title);
    if (am) {
      if (/\.overview\b/.test(am[1])) role = "overview";
      else if (/\.appendix\b/.test(am[1])) role = "appendix";
      if (role !== "module") title = title.slice(0, am.index).trim();
    }
    items.push({
      level: m[1].length,
      title: cleanTitle(title),
      raw: m[2].trim(),
      line: i + 1,
      role,
    });
  }
  return items;
}

export function buildTree(items) {
  const first = items.find((i) => i.level === 1) || null;
  const groups = [];
  const loose = [];
  const entries = [];        // 按文档顺序记录块（分组 / 无归组的散装节），渲染时照此顺序
  let g = null;
  let last = null;           // 最近一个二级标题节点，用来挂三级小节的父级

  for (const it of items) {
    if (it === first) continue;
    if (it.level === 1) {
      g = { ...it, children: [] };
      groups.push(g);
      entries.push({ type: "group", group: g });
      last = null;
      continue;
    }
    if (it.level === 2) {
      const node = { ...it, subs: [] };
      if (g) {
        g.children.push(node);
      } else {
        loose.push(node);
        entries.push({ type: "loose", item: node });
      }
      last = node;
      continue;
    }
    if (last) last.subs.push(it);
  }
  return { first, groups, loose, entries };
}

function targetOf(item, pages) {
  if (item.level === 1 && item.title) {                 // 分组页（模块独立渲染模式才有）
    const gp = pages.find((x) => x.kind === "group" && x.title === item.title);
    if (gp) return gp.file;
  }
  if (item.role === "overview") return "index.html";
  if (item.role === "appendix") {
    return pages.some((x) => x.file === "appendix.html") ? "appendix.html" : null;
  }
  const p = pages.find((x) => x.title === item.title);
  return p ? p.file : null;
}

export function renderOutlineInto(el, tree, opts) {
  const { pages = [], activePage = "index.html", collapsed, onPick, onToggle } = opts;
  el.innerHTML = "";

  if (!tree.first && !tree.groups.length && !tree.loose.length) {
    el.innerHTML = '<p class="ph">这份文档还没有任何标题。</p>';
    return;
  }

  const home = document.createElement("div");
  home.className = "o-item" + (activePage === "index.html" ? " on" : "");
  const hnm = document.createElement("span");
  hnm.className = "nm";
  hnm.textContent = "首页";
  home.appendChild(hnm);
  if (tree.first) {
    const hint = document.createElement("span");
    hint.className = "o-role";
    hint.textContent = "站点标题";
    home.appendChild(hint);
  }
  // home: true 让上层知道「这是首页」而不是某个分组标题
  home.onclick = () => onPick({ ...(tree.first || {}), home: true, level: 1,
                                title: "首页", line: tree.first ? tree.first.line : 0 });
  el.appendChild(home);

  const itemRow = (it) => {
    const row = document.createElement("div");
    const target = targetOf(it, pages);
    row.className = "o-item" + (target && target === activePage ? " on" : "");
    const nm = document.createElement("span");
    nm.className = "nm";
    nm.textContent = it.title || "(无标题)";
    nm.title = it.title || "";
    row.appendChild(nm);
    if (it.role === "overview" || it.role === "appendix") {
      const tag = document.createElement("span");
      tag.className = "o-role" + (it.role === "appendix" ? " app" : "");
      tag.textContent = it.role === "overview" ? "总览" : "附录";
      row.appendChild(tag);
    }
    row.onclick = () => onPick(it);
    return row;
  };

  // 一个二级标题 + 它下面的三级小节
  const itemWithSubs = (it) => {
    el.appendChild(itemRow(it));
    for (const sub of it.subs) {
      const srow = document.createElement("div");
      srow.className = "o-sub";
      srow.textContent = sub.title || "(无标题)";
      srow.title = sub.title || "";
      srow.onclick = () => onPick(sub);
      el.appendChild(srow);
    }
  };

  const groupBlock = (g) => {
    const open = !collapsed.has(g.title);
    const head = document.createElement("div");
    head.className = "o-group";
    const caret = document.createElement("span");
    caret.className = "caret";
    caret.textContent = open ? "▾" : "▸";
    const nm = document.createElement("span");
    nm.className = "nm";
    nm.textContent = g.title || "(未命名分组)";
    nm.style.overflow = "hidden";
    nm.style.textOverflow = "ellipsis";
    nm.style.whiteSpace = "nowrap";
    head.append(caret, nm);
    // 箭头只管折叠；点标题本体则跳转（分组独立成页时有分组页，否则退回折叠）
    caret.onclick = (e) => {
      e.stopPropagation();
      onToggle(g.title);
    };
    head.onclick = () => {
      if (targetOf(g, pages)) onPick(g);
      else onToggle(g.title);
    };
    head.title = targetOf(g, pages)
      ? "点击打开该分组的页面；点左侧箭头折叠"
      : "点击折叠 / 展开";
    if (targetOf(g, pages) === activePage) head.classList.add("on");
    el.appendChild(head);
    if (!open) return;
    for (const child of g.children) itemWithSubs(child);
  };

  // 严格按文档顺序：首组之前的散装节排在最前，而不是被挤到末尾
  for (const e of tree.entries) {
    if (e.type === "group") groupBlock(e.group);
    else itemWithSubs(e.item);
  }
}
