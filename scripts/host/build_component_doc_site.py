# -*- coding: utf-8 -*-
"""《组件 API 参考》多页站点生成器（Markpage 参数化版）

从「宿主工程文档专用固化脚本」参数化迁移而来，随 Markpage 仓库统一演进。
与原版差异：
  - 路径全部参数化：--pkg / --src / --out / --title / --brand（默认值保持原行为）；
  - 渲染核心改用 Markpage 引擎（from md_site_builder import convert, AssetCollector），
    自动获得代码块增强(行号/语言/复制)、站内资源收集与 ../ 链接重定位等后续修复，
    不再维护一份 convert 副本；
  - FILEMAP / CELL_LINK 可经 --filemap / --cellmap 提供 JSON 覆盖（默认内嵌原值）。
仍保留的文档专属语义（参数化救不了也不需要救）：
  `# 部件`分组 + `## 类型/契约/类`=模块页 + `**class in ...**` api-meta + 总览表自动改链
  + 固定「完整装配样例」桥接层附录。

用法:
  python scripts/host/build_component_doc_site.py                       # 自动探测宿主包
  python scripts/host/build_component_doc_site.py --pkg <宿主包根>       # 显式指定
  python scripts/host/build_component_doc_site.py --src a.md --out 某目录  # 全手动
  环境变量 MARKPAGE_PKG 可代替 --pkg。
"""
import argparse
import json
import re
import sys
import datetime
import pathlib
import html as _html

# ---- 引用 Markpage 引擎（本文件位于 scripts/host/，引擎在 scripts/）----
_SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from md_site_builder import convert  # noqa: E402
from md_site_builder import AssetCollector  # noqa: E402

DATE = datetime.date.today().isoformat()

# 默认宿主包（开发机探测）：显式 --pkg / MARKPAGE_PKG > 已知开发机路径 > None
_DEFAULT_PKG = r"D:\Unity\Project\MicrobialNet\MicrobialNextUnityProj\Packages\com.microbialnet.story"

# 文档专属：模块页标题 -> 固定文件名（默认；可用 --filemap JSON 覆盖）
DEFAULT_FILEMAP = {
    "StoryFlow": "story-flow.html",
    "StoryGraphRegistry": "story-graph-registry.html",
    "StoryView（TMP 表现层，可选程序集）": "story-view.html",
    "DialogueBoxManager（UI 程序集）": "dialogue-box-manager.html",
    "VariableDebugView": "variable-debug-view.html",
    "对话框盒子视图：StoryLineBoxView / StoryChoiceBoxView / StoryMessageBoxView": "dialogue-box-views.html",
    "StoryFlowConfig": "story-flow-config.html",
    "StoryConstants": "story-constants.html",
    "StoryEventBus": "story-event-bus.html",
    "InMemoryVariableProvider": "in-memory-variable-provider.html",
    "LocalizationTextProvider": "localization-text-provider.html",
    "StoryGraphLocalizationProvider": "story-graph-localization-provider.html",
    "ScriptableCharacterResolver": "scriptable-character-resolver.html",
    "PlayerPrefsSaveStore": "player-prefs-save-store.html",
    "StoryGraphCollection": "story-graph-collection.html",
    "StoryAssetLocator / ResourcesStoryAssetLocator / IStoryAssetLocator": "story-asset-locator.html",
    "IStoryVariableProvider": "i-story-variable-provider.html",
    "IStoryEventHandler + IStoryEvent + [StoryEvent]": "i-story-event.html",
    "IStoryTextProvider": "i-story-text-provider.html",
    "IStoryCharacterResolver": "i-story-character-resolver.html",
    "IStorySaveStore": "i-story-save-store.html",
    "IStoryPresenter": "i-story-presenter.html",
    "IStoryAssetLocator（适配器实现）": "i-story-asset-locator.html",
    "StoryGraphAsset": "story-graph-asset.html",
    "StoryCharacterAsset": "story-character-asset.html",
    "StoryGlobalVariableAsset + StoryVariableDef": "story-global-variable-asset.html",
    "StoryLocalizationTable / StoryLocalizationAsset": "story-localization-table.html",
    "样式 / 打字机 / 定位 / 生成策略资产": "style-and-positioning-assets.html",
    "StoryTableAsset（剧情表）": "story-table-asset.html",
}

# 文档专属：总览一览表单元格 -> 模块链接（默认；可用 --cellmap JSON 覆盖）
DEFAULT_CELL_LINK = {
    "`StoryFlow`": "[StoryFlow](story-flow.html)",
    "`StoryGraphRegistry`": "[StoryGraphRegistry](story-graph-registry.html)",
    "`StoryView`（TMP）": "[StoryView（TMP）](story-view.html)",
    "`DialogueBoxManager`（UI）": "[DialogueBoxManager（UI）](dialogue-box-manager.html)",
    "`VariableDebugView`（TMP）": "[VariableDebugView（TMP）](variable-debug-view.html)",
    "`StoryLineBoxView` / `StoryChoiceBoxView` / `StoryMessageBoxView`（TMP）":
        "[对话框盒子视图](dialogue-box-views.html)",
    "`StoryFlowConfig`": "[StoryFlowConfig](story-flow-config.html)",
    "`StoryConstants`": "[StoryConstants](story-constants.html)",
    "`StoryEventBus`": "[StoryEventBus](story-event-bus.html)",
    "`InMemoryVariableProvider`": "[InMemoryVariableProvider](in-memory-variable-provider.html)",
    "`LocalizationTextProvider`": "[LocalizationTextProvider](localization-text-provider.html)",
    "`StoryGraphLocalizationProvider`": "[StoryGraphLocalizationProvider](story-graph-localization-provider.html)",
    "`ScriptableCharacterResolver`": "[ScriptableCharacterResolver](scriptable-character-resolver.html)",
    "`PlayerPrefsSaveStore`": "[PlayerPrefsSaveStore](player-prefs-save-store.html)",
    "`StoryGraphCollection`": "[StoryGraphCollection](story-graph-collection.html)",
    "`StoryAssetLocator` / `ResourcesStoryAssetLocator`":
        "[StoryAssetLocator / ResourcesStoryAssetLocator](story-asset-locator.html)",
    "`IStoryVariableProvider` 等七条契约": "[契约接口（IStoryVariableProvider 等七条）](i-story-variable-provider.html)",
    "`StoryGraphAsset` 等数据资产": "[数据资产（StoryGraphAsset 等）](story-graph-asset.html)",
}


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="《组件 API 参考》多页站点生成器（Markpage 参数化版）")
    ap.add_argument("--pkg", help="宿主包根目录（默认推导 src/out 用；可被 --src/--out 覆盖）")
    ap.add_argument("--src", help="源 Markdown（默认 <pkg>/Documentation/组件API参考/组件API参考.md）")
    ap.add_argument("--out", help="输出目录（默认 <pkg>/Documentation/组件API参考/html）")
    ap.add_argument("--title", default="组件 API 参考（业务侧）", help="站点标题（默认：组件 API 参考（业务侧））")
    ap.add_argument("--brand", default="MicrobialNet Story", help="品牌名（默认：MicrobialNet Story）")
    ap.add_argument("--filemap", help="可选 JSON：模块标题 -> 文件名 映射，覆盖内置默认")
    ap.add_argument("--cellmap", help="可选 JSON：总览表单元格 -> 链接 映射，覆盖内置默认")
    a = ap.parse_args(argv)

    pkg = a.pkg or __import__("os").environ.get("MARKPAGE_PKG") or ""
    if not a.src:
        base = pathlib.Path(pkg) if pkg else pathlib.Path(_DEFAULT_PKG)
        a.src = str(base / "Documentation" / "组件API参考" / "组件API参考.md")
    if not a.out:
        base = pathlib.Path(pkg) if pkg else pathlib.Path(_DEFAULT_PKG)
        a.out = str(base / "Documentation" / "组件API参考" / "html")
    return a


def slugify(value: str, sep: str = "-") -> str:
    value = re.sub(r"[`*_>]", "", value)
    value = re.sub(r"[^\w\u4e00-\u9fff\- ]", "", value, flags=re.UNICODE)
    return re.sub(r"\s+", sep, value.strip()).lower()


def main(argv=None) -> int:
    a = parse_args(argv)
    src = pathlib.Path(a.src)
    if not src.is_file():
        print(f"!! 找不到源文档: {src}")
        return 1
    out = pathlib.Path(a.out)
    filemap = json.load(open(a.filemap, encoding="utf-8")) if a.filemap else DEFAULT_FILEMAP
    cell_link = json.load(open(a.cellmap, encoding="utf-8")) if a.cellmap else DEFAULT_CELL_LINK
    doc_title, brand = a.title, a.brand

    text = src.read_text(encoding="utf-8")
    lines = text.split("\n")
    col = AssetCollector(src.parent, out)          # 资源收集 + ../链接重定位（与通用站一致）

    # ---------- 解析标题结构 ----------
    class H:
        __slots__ = ("idx", "level", "title", "id")
        def __init__(self, idx, level, title):
            self.idx = idx; self.level = level; self.title = title
            self.id = slugify(title)

    heads = []
    for i, l in enumerate(lines):
        m = re.match(r"^(#{1,3})\s+(.*)$", l)
        if m:
            heads.append(H(i, len(m.group(1)), m.group(2).strip()))

    def slice_text(a, b):
        return "\n".join(lines[a:b]).strip("\n")

    def seg_html(a, b, plain_h1=False):
        seg = slice_text(a, b)
        if not seg.strip():
            return "", []
        body, tok = convert(seg, plain_h1=plain_h1)
        return col.rebase_links(col.rewrite(body)), tok

    def next_head(idx):
        for h in heads:
            if h.idx > idx and h.level <= 2:
                return h
        return None

    parts, modules = [], []
    part_idx = -1
    for h in heads:
        if h.level == 1:
            if h.title != doc_title:
                part_idx += 1
                parts.append({"title": h.title, "intro": (h.idx + 1, None), "mods": []})
            continue
        if h.level == 2:
            if h.title == "组件总览" or h.title.startswith("附录"):
                continue
            nxt = next_head(h.idx)
            f = filemap.get(h.title)
            if not f:
                print("!! 未映射模块页:", h.title); continue
            rec = {"title": h.title, "file": f, "start": h.idx,
                   "end": nxt.idx if nxt else len(lines),
                   "part": parts[part_idx]["title"] if part_idx >= 0 else ""}
            modules.append(rec)
            if part_idx >= 0:
                parts[part_idx]["mods"].append(rec)
    for p in parts:
        endline = p["mods"][0]["start"] if p["mods"] else len(lines)
        p["intro"] = (p["intro"][0], endline)

    ov = next((h for h in heads if h.title == "组件总览"), None)
    scene_part = next((p for p in parts if p["title"].startswith("场景组件")), None)
    appendix_h = next((h for h in heads if h.title.startswith("附录")), None)
    if ov is None or scene_part is None or appendix_h is None:
        print("!! 文档结构不符合组件参考约定（缺 组件总览/场景组件 部件/附录 标题）")
        return 2
    APPENDIX_GROUP = "附录"

    # 总览一览表单元格 -> 链接
    overview_lines = lines[ov.idx:scene_part["mods"][0]["start"]]
    overview_linked = []
    for l in overview_lines:
        hit = None
        for cell, link in cell_link.items():
            if cell in l:
                hit = link; break
        if hit and l.lstrip().startswith("|"):
            parts_ = l.split("|")
            if len(parts_) >= 4:
                parts_[1] = " " + hit + " "
                l = "|".join(parts_)
        overview_linked.append(l)
    overview_md = "\n".join(overview_linked).strip("\n")

    # ---------- 左侧目录（分类抽屉）----------
    NAV_GROUPS = [{"title": p["title"], "file": None, "items": [(m["title"], m["file"]) for m in p["mods"]]}
                  for p in parts]
    NAV_GROUPS.append({"title": APPENDIX_GROUP, "file": None,
                       "items": [("附录：完整装配样例", "appendix.html")]})

    def make_nav(current: str) -> str:
        def item(title, file):
            active = " active" if file == current else ""
            return f'<li><a class="toc-link{active}" href="{file}">{_html.escape(title)}</a></li>'
        groups_html = []
        for gi, g in enumerate(NAV_GROUPS):
            active_here = any(f == current for _, f in g["items"])
            open_attr = ' open' if active_here else ''
            lis = "".join(item(t, f) for t, f in g["items"])
            groups_html.append(
                f'<details class="toc-group" data-i="{gi}"{open_attr}>'
                f'<summary>{_html.escape(g["title"])}<span class="cnt">{len(g["items"])}</span></summary>'
                f'<ul>{lis}</ul></details>')
        index_active = " active" if current == "index.html" else ""
        return (
            '<nav id="toc" aria-label="目录">'
            '<div class="toc-home"><a class="toc-home-link" href="index.html">组件 API 参考</a></div>'
            f'<a class="toc-link toc-top{index_active}" href="index.html">总览</a>'
            + "".join(groups_html)
            + '<div class="toc-foot"></div></nav>'
            '<div id="tocBackdrop"></div>'
        )

    from doc_site_assets import CSS, JS  # noqa: E402  Markpage scripts/ 内单一事实源

    def page(title, current, body_html, prev=None, nxt=None, chips_html="", crumb=""):
        pag = ('<nav class="pager"><span>' +
               (('<a href="%s">← %s</a>' % (prev[1], prev[0])) if prev else '<span></span>') +
               '</span><span style="flex:1;text-align:center"><a href="index.html">☰ 返回总览</a></span>' +
               '<span>' + (('<a href="%s">%s →</a>' % (nxt[1], nxt[0])) if nxt else '<span></span>') + '</span></nav>')
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="generator" content="{brand}">
<title>{_html.escape(title)} · {doc_title}</title>
<style>{CSS}</style>
<script src="search-index.js"></script></head>
<body>
<div class="topbar">
  <span class="brand"><a href="index.html" style="color:var(--ink)">{brand} · 组件 API 参考</a></span>
  <span class="crumb" style="color:var(--muted);font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{crumb}</span>
  <span class="spacer"></span>
  <div class="search" id="searchBox">
    <input id="searchInput" type="text" placeholder="搜索组件 / API / 关键词…" autocomplete="off" spellcheck="false" aria-label="站内搜索">
    <svg class="s-ico" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
    <div class="s-panel" id="searchPanel"></div>
  </div>
  <button id="tocBtn">☰ 目录</button>
  <button id="themeBtn">🌙 深色</button>
</div>
<div class="layout">
{make_nav(current)}
<main><article>
{chips_html}
{body_html}
{pag}
<p class="foot">{brand} · 生成于 {DATE}</p>
</article></main>
</div>
<script>{JS}</script>
</body></html>"""

    out.mkdir(parents=True, exist_ok=True)
    PAGES = {}  # file -> 页面 html（内存副本，构建索引用）

    # ---- 首页 ----
    intro_raw = slice_text(0, ov.idx)
    intro_raw = "\n".join(x for x in intro_raw.split("\n") if x.strip() != "---")
    intro_html, _ = convert(intro_raw, plain_h1=True) if intro_raw.strip() else ("", [])
    intro_html = col.rebase_links(col.rewrite(intro_html))
    overview_body, _ = convert(overview_md)
    overview_body = col.rebase_links(col.rewrite(overview_body))
    cards = []
    for p in parts:
        items = "".join(f'<a class="dir-card" href="{m["file"]}"><h4>{_html.escape(m["title"])}</h4></a>'
                        for m in p["mods"])
        intro_html_part = ""
        a0, b0 = p["intro"]
        seg = slice_text(a0, b0)
        if seg.strip() and not seg.strip().startswith("---"):
            intro_html_part = '<div class="part-intro">' + seg_html(a0, b0)[0] + "</div>"
        cards.append(f'<div class="part-block"><h3>{_html.escape(p["title"])}</h3>{intro_html_part}'
                     f'<div class="dir-grid">{items}</div></div>')
    index_body = intro_html + overview_body + "".join(cards) + \
        '<p style="margin-top:26px"><a class="chip" href="appendix.html">附录：完整装配样例（宿主桥接层）→</a></p>'
    PAGES["index.html"] = page("总览", "index.html", index_body, crumb="总览")
    (out / "index.html").write_text(PAGES["index.html"], encoding="utf-8")

    # ---- 模块页 ----
    for i, m in enumerate(modules):
        body_html, tokens = seg_html(m["start"], m["end"])
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
        prev = modules[i - 1] if i > 0 else None
        nxt = modules[i + 1] if i < len(modules) - 1 else None
        prev_t = (prev["title"], prev["file"]) if prev else None
        nxt_t = (nxt["title"], nxt["file"]) if nxt else None
        page_html = page(m["title"], m["file"], body_html, prev_t, nxt_t, chips_html, m["part"])
        PAGES[m["file"]] = page_html
        (out / m["file"]).write_text(page_html, encoding="utf-8")

    # ---- 附录 ----
    app_body, _ = seg_html(appendix_h.idx, len(lines))
    app_html = page("附录：完整装配样例", "appendix.html", app_body,
                    (modules[-1]["title"], modules[-1]["file"]) if modules else None, None, crumb="附录")
    PAGES["appendix.html"] = app_html
    (out / "appendix.html").write_text(app_html, encoding="utf-8")

    # ---- 跨页搜索索引：按 h2/h3 切节提取纯文本 -> search-index.js ----
    def _txt(frag):
        frag = re.sub(r'<a class="anchor"[^>]*>.*?</a>', "", frag, flags=re.S)
        frag = re.sub(r"<[^>]+>", "", frag)
        frag = _html.unescape(frag)
        return re.sub(r"\s+", " ", frag).strip()[:2000]

    def build_search_index(pages):
        files = [("index.html", "总览", "总览"),
                 *((m["file"], m["title"], m["part"]) for m in modules),
                 ("appendix.html", "附录", "附录")]
        idx = []
        for fname, title, group in files:
            s = pages[fname]
            art = re.search(r"<article[^>]*>(.*?)</article>", s, re.S)
            body = art.group(1) if art else ""
            hs = list(re.finditer(r'<h([23])[^>]*id="([^"]*)"[^>]*>(.*?)</h\1>', body, re.S))
            anchors = []
            if hs:
                for k, h in enumerate(hs):
                    hid = h.group(2)
                    if not hid:
                        continue
                    hname = _txt(h.group(3))
                    st, en = h.end(), (hs[k + 1].start() if k + 1 < len(hs) else len(body))
                    if k == 0:
                        st = 0
                    x = _txt(body[st:en])
                    if not x and not hname:
                        continue
                    anchors.append({"id": hid, "h": hname, "x": x})
            else:
                x = _txt(body)
                if x:
                    anchors.append({"id": "", "h": "", "x": x})
            if anchors:
                idx.append({"f": fname, "t": title, "g": group, "a": anchors})
        js = "window.SEARCH_INDEX=" + json.dumps(idx, ensure_ascii=False) + ";"
        (out / "search-index.js").write_text(js, encoding="utf-8")
        return len(idx), len(js.encode("utf-8"))

    n_pages, n_bytes = build_search_index(PAGES)

    print(f"生成: {out} | HTML: {len(list(out.glob('*.html')))} | 模块页: {len(modules)} | "
          f"索引页: {n_pages} | search-index.js: {round(n_bytes / 1024)} KB")
    if col._missing:
        print("⚠ 资源缺失（仅提示，不中断）:", *col._missing[:6], sep="\n    - ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
