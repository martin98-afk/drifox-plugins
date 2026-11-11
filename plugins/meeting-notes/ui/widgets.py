# -*- coding: utf-8 -*-
"""卡片内自绘控件：可编辑标题、可编辑说话人徽章、会议列表项、转写行、录音按钮。

交互取向（现代桌面软件）：改名一律就地编辑——双击标题直接改，点说话人徽章直接改，
回车/失焦提交、Esc 取消。不弹输入框。

样式全部走 QSS + 少量 paintEvent，颜色来自 Theme（跟随宿主主题 token）。
"""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QEvent, QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from loguru import logger

from .store import Meeting, _fmt_clock
from .theme import RECORD_RED, Theme


class EditableTitle(QWidget):
    """双击就地编辑的标题文本。"""

    edited = pyqtSignal(str)

    def __init__(
        self,
        text: str,
        theme: Theme,
        font_delta: int = 0,
        weight: int = 600,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self._font_delta = font_delta
        self._weight = weight
        self._cancelling = False

        self._label = QLabel(text, self)
        self._label.setCursor(Qt.IBeamCursor)
        self._label.setToolTip("双击重命名")
        self._label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._label.installEventFilter(self)

        self._edit = QLineEdit(self)
        self._edit.hide()
        self._edit.editingFinished.connect(self._commit)
        self._edit.installEventFilter(self)

        lay = QStackedLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._label)
        lay.addWidget(self._edit)
        lay.setCurrentWidget(self._label)
        self._lay = lay

        self.apply_theme(theme)

    # ── 对外 ──

    def text(self) -> str:
        return self._label.text()

    def setText(self, text: str) -> None:
        self._label.setText(text)

    def set_tooltip(self, text: str) -> None:
        self._label.setToolTip(text)

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        t = theme
        self._label.setStyleSheet(
            f"background: transparent; {t.font(self._font_delta, self._weight)} "
            f"{t.fg(t.text_primary)}"
        )
        self._edit.setStyleSheet(
            "QLineEdit {"
            f"background: {t.hover_bg}; color: {t.text_primary};"
            f"border: 1px solid {t.dim(t.accent, 0.8)}; border-radius: 6px;"
            f"padding: 1px 6px; {t.font(self._font_delta, self._weight)}"
            "}"
        )

    # ── 交互 ──

    def eventFilter(self, obj, event):  # noqa: N802 — Qt 命名
        if obj is self._label and event.type() == QEvent.MouseButtonDblClick:
            self.start_edit()
            return True
        if obj is self._edit and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self.cancel_edit()
                return True
        return super().eventFilter(obj, event)

    def start_edit(self) -> None:
        if self._lay.currentWidget() is self._edit:
            return
        self._cancelling = False
        self._edit.setText(self._label.text())
        width = max(self._label.width() + 80, 200)
        self._edit.setMinimumWidth(width)
        # 必须切 currentWidget：只 show() 会让输入框和标签叠在一起
        self._lay.setCurrentWidget(self._edit)
        self._edit.setFocus()
        self._edit.selectAll()

    def cancel_edit(self) -> None:
        self._cancelling = True
        self._lay.setCurrentWidget(self._label)

    def _commit(self) -> None:
        if self._cancelling:
            self._cancelling = False
            return
        if self._lay.currentWidget() is not self._edit:
            return
        new_text = self._edit.text().strip()
        self._lay.setCurrentWidget(self._label)
        if new_text and new_text != self._label.text():
            self._label.setText(new_text)
            self.edited.emit(new_text)


class EditableBadge(QLabel):
    """说话人胶囊：单击就地改名。"""

    edited = pyqtSignal(str)

    def __init__(self, speaker: str, label: str, theme: Theme, parent=None) -> None:
        super().__init__(label, parent)
        self.speaker = speaker
        self._theme = theme
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("点击重命名")
        self.setAlignment(Qt.AlignCenter)
        self._edit: Optional[QLineEdit] = None
        self.apply_theme(theme)

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        color = theme.speaker_color(self.speaker)
        self.setStyleSheet(
            f"background: {theme.dim(color, 0.16)};"
            f"color: {color};"
            f"border: 1px solid {theme.dim(color, 0.35)};"
            "border-radius: 9px; padding: 1px 8px;"
            f"{theme.font(-3, 600)}"
        )

    def set_data(self, speaker: str, label: str, theme: Theme) -> None:
        """复用控件改数据：只重算样式当 speaker 变了（颜色按编号取）。"""
        changed = speaker != self.speaker
        self.speaker = speaker
        self._theme = theme
        self.setText(label)
        if changed:
            self.apply_theme(theme)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._start_inline_edit()
        super().mousePressEvent(event)

    def _start_inline_edit(self) -> None:
        """在徽章位置上叠一个输入框，回车/失焦提交，Esc 取消。"""
        if self._edit is not None:
            return
        t = self._theme
        color = t.speaker_color(self.speaker)
        edit = QLineEdit(self.window())
        edit.setText(self.text())
        edit.setStyleSheet(
            "QLineEdit {"
            f"background: {t.card_bg_solid}; color: {color};"
            f"border: 1px solid {t.dim(color, 0.7)}; border-radius: 9px;"
            f"padding: 1px 8px; {t.font(-3, 600)}"
            "}"
        )
        edit.setFixedWidth(max(self.width() + 60, 120))
        edit.setFixedHeight(max(self.height(), 22))
        global_pos = self.mapToGlobal(self.rect().topLeft())
        edit.move(edit.parentWidget().mapFromGlobal(global_pos))
        edit.show()
        edit.setFocus()
        edit.selectAll()
        edit.editingFinished.connect(lambda: self._finish_inline_edit(edit))
        edit.installEventFilter(self)
        self._edit = edit

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self._edit and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self._close_editor(commit=False)
                return True
        return super().eventFilter(obj, event)

    def _finish_inline_edit(self, edit: QLineEdit) -> None:
        self._close_editor(commit=True, text=edit.text().strip())

    def _close_editor(self, commit: bool, text: str = "") -> None:
        edit, self._edit = self._edit, None
        if edit is None:
            return
        try:
            edit.removeEventFilter(self)
            edit.deleteLater()
        except RuntimeError:
            pass
        if commit:
            self.edited.emit(text)


class RecordButton(QPushButton):
    """圆形录音按钮，三态：录音（麦克风） / 暂停（两条竖线） / 继续（三角）。

    自绘而不用图标字体：按钮底色是强调色/红色，qfluentwidgets 的 FluentIcon
    按主题取色，在彩色底上会变暗看不清；自绘能保证白描边在任何底色上可见。
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._mode = "record"
        self._accent = "#2563eb"
        self._hover = False
        self.setFixedSize(52, 52)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("background: transparent; border: none;")
        self.setFocusPolicy(Qt.NoFocus)

    def set_colors(self, accent: str) -> None:
        self._accent = accent
        self.update()

    def set_mode(self, mode: str) -> None:
        """mode: record（空闲）/ pause（录音中）/ resume（暂停中）。"""
        self._mode = mode
        self.update()

    def enterEvent(self, event):  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        recording = self._mode in ("pause", "resume")
        base = QColor(RECORD_RED if recording else self._accent)
        if self._hover:
            base = base.lighter(112)
        if not self.isEnabled():
            base.setAlpha(90)
        rect = QRectF(1.5, 1.5, self.width() - 3, self.height() - 3)
        p.setPen(Qt.NoPen)
        p.setBrush(base)
        p.drawEllipse(rect)

        cx, cy = self.width() / 2.0, self.height() / 2.0
        white = QColor("#ffffff")
        if not self.isEnabled():
            white.setAlpha(130)

        if self._mode == "pause":
            # 两条竖线：暂停
            p.setBrush(white)
            p.drawRoundedRect(QRectF(cx - 6.0, cy - 7.0, 4.0, 14.0), 1.6, 1.6)
            p.drawRoundedRect(QRectF(cx + 2.0, cy - 7.0, 4.0, 14.0), 1.6, 1.6)
        elif self._mode == "resume":
            # 三角：继续
            path = QPolygonF(
                [
                    QPointF(cx - 4.5, cy - 8.0),
                    QPointF(cx + 8.0, cy),
                    QPointF(cx - 4.5, cy + 8.0),
                ]
            )
            p.setBrush(white)
            p.drawPolygon(path)
        else:
            p.setBrush(white)
            p.drawRoundedRect(QRectF(cx - 4.0, cy - 9.5, 8.0, 14.0), 4.0, 4.0)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(white, 2.0, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(QRectF(cx - 8.5, cy - 4.5, 17.0, 14.0), 200 * 16, 140 * 16)
            p.drawLine(QPointF(cx, cy + 9.5), QPointF(cx, cy + 14.0))
            p.drawLine(QPointF(cx - 4.5, cy + 14.0), QPointF(cx + 4.5, cy + 14.0))
        p.end()


class MeetingListItem(QFrame):
    """左侧会议列表的单条：双击标题就地改名，右键出快捷菜单。"""

    clicked = pyqtSignal(str)
    renamed = pyqtSignal(str, str)  # (meeting_id, new_title)
    context_requested = pyqtSignal(str, object)  # (meeting_id, global_pos)

    def __init__(self, meeting: Meeting, theme: Theme, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.meeting_id = meeting.id
        self._selected = False
        self._status = meeting.status
        self._has_summary = bool((meeting.summary_md or "").strip())
        self._theme = theme
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(66)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(3)

        top = QHBoxLayout()
        top.setSpacing(6)
        self._title = EditableTitle(meeting.display_title(), theme, font_delta=0, weight=600, parent=self)
        self._title.edited.connect(self._on_title_edited)
        # 搜索用的小写标题缓存：避免每次输入都去读磁盘上的会议文件
        self.search_text = meeting.display_title().lower()
        top.addWidget(self._title, 1)
        self._dot = QLabel()
        self._dot.setFixedSize(8, 8)
        top.addWidget(self._dot, 0, Qt.AlignVCenter)
        lay.addLayout(top)

        meta_bits = [meeting.created_at and _fmt_date(meeting.created_at) or ""]
        if meeting.duration_sec:
            meta_bits.append(_fmt_clock(meeting.duration_sec))
        self._meta = QLabel(" · ".join([b for b in meta_bits if b]))
        lay.addWidget(self._meta)

        self.apply_theme(theme)

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._title.apply_theme(theme)
        self._meta.setStyleSheet(
            f"background: transparent; border: none; {theme.font(-3)} {theme.fg(theme.text_muted)}"
        )
        if self._status == "recording":
            self._dot.setStyleSheet(f"background: {theme.error}; border-radius: 4px;")
        elif self._has_summary:
            self._dot.setStyleSheet(f"background: {theme.success}; border-radius: 4px;")
        else:
            self._dot.setStyleSheet("background: transparent;")
        self._apply_state()

    def set_status(self, status: str, theme: Theme) -> None:
        self._status = status
        self.apply_theme(theme)

    def _on_title_edited(self, text: str) -> None:
        self.search_text = (text or "").lower()
        self.renamed.emit(self.meeting_id, text)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._apply_state()

    def _apply_state(self) -> None:
        theme = self._theme
        bg = theme.selected_bg if self._selected else "transparent"
        border = theme.dim(theme.accent, 0.45) if self._selected else "transparent"
        self.setStyleSheet(
            "MeetingListItem {"
            f"background: {bg}; border: 1px solid {border}; border-radius: 10px;"
            "}"
            f"MeetingListItem:hover {{ background: {theme.selected_bg if self._selected else theme.hover_bg}; }}"
        )

    def mousePressEvent(self, event):  # noqa: N802 — Qt 命名
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.meeting_id)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):  # noqa: N802
        self.context_requested.emit(self.meeting_id, event.globalPos())


class TranscriptRow(QWidget):
    """一条转写：[00:12] [说话人 1] 文本…

    支持 set_data 就地复用：转写整页刷新时逐行改数据比销毁重建快两个数量级
    （600 行实测 327ms → 1ms），精转与说话人改名都因此不再卡主线程。
    """

    speaker_renamed = pyqtSignal(str, str)  # (speaker, new_name)

    def __init__(
        self,
        t: float,
        speaker: str,
        label: str,
        text: str,
        theme: Theme,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self._speaker = ""
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 3, 0, 3)
        lay.setSpacing(10)
        self._lay = lay

        self._time = QLabel(_fmt_clock(t))
        self._time.setFixedWidth(52)
        self._time.setAlignment(Qt.AlignRight | Qt.AlignTop)
        lay.addWidget(self._time, 0, Qt.AlignTop)

        self._badge: Optional[EditableBadge] = None
        self._text = QLabel(text)
        self._text.setWordWrap(True)
        self._text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lay.addWidget(self._text, 1)

        self.set_data(t, speaker, label, text, theme)
        # 首帧保证行级 QSS 生效：set_data 的 theme_changed 此时为 False
        self.apply_theme(theme)

    def set_data(
        self, t: float, speaker: str, label: str, text: str, theme: Theme
    ) -> None:
        """复用本行显示另一段数据。只改文字，不重建子控件。

        QSS 只取决于 theme 对象与 speaker 颜色：theme 没换、speaker 没变时
        跳过 apply_theme，否则 600 行的 3 次 setStyleSheet polish 会吃掉 37ms。
        """
        theme_changed = theme is not self._theme
        self._theme = theme
        self._speaker = speaker
        self._time.setText(_fmt_clock(t))
        self._text.setText(text)
        if speaker:
            if self._badge is None:
                self._badge = EditableBadge(speaker, label, theme)
                self._badge.edited.connect(self._on_badge_edited)
                self._lay.insertWidget(1, self._badge, 0, Qt.AlignTop)
            else:
                self._badge.set_data(speaker, label, theme)
            self._badge.setVisible(True)
        elif self._badge is not None:
            # 隐藏不计入布局尺寸；保留控件以便下次 set_data 再用
            self._badge.setVisible(False)
        # badge 的 set_data 已按 speaker 变化重算自身 QSS；行级两类标签的 QSS
        # 只随 theme 变，speaker 变化不影响它们的样式
        if theme_changed:
            self.apply_theme(theme)

    def update_speaker_label(self, speaker: str, label: str) -> None:
        """说话人改名：只更新匹配徽章的文字，零重建。"""
        if self._badge is not None and self._badge.speaker == speaker:
            self._badge.setText(label)

    def _on_badge_edited(self, name: str) -> None:
        # 动态取当前 speaker：复用行后编号会变，不能捕获构造时的值
        self.speaker_renamed.emit(self._speaker, name)

    def apply_theme(self, theme: Theme) -> None:
        self._time.setStyleSheet(
            f"background: transparent; {theme.font(-3)} {theme.fg(theme.text_muted)}"
        )
        self._text.setStyleSheet(
            f"background: transparent; {theme.font(0)} {theme.fg(theme.text_primary)}"
        )
        if self._badge is not None:
            self._badge.apply_theme(theme)


class EmptyState(QWidget):
    """空状态：一行主文案 + 一行引导。"""

    def __init__(self, title: str, subtitle: str, theme: Theme, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 40, 24, 40)
        lay.setSpacing(8)
        lay.addStretch(1)
        self._title = QLabel(title)
        self._title.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._title)
        self._sub = QLabel(subtitle)
        self._sub.setAlignment(Qt.AlignCenter)
        self._sub.setWordWrap(True)
        lay.addWidget(self._sub)
        lay.addStretch(1)
        self.apply_theme(theme)

    def apply_theme(self, theme: Theme) -> None:
        self._title.setStyleSheet(
            f"background: transparent; {theme.font(2, 600)} {theme.fg(theme.text_secondary)}"
        )
        self._sub.setStyleSheet(
            f"background: transparent; {theme.font(-1)} {theme.fg(theme.text_muted)}"
        )


def _fmt_date(ts: float) -> str:
    import time

    try:
        return time.strftime("%m-%d %H:%M", time.localtime(ts))
    except (ValueError, OSError) as e:
        logger.debug(f"[meeting-notes] 时间格式化失败: {e}")
        return ""
