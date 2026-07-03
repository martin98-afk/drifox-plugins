# UI 卡片向外展开功能设计

**日期**: 2026-07-03
**状态**: 设计已审批

## 1. 概述

当前 DriFox 的 UI 浮动卡片只能在主窗口内部的 `TopCardContainer` / `BottomCardContainer` 中展开。本功能允许用户通过方向参数，将卡片作为无边框浮层面板展开到主窗口外部（上/下/左/右），提供更灵活的空间利用方式。

## 2. 使用方式

### 命令交互

所有通过 `register_floating_card` 注册的 UI 命令自动获得四个互斥方向参数：

```
/plugin-name              → 内部展开（现有行为，不变）
/plugin-name --up         → 窗口上方弹出无边框面板
/plugin-name --down       → 窗口下方弹出
/plugin-name --left       → 窗口左侧弹出
/plugin-name --right      → 窗口右侧弹出
```

- 参数是互斥的（mutex group `direction`），一次只能选一个方向
- 再次执行同一方向命令 toggle 关闭面板
- 内部与外部可同时显示，互不干扰

### 自动补全

用户在输入 `--` 时，命令 card 会自动弹出参数列表：

```
/plugin-name --
  ├── --up     窗口上方展开
  ├── --down   窗口下方展开
  ├── --left   窗口左侧展开
  └── --right  窗口右侧展开
```

## 3. 架构变更

### 3.1 新增文件

**`app/widgets/cards/floating/outward_card_panel.py`**

无边框浮层面板组件，负责：
- 渲染为独立于主窗口的 frameless QWidget
- 承载插件提供的卡片 widget
- 在指定方向定位到主窗口外沿
- 跟随主窗口 move/resize 事件
- 边界裁剪（不超出屏幕）
- 提供关闭按钮

### 3.2 修改文件

**`app/core/ui_plugin_registry.py`**

1. `_register_command_for_card` — 自动注入四个方向 flag 参数 + mutex_group
2. `_handler` — 解析 args 中的方向参数，分派到内部/外部展示
3. 新增 `_show_outward_card(card_id, direction)` 方法
4. 新增 `_outward_panels: Dict[Tuple[str, str], OutwardCardPanel]` 实例集合
5. `unload_plugin` 清理外部面板
6. 新增 `_make_context_provider` 提取为独立方法（现有代码已有类似逻辑）

## 4. OutwardCardPanel 详细设计

### 窗口属性
- `Qt.Window | Qt.FramelessWindowHint` — 无边框
- `Qt.WA_TranslucentBackground` — 半透明背景（阴影效果）
- `setAttribute(Qt.WA_ShowWithoutActivating)` — 显示时不夺走焦点

### UI 结构

```
┌──────────────────────────────────┐
│  ┌─[×]─────────────────────────┐ │  ← 标题区域（关闭按钮，10px 高）
│  ├──────────────────────────────┤ │
│  │                              │ │
│  │    卡片内容 widget           │ │  ← 主要内容区
│  │    (由插件 widget_class 实例化) │ │
│  │                              │ │
│  └──────────────────────────────┘ │
│  阴影边框 ──────────────────────  │
└──────────────────────────────────┘
```

### 尺寸策略

| 方向 | 宽度 | 高度 |
|------|------|------|
| `--up` | 主窗口宽度 × 0.9 | 自适应内容，最大屏幕高 × 0.6 |
| `--down` | 主窗口宽度 × 0.9 | 自适应内容，最大屏幕高 × 0.6 |
| `--left` | 自适应，最大 400px | 主窗口高度 × 0.8 |
| `--right` | 自适应，最大 400px | 主窗口高度 × 0.8 |

### 定位算法

```python
GAP = 4  # 面板与主窗口外沿的间距（px）

def calculate_position(direction, main_rect, panel_size, screen_rect):
    pw, ph = panel_size
    gap = GAP

    if direction == "up":
        x = main_rect.center().x() - pw // 2
        y = main_rect.top() - ph - gap
    elif direction == "down":
        x = main_rect.center().x() - pw // 2
        y = main_rect.bottom() + gap
    elif direction == "left":
        x = main_rect.left() - pw - gap
        y = main_rect.center().y() - ph // 2
    elif direction == "right":
        x = main_rect.right() + gap
        y = main_rect.center().y() - ph // 2

    # 边界裁剪：保证面板完全在屏幕内
    x = max(screen_rect.left(), min(x, screen_rect.right() - pw))
    y = max(screen_rect.top(), min(y, screen_rect.bottom() - ph))
    return (x, y)
```

### 窗口跟随

使用 `installEventFilter` 监听主窗口的 `QEvent.Move` 和 `QEvent.Resize`，自动重新计算位置。

窗口最小化时自动 `hide()`，恢复时自动 `show()` + `reposition()`。

### 生命周期管理

```python
# 创建
panel = OutwardCardPanel(
    main_window=mw,
    direction="up",
    widget_class=MarketplaceCard,
    context_provider=context_provider,
)
panel.show_panel()

# 关闭
panel.close()
panel.deleteLater()

# 复用（toggle）
if panel.isVisible():
    panel.close()
else:
    panel.show_panel()
```

## 5. 边界情况

| 场景 | 行为 |
|------|------|
| 外部面板已打开，再执行内部展开 | 内部 + 外部同时显示，互不干扰 |
| 主窗口移动/缩放 | 面板自动跟随重新定位 |
| 主窗口最小化 | 面板自动隐藏，恢复时重新显示 |
| 切换屏幕 | 面板重新定位到主窗口所在屏幕 |
| 屏幕空间不足 | `clamp_to_screen` 保证面板不超出可见区域 |
| 插件重载/卸载 | 清理所有该插件的外部面板 |
| 多窗口模式 | 每个窗口有独立的 `_outward_panels` 集合 |

## 6. 上下文注入

OutwardCardPanel 在实例化卡片 widget 后，需要注入上下文。采用与内部卡片一致的拉模型：

```python
ctx_provider = self._make_context_provider(card_info)
if hasattr(widget, "set_context_provider") and callable(widget.set_context_provider):
    widget.set_context_provider(ctx_provider)
elif hasattr(widget, "set_context") and callable(widget.set_context):
    widget.set_context(ctx_provider())
```

## 7. 实现计划

1. 创建 `outward_card_panel.py` — 无边框面板组件
2. 修改 `ui_plugin_registry.py` — 参数注入 + 方向分派 + 外部面板管理
3. 验证：所有现有 UI 插件命令自动获得方向参数
4. 测试：四种方向展开、边界裁剪、窗口跟随、多窗口隔离

## 8. 未纳入范围

- 外部面板的拖拽移动（后续可加）
- 外部面板的大小调整（后续可加）
- 多面板的层叠/避让策略（后续按需）
- 快捷键绑定方向展开
