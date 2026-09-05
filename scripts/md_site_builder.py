# -*- coding: utf-8 -*-
"""通用 md -> 多页文档站生成器（供任意 Markdown 文档使用，GUI/CLI 共用核心）。

用法（命令行）:
  python md_site_builder.py 某文档.md [--out 输出目录] [--title 站点标题]

规则（依据源文档标题结构自动推导，无需额外配置）:
  - 第一个 `# 标题`           -> 站点标题（缺省用文件名），其下到首个分组前的正文进入首页总览区；
  - 后续每个 `#` 一级标题      -> 一个分组（左侧目录的分类抽屉、首页分组卡片）；若全文再无 `#`，则不分
                                  组，所有 `##` 模块平铺；
  - `## 模块`                 -> 一个独立模块页（文件名取标题的 slug，保留中文）；
  - `### 小节`                -> 模块页内栏目（页顶 chips + 搜索锚点）；
  - 标题以「附录」开头的 `##`  -> 独立为附录页并置于目录末尾（可有多个附录小节，从首个起直至文末）；
  - 生成的站点 = 输出目录/index.html + 每模块一页 + 附录 + search-index.js（顶栏搜索数据源），
    含左侧目录（分组收缩抽屉）、深浅主题、跨页搜索、上一页/下一页。

样式与交互（CSS/JS）统一来自同目录 doc_site_assets.py（单一事实来源，与组件 API 参考站点共用）。
需要 python-markdown + pygments（本仓库 venv 已装）。
"""
import re, sys, json, argparse, pathlib, datetime, html as _html
import urllib.parse
import markdown

TOOLS = pathlib.Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
from doc_site_assets import CSS, JS  # noqa: E402

SITE_DATE = datetime.date.today().isoformat()

# ---------- md 渲染 ----------
def slugify(value: str, sep: str = "-") -> str:
    value = re.sub(r"[`*_>]", "", value)
    value = re.sub(r"[^\w\u4e00-\u9fff\- ]", "", value, flags=re.UNICODE)
    return re.sub(r"\s+", sep, value.strip()).lower()

def clean_title(value: str) -> str:
    """标题清洗：去反引号、去 markdown 链接只留文字。"""
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    return re.sub(r"[`*_]", "", value).strip()

def new_md():
    return markdown.Markdown(
        extensions=["tables", "fenced_code", "codehilite", "toc", "sane_lists", "attr_list"],
        extension_configs={
            "toc": {"slugify": slugify, "permalink": False, "toc_depth": "1-3"},
            "codehilite": {"css_class": "hl", "guess_lang": False},
        },
    )

def convert(mdtext: str, plain_h1: bool = False):
    m = new_md()
    body = m.convert(mdtext)
    body = re.sub(r"<table>", '<div class="tbl-wrap"><table>', body).replace("</table>", "</table></div>")
    body = re.sub(r"<p>(<strong>class in</strong>.*?)</p>", r'<p class="api-meta">\1</p>', body, flags=re.S)
    if not plain_h1:
        body = re.sub(r"<h1 id=\"([^\"]+)\">", r'<h1 class="part-title" id="\1">', body)
    body = decorate_code_blocks(body, mdtext)
    return body, m.toc_tokens

# ---------- 代码块增强：行号列 + 语言标签 ----------
LANG_NAMES = {
    "c": "C", "csharp": "C#", "c#": "C#", "cs": "C#", "cpp": "C++", "c++": "C++",
    "java": "Java", "python": "Python", "py": "Python", "javascript": "JavaScript",
    "js": "JavaScript", "typescript": "TypeScript", "ts": "TypeScript",
    "json": "JSON", "xml": "XML", "html": "HTML", "css": "CSS",
    "hlsl": "HLSL", "cg": "CG", "shader": "ShaderLab", "shadergraph": "ShaderGraph",
    "yaml": "YAML", "yml": "YAML", "toml": "TOML", "ini": "INI", "sql": "SQL",
    "bash": "Shell", "sh": "Shell", "shell": "Shell", "zsh": "Shell",
    "powershell": "PowerShell", "ps1": "PowerShell", "lua": "Lua",
    "markdown": "Markdown", "md": "Markdown", "text": "Text", "plaintext": "Text",
    "diff": "Diff", "regex": "Regex", "console": "Console", "log": "Log",
}

# 围栏起始行：```` lang 或 `~~~ lang`（lang 可空）
_FENCE_OPEN = re.compile(r"^(?: {0,3})(?P<fence>`{3,}|~{3,})[ \t]*(?P<lang>[A-Za-z0-9_+.#-]*)[ \t]*$")

def _fenced_langs(mdtext: str):
    """按源码出现顺序收集每个围栏代码块的语言（无语言围栏为空串）。"""
    langs = []
    in_ch = None      # 当前围栏字符（` 或 ~）
    in_len = 0
    for ln in mdtext.split("\n"):
        m = _FENCE_OPEN.match(ln)
        if in_ch is None:
            if m:
                in_ch = m.group("fence")[0]
                in_len = len(m.group("fence"))
                langs.append(m.group("lang"))
        else:
            if m and m.group("fence")[0] == in_ch and len(m.group("fence")) >= in_len:
                in_ch = None
    return langs

def _lang_label(lang: str) -> str:
    if not lang:
        return ""
    key = lang.lower()
    if key in LANG_NAMES:
        return LANG_NAMES[key]
    return lang if lang[:1].isupper() else lang[:1].upper() + lang[1:]

_HL_BLOCK = re.compile(r'<div class="hl">(.*?)</div>', re.S)

def _hl_line_count(code_html: str) -> int:
    """由 code 内部 HTML 推视觉行数（pygments 的换行符在 span 之外，安全）。"""
    n = code_html.count("\n")
    if not code_html.endswith("\n"):
        n += 1
    return max(n, 1)

def decorate_code_blocks(html: str, mdtext: str):
    """给代码块补两样东西：
      1) 行号列  —— 包装为 .hl-scroll（行号 gutter + 原 pre），纯 HTML 侧即可完成；
      2) 语言标签——md 源里的围栏语言与产物 .hl 顺序一一对应（本语料全部为 fenced）；
         数量不一致（存在缩进式代码块等）时降级：仍加行号，语言标签不给。
    """
    langs = _fenced_langs(mdtext)
    n_hl = len(_HL_BLOCK.findall(html))
    aligned = len(langs) == n_hl
    if not aligned:
        sys.stderr.write(f"[decorate] 代码块对齐跳过语言标签: fenced={len(langs)} .hl={n_hl}\n")
    state = {"i": 0}

    def repl(m):
        inner = m.group(1)
        if '<div class="hl-scroll">' in inner:      # 已装饰，幂等
            return m.group(0)
        cb = inner.find("<code>")
        ce = inner.rfind("</code>")
        if cb < 0 or ce < 0:
            return m.group(0)
        code_html = inner[cb + len("<code>"):ce]
        n_lines = _hl_line_count(code_html)
        gutter = "\n".join(str(k) for k in range(1, n_lines + 1))

        lang = ""
        if aligned and state["i"] < len(langs):
            lang = langs[state["i"]]
        state["i"] += 1

        label = _lang_label(lang)
        lang_attr = f' data-lang="{_html.escape(lang)}"' if lang else ""
        badge = f'<span class="hl-lang-badge">{_html.escape(label)}</span>' if label else ""
        actions = ('<div class="hl-actions">' + badge
                   + '<button type="button" class="hl-copy" title="复制代码" aria-label="复制代码">复制</button>'
                   + '</div>')
        core = inner.strip()
        return (f'<div class="hl"{lang_attr}>'
                f'<div class="hl-scroll">'
                f'<pre class="hl-gutter" aria-hidden="true">{gutter}</pre>'
                f'{core}'
                f'</div>{actions}</div>')

    return _HL_BLOCK.sub(repl, html)


# ---------- 图片 / 视频资源：拷贝进站内 assets/ 并改写引用 ----------
IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".avif"}
VID_EXT = {".mp4", ".webm", ".ogv", ".mov", ".m4v"}
_SRC_RE = re.compile(r'(<(?:img|video|source|audio)\b[^>]*?\b(?:src|poster))="([^"]*)"', re.I)

class AssetCollector:
    """把页面 HTML 里引用的本地图片/视频拷进 <站点>/assets/，并把 src/poster 改写为站内路径。
    路径以「源 md 所在目录」为基准解析（支持 ./、../、绝对盘符路径）。
    远程 URL / data: / 锚点 / 站内根路径 / 非图片视频扩展名一律不动。
    缺失文件不中断生成，记录 warning（页面保留原 src，显示 alt 文字）。"""

    def __init__(self, md_dir, out_dir, log=print):
        self.md_dir = pathlib.Path(md_dir).resolve()
        self.out_dir = pathlib.Path(out_dir).resolve()
        self.assets_dir = self.out_dir / "assets"
        self.log = log
        self._map = {}            # 源文件绝对路径 -> assets/下的文件名
        self._taken = set()       # 已占用文件名（防重名冲突）
        self._missing = []        # 缺失文件（保持顺序去重）
        self.copied = 0

    # 解析原始属性值为绝对路径；不支持/不存在的返回 None
    def _resolve(self, raw):
        v = _html.unescape(raw).strip()
        if not v or v.startswith(("http://", "https://", "data:", "#", "//", "/")):
            return None
        try:
            p = urllib.parse.unquote(v)
        except Exception:
            p = v
        p = p.split("?", 1)[0].split("#", 1)[0]
        if not p:
            return None
        ext = pathlib.Path(p).suffix.lower()
        if ext not in IMG_EXT | VID_EXT:
            return None
        if re.match(r"^[A-Za-z]:[\\/]", p) or p.startswith(("\\\\", "\\")):
            cand = pathlib.Path(p)
        else:
            cand = self.md_dir
            for part in pathlib.PurePosixPath(p).parts:
                cand = cand / part
        try:
            cand = cand.resolve()
        except OSError:
            cand = cand
        if not cand.is_file():
            if str(cand) not in self._missing:
                self._missing.append(str(cand))
            return None
        return cand

    def _name_for(self, abs_p):
        """返回站内相对路径（assets/ 之下）：md 目录内的资源保留子目录层级；
        md 目录之外（如 ../ 引出的）拍平到 assets/ 根。均防重名冲突。"""
        if abs_p in self._map:
            return self._map[abs_p]
        try:
            relp = abs_p.relative_to(self.md_dir)
            parts = tuple(p for p in relp.parts if p not in ("", ".", ".."))
        except ValueError:
            parts = (abs_p.name,)
        if not parts:
            parts = (abs_p.name,)
        name = parts[-1]
        stem, ext = pathlib.Path(name).stem, pathlib.Path(name).suffix
        cand, k = list(parts), 1
        while "/".join(cand).lower() in self._taken:
            k += 1
            cand = list(parts[:-1]) + [f"{stem}-{k}{ext}"]
        self._taken.add("/".join(cand).lower())
        dst = self.assets_dir.joinpath(*cand)
        dst.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(abs_p, dst)
        self.copied += 1
        rel = "/".join(cand)
        self._map[abs_p] = rel
        return rel

    def rewrite(self, body):
        if not body:
            return body

        def rep(m):
            abs_p = self._resolve(m.group(2))
            if abs_p is None:
                return m.group(0)  # 不支持或缺失：原样保留
            return f'{m.group(1)}="assets/{urllib.parse.quote(self._name_for(abs_p), safe="/")}"'

        return _SRC_RE.sub(rep, body)

    def rebase_links(self, body):
        """重定位 md 源文里的相对 <a href> 链接。

        md 里的相对链接以「源 md 所在目录」为基准书写（与图片引用同一约定）。
        当站点输出目录位于 md 目录之下（如 <md>/html）时，页面实际深了一层，
        指向 md 目录之外的 '../xxx' 链接若原样输出会少一级 ../ 而解析错位。
        这里对这类链接统一补足 ../ 层级，使生成页面上的相对链接正确解析；
        md 源文件保持原样（在 md 预览里仍可直接点击跳转）。

        仅当 out_dir 严格位于 md_dir 之下时生效；输出目录与 md 目录同级
        （旧用法/任意输出目录）时不做改写，维持原行为。"""
        if not body:
            return body
        try:
            rel = self.out_dir.relative_to(self.md_dir)
        except ValueError:
            return body  # out_dir 不在 md_dir 之下（任意输出目录/旧用法：不做改写）
        if not rel.parts:
            return body  # out_dir == md_dir
        prefix = "../" * len(rel.parts)

        def rep(m):
            raw = m.group(2).strip()
            if not raw or not raw.startswith("../"):
                return m.group(0)  # 只处理指向 md 目录之外的相对链接
            return f'{m.group(1)}="{prefix}{raw}"'

        return re.sub(r'(<a\b[^>]*?\bhref)="([^"]*)"', rep, body, flags=re.I)

# ---------- 源文档结构解析 ----------
class Heading:
    __slots__ = ("idx", "level", "title", "clean")
    def __init__(self, idx, level, title):
        self.idx = idx
        self.level = level
        self.title = title
        self.clean = clean_title(title)

def scan_headings(lines):
    heads = []
    fence = None
    for i, l in enumerate(lines):
        s = l.strip()
        if s.startswith("```") or s.startswith("~~~"):
            fence = None if fence else s[:3]
            continue
        if fence:
            continue
        m = re.match(r"^(#{1,3})\s+(.*)$", l)
        if m:
            heads.append(Heading(i, len(m.group(1)), m.group(2).strip()))
    return heads

def build_model(md_text, doc_title=None):
    """返回 dict：title / overview(行区间) / groups[{title,start,end,mods[]}] / appendix{start,end} / lines。"""
    lines = md_text.split("\n")
    heads = scan_headings(lines)
    h1s = [h for h in heads if h.level == 1]
    h2s = [h for h in heads if h.level == 2]
    title = clean_title(h1s[0].title) if h1s else (doc_title or "")
    if not title:
        raise ValueError("找不到文档标题：请以 `# 标题` 开头，或在参数里提供 --title")
    groups, singles = [], None  # singles = 单组模式的模块 h2 列表
    mod_h2s = list(h2s)
    # 附录模块（标题以 附录 开头）
    app_head = next((h for h in mod_h2s if h.clean.startswith("附录")), None)
    if len(h1s) > 1:                      # 多分组
        overview = (h1s[0].idx + 1, h1s[1].idx)
        for k, h in enumerate(h1s[1:]):
            end = h1s[k + 2].idx if k + 2 < len(h1s) else len(lines)
            groups.append({"title": h.clean, "start": h.idx + 1, "end": end, "mods": []})
        for h in mod_h2s:
            if app_head and h.idx >= app_head.idx:
                continue
            g = next((g for g in groups if g["start"] <= h.idx < g["end"]), None)
            if g:
                g["mods"].append(h)
        groups = [g for g in groups if g["mods"]]
    else:                                 # 无分组（单标题文档）
        first_h2 = h2s[0].idx if h2s else len(lines)
        overview = (h1s[0].idx + 1, first_h2)
        singles = [h for h in h2s if not (app_head and h.idx >= app_head.idx)]
    # 模块切片终点：同文件内下一个 h2（或更高 h1）前
    def mod_end(h, allh):
        for nh in allh:
            if nh.idx > h.idx and nh.level <= 2:
                return nh.idx
        return len(lines)
    mods_all = []
    if groups:
        for g in groups:
            for h in g["mods"]:
                mods_all.append({"title": h.clean, "start": h.idx, "end": mod_end(h, h2s),
                                 "group": g["title"]})
    else:
        for h in singles:
            mods_all.append({"title": h.clean, "start": h.idx, "end": mod_end(h, h2s),
                             "group": ""})
    appendix = None
    if app_head:
        appendix = {"title": app_head.clean, "start": app_head.idx, "end": len(lines)}
    return {"lines": lines, "title": title, "overview": overview,
            "groups": groups, "mods": mods_all, "appendix": appendix}

def slice_text(model, a, b):
    return "\n".join(model["lines"][a:b]).strip("\n")

# ---------- 页面导航 ----------
def make_nav(model, current, mods):
    """mods: [{title,file,group}]；index 固定 index.html。"""
    home = _html.escape(model["title"])
    groups = []   # [{title, items:[(title,file)]}]
    if model["groups"]:
        for g in model["groups"]:
            items = [(m["title"], m["file"]) for m in mods if m["group"] == g["title"]]
            if items:
                groups.append({"title": g["title"], "items": items})
    else:
        items = [(m["title"], m["file"]) for m in mods]
        groups.append({"title": "", "items": items})
    if model["appendix"]:
        groups.append({"title": "附录", "items": [("附录", "appendix.html")]})

    def item(title, file):
        active = " active" if file == current else ""
        return f'<li><a class="toc-link{active}" href="{file}">{_html.escape(title)}</a></li>'
    groups_html = []
    for gi, g in enumerate(groups):
        active_here = any(f == current for _, f in g["items"])
        open_attr = " open" if active_here else ""
        lis = "".join(item(t, f) for t, f in g["items"])
        # 单组模式：组即全文，平铺不折叠
        if len(groups) == 1 and not g["title"]:
            groups_html.append(f"<ul>{lis}</ul>")
        else:
            groups_html.append(
                f'<details class="toc-group" data-i="{gi}"{open_attr}>'
                f'<summary>{_html.escape(g["title"])}<span class="cnt">{len(g["items"])}</span></summary>'
                f"<ul>{lis}</ul></details>")
    index_active = " active" if current == "index.html" else ""
    return (
        '<nav id="toc" aria-label="目录">'
        f'<div class="toc-home"><a class="toc-home-link" href="index.html">{home}</a></div>'
        f'<a class="toc-link toc-top{index_active}" href="index.html">总览</a>'
        + "".join(groups_html)
        + '<div class="toc-foot"></div></nav>'
        '<div id="tocBackdrop"></div>'
    )

# ---------- 整页模板 ----------
def render_page(model, page_title, current, body_html, prev=None, nxt=None, chips_html="", crumb="", out_meta=None):
    pag = ('<nav class="pager"><span>' +
           (('<a href="%s">← %s</a>' % (prev[1], prev[0])) if prev else "<span></span>") +
           '</span><span style="flex:1;text-align:center"><a href="index.html">☰ 返回总览</a></span>' +
           "<span>" + (('<a href="%s">%s →</a>' % (nxt[1], nxt[0])) if nxt else "<span></span>") + "</span></nav>")
    nav = make_nav(model, current, model.get("mods") or [])
    crumb_span = f'<span class="crumb" style="color:var(--muted);font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{_html.escape(crumb)}</span>'
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="generator" content="MicrobialNet Story">
<title>{_html.escape(page_title)} · {_html.escape(model["title"])}</title>
<style>{CSS}</style>
<script src="search-index.js"></script></head>
<body>
<div class="topbar">
  <span class="brand"><a href="index.html" style="color:var(--ink)">{_html.escape(model["title"])}</a></span>
  {crumb_span}
  <span class="spacer"></span>
  <div class="search" id="searchBox">
    <input id="searchInput" type="text" placeholder="搜索本文档…" autocomplete="off" spellcheck="false" aria-label="站内搜索">
    <svg class="s-ico" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
    <div class="s-panel" id="searchPanel"></div>
  </div>
  <button id="tocBtn">☰ 目录</button>
  <button id="themeBtn">🌙 深色</button>
</div>
<div class="layout">
{nav}
<main><article>
{chips_html}
{body_html}
{pag}
<p class="foot">生成于 {SITE_DATE}</p>
</article></main>
</div>
<script>{JS}</script>
</body></html>"""

# ---------- 站点构建 ----------
def build_site(md_path, out_dir=None, doc_title=None, log=print):
    md_path = pathlib.Path(md_path)
    if not md_path.exists():
        raise FileNotFoundError(f"找不到源文档: {md_path}")
    md_text = md_path.read_text(encoding="utf-8")
    model = build_model(md_text, doc_title)
    if doc_title:
        model["title"] = clean_title(doc_title)
    out_dir = pathlib.Path(out_dir) if out_dir else md_path.parent / md_path.stem
    # 输出目录中本站自产文件（*.html / search-index.js / assets/）先清空，
    # 避免模块改名/删减后旧页面残留；非本站文件一律保留。
    if out_dir.exists():
        for f in out_dir.glob("*.html"):
            f.unlink()
        (out_dir / "search-index.js").unlink(missing_ok=True)
        import shutil as _sh
        if (out_dir / "assets").is_dir():
            _sh.rmtree(out_dir / "assets")
    out_dir.mkdir(parents=True, exist_ok=True)
    col = AssetCollector(md_path.parent, out_dir, log)

    # 模块文件名（slug 唯一化）
    used = {}
    def uniq(slug):
        used[slug] = used.get(slug, 0) + 1
        return f"{slug}" if used[slug] == 1 else f"{slug}-{used[slug]}"
    out_meta = {}
    for m in model["mods"]:
        f = uniq(slugify(m["title"]) or "page")
        out_meta[f + ".html"] = {"title": m["title"], "group": m["group"]}
        m["file"] = f + ".html"

    def convert_seg(a, b):
        seg = slice_text(model, a, b)
        if not seg.strip():
            return ("", [])
        body, tok = convert(seg)
        return col.rebase_links(col.rewrite(body)), tok

    # ---- 首页 ----
    ov_body, _ = convert_seg(*model["overview"])
    cards_html = ""
    if model["groups"]:
        for g in model["groups"]:
            gmods = [m for m in model["mods"] if m["group"] == g["title"]]
            if not gmods:
                continue
            # 组内导语（组 h1 之后、首模块 h2 之前的文本）
            intro = ""
            seg = slice_text(model, g["start"], gmods[0]["start"])
            if seg.strip() and not seg.strip().startswith("---"):
                intro = '<div class="part-intro">' + col.rebase_links(col.rewrite(convert(seg)[0])) + "</div>"
            items = "".join(
                f'<a class="dir-card" href="{m["file"]}"><h4>{_html.escape(m["title"])}</h4></a>'
                for m in gmods)
            cards_html += (f'<div class="part-block"><h3>{_html.escape(g["title"])}</h3>{intro}'
                           f'<div class="dir-grid">{items}</div></div>')
    else:
        items = "".join(
            f'<a class="dir-card" href="{m["file"]}"><h4>{_html.escape(m["title"])}</h4></a>'
            for m in model["mods"])
        cards_html += f'<div class="dir-grid">{items}</div>'
    if model["appendix"]:
        cards_html += ('<p style="margin-top:26px"><a class="chip" href="appendix.html">'
                       f'附录：{_html.escape(model["appendix"]["title"])} →</a></p>')
    index_body = f'<h1>{_html.escape(model["title"])}</h1>' + ov_body + cards_html
    PAGES = {}
    PAGES["index.html"] = render_page(model, model["title"], "index.html", index_body,
                                      crumb="总览", out_meta=out_meta)
    (out_dir / "index.html").write_text(PAGES["index.html"], encoding="utf-8")

    # ---- 模块页 ----
    order = model["mods"]
    for i, m in enumerate(order):
        body_html, tokens = convert_seg(m["start"], m["end"])
        h3s = []
        def walk(items):
            for t in items:
                if t["level"] == 3:
                    h3s.append(t)
                walk(t.get("children", []))
        walk(tokens)
        chips = "".join(
            f'<a class="chip" href="#{t["id"]}">{_html.escape(re.sub(r"[`*_]+", "", t.get("name", "")))}</a>'
            for t in h3s)
        chips_html = f'<div class="chips">{chips}</div>' if chips else ""
        prev = order[i - 1] if i > 0 else None
        nxt = order[i + 1] if i < len(order) - 1 else None
        prev_t = (prev["title"], prev["file"]) if prev else None
        nxt_t = (nxt["title"], nxt["file"]) if nxt else None
        out = render_page(model, m["title"], m["file"], body_html, prev_t, nxt_t,
                          chips_html, m["group"] or model["title"], out_meta=out_meta)
        PAGES[m["file"]] = out
        (out_dir / m["file"]).write_text(out, encoding="utf-8")

    # ---- 附录页 ----
    if model["appendix"]:
        app_body, _ = convert_seg(model["appendix"]["start"], model["appendix"]["end"])
        app_html = render_page(model, model["appendix"]["title"], "appendix.html", app_body,
                               (order[-1]["title"], order[-1]["file"]) if order else None,
                               None, crumb="附录", out_meta=out_meta)
        PAGES["appendix.html"] = app_html
        (out_dir / "appendix.html").write_text(app_html, encoding="utf-8")

    # ---- 跨页搜索索引 ----
    def _txt(frag):
        frag = re.sub(r'<a class="anchor"[^>]*>.*?</a>', "", frag, flags=re.S)
        frag = re.sub(r"<[^>]+>", "", frag)
        frag = _html.unescape(frag)
        return re.sub(r"\s+", " ", frag).strip()[:2000]
    idx = []
    for fname, meta in [("index.html", (model["title"], model["title"]))] + \
                        [(m["file"], (m["title"], m["group"] or model["title"])) for m in order] + \
                        ([("appendix.html", ("附录", "附录"))] if model["appendix"] else []):
        s = PAGES[fname]
        art = re.search(r"<article[^>]*>(.*?)</article>", s, re.S)
        body = art.group(1) if art else ""
        hs = list(re.finditer(r'<h([23])[^>]*id="([^"]*)"[^>]*>(.*?)</h\1>', body, re.S))
        anchors = []
        if hs:
            for k, h in enumerate(hs):
                if not h.group(2):
                    continue
                st, en = h.end(), (hs[k + 1].start() if k + 1 < len(hs) else len(body))
                if k == 0:
                    st = 0
                x = _txt(body[st:en])
                if not x and not _txt(h.group(3)):
                    continue
                anchors.append({"id": h.group(2), "h": _txt(h.group(3)), "x": x})
        else:
            x = _txt(body)
            if x:
                anchors.append({"id": "", "h": "", "x": x})
        if anchors:
            idx.append({"f": fname, "t": meta[0], "g": meta[1], "a": anchors})
    js = "window.SEARCH_INDEX=" + json.dumps(idx, ensure_ascii=False) + ";"
    (out_dir / "search-index.js").write_text(js, encoding="utf-8")
    # 资源缺失告警（不中断生成）
    if col._missing:
        shown = col._missing if len(col._missing) <= 6 else col._missing[:6] + ["…"]
        log("⚠ 资源缺失（HTML 中保留原引用，alt 文本仍可见）：")
        for p in shown:
            log(f"    - {p}")
    return {"dir": str(out_dir), "pages": len(PAGES), "modules": len(order),
            "groups": len(model["groups"]) or (1 if model["mods"] else 0),
            "appendix": bool(model["appendix"]), "title": model["title"],
            "index_kb": round(len(js.encode("utf-8")) / 1024),
            "assets_copied": col.copied, "assets_missing": len(col._missing)}

# ---------- CLI ----------
def main(argv=None):
    ap = argparse.ArgumentParser(description="通用 Markdown 多页文档站生成器")
    ap.add_argument("md", help="源 Markdown 文件路径")
    ap.add_argument("--out", help="输出目录（默认：源文件同目录/<文件名>）")
    ap.add_argument("--title", help="站点标题（默认取首个 `#` 标题）")
    a = ap.parse_args(argv)
    r = build_site(a.md, a.out, a.title)
    print(f"生成: {r['dir']} | 页面: {r['pages']} | 模块: {r['modules']} | "
          f"分组: {r['groups']} | 附录: {r['appendix']} | 索引: {r['index_kb']} KB | "
          f"资源: 拷贝 {r['assets_copied']} / 缺失 {r['assets_missing']}")
    return r

if __name__ == "__main__":
    main()
