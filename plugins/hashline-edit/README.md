# hashline-edit — DriFox 插件

pi 式 **hashline 锚点编辑**工具插件：覆盖系统 `read` / `edit` / `multi_edit` 三个文件工具，
改用「行号 + 内容哈希」锚点定位（纯锚点模式），消除 oldString 匹配的歧义与误替换风险。

## 功能

| 工具 | 覆盖 | 说明 |
|------|------|------|
| `read` | 系统 read | 每行输出 `LINE#HASH:` 锚点前缀（pi 格式）；图片仍走 base64 视觉注入；记录 mtime 检测外部修改 |
| `edit` | 系统 edit | 纯锚点编辑：整行替换 / 行尾追加 / 行首插入 / 行内文本替换；成功后返回 diff + 新锚点块（链式编辑） |
| `multi_edit` | 系统 multi_edit | 批量锚点编辑：多编辑点对同一 pre-edit 快照校验、自底向上应用，任一陈旧则整体拒绝 |

## 安装

### 方式一：从插件市场安装

```bash
/plugin --install hashline-edit
```

### 方式二：复制到插件目录

```bash
cp -r plugins/hashline-edit ~/.drifox/plugins/
# 或 Windows
xcopy /E /I plugins\hashline-edit %USERPROFILE%\.drifox\plugins\hashline-edit
```

DriFox 启动时自动发现并加载。插件为 `type: user`，同名工具注册后**覆盖系统工具**
（user > system 优先级），无需额外声明；插件默认启用。

## 锚点协议

### read 输出格式

```text
#File: src/main.py (Lines 1-3 of 3)
1#ZM: import os
2#NW: from pathlib import Path
3#KT: def main():
```

- `LINE`：1 起始行号
- `HASH`：2-4 字符内容哈希（默认 2 字符）
- 哈希为 **16 字符字母表** `ZPMQVRWSNKTXJBYH` 编码（xxh32 低 4N 位，Python 实现用 zlib.crc32）
- **上下文哈希**：`hash = f(prev + curr + next)` 三行窗口
  → 相同行在不同上下文产生不同 hash；**编辑行 N 只影响 N-1/N/N+1 三个锚点**，
  其余行锚点保持稳定，长文件多次编辑无需整文件重读

### edit 参数

```text
edit(path="src/main.py", operations=[
  {"op": "replace", "anchor": "3#KT", "lines": ["def main():", "    print('hi')"]},
  {"op": "append",  "anchor": "1#ZM", "content": "  # 行尾追加"},
  {"op": "prepend", "anchor": "2#NW", "content": "import sys  # 行首插入"},
  {"op": "replace_text", "anchor": "3#KT", "content": '{"old": "main", "new": "run"}'},
])
```

| 字段 | 说明 |
|------|------|
| `op` | `replace`（整行替换，`lines` 为新行内容，空列表=删除）、`append`（行尾追加）、`prepend`（行首插入）、`replace_text`（行内文本替换） |
| `anchor` | 目标锚点 `LINE#HASH`（来自 read 输出） |
| `end` | 可选，仅 `replace`：区间结束锚点，替换/删除 `[anchor, end]` 整段 |
| `lines` | `replace` 的新行内容列表 |
| `content` | `append`/`prepend` 的文本；`replace_text` 时为 JSON 字符串 `{"old":..,"new":..}` |
| `textHint` | 可选第二因子：目标行内容前缀，防止陈旧锚点误编辑 |

### 防错机制

| 错误码 | 触发条件 | 行为 |
|--------|---------|------|
| `E_STALE_ANCHOR` | 锚点 hash 与当前文件不匹配 / 行号超界 / textHint 不匹配 | 拒绝编辑并提示重新 read，**绝不静默移位** |
| `E_INVALID_PATCH` | lines/content 含锚点显示前缀或 diff 标记；replace_text 的 old 不唯一或不存在；content 含换行 | 拒绝 |
| `E_NOOP_LOOP` | 连续 3 次相同的 no-op 编辑（内容未变化） | 报错，提示先 read 确认 |
| 外部修改 | read 后文件 mtime 变化 | 拒绝，提示重新 read |

### 链式编辑

`edit` / `multi_edit` 成功后返回 `--- Anchors A-B ---` 新锚点块（ToolResult.anchors 字段），
覆盖受影响行（编辑行及其相邻行）。LLM 可直接用块内新锚点继续编辑，无需重新 read：

```text
--- Anchors 2-4 ---
2#MQ: from pathlib import Path
3#JT: def main():
4#WV:     print('hi')
```

## 使用示例

```text
# 1. 读取文件拿锚点
read(path="src/main.py")

# 2. 用锚点精准编辑（参数命名对齐主程序预留接口：operations/anchor）
edit(path="src/main.py", operations=[{"op": "replace", "anchor": "3#KT", "lines": ["def run():"]}])

# 3. 用返回的新锚点块继续链式编辑
edit(path="src/main.py", operations=[{"op": "append", "anchor": "3#JT", "content": "  pass"}])

# 4. 批量编辑（自底向上，任一失败整体拒绝）
multi_edit(path="src/main.py", operations=[
  {"op": "replace_text", "anchor": "1#ZM", "content": '{"old": "os", "new": "sys"}'},
  {"op": "replace", "anchor": "5#KY", "lines": ["if __name__ == '__main__':"]},
])
```

## 与系统工具的关系

- **覆盖机制**：user 根插件同名注册即覆盖 system 同名工具（registry 跨根优先级 user > system）
- **契约对齐**：`danger`（read=safe，edit/multi_edit=dangerous）、
  `metadata`（`permission_arg=filePath`；read 另带 `provides_image`；edit 另带 `reconstruct_diff`）
  与系统基线一致
- **参数契约**：顶层 `operations` 数组 + 每项 `anchor`（=LINE#HASH），对齐主程序预留接口
  （chat_worker 畸形 JSON 提取、tool_call_parser `_rebuild_edit_json`、message_card
  reconstruct_diff 历史重建三条消费路径共用）；`edits`/`pos` 为旧参数兼容兜底
- **差异**：edit/multi_edit **无 oldString/newString 纯文本兼容路径**（用户拍板的纯锚点模式设计）
- 图片读取协议（base64 image_data）与系统行为一致；read 遇目录自动转 list（与系统一致）
- **已知边界**：同一次 `operations` 中多个编辑点作用于同一行的重叠编辑不做专门检测
  （按自底向上顺序应用，结果取决于编辑顺序；如需覆盖检测属后续增强）

## 架构

```
tools/
├── hashline_engine.py   # 纯逻辑：字母表/上下文哈希/锚点解析/格式化（无 IO 无状态）
├── file_io.py           # 路径解析/二进制检测/mtime 记录（window_state 窗口隔离）
├── snapshot.py          # 编辑校验（E_STALE_ANCHOR/E_INVALID_PATCH）/bottom-up 应用/
│                        #   no-op 循环检测（E_NOOP_LOOP）/新锚点块生成
├── read_tool.py         # hashline read（锚点输出 + 图片协议 + mtime）
└── edit_tool.py         # hashline edit + multi_edit（纯锚点 + 链式锚点 + diff）
```

- 完全自包含：仅依赖 Python 标准库（zlib/difflib），无第三方依赖
- 状态池放 `services.window_state`（窗口隔离；无则模块级降级）
- 渲染闭包 `_render_diff_body` 与系统 `_render_edit_diff_body` 同款实现
  （复用 `app.widgets.render_helpers` 的 `_render_diff_preview`，差异框与系统一致）

## 测试

```bash
python -m pytest tests/test_hashline_edit.py -q
```

覆盖：哈希稳定性/上下文区分/编辑局部性、锚点解析、四种 op 的 bottom-up 应用、
陈旧锚点拒绝、注入内容拒绝、no-op 循环、multi_edit 多编辑点、read/edit 全流程链式编辑。

## 校验

```bash
python tools/validate_plugins.py
python tools/generate_marketplace.py
```
