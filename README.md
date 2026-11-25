# Markpage

把一份 Markdown 文档一键生成「多页 HTML 文档站」的小工具：左侧可折叠分组目录、深浅主题、
跨页搜索、代码块行号 / 语言标签 / 一键复制。图形界面，双击即用。

> 独立发布版已内置 Python 运行时与渲染依赖，**目标电脑无需安装 Python、无需联网**。

## 快速上手

**普通用户（用独立版）**

1. 取 `releases/Markpage.zip`（或整个 `releases/Markpage/` 文件夹）拷贝到任意 Windows 电脑；
2. 解压后双击 `Markpage.exe`；
3. 选一份 `.md` → 生成站点 → 日志显示「生成完成 ✔」后点【在浏览器打开】。
   （使用细节见独立版内置 `使用说明.txt`）

**开发者（跑源码）**

```bat
md_doc_gui.bat          :: 双击启动：起本地服务 + 开 Edge 应用窗口（界面是网页）
python scripts\md_site_builder.py 文档.md --out 输出目录 [--title 站点标题]
python scripts\md_doc_gui.py :: 同 .bat；可加 --port 8791 / --browser default / --no-exit
```

界面已迁到浏览器（2026-11）：`md_doc_gui.py` 起一个只监听 127.0.0.1 的本地服务，
用 `msedge --app=` 打开一个无地址栏的独立窗口；没装 Edge 就退回默认浏览器。
好处是真·实时预览（iframe 直接加载渲染结果，站内搜索、代码复制都能点）、
编辑与产物同屏、构建日志流式输出。引擎侧零改动。

源码运行时同样是双模式自适应：解释器能 `import` 生成核心（装了 markdown/pygments）
就线程内直接调用；否则自动退回用仓库 venv 的 python 以子进程执行。

拖入 `.md`：浏览器出于安全不提供拖入文件的磁盘路径，因此**主入口是界面里的
「选择 Markdown 文件」（内置目录浏览器）**；拖放仅在「上次目录下存在同名且内容
完全一致的文件」时能定位到磁盘，否则会提示改用浏览按钮。

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

生成的站点 = `index.html` + 每模块一页 + 附录 + `site.css`/`site.js`（全站样式与交互，
**外链一次**，页面只引用不内联，多模块站点体积不随页数重复膨胀）+ `search-index.js`（站内搜索）+ `assets/`（图片资源）。

## 站点选项（GUI「站点选项」面板 / CLI 参数；均默认关闭）

| 选项 | 作用 | CLI |
| --- | --- | --- |
| 总览表自动链接 | 首页正文表格中**整格文本 == 模块标题**（或别名）的单元格自动变为指向模块页的链接 | `--overview-links` |
| 分组独立成页 | 每个一级标题（分组）单独一页：页面里放该组导语、组内总览与模块卡片；首页只保留全篇总览与各组入口，组多时首页不会过长 | `--group-pages` |
| 栏目规则表 | 给未带后缀的 `##` 声明角色（每行：`标题=overview|appendix`，前缀匹配 `前缀*=…`） | `--route '标题=overview'`（可多次） |
| 总览表别名 | 一览表「显示名 ≠ 模块页标题」时的映射（每行：`显示名=模块标题`） | `--alias '显示名=模块标题'`（可多次） |

> 标题层级：站点标题 → 分组标题（`#`）→ **总览节（带左侧色条 + 「总览」角标）** → 模块卡片。
> 总览节刻意压到与模块卡片同量级，只靠色条与角标区分，避免它被误读成模块标题。
> 开启「分组独立成页」后，分组标题成为分组页的页标题，总览节仍是分组页里的节标签。

```bat
:: 示例：带后缀声明的 md + 总览表链接 + 两条别名
python scripts\md_site_builder.py 文档.md --out out --overview-links ^
    --alias "StoryView（TMP）=StoryView（TMP 表现层，可选程序集）" ^
    --alias "DialogueBoxManager（UI）=DialogueBoxManager（UI 程序集）"

:: 示例：用规则表替代 md 后缀（不修改源文档）
python scripts\md_site_builder.py 文档.md --out out --route "组件总览=overview" --route "附录*=appendix"
```

界面用法（不需要记语法）：

- **栏目角色**：右栏「结构」页签列出文档里每个 `##` 标题，旁边一个下拉选「模块页 / 总览 / 附录」。
  选完会把标记直接写回源文档行尾，预览立刻更新 —— 不用手写 `{.overview}`。
- **总览表链接**：在「站点选项」里勾上开关即可。表格里写的名字和模块标题对不上时，
  对话框会自动列出「差的这一口气」的候选行（左边表格里的写法、右边下拉选目标模块），
  删掉某行即表示不需要它 —— 不用手写 `显示名=模块标题`。
- 文本规则（`--route` / `--alias` 的等价写法）收在「站点选项 → 高级」里，一般用不到。
- **检查**：右栏「检查」页签列出结构问题——标题跳级、模块重名、模块没正文、图片找不到、
  规则与别名没命中。每条都能点，点了跳到源文档对应行；有错误的条数会显示成页签上的角标。
- **源行底纹**：预览哪一页，编辑器里就把「拼成这一页的源行」涂上底色；
  点左栏结构里的模块，对应整段会闪两下并自动滚到位。这样「预览里看到的东西」和
  「源文档哪一段」永远对得上。
- **产物**：生成后列出所有页面（点一下在预览区打开），并可打包成 zip、清理输出目录
  （只删本站产出物，目录里其他文件不动）。
- **输出位置**：「站点选项」里默认是**当前 md 所在目录**，并默认套一层名为 `site` 的子目录
  （可在弹窗里改名字，取消勾选则直接生成在该目录下）。同一目录放多份文档时记得改子目录名，
  否则后生成的会覆盖前一份的 html。
- **目录快捷入口**：文件浏览器顶部预置「桌面 / 文档 / 下载」，鼠标悬停每个入口右侧出现 `×` 可删除
  （会先确认，只删入口不动磁盘文件）；末尾 `+` 把当前目录加为入口。配置写在
  `%LOCALAPPDATA%\Markpage\quick_dirs.json`，可直接手改；首次运行会从系统注册表
  （`User Shell Folders`，能正确处理 OneDrive 重定向）生成初始三条。

## 仓库结构

```text
Markpage/
├─ md_doc_gui.bat / md_doc_gui_debug.bat   源码运行启动器（放仓库根，双击即可）
├─ build_standalone.bat                    一键重建独立版（也在根）
├─ pack_usage_说明.txt                     独立版内置使用说明
├─ docs/                                   Markpage 自身使用文档与示例（用本工具生成）
├─ releases/                               ★ 独立发布包（zip + 解压文件夹），拷给别人用
└─ scripts/                                源码与打包脚本
   ├─ md_doc_gui.py                       启动器：起本地服务 + 开浏览器窗口（纯标准库）
   ├─ webapp/
   │  ├─ server.py                        本地 HTTP 服务：静态界面 + JSON/SSE 接口
   │  ├─ engine.py                        引擎门面（内嵌 / venv 子进程，统一为流式事件）
   │  ├─ state.py                         最近文件与按 md 记忆的选项
   │  └─ ui/                              界面本体（index.html / app.css / app.js 等，无构建步骤）
   │     ├─ icon.svg                      应用图标（矢量源文件）
   │     └─ icon.ico                      同上的 16/32/48/64/128/256 六尺寸打包版（exe 用）
   ├─ md_site_builder.py                  生成核心（python-markdown + pygments）
   ├─ doc_site_assets.py                  站点 CSS/JS（单一事实来源）
   ├─ md_doc_gui.spec                     独立版打包配置（PyInstaller）
   ├─ make_icon.py                        由 icon.svg 重新生成多尺寸 icon.ico（需本机 Edge）
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
组装 `releases/Markpage/` 与 `Markpage.zip`。环境变量 `MARKPAGE_PY311` 可指定 Python 路径。

## 应用图标

`scripts/webapp/ui/icon.svg` 是唯一源文件，窗口/任务栏从它取（`index.html` 里的 favicon）。
改了图之后重新生成 ico：

```bat
python scripts\make_icon.py
```

脚本用 Edge 无头**按每个尺寸原生渲染**矢量图（不是从大图缩），再手工打包成 ICO，
不依赖 Pillow 之类。exe 打包时 `md_doc_gui.spec` 用 `icon.ico` 作程序图标。

## 无头自检

验证依赖与代码是否完整（打包后尤其有用）：

```bat
Markpage.exe --selftest 某文档.md 某输出目录
:: 或源码： python scripts\md_doc_gui.py --selftest 某文档.md 某输出目录
```

结果写入「输出目录上级」的 `_selftest_result.txt`（PASS/FAIL + 引擎模式、页数等细节）。
自检现在走的是浏览器会走的同一批接口（静态资源 → 构建 → 产物经 HTTP 访问），
打包漏带 `webapp/ui` 导致的白屏会被它直接判 FAIL。
