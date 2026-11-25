# -*- coding: utf-8 -*-
"""构建引擎门面 —— 把「怎么跑引擎」的细节挡在界面之外。

两种执行方式，向上暴露同一套流式事件 (kind, payload)：
  ① embed      当前解释器能 import md_site_builder（独立版 exe 即是）→ 线程内直调；
  ② subprocess 源码直跑、系统 Python 没装 markdown/pygments → 用带依赖的
               venv python 起子进程，按行读 stdout（老行为）。

事件类型：log(一行日志) / stats(结果字典) / error(错误文本) / cancelled / done。
取消靠 threading.Event：embed 模式在日志回调里抛 Cancelled 中断引擎，
subprocess 模式 terminate 子进程。
"""
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading

__all__ = ["Engine", "Cancelled"]


class Cancelled(Exception):
    """用户取消构建。"""


def _looks_like_python(path):
    return bool(path) and os.path.isfile(path)


def quiet_kwargs():
    """子进程不弹控制台窗口。

    启动器是 pythonw（无控制台）跑的时候，如果再 spawn 一个带控制台的 python.exe，
    Windows 会给子进程**新分配一个黑窗口**——表现为「改一下选项就闪一个 cmd 窗」。
    打包成 console=False 的 exe 同样会犯。所以凡是我们自己起的子进程，一律带上
    CREATE_NO_WINDOW（并额外给 STARTUPINFO 的 SW_HIDE 兜底，其他启动方式也压得住）。"""
    if os.name != "nt":
        return {}
    kw = {"creationflags": 0x08000000}          # CREATE_NO_WINDOW
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        kw["startupinfo"] = si
    except (AttributeError, ValueError):
        pass
    return kw


class Engine:
    def __init__(self, tools_dir):
        self.tools_dir = tools_dir
        self.builder = os.path.join(tools_dir, "md_site_builder.py")
        self.embed_mod = self._try_embed()
        self.venv_py = None if self.embed_mod is not None else self._find_venv()

    # ---------- 环境探测 ----------
    def _try_embed(self):
        if self.tools_dir not in sys.path:
            sys.path.insert(0, self.tools_dir)
        try:
            import md_site_builder          # noqa: F401
            return md_site_builder
        except Exception:                   # noqa: BLE001
            return None

    def _find_venv(self):
        """按序探测带 markdown+pygments 的解释器，逐个实测 import。"""
        cands = [
            os.environ.get("WORKBUDDY_VENV_PY", ""),
            os.path.join(self.tools_dir, "..", ".venv", "Scripts", "python.exe"),
            os.path.join(self.tools_dir, "..", "venv", "Scripts", "python.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python311\python.exe"),
            r"C:\Users\Lenovo\.workbuddy\binaries\python\envs\default\Scripts\python.exe",
            sys.executable,
        ]
        seen = set()
        for c in cands:
            p = os.path.abspath(c) if c else ""
            if not _looks_like_python(p) or p in seen:
                continue
            seen.add(p)
            if self._probe(p):
                return p
        return None

    @staticmethod
    def _probe(py):
        try:
            r = subprocess.run([py, "-c", "import markdown,pygments"],
                               capture_output=True, timeout=20,
                               env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                               **quiet_kwargs())
            return r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    # ---------- 对外信息 ----------
    @property
    def mode(self):
        if self.embed_mod is not None:
            return "embed"
        if self.venv_py:
            return "subprocess"
        return "unavailable"

    def info(self):
        return {"mode": self.mode,
                "python": sys.version.split()[0],
                "python_exe": self.venv_py or sys.executable,
                "embed": self.embed_mod is not None,
                "ok": self.mode != "unavailable"}

    # ---------- 构建 ----------
    def build(self, md_path, out_dir, title=None, opts=None, text=None, cancel=None):
        """生成器：产出 (kind, payload) 事件流。"""
        if self.embed_mod is not None:
            yield from self._build_embed(md_path, out_dir, title, opts, text, cancel)
        elif self.venv_py:
            yield from self._build_sub(md_path, out_dir, title, opts, text, cancel)
        else:
            yield ("error", "未找到可用的 Python 环境（需要 markdown + pygments）。"
                            "可用环境变量 WORKBUDDY_VENV_PY 指定解释器路径。")
            yield ("done", None)

    def _build_embed(self, md_path, out_dir, title, opts, text, cancel):
        B = self.embed_mod
        q = queue.Queue()

        def log(line="", *_a):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            q.put(("log", str(line)))

        def work():
            try:
                r = B.build_site(md_path, out_dir, title or None, log=log,
                                 opts=opts or None, md_text=text)
                q.put(("stats", r))
            except Cancelled:
                q.put(("cancelled", None))
            except Exception as e:                       # noqa: BLE001
                import traceback
                q.put(("error", f"{type(e).__name__}: {e}"))
                q.put(("trace", traceback.format_exc(limit=6)))
            finally:
                q.put(("eof", None))

        threading.Thread(target=work, daemon=True).start()
        while True:
            kind, payload = q.get()
            if kind == "eof":
                break
            yield (kind, payload)
        yield ("done", None)

    # 界面选项 → CLI 开关。加新选项时**必须**在这里登记一行，否则只有内嵌模式生效、
    # 子进程模式会被静默丢掉（.bat 默认就是子进程模式，极易漏测）。
    BOOL_FLAGS = (
        ("overview_links", "--overview-links"),
        ("group_pages", "--group-pages"),
    )

    def _build_sub(self, md_path, out_dir, title, opts, text, cancel):
        opts = opts or {}
        cmd = [self.venv_py, "-u", self.builder, md_path, "--out", out_dir, "--json"]
        if title:
            cmd += ["--title", title]
        for key, flag in self.BOOL_FLAGS:
            if opts.get(key):
                cmd.append(flag)
        for r in opts.get("route") or []:
            key = r["title"] + ("*" if r.get("match") == "prefix" else "")
            cmd += ["--route", f"{key}={r['role']}"]
        for cell, mtitle in (opts.get("alias") or {}).items():
            cmd += ["--alias", f"{cell}={mtitle}"]

        tmp_text = None
        if text is not None:
            fd, tmp_text = tempfile.mkstemp(prefix="markpage-buf-", suffix=".md")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            cmd += ["--text-from", tmp_text]

        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        yield ("log", "> " + " ".join(cmd))
        proc = None
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    encoding="utf-8", errors="replace", bufsize=1,
                                    text=True, env=env, cwd=self.tools_dir,
                                    stdin=subprocess.DEVNULL, **quiet_kwargs())
            for line in proc.stdout:
                if cancel is not None and cancel.is_set():
                    proc.terminate()
                    break
                line = line.rstrip("\n")
                if line.startswith("##RESULT##"):
                    try:
                        yield ("stats", json.loads(line[len("##RESULT##"):]))
                    except ValueError:
                        pass
                    continue
                yield ("log", line)
            rc = proc.wait()
            if cancel is not None and cancel.is_set():
                yield ("cancelled", None)
            elif rc != 0:
                yield ("error", f"生成器退出码 {rc}（详见上方日志）")
        except OSError as e:
            yield ("error", f"启动生成器失败: {e}")
        finally:
            if proc is not None and proc.poll() is None:
                try:
                    proc.kill()
                except OSError:
                    pass
            if tmp_text:
                try:
                    os.unlink(tmp_text)
                except OSError:
                    pass
        yield ("done", None)
