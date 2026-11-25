# -*- coding: utf-8 -*-
"""生成 webapp/ui/icon.ico（16/32/48/64/128/256）。

做法：用 Edge 无头把 icon.svg **按目标尺寸原生渲染**成 PNG（矢量缩放，小尺寸不糊），
再手工打包成 ICO。ICO 结构就是「6 字节文件头 + N 个 16 字节目录项 + 数据」，
条目用 PNG 编码（Vista 起支持），所以不需要 Pillow 之类的依赖。

用法：python scripts/make_icon.py
依赖：本机有 Edge/Chrome；无需网络。
"""
import os
import pathlib
import struct
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "webapp"))

SVG = HERE / "webapp" / "ui" / "icon.svg"
ICO = HERE / "webapp" / "ui" / "icon.ico"
SIZES = (16, 32, 48, 64, 128, 256)

PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;padding:0;background:transparent}}
img{{display:block;width:{s}px;height:{s}px}}
</style></head><body><img src="{src}"></body></html>"""


def find_browser():
    import md_doc_gui as gui            # 复用界面启动时的查找逻辑，避免两处漂移
    return gui.find_edge()


def render(browser, size, workdir):
    """按 size 渲染一张 PNG，返回字节。"""
    page = workdir / f"icon-{size}.html"
    png = workdir / f"icon-{size}.png"
    page.write_text(PAGE.format(s=size, src=SVG.as_uri()), encoding="utf-8")
    cmd = [
        browser, "--headless=new", "--disable-gpu", "--no-first-run",
        "--hide-scrollbars",
        f"--user-data-dir={workdir / ('profile-' + str(size))}",
        f"--window-size={size},{size}",
        "--default-background-color=00000000",      # 透明底，圆角外是镂空
        "--virtual-time-budget=1200",
        f"--screenshot={png}",
        page.as_uri(),
    ]
    subprocess.run(cmd, capture_output=True, timeout=120)
    if not png.is_file():
        raise RuntimeError(f"{size}px 渲染失败")
    return png.read_bytes()


def write_ico(entries, out):
    """entries: [(size, png_bytes)] → 写 ICO。"""
    n = len(entries)
    header = struct.pack("<HHH", 0, 1, n)          # reserved, type=icon, count
    offset = 6 + 16 * n
    dirs, blobs = b"", b""
    for size, blob in entries:
        dim = 0 if size >= 256 else size            # 256 在 ICO 里记作 0
        dirs += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
        blobs += blob
    out.write_bytes(header + dirs + blobs)


def main():
    if not SVG.is_file():
        print("找不到", SVG)
        return 1
    browser = find_browser()
    print("浏览器:", browser)
    with tempfile.TemporaryDirectory(prefix="markpage-ico-") as td:
        work = pathlib.Path(td)
        entries = []
        for s in SIZES:
            blob = render(browser, s, work)
            entries.append((s, blob))
            print(f"  {s:>3}px  {len(blob)/1024:.1f} KB")
        write_ico(entries, ICO)
    print(f"写出 {ICO}（{ICO.stat().st_size/1024:.1f} KB，{len(SIZES)} 个尺寸）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
