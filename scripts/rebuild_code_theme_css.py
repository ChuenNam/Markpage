# -*- coding: utf-8 -*-
"""重建 doc_site_assets.CSS 的代码块主题段（浅色 friendly / 深色 monokai）。

背景：CSS 常量源自从组件页提取的内联 monokai（无作用域），曾导致浅色模式下代码块
黑底。本脚本把 CSS 从标记“/* 代码块底色跟随主题 */”处截断，替换为三层结构：

  1) friendly（浅色 token）无作用域基座 —— 覆盖默认/无属性/OS浅色；
  2) monokai（深色 token）html[data-theme=dark] 前缀副本 —— 显式深色开关；
  3) monokai（深色 token）@media(prefers-color-scheme:dark){ :root:not([data-theme=light]) }
     前缀副本 —— 首次访问无存档 + 系统深色。

原理：CSS 层叠靠“更靠后的文件顺序 + 更高特异度”决定胜负。friendly 基座靠后覆盖旧的
无作用域 monokai；两个 monokai 副本各自特异度 (0,3,0)+ 压过 friendly 基座 (0,2,0)，
且三种状态（attr=light / attr=dark / 无属性）恰好各命中一套，互斥无冲突。

用法：python rebuild_code_theme_css.py  （直接改写 doc_site_assets.py 的 CSS 常量）
"""
import json
import re
import sys

sys.path.insert(0, __import__('os').path.dirname(__file__) or '.')
import doc_site_assets as d  # noqa: E402

from pygments.formatters import HtmlFormatter  # noqa: E402

MARKER = "/* 代码块底色跟随主题 */"
FILE = __import__('os').path.join(__import__('os').path.dirname(__file__), 'doc_site_assets.py')


def split_rules(style_defs):
    """把 pygments get_style_defs 输出拆成 (selector文本, body文本) 规则列表。

    注意：pygments 的“/* Comment.XXX */”注释位于规则右括号之后、下一条规则左括号之前，
    会粘连进下一条规则的选择器文本里，必须先剥离，否则会产生非法选择器。
    """
    rules = []
    for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', style_defs):
        sel = re.sub(r'/\*.*?\*/', '', m.group(1), flags=re.S).strip()
        if sel:
            rules.append((sel, m.group(2)))
    return rules


def is_linenos(sel):
    return sel.startswith('td.') or sel.startswith('span.')


def prefix_selectors(selector_text, prefix):
    """给规则的选择器加前缀；td./span. 行号规则保持原样（主题中立）。返回 None 表示跳过整条。"""
    parts = [s.strip() for s in selector_text.split(',')]
    out = []
    for p in parts:
        if is_linenos(p):
            continue
        if p == '.hl':
            out.append(prefix + ' .hl')
        elif p.startswith('.hl'):
            out.append(prefix + ' ' + p)
        else:
            # 其它选择器（理论不会出现）保持原样，避免丢规则
            out.append(p)
    return ', '.join(out) if out else None


def build_tail():
    """构造新的代码块主题段（追加在 CSS 末尾、覆盖旧的无作用域 monokai 段）。"""
    friendly = split_rules(HtmlFormatter(style='friendly').get_style_defs('.hl'))
    monokai = split_rules(HtmlFormatter(style='monokai').get_style_defs('.hl'))

    def _container_override(rules, new_selector, new_body=None):
        """把规则里的容器(.hl)规则替换/调整；返回 token 规则子集（不含容器）。"""
        out = []
        for sel, body in rules:
            sels = [s.strip() for s in sel.split(',')]
            # 容器规则只保留背景/前景的容器本体，token 规则原样保留
            if [s for s in sels if s == '.hl']:
                continue  # 容器另行统一生成
            keep = [s for s in sels if not is_linenos(s)]
            if not keep:
                continue
            out.append((', '.join(keep), body))
        return out

    fr_tokens = _container_override(friendly, None)
    mk_tokens = _container_override(monokai, None)

    def render_rules(tokens):
        lines = []
        for sel, body in tokens:
            lines.append(f'{sel} {{ {body.strip()} }}')
        return '\n'.join(lines)

    blocks = []
    blocks.append('/* 代码块主题：浅色=friendly / 深色=monokai（含显式开关与系统深色两种深色态） */')

    # 0) 代码面板变量（默认浅色；base :root 里写死的是深色 #0d1117，必须在本段整体覆盖）
    blocks.append('/* 0) 代码面板变量：默认浅色；系统深色 / html[data-theme=dark] 翻转为深色 */')
    blocks.append(':root{ --code-bg:#f6f8fa; --code-ink:#1f2328; }')
    blocks.append('@media (prefers-color-scheme: dark){ :root:not([data-theme=light]){ --code-bg:#0d1117; --code-ink:#e6edf3; } }')
    blocks.append('html[data-theme=dark]{ --code-bg:#0d1117; --code-ink:#e6edf3; }')
    blocks.append('html[data-theme=light]{ --code-bg:#f6f8fa; --code-ink:#1f2328; }')

    # 1) 浅色基座：容器 + friendly token 无作用域（在文件末尾 → 覆盖更早的无作用域 monokai）
    blocks.append('/* 1) 浅色基座（无属性/OS浅色/显式浅色 共用；--code-bg 由主题变量决定） */')
    blocks.append('.hl { background: var(--code-bg); color: var(--code-ink); }')
    blocks.append(render_rules(fr_tokens))

    # 2) 显式深色开关 html[data-theme=dark]
    blocks.append('/* 2) 深色 monokai —— html[data-theme=dark]（显式切到深色时命中） */')
    dark_sel = 'html[data-theme=dark]'
    mk_dark = [(prefix_selectors(sel, dark_sel), body) for sel, body in mk_tokens]
    mk_dark = [(s, b) for s, b in mk_dark if s]
    blocks.append(f'{dark_sel} .hl {{ background: #272822; color: #F8F8F2; }}')
    blocks.append(render_rules(mk_dark))

    # 3) 系统深色 + 未显式选浅色（首次访问无 localStorage 存档）
    blocks.append('/* 3) 深色 monokai —— 系统深色且未显式浅色（:root:not([data-theme=light])，供首次访问） */')
    blocks.append('@media (prefers-color-scheme: dark){')
    notl = ':root:not([data-theme=light])'
    mk_notl = [(prefix_selectors(sel, notl), body) for sel, body in mk_tokens]
    mk_notl = [(s, b) for s, b in mk_notl if s]
    blocks.append(f'{notl} .hl {{ background: #272822; color: #F8F8F2; }}')
    blocks.append(render_rules(mk_notl))
    blocks.append('}')

    return '\n' + '\n'.join(blocks) + '\n', len(fr_tokens), len(mk_tokens)


def main():
    css = d.CSS
    # 锚定“代码块主题”尾段起点（首次重建用旧标记，重跑时用新段标题，保证幂等）
    anchors = ['/* 代码块主题：浅色=friendly', MARKER]
    i = -1
    for a in anchors:
        k = css.find(a)
        if k >= 0 and css.count(a) == 1:
            i = k
            break
    if i < 0:
        raise SystemExit(f'neither anchor found: {anchors}')
    base = css[:i]  # 保留原 CSS 直至 lightbox 结束，丢弃此前有缺陷的追加段

    # 主题段之后可能还追加了其它自定义样式（如“代码块增强”），重建时原样保留
    enh_hdr = '/* ===== 代码块增强'
    j = css.find(enh_hdr)
    if j >= 0 and j > i:
        post = css[j:]          # 增强段及其后内容，保持原样
        tail_old_end = j
    else:
        post = ''
        tail_old_end = len(css)
    # 确认主题段确实在 (i, tail_old_end) 内结束于一个闭合的 media 块，不强求严格校验，
    # 只做粗检：重建后若发现主题段重复可人工检查。

    tail, n_fr, n_mk = build_tail()

    # —— 步骤 A：清除 base 区“无作用域 monokai 死代码” ——
    # 旧样式曾以内联 monokai（行首无前缀的 `.hl …` 规则）作为唯一高亮来源。
    # 它覆盖的 token 全集含 friendly 未着色的类（如 `.p` 标点=monokai 白 #F8F8F2），
    # 浅色模式下无对手覆盖 → 白字融底。深色现由 tail 的带前缀副本接管，浅色由
    # friendly 基座接管，因此 base 区行首 `.hl` 的规则全部删除即可（td./span. 行号
    # 主题中立规则保留）。
    base_lines = base.split('\n')
    removed = [ln for ln in base_lines if re.match(r'\.hl(?:\s|$|\.)', ln)]
    base_lines = [ln for ln in base_lines if not re.match(r'\.hl(?:\s|$|\.)', ln)]
    base = '\n'.join(base_lines)
    new_css = base + tail + post

    # 校验
    for probe in [':root{ --code-bg:#f6f8fa; --code-ink:#1f2328; }',
                  'html[data-theme=light]{ --code-bg:#f6f8fa; --code-ink:#1f2328; }',
                  'html[data-theme=dark]{ --code-bg:#0d1117; --code-ink:#e6edf3; }',
                  '.hl { background: var(--code-bg); color: var(--code-ink); }',
                  'html[data-theme=dark] .hl { background: #272822; color: #F8F8F2; }',
                  'html[data-theme=dark] .hl .c1 {',
                  '@media (prefers-color-scheme: dark){',
                  ':root:not([data-theme=light]) .hl .c1 {']:
        if probe not in new_css:
            raise SystemExit(f'missing probe: {probe!r}')
    for token in ['friendly', 'monokai']:
        pass  # 样式名不会出现在产物里（pygments 输出为具体规则），不做断言

    # 写回：只替换第 8 行（索引 7）CSS 字面量，其余行原样保留
    lines = open(FILE, encoding='utf-8').read().split('\n')
    assert lines[7].startswith('CSS = "'), 'unexpected CSS line layout'
    lines[7] = 'CSS = ' + json.dumps(new_css, ensure_ascii=False)
    open(FILE, 'w', encoding='utf-8').write('\n'.join(lines))

    print(f'OK  CSS {len(css)} -> {len(new_css)} chars; theme-seg@ {i}; enh preserved={bool(post)}; '
          f'friendly token rules={n_fr}, monokai rules={n_mk}; '
          f'base unstyled .hl rules removed={len(removed)}')


if __name__ == '__main__':
    main()
