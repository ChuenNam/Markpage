# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置：Markpage = 本地 Web 服务 + 生成核心，打成单文件夹独立 exe。
# 用法：<打包venv python> -m PyInstaller --noconfirm --clean --distpath <dist> --workpath <tmp> md_doc_gui.spec
# 产物：<dist>/Markpage/Markpage.exe（双击即用，目标电脑无需安装 Python）。
#
# 说明：
#   - 界面是 webapp/ui 下的静态文件，必须随包带上（onedir 的 _MEIPASS 根下 webapp/ui）；
#     漏带的表现是「窗口打开但白屏」—— 无头自检 --selftest 会直接断言这批文件可访问；
#   - GUI 已做「内嵌模式」：exe 内自带 markdown/pygments，直接线程内调用 build_site()；
#   - markdown 扩展是动态加载，必须显式 hiddenimports；
#   - pygments 词法器由官方 hook 收集，无需额外配置；
#   - pathex 基于 SPECPATH（spec 所在目录），仓库可整体移动，无需改路径。
#   - 2026-11 起界面迁到浏览器（本地 HTTP 服务），不再依赖 tkinter / tkinterdnd2。

import os

datas = [
    (os.path.join(SPECPATH, "webapp", "ui"), "webapp/ui"),
]

hiddenimports = [
    "md_site_builder",
    "doc_site_assets",
    "webapp",
    "webapp.server",
    "webapp.engine",
    "webapp.state",
    "webapp.lint",
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
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    # 程序图标（资源管理器/任务栏）；由 scripts/make_icon.py 从 ui/icon.svg 生成
    icon=os.path.join(SPECPATH, "webapp", "ui", "icon.ico"),
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
