# -*- coding: utf-8 -*-
"""浏览器卡片内的历史、收藏与下载面板共用的布局、主题和异步列表。"""

from typing import Any, Callable, List, Optional

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPalette
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QStackedWidget,
    QWidget,
)
from qfluentwidgets import FluentIcon, IconWidget, TransparentToolButton

from .data import AsyncDataLoader
from .theme import dialog_style, font_css, scrollbar_style, theme_colors


class PageRowDelegate(QStyledItemDelegate):
    """历史与收藏共用两行布局，网址和长标题按实际行宽省略。"""

    def sizeHint(self, option, index):
        return QSize(80, option.fontMetrics.height() * 2 + 18)

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        title = opt.text
        opt.text = ""
        style = option.widget.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, option.widget)
        rect = style.subElementRect(QStyle.SE_ItemViewItemText, opt, option.widget)
        rect = rect.adjusted(6, 0, -8, 0)
        top = rect.height() // 2
        painter.save()
        font = QFont(opt.font)
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        color = opt.palette.color(QPalette.Text)
        painter.setPen(color)
        painter.drawText(rect.adjusted(0, 0, 0, -top), Qt.AlignLeft | Qt.AlignBottom,
                         QFontMetrics(font).elidedText(title, Qt.ElideRight, rect.width()))
        muted = QColor(color)
        muted.setAlphaF(color.alphaF() * 0.75)
        painter.setPen(muted)
        painter.setFont(opt.font)
        detail = index.data(Qt.UserRole + 1) or index.data(Qt.UserRole) or ""
        painter.drawText(rect.adjusted(0, top + 2, 0, 0), Qt.AlignLeft | Qt.AlignTop,
                         opt.fontMetrics.elidedText(detail, Qt.ElideRight, rect.width()))
        painter.restore()


# ════════════════════════════════════════════════════════════════════
# Mixin：给子类提供统一的列表/异步加载接口
# ════════════════════════════════════════════════════════════════════


class _PanelMixin:
    """子类提供列表控件、查询参数和记录渲染，共用加载与空状态容器。"""

    _list: QListWidget  # 类型提示，运行时由子类赋值
    _owner: Any
    _items_cache: List[Any]
    _loader: AsyncDataLoader
    preferred_size = (460, 320)

    def _build_results(self):
        self._results = QStackedWidget(self)
        self._results.addWidget(self._list)
        self._message = QLabel(self._results)
        self._message.setObjectName("panelMessage")
        self._message.setAlignment(Qt.AlignCenter)
        self._message.setWordWrap(True)
        self._results.addWidget(self._message)
        return self._results

    def _show_message(self, text):
        self._message.setText(text)
        self._results.setCurrentWidget(self._message)

    def _reload(self):
        """只接收最后一次查询的结果，避免慢查询覆盖新的搜索或刷新。"""
        request = getattr(self, "_request", 0) + 1
        self._request = request
        self._list.clear()
        self._show_message("正在加载…")

        def loaded(items):
            if request == self._request:
                self._items_cache = list(items)
                self._results.setCurrentWidget(self._list)
                self._render_items()

        def failed(error):
            if request == self._request:
                self._show_message("加载失败，请重新打开面板重试。")
                self._message.setToolTip(str(error))

        self._message.setToolTip("")
        query, params = self._list_query()
        self._loader.load(query, loaded, on_error=failed, **params)


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
    title_lb.setObjectName("panelTitle")
    header.addWidget(title_lb)
    header.addStretch(1)

    if actions is not None:
        actions(header, c)

    close_btn = TransparentToolButton(FluentIcon.CLOSE, parent)
    close_btn.setFixedSize(28, 28)
    close_btn.setToolTip("关闭面板")
    close_btn.setAccessibleName("关闭面板")
    close_btn.clicked.connect(parent.close)
    header.addWidget(close_btn)
    return header


def build_footer(actions: Callable[[QHBoxLayout], None]) -> QHBoxLayout:
    """底部操作靠左排列，余下空间留白。"""
    footer = QHBoxLayout()
    footer.setSpacing(8)
    actions(footer)
    footer.addStretch(1)
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
    style += (
        f"QLabel#panelTitle {{ {font_css(c['ff'], c['fs'] + 2)} font-weight: 600; }}"
        f"QLabel#panelMessage {{ color: {c['secondary']}; background: {c['raised']};"
        f" padding: 10px; border-radius: 8px; {font_css(c['ff'], c['fs'])} }}"
    )
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
