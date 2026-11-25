# -*- coding: utf-8 -*-
"""界面状态持久化：最近文件 + 按 md 路径记忆的选项。

存放位置：%LOCALAPPDATA%\\Markpage\\state.json（Windows），其他平台退到 ~/.markpage。
写盘采用「临时文件 + 原子替换」，避免中途崩溃留下半截 JSON 把界面卡死。
"""
import json
import os
import pathlib
import tempfile
import time

MAX_RECENT = 12


def state_path():
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_STATE_HOME")
    if base:
        d = pathlib.Path(base) / "Markpage"
    else:
        d = pathlib.Path.home() / ".markpage"
    return d / "state.json"


class State:
    def __init__(self, path=None):
        self.path = pathlib.Path(path) if path else state_path()
        self.data = self._load()

    # ---------- 读写 ----------
    def _blank(self):
        return {"version": 1, "last_path": "", "last_dir": os.path.expanduser("~"),
                "recent": [], "projects": {}}

    def _load(self):
        try:
            raw = self.path.read_text(encoding="utf-8")
            d = json.loads(raw)
            if not isinstance(d, dict):
                raise ValueError("state 不是对象")
        except (OSError, ValueError):
            return self._blank()
        base = self._blank()
        base.update({k: d.get(k, base[k]) for k in base})
        if not isinstance(base["recent"], list):
            base["recent"] = []
        if not isinstance(base["projects"], dict):
            base["projects"] = {}
        return base

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except OSError:
            pass   # 状态存不下来不该影响生成

    # ---------- 查询 ----------
    def snapshot(self):
        rec = [r for r in self.data["recent"] if os.path.isfile(r.get("path", ""))]
        return {"last_path": self.data["last_path"], "last_dir": self.data["last_dir"],
                "recent": rec, "projects": self.data["projects"]}

    def project(self, md_path):
        """取某份 md 上次的界面选项。键按 normcase 归一，路径写法变了也能命中。"""
        if not md_path:
            return {}
        key = os.path.normcase(os.path.abspath(md_path))
        got = self.data["projects"].get(key)
        if got is None:
            got = self.data["projects"].get(md_path, {})
        return got

    # ---------- 更新 ----------
    def patch(self, patch):
        for k in ("last_path", "last_dir"):
            if isinstance(patch.get(k), str) and patch[k]:
                self.data[k] = patch[k]
        self.save()
        return self.snapshot()

    def remember(self, md_path, project=None):
        """记一条最近文件 + 该文档的界面选项。"""
        if not md_path:
            return
        key = os.path.normcase(os.path.abspath(md_path))
        self.data["last_path"] = md_path
        self.data["last_dir"] = os.path.dirname(md_path) or self.data["last_dir"]
        if project is not None:
            self.data["projects"][key] = dict(project, ts=int(time.time()))
            # 只保留最近 200 份文档的选项，防止无限增长
            if len(self.data["projects"]) > 200:
                oldest = sorted(self.data["projects"].items(),
                                key=lambda kv: kv[1].get("ts", 0))[:len(self.data["projects"]) - 200]
                for k, _ in oldest:
                    self.data["projects"].pop(k, None)
        recent = [r for r in self.data["recent"]
                  if os.path.normcase(os.path.abspath(r.get("path", ""))) != key]
        recent.insert(0, {"path": md_path, "name": os.path.basename(md_path),
                          "dir": os.path.dirname(md_path), "ts": int(time.time())})
        self.data["recent"] = recent[:MAX_RECENT]
        self.save()
