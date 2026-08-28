# -*- coding: utf-8 -*-
"""右侧 AI 思考记录面板（#7 扩展）

类：AIThoughtPanel
- 顶部工具栏：标题 + 自动滚动 + 复制全部 + 清空 + 折叠按钮
- 内容：单个 QTextBrowser（setMarkdown 渲染）
- 底部：状态栏（记录条数 + 总字符数）

JSON / 走法剥离规则：
1. ```json … ``` 或 ``` … ``` 代码块（含 {...} JSON 对象）
2. 单行 JSON（如 {"move":"h2-e2"}）
3. _MOVE_RE 匹配到的走法字符串（如 {"from":[1,9],"to":[1,7]}）
统一替换为占位符 `（走法已省略）`
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Optional

from loguru import logger
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

# ── 复用 ai_engine 已有的 JSON 走法正则 + 剥离函数 ──
from .ai_engine import _MOVE_RE, _strip_thinking  # noqa: F401

# ── 剥离正则（模块级常量）──
# 1) ```json ... ``` / ``` ... ``` 代码块（含内部 JSON）
_RE_FENCED_CODE = re.compile(r"```(?:json|JSON)?\s*\n?(.*?)```", re.DOTALL)
# 2) 单行 / 多行纯 JSON 对象（含嵌套，用计数器）
_RE_BARE_JSON_OBJ = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}")
# 3) _MOVE_RE 走法字符串（ai_engine 同款）—— 由 .ai_engine 复用

PLACEHOLDER = "（走法已省略）"


def strip_json_and_moves(text: str) -> str:
    """剥离 JSON 代码块 / 纯 JSON 对象 / 走法字符串，替换为占位符。

    Args:
        text: 原始 LLM 响应（已剥离 <think>…</think>）

    Returns:
        脱敏文本：用 `（走法已省略）` 替换所有走法相关字符串
    """
    if not text:
        return text
    out = text

    # 1) 替换 ```json … ``` 代码块
    out = _RE_FENCED_CODE.sub(PLACEHOLDER, out)

    # 2) 替换纯 JSON 对象（多次迭代，处理嵌套）
    #    _RE_BARE_JSON_OBJ 自身无法处理 1 层以上嵌套，用循环直到无变化
    prev = None
    while prev != out:
        prev = out
        out = _RE_BARE_JSON_OBJ.sub(PLACEHOLDER, out)

    # 3) 替换 _MOVE_RE 走法字符串
    out = _MOVE_RE.sub(PLACEHOLDER, out)

    # 合并多处连续占位符
    out = re.sub(r"(?:（走法已省略）\s*){2,}", "（走法已省略）", out)
    return out.strip()


class AIThoughtPanel(QWidget):
    """右侧 AI 思考记录面板。

    协议（由 ai_engine._AISignals.thought_received 触发）：
        card._on_thought_received(side_cn, model_name, raw_text)
            → self.add_thought(step=auto, side=side_cn, model=model_name, text=raw_text)
    """

    # 折叠/展开按钮字符
    _BTN_COLLAPSE = "▼"
    _BTN_EXPAND = "▲"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        # 步数自增计数器
        self._step = 0
        self._total_chars = 0
        self._collapsed = False
        self._md_buffer = ""  # 自维护 markdown 全文（Qt 5.15 无 insertMarkdown）

        # 整体布局
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── 顶部工具栏 ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self._title_label = QLabel("🤖 AI 思考记录")
        font = QFont("Microsoft YaHei", 11)
        font.setBold(True)
        self._title_label.setFont(font)

        self._auto_scroll = QCheckBox("自动滚动")
        self._auto_scroll.setChecked(True)

        self._copy_btn = QPushButton("📋 复制")
        self._copy_btn.setFixedHeight(26)
        self._copy_btn.clicked.connect(self.copy_all)

        self._clear_btn = QPushButton("🗑 清空")
        self._clear_btn.setFixedHeight(26)
        self._clear_btn.clicked.connect(self.clear_all)

        self._collapse_btn = QPushButton(self._BTN_COLLAPSE)
        self._collapse_btn.setFixedSize(28, 26)
        self._collapse_btn.clicked.connect(self._toggle_collapse)

        toolbar.addWidget(self._title_label)
        toolbar.addStretch(1)
        toolbar.addWidget(self._auto_scroll)
        toolbar.addWidget(self._copy_btn)
        toolbar.addWidget(self._clear_btn)
        toolbar.addWidget(self._collapse_btn)
        root.addLayout(toolbar)

        # ── 内容区（QTextBrowser 支持 setMarkdown）──
        self._text_browser = QTextBrowser()
        self._text_browser.setOpenExternalLinks(False)
        self._text_browser.setMinimumWidth(280)
        self._text_browser.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # 主题感知底色（白底黑字）
        try:
            from app.utils.design_tokens import Colors  # type: ignore

            self._text_browser.setStyleSheet(
                f"QTextBrowser {{ background-color: #fafafa;"
                f" color: {Colors.TEXT_PRIMARY};"
                f" border: 1px solid {Colors.BORDER};"
                f" border-radius: 6px; padding: 8px; }}"
            )
        except Exception:
            self._text_browser.setStyleSheet(
                "QTextBrowser { background-color: #fafafa; color: #1a1a1a;"
                " border: 1px solid #3d3d3d; border-radius: 6px; padding: 8px; }"
            )
        root.addWidget(self._text_browser)

        # ── 底部状态栏 ──
        self._status_label = QLabel("0 条 · 0 字符")
        self._status_label.setStyleSheet("color: rgba(0,0,0,0.45); font-size: 11px;")
        root.addWidget(self._status_label)

    # ══════════════════════════════════════════════════════════════════

    def add_thought(self, side: str, model: str, text: str) -> int:
        """追加一条 AI 思考记录（外部主线程调用）。

        Args:
            side: '红' / '黑'（执子方中文）
            model: 模型显示名
            text: LLM 原始响应（已剥离 <think>）

        Returns:
            step（新增的步数，从 1 起）
        """
        self._step += 1
        cleaned = strip_json_and_moves(text or "")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 构造 Markdown 片段
        md = (
            f"\n\n---\n\n"
            f"**第 {self._step} 步 · {side}方 · {model}** · `{ts}`\n\n"
            f"{cleaned or '_（无文本，已自动剥离走法）_'}"
        )

        # Qt 5.15 无 insertMarkdown（仅 Qt 6.4+ 有），改用自维护 markdown
        # 缓冲区 + setMarkdown 整体重渲染（setMarkdown 在 Qt 5.15 可用）
        self._md_buffer += md
        self._text_browser.setMarkdown(self._md_buffer)

        # 统计字符
        self._total_chars += len(cleaned)
        self._refresh_status()

        if self._auto_scroll.isChecked():
            self._scroll_to_bottom()

        return self._step

    def copy_all(self) -> None:
        """复制全部 Markdown 文本到剪贴板。"""
        try:
            QGuiApplication.clipboard().setText(self._text_browser.toPlainText())
            logger.debug("[chinese-chess] 复制全部 Markdown")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[chinese-chess] 复制失败: {e}")

    def clear_all(self) -> None:
        """清空面板。"""
        self._text_browser.clear()
        self._md_buffer = ""
        self._step = 0
        self._total_chars = 0
        self._refresh_status()

    def _toggle_collapse(self) -> None:
        """折叠/展开 内容区。"""
        self._collapsed = not self._collapsed
        if self._collapsed:
            self._text_browser.setVisible(False)
            self._collapse_btn.setText(self._BTN_EXPAND)
        else:
            self._text_browser.setVisible(True)
            self._collapse_btn.setText(self._BTN_COLLAPSE)

    def _scroll_to_bottom(self) -> None:
        """自动滚动到底部。"""
        try:
            sb = self._text_browser.verticalScrollBar()
            sb.setValue(sb.maximum())
        except Exception:  # noqa: BLE001
            pass

    def _refresh_status(self) -> None:
        self._status_label.setText(f"{self._step} 条 · {self._total_chars} 字符")

    # ── 测试钩子（方便单测）──

    def get_step(self) -> int:
        return self._step

    def get_total_chars(self) -> int:
        return self._total_chars

    def get_text(self) -> str:
        return self._text_browser.toPlainText()


# ── 模块导出 ──
__all__ = [
    "AIThoughtPanel",
    "strip_json_and_moves",
    "PLACEHOLDER",
]
