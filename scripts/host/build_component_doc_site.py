# -*- coding: utf-8 -*-
"""《组件 API 参考》站点生成 —— Markpage 通用引擎直驱（宿主收敛版）

历史：
  - v1 前：本脚本是「通用引擎特化固化版」——自带 FILEMAP(标题→固定文件名)/CELL_LINK(总览表单元格→链接)
    及全套分页模板/搜索/导航自实现；
  - v1（2026-09）：总览表自动链接、栏目角色（{.overview}/{.appendix}）已上收进通用引擎
    （md_site_builder.build_site），宿主 md 源已加角色后缀 → 本脚本退化为薄参数包：
    定位源/输出 + 传站点标题 + 打开总览表链接 + 注入一览表别名，其余全部走引擎。

用法:
  python scripts/host/build_component_doc_site.py                       # 自动探测宿主包
  python scripts/host/build_component_doc_site.py --pkg <宿主包根>       # 显式指定
  python scripts/host/build_component_doc_site.py --src a.md --out 某目录  # 全手动
  环境变量 MARKPAGE_PKG 可代替 --pkg。
"""
import argparse
import json
import sys
import pathlib

# ---- 引用 Markpage 引擎（本文件位于 scripts/host/，引擎在 scripts/）----
_SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from md_site_builder import build_site  # noqa: E402

# 默认宿主包（开发机探测）：显式 --pkg / MARKPAGE_PKG > 已知开发机路径 > None
_DEFAULT_PKG = r"D:\Unity\Project\MicrobialNet\MicrobialNextUnityProj\Packages\com.microbialnet.story"

# 一览表别名：表格显示名 -> 模块页标题（模块标题即 ## 标题）。
# 整格文本 == 模块标题的直接命中无需列出；这里只补「显示名 ≠ 模块标题」的行。
DEFAULT_ALIAS = {
    "StoryView（TMP）": "StoryView（TMP 表现层，可选程序集）",
    "DialogueBoxManager（UI）": "DialogueBoxManager（UI 程序集）",
    "VariableDebugView（TMP）": "VariableDebugView",
    "StoryLineBoxView / StoryChoiceBoxView / StoryMessageBoxView（TMP）":
        "对话框盒子视图：StoryLineBoxView / StoryChoiceBoxView / StoryMessageBoxView",
    "StoryAssetLocator / ResourcesStoryAssetLocator":
        "StoryAssetLocator / ResourcesStoryAssetLocator / IStoryAssetLocator",
    "IStoryVariableProvider 等七条契约": "IStoryVariableProvider",
    "StoryGraphAsset 等数据资产": "StoryGraphAsset",
}


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="《组件 API 参考》多页站点生成器（Markpage 引擎直驱）")
    ap.add_argument("--pkg", help="宿主包根目录（默认推导 src/out 用；可被 --src/--out 覆盖）")
    ap.add_argument("--src", help="源 Markdown（默认 <pkg>/Documentation/组件API参考/组件API参考.md）")
    ap.add_argument("--out", help="输出目录（默认 <pkg>/Documentation/组件API参考/html）")
    ap.add_argument("--title", default="组件 API 参考（业务侧）", help="站点标题")
    ap.add_argument("--alias-json", help="可选 JSON：一览表显示名 -> 模块标题 映射，覆盖内置默认")
    ap.add_argument("--no-overview-links", action="store_true",
                    help="关闭总览表自动链接（默认开）")
    a = ap.parse_args(argv)

    pkg = a.pkg or __import__("os").environ.get("MARKPAGE_PKG") or ""
    if not a.src:
        base = pathlib.Path(pkg) if pkg else pathlib.Path(_DEFAULT_PKG)
        a.src = str(base / "Documentation" / "组件API参考" / "组件API参考.md")
    if not a.out:
        base = pathlib.Path(pkg) if pkg else pathlib.Path(_DEFAULT_PKG)
        a.out = str(base / "Documentation" / "组件API参考" / "html")
    return a


def main(argv=None) -> int:
    a = parse_args(argv)
    src = pathlib.Path(a.src)
    if not src.is_file():
        print(f"!! 找不到源文档: {src}")
        return 1
    alias = json.load(open(a.alias_json, encoding="utf-8")) if a.alias_json else DEFAULT_ALIAS
    opts = {"alias": alias}
    if not a.no_overview_links:
        opts["overview_links"] = True
    try:
        r = build_site(src, a.out, a.title, log=print, opts=opts)
    except Exception as e:  # noqa: BLE001
        import traceback
        print(f"!! 生成异常: {type(e).__name__}: {e}")
        traceback.print_exc(limit=6)
        return 1
    print(f"生成: {r['dir']} | 页面: {r['pages']} | 模块: {r['modules']} | "
          f"分组: {r['groups']} | 附录: {r['appendix']} | 索引: {r['index_kb']} KB | "
          f"资源: 拷贝 {r['assets_copied']} / 缺失 {r['assets_missing']} | "
          f"严格模式: {r['strict']} | 总览节: {r['overview_sections']} | 附录节: {r['appendix_sections']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
