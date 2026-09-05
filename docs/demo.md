# Markpage 示例文档

> 本文档本身即 Markpage 的输入样例，`demo_site/` 目录就是用它生成的站点。
> 重新生成：`python md_site_builder.py docs/demo.md --out docs/demo_site`

## 支持的能力一览

### 代码块（行号 / 语言标签 / 复制）

```csharp
public class StoryFlow
{
    public void Start() => Debug.Log("Hello Markpage");
}
```

```json
{ "theme": "auto", "lineNumbers": true, "copy": true }
```

### 表格

| 语法 | 效果 |
| ---- | ---- |
| `#` 一级标题 | 分组抽屉 |
| `##` 二级标题 | 独立页面 |
| `###` 三级标题 | 页内栏目（chips 跳转） |

### 文本样式

支持**加粗**、*斜体*、`行内代码`、[站内锚点跳转](#支持的能力一览)，
以及代码块右上角的一键复制。
