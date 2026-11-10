# -*- coding: utf-8 -*-
"""系统规范的确认弹窗（MaskDialogBase 自绘）。

为什么不用 QMessageBox：那是 Windows 原生样式，跟宿主主题完全两张皮
（英文 Yes/No、系统蓝问号图标）。

为什么也不用 host 的 ui.dialog 能力：该能力要解析窗口宿主，卡片在少数
时序下拿不到 host 时会静默返回 None，就退化成原生弹窗了（实测踩过）。
这里直接用 qfluentwidgets 的 MaskDialogBase 自绘，样式与宿主内置弹窗一致，
不依赖任何宿主能力。

⚠ MaskDialogBase 的 _hBoxLayout 默认 addWidget 会把卡片拉到全屏，必须显式
AlignCenter；也不要在外面手动 setGeometry，会让卡片漂移。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from qfluentwidgets import MaskDialogBase

if TYPE_CHECKING:  # pragma: no cover
    from .theme import Theme


def _dialog_btn(text: str, *, primary: bool, theme: "Theme") -> QPushButton:
    btn = QPushButton(text)
    btn.setFixedHeight(32)
    btn.setCursor(Qt.PointingHandCursor)
    if primary:
        btn.setStyleSheet(
            "QPushButton {"
            f"background: {theme.accent}; color: #ffffff; border: none;"
            "border-radius: 8px; padding: 4px 26px;"
            f"{theme.font(-2, 600)}"
            "}"
            f"QPushButton:hover {{ background: {theme.with_alpha(theme.accent, 0.86)}; }}"
        )
    else:
        btn.setStyleSheet(
            "QPushButton {"
            f"background: transparent; color: {theme.text_primary};"
            f"border: 1px solid {theme.border}; border-radius: 8px; padding: 4px 26px;"
            f"{theme.font(-2)}"
            "}"
            f"QPushButton:hover {{ background: {theme.hover_bg}; }}"
        )
    return btn


class ConfirmDialog(MaskDialogBase):
    """确认框：标题 + 正文 + 取消/确定。`confirmed` 为 True 表示用户确认。"""

    def __init__(self, parent, theme: "Theme", title: str, text: str, confirm_text: str = "确定"):
        # MaskDialogBase 要读 parent.width()，parent 为 None 会直接 AttributeError
        if parent is None:
            from PyQt5.QtWidgets import QApplication

            parent = QApplication.activeWindow()
        super().__init__(parent)
        self.confirmed = False
        self.setShadowEffect(60, (0, 10), QColor(0, 0, 0, 100))
        self.setClosableOnMaskClicked(True)
        self.setDraggable(True)
        self.setMaskColor(QColor(0, 0, 0, 76))

        self.widget.setObjectName("mnConfirm")
        self.widget.setStyleSheet(
            "#mnConfirm {"
            f"background: {theme.card_bg_solid}; border: 1px solid {theme.border};"
            "border-radius: 12px;"
            "}"
        )
        v = QVBoxLayout(self.widget)
        v.setContentsMargins(24, 20, 24, 18)
        v.setSpacing(10)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"color: {theme.text_primary}; background: transparent; border: none;"
            f"{theme.font(0, 600)}"
        )
        v.addWidget(title_lbl)

        body = QLabel(text)
        body.setWordWrap(True)
        body.setStyleSheet(
            f"color: {theme.text_muted}; background: transparent; border: none;"
            f"{theme.font(-2)}"
        )
        v.addWidget(body)
        v.addStretch()

        row = QHBoxLayout()
        row.addStretch()
        cancel = _dialog_btn("取消", primary=False, theme=theme)
        cancel.clicked.connect(self.reject)
        ok = _dialog_btn(confirm_text, primary=True, theme=theme)
        ok.clicked.connect(self._accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        v.addLayout(row)

        # 必须显式 AlignCenter：默认会把卡片拉伸到整个遮罩区域
        self._hBoxLayout.addWidget(self.widget, 0, Qt.AlignCenter)
        self.widget.setFixedWidth(420)
        self.widget.setFixedHeight(self.widget.sizeHint().height() + 40)

    def _accept(self) -> None:
        self.confirmed = True
        self.accept()


def confirm_dialog(
    parent,
    theme: "Theme",
    title: str,
    text: str,
    confirm_text: str = "确定",
) -> bool:
    """显示确认框并返回结果（同步模态）。"""
    dlg = ConfirmDialog(parent, theme, title, text, confirm_text)
    dlg.exec_()
    return dlg.confirmed
