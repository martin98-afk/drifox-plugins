# file-designer 框选批量拾取与组合标注设计

- 日期：2026-11-06
- 状态：已获用户批准的设计，待实现
- 前置阅读：`docs/superpowers/specs/2026-11-06-file-designer-design.md`（插件本体）

## 目标

file-designer 预览窗口的拾取/标注模式新增左键拖拽框选（marquee）：

- 拾取：单击选单个（现状保留），按住左键拖拽画框一次圈选多个元素，一张选框截图 + 逐元素回填输入框。
- 标注：框选多元素后一条注释挂一组元素（用户明确选择「一条注释挂一组」，每元素各一条方案否决）。

## 现状

- `_PICK_JS`（html_renderer.py）：document click → `closest('[data-anchor]')` → `__bridge.pick(anchor, x, y, w, h, preview)` 单元素回传。
- `_ANNOTATE_JS`：`window.__annotations` 条目 `{anchor, comment, seq, snippet}`；`__markAll/__renumber/__openNote/__closeNote` 全部单 anchor；桥槽 `annotate_added(anchor, comment, seq, snippet, x, y, w, h)`。
- `_VIEW_JS`：平移拖拽在 pick/annotate 态主动让位，框选无冲突。
- `docx_window.py`：`self._annotations` 持久化到 plugin_data JSON（`_save/_load_annotations`）；`_lookup_block(anchor)` 提供锚点上下文；`_send_annotations` 走 `format_annotations`。
- 六种格式（docx/pptx/xlsx/csv/xmind/mermaid）共用同一份 JS。

## 交互设计（新 `_MARQUEE_JS`，全格式共用）

- 仅 pick/annotate 态激活；左键 mousedown 起点记录，mousemove 位移 > 4px（与 `_VIEW_JS` 同阈值）显示 fixed 选框 div（accent 描边 + 半透明填充），mouseup 收集命中。
- 命中判定：`getBoundingClientRect()` 与选框矩形**任意相交**；fixed 坐标系天然限定当前视口。
- 位移 ≤ 4px = 单击，现有 click 逻辑完全不变。
- 真拖拽（moved）后抑制紧随的 click：mouseup 置 `window.__marqueeJustEnded = true`，click 监听开头检查并清除。
- 命中分流：
  - pick 态 N=1：复用现有单元素回传路径（与单击行为一致）。
  - pick 态 N≥2：`__bridge.pick_many(items_json, rx, ry, rw, rh)`，items 含各元素 anchor/rect/preview，矩形为选框。
  - annotate 态 N≥1：`__openNoteMulti(els)` 打开 note-box（定位选框旁）。
  - N=0：仅清除选框，不做事。
- 选框期间清除文本选区（复用 `_VIEW_JS` 手法）；Esc 退出模式逻辑不变；`#note-box` 区域内 mousedown 不起框。

## 数据模型（组合标注，方案 A：条目升级 anchors 数组）

- 新条目：`{anchors: [a1, a2, ...], comment, seq, snippet, shot}`；snippet 取首元素。
- 归一化：读取与注入 `__restored` 前，旧条目 `{anchor}` → `{anchors: [anchor]}`。纯函数放 `pick_format.py`（`normalize_annotations`），Python 侧统一入口 `_load_annotations` 调用；写出恒为 anchors 数组（数据只被本插件消费，不留旧字段）。
- note-box 编辑定位从 anchor 字符串改为 **seq**：单元素与组合统一按 seq 找条目（`data-editing` 存 seq）。
- 删除语义：编辑态删整条（组合删 = 整组去标记；单元素删行为不变）。
- 桥槽协议（页面 JS 与桥同步改，无外部消费者，无兼容负担）：
  - `pick_many(items_json: str, x, y, w, h)` 新增。
  - `annotate_added(anchors_json: str, comment, seq, snippet, x, y, w, h)`：首参 anchor → anchors JSON 串，pyqtSlot 签名不变（str→str）。
  - `annotate_updated(seq_str, comment)` / `annotate_deleted(seq_str)`：按 seq 定位。

## Python 侧改动

- `picker.py`：`DocxBridge` 加 `pick_many` 槽；`annotate_added/updated/deleted` 参数语义按上表调整。
- `docx_window.py`：
  - 新 `on_elements_picked(items, rect)`：按选框矩形裁**一张**截图（`capture_view_rect` 复用），逐元素 `format_pick` 连号追加回填，截图路径仅附首条；`_lookup_block(anchor)` 逐元素照常携带上下文；状态栏报「框选拾取 N 个元素」。
  - `on_annotation_added`：解析 anchors JSON 数组；`shot` 裁选框矩形。
  - `on_annotation_updated/deleted`：按 seq 匹配。
  - `_load_annotations`：读后过 `normalize_annotations`。
  - `_send_annotations` / `_clear_annotations` / `_reload_document`：逻辑不变，数据结构自适应。
- 批量回填文本拼装抽纯函数入 `pick_format.py`（输入：起始计数、文件路径、items、blocks、shot；输出：整段文本），不依赖 Qt，可单测。
- `on_element_picked`（单击路径）保持不变。

## 回填格式（pick_format.py）

- `format_pick` 不动。
- `format_annotations` 组合条目：注释行描述为多锚点连接（顿号分隔），超过 3 个显示前 3 + 「等 N 处」；snippet 用首元素文本。

```
📝 docx 标注 共 2 条 [path]
①[表格 #52 单元格 r1c1]、[表格 #52 单元格 r2c1] "首元素预览…"
  ↳ 注释：这批单元格一起说明…
  截图：pick_xxx.png
```

## 影响面

- JS 改动集中在 html_renderer.py：新增 `_MARQUEE_JS`、改造 `_PICK_JS`/`_ANNOTATE_JS`；`wrap_html`（generic_renderer 经此拼装）与 docx `render_full` 两处拼装点追加 `_MARQUEE_JS`。
- docx 分页 `_PAGINATE_JS` 重建 DOM 不受影响（marquee 监听挂 document，anchor 在最终 DOM 上，SVG 元素 `getBoundingClientRect` 有效）。
- 六种格式自动获得框选。

## 测试计划

- `tests/test_pick_format_formats.py`：组合条目 `format_annotations`（2 锚点、6 锚点截断）输出断言。
- 新增/扩展：`normalize_annotations` 旧格式归一化往返；批量回填纯函数拼装（计数连号、截图仅首条）。
- `tests/test_renderer.py`：断言 `_MARQUEE_JS` 关键片段存在、两处拼装点注入（跟随现有字符串断言水平）。

## 风险与边界

- 表格密集区框选会命中一串 cell 锚点：预期行为，框多大选多大。
- 一次框选限当前视口，跨页内容多次框选。
- 存量标注 JSON 兼容靠归一化单测兜底，老文件不得丢标注。
- mousemove 只更新选框几何，元素 rect 收集仅在 mouseup 一次，无性能风险。
