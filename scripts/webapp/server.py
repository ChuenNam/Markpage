# -*- coding: utf-8 -*-
"""Markpage 本地 Web 服务 —— 界面后端（纯标准库，无第三方依赖）。

托管 webapp/ui 下的静态界面，并把浏览器上的操作翻译成对生成引擎的调用。

安全边界（本地工具，但仍然当成公网服务来写）：
  - 只绑定 127.0.0.1，不监听外网；
  - 所有请求路径形如 /s/<一次性随机 token>/...，token 由启动时生成并只写在
    打开的 URL 里 —— 别的网页猜不到，天然挡住跨站调用与 DNS rebinding；
  - 所有文件访问都过 _safe_join，限制在明确登记的根目录（界面资源 / 预览临时
    目录 / 当前输出目录）内，杜绝 .. 穿越。

接口一览（均为 JSON，构建与状态为流/轮询）：
  GET  /api/env                  环境与状态快照
  GET  /api/browse?path=&mode=   目录浏览（mode=file 只看目录+md，mode=dir 只看目录）
  POST /api/md/read              读源 md
  POST /api/md/write             保存（带 mtime 冲突检测）
  POST /api/preview              用编辑缓冲区渲染到临时目录，返回页面清单
  POST /api/build                SSE 流式构建（log / stats / error / done 事件）
  POST /api/cancel               取消正在进行的构建
  POST /api/open                 打开站点 / 输出目录 / 文件
  GET  /api/state  POST          界面状态（最近文件、按文档记忆的选项）
  POST /api/ping                 心跳（页面关闭后服务端自动退出，见 launcher）
  POST /api/reset-data           清理本机保存的数据（需 confirm）
"""
import json
import mimetypes
import os
import pathlib
import re
import shutil
import sys
import tempfile
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import shortcuts as shortcuts_store
from .lint import lint as run_lint
from .state import state_path

MIME = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
    ".map": "application/json; charset=utf-8",
}


def clear_saved_data(ctx):
    """清理缓存按钮：删掉本机持久数据，返回被处理的文件名。

    运行锁 instance.json 不算用户数据，清完立刻按当前实例重写，
    否则单实例保护会失效。日志文件被当前进程打开，Windows 下删不掉，改为清空。
    """
    base = pathlib.Path(state_path()).parent
    touched = []
    if base.is_dir():
        for p in sorted(base.iterdir()):
            if not p.is_file() or p.name == "instance.json":
                continue
            try:
                if p.name == "markpage.log":
                    p.write_text("", encoding="utf-8")
                else:
                    p.unlink()
                touched.append(p.name)
            except OSError:
                pass
    ctx.state.reset()
    try:
        (base / "instance.json").write_text(
            json.dumps({"pid": os.getpid(), "url": ctx.url(),
                        "started": time.time(), "exe": sys.executable},
                       ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    # 只清其它会话遗留的临时预览目录，当前正在用的不动
    try:
        cur = pathlib.Path(ctx.preview_dir).resolve()
        for p in pathlib.Path(tempfile.gettempdir()).glob("markpage-prev-*"):
            if p.is_dir() and p.resolve() != cur:
                shutil.rmtree(p, ignore_errors=True)
    except OSError:
        pass
    return touched


# ---------- 站点选项文本解析（与 CLI 语法一致，校验失败给中文提示） ----------
def parse_route_text(text):
    route = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "//")):
            continue
        k, sep, role = line.rpartition("=")
        if not sep or role.strip() not in ("overview", "appendix"):
            raise ValueError(f"栏目规则行应形如 `标题=overview|appendix` 或 `前缀*=…`，收到：{line!r}")
        k = k.strip()
        if k.endswith("*"):
            route.append({"title": k[:-1].strip(), "role": role.strip(), "match": "prefix"})
        else:
            route.append({"title": k, "role": role.strip(), "match": "exact"})
    return route


def parse_alias_text(text):
    alias = {}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "//")):
            continue
        cell, sep, mtitle = line.partition("=")
        if not sep or not mtitle.strip():
            raise ValueError(f"别名行应形如 `表格显示名=模块标题`，收到：{line!r}")
        alias[cell.strip()] = mtitle.strip()
    return alias


def opts_from_body(raw):
    """界面提交的选项 → build_site(opts=…) 需要的结构。

    界面走图形化之后，大量场景直接给结构化数据（alias 字典 / route 列表）；
    文本规则仍保留作为「高级」入口，两条路都认，结构化优先。"""
    raw = raw or {}
    out = {}
    if raw.get("overview_links"):
        out["overview_links"] = True
    if raw.get("group_pages"):
        out["group_pages"] = True

    route = raw.get("route")
    if isinstance(route, list) and route:
        rows = []
        for r in route:
            if not isinstance(r, dict):
                continue
            title = str(r.get("title") or "").strip()
            role = str(r.get("role") or "").strip()
            if title and role in ("overview", "appendix"):
                rows.append({"title": title, "role": role,
                             "match": "prefix" if r.get("match") == "prefix" else "exact"})
        if rows:
            out["route"] = rows
    if "route" not in out and (raw.get("route_text") or "").strip():
        out["route"] = parse_route_text(raw["route_text"])

    alias = raw.get("alias")
    if isinstance(alias, dict) and alias:
        pairs = {}
        for k, v in alias.items():
            k, v = str(k).strip(), str(v).strip()
            if k and v:
                pairs[k] = v
        if pairs:
            out["alias"] = pairs
    if "alias" not in out and (raw.get("alias_text") or "").strip():
        out["alias"] = parse_alias_text(raw["alias_text"])
    return out


def _safe_join(root, rel):
    """把 rel 拼到 root 下并校验没有越界；越界返回 None。"""
    if not root:
        return None
    root_abs = os.path.realpath(root)
    p = os.path.realpath(os.path.join(root_abs, rel or ""))
    if p == root_abs or p.startswith(root_abs + os.sep):
        return p
    return None


def _shell_folder(reg_name, fallback):
    """取用户外壳文件夹（桌面/文档/下载）的真实路径。

    走注册表而不是直接拼 %USERPROFILE%\\Desktop：这些目录可能被 OneDrive 或
    组策略重定向，只有注册表里的值是准的（值里可能含 %USERPROFILE% 这类环境变量）。"""
    if os.name != "nt":
        return fallback
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\User Shell Folders") as k:
            val, _ = winreg.QueryValueEx(k, reg_name)
        path = os.path.expandvars(str(val))
        return path if os.path.isdir(path) else fallback
    except (OSError, ImportError, ValueError, TypeError):
        return fallback


def quick_dirs():
    """目录浏览器的快捷入口。只返回真实存在的，避免点了没反应。"""
    home = os.path.expanduser("~")
    cand = [
        ("桌面", _shell_folder("Desktop", os.path.join(home, "Desktop"))),
        ("文档", _shell_folder("Personal", os.path.join(home, "Documents"))),
        ("下载", _shell_folder("{374DE290-123F-4565-9164-39C4925E467B}",
                            os.path.join(home, "Downloads"))),
    ]
    seen, out = set(), []
    for label, path in cand:
        path = os.path.abspath(path) if path else ""
        if path and os.path.isdir(path) and path.lower() not in seen:
            seen.add(path.lower())
            out.append({"name": label, "path": path})
    return out


def _md_title(text):
    for line in (text or "").splitlines():
        s = line.strip()
        if s.startswith("# "):
            return re.sub(r"[`*_]", "", s[2:]).strip()
    return ""


def write_md(path, text):
    """写回源文档，**保留原文件的换行风格**。

    编辑器里一律是 \\n；如果原文件是 CRLF（Windows 上很常见），直接按 \\n 写回会把
   整篇文件的换行都改掉 —— 用户在 git 里看到的是「整文件重写」的 diff。
    """
    nl = "\n"
    try:
        head = pathlib.Path(path).read_bytes()[:8192]
        if b"\r\n" in head:
            nl = "\r\n"
    except OSError:
        pass
    body = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    with open(path, "w", encoding="utf-8", newline=nl) as f:
        f.write(body)


class Ctx:
    def __init__(self, tool_root, ui_dir, engine, state, preview_dir):
        self.tool_root = tool_root
        self.ui_dir = ui_dir
        self.engine = engine
        self.state = state
        self.preview_dir = preview_dir
        self.out_dir = None
        self.token = ""
        self.port = 0
        self.stamp = 0
        self.preview_lock = threading.Lock()
        self.build_lock = threading.Lock()
        self.cancel_event = None
        self.last_ping = time.time()
        self.close_requested_at = 0.0   # 页面 pagehide 主动告别；刷新后 ping 会清掉
        self.started = time.time()

    def default_out(self, md_path):
        """界面没给输出目录时的兜底：md 同级的 site 子目录
        （对应「输出位置 = 当前 md 所在目录」+「生成到子目录 site」）。"""
        return os.path.join(os.path.dirname(md_path), "site")

    def url(self, *parts):
        return f"http://127.0.0.1:{self.port}/s/{self.token}/" + "/".join(parts)


def _make_handler(ctx):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Markpage"
        sys_version = ""

        def log_message(self, fmt, *args):      # 静音：访问日志没有价值，还会刷屏
            pass

        # ---------- 响应助手 ----------
        def _json(self, obj, code=200):
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _err(self, msg, code=400):
            self._json({"ok": False, "error": msg}, code)

        def _send_file(self, path):
            if not path or not os.path.isfile(path):
                self._err("未找到文件: " + str(path), 404)
                return
            ext = os.path.splitext(path)[1].lower()
            ctype = MIME.get(ext) or mimetypes.guess_type(path)[0] or "application/octet-stream"
            try:
                data = pathlib.Path(path).read_bytes()
            except OSError as e:
                self._err(f"读取失败: {e}", 500)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        # ---------- 请求体 ----------
        def _body(self):
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = 0
            if n <= 0:
                return {}
            raw = self.rfile.read(n)
            try:
                return json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return {}

        # ---------- 路由 ----------
        def _parts(self):
            u = urllib.parse.urlsplit(self.path)
            # 必须逐段解码：模块页文件名保留中文，浏览器会把它们编码成 %E5%A4%9A…
            segs = [urllib.parse.unquote(s) for s in u.path.split("/") if s]
            return segs, urllib.parse.parse_qs(u.query)

        def _authorized(self, segs):
            if len(segs) < 2 or segs[0] != "s" or segs[1] != ctx.token:
                return None
            return segs[2:]

        def do_GET(self):
            segs, q = self._parts()
            rest = self._authorized(segs)
            if rest is None:
                # 根路径（或 token 不对）统一引导到带 token 的入口；不泄露 token
                self.send_response(302)
                self.send_header("Location", f"/s/{ctx.token}/")
                self.end_headers()
                return
            if not rest or rest == [""]:
                ctx.last_ping = time.time()
                return self._send_file(os.path.join(ctx.ui_dir, "index.html"))
            head = rest[0]
            if head == "static":
                return self._send_file(_safe_join(ctx.ui_dir, "/".join(rest[1:])))
            if head == "preview":
                return self._send_file(_safe_join(ctx.preview_dir, "/".join(rest[1:])))
            if head == "out":
                return self._send_file(_safe_join(ctx.out_dir, "/".join(rest[1:])))
            if head == "api":
                return self._api_get("/".join(rest[1:]), q)
            self._err("未知路径", 404)

        def do_POST(self):
            segs, _q = self._parts()
            rest = self._authorized(segs)
            if rest is None:
                return self._err("无效入口", 403)
            if rest and rest[0] == "api":
                body = self._body()
                return self._api_post("/".join(rest[1:]), body)
            self._err("未知路径", 404)

        # ---------- GET 接口 ----------
        def _api_get(self, name, q):
            if name == "env":
                return self._json({
                    "ok": True,
                    "engine": ctx.engine.info(),
                    "state": ctx.state.snapshot(),
                    "preview_base": f"/s/{ctx.token}/preview/",
                    "out_base": f"/s/{ctx.token}/out/",
                    "out_dir": ctx.out_dir,
                    "home": os.path.expanduser("~"),
                    "sep": os.sep,
                    "is_win": os.name == "nt",
                    "tool_root": ctx.tool_root,
                })
            if name == "browse":
                path = (q.get("path") or [""])[0]
                mode = (q.get("mode") or ["file"])[0]
                return self._json(self._browse(path, mode))
            if name == "state":
                return self._json({"ok": True, "state": ctx.state.snapshot()})
            self._err("未知接口: " + name, 404)

        def _browse(self, path, mode):
            home = os.path.expanduser("~")
            p = path or ctx.state.data.get("last_dir") or home
            p = os.path.abspath(os.path.expandvars(p)) if p else home
            if not os.path.isdir(p):
                p = home
            drives = []
            if os.name == "nt":
                drives = [f"{c}:\\" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(f"{c}:\\")]
            entries = []
            try:
                for name in os.listdir(p):
                    if name.startswith("."):
                        continue
                    fp = os.path.join(p, name)
                    try:
                        isdir = os.path.isdir(fp)
                        st = os.stat(fp)
                    except OSError:
                        continue
                    if not isdir:
                        if mode == "dir":
                            continue
                        if not name.lower().endswith((".md", ".markdown")):
                            continue
                    entries.append({"name": name, "path": fp, "dir": isdir,
                                    "size": st.st_size, "mtime": int(st.st_mtime)})
            except PermissionError:
                return {"ok": False, "error": "没有权限读取该目录", "path": p,
                        "parent": None, "drives": drives, "entries": []}
            entries.sort(key=lambda e: (not e["dir"], e["name"].casefold()))
            parent = os.path.dirname(p.rstrip("\\/")) or None
            if parent and not os.path.isdir(parent):
                parent = None
            return {"ok": True, "path": p, "parent": parent, "drives": drives,
                    "quick": shortcuts_store.visible(), "entries": entries}

        # ---------- POST 接口 ----------
        def _api_post(self, name, body):
            try:
                if name == "md/read":
                    return self._md_read(body)
                if name == "md/write":
                    return self._md_write(body)
                if name == "preview":
                    return self._preview(body)
                if name == "build":
                    return self._build(body)
                if name == "cancel":
                    if ctx.cancel_event is not None:
                        ctx.cancel_event.set()
                    return self._json({"ok": True})
                if name == "open":
                    return self._open(body)
                if name == "shortcuts/add":
                    return self._shortcuts_add(body)
                if name == "shortcuts/remove":
                    return self._shortcuts_remove(body)
                if name == "lint":
                    return self._lint(body)
                if name == "zip":
                    return self._zip(body)
                if name == "clean":
                    return self._clean(body)
                if name == "state":
                    return self._json({"ok": True, "state": ctx.state.patch(body or {})})
                if name == "ping":
                    ctx.last_ping = time.time()
                    ctx.close_requested_at = 0.0   # 刷新/重新打开：取消待退出
                    return self._json({"ok": True})
                if name == "bye":
                    # 页面 pagehide（关窗）时由 sendBeacon 告知；不立即 shutdown，
                    # 留 5 秒给刷新后的新页面 ping 取消，避免误杀。
                    ctx.close_requested_at = time.time()
                    return self._json({"ok": True})
                if name == "remember":
                    ctx.state.remember(body.get("path") or "", body.get("project"))
                    return self._json({"ok": True, "state": ctx.state.snapshot()})
                if name == "reset-data":
                    if not body.get("confirm"):
                        return self._json({"ok": False, "error": "需要确认才能清理缓存"})
                    return self._json({"ok": True, "removed": clear_saved_data(ctx)})
            except ValueError as e:
                return self._json({"ok": False, "error": str(e)})
            except Exception as e:                       # noqa: BLE001
                import traceback
                traceback.print_exc()
                return self._json({"ok": False, "error": f"{type(e).__name__}: {e}"}, 500)
            self._err("未知接口: " + name, 404)

        # ---------- 具体接口实现 ----------
        def _md_read(self, body):
            p = body.get("path") or ""
            if not p or not os.path.isfile(p):
                return self._json({"ok": False, "error": "文件不存在: " + p})
            try:
                text = pathlib.Path(p).read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = pathlib.Path(p).read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                return self._json({"ok": False, "error": f"读取失败: {e}"})
            st = os.stat(p)
            return self._json({"ok": True, "path": p, "text": text,
                               "mtime": st.st_mtime, "size": st.st_size,
                               "title": _md_title(text),
                               "project": ctx.state.project(p)})

        def _md_write(self, body):
            p = body.get("path") or ""
            text = body.get("text")
            if not p:
                return self._json({"ok": False, "error": "没有指定文件"})
            if text is None:
                return self._json({"ok": False, "error": "没有内容"})
            if os.path.isfile(p) and body.get("mtime"):
                try:
                    disk = os.stat(p).st_mtime
                    if abs(disk - float(body["mtime"])) > 1.0:
                        return self._json({"ok": False, "conflict": True, "mtime": disk,
                                           "error": "磁盘上的文件已被外部修改"}, 409)
                except (OSError, TypeError, ValueError):
                    pass
            pathlib.Path(p).parent.mkdir(parents=True, exist_ok=True)
            write_md(p, text)
            return self._json({"ok": True, "mtime": os.stat(p).st_mtime})

        def _resolve(self, body):
            """校验源与输出，返回 (md_path, out_dir, title, opts, text)。"""
            md = (body.get("path") or "").strip().strip('"')
            if not md or not os.path.isfile(md):
                raise ValueError("请先选择一个存在的 Markdown 文件")
            md = os.path.abspath(md)          # 统一分隔符与大小写，状态记忆才不会分裂成两条
            out = (body.get("out") or "").strip().strip('"') or ctx.default_out(md)
            out = os.path.abspath(out)
            title = (body.get("title") or "").strip()
            opts = opts_from_body(body.get("opts"))
            return md, out, title, opts, body.get("text")

        def _preview(self, body):
            md, _out, title, opts, text = self._resolve(body)
            if text is None:
                text = pathlib.Path(md).read_text(encoding="utf-8", errors="replace")
            t0 = time.time()
            with ctx.preview_lock:
                stats = None
                err = None
                for kind, payload in ctx.engine.build(md, ctx.preview_dir, title, opts, text, None):
                    if kind == "stats":
                        stats = payload
                    elif kind == "error":
                        err = payload
                    elif kind == "trace":
                        pass
            if err:
                return self._json({"ok": False, "error": err})
            if not stats:
                return self._json({"ok": False, "error": "预览未产出结果"})
            ctx.stamp += 1
            return self._json({"ok": True, "stamp": ctx.stamp,
                               "pages": stats.get("page_list") or [],
                               "stats": _slim(stats),
                               "ms": int((time.time() - t0) * 1000)})

        def _build(self, body):
            md, out, title, opts, text = self._resolve(body)
            if not ctx.build_lock.acquire(blocking=False):
                return self._json({"ok": False, "error": "已有构建在进行中"}, 409)
            ctx.cancel_event = threading.Event()
            try:
                if body.get("save") and text is not None:
                    write_md(md, text)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                self._emit({"t": "start", "path": md, "out": out})
                stats, err, cancelled = None, None, False
                t0 = time.time()
                for kind, payload in ctx.engine.build(md, out, title, opts, text=None,
                                                      cancel=ctx.cancel_event):
                    if kind == "log":
                        self._emit({"t": "log", "m": payload})
                    elif kind == "stats":
                        stats = payload
                    elif kind == "error":
                        err = payload
                        self._emit({"t": "log", "m": "!! " + payload})
                    elif kind == "trace":
                        self._emit({"t": "log", "m": payload})
                    elif kind == "cancelled":
                        cancelled = True
                        self._emit({"t": "log", "m": "!! 已取消"})
                ok = bool(stats) and not err and not cancelled
                if ok:
                    ctx.out_dir = out
                    ctx.state.remember(md, {
                        "out": out, "title": title,
                        "opts": body.get("opts") or {},
                        # 输出位置的三段信息：父目录 / 是否套子目录 / 子目录名
                        "out_base": body.get("out_base") or "",
                        "subdir": body.get("subdir"),
                        "subdir_name": body.get("subdir_name") or "",
                    })
                self._emit({"t": "done", "ok": ok, "cancelled": cancelled,
                            "error": err, "stats": _slim(stats) if stats else None,
                            "pages": (stats or {}).get("page_list") or [],
                            "out": out, "mtime": _mtime_or_zero(md),
                            "ms": int((time.time() - t0) * 1000)})
            finally:
                ctx.cancel_event = None
                ctx.build_lock.release()

        def _emit(self, obj):
            try:
                self.wfile.write(("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode("utf-8"))
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ValueError):
                pass

        def _open(self, body):
            what = body.get("what") or "site"
            if what == "site":
                out = ctx.out_dir
                if not out or not os.path.isfile(os.path.join(out, "index.html")):
                    return self._json({"ok": False, "error": "还没有生成站点"})
                page = body.get("page") or "index.html"
                url = ctx.url("out", urllib.parse.quote(page))   # 模块页文件名含中文
                webbrowser.open(url)
                return self._json({"ok": True, "url": url})
            if what == "dir":
                target = (body.get("path") or ctx.out_dir or "").strip()
                if not target or not os.path.isdir(target):
                    return self._json({"ok": False, "error": "目录不存在"})
                try:
                    os.startfile(target)          # noqa: S606  (Windows)
                except AttributeError:
                    webbrowser.open("file:///" + target.replace("\\", "/"))
                except OSError as e:
                    return self._json({"ok": False, "error": f"打开失败: {e}"})
                return self._json({"ok": True})
            return self._json({"ok": False, "error": "未知目标"})

        def _shortcuts_add(self, body):
            items, err = shortcuts_store.add(body.get("path") or "", body.get("name") or "")
            return self._json({"ok": True, "quick": [x for x in items
                                                     if os.path.isdir(x["path"])],
                               "added": not err, "message": err})

        def _shortcuts_remove(self, body):
            items = shortcuts_store.remove(body.get("path") or "")
            return self._json({"ok": True, "quick": [x for x in items
                                                     if os.path.isdir(x["path"])]})

        def _lint(self, body):
            md = (body.get("path") or "").strip().strip('"')
            if not md or not os.path.isfile(md):
                return self._json({"ok": False, "error": "请先选择一个存在的 Markdown 文件"})
            md = os.path.abspath(md)
            text = body.get("text")
            if text is None:
                text = pathlib.Path(md).read_text(encoding="utf-8", errors="replace")
            return self._json(run_lint(md, text, opts_from_body(body.get("opts"))))

        def _zip(self, body):
            out = ctx.out_dir
            if not out or not os.path.isdir(out):
                return self._json({"ok": False, "error": "还没有生成站点"})
            out = os.path.abspath(out).rstrip("\\/")
            parent, name = os.path.split(out)
            if not parent or not name:
                return self._json({"ok": False, "error": "输出目录的位置不支持打包"})
            try:
                arc = shutil.make_archive(os.path.join(parent, name), "zip",
                                          root_dir=parent, base_dir=name)
            except (OSError, ValueError) as e:
                return self._json({"ok": False, "error": f"打包失败: {e}"})
            return self._json({"ok": True, "path": arc,
                               "size": os.path.getsize(arc) if os.path.isfile(arc) else 0})

        def _clean(self, body):
            """只删本站自己产出的东西（*.html / site.css / site.js / search-index.js / assets/），
            目录里其他文件一律保留 —— 与 build_site 的清理口径一致。"""
            if not body.get("confirm"):
                return self._json({"ok": False, "error": "需要确认后才会清理"})
            out = ctx.out_dir
            if not out or not os.path.isdir(out):
                return self._json({"ok": False, "error": "还没有生成站点"})
            d = pathlib.Path(out)
            removed = 0
            for f in d.glob("*.html"):
                try:
                    f.unlink()
                    removed += 1
                except OSError:
                    pass
            for name in ("site.css", "site.js", "search-index.js"):
                p = d / name
                if p.is_file():
                    try:
                        p.unlink()
                        removed += 1
                    except OSError:
                        pass
            if (d / "assets").is_dir():
                try:
                    shutil.rmtree(d / "assets")
                    removed += 1
                except OSError:
                    pass
            return self._json({"ok": True, "removed": removed, "dir": str(d)})

    return Handler


def _mtime_or_zero(path):
    try:
        return os.stat(path).st_mtime
    except OSError:
        return 0


def _slim(stats):
    """只把界面要展示的字段回传，避免把整份 page_list 塞进两处。"""
    if not stats:
        return None
    keys = ("dir", "pages", "modules", "groups", "appendix", "title", "index_kb",
            "assets_copied", "assets_missing", "strict",
            "overview_sections", "appendix_sections")
    return {k: stats.get(k) for k in keys if k in stats}


def create_server(engine, state, ui_dir, tool_root, preview_dir, port=0):
    ctx = Ctx(tool_root, ui_dir, engine, state, preview_dir)
    ctx.token = _new_token()
    handler = _make_handler(ctx)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    httpd.daemon_threads = True
    ctx.port = httpd.server_address[1]
    return ctx, httpd


def _new_token():
    import secrets
    return secrets.token_urlsafe(16).replace("-", "").replace("_", "")
