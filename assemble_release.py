# -*- coding: utf-8 -*-
"""打包收尾（纯 Python，避免 .bat 非 ASCII 在 GBK 代码页乱码）：
把 PyInstaller 产物 dist/DocSiteTool 组装为 releases/MD文档站生成器/ 并生成 zip。
用法：python assemble_release.py
"""
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent
STAGE = ROOT / "dist" / "DocSiteTool"
REL = ROOT / "releases" / "MD文档站生成器"


def main() -> int:
    if not STAGE.is_dir():
        print("!! 未找到 PyInstaller 产物:", STAGE)
        return 1
    if REL.exists():
        shutil.rmtree(REL)
    shutil.copytree(STAGE, REL)
    usage = ROOT / "pack_usage_说明.txt"
    if usage.is_file():
        shutil.copy2(usage, REL / "使用说明.txt")
    zpath = ROOT / "releases" / "MD文档站生成器.zip"
    if zpath.exists():
        zpath.unlink()
    shutil.make_archive(
        str(ROOT / "releases" / "MD文档站生成器"), "zip",
        root_dir=ROOT / "releases", base_dir="MD文档站生成器")
    print("OK 文件夹:", REL)
    print("OK zip   :", zpath)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
