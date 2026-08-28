# -*- coding: utf-8 -*-
"""_ElidedLabel - 自动根据可用宽度省略文本的 QLabel（中间省略）+ tooltip

精简自 DriFox 主应用 app/widgets/elided_label.py：
- 宽度由布局决定（QSizePolicy.Ignored），超长文本不撑宽侧栏/按钮不被挤出屏幕
- 按可用宽度 ElideMiddle 省略，完整文本放 tooltip
- 去掉了搜索高亮相关逻辑（git-panel 无需）

插件自包含：不依赖主应用内部模块，可独立加载测试。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy


class _ElidedLabel(QLabel):
    """自动根据可用宽度省略文本的 QLabel（中间省略），完整文本放 tooltip"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._full_text = text
        self.setToolTip(text)
        # 宽度交给父布局决定，防止长文本把布局撑宽
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def setText(self, text: str):
        self._full_text = text
        self.setToolTip(text)
        self._update_elided()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elided()

    def _update_elided(self):
        w = self.width()
        if w <= 0:
            # 未布局：显示原文。强制 PlainText，避免路径含 < > 时误判富文本
            self.setTextFormat(Qt.PlainText)
            if self.text() != self._full_text:
                super().setText(self._full_text)
            return
        fm = self.fontMetrics()
        elided = fm.elidedText(self._full_text, Qt.ElideMiddle, w)
        self.setTextFormat(Qt.PlainText)
        if self.text() != elided:
            super().setText(elided)
