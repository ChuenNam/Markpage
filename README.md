# Markpage

把一份 Markdown 文档一键生成「多页 HTML 文档站」的小工具：左侧可折叠分组目录、深浅主题、
跨页搜索、代码块行号 / 语言标签 / 一键复制。图形界面，双击即用。

> 独立发布版已内置 Python 运行时与渲染依赖，**目标电脑无需安装 Python、无需联网**。

## 快速上手

**普通用户（用独立版）**

1. 取 `releases/MD文档站生成器.zip`（或整个 `releases/MD文档站生成器/` 文件夹）拷贝到任意 Windows 电脑；
2. 解压后双击 `DocSiteTool.exe`；
3. 选一份 `.md` → 生成站点 → 日志显示「生成完成 ✔」后点【在浏览器打开】。
   （使用细节见独立版内置 `使用说明.txt`）

**开发者（跑源码）**

```bat
md_doc_gui.bat          :: 双击启动 GUI（自动找系统 Python，纯标准库）
python scripts\md_site_builder.py 文档.md --out 输出目录 [--title 站点标题]
```

源码 GUI 采用双模式自适应：解释器能 `import` 生成核心（装了 markdown/pygments）时线程内直接
调用；否则自动退回用仓库 venv 的 python 以子进程执行（需先 `pip install markdown pygments`）。

## 支持的 md 标题规则（决定站点结构）

| md 写法 | 站点效果 |
| --- | --- |
| 第一个 `# 标题` | 站点标题（其下正文进首页总览区） |
| 后续每个 `# 一级标题` | 分组（左侧目录的分类抽屉、首页分组卡片） |
| `## 模块标题` | 一个独立模块页 |
| `### 小节` | 页内栏目（页顶 chips 快捷跳转 + 搜索锚点） |
| `## 附录…` | 独立附录页，置于目录末尾 |

生成的站点 = `index.html` + 每模块一页 + 附录 + `search-index.js`（站内搜索）+ `assets/`（图片资源）。

## 仓库结构

```text
Markpage/
├─ md_doc_gui.bat / md_doc_gui_debug.bat   源码运行启动器（放仓库根，双击即可）
├─ build_standalone.bat                    一键重建独立版（也在根）
├─ pack_usage_说明.txt                     独立版内置使用说明
├─ docs/                                   Markpage 自身使用文档与示例（用本工具生成）
├─ releases/                               ★ 独立发布包（zip + 解压文件夹），拷给别人用
└─ scripts/                                源码与打包脚本
   ├─ md_doc_gui.py                       图形界面（tkinter，纯标准库）
   ├─ md_site_builder.py                  生成核心（python-markdown + pygments）
   ├─ doc_site_assets.py                  站点 CSS/JS（单一事实来源）
   ├─ md_doc_gui.spec                     独立版打包配置（PyInstaller）
   ├─ assemble_release.py                 打包收尾（组装 releases/ + zip）
   ├─ rebuild_code_theme_css.py           doc_site_assets 代码块主题段幂等重建
   │                                     （浅色 friendly / 深色 monokai；维护样式用）
   └─ host/
      └─ build_component_doc_site.py     宿主《组件 API 参考》专用生成器（参数化版）
```

## 宿主《组件 API 参考》站点

Markpage 引擎之上的文档专属固化器（`# 部件`分组 + `## 类型/契约`模块页 + 总览表自动改链
+ api-meta + 固定桥接层附录），路径全参数化、渲染复用 Markpage 引擎：

```bat
:: 指定宿主包根（src/out 自动推导为 组件API参考/组件API参考.md -> 组件API参考/html）
python scripts\host\build_component_doc_site.py --pkg <宿主包根>

:: 或全手动
python scripts\host\build_component_doc_site.py --src a.md --out 某目录
```

可选参数：`--title`（默认 组件 API 参考（业务侧））、`--brand`（默认 MicrobialNet Story）、
`--filemap` / `--cellmap`（JSON 覆盖模块页文件名映射 / 总览表改链映射）。环境变量
`MARKPAGE_PKG` 可代替 `--pkg`。
```

## 重新构建独立版（维护者）

在装有 Python 3.11（需带 tkinter）的开发机执行：

```bat
build_standalone.bat
```

脚本会自动：建打包 venv → 装 markdown/pygments/pyinstaller → PyInstaller 打 onedir →
组装 `releases/MD文档站生成器/` 与 `.zip`。环境变量 `MARKPAGE_PY311` 可指定 Python 路径。

## 无头自检

验证依赖与代码是否完整（打包后尤其有用）：

```bat
DocSiteTool.exe --selftest 某文档.md 某输出目录
:: 或源码： python scripts\md_doc_gui.py --selftest 某文档.md 某输出目录
```

结果写入「输出目录上级」的 `_selftest_result.txt`（PASS/FAIL）。
