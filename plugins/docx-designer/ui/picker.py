# -*- coding: utf-8 -*-
"""拾取模式：body.pick 切换 → JS 点击回传锚点与矩形 → 视口截图裁剪 → input.write 回填。

回填文本格式化见 pick_format.py（纯函数）；本模块只管 Qt 侧：桥、截图、能力池写入。
"""

import time
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSlot


class DocxBridge(QObject):
    """QWebChannel 桥：页面 JS → Python。挂在 window 上防 GC。"""

    def __init__(self, window):
        super().__init__(window)
        self._window = window

    @pyqtSlot(str, float, float, float, float, str)
    def pick(self, anchor, x, y, w, h, preview):
        self._window.on_element_picked(anchor, x, y, w, h, preview)

    @pyqtSlot(str, str, int, str)
    def annotate_added(self, anchor, comment, seq, snippet):
        self._window.on_annotation_added(anchor, comment, seq, snippet)

    @pyqtSlot()
    def escape(self):
        self._window.set_pick_mode(False)
        self._window.set_annotate_mode(False)


def make_picks_dir():
    """截图目录：能力池 storage.data_dir（数据根，自拼 plugin_data/<name>/）。"""
    try:
        from app.plugins.sdk import caps_for

        root = Path(str(caps_for("storage.data_dir", plugin="docx-designer", surface="ui")))
        root = root / "plugin_data" / "docx-designer" / "picks"
    except Exception:
        root = Path.home() / ".drifox" / "plugin_data" / "docx-designer" / "picks"
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_input(text, count):
    """经能力池写输入框。首条覆盖，后续追加，全程不抢焦点。"""
    try:
        from app.plugins.sdk import caps_for

        write = caps_for("input.write", plugin="docx-designer", surface="ui")
    except Exception:
        write = None
    if write is None:
        return False
    try:
        write(text, append=count > 1, focus=False)
        return True
    except Exception:
        return False


def capture_view_rect(view, x, y, w, h):
    """view.grab() 全视口 → 按 CSS 矩形（dpr 换算）裁剪 → PNG 存盘。失败返回 None。"""
    pm = view.grab()
    if pm.isNull() or w <= 0 or h <= 0:
        return None
    dpr = view.devicePixelRatioF() or 1.0
    ix = max(0, min(int(x * dpr), pm.width() - 1))
    iy = max(0, min(int(y * dpr), pm.height() - 1))
    iw = min(int(w * dpr), pm.width() - ix)
    ih = min(int(h * dpr), pm.height() - iy)
    if iw <= 0 or ih <= 0:
        return None
    cropped = pm.copy(ix, iy, iw, ih)
    if cropped.isNull():
        return None
    path = make_picks_dir() / f"pick_{int(time.time() * 1000)}.png"
    return path if cropped.save(str(path), "PNG") else None
