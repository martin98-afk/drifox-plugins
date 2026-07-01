# -*- coding: utf-8 -*-
"""
GitDashboardCard 浮动卡片 — Git 仓库可视化仪表盘

布局：左日历（竖向：x=周几，y=月份向下） + 右提交横向排列
"""

from __future__ import annotations

import subprocess
import traceback
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple

from PyQt5.QtCore import QObject, QPointF, QRectF, QSize, QThread, Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import FluentIcon, IconWidget, ScrollArea, StrongBodyLabel, TransparentToolButton, isDarkTheme
from loguru import logger

PLUGIN_NAME = "git-dashboard"
GIT_TIMEOUT = 5
_DEFAULT_FONT = "Segoe UI"
_DEFAULT_FONT_SIZE = 14
COMMIT_COUNT = 50

# ── 日历常量 ──
CAL_MARGIN_LEFT = 40  # 留给月份标签
CAL_TOP = 60  # 标题+星期标签占高
CELL_SIZE = 20
CELL_GAP = 3
STEP = CELL_SIZE + CELL_GAP
COLS = 7  # 一周7天
CAL_PAD_BOTTOM = 30  # 底部留白（图例）
CAL_WIDTH = 280  # 日历面板固定宽


# ============================================================
# 工具函数
# ============================================================


def _resolve_colors(context: dict | None = None) -> dict:
    if context and context.get("colors"):
        return _from_theme_dict(context["colors"], context.get("is_dark", isDarkTheme()))
    return _fallback_colors()


def _c_str(raw: dict, key: str, fallback: str) -> QColor:
    val = raw.get(key, fallback)
    return QColor(val) if isinstance(val, str) else QColor(*val) if isinstance(val, (list, tuple)) else QColor(fallback)


def _from_theme_dict(raw: dict, is_dark: bool) -> dict:
    txt = _c_str(raw, "text_primary", "#ffffff")
    txt_sec = _c_str(raw, "text_secondary", "rgba(255,255,255,0.5)")
    card_bg = _c_str(raw, "card_bg", "rgba(33,33,38,250)")
    card_bg.setAlpha(200)
    accent = _c_str(raw, "accent", "#62a0ea" if is_dark else "#2878dc")
    if is_dark:
        return {
            "card_bg": card_bg,
            "text": txt,
            "text_secondary": txt_sec,
            "separator": QColor(255, 255, 255, 20),
            "accent": accent,
            "success": QColor(80, 227, 194, 220),
            "cal_0": QColor(40, 40, 40),
            "cal_1": QColor(14, 68, 41),
            "cal_2": QColor(0, 109, 50),
            "cal_3": QColor(38, 166, 65),
            "cal_4": QColor(57, 211, 83),
            "cal_label": QColor(255, 255, 255, 110),
            "cal_border": QColor(255, 255, 255, 8),
            "cal_tooltip_border": accent,
            "scrollbar_handle": QColor(255, 255, 255, 30),
            "scrollbar_handle_hover": QColor(255, 255, 255, 50),
        }
    return {
        "card_bg": card_bg,
        "text": txt,
        "text_secondary": txt_sec,
        "separator": QColor(0, 0, 0, 10),
        "accent": accent,
        "success": QColor(16, 185, 129, 220),
        "cal_0": QColor(235, 237, 240),
        "cal_1": QColor(155, 233, 168),
        "cal_2": QColor(0, 184, 77),
        "cal_3": QColor(0, 140, 60),
        "cal_4": QColor(0, 100, 40),
        "cal_label": QColor(0, 0, 0, 110),
        "cal_border": QColor(0, 0, 0, 6),
        "cal_tooltip_border": accent,
        "scrollbar_handle": QColor(0, 0, 0, 20),
        "scrollbar_handle_hover": QColor(0, 0, 0, 40),
    }


def _fallback_colors() -> dict:
    is_dark = isDarkTheme()
    if is_dark:
        return {
            "card_bg": QColor(33, 33, 38, 200),
            "text": QColor(255, 255, 255),
            "text_secondary": QColor(255, 255, 255, 128),
            "separator": QColor(255, 255, 255, 20),
            "accent": QColor(98, 160, 234),
            "success": QColor(80, 227, 194, 220),
            "cal_0": QColor(40, 40, 40),
            "cal_1": QColor(14, 68, 41),
            "cal_2": QColor(0, 109, 50),
            "cal_3": QColor(38, 166, 65),
            "cal_4": QColor(57, 211, 83),
            "cal_label": QColor(255, 255, 255, 110),
            "cal_border": QColor(255, 255, 255, 8),
            "cal_tooltip_border": QColor(98, 160, 234),
            "scrollbar_handle": QColor(255, 255, 255, 30),
            "scrollbar_handle_hover": QColor(255, 255, 255, 50),
        }
    return {
        "card_bg": QColor(255, 255, 255, 200),
        "text": QColor(0, 0, 0),
        "text_secondary": QColor(0, 0, 0, 128),
        "separator": QColor(0, 0, 0, 10),
        "accent": QColor(40, 120, 220),
        "success": QColor(16, 185, 129, 220),
        "cal_0": QColor(235, 237, 240),
        "cal_1": QColor(155, 233, 168),
        "cal_2": QColor(0, 184, 77),
        "cal_3": QColor(0, 140, 60),
        "cal_4": QColor(0, 100, 40),
        "cal_label": QColor(0, 0, 0, 110),
        "cal_border": QColor(0, 0, 0, 6),
        "cal_tooltip_border": QColor(40, 120, 220),
        "scrollbar_handle": QColor(0, 0, 0, 20),
        "scrollbar_handle_hover": QColor(0, 0, 0, 40),
    }


def _format_number(n: int) -> str:
    if n >= 1000000:
        return f"{n / 1000000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


# ============================================================
# Git 数据采集
# ============================================================


def _run_git(cwd: str, *args: str) -> Tuple[str, str, int]:
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT,
        )
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", -1
    except FileNotFoundError:
        return "", "git not found", -1
    except Exception as e:
        return "", str(e), -1


def _is_git_repo(cwd: str) -> bool:
    if not cwd:
        return False
    _, _, code = _run_git(cwd, "rev-parse", "--is-inside-work-tree")
    return code == 0


def _collect_header(cwd: str) -> dict:
    info: dict = {"repo_name": "", "branch": "", "ahead": 0, "behind": 0}
    stdout, _, _ = _run_git(cwd, "rev-parse", "--show-toplevel")
    if stdout:
        import os as _os

        info["repo_name"] = _os.path.basename(stdout)
    stdout, _, code = _run_git(cwd, "branch", "--show-current")
    if code == 0 and stdout:
        info["branch"] = stdout
    else:
        stdout, _, _ = _run_git(cwd, "rev-parse", "--short", "HEAD")
        if stdout:
            info["branch"] = f"(detached @ {stdout})"
    stdout, _, _ = _run_git(cwd, "rev-list", "--left-right", "--count", "HEAD...@{u}")
    if stdout:
        parts = stdout.split()
        if len(parts) == 2:
            try:
                info["ahead"] = int(parts[0])
                info["behind"] = int(parts[1])
            except ValueError:
                pass
    return info


def _collect_commit_calendar(cwd: str) -> Dict[str, int]:
    stdout, _, code = _run_git(cwd, "log", "--after=6 months ago", "--format=%ai", "--all", "--no-merges")
    if code != 0 or not stdout:
        return {}
    daily: Dict[str, int] = defaultdict(int)
    for line in stdout.splitlines():
        date_str = line[:10]
        if date_str:
            daily[date_str] += 1
    return dict(daily)


def _collect_recent_commits(cwd: str, n: int = COMMIT_COUNT) -> List[str]:
    stdout, _, code = _run_git(cwd, "log", f"-n{n}", "--oneline", "--decorate", "--no-merges")
    if code == 0 and stdout:
        return stdout.splitlines()
    return []


class _GitDataWorker(QObject):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, cwd: str):
        super().__init__()
        self._cwd = cwd

    def run(self):
        try:
            data = {
                "header": _collect_header(self._cwd),
                "calendar": _collect_commit_calendar(self._cwd),
                "commits": _collect_recent_commits(self._cwd),
            }
            self.finished.emit(data)
        except Exception as e:
            self.error.emit(f"{e}\n{traceback.format_exc()}")


# ============================================================
# 提交日历热力图（竖向：x=周几，y=月份向下）
# ============================================================


class _CalendarWidget(QWidget):
    """竖向提交日历：x轴=周日~周六，y轴=按周向下排列，左侧标月份"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._daily: Dict[str, int] = {}
        self._total_commits = 0
        self._colors = _resolve_colors()
        self._font_family = _DEFAULT_FONT
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setStyleSheet("background: transparent;")
        self.setFixedWidth(CAL_WIDTH)

        self._hover_date: str | None = None
        self._hover_count: int = 0
        self._cell_rects: Dict[str, QRectF] = {}
        self._cell_map: Dict[str, Tuple[int, int]] = {}  # date_key -> (col_day, row_week)
        self._month_rows: Dict[str, int] = {}  # "YYYY-MM" -> first_row_index
        self._num_rows = 0
        self._cell_size = 20
        self._step = 23

    def set_data(self, daily: Dict[str, int]):
        self._daily = daily
        self._total_commits = sum(daily.values())
        self._colors = _resolve_colors()
        self._build_cell_map()
        self._recalc_geometry()
        self.update()

    def set_font_info(self, family: str, size: int):
        self._font_family = family

    # ── 几何 ──

    def _build_cell_map(self):
        """建立竖向映射：col=周几(0=日…6=六)，row=第几周(0开始)，左侧标月份"""
        today = datetime.now()
        start = today - timedelta(days=182)
        start -= timedelta(days=start.weekday())  # 对齐周一，保证完整周

        # 收集所有日期
        all_dates: List[datetime] = []
        d = start
        while d <= today:
            all_dates.append(d)
            d += timedelta(days=1)

        # 按周分组：同一周的行号相同
        week_map: Dict[str, int] = {}  # week_key -> row
        cell_map: Dict[str, Tuple[int, int]] = {}
        month_rows: Dict[str, int] = {}  # "YYYY-MM" -> first row

        prev_month = -1
        for d in all_dates:
            # 周一开始的一周作为key
            mon = d - timedelta(days=d.weekday())
            week_key = mon.strftime("%Y-%m-%d")
            if week_key not in week_map:
                week_map[week_key] = len(week_map)
            row = week_map[week_key]
            col = (d.weekday() + 1) % 7  # 0=周日…6=周六
            date_key = d.strftime("%Y-%m-%d")
            cell_map[date_key] = (col, row)

            # 记录月份起始行
            m = d.month
            if m != prev_month:
                ym = d.strftime("%Y-%m")
                if ym not in month_rows:
                    month_rows[ym] = row
                prev_month = m

        # 反转行号：最近一周在最上面（row=0），最旧在底部
        total_rows = len(week_map)
        reversed_cell = {}
        for k, (col, row) in cell_map.items():
            reversed_cell[k] = (col, total_rows - 1 - row)
        self._cell_map = reversed_cell

        # 月份行号也反转
        reversed_months = {}
        for ym, row in month_rows.items():
            reversed_months[ym] = total_rows - 1 - row
        self._month_rows = dict(sorted(reversed_months.items(), key=lambda x: x[1]))
        self._num_rows = total_rows

    def _recalc_geometry(self):
        """根据行数计算固定高度"""
        # 尽量用大格子让日历饱满
        avail_x = CAL_WIDTH - CAL_MARGIN_LEFT - 8
        cs = max(14, min(28, (avail_x - COLS * CELL_GAP) // COLS))
        self._cell_size = cs
        self._step = cs + CELL_GAP
        h = CAL_TOP + self._num_rows * self._step + CAL_PAD_BOTTOM
        self.setFixedHeight(h)

    def sizeHint(self) -> QSize:
        return QSize(CAL_WIDTH, 500)

    # ── 悬浮 ──

    def mouseMoveEvent(self, event):
        pos = event.pos()
        self._hover_date = None
        for date_key, rect in self._cell_rects.items():
            if rect.contains(pos):
                self._hover_date = date_key
                self._hover_count = self._daily.get(date_key, 0)
                weekday_cn = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]
                try:
                    dt = datetime.strptime(date_key, "%Y-%m-%d")
                    date_str = f"{dt.year}年{dt.month}月{dt.day}日（{weekday_cn[dt.weekday()]}）"
                except ValueError:
                    date_str = date_key
                QToolTip.showText(event.globalPos(), f"{date_str}\n{self._hover_count} 次提交", self)
                break
        if not self._hover_date:
            QToolTip.hideText()
        self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover_date = None
        QToolTip.hideText()
        self.update()
        super().leaveEvent(event)

    # ── 绘制 ──

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        colors = self._colors
        w = self.width()
        cs = self._cell_size
        step = self._step

        ox = CAL_MARGIN_LEFT  # 网格起始X
        oy = CAL_TOP  # 网格起始Y
        cw = COLS * step  # 网格总宽

        # ── 标题 ──
        painter.setFont(QFont(self._font_family, 11, QFont.Bold))
        painter.setPen(colors["text"])
        painter.drawText(
            QRectF(6, 4, w - 12, 20),
            Qt.AlignLeft | Qt.AlignVCenter,
            f"☀ 提交日历 · {_format_number(self._total_commits)} 次",
        )

        # 日期范围
        painter.setFont(QFont(self._font_family, 8))
        painter.setPen(colors["text_secondary"])
        try:
            today = datetime.now()
            start = today - timedelta(days=182)
            painter.drawText(
                QRectF(6, 22, w - 12, 16),
                Qt.AlignLeft | Qt.AlignVCenter,
                f"{start.month}月{start.day}日 → {today.month}月{today.day}日",
            )
        except Exception:
            pass

        # ── 星期标签（顶部） ──
        day_labels = ["日", "一", "二", "三", "四", "五", "六"]
        painter.setFont(QFont(self._font_family, 9))
        painter.setPen(colors["cal_label"])
        for i, label in enumerate(day_labels):
            lx = ox + i * step + (cs - painter.fontMetrics().width(label)) / 2
            painter.drawText(QPointF(lx, oy - 8), label)

        if not self._daily or not self._cell_map:
            painter.setFont(QFont(self._font_family, 9))
            painter.setPen(colors["text_secondary"])
            painter.drawText(QRectF(ox, oy, w - ox - 8, self.height() - oy - 8), Qt.AlignCenter, "暂无提交数据")
            painter.end()
            return

        # ── 颜色等级 ──
        values = sorted(self._daily.values())
        max_val = max(values)
        if max_val <= 6:
            thresholds = [0, 1, 3, 6]
        else:
            thresholds = [max(1, int(max_val * 0.1)), max(2, int(max_val * 0.3)), max(3, int(max_val * 0.6))]
        while len(thresholds) < 3:
            thresholds.append(max_val)
        thresholds = thresholds[:3]

        def _level(c: int) -> int:
            if c == 0:
                return 0
            if c <= thresholds[0]:
                return 1
            if c <= thresholds[1]:
                return 2
            if c <= thresholds[2]:
                return 3
            return 4

        cal_colors = [colors["cal_0"], colors["cal_1"], colors["cal_2"], colors["cal_3"], colors["cal_4"]]

        # ── 月份标签（左侧Y轴） ──
        month_cn = ["", "1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"]
        painter.setFont(QFont(self._font_family, 9))
        painter.setPen(colors["cal_label"])
        for ym, first_row in self._month_rows.items():
            try:
                m = int(ym.split("-")[1])
                label_y = oy + first_row * step + cs / 2 + 4
                painter.drawText(
                    QRectF(2, label_y - 10, CAL_MARGIN_LEFT - 4, 20), Qt.AlignRight | Qt.AlignVCenter, month_cn[m]
                )
            except ValueError, IndexError:
                pass

        # ── 画格子 ──
        self._cell_rects.clear()
        for date_key, count in self._daily.items():
            if date_key not in self._cell_map:
                continue
            col, row = self._cell_map[date_key]
            x = ox + col * step
            y = oy + row * step
            lvl = _level(count)
            rect = QRectF(x, y, cs, cs)
            self._cell_rects[date_key] = rect

            path = QPainterPath()
            path.addRoundedRect(rect, 2.5, 2.5)
            if date_key == self._hover_date:
                hl = QColor(cal_colors[lvl])
                hl = hl.lighter(135) if isDarkTheme() else hl.darker(85)
                painter.fillPath(path, QBrush(hl))
                painter.setPen(QPen(colors["cal_tooltip_border"], 1.5))
            else:
                painter.fillPath(path, QBrush(cal_colors[lvl]))
                painter.setPen(QPen(colors["cal_border"], 0.5))
            painter.drawPath(path)

        # ── 横线分隔月份（可选，增强可读性） ──
        painter.setPen(QPen(colors["separator"], 1))
        for ym, first_row in self._month_rows.items():
            if first_row > 0:
                y_line = oy + first_row * step - 1
                painter.drawLine(QPointF(ox, y_line), QPointF(ox + cw, y_line))

        # ── 图例（底部居中） ──
        legend_y = self.height() - 18
        legend_x = (w - (5 * (cs + 2) + 34)) / 2
        painter.setFont(QFont(self._font_family, 8))
        painter.setPen(colors["cal_label"])
        painter.drawText(QPointF(legend_x, legend_y + cs - 4), "少")
        for i, color in enumerate(cal_colors):
            lx = legend_x + 18 + i * (cs + 2)
            lr = QRectF(lx, legend_y, cs, cs)
            p2 = QPainterPath()
            p2.addRoundedRect(lr, 2.5, 2.5)
            painter.fillPath(p2, QBrush(color))
            painter.setPen(QPen(colors["cal_border"], 0.5))
            painter.drawPath(p2)
        painter.drawText(QPointF(legend_x + 18 + 5 * (cs + 2) + 4, legend_y + cs - 4), "多")

        painter.end()


# ============================================================
# 提交列表组件（右侧，支持自动换行）
# ============================================================


class _CommitListWidget(QWidget):
    """提交列表，自动换行"""

    COMMIT_LINE_HEIGHT = 30

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lines: List[str] = []
        self._colors = _resolve_colors()
        self._font_family = _DEFAULT_FONT
        self._font_size = _DEFAULT_FONT_SIZE
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet("background: transparent;")

    def set_lines(self, lines: List[str]):
        self._lines = lines
        self._colors = _resolve_colors()
        self._update_size()
        self.update()

    def set_font_info(self, family: str, size: int):
        self._font_family = family
        self._font_size = size

    def _update_size(self):
        avail_w = max(100, self.width() - 16)
        total_h = 42
        for line in self._lines:
            lines_needed = self._calc_lines(line, avail_w)
            total_h += lines_needed * self.COMMIT_LINE_HEIGHT
        total_h = max(total_h, 60)
        self.setMinimumHeight(total_h)
        self.setMaximumHeight(min(total_h, 3000))

    def _calc_lines(self, line: str, avail_w: int) -> int:
        if avail_w <= 0 or not line:
            return 1
        hash_end = line.find(" ")
        if hash_end <= 0:
            return 1
        msg = line[hash_end:].strip()
        if not msg:
            return 1
        fm = QFontMetrics(QFont(self._font_family, 11))
        msg_w = fm.width(msg)
        line_w = avail_w - 48
        if line_w <= 0 or msg_w <= line_w:
            return 1
        return (msg_w // line_w) + 1

    def sizeHint(self) -> QSize:
        return QSize(300, 200)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_size()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        colors = self._colors
        w = self.width()

        # ── 标题 ──
        painter.setFont(QFont(self._font_family, 13, QFont.Bold))
        painter.setPen(colors["text"])
        painter.drawText(QRectF(4, 4, w - 8, 26), Qt.AlignLeft | Qt.AlignVCenter, "📜  最近提交")

        # ── 分隔线 ──
        painter.setPen(QPen(colors["separator"], 1))
        painter.drawLine(QPointF(8, 32), QPointF(w - 8, 32))

        if not self._lines:
            painter.setFont(QFont(self._font_family, 11))
            painter.setPen(colors["text_secondary"])
            painter.drawText(QRectF(12, 40, w - 24, self.height() - 48), Qt.AlignLeft | Qt.AlignTop, "(暂无数据)")
            painter.end()
            return

        y = 40
        list_font = QFont(self._font_family, 11)
        hash_font = QFont("Consolas", 10)

        for line in self._lines:
            if y > self.height() - 4:
                break
            if not line:
                y += self.COMMIT_LINE_HEIGHT
                continue

            hash_end = line.find(" ")
            if hash_end > 0:
                hash_part = line[:hash_end]
                msg_part = line[hash_end:].strip()

                painter.setFont(list_font)
                painter.setPen(colors["success"])
                painter.drawText(QPointF(12, y), "●")

                painter.setFont(hash_font)
                painter.setPen(colors["accent"])
                painter.drawText(QPointF(28, y), hash_part)
                hash_w = 28 + QFontMetrics(hash_font).width(hash_part) + 8

                painter.setFont(list_font)
                painter.setPen(colors["text"])
                msg_rect = QRectF(hash_w, y - 8, w - hash_w - 12, 500)
                painter.drawText(msg_rect, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, msg_part)

                br = painter.boundingRect(msg_rect, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, msg_part)
                used = max(1, int(br.height() / self.COMMIT_LINE_HEIGHT + 0.5))
                y += used * self.COMMIT_LINE_HEIGHT
            else:
                painter.setFont(list_font)
                painter.setPen(colors["text_secondary"])
                painter.drawText(QPointF(12, y), line)
                y += self.COMMIT_LINE_HEIGHT

        painter.end()


# ============================================================
# GitDashboardCard 主卡片
# ============================================================


class GitDashboardCard(QWidget):
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._context_provider: Optional[Callable[[], Dict[str, str]]] = None
        self._context: Dict[str, str] = {}
        self._data: Optional[dict] = None
        self._loading = False
        self._worker: Optional[_GitDataWorker] = None
        self._thread: Optional[QThread] = None
        self._last_project_root: str = ""
        self._font_family: str = _DEFAULT_FONT
        self._font_size: int = _DEFAULT_FONT_SIZE
        self._colors: dict = {}
        self._setup_ui()

    def _setup_ui(self):
        self.setObjectName("git-dashboard-card")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        self.setMinimumHeight(650)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._content_widget = QWidget(self)
        self._content_widget.setObjectName("cardContent")
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(20, 16, 20, 16)
        self._content_layout.setSpacing(0)

        self._build_header()
        self._content_layout.addWidget(self._header_widget)

        self._separator = QFrame(self)
        self._separator.setFrameShape(QFrame.HLine)
        self._separator.setFrameShadow(QFrame.Sunken)
        self._separator.setMaximumHeight(1)
        self._content_layout.addWidget(self._separator)

        self._build_content_area()
        self._content_layout.addWidget(self._body_widget, 1)

        layout.addWidget(self._content_widget)
        self._refresh_styles()
        self._status_label.setText("等待上下文...")

    def _build_header(self):
        self._header_widget = QWidget()
        self._header_widget.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(self._header_widget)
        hl.setContentsMargins(0, 0, 0, 12)
        hl.setSpacing(8)
        self._repo_icon = IconWidget(FluentIcon.GITHUB, self)
        self._repo_icon.setFixedSize(22, 22)
        self._repo_icon.setStyleSheet("background: transparent;")
        hl.addWidget(self._repo_icon)
        self._repo_label = StrongBodyLabel("", self)
        self._repo_label.setStyleSheet("background: transparent; font-weight: 600;")
        hl.addWidget(self._repo_label)
        hl.addSpacing(12)
        self._branch_icon = IconWidget(FluentIcon.CODE, self)
        self._branch_icon.setFixedSize(15, 15)
        self._branch_icon.setStyleSheet("background: transparent;")
        hl.addWidget(self._branch_icon)
        self._branch_label = QLabel("", self)
        self._branch_label.setStyleSheet("background: transparent;")
        hl.addWidget(self._branch_label)
        hl.addStretch(1)
        self._status_label = QLabel("", self)
        self._status_label.setStyleSheet("background: transparent;")
        hl.addWidget(self._status_label)
        self._refresh_btn = TransparentToolButton(FluentIcon.SYNC, self)
        self._refresh_btn.setFixedSize(28, 28)
        self._refresh_btn.setToolTip("刷新")
        self._refresh_btn.clicked.connect(self._refresh_data)
        hl.addWidget(self._refresh_btn)
        self._close_btn = TransparentToolButton(FluentIcon.CLOSE, self)
        self._close_btn.setFixedSize(28, 28)
        self._close_btn.setToolTip("关闭")
        self._close_btn.clicked.connect(self.closed.emit)
        hl.addWidget(self._close_btn)

    def _build_content_area(self):
        """横向：左日历（可滚动） + 右提交（可滚动）"""
        self._body_widget = QWidget()
        self._body_widget.setStyleSheet("background: transparent;")
        bl = QHBoxLayout(self._body_widget)
        bl.setContentsMargins(0, 10, 0, 0)
        bl.setSpacing(16)

        # 左日历（独立滚动）
        self._calendar_scroll = ScrollArea(self._body_widget)
        self._calendar_scroll.setWidgetResizable(False)
        self._calendar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._calendar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._calendar_scroll.setFrameShape(QFrame.NoFrame)
        self._calendar = _CalendarWidget()
        self._calendar_scroll.setWidget(self._calendar)
        bl.addWidget(self._calendar_scroll)

        # 右提交（独立滚动）
        self._commits_scroll = ScrollArea(self._body_widget)
        self._commits_scroll.setWidgetResizable(True)
        self._commits_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._commits_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._commits_scroll.setFrameShape(QFrame.NoFrame)
        self._commits_widget = _CommitListWidget()
        self._commits_scroll.setWidget(self._commits_widget)
        bl.addWidget(self._commits_scroll, 1)

    def _refresh_styles(self):
        self._colors = _resolve_colors(self._context)
        ctx_font = self._context.get("font_family", _DEFAULT_FONT)
        ctx_font_size = self._context.get("font_size", _DEFAULT_FONT_SIZE)
        self._font_family = ctx_font

        self._calendar.set_font_info(ctx_font, ctx_font_size)
        self._commits_widget.set_font_info(ctx_font, ctx_font_size)

        colors = self._colors
        bg = colors["card_bg"]
        bg_rgba = f"rgba({bg.red()}, {bg.green()}, {bg.blue()}, {bg.alpha()})"
        sep = colors["separator"]
        sep_hex = f"rgba({sep.red()}, {sep.green()}, {sep.blue()}, {sep.alpha()})"

        self._content_widget.setStyleSheet(f"""
            QWidget#cardContent {{
                background: {bg_rgba};
                border: 1px solid {sep_hex};
                border-radius: 10px;
            }}
        """)

        self._repo_label.setStyleSheet(
            f"background: transparent; color: {colors['text'].name()}; "
            f"font-size: {ctx_font_size + 1}px; font-weight: 600; font-family: '{ctx_font}';"
        )
        self._branch_label.setStyleSheet(
            f"background: transparent; color: {colors['text_secondary'].name()}; "
            f"font-size: {ctx_font_size - 1}px; font-weight: 500; font-family: '{ctx_font}';"
        )
        self._status_label.setStyleSheet(
            f"background: transparent; color: {colors['text_secondary'].name()}; "
            f"font-size: {ctx_font_size - 3}px; font-family: '{ctx_font}';"
        )
        self._separator.setStyleSheet(
            f"QFrame {{ border: none; border-top: 1px solid {sep_hex}; margin: 0; max-height: 1px; }}"
        )

        sh = colors.get("scrollbar_handle", QColor(255, 255, 255, 30))
        sh_h = colors.get("scrollbar_handle_hover", QColor(255, 255, 255, 50))
        sh_hex = f"rgba({sh.red()}, {sh.green()}, {sh.blue()}, {sh.alpha()})"
        sh_hover = f"rgba({sh_h.red()}, {sh_h.green()}, {sh_h.blue()}, {sh_h.alpha()})"
        scroll_qss = f"""
            ScrollArea {{ border: none; background: transparent; }}
            ScrollArea > QWidget > QWidget {{ background: transparent; }}
            ScrollArea QScrollBar:vertical {{ width: 6px; background: transparent; }}
            ScrollArea QScrollBar::handle:vertical {{ background: {sh_hex}; border-radius: 3px; min-height: 30px; }}
            ScrollArea QScrollBar::handle:vertical:hover {{ background: {sh_hover}; }}
            ScrollArea QScrollBar::add-line:vertical, ScrollArea QScrollBar::sub-line:vertical {{ height: 0; }}
        """
        self._calendar_scroll.setStyleSheet(scroll_qss)
        self._commits_scroll.setStyleSheet(scroll_qss)

        if self._data:
            self._calendar.set_data(self._data.get("calendar", {}))
            self._commits_widget.set_lines(self._data.get("commits", []))

    def set_context_provider(self, provider: Callable[[], Dict[str, str]]):
        self._context_provider = provider

    def set_context(self, context: dict):
        self._context = dict(context)
        self._refresh_styles()
        self._refresh_data()

    def show_card(self):
        self.setVisible(True)
        if self._context_provider:
            nc = self._context_provider()
            pr = nc.get("project_root", "")
            changed = pr != self._last_project_root and pr != self._context.get("project_root", "")
            self._context = nc
            self._refresh_styles()
            if changed:
                self._data = None
                self._last_project_root = pr
                self._refresh_data()
            elif self._data is None:
                self._refresh_data()

    def hide_card(self):
        self.setVisible(False)

    def _refresh_data(self):
        pr = self._context.get("project_root", "")
        if not pr:
            self._status_label.setText("未获取到项目路径")
            return
        if not _is_git_repo(pr):
            self._status_label.setText("非 Git 仓库")
            self._repo_label.setText(self._context.get("project_name", "(未知)"))
            self._branch_label.setText("⛔ 无仓库")
            return
        if self._loading:
            return
        self._loading = True
        self._status_label.setText("加载中...")
        self._refresh_btn.setEnabled(False)
        self._thread = QThread()
        self._worker = _GitDataWorker(pr)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_data_loaded)
        self._worker.error.connect(self._on_data_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_data_loaded(self, data: dict):
        self._data = data
        self._loading = False
        self._refresh_btn.setEnabled(True)
        self._colors = _resolve_colors(self._context)
        self._refresh_styles()
        hdr = data.get("header", {})
        rn = hdr.get("repo_name", "")
        br = hdr.get("branch", "")
        a = hdr.get("ahead", 0)
        b = hdr.get("behind", 0)
        self._repo_label.setText(rn or self._context.get("project_name", "(未知)"))
        bt = br
        if a or b:
            bt += f"  ↑{a}  ↓{b}"
        self._branch_label.setText(bt)
        self._status_label.setText("")
        self._calendar.set_data(data.get("calendar", {}))
        self._commits_widget.set_lines(data.get("commits", []))

    def _on_data_error(self, err: str):
        self._loading = False
        self._refresh_btn.setEnabled(True)
        self._status_label.setText("加载失败")
        logger.error(f"[GitDashboard] 数据加载失败: {err}")

    def refresh_style(self):
        self._colors = _resolve_colors(self._context)
        changed = False
        if self._context_provider:
            nc = self._context_provider()
            nr = nc.get("project_root", "")
            or_ = self._context.get("project_root", "")
            if nr and nr != or_ and nr != self._last_project_root:
                self._context = nc
                self._last_project_root = nr
                self._data = None
                changed = True
        if changed:
            self._refresh_data()
        elif self._data:
            self._calendar.set_data(self._data.get("calendar", {}))
            self._commits_widget.set_lines(self._data.get("commits", []))
        self._refresh_styles()
        self.update()
