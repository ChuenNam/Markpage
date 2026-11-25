# -*- coding: utf-8 -*-
"""Markpage Web 界面后端包（纯标准库）。

模块划分：
  engine.py  构建引擎门面（内嵌 / venv 子进程两种执行方式，统一为流式事件）
  state.py   界面状态持久化（最近文件、按 md 记住的选项）
  server.py  本地 HTTP 服务：静态界面 + JSON/SSE 接口
"""
