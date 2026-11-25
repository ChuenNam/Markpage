# -*- coding: utf-8 -*-
"""Markpage 启动器 —— 起一个本地 Web 服务，然后用浏览器窗口承载界面。

界面本身是 webapp/ui 下的静态页（HTML/CSS/JS），生成核心仍是 md_site_builder.py。
这样换来的关键能力：真·实时预览（iframe 直接加载渲染结果）、产物可点开、
编辑/结构/日志同时可见 —— 都是 tkinter 时代给不了的。

两种打开方式：
  ① 默认 `msedge --app=URL`：无地址栏、无标签页的独立窗口，观感就是桌面应用；
     Windows 10/11 自带 Edge，零新依赖；
  ② 没装 Edge（或 --browser default）→ 退回系统默认浏览器开一个标签页。

用法：
  python md_doc_gui.py                  :: 双击 .bat 即此
  python md_doc_gui.py 某文档.md         :: 启动后直接打开该文档
  python md_doc_gui.py --no-exit        :: 页面关掉也不退出进程
  python md_doc_gui.py --selftest a.md out
"""
import argparse
import atexit
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser

TOOLS = os.path.dirname(os.path.abspath(__file__))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from webapp.engine import Engine, quiet_kwargs   # noqa: E402
from webapp.server import create_server     # noqa: E402
from webapp.state import State              # noqa: E402

EDGE_CANDIDATES = [
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe",
]


# ---------- 路径 ----------
def resource_root():
    """打包后在 _MEIPASS（onedir 即 exe 同级），源码运行即 scripts/。"""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    return TOOLS


def ui_dir():
    return os.path.join(resource_root(), "webapp", "ui")


def _stderr_to_log():
    """PyInstaller windowed 模式下 stdout/stderr 为 None，print 会炸 —— 落到日志文件。"""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
        d = pathlib.Path(base) / "Markpage"
        d.mkdir(parents=True, exist_ok=True)
        f = open(d / "markpage.log", "a", encoding="utf-8", buffering=1)
    except OSError:
        class _Sink:
            def write(self, *_a):
                pass

            def flush(self):
                pass
        f = _Sink()
    sys.stdout = sys.stdout or f
    sys.stderr = sys.stderr or f


# ---------- 打开窗口 ----------
def find_edge():
    for c in EDGE_CANDIDATES:
        p = os.path.expandvars(c)
        if os.path.isfile(p):
            return p
    return shutil.which("msedge")


def open_app_window(url, prefer="edge"):
    """优先 Edge 应用窗口（无地址栏的独立窗口），失败退回默认浏览器。"""
    if prefer == "edge":
        exe = find_edge()
        if exe:
            try:
                subprocess.Popen([exe, f"--app={url}", "--window-size=1380,900"],
                                 close_fds=True, stdin=subprocess.DEVNULL,
                                 **quiet_kwargs())
                return "edge"
            except OSError:
                pass
    webbrowser.open(url)
    return "browser"


# ---------- 服务 ----------
def start_server(port=0):
    engine = Engine(TOOLS)
    state = State()
    preview = tempfile.mkdtemp(prefix="markpage-prev-")
    atexit.register(lambda: shutil.rmtree(preview, ignore_errors=True))
    ctx, httpd = create_server(engine, state, ui_dir(), resource_root(), preview, port)
    return ctx, httpd, engine


def start_watchdog(ctx, httpd, idle=180.0, grace=90.0):
    """页面关掉后自动退出：界面每 5s 一次心跳，长时间没有心跳就收摊。

    idle 取 180s 而不是 45s —— 浏览器会把后台标签页的定时器节流到每分钟一次，
    阈值太靠近就会把正在用的服务误杀。"""
    def loop():
        while True:
            time.sleep(10)
            if time.time() - ctx.started < grace:
                continue
            if time.time() - ctx.last_ping > idle:
                httpd.shutdown()
                return

    threading.Thread(target=loop, daemon=True).start()


# ---------- 自检 ----------
def _selftest(md, out):
    """无头自检：静态资源 + HTTP 构建全链路，结果写 <out> 上级目录 _selftest_result.txt。

    比旧的自检更有价值：它真的走了一遍「浏览器会走的那些接口」，
    打包后静态文件漏带（白屏）能立刻暴露。"""
    marker = pathlib.Path(out).parent / "_selftest_result.txt"
    ok = False
    detail = ""
    httpd = None
    try:
        ctx, httpd, engine = start_server(port=0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{ctx.port}/s/{ctx.token}"
        detail = f"engine={engine.mode} python={sys.version.split()[0]} "

        css = urllib.request.urlopen(base + "/static/app.css", timeout=15).read()
        if len(css) < 500:
            raise RuntimeError("界面静态资源为空（打包漏带 webapp/ui？）")
        for name in ("app.js", "editor.js", "outline.js", "picker.js"):
            urllib.request.urlopen(f"{base}/static/{name}", timeout=15).read()

        payload = json.dumps({"path": md, "out": out, "save": False}).encode("utf-8")
        req = urllib.request.Request(base + "/api/build", data=payload,
                                     headers={"Content-Type": "application/json"})
        raw = urllib.request.urlopen(req, timeout=300).read().decode("utf-8")
        events = [json.loads(line[6:]) for line in raw.split("\n") if line.startswith("data: ")]
        done = [e for e in events if e.get("t") == "done"]
        if not done:
            raise RuntimeError("构建没有返回 done 事件")
        if not done[-1].get("ok"):
            raise RuntimeError("构建失败: " + str(done[-1].get("error")))
        detail += f"pages={(done[-1].get('stats') or {}).get('pages')} "

        if not pathlib.Path(out, "index.html").is_file():
            raise RuntimeError("产物缺少 index.html")
        served = urllib.request.urlopen(f"{base}/out/index.html", timeout=15).read()
        if b"<html" not in served.lower():
            raise RuntimeError("产物无法通过 HTTP 访问")

        # 选项透传自检：子进程模式最容易漏传 --xxx 开关（漏了不报错，只是效果消失）。
        # 用一份必有两个分组的合成文档，确认「分组独立成页」真的落地。
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="markpage-opt-"))
        pmd = tmp / "opt.md"
        pmd.write_text("# 选项自检\n\n## 总览 {.overview}\n\n总览正文。\n\n"
                       "# 组甲\n\n## 模块一\n\n正文一。\n\n"
                       "# 组乙\n\n## 模块二\n\n正文二。\n", encoding="utf-8")
        pout = tmp / "site"
        payload = json.dumps({"path": str(pmd), "out": str(pout), "save": False,
                              "opts": {"group_pages": True}}).encode("utf-8")
        req = urllib.request.Request(base + "/api/build", data=payload,
                                     headers={"Content-Type": "application/json"})
        raw = urllib.request.urlopen(req, timeout=300).read().decode("utf-8")
        evs = [json.loads(line[6:]) for line in raw.split("\n") if line.startswith("data: ")]
        d2 = [e for e in evs if e.get("t") == "done"]
        if not d2 or not d2[-1].get("ok"):
            raise RuntimeError("选项自检构建失败: " + str(d2[-1].get("error") if d2 else "无 done"))
        gpages = [f for f in os.listdir(pout) if f.startswith("g-") and f.endswith(".html")]
        if len(gpages) < 2:
            raise RuntimeError(f"--group-pages 未生效（只生成 {len(gpages)} 个分组页，"
                               f"检查 engine.BOOL_FLAGS 是否漏登记）")
        detail += f"opt=ok({len(gpages)}) "
        shutil.rmtree(tmp, ignore_errors=True)
        ok = True
    except Exception as e:                       # noqa: BLE001
        detail += f"EXC {type(e).__name__}: {e}"
    finally:
        if httpd is not None:
            try:
                httpd.shutdown()
            except Exception:                    # noqa: BLE001
                pass
    try:
        marker.write_text(("PASS\n" if ok else "FAIL\n") + detail + "\n", encoding="utf-8")
    except OSError:
        pass
    return 0 if ok else 1


# ---------- 主入口 ----------
def main(argv=None):
    _stderr_to_log()
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--selftest":
        if len(argv) < 3:
            print("用法: md_doc_gui.py --selftest <md> <输出目录>")
            return 2
        return _selftest(argv[1], argv[2])

    ap = argparse.ArgumentParser(description="Markpage：Markdown 一键生成多页 HTML 文档站")
    ap.add_argument("md", nargs="?", help="启动后直接打开的 md 文件")
    ap.add_argument("--port", type=int, default=0, help="固定端口（默认自动挑一个空闲端口）")
    ap.add_argument("--no-browser", action="store_true", help="只起服务，不打开窗口")
    ap.add_argument("--browser", choices=["edge", "default"], default="edge",
                    help="edge=无地址栏应用窗口（默认）；default=系统默认浏览器")
    ap.add_argument("--no-exit", action="store_true", help="页面关闭后不退出进程")
    args = ap.parse_args(argv)

    ctx, httpd, engine = start_server(port=args.port)
    if args.md:
        md = os.path.abspath(args.md)
        if os.path.isfile(md):
            ctx.state.patch({"last_path": md})
    url = f"http://127.0.0.1:{ctx.port}/s/{ctx.token}/"

    if not args.no_browser:
        open_app_window(url, args.browser)
    print(f"Markpage 已启动: {url}")
    print(f"引擎: {engine.info()}")

    if not args.no_exit:
        start_watchdog(ctx, httpd)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            httpd.server_close()
        except Exception:                        # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
