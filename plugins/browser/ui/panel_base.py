# -*- coding: utf-8 -*-
"""统一列表弹窗构建工具 — 历史 / 收藏 / 下载共享同一视觉与交互

设计目标（替代三份重复的 _setup_ui）：
- 头部：图标 + 标题 + 右侧操作按钮（动态注入，子类按需添加）
- 中部：QListWidget（统一 padding / hover / 选中样式）
- 底部：操作按钮行（动态注入，默认含「关闭」）
- 统一应用 dialog_style + scrollbar_style，字体走 context_provider 字体

由于历史面板继承 QFrame（卡片内嵌），收藏/下载继承 QDialog（独立窗口），
本模块不强制单一基类，而是提供：
- _PanelMixin    混入类，提供 _list/_items_cache/异步加载/_reload 协议
- 三个 helper    build_header / build_panel_style / show_singleton_panel
- 子类在 _setup_ui() 里按需调用，结构完全一致
"""

from typing import Any, Callable, List, Optional

from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QWidget,
)
from qfluentwidgets import FluentIcon, IconWidget

from .data import AsyncDataLoader
from .theme import dialog_style, font_css, scrollbar_style, theme_colors


# ════════════════════════════════════════════════════════════════════
# Mixin：给子类提供统一的列表/异步加载接口
# ════════════════════════════════════════════════════════════════════


class _PanelMixin:
    """混入类：要求子类拥有 QListWidget(self._list)、theme owner(self._owner)

    子类只需：
    1. 在 _setup_ui() 里 build_header + 创建 self._list + build_footer
    2. 重写 _reload_async() 异步取数据 → self._on_items_loaded(items)
    3. 重写 _render_items() 把 self._items_cache 渲染到 self._list
    """

    _list: QListWidget  # 类型提示，运行时由子类赋值
    _owner: Any
    _items_cache: List[Any]
    _loader: AsyncDataLoader

    # ── 异步加载协议 ──

    def _reload(self):
        """统一入口：清空 → 显示加载占位 → 异步加载 → 回填渲染

        与原三面板保持一致的语义（调用方在 show 时直接 _reload()）。
        """
        self._list.clear()
        placeholder = QListWidgetItem("加载中…")
        self._list.addItem(placeholder)
        self._reload_async()

    def _reload_async(self) -> None:
        """子类重写：异步查询数据并回填 _items_cache + _render_items

        默认实现：仅显示「暂无数据」占位（兜底，子类必须重写）。
        """
        self._items_cache = []
        self._render_items()

    def _on_items_loaded(self, items: List[Any]) -> None:
        """统一 worker 回调：缓存 + 渲染"""
        self._items_cache = list(items)
        self._render_items()

    def _render_items(self) -> None:
        """子类重写：把 _items_cache 渲染到 self._list"""
        self._list.clear()
        placeholder = QListWidgetItem("暂无数据")
        self._list.addItem(placeholder)


# ════════════════════════════════════════════════════════════════════
# 头部 / 底部 / 主题 helper
# ════════════════════════════════════════════════════════════════════


def build_header(
    parent: QWidget,
    owner: Any,
    title: str,
    icon: Any = FluentIcon.HISTORY,
    actions: Optional[Callable[[QHBoxLayout, dict], None]] = None,
) -> QHBoxLayout:
    """构造统一头部：图标 + 标题 + 右侧动作（子类按需注入按钮）

    Args:
        parent:  父 QWidget
        owner:   浏览器卡片实例（取主题/字体）
        title:   标题文本
        icon:    FluentIcon 或 QIcon
        actions: 可选回调 fn(layout, colors) → 子类在右侧追加按钮

    Returns:
        已加入 parent 的 QHBoxLayout（外层负责 add 到 root layout）
    """
    c = theme_colors(owner)
    header = QHBoxLayout()
    header.setSpacing(8)

    icon_w = IconWidget(icon, parent)
    icon_w.setFixedSize(16, 16)
    header.addWidget(icon_w)

    title_lb = QLabel(title, parent)
    title_lb.setStyleSheet(
        f"{font_css(c['ff'], c['fs'] + 2)} font-weight: 600;"
        f"color: {c['text']}; background: transparent;"
    )
    header.addWidget(title_lb)
    header.addStretch(1)

    if actions is not None:
        actions(header, c)

    return header


def build_footer(
    parent: QWidget,
    actions: Optional[Callable[[QHBoxLayout], None]] = None,
    default_close: bool = True,
) -> QHBoxLayout:
    """构造统一底部：左侧动作（按需） + 右侧「关闭」

    Args:
        parent:        父 QWidget（用于 close 按钮的 parent 参数）
        actions:       子类回调 fn(footer_layout) → 追加左侧按钮
        default_close: True 时自动在右侧添加「关闭」按钮
    """
    footer = QHBoxLayout()
    footer.setSpacing(8)
    if actions is not None:
        actions(footer)
    if default_close:
        footer.addStretch(1)
        close_btn = QPushButton("关闭", parent)
        close_btn.setFixedHeight(28)
        close_btn.clicked.connect(parent.close)
        footer.addWidget(close_btn)
    return footer


def apply_panel_theme(widget: QWidget, owner: Any) -> None:
    """统一应用 dialog_style + scrollbar_style 到弹窗容器

    弹窗创建 + 主题切换 + 重新显示 时调用。

    修复透明背景：历史/收藏/下载面板均为卡片内嵌 QFrame（非 QDialog），
    dialog_style 只给 QDialog 设背景 → QFrame 无背景 → 透明。
    这里按 objectName 追加 QFrame 容器背景规则（surface + border + 圆角）。
    include_line_edit=True 顺带给面板内输入框（历史搜索）统一 raised 底/
    边框/聚焦色，避免深色主题下 QLineEdit 默认白底刺眼。
    """
    c = theme_colors(owner)
    style = dialog_style(owner, include_line_edit=True) + scrollbar_style(owner)
    name = widget.objectName()
    if name:
        style += (
            f"QFrame#{name} {{ background: {c['surface']};"
            f" border: 1px solid {c['border']}; border-radius: 8px;"
            f" {font_css(c['ff'], max(10, c['fs'] - 1))} }}"
        )
    widget.setStyleSheet(style)


def show_singleton_panel(
    owner: Any,
    attr_name: str,
    factory: Callable[[Any], QWidget],
    *,
    position: bool = False,
) -> QWidget:
    """统一的弹窗单例复用 + 主题刷新 + 数据刷新

    Args:
        owner:      浏览器卡片实例
        attr_name:  owner 上保存弹窗的属性名（如 "_history_panel"）
        factory:    创建弹窗的工厂函数 fn(owner) -> widget
        position:   True 时调 owner._position_popup（history 卡片内嵌用）

    Returns:
        已显示的 widget 实例
    """
    panel = getattr(owner, attr_name, None)
    if panel is None:
        panel = factory(owner)
        setattr(owner, attr_name, panel)
    apply_panel_theme(panel, owner)
    if hasattr(panel, "_reload"):
        panel._reload()
    panel.show()
    if position and hasattr(owner, "_position_popup"):
        owner._position_popup(panel)
    panel.raise_()
    return panel