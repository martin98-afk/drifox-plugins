# project-side-rail — 响应式项目侧栏

悬浮在**侧边栏（Tab 列表）与右边圆角矩形（对话区）之间**的 dock widget，支持响应式切换：

- **窄模式**（宽度 < 160px）：仅显示项目彩色 icon 列，最小可缩到 40px
- **宽模式**（宽度 ≥ 160px）：嵌入主程序既有 `ProjectSelectorCardContent`，完整功能

通过 dockSplitter 拖拽宽度实时切换；底部"+"按钮新建项目。

## 功能

- 竖向排列所有项目（彩色缩写方块 24×24 squircle）
- 单击切换项目（走主程序既有 `_on_project_selected` 路径，与既有项目卡片完全等价）
- 当前项目左侧 3px 强调条
- hover 显示 tooltip（项目名 + 工作目录）
- 右键菜单：打开项目根目录 / 复制路径
- 底部"+"按钮新建项目（弹 QInputDialog → 走主程序既有 `_on_new_project_created`）
- 主题色 + 字体跟随主程序 context
- 多 Tab 隔离：信号动态分派到当前活跃 Tab 的 main_widget

## 位置

通过 `register_floating_card(container="left")` 挂载到 `TabManagerWindow` 的左侧停靠区
（`_global_left_container`），视觉上正好位于：

```
┌──────────┬──┬────────────────────┐
│ Tab 列表 │📂│  对话区（圆角矩形）│
│ (侧边栏) │+│                    │
└──────────┴──┴────────────────────┘
```

## 数据源（**完全复用主程序，不新建存储**）

| 数据 | 来源 |
|------|------|
| 项目列表 | `main_widget.history_manager.get_projects()` |
| 当前项目 | `main_widget._current_project` |
| 项目工作目录 | `main_widget.backend.memory_manager.get_working_directory()` |
| 切换项目 | `main_widget._on_project_selected()`（既有稳定 slot） |
| 新建项目 | `main_widget._on_new_project_created()` |

## 复用算法（与主程序 `project_selector_card` 行为对齐）

- **首字母** — `extract_project_initials`
- **项目色** — `get_project_color`（HSL 全空间 CRC32 哈希）
- **图标尺寸** — 24×24 squircle 5px radius（与 `_SquareAvatar` 一致）
- **行高** — 30px（与 `ProjectItem._SINGLE_LINE_HEIGHT` 一致）
- **间距** — 1px（与 `ProjectItem` 一致）
- **滚动条** — QScrollBar 4px 宽 + 圆角 handle + hover 加宽（与 `get_unified_scrollbar_style` 一致）

两个算法独立实现以避免 import 主程序私有模块。

## 主程序改动（已申请用户授权）

`app/widgets/cards/card_container.py:33` —— `_DOCK_MIN_H: 300 → 40`

旧值 300 是历史安全下限，限制了所有 LEFT/RIGHT 停靠区的最小宽度。新值 40 让卡片可以通过自己的 `minimumWidth()` 自由声明最小宽度。已有的大卡片（context-usage-stats setMinimumWidth=300 等）仍被 `visible_cards_min_axis` 尊重。

## 组件结构

```
project-side-rail/
├── .drifox-plugin/
│   └── plugin.json
├── ui/
│   ├── __init__.py           ← register_ui(registry)
│   └── project_rail.py       ← ProjectSideRailCard / _ProjectIcon / ProjectSideRailNarrow / ProjectSideRailFull
├── icons/
│   └── add.svg               ← 新建项目按钮 SVG 图标
├── icon.svg
├── icon_dark.svg
└── README.md
```

## 已知约束

- 与主程序已有「项目切换」卡片共存：项目侧栏是**导航 + 新建**，项目卡片是**管理 + 高级操作**（归档、导出、文件拖入等仍走顶部卡片）
- 多窗口隔离天然继承：每个 Tab 通过 context provider 动态解析自己的 main_widget