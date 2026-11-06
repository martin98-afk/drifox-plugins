# file-designer 设计文档

日期：2026-11-06 ｜ 状态：设计已获用户确认
前置：2026-11-03-docx-designer-design.md（docx/pptx 已落地，本设计在其上扩展并改名）

## 任务目标

docx-designer 升级为 file-designer：保留 docx/pptx 全部能力，新增 xmind、excel(xlsx/xlsm)、csv、mermaid 流程图的预览、拾取、标注、注入。注入 = 与 docx 现状一致：锚点 + 文本 + 截图回填输入框，不做文件写回。

## 需求决策记录（用户逐项确认）

| 决策点 | 结论 |
|---|---|
| 流程图格式 | Mermaid（.mmd / .mermaid），不含 drawio / vsdx |
| 注入语义 | 注入到对话（回填输入框），不提供写回工具 |
| xmind 形态 | 图形化导图（自绘 SVG），不还原原文件配色与自由布局 |
| excel 保真度 | 数据优先：值 + 合并单元格 + 列宽 + 多 sheet + 冻结首行，统一表格样式，不还原颜色字体 |
| 改名程度 | 彻底改名 file-designer + 旧接口兼容（open_docx 工具保留别名，数据目录自动迁移） |

## 方案对比（定案：A）

| 方案 | 做法 | 判断 |
|---|---|---|
| A. 统一 HTML 管线 + 格式注册表 | 每格式 parser/renderer 输出带 `data-anchor` 的 HTML，窗口/Picker/标注/截图全复用 | **采用**：拾取/标注/注入零复制 |
| B. 每格式独立窗口与拾取链 | 拾取/标注/截图实现 6 份 | 否：维护成本高 |
| C. 拆多个插件 | 违背「升级为一个插件」 | 否 |

## 1. 身份与迁移

- `git mv plugins/docx-designer plugins/file-designer`
- `plugin.json`：name → `file-designer`，version → `0.4.0`，description/keywords 扩为全格式
- 浮卡：`plugin_name`/`card_id` → `file-designer`，title「文件设计」；宿主自动注册 `/file-designer` 命令
- 数据迁移：注册时 `plugin_data/file-designer/` 不存在且 `plugin_data/docx-designer/` 存在 → 整目录复制（picks 截图、标注 JSON 沿用，标注按文件路径 hash，迁移后仍恢复）
- 市场：重跑 `generate_marketplace.py`；`downloads_cache.json` 中 docx-designer 下载量并入 file-designer；CHANGELOG 记迁移说明
- 不保留 `/docx-designer` 命令别名

## 2. 格式注册表与窗口分派

新增 `ui/formats.py`：

```python
FORMATS = {
    ".docx":    Spec("docx",    parse_docx,    render_docx),
    ".pptx":    Spec("pptx",    parse_pptx,    render_pptx),
    ".xmind":   Spec("xmind",   parse_xmind,   render_xmind),
    ".xlsx":    Spec("xlsx",    parse_xlsx,    render_sheet),
    ".xlsm":    Spec("xlsx",    parse_xlsx,    render_sheet),
    ".csv":     Spec("csv",     parse_csv,     render_sheet),
    ".mmd":     Spec("mermaid", parse_mermaid, render_mermaid),
    ".mermaid": Spec("mermaid", parse_mermaid, render_mermaid),
}
```

`docx_window.open_path` 的后缀 if 分支收敛为查表；`_blocks/_pptx_model` 泛化为 `_model`；打开对话框与拖拽白名单从 `FORMATS` 派生。

## 3. 各格式实现与锚点契约

| 格式 | 解析 | 渲染 | 锚点 | 拾取回填 |
|---|---|---|---|---|
| xmind | zip → `content.json`（XMind 2020+），回退 `content.xml`（XMind 8）→ 多 sheet + 主题树（标题/备注/标签） | 自绘 SVG：根居中、一级分支左右交替、贝塞尔连线、文本 28 字符换行 | `s{sheet}/n/{节点路径}` 如 `s0/n/0.2.1` | 节点标题 + 根到节点的层级路径 + 同级兄弟标题 |
| xlsx | openpyxl `data_only=True` 取值 + `merged_cells` + 列宽 | HTML 表格，多 sheet tab 页内切换，冻结首行，列宽按字符估算 | `s{sheet}!{列}{行}` 如 `s1!B3` | 单元格值 + 表头列名 + 整行内容 |
| csv | 编码链 `utf-8-sig → utf-8 → gb18030 → latin-1`；`csv.Sniffer` 探分隔符 | 复用 xlsx 的 table renderer（首行作表头） | `r{行}c{列}` / 整表 `table` | 单元格值 + 表头映射 + 整行 |
| mermaid | 读源码，`graph/flowchart` 类语法建行号索引 | 内嵌 `mermaid.min.js` 客户端渲染 SVG，明暗主题跟随；失败降级源码 + 错误 | `L{行号}` | 该行源码语句 + 节点/连线文本；点节点反查首次出现行 |

防护上限（超出截断并在状态栏提示）：xlsx 单 sheet 2000 行 × 200 列；csv 5000 行 × 200 列；xmind 800 节点。

## 4. 拾取 / 标注 / 注入复用

- `_BOOT_JS` / `_PICK_JS` / `_ANNOTATE_JS` 不动，新 renderer 吐出 `data-anchor` 元素即自动具备拾取 + 标注
- `pick_format.py` 按 mode 扩展描述头：`📎 xmind 拾取 #N` / `excel` / `csv` / `mermaid`，锚点规则说明按格式给示例
- 截图裁剪、`input.write` 回填、标注持久化（按文件路径 hash JSON）全部沿用

## 5. 工具与入口

`tools/docx_tools.py` → `tools/file_tools.py`：

- `open_file(path)`：全格式统一入口，按后缀分派
- `open_docx(path)`：保留，描述改为「打开文档/文件预览（兼容旧名）」，同一 impl
- 工具组「文档」保持

## 6. 依赖与资源

- `plugin.json` 依赖加 `openpyxl>=3.1.0`
- `assets/mermaid.min.js`：锁 v10.9.1 UMD（约 2.8MB，兼容 Qt5 WebEngine Chromium 87）；实装先经 Edge headless 验证渲染，不兼容降 v9.4.3
- 确认 `build_plugin_tarballs.py` 打包含 `assets/`，不含则补规则

## 7. 测试与验收

- 新增单测：`test_xmind_parser.py`、`test_xlsx_parser.py`、`test_csv_parser.py`、`test_mermaid_anchor.py`、`test_pick_format_formats.py`（纯函数无 Qt）
- 现有 docx/pptx 测试全绿为回归门槛
- 人工验收：6 类格式样例各做 打开→拾取→标注→发送→截图落盘
- 通过标准：每种格式回填文本含「文件绝对路径 + 锚点 + 上下文文本 + 截图路径」，模型凭锚点可定位

## 8. 风险

| 风险 | 缓解 |
|---|---|
| mermaid.js 与 Chromium 87 兼容性 | 先实测定版本，最坏降 v9 |
| xmind 自绘布局观感（文本宽度估算） | 中文 12px/字、英文 7px/字，超宽换行，先可用后美观 |
| 插件改名市场条目/下载统计断档 | 一次性迁移，先在市场侧核对 |
| openpyxl 大文件内存 | 行列上限 + 失败提示 |
