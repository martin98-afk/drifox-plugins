# -*- coding: utf-8 -*-
"""地址栏 — Chrome 风格 URL 输入框

功能：
- URL 规范化：localhost:port 自动补 http://；无 scheme 的裸域名补 https://
- 加载指示：页面加载时显示转圈动画/进度，加载完成恢复
- 自动补全：从历史 + 收藏合并排序（QCompleter 数据源）
"""

import re
from typing import Callable, List, Tuple

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QCompleter,
    QHBoxLayout,
    QLineEdit,
    QProgressBar,
    QWidget,
)

from .theme import font_css, list_item_style, theme_colors

# ── URL 规范化 ──────────────────────────────────────────

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
_LOCALHOST_RE = re.compile(r"^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?(/.*)?$")
_IP_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}(:\d+)?(/.*)?$")
_DOMAIN_RE = re.compile(
    r"^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
    r"[a-zA-Z]{2,}(:\d+)?(/.*)?$"
)


def normalize_url(text: str) -> str:
    """将用户输入规范化为完整 URL

    - 已是完整 URL（含 scheme）→ 原样返回
    - localhost:8080 / 127.0.0.1:8080 → http:// 前缀
    - 裸域名 example.com → https:// 前缀
    - 其他（可能是搜索词）→ 返回 None 由调用方决定走搜索
    """
    text = text.strip()
    if not text:
        return ""

    if _SCHEME_RE.match(text):
        return text

    # 去掉多余空格（"localhost: 8080" → "localhost:8080"）
    text = text.replace(" ", "")

    if _LOCALHOST_RE.match(text) or _IP_RE.match(text):
        return f"http://{text}"

    if _DOMAIN_RE.match(text):
        return f"https://{text}"

    return ""  # 不是 URL，交给搜索


def is_blank_page(url: str) -> bool:
    """判断是否为空白起始页"""
    return url in ("", "about:blank")


# ── 地址栏控件 ──────────────────────────────────────────


class UrlBar(QWidget):
    """Chrome 风格地址栏：圆角输入框 + 内嵌加载进度条

    Signals:
        navigate_requested(str url): 用户回车导航
    """

    navigate_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = False
        self._progress = 0
        self._completer_source: Callable[[], List[Tuple[str, str]]] = lambda: []
        self._c = theme_colors(None)  # 主题派生色缓存（apply_theme 前的默认观感）
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedHeight(38)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._edit = QLineEdit(self)
        self._edit.setPlaceholderText("搜索或输入网址")
        self._edit.textChanged.connect(self._sync_placeholder)
        self._edit.setClearButtonEnabled(True)
        self._edit.returnPressed.connect(self._on_return_pressed)
        self._edit.setMinimumHeight(34)
        self._edit.setStyleSheet(self._edit_style(self._c))

        layout.addWidget(self._edit, 1)

        # 内嵌进度条（叠在输入框底部）
        self._progress_bar = QProgressBar(self)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(3)
        self._progress_bar.setStyleSheet(self._progress_style(self._c))
        self._progress_bar.setVisible(False)

        # 用 QTimer 合并 80ms 内的连续进度更新（渲染合并，减少重绘）
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(80)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._apply_progress)

    # ── 样式构建（对齐主程序输入框观感） ──

    def _edit_style(self, c: dict) -> str:
        """输入框 QSS：content_bg 底 + input_border/focus_border + 8px 圆角"""
        return (
            f"QLineEdit {{ {font_css(c['ff'], c['fs'])} color: {c['text']};"
            f" border: 1px solid {c['input_border']}; border-radius: 8px;"
            f" padding: 0 12px; background: {c['raised']};"
            f" selection-background-color: {c['selected']}; }}"
            f"QLineEdit:focus {{ border: 1px solid {c['focus_border']};"
            f" background: {c['raised']}; }}"
        )

    def _progress_style(self, c: dict) -> str:
        """内嵌进度条：accent chunk + 2px 圆角 + 透明底"""
        return (
            "QProgressBar { border: none; border-radius: 2px; background: transparent; }"
            f"QProgressBar::chunk {{ border-radius: 2px; background: {c['accent']}; }}"
        )

    def _completer_style(self, c: dict) -> str:
        """补全弹出列表：content_bg 容器 + item hover/selected"""
        return (
            f"QAbstractItemView {{ background: {c['raised']}; color: {c['text']};"
            f" border: 1px solid {c['border']}; border-radius: 8px;"
            f" {font_css(c['ff'], c['fs'])} padding: 4px; }}"
            + list_item_style(c["ff"], c["fs"], c["hover"], c["selected"])
        )

    def apply_theme(self, c: dict):
        """应用主题派生色字典（来自 theme.theme_colors(owner)）。"""
        self._c = c
        self._edit.setStyleSheet(self._edit_style(c))
        self._progress_bar.setStyleSheet(self._progress_style(c))
        completer = self._edit.completer()
        if completer is not None:
            completer.popup().setStyleSheet(self._completer_style(c))

    def _sync_placeholder(self, text: str):
        """避免部分高 DPI/主题组合下 placeholder 与 URL 同时绘制。"""
        self._edit.setPlaceholderText("" if text else "搜索或输入网址")

    def _on_return_pressed(self):
        text = self._edit.text().strip()
        if not text:
            return
        url = normalize_url(text)
        if not url:
            # 不是 URL：作为搜索词
            url = _search_url(text)
        self.navigate_requested.emit(url)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 进度条跟随输入框底部
        self._progress_bar.setGeometry(12, self.height() - 6, self.width() - 24, 3)

    # ── 加载状态 ──

    def set_loading(self, loading: bool, progress: int = 0):
        """设置加载状态（进度合并渲染）"""
        self._loading = loading
        self._progress = progress
        if loading:
            self._progress_bar.setVisible(True)
            self._render_timer.start()  # 合并 80ms 内的更新
        else:
            self._render_timer.stop()
            self._progress_bar.setVisible(False)
            self._progress_bar.setValue(100 if progress >= 100 else progress)

    def _apply_progress(self):
        if self._loading:
            self._progress_bar.setValue(self._progress)

    # ── 文本 / 焦点 ──

    def set_url(self, url: str):
        """设置地址栏显示文本（不触发导航）"""
        if self._edit.text() != url:
            self._edit.setPlaceholderText("")
            self._edit.setText(url)

    def url_text(self) -> str:
        return self._edit.text()

    def select_all(self):
        """聚焦并全选（Ctrl+L 行为）"""
        self._edit.setFocus()
        self._edit.selectAll()

    def set_completer_source(self, source: Callable[[], List[Tuple[str, str]]]):
        """设置补全数据源：返回 [(url, title)] 列表"""
        self._completer_source = source

    def update_completer(self):
        """重建补全（历史+收藏合并，按访问次数排序）"""
        try:
            items = self._completer_source()
        except Exception:
            items = []

        entries = []
        seen = set()
        for url, title in items:
            if not url or url in seen:
                continue
            seen.add(url)
            label = title if title else url
            entries.append(f"{label}  —  {url}")

        completer = QCompleter(entries, self._edit)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.popup().setStyleSheet(self._completer_style(self._c))
        self._edit.setCompleter(completer)


def _search_url(query: str) -> str:
    """搜索词 → 搜索引擎 URL（Bing，国内可达性好）"""
    from urllib.parse import quote

    return f"https://www.bing.com/search?q={quote(query)}"
