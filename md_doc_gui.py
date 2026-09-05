# -*- coding: utf-8 -*-
"""MD 文档站生成器 —— 图形界面（把任意 Markdown 一键生成为多页 HTML 文档站）。

架构（壳与生成核心分层）:
  - 本文件只需 tkinter（标准库），用系统 Python 直接双击运行（见同目录 .bat 启动器）；
  - 真正的生成核心是 md_site_builder.py，需要 python-markdown + pygments；
  - 双运行模式（自适应）：
      ① 内嵌模式：若当前解释器能 import md_site_builder（即 markdown/pygments 可用，
         PyInstaller 打包出的独立 exe 即此模式）→ 直接线程内调用 build_site()，
         不依赖任何外部文件/venv；
      ② 子进程模式：源码直接运行时系统 Python 通常没装依赖 → 自动退回用
         「仓库 venv python」以子进程方式执行 md_site_builder.py（老行为）。
  - 附带无头自检：python md_doc_gui.py --selftest <md> <out>
    （打包后用于验证 exe 内依赖完整；结果写入 <out> 所在目录 _selftest_result.txt）

用法:
  双击 md_doc_gui.bat（或 python md_doc_gui.py）
"""
import os
import re
import sys
import time
import queue
import pathlib
import threading
import subprocess
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox

TOOLS = os.path.dirname(os.path.abspath(__file__))
BUILDER = os.path.join(TOOLS, "md_site_builder.py")

# 内嵌模式探测：解释器能 import 生成核心（含 markdown/pygments）就直接内嵌调用
try:
    import md_site_builder as _builder  # noqa: F401
    _EMBED = True
except Exception:  # noqa: BLE001
    _builder = None
    _EMBED = False

# venv python（含 markdown/pygments）候选路径，按序探测
VENV_CANDIDATES = [
    os.environ.get("WORKBUDDY_VENV_PY", ""),
    r"C:\Users\Lenovo\.workbuddy\binaries\python\envs\default\Scripts\python.exe",
]
VENV_PY = next((p for p in VENV_CANDIDATES if p and os.path.isfile(p)), None)

STYLE = {"pad": 6}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MD 文档站生成器（通用）")
        self.geometry("820x600")
        self.minsize(680, 460)
        self._build_ui()
        # 跨线程回调队列：子线程只往队列放任务，主线程轮询执行，避免直接跨线程调 tkinter
        self._q = queue.Queue()
        self.after(120, self._poll_queue)
        if VENV_PY is None:
            messagebox.showwarning(
                "依赖未找到",
                "未找到仓库 venv 的 python（需包含 markdown + pygments）。\n"
                "可用环境变量 WORKBUDDY_VENV_PY 指定其路径。\n"
                "界面可继续使用，但生成会失败。", parent=self)

    # ---------- UI ----------
    def _build_ui(self):
        pad = STYLE["pad"]
        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)

        ttk.Label(body, text="源 Markdown 文件 *", font=("", 10, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 2))
        row1 = ttk.Frame(body); row1.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        body.columnconfigure(0, weight=1)
        self.md_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self.md_var).pack(side="left", fill="x", expand=True, ipady=2)
        ttk.Button(row1, text="浏览…", width=8, command=self.pick_md).pack(side="left", padx=(6, 0))

        ttk.Label(body, text="输出目录").grid(row=2, column=0, sticky="w", pady=(0, 2))
        row2 = ttk.Frame(body); row2.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self.out_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.out_var).pack(side="left", fill="x", expand=True, ipady=2)
        ttk.Button(row2, text="浏览…", width=8, command=self.pick_out).pack(side="left", padx=(6, 0))

        ttk.Label(body, text="站点标题（留空自动取首个 `#` 标题）").grid(
            row=4, column=0, sticky="w", pady=(0, 2))
        self.title_var = tk.StringVar()
        ttk.Entry(body, textvariable=self.title_var).grid(
            row=5, column=0, sticky="ew", ipady=2, pady=(0, 10))

        row6 = ttk.Frame(body); row6.grid(row=6, column=0, sticky="w", pady=(0, 6))
        self.gen_btn = ttk.Button(row6, text="生成站点", command=self.generate, width=14)
        self.gen_btn.pack(side="left")
        self.open_btn = ttk.Button(row6, text="在浏览器打开", command=self.open_site,
                                   width=16, state="disabled")
        self.open_btn.pack(side="left", padx=8)
        self.hint_var = tk.StringVar(value="说明：`#` 一级标题为分组（首个为站点标题），`##` 每个模块一页，`###` 页内栏目。")
        ttk.Label(body, textvariable=self.hint_var, foreground="#888").grid(
            row=7, column=0, sticky="w", pady=(0, 2))

        self.log = scrolledtext.ScrolledText(body, height=14, state="disabled",
                                             font=("Consolas", 10))
        self.log.grid(row=8, column=0, sticky="nsew", pady=(8, 0))
        body.rowconfigure(8, weight=1)

        self._busy = False

    # ---------- 交互 ----------
    def pick_md(self):
        p = filedialog.askopenfilename(
            title="选择源 Markdown", filetypes=[("Markdown", "*.md"), ("所有文件", "*.*")],
            initialdir=os.path.expanduser("~"))
        if not p:
            return
        self.md_var.set(p)
        # 默认输出：同目录/<文件名>；默认标题：首 # 标题
        out = os.path.join(os.path.dirname(p), os.path.splitext(os.path.basename(p))[0])
        self.out_var.set(out)
        try:
            with open(p, encoding="utf-8") as f:
                head = f.readline().strip()
            if head.startswith("# "):
                self.title_var.set(re.sub(r"[`*_]", "", head[2:]).strip())
        except OSError:
            pass

    def pick_out(self):
        p = filedialog.askdirectory(title="选择输出目录")
        if p:
            self.out_var.set(p)

    def _append_log(self, line):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _post(self, fn):
        """跨线程安全：把回调交给主线程执行。"""
        self._q.put(fn)

    def _log(self, line):
        self._post(lambda: self._append_log(line))

    def _poll_queue(self):
        try:
            while True:
                fn = self._q.get_nowait()
                try:
                    fn()
                except Exception:  # noqa: BLE001
                    import traceback
                    self._append_log("!! 界面回调异常: " + traceback.format_exc(limit=3))
        except queue.Empty:
            pass
        self.after(120, self._poll_queue)

    def _set_busy(self, busy):
        self._busy = busy
        self.gen_btn.configure(state="disabled" if busy else "normal")
        # 「在浏览器打开」只在生成成功后启用；忙时一律禁用
        if busy:
            self.open_btn.configure(state="disabled")

    def generate(self):
        md = self.md_var.get().strip().strip('"')
        out = self.out_var.get().strip().strip('"')
        if not md or not os.path.isfile(md):
            messagebox.showwarning("缺源文件", "请先选择存在的 Markdown 文件。", parent=self)
            return
        if not out:
            out = os.path.join(os.path.dirname(md),
                               os.path.splitext(os.path.basename(md))[0])
            self.out_var.set(out)
        if VENV_PY is None:
            messagebox.showerror("依赖未找到", "未找到带 markdown/pygments 的 python，无法生成。",
                                 parent=self)
            return
        title = self.title_var.get().strip()   # 主线程读 tk 变量，只把值交给子线程
        self._set_busy(True)
        threading.Thread(target=self._run_build, args=(md, out, title), daemon=True).start()

    def _run_build(self, md, out, title):
        """子线程执行构建；UI 一律经 _log/_post 队列回流主线程。"""
        if _EMBED:
            self._log("> 内嵌模式：build_site()（markdown/pygments 已随本程序内置）")
            self._log(f"  源: {md}")
            self._log(f"  输出: {out}")
            try:
                r = _builder.build_site(md, out, title or None, log=self._log)
                self._log(f"生成: {r['dir']} | 页面: {r['pages']} | 模块: {r['modules']} | "
                          f"分组: {r['groups']} | 附录: {r['appendix']} | 索引: {r['index_kb']} KB | "
                          f"资源: 拷贝 {r['assets_copied']} / 缺失 {r['assets_missing']}")
                ok = True
            except Exception as e:  # noqa: BLE001
                import traceback
                ok = False
                self._log(f"!! 生成异常: {type(e).__name__}: {e}")
                self._log(traceback.format_exc(limit=6))
        else:
            cmd = [VENV_PY, BUILDER, md, "--out", out]
            if title:
                cmd += ["--title", title]
            if VENV_PY is None:
                self._log("!! 未找到带 markdown/pygments 的 python（内嵌不可用且无 venv），无法生成。")
                ok = False
            else:
                env = dict(os.environ)
                env["PYTHONIOENCODING"] = "utf-8"
                self._log("> " + " ".join(cmd))
                self._log("---- 开始生成 ----")
                try:
                    p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT,
                                         encoding="utf-8", errors="replace", bufsize=1,
                                         text=True, env=env)
                    for line in p.stdout:
                        self._log(line.rstrip("\n"))
                    p.wait()
                    ok = p.returncode == 0
                except Exception as e:  # noqa: BLE001
                    ok = False
                    self._log(f"!! 启动生成器失败: {e}")
        self._log("---- " + ("生成完成 ✔" if ok else "生成失败 ✘") + " ----")
        # 收尾统一放主线程执行；成功才启用「在浏览器打开」
        self._post(lambda: self._finish(ok, out))

    def _finish(self, ok, out):
        self._set_busy(False)
        if ok:
            self.open_btn.configure(state="normal")
            self._last_out = out

    def open_site(self):
        # 优先打开最近一次成功生成的位置；否则退回当前输出框的值
        out = getattr(self, "_last_out", None) or self.out_var.get().strip().strip('"')
        self._open(out)

    @staticmethod
    def _open(out_dir):
        idx = os.path.join(out_dir, "index.html")
        if os.path.isfile(idx):
            webbrowser.open("file:///" + idx.replace("\\", "/"))
        else:
            messagebox.showinfo("未找到", "站点还没生成，请先生成。")

def _selftest(md, out):
    """无头自检：真实跑一次生成，校验打包/依赖完整。结果写 <out> 上级目录 _selftest_result.txt。"""
    marker = pathlib.Path(out).parent / "_selftest_result.txt"
    good = False
    try:
        app = App()
        app.withdraw()
        app.update()
        app.md_var.set(md)
        app.out_var.set(out)
        app.generate()
        deadline = time.time() + 300
        while time.time() < deadline:
            app.update()
            if not app._busy:
                break
            time.sleep(0.05)
        for _ in range(6):
            app.update()
            time.sleep(0.05)
        good = (pathlib.Path(out, "index.html").is_file()
                and getattr(app, "_last_out", None) == out)
        app.destroy()
    except Exception as e:  # noqa: BLE001
        good = False
        try:
            marker.write_text("EXC " + repr(e) + "\n", encoding="utf-8")
        except OSError:
            pass
    try:
        marker.write_text("PASS\n" if good else "FAIL\n", encoding="ascii")
    except OSError:
        pass
    return 0 if good else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--selftest" and len(argv) >= 3:
        raise SystemExit(_selftest(argv[1], argv[2]))
    try:
        app = App()
        app.mainloop()
    except Exception as e:
        import traceback
        log = os.path.join(TOOLS, "gui_error.log")
        try:
            with open(log, "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
        except OSError:
            pass
        try:
            messagebox.showerror("启动失败", f"GUI 启动出错：{e}\n详情已写入：\n{log}")
        except Exception:
            pass
        raise

if __name__ == "__main__":
    main()
