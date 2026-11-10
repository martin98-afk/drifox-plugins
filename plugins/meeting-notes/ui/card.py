# -*- coding: utf-8 -*-
"""会议纪要 full 卡片：左侧会议列表 + 右侧转写/纪要。

状态机::

    idle ──开始会议──▶ recording ──结束──▶ transcribing ──▶ summarizing ──▶ idle
      ▲                                          │
      └────────────── 识别队列清空后逐段精转 ◀────┘

线程模型：
- 录音与切片在主线程（MCI/AVFoundation 调用都在毫秒级，不阻塞事件循环）
- 识别走 TranscribeQueue 的后台线程，结果经 pyqtSignal 转主线程
- 分段精转、AI 纪要各起独立后台线程，同样经信号回主线程
"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    FluentIcon,
    PushButton,
    SearchLineEdit,
    SegmentedWidget,
    SmoothScrollArea,
    TransparentToolButton,
)

from . import asr, config, recorder as recorder_mod, store, summary as summary_mod
from .markdown import to_html as md_to_html
from .store import Meeting
from .theme import RECORD_RED, Theme
from .widgets import (
    EditableTitle,
    EmptyState,
    MeetingListItem,
    RecordButton,
    TranscriptRow,
)

PLUGIN_NAME = "meeting-notes"

# 识别队列轮询间隔：队列空闲且录音已结束 → 触发精转收尾
_IDLE_POLL_MS = 700

# 增量精转：录音中每攒够这么久就后台精转一段（秒）
_REFINE_SEGMENT_SEC = 600
# 不足这么长的尾巴不单独精转（秒）
_MIN_REFINE_SEC = 30


class MeetingNotesCard(QWidget):
    """会议纪要主卡片。"""

    closed = pyqtSignal()

    # 后台线程 → 主线程（必须用信号：daemon 线程没有 Qt 事件循环，
    # QTimer.singleShot 在那种线程里永远不会触发）
    _sig_asr_result = pyqtSignal(object)
    _sig_asr_error = pyqtSignal(object, str)
    _sig_refine_done = pyqtSignal(object, bool)
    _sig_summary_done = pyqtSignal(str)
    _sig_summary_error = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._context_provider: Optional[Callable[[], dict]] = None
        self._theme = Theme({})

        # 会议状态
        self._meeting: Optional[Meeting] = None
        self._items: Dict[str, MeetingListItem] = {}

        # 录音状态
        self._recorder = None
        self._joiner: Optional[store.WavJoiner] = None
        self._queue: Optional[asr.TranscribeQueue] = None
        self._tmp_dir: Optional[Path] = None
        self._chunk_index = 0
        self._chunk_offset = 0.0
        self._rec_started_at = 0.0
        self._elapsed_base = 0.0
        self._recording = False
        self._paused = False
        self._finished_pending = False  # 录音已停，等队列清空并精转完剩余的尾段
        self._summarizing = False
        self._refining = False
        # 实时片段与精转结果会从不同线程改写 segments
        self._seg_lock = threading.RLock()

        self._chunk_timer = QTimer(self)
        self._chunk_timer.setSingleShot(True)
        self._chunk_timer.timeout.connect(self._rotate_chunk)

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._tick)

        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(_IDLE_POLL_MS)
        self._idle_timer.timeout.connect(self._on_idle_poll)

        # 透明背景由宿主容器承托（与内置 full 卡一致）
        self.setProperty("transparentOverlay", True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("")

        # 后台线程 → 主线程的信号汇入点（Qt 自动走 QueuedConnection）
        self._sig_asr_result.connect(self._on_asr_result)
        self._sig_asr_error.connect(self._on_asr_error)
        self._sig_refine_done.connect(self._on_refine_done)
        self._sig_summary_done.connect(self._on_summary_done)
        self._sig_summary_error.connect(self._on_summary_error)

        self._build_ui()

    # ══════════════════════════════════════════════════
    #  宿主接口
    # ══════════════════════════════════════════════════

    def set_context_provider(self, provider: Callable[[], dict]) -> None:
        self._context_provider = provider

    def _ctx(self) -> Dict[str, Any]:
        if not callable(self._context_provider):
            return {}
        try:
            return self._context_provider() or {}
        except Exception as e:  # noqa: BLE001 — ctx 失败不阻塞卡片
            logger.debug(f"[meeting-notes] 取上下文失败: {e}")
            return {}

    def show_card(self) -> None:
        self.apply_theme()
        self._reload_list()
        self.setVisible(True)

    def apply_theme(self) -> None:
        self._theme = Theme(self._ctx())
        t = self._theme
        side_bg = t.dim("#000000", 0.18 if t.is_dark else 0.035)
        # 内容面板自带底色：整页铺满的实心面，跟壁纸隔开
        self.setStyleSheet(
            f"MeetingNotesCard {{ background: transparent; {t.font()} }}"
            "QFrame#mnPanel {"
            f"background: {t.card_bg_solid};"
            f"border: 1px solid {t.border};"
            "border-radius: 0px;"
            "}"
            "QFrame#mnSide {"
            f"background: {side_bg};"
            f"border-right: 1px solid {t.border};"
            "}"
        )

        self._title_edit.apply_theme(t)
        self._side_title.setStyleSheet(
            f"background: transparent; {t.font(3, 700)} {t.fg(t.text_primary)}"
        )
        self._meta_lbl.setStyleSheet(
            f"background: transparent; {t.font(-2)} {t.fg(t.text_muted)}"
        )
        self._list_empty.setStyleSheet(
            f"background: transparent; {t.font(-1)} {t.fg(t.text_muted)}"
        )
        self._side_count.setStyleSheet(
            f"background: transparent; {t.font(-3)} {t.fg(t.text_muted)}"
        )
        self._ctrl_card.setStyleSheet(
            "QFrame#ctrlCard {"
            f"background: {t.card_bg}; border: 1px solid {t.border}; border-radius: 14px;"
            "}"
        )
        self._status_lbl.setStyleSheet(
            f"background: transparent; {t.font(0, 600)} {t.fg(t.text_primary)}"
        )
        self._hint_lbl.setStyleSheet(
            f"background: transparent; {t.font(-2)} {t.fg(t.text_muted)}"
        )
        self._timer_lbl.setStyleSheet(
            f"background: transparent; font-family: 'Consolas','Menlo',monospace;"
            f" font-size: {t.font_size + 2}px; font-weight: 600; {t.fg(t.text_primary)}"
        )
        self._apply_record_button_style()
        # 结束按钮：录音中才出现的次级动作
        self._stop_btn.setStyleSheet(
            "QPushButton {"
            f"background: {t.dim(RECORD_RED, 0.12)}; color: {RECORD_RED};"
            f"border: 1px solid {t.dim(RECORD_RED, 0.38)}; border-radius: 8px;"
            f"padding: 6px 16px; {t.font(-1, 600)}"
            "}"
            f"QPushButton:hover {{ background: {t.dim(RECORD_RED, 0.2)}; }}"
        )
        # 纪要动作：次级按钮，只有纪要页才出现
        self._summary_btn.setStyleSheet(
            "QPushButton {"
            f"background: transparent; color: {t.accent};"
            f"border: 1px solid {t.dim(t.accent, 0.45)}; border-radius: 8px;"
            f"padding: 5px 14px; {t.font(-1, 600)}"
            "}"
            f"QPushButton:hover {{ background: {t.dim(t.accent, 0.12)}; }}"
            f"QPushButton:disabled {{ color: {t.text_muted};"
            f" border-color: {t.border}; }}"
        )
        self._seg.setStyleSheet(
            f"SegmentedWidget {{ background: transparent; }}"
            f"SegmentedWidget::item {{ color: {t.text_secondary}; {t.font(-1)} }}"
            f"SegmentedWidget::item:selected {{ color: {t.text_primary}; }}"
        )
        self._empty_right.apply_theme(t)
        self._browser.setStyleSheet(
            f"QTextBrowser {{ background: transparent; border: none; {t.fg(t.text_primary)} }}"
        )

        for item in self._items.values():
            item.apply_theme(t)
        for row in self._find_rows():
            row.apply_theme(t)

        self._render_meta()

    def _summary_css(self) -> Dict[str, str]:
        """纪要渲染的内联样式表。

        必须内联：Qt 富文本引擎对 heading 标签有内置格式，setDefaultStyleSheet
        的 font-size 被内置值覆盖（实测标题永远异常大）。因此 markdown 转换器
        把标题输出为 <p style="...">。
        """
        t = self._theme
        # 正文比全局字号大 2px：满屏阅读距离下 14px 偏小
        body = t.font_size + 2
        return {
            "h1": f"font-size:{body + 6}px; font-weight:700; color:{t.text_primary};"
            " margin-top:2px; margin-bottom:10px;",
            "h2": f"font-size:{body + 3}px; font-weight:700; color:{t.text_primary};"
            " margin-top:20px; margin-bottom:8px;",
            "h3": f"font-size:{body + 1}px; font-weight:600; color:{t.text_secondary};"
            " margin-top:14px; margin-bottom:6px;",
            "p": f"font-size:{body}px; color:{t.text_primary}; margin-top:2px; margin-bottom:8px;",
            "li": f"font-size:{body}px; color:{t.text_primary}; margin-bottom:6px;"
            " margin-left:6px;",
            "td": f"font-size:{body - 1}px; color:{t.text_primary}; padding:4px 10px;",
            "th": f"font-size:{body - 1}px; color:{t.text_primary}; font-weight:600;"
            " padding:4px 10px;",
        }

    # ══════════════════════════════════════════════════
    #  UI 构建
    # ══════════════════════════════════════════════════

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 内容面板：整页铺满且自身不透明。full 卡容器是透明承托，
        # 不铺底的话主题壁纸会直接透上来，正文对比度不够。
        self._panel = QFrame(self)
        self._panel.setObjectName("mnPanel")
        outer.addWidget(self._panel)

        root = QHBoxLayout(self._panel)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_left(), 0)
        root.addWidget(self._build_right(), 1)

    def _build_left(self) -> QWidget:
        panel = QFrame(self._panel)
        panel.setObjectName("mnSide")
        panel.setFixedWidth(284)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(16, 14, 12, 12)
        lay.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(6)
        self._side_title = QLabel("会议", panel)
        head.addWidget(self._side_title)
        head.addStretch(1)
        self._side_count = QLabel("", panel)
        head.addWidget(self._side_count)
        lay.addLayout(head)

        self._search = SearchLineEdit(panel)
        self._search.setPlaceholderText("搜索会议")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_search)
        lay.addWidget(self._search)

        # 新建会议：显式入口。麦克风只负责「在会议内录音」，不再兼职开新会议
        self._new_btn = PushButton(FluentIcon.ADD, "新建会议", panel)
        self._new_btn.setCursor(Qt.PointingHandCursor)
        self._new_btn.clicked.connect(self._on_new_meeting)
        lay.addWidget(self._new_btn)

        self._list_scroll = SmoothScrollArea(panel)
        self._list_scroll.setWidgetResizable(True)
        self._list_scroll.setFrameShape(QFrame.NoFrame)
        self._list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list_scroll.enableTransparentBackground()
        self._list_host = QWidget()
        self._list_host.setStyleSheet("background: transparent;")
        self._list_lay = QVBoxLayout(self._list_host)
        self._list_lay.setContentsMargins(0, 0, 4, 0)
        self._list_lay.setSpacing(6)
        self._list_lay.addStretch(1)
        self._list_scroll.setWidget(self._list_host)

        self._list_empty = QLabel("还没有会议记录\n点上方麦克风开第一场", self._list_host)
        self._list_empty.setAlignment(Qt.AlignCenter)
        self._list_lay.insertWidget(0, self._list_empty)
        lay.addWidget(self._list_scroll, 1)
        return panel

    def _build_right(self) -> QWidget:
        panel = QWidget(self._panel)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(20, 14, 20, 14)
        lay.setSpacing(12)

        # 标题区：标题 + 元信息在左，「更多」菜单在右（重命名/导出/删除都收进去）
        head = QHBoxLayout()
        head.setSpacing(6)
        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        self._title_edit = EditableTitle("会议纪要", self._theme, font_delta=9, weight=700, parent=panel)
        self._title_edit.setMinimumWidth(240)
        self._title_edit.edited.connect(self._on_title_changed)
        title_box.addWidget(self._title_edit)
        self._meta_lbl = QLabel("", panel)
        title_box.addWidget(self._meta_lbl)
        head.addLayout(title_box, 1)
        self._timer_lbl = QLabel("00:00", panel)
        head.addWidget(self._timer_lbl, 0, Qt.AlignTop)
        self._more_btn = TransparentToolButton(FluentIcon.MORE, panel)
        self._more_btn.setToolTip("更多操作")
        self._more_btn.clicked.connect(self._on_more_menu)
        self._more_btn.setVisible(False)
        head.addWidget(self._more_btn, 0, Qt.AlignTop)
        lay.addLayout(head)

        # 录音控制卡：状态在左，操作全部右对齐（主按钮三态：录音/暂停/继续）
        self._ctrl_card = QFrame(panel)
        self._ctrl_card.setObjectName("ctrlCard")
        ctrl = QHBoxLayout(self._ctrl_card)
        ctrl.setContentsMargins(16, 12, 16, 12)
        ctrl.setSpacing(10)

        texts = QVBoxLayout()
        texts.setSpacing(3)
        self._status_lbl = QLabel("准备开始", self._ctrl_card)
        texts.addWidget(self._status_lbl)
        self._hint_lbl = QLabel("点右侧麦克风开始录音，自动分片转写", self._ctrl_card)
        texts.addWidget(self._hint_lbl)
        ctrl.addLayout(texts, 1)

        self._stop_btn = QPushButton("结束", self._ctrl_card)
        self._stop_btn.setCursor(Qt.PointingHandCursor)
        self._stop_btn.setToolTip("结束本次录音并整理转写")
        self._stop_btn.clicked.connect(self._on_stop_clicked)
        self._stop_btn.setVisible(False)
        ctrl.addWidget(self._stop_btn)

        self._record_btn = RecordButton(self._ctrl_card)
        self._record_btn.clicked.connect(self._on_record_clicked)
        ctrl.addWidget(self._record_btn)

        lay.addWidget(self._ctrl_card)

        # Tab 行：左侧切视图，右侧放「当前视图的动作」（纪要页 → 生成纪要）
        tab_row = QHBoxLayout()
        tab_row.setSpacing(8)
        self._seg = SegmentedWidget(panel)
        self._seg.addItem("transcript", "实时转写", lambda: self._switch_tab(0))
        self._seg.addItem("summary", "AI 纪要", lambda: self._switch_tab(1))
        self._seg.setCurrentItem("transcript")
        tab_row.addWidget(self._seg, 0, Qt.AlignLeft)
        tab_row.addStretch(1)

        self._summary_btn = QPushButton("生成纪要", panel)
        self._summary_btn.setCursor(Qt.PointingHandCursor)
        self._summary_btn.setToolTip("用当前转写稿生成结构化纪要")
        self._summary_btn.clicked.connect(self._on_generate_summary)
        self._summary_btn.setVisible(False)
        tab_row.addWidget(self._summary_btn, 0, Qt.AlignRight)
        lay.addLayout(tab_row)

        self._stack = QStackedWidget(panel)
        self._stack.addWidget(self._build_transcript_page())
        self._stack.addWidget(self._build_summary_page())
        lay.addWidget(self._stack, 1)

        return panel

    def _build_transcript_page(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._tr_scroll = SmoothScrollArea(page)
        self._tr_scroll.setWidgetResizable(True)
        self._tr_scroll.setFrameShape(QFrame.NoFrame)
        self._tr_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._tr_scroll.enableTransparentBackground()
        self._tr_host = QWidget()
        self._tr_host.setStyleSheet("background: transparent;")
        self._tr_lay = QVBoxLayout(self._tr_host)
        self._tr_lay.setContentsMargins(4, 8, 12, 8)
        self._tr_lay.setSpacing(2)
        self._tr_lay.addStretch(1)
        self._tr_scroll.setWidget(self._tr_host)
        lay.addWidget(self._tr_scroll, 1)

        self._empty_right = EmptyState(
            "还没有转写内容",
            "点右侧麦克风开始录音：发言会按片实时转写，结束后自动整理成纪要。",
            self._theme,
            page,
        )
        lay.addWidget(self._empty_right, 1)
        self._tr_scroll.setVisible(False)
        return page

    def _build_summary_page(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        self._browser = QTextBrowser(page)
        self._browser.setOpenExternalLinks(True)
        self._browser.setFrameShape(QFrame.NoFrame)
        self._browser.setPlaceholderText("会议结束后，这里会显示 AI 生成的纪要与待办")
        lay.addWidget(self._browser, 1)
        return page

    def _apply_record_button_style(self) -> None:
        t = self._theme
        self._record_btn.set_colors(t.accent)
        if not self._recording:
            mode = "record"
        elif self._paused:
            mode = "resume"
        else:
            mode = "pause"
        self._record_btn.set_mode(mode)
        self._record_btn.setToolTip(
            {"record": "开始录音", "pause": "暂停录音", "resume": "继续录音"}[mode]
        )

    # ══════════════════════════════════════════════════
    #  左侧列表
    # ══════════════════════════════════════════════════

    def _reload_list(self) -> None:
        # 必须在布局里 takeAt 移除：只 setParent(None) 会在布局里留下无效项，
        # 多次刷新后列表底部出现幽灵空白
        for i in reversed(range(self._list_lay.count())):
            it = self._list_lay.itemAt(i)
            w = it.widget() if it is not None else None
            if isinstance(w, MeetingListItem):
                self._list_lay.takeAt(i)
                w.setParent(None)
                w.deleteLater()
        self._items.clear()

        meetings = store.list_meetings()
        # 清掉没有内容的空会议：只有「新建会议」会产生 draft，留着只会堆垃圾
        alive = []
        for m in meetings:
            if (
                m.status == "draft"
                and _is_empty_meeting(m)
                and (self._meeting is None or m.id != self._meeting.id)
            ):
                store.delete(m.id)
                continue
            alive.append(m)
        meetings = alive

        for m in meetings:
            item = MeetingListItem(m, self._theme, self._list_host)
            item.clicked.connect(self._on_item_clicked)
            item.renamed.connect(self._on_item_renamed)
            item.context_requested.connect(self._on_item_menu)
            item.set_status(m.status, self._theme)
            self._list_lay.insertWidget(self._list_lay.count() - 1, item)
            self._items[m.id] = item

        self._list_empty.setVisible(not meetings)
        self._side_count.setText(f"{len(meetings)} 场" if meetings else "")
        if self._meeting:
            self._mark_selected(self._meeting.id)

    def _mark_selected(self, mid: str) -> None:
        for key, item in self._items.items():
            item.set_selected(key == mid)

    def _on_search(self, text: str) -> None:
        text = (text or "").strip().lower()
        for item in self._items.values():
            if not text:
                item.setVisible(True)
                continue
            item.setVisible(text in item.search_text)

    def _on_item_clicked(self, mid: str) -> None:
        if self._recording and self._meeting and mid != self._meeting.id:
            self._notify("info", "正在录音", "结束当前会议后才能切换到其他会议")
            return
        m = store.load(mid)
        if m is None:
            self._notify("error", "打开失败", "会议文件损坏或已被删除")
            self._reload_list()
            return
        self._meeting = m
        self._mark_selected(mid)
        self._render_current()

    # ══════════════════════════════════════════════════
    #  渲染
    # ══════════════════════════════════════════════════

    def _render_current(self) -> None:
        self._render_meta()
        self._render_transcript()
        self._render_summary()
        self._sync_buttons()
        self._sync_idle_status()

    def _sync_idle_status(self) -> None:
        """非工作态同步状态文案（录音/整理/生成中由各自流程接管）。"""
        if self._recording or self._summarizing or self._refining or self._finished_pending:
            return
        m = self._meeting
        if m is None:
            self._status_lbl.setText("准备开始")
            self._hint_lbl.setText("点麦克风开始录音，自动分片转写")
            return
        self._status_lbl.setText("会议已结束" if m.status == "done" else "准备开始")
        self._hint_lbl.setText("双击标题可改名 · 右上角 ⋯ 导出或删除")

    def _render_meta(self) -> None:
        m = self._meeting
        t = self._theme
        if m is None:
            self._title_edit.setText("会议纪要")
            self._meta_lbl.setText("点麦克风开始一场新会议，或从左侧选择历史会议")
            self._more_btn.setVisible(False)
            self._timer_lbl.setText("00:00")
            return
        self._title_edit.setText(m.display_title())
        self._more_btn.setVisible(True)
        if not self._recording:
            self._timer_lbl.setText(store._fmt_clock(m.duration_sec))
        bits = [time.strftime("%Y-%m-%d %H:%M", time.localtime(m.created_at))]
        if m.duration_sec:
            bits.append(f"时长 {store._fmt_clock(m.duration_sec)}")
        if m.model:
            bits.append(_short_model(m.model))
        seg_count = len([s for s in m.segments if s.text.strip()])
        if seg_count:
            chars = sum(len(s.text) for s in m.segments)
            bits.append(f"{seg_count} 段 · {chars} 字")
        if m.refined:
            bits.append("已精转")
        self._meta_lbl.setText(" · ".join(bits))
        self._meta_lbl.setStyleSheet(
            f"background: transparent; {t.font(-2)} {t.fg(t.text_muted)}"
        )

    def _find_rows(self) -> List[TranscriptRow]:
        return self._tr_host.findChildren(TranscriptRow)

    def _render_transcript(self) -> None:
        for i in reversed(range(self._tr_lay.count())):
            it = self._tr_lay.itemAt(i)
            w = it.widget() if it is not None else None
            if isinstance(w, TranscriptRow):
                self._tr_lay.takeAt(i)
                w.setParent(None)
                w.deleteLater()

        m = self._meeting
        segments = [s for s in (m.segments if m else []) if (s.text or "").strip()]
        self._tr_scroll.setVisible(bool(segments))
        self._empty_right.setVisible(not segments)
        if not segments:
            return

        for seg in segments:
            row = TranscriptRow(
                seg.t,
                seg.speaker,
                m.speaker_label(seg.speaker),
                seg.text,
                self._theme,
                self._tr_host,
            )
            row.speaker_renamed.connect(self._on_speaker_renamed)
            self._tr_lay.insertWidget(self._tr_lay.count() - 1, row)

    def _append_transcript_rows(self, segs: List[dict]) -> None:
        """录音中增量追加（不整页重绘，避免滚动位置跳动）。"""
        m = self._meeting
        if m is None or not segs:
            return
        self._tr_scroll.setVisible(True)
        self._empty_right.setVisible(False)

        bar = self._tr_scroll.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 80

        for d in segs:
            row = TranscriptRow(
                d["t"],
                d["speaker"],
                m.speaker_label(d["speaker"]),
                d["text"],
                self._theme,
                self._tr_host,
            )
            row.speaker_renamed.connect(self._on_speaker_renamed)
            self._tr_lay.insertWidget(self._tr_lay.count() - 1, row)

        if at_bottom:
            QTimer.singleShot(0, lambda: self._tr_scroll.verticalScrollBar().setValue(
                self._tr_scroll.verticalScrollBar().maximum()
            ))

    def _render_summary(self) -> None:
        m = self._meeting
        md = (m.summary_md or "").strip() if m else ""
        # 文档内边距：不给的话首个标题的 margin 会被裁在可视区外
        self._browser.document().setDocumentMargin(18)
        if not md:
            self._browser.setHtml(
                f"<div style='color:{self._theme.text_muted};"
                f"font-family:{self._theme.font_family};"
                f"font-size:{self._theme.font_size + 1}px;padding:24px'>"
                "还没有纪要。会议结束后会自动生成，也可以点上方「生成纪要」。</div>"
            )
            return
        self._browser.setHtml(md_to_html(md, self._summary_css()))

    def _switch_tab(self, index: int) -> None:
        if self._stack.currentIndex() != index:
            self._stack.setCurrentIndex(index)
        key = "transcript" if index == 0 else "summary"
        if self._seg.currentRouteKey() != key:
            self._seg.setCurrentItem(key)
        if index == 1:
            # 文档在隐藏状态下渲染，首次显示会沿用旧滚动位置，
            # 表现为「第一个标题被裁掉」——切过来时强制回顶
            self._browser.verticalScrollBar().setValue(0)
        self._sync_buttons()

    # ══════════════════════════════════════════════════
    #  录音
    # ══════════════════════════════════════════════════

    def _on_record_clicked(self) -> None:
        """圆形主按钮三态：空闲→开始录，录音中→暂停，暂停中→继续。"""
        if not self._recording:
            self._start_recording()
        elif self._paused:
            self._resume_recording()
        else:
            self._pause_recording()

    def _on_new_meeting(self) -> None:
        """新建一场空会议。当前会议本来就是空的就复用，不再堆空壳。"""
        if self._recording or self._finished_pending or self._refining:
            self._notify("info", "正在处理", "结束当前录音或整理完再新建")
            return
        cur = self._meeting
        if cur is not None and _is_empty_meeting(cur):
            self._reload_list()
            self._mark_selected(cur.id)
            self._render_current()
            self._switch_tab(0)
            self._notify("info", "当前已是新会议", "直接点右侧麦克风开始录音")
            return
        cfg = config.read_config()
        m = store.new_meeting(str(cfg.get("asr_model") or config.DEFAULT_MODEL))
        m.status = "draft"
        store.save(m)
        self._meeting = m
        self._reload_list()
        self._mark_selected(m.id)
        self._render_current()
        self._switch_tab(0)
        self._notify("success", "已新建会议", "点右侧麦克风开始录音")

    def _start_recording(self) -> None:
        """在当前会议里开始录音（已有录音则往后追加）；没有会议时先建一场。"""
        cfg = config.read_config()
        key = config.resolve_api_key(cfg)
        if not key:
            self._notify(
                "error",
                "缺少 API Key",
                "请到 设置 → 会议纪要配置 填写硅基流动 Key（或先配置「语音输入」插件）",
            )
            return
        if not recorder_mod.is_supported():
            self._notify("error", "不支持录音", "当前平台暂不支持麦克风采集")
            return

        hint = recorder_mod.mac_permission_hint()
        if hint:
            self._notify("info", "麦克风权限", hint)

        m = self._meeting
        if m is None:
            m = store.new_meeting(str(cfg.get("asr_model") or config.DEFAULT_MODEL))
            m.status = "draft"
            store.save(m)
            self._meeting = m
        if not m.model:
            m.model = str(cfg.get("asr_model") or config.DEFAULT_MODEL)

        audio_path = store.audio_path_for(m)
        append = audio_path.exists() and audio_path.stat().st_size > 44

        try:
            rec = recorder_mod.make_recorder()
            self._tmp_dir = Path(tempfile.mkdtemp(prefix="drifox_meeting_"))
            self._chunk_index = 0
            self._chunk_offset = 0.0
            rec.start_chunk(recorder_mod.chunk_path(self._tmp_dir, self._chunk_index))
        except Exception as e:  # noqa: BLE001 — 设备被占用/无权限
            logger.error(f"[meeting-notes] 启动录音失败: {e}")
            self._notify("error", "无法开始录音", str(e))
            self._cleanup_record_resources()
            return

        self._recorder = rec
        self._joiner = store.WavJoiner(audio_path, append=append)
        self._queue = asr.TranscribeQueue(
            config.SILICONFLOW_URL,
            m.model,
            key,
        )
        self._queue.on_result = lambda task: self._sig_asr_result.emit(task)
        self._queue.on_error = lambda task, err: self._sig_asr_error.emit(task, err)
        self._queue.start()

        m.status = "recording"
        store.save(m)
        self._recording = True
        self._paused = False
        self._finished_pending = False
        self._rec_started_at = time.time()
        # 计时接着已有内容走，显示的是会议总时长
        self._elapsed_base = self._joiner.duration_sec()

        self._chunk_timer.start(int(cfg.get("chunk_seconds") or config.DEFAULT_CHUNK_SEC) * 1000)
        self._tick_timer.start()
        self._idle_timer.stop()

        self._reload_list()
        self._mark_selected(m.id)
        self._render_current()
        self._switch_tab(0)
        self._status_lbl.setText("录音中")
        self._hint_lbl.setText(
            f"每 {cfg.get('chunk_seconds') or config.DEFAULT_CHUNK_SEC} 秒上送一片 · "
            f"{_short_model(m.model)}"
        )
        self._apply_record_button_style()
        self._notify(
            "success",
            "继续录音" if append else "开始录音",
            "新内容会接在已有转写之后" if append else "正在录音并实时转写",
        )

    def _rotate_chunk(self) -> None:
        """切一片：先收尾并立刻重开设备（缺口最小），再做落盘与上送。"""
        if not self._recording or self._paused or self._recorder is None:
            return

        chunk = self._recorder.stop_chunk()
        self._chunk_index += 1
        next_path = recorder_mod.chunk_path(self._tmp_dir, self._chunk_index)
        try:
            self._recorder.start_chunk(next_path)
        except Exception as e:  # noqa: BLE001 — 设备被抢走：停录并保留已录内容
            logger.error(f"[meeting-notes] 重开录音设备失败: {e}")
            self._recording = False
            self._chunk_timer.stop()
            self._notify("error", "录音中断", f"麦克风设备不可用：{e}")
            self._finish_meeting()
            return

        if chunk and self._joiner is not None and self._queue is not None:
            offset = self._joiner.duration_sec()
            dur = self._joiner.append(chunk)
            if dur > 0:
                self._chunk_offset = offset + dur
                self._queue.submit(str(chunk), offset, meeting_id=self._meeting.id if self._meeting else "")
            else:
                recorder_mod.safe_remove(chunk)

        cfg = config.read_config()
        chunk_ms = int(cfg.get("chunk_seconds") or config.DEFAULT_CHUNK_SEC) * 1000
        self._chunk_timer.start(chunk_ms)
        # 长会增量精转：攒够一段就在后台转，不等到会议结束再一次性等
        self._maybe_refine_async()

    def _tick(self) -> None:
        if not self._recording:
            return
        if self._paused:
            self._timer_lbl.setText(store._fmt_clock(self._elapsed_base))
            return
        elapsed = self._elapsed_base + (time.time() - self._rec_started_at)
        self._timer_lbl.setText(store._fmt_clock(elapsed))
        pending = self._queue.pending() if self._queue else 0
        if pending:
            self._hint_lbl.setText(f"{pending} 片待识别 · 边说边转写中")
        else:
            self._hint_lbl.setText("正在聆听…")

    def _on_pause_clicked(self) -> None:
        if not self._recording:
            return
        if self._paused:
            self._resume_recording()
        else:
            self._pause_recording()

    def _pause_recording(self) -> None:
        """暂停：当前片收尾上送，释放设备，计时冻结。"""
        if self._recorder is None:
            return
        self._paused = True
        self._chunk_timer.stop()
        self._elapsed_base += time.time() - self._rec_started_at

        chunk = self._recorder.stop_chunk()
        try:
            self._recorder.close()
        except Exception:  # noqa: BLE001 — 设备已断也不影响已录部分
            pass
        if chunk and self._joiner is not None and self._queue is not None:
            offset = self._joiner.duration_sec()
            if self._joiner.append(chunk) > 0:
                self._queue.submit(
                    str(chunk), offset, meeting_id=self._meeting.id if self._meeting else ""
                )
            else:
                recorder_mod.safe_remove(chunk)

        m = self._meeting
        if m is not None:
            m.duration_sec = self._joiner.duration_sec() if self._joiner else m.duration_sec
            store.save(m)

        self._timer_lbl.setText(store._fmt_clock(self._elapsed_base))
        self._status_lbl.setText("已暂停")
        self._hint_lbl.setText("暂停期间不录音，点继续接着录")
        self._apply_record_button_style()
        self._sync_buttons()

    def _resume_recording(self) -> None:
        """继续：重新开设备录新片，计时接着走。"""
        if self._recorder is None:
            return
        self._chunk_index += 1
        path = recorder_mod.chunk_path(self._tmp_dir, self._chunk_index)
        try:
            self._recorder.start_chunk(path)
        except Exception as e:  # noqa: BLE001 — 设备被占/权限变化
            logger.error(f"[meeting-notes] 继续录音失败: {e}")
            self._notify("error", "无法继续录音", f"麦克风设备不可用：{e}")
            self._on_stop_clicked()
            return

        self._paused = False
        self._rec_started_at = time.time()
        cfg = config.read_config()
        self._chunk_timer.start(int(cfg.get("chunk_seconds") or config.DEFAULT_CHUNK_SEC) * 1000)
        self._status_lbl.setText("录音中")
        self._hint_lbl.setText("正在聆听…")
        self._apply_record_button_style()
        self._sync_buttons()

    def _on_stop_clicked(self) -> None:
        if not self._recording:
            return
        self._recording = False
        self._paused = False
        self._chunk_timer.stop()
        self._tick_timer.stop()
        self._finish_meeting()

    def _finish_meeting(self) -> None:
        """收尾最后一片、落状态、开始等队列清空。"""
        chunk = None
        if self._recorder is not None:
            chunk = self._recorder.stop_chunk()
            try:
                self._recorder.close()
            except Exception:  # noqa: BLE001
                pass
        if chunk and self._joiner is not None and self._queue is not None:
            offset = self._joiner.duration_sec()
            if self._joiner.append(chunk) > 0:
                self._queue.submit(
                    str(chunk), offset, meeting_id=self._meeting.id if self._meeting else ""
                )
            else:
                recorder_mod.safe_remove(chunk)

        m = self._meeting
        if m is None:
            self._cleanup_record_resources()
            return
        m.status = "done"
        m.duration_sec = self._joiner.duration_sec() if self._joiner else 0.0
        store.save(m)

        self._status_lbl.setText("正在整理转写")
        self._hint_lbl.setText("识别剩余分片…")
        self._apply_record_button_style()
        self._sync_buttons()

        self._finished_pending = True
        self._idle_timer.start()

    def _on_idle_poll(self) -> None:
        if not self._finished_pending:
            self._idle_timer.stop()
            return
        if self._queue is not None and self._queue.is_busy():
            return

        self._idle_timer.stop()
        if self._queue is not None:
            self._queue.stop()
        self._queue = None

        m = self._meeting
        if m is None:
            self._cleanup_record_resources()
            return

        m.duration_sec = self._joiner.duration_sec() if self._joiner else m.duration_sec
        store.save(m)
        self._render_meta()
        self._reload_list()

        # 把剩余未精转的尾巴转完，再进收尾（自动生成纪要）
        self._drain_refine_then_finish()

    # ══════════════════════════════════════════════════
    #  识别回调（主线程）
    # ══════════════════════════════════════════════════

    def _on_asr_result(self, task: dict) -> None:
        """分片识别完成。task 带 meeting_id：录音结束后用户可能已切到别的会议，
        结果必须回写到它所属的会议，不能跟着 self._meeting 走。"""
        mid = str(task.get("meeting_id") or "")
        m = self._meeting
        if not mid or m is None or m.id != mid:
            m = store.load(mid) if mid else None
            if m is None:
                recorder_mod.safe_remove(Path(task["wav"]) if task.get("wav") else None)
                return
        is_current = self._meeting is not None and self._meeting.id == m.id

        result = task.get("result") or {}
        segs = asr.to_absolute_segments(result, float(task.get("offset") or 0.0))
        if segs:
            with self._seg_lock:
                for d in segs:
                    m.segments.append(store.Segment(t=d["t"], speaker=d["speaker"], text=d["text"]))
                m.segments.sort(key=lambda s: s.t)
            store.save(m)
            if is_current:
                self._append_transcript_rows(segs)
                self._render_meta()
            else:
                self._reload_list()
        recorder_mod.safe_remove(Path(task["wav"]) if task.get("wav") else None)

    def _on_asr_error(self, task: dict, err: str) -> None:
        recorder_mod.safe_remove(Path(task["wav"]) if task.get("wav") else None)
        logger.warning(f"[meeting-notes] 分片识别失败: {err}")
        mid = str(task.get("meeting_id") or "")
        if mid and (self._meeting is None or self._meeting.id != mid):
            return  # 不是当前会议的片，不打扰用户
        if self._recording:
            self._hint_lbl.setText(f"有一片识别失败（会继续录）：{err}")
        else:
            self._notify("warning", "部分片段识别失败", err)

    # ══════════════════════════════════════════════════
    #  增量精转（分段，后台跑）
    # ══════════════════════════════════════════════════

    def _maybe_refine_async(self, force_final: bool = False) -> bool:
        """攒够一段就送精转，返回是否启动了任务。

        录音中每攒够 10 分钟转一段；会议结束时把剩余部分（≥30 秒）一次转完。
        这样「结束会议」最多只需等最后一段，而不是整场音频。
        """
        m = self._meeting
        if m is None or self._refining or self._joiner is None:
            return False
        cfg = config.read_config()
        key = config.resolve_api_key(cfg)
        if not key:
            return False

        total = self._joiner.duration_sec()
        start = float(m.refined_until or 0.0)
        remain = total - start
        if remain < _MIN_REFINE_SEC:
            return False
        if not force_final and remain < _REFINE_SEGMENT_SEC:
            return False
        end = total if force_final else start + _REFINE_SEGMENT_SEC

        # 切片在主线程做完：录音中主 WAV 正被追加写，后台并发读同一文件
        # 会与追加重写 RIFF 头撞上。读 10 分钟音频只要几十毫秒。
        tmp_dir = Path(tempfile.mkdtemp(prefix="drifox_meeting_refine_"))
        audio = store.audio_path_for(m)
        try:
            part = store.extract_wav_range(audio, tmp_dir / "part.wav", start, end)
        except Exception as e:  # noqa: BLE001 — 切不出来就放弃这段
            logger.warning(f"[meeting-notes] 切音频段失败: {e}")
            part = None
        if part is None:
            store.cleanup_temp(list(tmp_dir.glob("*.wav")))
            try:
                tmp_dir.rmdir()
            except OSError:
                pass
            return False

        self._refining = True
        self._sync_buttons()
        model = str(cfg.get("asr_model") or config.DEFAULT_MODEL)
        snapshot = m
        if force_final:
            self._status_lbl.setText("精转最后一段")
            self._hint_lbl.setText("用完整录音重新识别，说话人更连贯")

        def work() -> None:
            ok = False
            try:
                ok = self._do_refine_segment(snapshot, part, start, end, key, model)
            except Exception as e:  # noqa: BLE001 — 精转失败不能毁掉实时转写
                logger.error(f"[meeting-notes] 分段精转失败 [{start:.0f}-{end:.0f}s]: {e}")
            finally:
                store.cleanup_temp(list(tmp_dir.glob("*.wav")))
                try:
                    tmp_dir.rmdir()
                except OSError:
                    pass
                self._sig_refine_done.emit(snapshot, ok)

        threading.Thread(target=work, daemon=True, name="meeting-notes-refine").start()
        return True

    def _do_refine_segment(
        self, m: Meeting, part: Path, start: float, end: float, key: str, model: str
    ) -> bool:
        """识别已切好的一段音频，替换该时间段内的实时结果。"""
        result = asr.transcribe_with_retry(
            config.SILICONFLOW_URL, model, key, str(part), timeout=asr.FULL_TIMEOUT_SEC
        )
        segs = asr.to_absolute_segments(result, start)
        if not segs:
            return False
        new_items = [store.Segment(t=s["t"], speaker=s["speaker"], text=s["text"]) for s in segs]
        with self._seg_lock:
            kept = [s for s in m.segments if not (start - 0.5 <= s.t < end)]
            m.segments = sorted(kept + new_items, key=lambda s: s.t)
            m.refined_until = max(float(m.refined_until or 0.0), end)
            m.duration_sec = max(m.duration_sec, end)
            store.save(m)
        logger.info(
            f"[meeting-notes] 分段精转完成 [{start:.0f}-{end:.0f}s]：{len(new_items)} 段"
        )
        return True

    def _on_refine_done(self, m: Meeting, ok: bool) -> None:
        self._refining = False
        if self._meeting and self._meeting.id == m.id:
            self._meeting = store.load(m.id) or self._meeting
            self._render_current()
        self._reload_list()
        if not ok:
            logger.info("[meeting-notes] 本段精转未成功，保留实时转写结果")
        if self._finished_pending:
            # 会议已结束：把剩余段继续转完，再进收尾
            self._drain_refine_then_finish()

    def _drain_refine_then_finish(self) -> None:
        if self._maybe_refine_async(force_final=True):
            return
        self._after_refine()

    def _after_refine(self) -> None:
        m = self._meeting
        if m is None:
            self._cleanup_record_resources()
            return
        self._finished_pending = False
        # 收尾资源：切片临时目录/队列句柄不能留到下一场
        self._cleanup_record_resources()
        self._status_lbl.setText("会议已结束" if m.status == "done" else "准备开始")
        self._hint_lbl.setText("可以生成纪要，或继续录这场会议")
        self._sync_buttons()
        self._render_meta()
        self._reload_list()

        cfg = config.read_config()
        if not cfg.get("keep_audio", True):
            store.remove_audio(m)

        if m.summary_md.strip():
            return
        if any(s.text.strip() for s in m.segments):
            self._on_generate_summary()
        else:
            self._notify("warning", "没有识别到内容", "这次会议没有可用的转写，未生成纪要")

    # ══════════════════════════════════════════════════
    #  纪要
    # ══════════════════════════════════════════════════

    def _on_generate_summary(self) -> None:
        m = self._meeting
        if m is None:
            return
        if self._summarizing:
            self._notify("info", "正在生成", "纪要生成中，请稍候")
            return
        if not any(s.text.strip() for s in m.segments):
            self._notify("warning", "没有转写内容", "先录一场会议再来生成纪要")
            return

        cfg = config.read_config()
        # 会话在主线程建：要解析窗口宿主，且失败能立刻反馈（后台线程里建会静默失败）
        try:
            session = summary_mod.create_session(str(cfg.get("summary_model") or ""))
        except Exception as e:  # noqa: BLE001
            logger.error(f"[meeting-notes] 创建纪要会话失败: {e}")
            self._status_lbl.setText("纪要生成失败")
            self._hint_lbl.setText(str(e))
            self._notify("error", "无法生成纪要", str(e))
            return

        self._summarizing = True
        self._status_lbl.setText("AI 纪要生成中")
        model_hint = str(cfg.get("summary_model") or "").strip() or "当前对话模型"
        self._hint_lbl.setText(f"正在用 {model_hint} 整理要点、决议与待办…")
        self._sync_buttons()
        snapshot = m
        custom_prompt = str(cfg.get("summary_prompt") or "")

        def work() -> None:
            try:
                text = summary_mod.generate_summary(session, snapshot, custom_prompt)
                self._sig_summary_done.emit(text)
            except Exception as e:  # noqa: BLE001 — 线程异常必须回主线程提示
                self._sig_summary_error.emit(str(e))

        threading.Thread(target=work, daemon=True, name="meeting-notes-summary").start()

    def _on_summary_done(self, text: str) -> None:
        self._summarizing = False
        m = self._meeting
        if m is not None:
            # 纪要首行的 `# 标题` 顺手当会议名，省一次手动改名
            title, body = summary_mod.split_title(text)
            m.summary_md = body or text
            m.summary_at = time.time()
            if title and _is_default_title(m.title):
                m.title = title
            store.save(m)
            if self._meeting and self._meeting.id == m.id:
                self._render_summary()
                self._render_meta()
        self._reload_list()
        self._status_lbl.setText("纪要已生成")
        self._hint_lbl.setText("可切换到「AI 纪要」查看，或导出 Markdown")
        self._sync_buttons()
        self._switch_tab(1)
        self._notify("success", "纪要已生成", "已保存到本地会议记录")

    def _on_summary_error(self, err: str) -> None:
        self._summarizing = False
        self._status_lbl.setText("纪要生成失败")
        self._hint_lbl.setText(err)
        self._sync_buttons()
        self._notify("error", "纪要生成失败", err)

    # ══════════════════════════════════════════════════
    #  其它操作
    # ══════════════════════════════════════════════════

    def _sync_buttons(self) -> None:
        """按钮可见性/可用性统一在这里算。

        分层：主圆形按钮三态（录音/暂停/继续）+ 录音中出现的「结束」；
        纪要动作跟着纪要页走；重命名/导出/删除在 ⋯ 菜单里。
        """
        m = self._meeting
        working = self._finished_pending or self._refining or self._summarizing
        busy = self._recording or working
        has_meeting = m is not None

        self._record_btn.setEnabled(not working)
        self._stop_btn.setVisible(self._recording)
        self._stop_btn.setEnabled(self._recording and not working)
        self._more_btn.setVisible(has_meeting)
        self._more_btn.setEnabled(has_meeting and not busy)

        # 纪要按钮只在「AI 纪要」页出现，和它作用的视图待在一起
        on_summary_tab = self._stack.currentIndex() == 1
        self._summary_btn.setVisible(has_meeting and on_summary_tab and not self._recording)
        if self._summarizing:
            self._summary_btn.setText("生成中…")
        elif working:
            self._summary_btn.setText("整理转写中…")
        else:
            self._summary_btn.setText("重新生成" if (m and m.summary_md) else "生成纪要")
        has_text = bool(m and any(s.text.strip() for s in m.segments))
        self._summary_btn.setEnabled(has_meeting and not busy and has_text)

    def _on_more_menu(self) -> None:
        """更多操作：重命名/导出/删除收进菜单，不占底部空间。"""
        m = self._meeting
        if m is None:
            return
        from qfluentwidgets import Action, RoundMenu

        menu = RoundMenu(parent=self)
        menu.addAction(Action(FluentIcon.EDIT, "重命名会议", triggered=self._on_rename))
        menu.addAction(
            Action(
                FluentIcon.SAVE, "导出 Markdown", triggered=lambda: self._export_meeting(m.id)
            )
        )
        audio_action = Action(
            FluentIcon.FOLDER, "打开录音位置", triggered=lambda: self._open_audio_of(m.id)
        )
        audio_action.setEnabled(store.audio_path_for(m).exists())
        menu.addAction(audio_action)
        menu.addSeparator()
        menu.addAction(
            Action(FluentIcon.DELETE, "删除会议", triggered=lambda: self._delete_meeting(m.id))
        )
        menu.exec_(self._more_btn.mapToGlobal(self._more_btn.rect().bottomLeft()))

    def _on_rename(self) -> None:
        """菜单里的重命名：直接让标题进入就地编辑态（不弹框）。"""
        if self._meeting is not None:
            self._title_edit.start_edit()

    def _on_title_changed(self, new_title: str) -> None:
        m = self._meeting
        if m is None or not new_title.strip() or new_title == m.title:
            return
        m.title = new_title.strip()
        store.save(m)
        self._reload_list()

    def _on_item_renamed(self, meeting_id: str, new_title: str) -> None:
        """列表项双击改名。"""
        m = store.load(meeting_id)
        if m is None or not new_title.strip():
            return
        m.title = new_title.strip()
        store.save(m)
        if self._meeting is not None and self._meeting.id == meeting_id:
            self._meeting.title = m.title
            self._render_meta()

    def _on_speaker_renamed(self, speaker: str, new_name: str) -> None:
        """说话人就地改名（空名恢复默认）。"""
        m = self._meeting
        if m is None or not speaker:
            return
        if new_name.strip():
            m.speaker_names[speaker] = new_name.strip()
        else:
            m.speaker_names.pop(speaker, None)
        store.save(m)
        self._render_transcript()

    def _on_item_menu(self, meeting_id: str, global_pos) -> None:
        """左栏列表项右键菜单：导出 / 定位录音 / 删除，不用先选中再开 ⋯。"""
        from qfluentwidgets import Action, RoundMenu

        m = store.load(meeting_id)
        if m is None:
            return
        menu = RoundMenu(parent=self)
        menu.addAction(
            Action(FluentIcon.SAVE, "导出 Markdown", triggered=lambda: self._export_meeting(m.id))
        )
        audio_action = Action(
            FluentIcon.FOLDER, "打开录音位置", triggered=lambda: self._open_audio_of(m.id)
        )
        audio_action.setEnabled(store.audio_path_for(m).exists())
        menu.addAction(audio_action)
        menu.addSeparator()
        menu.addAction(Action(FluentIcon.DELETE, "删除会议", triggered=lambda: self._delete_meeting(m.id)))
        menu.exec_(global_pos)

    def _export_meeting(self, meeting_id: str) -> None:
        m = store.load(meeting_id)
        if m is None:
            return
        default_name = f"{store.safe_filename(m.display_title())}.md"
        path = self._save_file("导出会议纪要", default_name, "Markdown (*.md)")
        if not path:
            return
        try:
            Path(path).write_text(store.export_markdown(m), encoding="utf-8")
        except OSError as e:
            self._notify("error", "导出失败", str(e))
            return
        self._notify("success", "已导出", path)

    def _open_audio_of(self, meeting_id: str) -> None:
        m = store.load(meeting_id)
        if m is None:
            return
        self._open_audio_path(store.audio_path_for(m))

    def _open_audio_path(self, path: Path) -> None:
        if not path.exists():
            self._notify(
                "warning", "没有录音文件", "可能关闭了「保留录音文件」，或这次录音未成功写入"
            )
            return
        try:
            import subprocess
            import sys

            if sys.platform == "win32":
                subprocess.Popen(["explorer", "/select," + str(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(path)])
            else:
                from PyQt5.QtCore import QUrl
                from PyQt5.QtGui import QDesktopServices

                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
        except Exception as e:  # noqa: BLE001 — 打不开目录不影响其他功能
            logger.warning(f"[meeting-notes] 打开录音位置失败: {e}")
            self._notify("error", "打开失败", str(e))

    def _delete_meeting(self, meeting_id: str) -> None:
        if self._recording and self._meeting and self._meeting.id == meeting_id:
            self._notify("info", "正在录音", "先结束这场录音再删除")
            return
        m = store.load(meeting_id)
        if m is None:
            return
        if not self._confirm(
            "删除会议",
            f"确定删除「{m.display_title()}」？录音与纪要会一并删除，不可恢复。",
            "删除",
        ):
            return
        store.delete(m.id)
        if self._meeting is not None and self._meeting.id == meeting_id:
            self._meeting = None
            self._render_current()
        self._reload_list()
        self._notify("success", "已删除", "会议记录已移除")

    # ══════════════════════════════════════════════════
    #  工具
    # ══════════════════════════════════════════════════

    def _cleanup_record_resources(self) -> None:
        if self._queue is not None:
            self._queue.stop()
            self._queue = None
        if self._tmp_dir is not None:
            try:
                for f in Path(self._tmp_dir).glob("*.wav"):
                    recorder_mod.safe_remove(f)
                Path(self._tmp_dir).rmdir()
            except OSError:
                pass
            self._tmp_dir = None
        self._joiner = None

    def _cap(self, cap_id: str):
        """取能力：ctx 池优先（宿主裁剪后的正规出口），caps_for 兜底。"""
        pool = (self._ctx() or {}).get("capabilities")
        if pool is not None:
            try:
                if cap_id in pool:
                    return pool[cap_id]
            except Exception as e:  # noqa: BLE001 — 池实现差异不阻塞
                logger.debug(f"[meeting-notes] ctx 能力池取 {cap_id} 失败: {e}")
        try:
            from app.plugins.sdk import caps_for

            return caps_for(cap_id, plugin=PLUGIN_NAME, surface="ui")
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[meeting-notes] caps_for({cap_id}) 不可用: {e}")
            return None

    def _notify(self, kind: str, title: str, msg: str) -> None:
        fn = self._cap("ui.notify")
        if callable(fn):
            try:
                fn(title, msg, kind=kind, duration=3200)
                return
            except Exception as e:  # noqa: BLE001 — 提示失败不回沮到主流程
                logger.debug(f"[meeting-notes] ui.notify 调用失败: {e}")
        logger.info(f"[meeting-notes] {title}: {msg}")

    # ── 弹窗 ──

    def _confirm(self, title: str, content: str, confirm_text: str = "确定") -> bool:
        """系统规范确认框（MaskDialogBase 自绘，跟随主题）。

        不走宿主 ui.dialog：它在卡片拿不到窗口宿主时会静默返回 None，
        退化成 Windows 原生 QMessageBox（英文 Yes/No），与宿主风格脱节。
        """
        try:
            from .dialogs import confirm_dialog

            parent = self.window() or self
            return bool(confirm_dialog(parent, self._theme, title, content, confirm_text))
        except Exception as e:  # noqa: BLE001 — 弹窗失败不应让删除等操作崩掉
            logger.error(f"[meeting-notes] 自绘确认框失败，回退原生: {e}")
        ret = QMessageBox.question(
            self, title, content, QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        return ret == QMessageBox.Yes

    def _save_file(self, title: str, start_dir: str, file_filter: str) -> str:
        api = self._cap("ui.dialog")
        fn = api.get("save_file") if isinstance(api, dict) else None
        if callable(fn):
            try:
                return str(fn(title, start_dir, file_filter) or "")
            except Exception as e:  # noqa: BLE001
                logger.debug(f"[meeting-notes] 宿主保存框失败，回退原生: {e}")
        path, _ = QFileDialog.getSaveFileName(self, title, start_dir, file_filter)
        return str(path or "")

    def _on_close(self) -> None:
        if self._recording:
            self._notify("warning", "会议仍在录音", "请先结束当前会议再关闭")
            return
        self.setVisible(False)
        self.closed.emit()

    def deleteLater(self):  # noqa: N802 — Qt 命名
        try:
            if self._recorder is not None:
                self._recorder.close()
        except Exception:  # noqa: BLE001
            pass
        self._cleanup_record_resources()
        super().deleteLater()


def _short_model(model: str) -> str:
    return model.rsplit("/", 1)[-1]


def _is_empty_meeting(m: Meeting) -> bool:
    """空会议：没转写、没纪要、没时长。只有「新建会议」会造出这种壳。"""
    return (
        not any((s.text or "").strip() for s in m.segments)
        and not (m.summary_md or "").strip()
        and float(m.duration_sec or 0.0) < 1.0
    )


def _is_default_title(title: str) -> bool:
    """判断标题是不是自动生成的默认名（如「11月11日 01:15 会议」）。

    只有默认名才被 AI 标题覆盖；用户手动改过的名字保留。
    """
    import re

    return bool(re.match(r"^\d{1,2}月\d{1,2}日 \d{1,2}:\d{2} 会议$", (title or "").strip()))
