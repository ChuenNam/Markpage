# -*- coding: utf-8 -*-
"""打包收尾（纯 Python，避免 .bat 非 ASCII 在 GBK 代码页乱码）：
把 PyInstaller 产物 dist/Markpage 组装为 releases/Markpage/ 并生成 zip。
用法：python scripts/assemble_release.py（仓库根为基准）
"""
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent   # scripts/ 的上一级 = 仓库根
STAGE = ROOT / "dist" / "Markpage"
REL = ROOT / "releases" / "Markpage"


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
    zpath = ROOT / "releases" / "Markpage.zip"
    if zpath.exists():
        zpath.unlink()
    shutil.make_archive(
        str(ROOT / "releases" / "Markpage"), "zip",
        root_dir=ROOT / "releases", base_dir="Markpage")
    print("OK 文件夹:", REL)
    print("OK zip   :", zpath)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
