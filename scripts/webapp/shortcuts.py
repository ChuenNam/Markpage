# -*- coding: utf-8 -*-
"""目录浏览器的快捷入口（桌面 / 文档 / 下载 …）。

第一次运行时从注册表取「用户外壳文件夹」播种，写成 `quick_dirs.json`；
之后**一律以文件为准** —— 用户既可以点界面上的 +/−，也可以直接编辑这个文件。

为什么首次不直接拼 %USERPROFILE%\\Desktop：这些目录可能被 OneDrive 或组策略重定向，
只有注册表里 `User Shell Folders` 的值是准的（且值里可能带 %USERPROFILE% 需要展开）。

存放位置与 state.json 同目录（%LOCALAPPDATA%\\Markpage\\quick_dirs.json）。
"""
import json
import os

from .state import state_path

# (显示名, 注册表键名, 兜底目录名)
REG_NAMES = (
    ("桌面", "Desktop", "Desktop"),
    ("文档", "Personal", "Documents"),
    ("下载", "{374DE290-123F-4565-9164-39C4925E467B}", "Downloads"),
)


def shortcuts_path():
    return state_path().with_name("quick_dirs.json")


def _reg_folder(reg_name, fallback_name):
    home = os.path.expanduser("~")
    if os.name != "nt":
        return os.path.join(home, fallback_name)
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
            val, _ = winreg.QueryValueEx(k, reg_name)
        return os.path.expandvars(str(val)) or os.path.join(home, fallback_name)
    except (OSError, ImportError, ValueError, TypeError):
        return os.path.join(home, fallback_name)


def seed():
    """从注册表取初始入口。"""
    out, seen = [], set()
    for label, reg, fb in REG_NAMES:
        p = os.path.abspath(_reg_folder(reg, fb))
        key = p.rstrip("\\/").lower()
        if os.path.isdir(p) and key not in seen:
            seen.add(key)
            out.append({"name": label, "path": p})
    return out


def _clean(items):
    """归一化 + 去重（同一目录只留第一个），顺带补名字。"""
    out, seen = [], set()
    for it in items or []:
        if not isinstance(it, dict):
            continue
        path = str(it.get("path") or "").strip()
        if not path:
            continue
        key = path.rstrip("\\/").lower()
        if key in seen:
            continue
        seen.add(key)
        name = str(it.get("name") or "").strip()
        out.append({"name": name or os.path.basename(path.rstrip("\\/")) or path,
                    "path": path})
    return out


def load():
    """读文件；不存在则播种并落盘。文件坏了就退回内存播种，**不覆盖**原文件。"""
    p = shortcuts_path()
    if not p.is_file():
        items = seed()
        save(items)
        return items
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        raw = data.get("items") if isinstance(data, dict) else data
        return _clean(raw)
    except (OSError, ValueError):
        return seed()


def save(items):
    p = shortcuts_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": 1, "items": _clean(items)},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)
    except OSError:
        pass


def visible():
    """给界面用的：只留磁盘上真实存在的（网络盘暂时离线不会把配置删掉）。"""
    return [x for x in load() if os.path.isdir(x["path"])]


def add(path, name=""):
    """返回 (完整列表, 错误信息)。已存在时列表原样返回并给出提示。"""
    p = os.path.abspath((path or "").strip()) if path else ""
    if not p or not os.path.isdir(p):
        return load(), "这个目录不存在"
    items = load()
    key = p.rstrip("\\/").lower()
    if any(x["path"].rstrip("\\/").lower() == key for x in items):
        return items, "这个目录已经在快捷入口里了"
    label = (name or "").strip() or os.path.basename(p.rstrip("\\/")) or p
    items.append({"name": label, "path": p})
    save(items)
    return load(), ""


def remove(path):
    key = os.path.abspath((path or "").strip()).rstrip("\\/").lower()
    items = [x for x in load() if x["path"].rstrip("\\/").lower() != key]
    save(items)
    return load()
