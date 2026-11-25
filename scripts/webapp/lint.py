# -*- coding: utf-8 -*-
"""结构检查 —— 把「不报错但会出错」的地方在构建前指出来。

引擎对很多情况是宽容的：标题跳级照样渲染、模块重名会偷偷加 -2 后缀、别名写错
就静默不生效、图片找不到只打印一行警告。这些在成稿前就该让作者看见，所以单独做一层。

**刻意不 import md_site_builder**：这个模块要跑在 Web 服务进程里，而「子进程模式」
下服务进程本身没有 markdown/pygments（引擎在子进程里跑）。标题扫描只是正则活，
本地实现一份即可，免得一个检查功能把整个界面拖崩。

约定：每条都带 line（1-based），界面点一下就跳到源文档对应行；line=0 表示整篇级问题。
"""
import os
import re

IMG_MD = re.compile(r"!\[[^\]]*\]\(\s*([^)\s]+)")
IMG_HTML = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.I)
HEADING = re.compile(r"^(\s*)(#{1,3})([ \t]+)(.*)$")
ATTR_BLOCK = re.compile(r"\s+\{([^{}]*)\}$")
CLASSNAME = re.compile(r"\.([A-Za-z_][\w-]*)")

SKIP_PREFIX = ("http://", "https://", "//", "data:", "mailto:", "tel:", "#")


def clean_title(value):
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    return re.sub(r"[`*_]", "", value).strip()


def scan_headings(lines):
    """与 md_site_builder.scan_headings 同规则（含 {.overview}/{.appendix} 剥离），
    但只读不改，且不依赖 python-markdown。"""
    heads = []
    fence = None
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("```") or s.startswith("~~~"):
            fence = None if fence else s[:3]
            continue
        if fence:
            continue
        m = HEADING.match(line)
        if not m:
            continue
        title = m.group(4).strip()
        role = "module"
        am = ATTR_BLOCK.search(title)
        if am:
            classes = CLASSNAME.findall(am.group(1))
            if "overview" in classes:
                role = "overview"
            elif "appendix" in classes:
                role = "appendix"
            if role != "module":
                title = title[:am.start()].rstrip()
        heads.append({"idx": i, "level": len(m.group(2)), "title": title,
                      "clean": clean_title(title), "role": role})
    return heads


def _is_remote(url):
    return url.lower().startswith(SKIP_PREFIX)


def _exists(md_dir, url):
    """相对路径按源文档所在目录解析；远程/锚点一律视为存在。"""
    try:
        u = url.split("#")[0].split("?")[0]
        if not u or _is_remote(u):
            return True
        if os.path.isabs(u):
            return os.path.exists(u)
        return os.path.exists(os.path.join(md_dir, u.replace("/", os.sep)))
    except (OSError, ValueError):
        return True


def lint(md_path, md_text, opts=None):
    """返回 {"ok": True, "items": [...], "counts": {...}}。任何异常都不外抛。"""
    items = []

    def add(level, msg, line=0):
        items.append({"level": level, "msg": msg, "line": int(line or 0)})

    text = md_text or ""
    lines = text.split("\n")
    md_dir = os.path.dirname(os.path.abspath(md_path)) if md_path else ""
    opts = opts or {}

    if not text.strip():
        add("error", "文档是空的。")
        return _pack(items)

    try:
        heads = scan_headings(lines)
    except Exception as e:                       # noqa: BLE001
        add("error", f"标题扫描失败：{e}")
        return _pack(items)

    h1s = [h for h in heads if h["level"] == 1]
    h2s = [h for h in heads if h["level"] == 2]

    # 1) 站点标题
    if not h1s:
        add("error", "没有一级标题（`# 标题`）—— 站点取不到名字，生成会直接失败。")
    else:
        first = h1s[0]
        nxt = next((h["idx"] for h in heads if h["idx"] > first["idx"] and h["level"] <= 2), len(lines))
        if not "\n".join(lines[first["idx"] + 1:nxt]).strip() and not h2s:
            add("info", "首页除了标题没有别的内容。", first["idx"] + 2)

    # 2) 标题跳级
    prev = None
    for h in heads:
        if prev is not None and h["level"] > prev["level"] + 1:
            add("warn", f"标题跳级：从 {'#' * prev['level']} 直接到 {'#' * h['level']}，"
                        f"中间少了 {'#' * (h['level'] - 1)}。", h["idx"] + 1)
        prev = h

    # 3) 空标题
    for h in heads:
        if not h["clean"].strip():
            add("warn", "标题是空的。", h["idx"] + 1)

    # 4) 模块标题重复 / 5) 分组标题重复
    seen, gseen = {}, {}
    for h in h2s:
        if h["role"] != "module":
            continue
        key = h["clean"].strip()
        if not key:
            continue
        if key in seen:
            add("warn", f"模块标题重复：「{key}」在第 {seen[key]} 行也有，"
                        f"生成时后一个会变成同名文件的 -2 版本。", h["idx"] + 1)
        else:
            seen[key] = h["idx"] + 1
    for h in h1s[1:]:
        key = h["clean"].strip()
        if key in gseen:
            add("warn", f"分组标题重复：「{key}」（第 {gseen[key]} 行也有）。", h["idx"] + 1)
        else:
            gseen[key] = h["idx"] + 1

    # 6) 没有模块页
    if not h2s:
        add("warn", "没有任何二级标题（`##`）—— 不会生成模块页，只会有一个首页。")

    # 7) 模块只有标题没正文
    for h in h2s:
        end = next((n["idx"] for n in heads if n["idx"] > h["idx"] and n["level"] <= 2), len(lines))
        if not "\n".join(lines[h["idx"] + 1:end]).strip():
            add("info", f"「{h['clean']}」这个模块页没有正文。", h["idx"] + 1)

    # 8) 图片指向的文件不存在
    for i, raw in enumerate(lines):
        for rx in (IMG_MD, IMG_HTML):
            for m in rx.finditer(raw):
                if not _exists(md_dir, m.group(1)):
                    add("warn", f"图片找不到：{m.group(1)}", i + 1)

    # 9) 界面里的规则 / 别名写了但没生效
    titles = {h["clean"] for h in h2s}
    for rule in (opts.get("route") or []):
        pat = (rule.get("title") or "").strip()
        if not pat:
            continue
        prefix = rule.get("match") == "prefix"
        hit = any((h["clean"].startswith(pat) if prefix else h["clean"] == pat) for h in h2s)
        if not hit:
            add("warn", f"栏目规则「{pat}{'*' if prefix else ''}={rule.get('role')}」"
                        f"没有匹配到任何二级标题。")
    for cell, target in (opts.get("alias") or {}).items():
        if target not in titles:
            add("warn", f"别名「{cell}」指向的模块「{target}」不存在。")

    return _pack(items)


def _pack(items):
    order = {"error": 0, "warn": 1, "info": 2}
    items.sort(key=lambda x: (order.get(x["level"], 3), x["line"] or 10 ** 6))
    counts = {"error": 0, "warn": 0, "info": 0}
    for it in items:
        counts[it["level"]] = counts.get(it["level"], 0) + 1
    return {"ok": True, "items": items, "counts": counts}
