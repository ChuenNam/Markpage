# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置：把 Markpage（GUI + 生成核心）打成单文件夹独立 exe。
# 用法：<打包venv python> -m PyInstaller --noconfirm --clean --distpath <dist> --workpath <tmp> md_doc_gui.spec
# 产物：<dist>/Markpage/Markpage.exe（双击即用，目标电脑无需安装 Python）。
# 说明：
#   - GUI 已做“内嵌模式”：exe 内自带 markdown/pygments，直接线程内调用 build_site()，
#     不再依赖任何外部 .py / venv；
#   - markdown 扩展是动态加载，必须显式 hiddenimports；
#   - pygments 词法器由官方 hook 收集，无需额外配置；
#   - pathex 基于 SPECPATH（spec 所在目录），仓库可整体移动，无需改路径。

#   - 拖放依赖 tkinterdnd2（可选）：collect_all 收集 tkdnd 原生库与 Tcl 资源；
#     打包环境未安装该包时为空 → 产物无拖放，GUI 自动降级为仅“浏览…”按钮。

try:
    from PyInstaller.utils.hooks import collect_all
    _dnd_datas, _dnd_bins, _dnd_hids = collect_all("tkinterdnd2")
except Exception:
    _dnd_datas, _dnd_bins, _dnd_hids = [], [], []

hiddenimports = [
    "md_site_builder",
    "doc_site_assets",
    # markdown 动态加载的扩展
    "markdown.extensions.tables",
    "markdown.extensions.fenced_code",
    "markdown.extensions.codehilite",
    "markdown.extensions.toc",
    "markdown.extensions.sane_lists",
    "markdown.extensions.attr_list",
    "markdown.extensions.extra",
]

a = Analysis(
    ["md_doc_gui.py"],
    pathex=[SPECPATH],
    binaries=_dnd_bins,
    datas=_dnd_datas,
    hiddenimports=hiddenimports + _dnd_hids,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["numpy", "PIL", "matplotlib", "pytest", "scipy", "pandas"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Markpage",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # 纯 GUI，无黑色控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Markpage",
)
