# file-designer

多格式文件设计模式 — 独立窗口预览 Word / PowerPoint / Excel / CSV / XMind / Mermaid 流程图，页内拾取元素并标注，锚点 + 文本 + 截图回填输入框，让大模型针对精确元素做修改。回填只进对话，不写回源文件。

## 支持格式与锚点

| 格式 | 后缀 | 解析要点 | 锚点 | 回填上下文 |
|---|---|---|---|---|
| docx | `.docx` | python-docx XML 流遍历 | `#N` = body 第 N 个块；单元格 `idx:r{n}c{n}`；`header` / `footer` | 块全文 / 单元格 + 所在行 + 表格全文 |
| pptx | `.pptx` | python-pptx 固定画布绝对定位 | `幻灯片:元素`（0 起） | 形状文本或表格全文 |
| xmind | `.xmind` | `content.json`（XMind 2020+），回退 `content.xml`（XMind 8）→ 多 sheet + 主题树 | `s{sheet}/n/{节点路径}`，如 `s0/n/0.2.1` | 节点标题 + 根到节点层级路径 + 同级兄弟 + 备注 |
| xlsx | `.xlsx` `.xlsm` | openpyxl `data_only=True`，合并单元格 / 列宽 / 多 sheet | `s{sheet}!{列}{行}`，如 `s1!B3` | 单元格值 + 表头列名 + 整行内容 |
| csv | `.csv` | 编码链 `utf-8-sig → utf-8 → gb18030 → latin-1` + `csv.Sniffer` 探分隔符 | `r{行}c{列}`（均 0 起，第 0 行表头）；`table` = 整表 | 单元格值 + 表头映射 + 整行 / 全表 |
| mermaid | `.mmd` `.mermaid` | 源码按行建索引，识别 `graph` / `flowchart` 等 | `L{行号}`（1 起） | 该行源码 + 图类型 + 上下文语句 |

防护上限（超出截断并在状态栏提示）：xlsx 单 sheet 2000 行 × 200 列；csv 5000 行 × 200 列；xmind 800 节点。

## 功能

- **预览（docx）**：python-docx XML 流遍历解析 → 自生成 HTML（QWebEngineView 渲染）
  - 标题层级 / 段落 / 粗斜体下划线 / 列表
  - 表格（colspan / rowspan，vMerge + gridSpan）
  - 内嵌图片（data URI）
  - OMML 公式 HTML/CSS 模拟（上下标/分数/根号/nary，复杂结构降级带边框文本块）
- **预览（pptx）**：python-pptx 解析 → 固定画布绝对定位渲染（每页一张 slide）
  - 文本框/占位符（字号/颜色/加粗/对齐/行距，版式占位符回退）、图片、表格、形状填充
  - 版式/母版非占位符形状垫底渲染（背景图/装饰件，showMasterSp="0" 时跳过母版），背景填充链 slide→layout→master（支持图片填充）
  - 图片按 blob 哈希去重；大 HTML（>1.5MB）自动改走本地文件加载（setHtml 超 ~2MB 静默不渲染）
  - 图表/媒体/动画降级为占位块（不渲染）
- **预览（xmind）**：自绘 SVG，根居中、一级分支左右交替、贝塞尔连线、文本按宽度估算换行；不还原原文件配色与自由布局
- **预览（xlsx / csv）**：统一 HTML 表格，多 sheet 页内 tab 切换、冻结首行、合并单元格、列宽按字符估算；数据优先，不还原颜色字体
- **预览（mermaid）**：内嵌 `assets/mermaid.min.js`（v10.9.1 UMD，3.3MB）客户端渲染 SVG，明暗主题跟随；渲染失败降级为源码 + 错误提示。Edge 156 headless `--dump-dom --virtual-time-budget` 离屏实测渲染成功，SVG 节点挂 `L{行号}` 锚点；Qt5 WebEngine / Chromium 87 兼容性尚未在宿主内实测
- **拾取**：点「拾取」进入拾取态（hover 高亮 + crosshair），点击元素即回填：
  - 文件绝对路径（模型可直接用工具重新打开）
  - 元素锚点 + 类型/样式描述 + 上下文文本
  - 元素区域截图 PNG（存 `plugin_data/file-designer/picks/`）
  - 连续拾取连续追加，Esc 退出，全程不抢输入框焦点
  - 首次回填附锚点规则说明
- **标注**：「标注」态点击元素弹注释框，角标编号；按文件路径 hash 持久化 JSON，重开恢复；「≡ → 发送标注」把全部注释一次性回填，供模型逐条按锚点修改
- **入口**：`/file-designer` 命令、`open_file(path)` 工具（`open_docx` 兼容旧名）、拖拽受支持格式到窗口、系统「打开」受支持后缀时拦截进预览
- **迁移**：注册时 `plugin_data/file-designer/` 不存在且 `plugin_data/docx-designer/` 存在 → 整目录复制，旧 picks 截图与标注沿用

## 架构

```
ui/formats.py        格式注册表（后缀 → mode / parse / render）+ 旧数据目录迁移
ui/docx_parser.py    XML 流遍历 → 中间结构 Block（纯函数，可单测）
ui/html_renderer.py  Block → HTML（data-anchor + QWebChannel 桥，纯函数，可单测）
ui/docx_window.py    窗口（打开分派 / 拖拽 / 缩放 / 状态栏 / 拾取标注接线）
ui/picker.py         Bridge + 拾取态 + 截图裁剪 + input.write 回填
ui/pick_format.py    按 mode 组装回填文本与标注发送文本（纯函数，可单测）
ui/pptx_parser.py    python-pptx → 固定画布中间结构（纯函数）
ui/pptx_renderer.py  pptx 中间结构 → HTML（绝对定位，复用拾取/标注 JS）
ui/xmind_parser.py   content.json / content.xml → 主题树 model + lookup（纯函数）
ui/xmind_renderer.py xmind model → 自绘 SVG HTML（data-anchor）
ui/sheet_parser.py   openpyxl / csv → 表格 model + lookup（纯函数）
ui/sheet_renderer.py 表格 model → HTML（多 sheet tab + data-anchor）
ui/mermaid_parser.py mermaid 源码 → 行索引 model + lookup（纯函数）
ui/mermaid_renderer.py mermaid model → HTML（mermaid.min.js + 源码行 data-anchor）
ui/external_open.py  系统打开重定向 + 后缀白名单（从 formats 派生）
tools/file_tools.py  open_file 工具 + open_docx 兼容别名
assets/mermaid.min.js Mermaid UMD（v10.9.1，已验 Edge headless；Chromium 87 待宿主实测）
```

共享契约（`ui/formats.py`）：通用格式 `parse(str(path)) -> model`，model 含 `mode` 与 `lookup(anchor) -> dict|None`；`render(model, *, outer, accent, restored) -> HTML`。HTML 必须内联 `<script src="qrc:///qtwebchannel/qwebchannel.js"></script>` + `html_renderer._BOOT_JS/_PICK_JS/_ANNOTATE_JS` + note-box DOM，可拾取元素带 `data-anchor`。docx / pptx 保留历史专用分支（`parse=None`）。

`lookup` 返回的 block 结构按 `pick_format._generic_block_lines` 消费：`xmind_node`（path / siblings / text / note）、`sheet_cell`（sheet / header / text / row_text）、`sheet_table`（rows）、`mermaid_line`（diagram_type / text / context）。

docx 锚点契约：`Block["anchor"]` = body 级块索引（0 起）；表格单元格 `"<idx>:r{row}c{col}"`（col 为网格列号）。文档不修改则锚点稳定；模型按锚点在 python-docx 中定位元素（遍历 body 第 N 个 `w:p`/`w:tbl`）。

## 测试

```bash
python -m pytest plugins/file-designer/tests/ -q --noconftest
```

项目根 `tests/conftest.py` 强依赖 PyQt5，插件纯函数单测须带 `--noconftest`；插件目录无 `__init__.py`，测试按文件路径 `importlib.util.spec_from_file_location` 加载。渲染器有相对导入时须构造包 `file_designer_ui` 注册到 `sys.modules` 再加载。

## 已知简化

- 窗口为浮动卡片单例（`register_floating_card` 机制约束），同一时刻一个文件；再打开新文件即替换当前预览
- 注入只回填对话输入框，不提供任何写回文件工具
- xmind 不还原原文件配色 / 自由布局 / 关系线 / 标记，超 800 节点截断
- xlsx / csv 数据优先，不还原颜色字体与公式（公式取缓存值），超上限截断
- mermaid 只建行号索引，不做完整 AST；点击节点反查首次出现行；v10.9.1 含 ES2020+ 语法，Chromium 87 若不支持需降级到 v9.4.3，库缺失或初始化失败时自动显示源码视图
- docx run 级样式只读直接 rPr，不做样式表继承推断；嵌套表格内容降级忽略
- pptx 主题色/渐变/阴影只取纯色，图表与媒体不渲染（占位提示）；母版/版式占位符只用于几何与字号回退；动画与切换效果不呈现
- 工具侧打开窗口若遇非主线程调度需改主线程派发
