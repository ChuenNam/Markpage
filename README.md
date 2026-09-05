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
| `## 标题 {.overview}` | 栏目角色=总览：**不进模块页**，归首页（导语之后、卡片之前；组内则置该分组卡片顶部） |
| `## 标题 {.appendix}` | 栏目角色=附录：**不进模块页**，归固定附录页（可多个，按文档顺序拼接；可与正文交错） |
| `### 小节` | 页内栏目（页顶 chips 快捷跳转 + 搜索锚点） |
| `## 附录…` | 兼容旧约定：无任何角色声明时，首个「附录…」标题至文末整体为附录页（与旧版输出一致） |

> 角色声明优先级：`{.overview}/{.appendix}` 行尾后缀 > GUI/CLI「栏目规则表」> 旧「附录…」前缀约定。
> 三者均未命中时行为与旧版完全一致（默认不启用 = 零变化）。

生成的站点 = `index.html` + 每模块一页 + 附录 + `search-index.js`（站内搜索）+ `assets/`（图片资源）。

## 站点选项（GUI「站点选项」面板 / CLI 参数；均默认关闭）

| 选项 | 作用 | CLI |
| --- | --- | --- |
| 总览表自动链接 | 首页正文表格中**整格文本 == 模块标题**（或别名）的单元格自动变为指向模块页的链接 | `--overview-links` |
| 栏目规则表 | 给未带后缀的 `##` 声明角色（每行：`标题=overview|appendix`，前缀匹配 `前缀*=…`） | `--route '标题=overview'`（可多次） |
| 总览表别名 | 一览表「显示名 ≠ 模块页标题」时的映射（每行：`显示名=模块标题`） | `--alias '显示名=模块标题'`（可多次） |

```bat
:: 示例：带后缀声明的 md + 总览表链接 + 两条别名
python scripts\md_site_builder.py 文档.md --out out --overview-links ^
    --alias "StoryView（TMP）=StoryView（TMP 表现层，可选程序集）" ^
    --alias "DialogueBoxManager（UI）=DialogueBoxManager（UI 程序集）"

:: 示例：用规则表替代 md 后缀（不修改源文档）
python scripts\md_site_builder.py 文档.md --out out --route "组件总览=overview" --route "附录*=appendix"
```

GUI 用法：生成前在「站点选项」框勾选 / 填写上述内容即可（填错会弹窗提示，不会开始生成）。

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
      └─ build_component_doc_site.py     宿主《组件 API 参考》站点生成（Markpage 引擎直驱薄包）
```

## 宿主《组件 API 参考》站点

通用引擎之上的轻量直驱（`scripts/host/build_component_doc_site.py`）：定位宿主 md → 打开总览表
自动链接 → 注入一览表别名（显示名 ≠ 模块标题的行）→ 其余全部交给通用引擎。宿主 md 源通过
`{.overview}` / `{.appendix}` 行尾后缀声明栏目角色（2026-09 起，v1 前为固化脚本内嵌 FILEMAP/CELL_LINK）：

```bat
:: 指定宿主包根（src/out 自动推导为 组件API参考/组件API参考.md -> 组件API参考/html）
python scripts\host\build_component_doc_site.py --pkg <宿主包根>

:: 或全手动 / 覆盖别名表
python scripts\host\build_component_doc_site.py --src a.md --out 某目录
python scripts\host\build_component_doc_site.py --alias-json 别名.json   :: {显示名: 模块标题}
```

可选参数：`--title`（默认 组件 API 参考（业务侧））、`--alias-json`、`--no-overview-links`。
环境变量 `MARKPAGE_PKG` 可代替 `--pkg`。模块页文件名 = 标题 slug（2026-09 起接受全变，
不再维护固定文件名映射）。


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
