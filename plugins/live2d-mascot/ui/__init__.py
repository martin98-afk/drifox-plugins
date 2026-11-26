# -*- coding: utf-8 -*-
"""live2d-mascot UI 入口 —— 桌面看板（独立悬浮窗）

宿主欢迎卡片的 WebView 没有 WebGL（实测 getContext('webgl') 为 null），
Live2D 的网页渲染方案在卡片里跑不起来，因此看板走 Qt 原生 OpenGL
（见 ui/pet.py），只注册一个控制页窗口，不往欢迎卡片注入任何内容。
"""

import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QMessageBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import pet


class MascotPanel(QWidget):
    """看板控制页：选模型、召唤、收起"""

    def __init__(self, parent=None):
        # 宿主实例化内容页时会传 parent，签名必须带默认值
        super().__init__(parent)
        self._provider = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title = QLabel("Live2D 看板")
        title.setStyleSheet("font-size:15px;font-weight:600")
        layout.addWidget(title)

        hint = QLabel(
            "看板是独立悬浮窗：真 60fps 形变，鼠标移过去视线跟随，"
            "左键拖动窗口，单击换表情，右键菜单可收起。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8a8f98;font-size:12px")
        layout.addWidget(hint)

        row = QHBoxLayout()
        row.addWidget(QLabel("模型"))
        self._combo = QComboBox()
        self._combo.addItems(pet.list_models())
        row.addWidget(self._combo, 1)
        layout.addLayout(row)

        self._through_box = QCheckBox("鼠标穿透（点它等于点底下窗口）")
        self._through_box.toggled.connect(self._on_through)
        layout.addWidget(self._through_box)
        self._top_box = QCheckBox("窗口置顶")
        self._top_box.setChecked(True)
        self._top_box.toggled.connect(self._on_top)
        layout.addWidget(self._top_box)

        btns = QHBoxLayout()
        self._summon_btn = QPushButton("召唤看板")
        self._summon_btn.clicked.connect(self._on_summon)
        btns.addWidget(self._summon_btn)
        self._dismiss_btn = QPushButton("收起看板")
        self._dismiss_btn.clicked.connect(pet.dismiss)
        btns.addWidget(self._dismiss_btn)
        btns.addStretch(1)
        layout.addLayout(btns)
        layout.addStretch(1)

        if not pet.list_models():
            self._summon_btn.setEnabled(False)
            hint.setText(
                "还没有模型：把 Live2D 模型目录放到 web/model/<名字>/，"
                "入口文件命名为 <名字>.model3.json"
            )

    def set_context_provider(self, provider):
        self._provider = provider

    def show_card(self):
        pass

    def refresh_theme(self):
        pass

    def _on_summon(self):
        try:
            win = pet.summon(self._combo.currentText() or "")
        except Exception as exc:  # OpenGL/live2d 初始化失败要让用户看见，不能静默
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "看板启动失败", str(exc))
            return
        if win is None:
            self._summon_btn.setEnabled(False)
            QMessageBox.information(self, "没有模型", "web/model 下没有可用的 .model3.json")
            return
        win.set_click_through(self._through_box.isChecked())
        win.set_on_top(self._top_box.isChecked())

    def _on_through(self, checked):
        for win in pet._windows:
            win.set_click_through(checked)

    def _on_top(self, checked):
        for win in pet._windows:
            win.set_on_top(checked)


def register_ui(registry):
    """注册看板：控制页窗口 + 欢迎卡片说明 tab"""
    prefix = "ui_plugin_live2d_mascot."
    for key in [k for k in sys.modules if k.startswith(prefix)]:
        del sys.modules[key]

    registry.register_window(
        plugin_name="live2d-mascot",
        window_id="live2d-mascot:panel",
        widget_class=MascotPanel,
        title="看板",
        width=460,
        height=300,
        min_width=380,
        min_height=240,
    )
