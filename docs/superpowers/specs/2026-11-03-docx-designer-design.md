# docx-designer 设计文档

日期：2026-11-03 ｜ 状态：设计已获用户确认

## 任务目标

DriFox UI 插件：独立窗口预览 docx 文档，页内拾取元素，回填（文本+锚点+截图）到输入框；修改完全交给模型，插件只做「预览 + 拾取回填」。

## 需求决策记录（用户逐项确认）

| 决策点 | 结论 |
|---|---|
| 修改闭环 | 拾取回填即止，不做文件写回、不做所见即所得 |
| 载体 | 独立窗口（同 browser），单窗口单文档，可多开 |
| 渲染路线 | python-docx 解析 → 自生成 HTML → QWebEngineView |
| 文档类型 | 普通文章、表格、OMML 公式、图文混排，全部支持 |
| 回填内容 | 文本 + 锚点 + 元素截图 |
| 公式渲染 | HTML/CSS 模拟（sSub/sSup/f/rad/nary），复杂结构降级文本块 |
| 拾取机制 | 页面内 JS 点击监听（HTML 自生成，挂 data-anchor 即可） |
| 解析层 | XML 流遍历（w:p/w:tbl 顺序真实）+ python-docx API 读 run 样式 |

## 目录结构

```
plugins/docx-designer/
├── .drifox-plugin/plugin.json   # dependencies.pip: python-docx；capabilities: input.read, input.write
├── __init__.py                  # 注册 tool + 窗口入口
├── README.md / icon.svg / icon_dark.svg
├── tools/docx_tools.py          # open_docx(path) 工具，供模型调用
└── ui/
    ├── docx_window.py           # 窗口：工具栏 + QWebEngineView + 状态栏
    ├── docx_parser.py           # XML 流遍历 → 中间结构（纯函数）
    ├── html_renderer.py         # 中间结构 → HTML（纯函数）
    └── picker.py                # JS 点击 → 锚点 → 截图 → 回填
```

## 数据契约

锚点 = body 级块索引（0 起）：段落/标题/图片 `"12"`；表格单元格 `"12:r2c3"`。文档不改则稳定。

中间结构 `Block`：`kind(heading|paragraph|table|image)`、`index`、`style`(pStyle 名)、`text`、`level`、`runs[]`（text/bold/italic/underline）、`rows[][]`（含 colspan/rowspan）、`image`(data URI)、`math`(OMML 结构)。docx_parser 产出，html_renderer 消费，picker 按锚点回查。

回填文本（`input.write(text, append=True, focus=False)`，首条 append=False 覆盖）：

```
📎 docx 拾取 #N [文件名.docx]
[段落 #12 | Heading 1] "1. 技术领域"
[表格 #15 单元格 r2c3] "参数值 0.82"
截图：<picks 绝对路径>
```

截图：`view.grab()` 全视口 → 按 `getBoundingClientRect` 裁剪 → PNG 存 `storage.data_dir` 自拼 `plugin_data/docx-designer/picks/`。

## 渲染器

自生成单页 HTML，CSS 内嵌：白纸居中 + 页边距近似 + 衬线正文。规则：

- heading：pStyle「Heading N」→ h1-h4；普通段落 p；`numPr` 近似 ol/ul
- runs：bold→strong、italic→em、underline→u
- 表格：`gridSpan`→colspan、`vMerge`→rowspan
- 图片：blip rId → part blob → data URI 内嵌
- OMML：递归转 HTML/CSS（m:sSub→sub、m:sSup→sup、m:f→分数、m:rad→√+上划线、m:nary→Σ/∫ 带上下标）；未覆盖结构降级为带边框文本块
- 块级元素挂 `data-anchor`；拾取态 body 加 class，hover 高亮 + 点击选中

## 窗口交互

工具栏：打开文件、拾取开关、字号缩放；顶栏文件名；拖拽 docx 打开。拾取态连续点击连续回填，Esc 退出，状态栏「已回填 N 个元素」。

## 环境事实与验证

- 宿主全程 PyQt5，插件同栈；`input.write(text, append, focus)` 纯文本，截图靠「存盘 + 路径入回填文本」（同 browser 惯例）
- 本机无可运行 PyQt5：docx_parser / html_renderer 纯函数用系统 Python + python-docx 单测（最小 docx 覆盖标题/表格/合并/OMML/图片）；UI 层 py_compile + ruff 静态校验；同步 `~/.drifox/plugins/docx-designer/` 后宿主实测（删 `__pycache__` 防 pyc 秒级 mtime 旧字节码）
- OMML 兼容性可参考 plugins/omml-docx 的已有沉淀（oMathPara 表格中断等）
