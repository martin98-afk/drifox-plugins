# docx-designer

docx / pptx 文档设计模式 — 独立窗口预览 Word 文档与 PowerPoint，页内拾取元素，锚点+文本+截图回填输入框，让大模型针对精确元素做修改。

## 功能

- **预览（docx）**：python-docx XML 流遍历解析 → 自生成 HTML（QWebEngineView 渲染）
  - 标题层级 / 段落 / 粗斜体下划线 / 列表
  - 表格（colspan / rowspan，vMerge + gridSpan）
  - 内嵌图片（data URI）
  - OMML 公式 HTML/CSS 模拟（上下标/分数/根号/nary，复杂结构降级带边框文本块）
- **拾取**：点「拾取」进入拾取态（hover 高亮 + crosshair），点击元素即回填：
  - 元素锚点（body 块索引，表格单元格 `idx:r{n}c{n}`）
  - 元素类型 / 样式 / 文本预览（≤200 字符）
  - 元素区域截图 PNG（存 `plugin_data/docx-designer/picks/`）
  - 连续拾取连续追加，Esc 退出，全程不抢输入框焦点
- **预览（pptx）**：python-pptx 解析 → 固定画布绝对定位渲染（每页一张 slide）
  - 文本框/占位符（字号/颜色/加粗/对齐/行距，版式占位符回退）、图片、表格、形状填充
  - 图表/媒体/动画降级为占位块（不渲染）
  - 幻灯片尺寸按 presentation.xml（EMU → pt），1:1 显示
- **入口**：`/docx-designer` 命令、`open_docx(path)` 工具、拖拽 docx/pptx 到窗口
- **锚点**：docx 为 body 块索引（表格单元格 `idx:r{n}c{n}`）；pptx 为 `幻灯片:元素`（0 起）

## 架构

```
ui/docx_parser.py   XML 流遍历 → 中间结构 Block（纯函数，可单测）
ui/html_renderer.py Block → HTML（data-anchor + QWebChannel 桥，纯函数，可单测）
ui/docx_window.py   窗口（工具栏/拖拽/缩放/状态栏）
ui/picker.py        Bridge + 拾取态 + 截图裁剪 + input.write 回填
ui/pptx_parser.py    python-pptx → 固定画布中间结构（slide/shape/文本框/表格/图片，纯函数）
ui/pptx_renderer.py  pptx 中间结构 → HTML（绝对定位，复用拾取/标注 JS）
tools/docx_tools.py  open_docx 工具
```

锚点契约：`Block["anchor"]` = body 级块索引（0 起）；表格单元格 `"<idx>:r{row}c{col}"`（col 为网格列号）。文档不修改则锚点稳定；模型按锚点在 python-docx 中定位元素（遍历 body 第 N 个 `w:p`/`w:tbl`）。

## 测试

```bash
python -m pytest plugins/docx-designer/tests/ -v
```

## 已知简化

- 窗口为浮动卡片单例（`register_floating_card` 机制约束），同一时刻一篇文档；再打开新文档即替换当前预览
- run 级样式只读直接 rPr，不做样式表继承推断
- 嵌套表格内容降级忽略
- pptx 主题色/渐变/阴影只取纯色，图表与媒体不渲染（占位提示）
- pptx 母版/版式只用于占位符几何与字号回退，动画与切换效果不呈现
- 工具侧打开窗口若遇非主线程调度需改主线程派发
