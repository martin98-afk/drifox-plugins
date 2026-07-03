# UI 卡片向外展开功能 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 DriFox 所有 UI 浮动卡片增加向外展开能力（上下左右四个方向），通过互斥方向参数控制

**Architecture:** 在 `app/widgets/cards/floating/outward_card_panel.py` 新建无边框浮层面板组件；在 `app/core/ui_plugin_registry.py` 中为所有自动注册的 UI 命令注入 `--up/--down/--left/--right` 互斥方向参数，并在 handler 中根据参数分派到内部或外部展示。

**Tech Stack:** PyQt5 (QWidget, Qt.Window, FramelessWindowHint), qfluentwidgets

---

### Task 1: 创建 OutwardCardPanel 组件

**Files:**
- Create: `app/widgets/cards/floating/outward_card_panel.py`

**Overview:**
OutwardCardPanel 是一个无边框、半透明背景的 QWidget 弹出面板，用于在 DriFox 主窗口外部展示 UI 卡片内容。它负责：
1. 创建为独立 frameless 窗口
2. 实例化插件提供的卡片 widget 并注入上下文
3. 根据方向定位到主窗口外沿
4. 跟踪主窗口移动/缩放自动重定位
5. 提供关闭按钮
6. 主窗口最小化时自动隐藏，恢复时重新显示

- [ ] **Step 1: 创建文件骨架和类定义**

```python
# -*- coding: utf-8 -*-
"""
OutwardCardPanel — 无边框浮层面板，在主窗口外部展示 UI 卡片

支持方向：up/down/left/right
自动跟随主窗口移动/缩放
半透明背景 + 阴影边框 + 关闭按钮
"""

from typing import Callable, Dict, Optional

from PyQt5.QtCore import QEvent, QRect, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPainterPath
from PyQt5.QtWidgets import QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget


class OutwardCardPanel(QWidget):
    """无边框浮层面板，在主窗口外部展示 UI 卡片"""

    closed = pyqtSignal()  # 面板关闭信号

    # 面板与主窗口外沿间距 (px)
    GAP = 4

    def __init__(
        self,
        main_window: QWidget,
        direction: str,
        widget_class: type,
        context_provider: Optional[Callable[[], Dict]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._main_window = main_window
        self._direction = direction  # "up" / "down" / "left" / "right"
        self._widget_class = widget_class
        self._context_provider = context_provider
        self._content_widget: Optional[QWidget] = None
        self._following = False  # 是否已开始跟踪主窗口

        self._setup_window()
        self._setup_ui()
        self._create_content_widget()
        self._start_following()

    def _setup_window(self):
        """配置窗口属性：无边框、半透明、工具窗口"""
        self.setWindowFlags(
            Qt.Window
            | Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_DeleteOnClose)

    def _setup_ui(self):
        """构建 UI 结构：阴影 → 背景 → 关闭按钮 → 内容区"""
        # ── 主布局（含阴影边距）──
        shadow_margin = 12
        layout = QVBoxLayout(self)
        layout.setContentsMargins(shadow_margin, shadow_margin, shadow_margin, shadow_margin)
        layout.setSpacing(0)

        # ── 背景容器（白色/主题色底 + 圆角）──
        self._bg_widget = QWidget(self)
        self._bg_widget.setObjectName("panelBg")
        self._bg_widget.setStyleSheet(self._bg_stylesheet())
        self._bg_layout = QVBoxLayout(self._bg_widget)
        self._bg_layout.setContentsMargins(0, 0, 0, 0)
        self._bg_layout.setSpacing(0)

        # ── 标题栏（关闭按钮）──
        title_bar = QWidget()
        title_bar.setFixedHeight(28)
        title_bar.setStyleSheet("background: transparent;")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(8, 0, 8, 0)
        title_layout.addStretch()

        self._close_btn = QLabel("✕")
        self._close_btn.setFixedSize(20, 20)
        self._close_btn.setAlignment(Qt.AlignCenter)
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.setStyleSheet("""
            QLabel {
                color: rgba(128,128,128,0.6);
                font-size: 14px;
                background: transparent;
                border-radius: 10px;
            }
            QLabel:hover {
                color: white;
                background: rgba(255,60,60,0.6);
            }
        """)
        self._close_btn.mousePressEvent = lambda e: self.close()
        title_layout.addWidget(self._close_btn)
        self._bg_layout.addWidget(title_bar)

        # ── 内容区占位 ──
        self._content_container = QWidget()
        self._content_container.setStyleSheet("background: transparent;")
        self._content_layout = QVBoxLayout(self._content_container)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._bg_layout.addWidget(self._content_container, 1)

        layout.addWidget(self._bg_widget)

        # ── 阴影效果 ──
        shadow = QGraphicsDropShadowEffect(self._bg_widget)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 4)
        self._bg_widget.setGraphicsEffect(shadow)

    def _bg_stylesheet(self) -> str:
        """返回背景容器的样式表（支持主题色）"""
        from app.utils.design_tokens import Colors
        Colors.refresh()
        bg_color = Colors.CARD_BG
        border_color = Colors.BORDER
        return f"""
            #panelBg {{
                background: {bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
        """

    def _create_content_widget(self):
        """实例化卡片 widget 并注入上下文"""
        widget = self._widget_class(parent=self._content_container)
        self._content_layout.addWidget(widget)
        self._content_widget = widget

        # 注入上下文（与 _show_floating_card 一致的拉模型）
        if self._context_provider:
            if hasattr(widget, "set_context_provider") and callable(widget.set_context_provider):
                widget.set_context_provider(self._context_provider)
            elif hasattr(widget, "set_context") and callable(widget.set_context):
                widget.set_context(self._context_provider())
            else:
                widget._card_context = self._context_provider()
                widget._card_context_provider = self._context_provider

    # ── 定位 ──

    def _calculate_geometry(self) -> QRect:
        """根据方向和主窗口位置计算面板几何"""
        mw = self._main_window
        main_rect = mw.frameGeometry()
        screen = mw.screen()
        screen_rect = screen.availableGeometry() if screen else mw.geometry()

        # 计算期望尺寸
        if self._direction in ("up", "down"):
            # 上下：宽度按主窗口比例，高度自适应
            target_w = int(main_rect.width() * 0.9)
            max_w = screen_rect.width() - 2 * self.GAP
            panel_w = min(target_w, max_w)
            # 先给一个初始高度让内容自适配
            panel_h = 400
        else:
            # 左右：宽度自适应，高度按主窗口比例
            target_w = min(400, screen_rect.width() // 3)
            panel_w = max(200, target_w)
            panel_h = int(main_rect.height() * 0.8)

        # 先设宽度让内容计算合适高度
        self.setFixedWidth(panel_w)

        # 适配内容高度
        if self._content_widget:
            self._content_widget.adjustSize()
            # 标题栏 28px + 阴影 margin 12*2
            content_h = self._content_widget.sizeHint().height()
            panel_h = min(content_h + 28 + 24, int(screen_rect.height() * 0.85))
            panel_h = max(panel_h, 100)

            if self._direction in ("left", "right"):
                panel_h = max(panel_h, int(main_rect.height() * 0.4))

        self.setFixedHeight(panel_h)

        # 计算位置
        pw, ph = panel_w, panel_h
        gap = self.GAP

        if self._direction == "up":
            x = main_rect.center().x() - pw // 2
            y = main_rect.top() - ph - gap
        elif self._direction == "down":
            x = main_rect.center().x() - pw // 2
            y = main_rect.bottom() + gap
        elif self._direction == "left":
            x = main_rect.left() - pw - gap
            y = main_rect.center().y() - ph // 2
        elif self._direction == "right":
            x = main_rect.right() + gap
            y = main_rect.center().y() - ph // 2
        else:
            x, y = main_rect.right() + gap, main_rect.top()

        # 边界裁剪（保证面板不超出屏幕）
        x = max(screen_rect.left(), min(x, screen_rect.right() - pw))
        y = max(screen_rect.top(), min(y, screen_rect.bottom() - ph))

        return QRect(x, y, pw, ph)

    def reposition(self):
        """重新计算并设置面板位置"""
        geo = self._calculate_geometry()
        self.setGeometry(geo)

    # ── 窗口跟踪 ──

    def _start_following(self):
        """开始跟踪主窗口的移动/缩放/最小化事件"""
        if self._following:
            return
        self._following = True
        self._main_window.installEventFilter(self)

    def _stop_following(self):
        """停止跟踪"""
        if self._following:
            self._main_window.removeEventFilter(self)
            self._following = False

    def eventFilter(self, obj, event):
        if obj is self._main_window:
            if event.type() == QEvent.Move:
                self.reposition()
            elif event.type() == QEvent.Resize:
                # 缩放后延迟重算（等待布局稳定）
                QTimer.singleShot(50, self.reposition)
            elif event.type() == QEvent.WindowStateChange:
                if self._main_window.isMinimized():
                    self.hide()
                elif self._main_window.isVisible() and not self.isVisible():
                    self.reposition()
                    self.show()
        return super().eventFilter(obj, event)

    # ── 显示/隐藏 ──

    def show_panel(self):
        """计算位置并显示面板"""
        self.reposition()
        self.show()
        self.raise_()

    def closeEvent(self, event):
        self._stop_following()
        self.closed.emit()
        super().closeEvent(event)
```

- [ ] **Step 2: 验证文件语法**

```bash
cd D:/work/DriFoxx && python -c "import ast; ast.parse(open('app/widgets/cards/floating/outward_card_panel.py').read()); print('OK')"
# 或使用 pyright
cd D:/work/DriFoxx && python -m pyright app/widgets/cards/floating/outward_card_panel.py
```
Expected: 无语法错误

- [ ] **Step 3: 更新 `floating/__init__.py` 导出**

修改 `app/widgets/cards/floating/__init__.py`：

```python
# -*- coding: utf-8 -*-
from .outward_card_panel import OutwardCardPanel

__all__ = ["OutwardCardPanel"]
```

---

### Task 2: 修改 UIPluginRegistry — 方向参数注入

**Files:**
- Modify: `app/core/ui_plugin_registry.py`

**Overview:**
1. 在 `_register_command_for_card` 中为命令注入四个互斥方向参数
2. 修改 handler 解析 args 中的方向参数
3. 新增 `_show_outward_card` 方法 + `_outward_panels` 集合
4. 卸载插件时清理外部面板

- [ ] **Step 1: 修改 `_register_command_for_card` — 注入方向参数**

```python
def _register_command_for_card(self, card_info: FloatingCardInfo) -> None:
    """为浮动卡片自动注册对应 FUNCTION 命令"""
    from app.core.command_manager import CommandManager, CommandType, CommandParameter
    from app.core.builtin_commands import FunctionCommandHandlers

    # 命名空间规则（保持不变）...
    if ":" in card_info.card_id:
        cmd_name = card_info.card_id
    elif card_info.plugin_name == "system" or card_info.card_id == card_info.plugin_name:
        cmd_name = card_info.card_id
    else:
        cmd_name = f"{card_info.plugin_name}:{card_info.card_id}"

    cmd_mgr = CommandManager.get_instance()
    if cmd_mgr.has_command(cmd_name):
        return

    # 构造方向参数（互斥组 "direction"）
    direction_params = [
        CommandParameter(
            name="--up",
            description="在窗口上方展开",
            param_type="flag",
            mutex_group="direction",
        ),
        CommandParameter(
            name="--down",
            description="在窗口下方展开",
            param_type="flag",
            mutex_group="direction",
        ),
        CommandParameter(
            name="--left",
            description="在窗口左侧展开",
            param_type="flag",
            mutex_group="direction",
        ),
        CommandParameter(
            name="--right",
            description="在窗口右侧展开",
            param_type="flag",
            mutex_group="direction",
        ),
    ]

    cmd_mgr.register(
        name=cmd_name,
        command_type=CommandType.FUNCTION,
        description=card_info.title or f"打开 {card_info.card_id}",
        argument_hint="",
        parameters=direction_params,
    )
    self._ui_command_names.add(cmd_name)

    # 注册处理器：解析方向参数
    def _handler(args: str, cid=card_info.card_id):
        direction = None
        for d in ("--up", "--down", "--left", "--right"):
            # 解析 args 中的 flag 参数（args 是以空格分隔的参数字符串）
            if d in args.strip().split():
                direction = d[2:]  # "up" / "down" / "left" / "right"
                break
        if direction:
            self._show_outward_card(cid, direction)
        else:
            self._show_floating_card(cid)

    FunctionCommandHandlers.register(cmd_name, _handler)
```

- [ ] **Step 2: 添加 `_outward_panels` 属性和 `_show_outward_card` 方法**

在 `__init__` 方法中新增 `_outward_panels`：

```python
def __init__(self):
    # ... 现有初始化代码 ...
    self._outward_panels: Dict[Tuple[str, str], Any] = {}  # {(card_id, direction): OutwardCardPanel}
```

新增 `_show_outward_card` 方法（放在 `_show_floating_card` 后面）：

```python
def _show_outward_card(self, card_id: str, direction: str) -> None:
    """以向外展开的方式显示卡片

    Args:
        card_id: 卡片 ID
        direction: 方向 "up" / "down" / "left" / "right"
    """
    mw = self._main_widget
    if mw is None:
        return

    card_info = self._floating_cards.get(card_id)
    if card_info is None:
        return

    # 管理外部面板实例（按 card_id + direction 隔离）
    key = (card_id, direction)
    panel = self._outward_panels.get(key)

    if panel is not None:
        # 已存在 → toggle 显示/隐藏
        if panel.isVisible():
            panel.close()
        else:
            panel.show_panel()
        return

    # 创建新面板
    from app.widgets.cards.floating import OutwardCardPanel

    panel = OutwardCardPanel(
        main_window=mw,
        direction=direction,
        widget_class=card_info.widget_class,
        context_provider=self._make_context_provider(card_info),
    )
    self._outward_panels[key] = panel
    panel.closed.connect(lambda: self._outward_panels.pop(key, None))
    panel.show_panel()
```

- [ ] **Step 3: 修改 `unload_plugin` — 清理外部面板**

在 `unload_plugin` 方法中找到清理 floating cards 的部分，添加外部面板清理逻辑：

```python
def unload_plugin(self, plugin_name: str) -> bool:
    # ... 现有代码 ...
    # 清理 floating cards + 对应命令
    cards_to_remove = [cid for cid, info in self._floating_cards.items() if info.plugin_name == plugin_name]
    for cid in cards_to_remove:
        # 清理该卡片的外部面板
        keys_to_remove = [k for k in self._outward_panels if k[0] == cid]
        for k in keys_to_remove:
            panel = self._outward_panels.pop(k, None)
            if panel is not None:
                try:
                    panel.close()
                except RuntimeError:
                    pass

        self._unregister_command_for_card(cid)
        self._floating_cards.pop(cid, None)
        # ... 其余现有代码 ...
```

- [ ] **Step 4: 验证语法**

```bash
cd D:/work/DriFoxx && python -m pyright app/core/ui_plugin_registry.py
```
Expected: 无错误

---

### Task 3: 验证功能

**交互验证步骤（手动执行，无自动化测试用例）：**

1. **启动 DriFox**，确保插件市场等 UI 插件已加载
2. **测试内部展开（回归）**：输入 `/plugin-marketplace`，确认仍然在窗口内部正常展开
3. **测试向上展开**：输入 `/plugin-marketplace --up`，确认：
   - 面板在窗口正上方弹出
   - 面板无边框、有阴影
   - 有关闭按钮
   - 内容正常显示
4. **测试四个方向**：分别测试 `--down`, `--left`, `--right`
5. **测试 toggle**：再次输入同一命令+同一方向，面板关闭
6. **测试同时显示**：先 `/plugin-marketplace` 内部展开，再 `/plugin-marketplace --up` 外部展开，两者应同时可见
7. **测试窗口跟随**：拖动主窗口，面板应自动跟随
8. **测试最小化**：主窗口最小化 → 面板隐藏；恢复 → 面板重新显示
9. **测试边界裁剪**：将主窗口拖到屏幕边缘，确认面板不超出屏幕
10. **测试参数补全**：输入 `/plugin-marketplace --` 确认弹出方向参数列表
