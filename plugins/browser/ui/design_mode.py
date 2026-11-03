# -*- coding: utf-8 -*-
"""Design Mode 控制器：事件拦截 + 查询 + 截图 + 回填。

事件挂在 view.focusProxy() 上（Qt WebEngine 实际渲染控件），
页面内只做无状态的 runJavaScript 查询，高亮框是 Python 侧的透明 QWidget。
纯函数与 JS 片段在 design_mode_core.py。
"""

import time
from pathlib import Path

from PyQt5.QtCore import QEvent, QObject, QPoint, QTimer, Qt
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QWidget

from .design_mode_core import build_prompt, clamp_rect, filter_styles, js_hit, js_pick


def _picks_dir():
    root = Path.home() / ".drifox" / "plugins" / "browser" / "data" / "picks"
    root.mkdir(parents=True, exist_ok=True)
    return root


class _Highlight(QWidget):
    """元素高亮框：透明、不接收鼠标、画在 view 之上。"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setCursor(Qt.CrossCursor)
        self.hide()
        self._color = QColor(64, 158, 255)

    def set_color(self, color):
        if isinstance(color, QColor):
            self._color = color
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(self._color, 2))
        fill = QColor(self._color)
        fill.setAlpha(40)
        painter.setBrush(fill)
        painter.drawRect(self.rect().adjusted(1, 1, -2, -2))


class _EscFilter(QObject):
    """Esc 优先退出 Design Mode，其余按键放行。"""

    def __init__(self, mode):
        super().__init__(mode)
        self._mode = mode

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self._mode.stop()
            return True
        return False


class DesignMode(QObject):
    """拾取模式控制器。"""

    HOVER_MS = 60

    def __init__(self, card):
        super().__init__(card)
        self._card = card
        self._view = None
        self._proxy = None
        self._highlight = None
        self._esc_filter = None
        self._active = False
        self._count = 0
        self._pending = False
        self._last_pos = QPoint()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.HOVER_MS)
        self._timer.timeout.connect(self._query_hover)

    # ── 生命周期 ──

    def is_active(self):
        return self._active

    def toggle(self):
        if self._active:
            self.stop()
        else:
            self.start()

    def start(self):
        view = self._card._current_view()
        if view is None:
            self._card._set_status("Design Mode：当前标签不可用")
            return
        try:
            from PyQt5.QtWebEngineWidgets import QWebEngineSettings

            js_on = view.page().settings().testAttribute(
                QWebEngineSettings.JavascriptEnabled
            )
            if not js_on:
                self._card._set_status("Design Mode：当前页面禁用了 JS，无法拾取")
                return
        except Exception:
            pass
        proxy = view.focusProxy() or view
        self._view = view
        self._proxy = proxy
        self._highlight = _Highlight(view)
        self._highlight.resize(view.size())
        self._highlight.show()
        self._highlight.raise_()
        proxy.installEventFilter(self)
        self._esc_filter = _EscFilter(self)
        view.installEventFilter(self._esc_filter)
        self._active = True
        self._count = 0
        view.setFocus()
        self._card._set_status("Design Mode：点击页面元素，Esc 退出")
        self._sync_button()

    def stop(self):
        if not self._active:
            return
        self._active = False
        self._timer.stop()
        if self._proxy is not None:
            try:
                self._proxy.removeEventFilter(self)
            except RuntimeError:
                pass
        if self._view is not None and self._esc_filter is not None:
            try:
                self._view.removeEventFilter(self._esc_filter)
            except RuntimeError:
                pass
        if self._highlight is not None:
            self._highlight.deleteLater()
            self._highlight = None
        self._esc_filter = None
        self._view = None
        self._proxy = None
        self._sync_button()
        if self._count:
            self._card._set_status(f"Design Mode 已退出，共追加 {self._count} 个元素")
        else:
            self._card._set_status("Design Mode 已退出")

    def _sync_button(self):
        btn = getattr(self._card, "_btn_pick", None)
        if btn is not None:
            btn.setDown(self._active)

    # ── 事件 ──

    def eventFilter(self, obj, event):
        if not self._active:
            return False
        kind = event.type()
        if kind == QEvent.MouseMove:
            self._last_pos = event.pos()
            if not self._timer.isActive():
                self._timer.start()
            return True
        if kind in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick):
            return True
        if kind == QEvent.MouseButtonRelease:
            if event.button() == Qt.LeftButton:
                self._pick(event.pos())
            return True
        if kind == QEvent.Resize and self._highlight is not None and self._view is not None:
            self._highlight.resize(self._view.size())
        return False

    def _to_page(self, pos):
        """focusProxy 坐标 → 页面 CSS 坐标。"""
        if self._proxy is not None and self._view is not None:
            pos = self._proxy.mapTo(self._view, pos)
        zoom = 1.0
        try:
            zoom = self._view.page().zoomFactor() or 1.0
        except Exception:
            pass
        return pos.x() / zoom, pos.y() / zoom

    # ── 查询 ──

    def _query_hover(self):
        if not self._active or self._pending or self._view is None:
            return
        if self._highlight is not None:
            self._highlight.resize(self._view.size())
        x, y = self._to_page(self._last_pos)
        self._pending = True

        def done(result):
            self._pending = False
            if not self._active or not isinstance(result, dict):
                return
            rect = result.get("rect") or {}
            w = int(rect.get("w") or 0)
            h = int(rect.get("h") or 0)
            if w <= 0 or h <= 0 or self._highlight is None:
                if self._highlight is not None:
                    self._highlight.hide()
                return
            self._highlight.setGeometry(int(rect["x"]), int(rect["y"]), w, h)
            self._highlight.show()
            self._highlight.raise_()

        self._view.page().runJavaScript(js_hit(x, y), done)

    def _pick(self, pos):
        if self._view is None:
            return
        x, y = self._to_page(pos)
        view = self._view

        def done(result):
            if not self._active or not isinstance(result, dict):
                self._card._set_status("Design Mode：该位置取不到元素")
                return
            self._count += 1
            styles = filter_styles(result.get("styles") or {})
            shot = self._capture(result.get("rect") or {}, self._count)
            text = build_prompt(
                index=self._count,
                url=view.url().toString(),
                title=view.title(),
                selector=result.get("selector") or "unknown",
                html=result.get("html") or "",
                styles=styles,
                shot_path=str(shot) if shot else None,
            )
            if self._write(text):
                self._card._set_status(
                    f"Design Mode：已追加第 {self._count} 个元素（Esc 退出）"
                )
            else:
                self._card._set_status("Design Mode：已拾取，但输入框写入失败")

        view.page().runJavaScript(js_pick(x, y), done)

    # ── 截图 ──

    def _capture(self, rect, index):
        """按元素矩形（外扩 40px）裁剪当前视口截图；失败返回 None。"""
        view = self._view
        if view is None:
            return None
        pixmap = view.grab()
        if pixmap.isNull():
            return None
        dpr = view.devicePixelRatioF() or 1.0
        vw = pixmap.width() / dpr
        vh = pixmap.height() / dpr
        box = clamp_rect(
            rect.get("x", 0), rect.get("y", 0),
            rect.get("w", 0), rect.get("h", 0),
            vw, vh, pad=40,
        )
        if box is None:
            return None
        x, y, w, h = (int(round(v * dpr)) for v in box)
        cropped = pixmap.copy(x, y, w, h)
        if cropped.isNull() or cropped.width() == 0 or cropped.height() == 0:
            return None
        path = _picks_dir() / f"pick_{int(time.time() * 1000)}_{index}.png"
        if not cropped.save(str(path), "PNG"):
            return None
        return path

    # ── 回填 ──

    def _write(self, text):
        """经能力池写入输入框。首次覆盖，后续追加，全程不抢焦点。"""
        try:
            from app.plugins.sdk import caps_for

            write = caps_for("input.write", plugin="browser", surface="ui")
        except Exception:
            write = None
        if write is None:
            return False
        try:
            write(text, append=self._count > 1, focus=False)
            return True
        except Exception:
            return False
