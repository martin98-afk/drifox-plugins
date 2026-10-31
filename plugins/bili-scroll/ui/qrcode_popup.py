# -*- coding: utf-8 -*-
"""扫码登录二维码弹窗：HTTP 线程经 ui_bridge 派发主线程创建，模块级引用保活。

每次 bili_login 出码新建窗口（deleteLater 旧的）；登录 done/timeout 由
control_server 调 close_qrcode 收窗。
"""
import base64

from loguru import logger

_POPUP = {"widget": None}


def show_qrcode(data_url: str):
    """显示二维码弹窗。data_url: data:image/png;base64,..."""
    def _create():
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QPixmap
        from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

        old = _POPUP.pop("widget", None)
        if old is not None:
            try:
                old.deleteLater()
            except RuntimeError:
                pass  # 已随窗口关闭析构

        payload = data_url.split(",", 1)[-1]
        pix = QPixmap()
        if not pix.loadFromData(base64.b64decode(payload), "PNG"):
            logger.warning("[bili-scroll] 二维码图片解码失败")
            return
        img = QLabel()
        img.setPixmap(pix)
        tip = QLabel("B站App → 扫一扫 → 确认登录（180 秒内有效）")
        tip.setWordWrap(True)
        box = QVBoxLayout()
        box.addWidget(img)
        box.addWidget(tip)
        win = QWidget()
        win.setWindowTitle("bili-scroll · B站扫码登录")
        win.setLayout(box)
        win.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        win.show()
        _POPUP["widget"] = win
        logger.info("[bili-scroll] 二维码弹窗已显示")

    from app.plugins.capabilities.providers.ui_bridge import _dispatch

    _dispatch(_create, wait=False)


def close_qrcode():
    """关闭二维码弹窗（登录 done/timeout 时调用；幂等）。"""
    def _close():
        w = _POPUP.get("widget")
        if w is not None:
            try:
                w.close()
                w.deleteLater()
            except RuntimeError:
                pass
            _POPUP["widget"] = None

    from app.plugins.capabilities.providers.ui_bridge import _dispatch

    _dispatch(_close, wait=False)
