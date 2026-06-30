# -*- coding: utf-8 -*-
"""
GitDashboardCard 浮动卡片 — Git 仓库可视化仪表盘

功能：
- 🔀 头部状态栏：仓库名、当前分支、ahead/behind
- ☀ 提交日历热力图（GitHub 风格）：过去一年每天的提交数
- 📜 最近提交列表：最近 20 条 commit
- 🌿 分支图：git log --graph 可视化

数据获取：
- 通过 context_provider 拿到 project_root（即 DriFox 当前工作目录）
- 所有 git 命令在 QThread 后台执行，不阻塞 UI

设计约束：
- 不导入 app.core 或 app.widgets 内部模块
- 所有数据通过 subprocess + git 命令获取
- 颜色方案自动跟随浅色/深色主题
"""

from __future__ import annotations

import subprocess
import traceback
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import QObject, QPointF, QRectF, QThread, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    FluentIcon,
    IconWidget,
    ScrollArea,
    StrongBodyLabel,
    ToolButton,
    TransparentToolButton,
    isDarkTheme,
)
from loguru import logger

PLUGIN_NAME = "git-dashboard"

# ── Git 命令超时 ────────────────────────────────────────
GIT_TIMEOUT = 5


# ============================================================
# 工具函数
# ============================================================


def _text_color(secondary: bool = False) -> str:
    if isDarkTheme():
        return "rgba(255,255,255,0.55)" if secondary else "rgba(255,255,255,0.9)"
    return "rgba(0,0,0,0.45)" if secondary else "rgba(0,0,0,0.85)"


def _card_bg() -> str:
    if isDarkTheme():
        return "rgba(255,255,255,0.05)"
    return "rgba(0,0,0,0.03)"


def _chart_colors() -> dict:
    """返回图表颜色方案（跟随主题）"""
    if isDarkTheme():
        return {
            "bg": QColor(30, 30, 30),
            "card_bg": QColor(255, 255, 255, 15),
            "text": QColor(255, 255, 255, 200),
            "text_secondary": QColor(255, 255, 255, 100),
            "grid": QColor(255, 255, 255, 15),
            "accent": QColor(98, 160, 234),
            "success": QColor(80, 227, 194, 200),
            "warning": QColor(255, 193, 7, 200),
            "danger": QColor(255, 107, 107, 200),
            "graph_line": QColor(98, 160, 234, 120),
            "graph_dot": QColor(98, 160, 234),
            # 提交日历 5 级颜色（从浅到深）
            "cal_0": QColor(40, 40, 40),          # 无提交
            "cal_1": QColor(14, 68, 41),           # 1-3 次
            "cal_2": QColor(0, 109, 50),           # 4-6 次
            "cal_3": QColor(38, 166, 65),          # 7-10 次
            "cal_4": QColor(57, 211, 83),          # 10+ 次
            "cal_label": QColor(255, 255, 255, 100),
            "cal_border": QColor(255, 255, 255, 8),
        }
    return {
        "bg": QColor(250, 250, 250),
        "card_bg": QColor(0, 0, 0, 6),
        "text": QColor(0, 0, 0, 200),
        "text_secondary": QColor(0, 0, 0, 100),
        "grid": QColor(0, 0, 0, 10),
        "accent": QColor(40, 120, 220),
        "success": QColor(16, 185, 129, 200),
        "warning": QColor(245, 158, 11, 200),
        "danger": QColor(239, 68, 68, 200),
        "graph_line": QColor(40, 120, 220, 100),
        "graph_dot": QColor(40, 120, 220),
        # 提交日历 5 级颜色
        "cal_0": QColor(235, 237, 240),
        "cal_1": QColor(155, 233, 168),
        "cal_2": QColor(0, 184, 77),
        "cal_3": QColor(0, 140, 60),
        "cal_4": QColor(0, 100, 40),
        "cal_label": QColor(0, 0, 0, 100),
        "cal_border": QColor(0, 0, 0, 6),
    }


def _format_number(n: int) -> str:
    if n >= 1000000:
        return f"{n / 1000000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


# ============================================================
# Git 数据采集（在 QThread 中运行）
# ============================================================


def _run_git(cwd: str, *args: str) -> Tuple[str, str, int]:
    """执行 git 命令，返回 (stdout, stderr, returncode)"""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT,
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
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
    """收集仓库状态：repo 名、分支、ahead/behind"""
    info: dict = {
        "repo_name": "",
        "branch": "",
        "ahead": 0,
        "behind": 0,
    }
    # 仓库名（目录名）
    stdout, _, _ = _run_git(cwd, "rev-parse", "--show-toplevel")
    if stdout:
        import os as _os
        info["repo_name"] = _os.path.basename(stdout)

    # 分支名
    stdout, _, code = _run_git(cwd, "branch", "--show-current")
    if code == 0 and stdout:
        info["branch"] = stdout
    else:
        stdout, _, _ = _run_git(cwd, "rev-parse", "--short", "HEAD")
        if stdout:
            info["branch"] = f"(detached @ {stdout})"

    # ahead/behind
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
    """收集过去一年每天的提交数

    Returns:
        {"2025-01-15": 3, "2025-01-16": 0, ...}
    """
    # git log 获取过去一年的提交日期
    stdout, _, code = _run_git(
        cwd, "log", "--after=1 year ago", "--format=%ai", "--all", "--no-merges"
    )
    if code != 0 or not stdout:
        return {}

    daily: Dict[str, int] = defaultdict(int)
    for line in stdout.splitlines():
        date_str = line[:10]  # "2025-01-15"
        if date_str:
            daily[date_str] += 1
    return dict(daily)


def _collect_recent_commits(cwd: str, n: int = 20) -> List[str]:
    """收集最近 n 条 commit（短 hash + subject）"""
    stdout, _, code = _run_git(
        cwd, "log", f"-n{n}", "--oneline", "--decorate", "--no-merges"
    )
    if code == 0 and stdout:
        return stdout.splitlines()
    return []


def _collect_commit_graph(cwd: str, n: int = 30) -> List[str]:
    """收集分支图（git log --graph）"""
    stdout, _, code = _run_git(
        cwd, "log", "--all", "--oneline", "--graph", f"-n{n}", "--decorate"
    )
    if code == 0 and stdout:
        return stdout.splitlines()
    return []


class _GitDataWorker(QObject):
    """后台线程：采集所有 git 数据"""

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
                "graph": _collect_commit_graph(self._cwd),
            }
            self.finished.emit(data)
        except Exception as e:
            self.error.emit(f"{e}\n{traceback.format_exc()}")


# ============================================================
# 提交日历热力图组件
# ============================================================


class _CalendarWidget(QWidget):
    """GitHub 风格提交日历热力图

    7 行（日~六） × 53 列（周），每格颜色深浅表示提交次数。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._daily: Dict[str, int] = {}
        self._total_commits = 0
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_data(self, daily: Dict[str, int]):
        self._daily = daily
        self._total_commits = sum(daily.values())
        self.update()

    @property
    def total_commits(self) -> int:
        return self._total_commits

    def paintEvent(self, event):
        if not self._daily:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            colors = _chart_colors()
            painter.setPen(colors["text_secondary"])
            font = QFont("Microsoft YaHei", 9)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignCenter, "暂无提交数据")
            painter.end()
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        colors = _chart_colors()
        w = self.width()
        h = self.height()

        # 布局参数
        margin_left = 36
        margin_top = 28
        margin_right = 16
        margin_bottom = 16

        cell_size = min(13, (w - margin_left - margin_right) // 54)
        cell_size = max(8, cell_size)
        cell_gap = 2
        step = cell_size + cell_gap

        chart_w = 53 * step
        chart_h = 7 * step

        # 居中
        offset_x = margin_left
        offset_y = margin_top

        # ── 标题 ──
        title_font = QFont("Microsoft YaHei", 10, QFont.Bold)
        painter.setFont(title_font)
        painter.setPen(colors["text"])
        painter.drawText(
            QRectF(offset_x, 4, 300, 22),
            Qt.AlignLeft | Qt.AlignVCenter,
            f"☀ 提交日历 · 过去一年 · 总计 {_format_number(self._total_commits)} 次提交",
        )

        # ── 计算颜色等级 ──
        values = sorted(self._daily.values())
        if not values:
            painter.end()
            return

        # 分 4 个提交密度等级（cal_1~4），cal_0 为 0 次
        max_val = max(values)
        thresholds = [0, 1, 3, 6] if max_val <= 6 else [
            max(1, int(max_val * 0.1)),
            max(2, int(max_val * 0.3)),
            max(3, int(max_val * 0.6)),
        ]
        # 补全到 4 个阈值
        while len(thresholds) < 3:
            thresholds.append(max_val)
        thresholds = thresholds[:3]

        def _level(count: int) -> int:
            if count == 0:
                return 0
            if count <= thresholds[0]:
                return 1
            if count <= thresholds[1]:
                return 2
            if count <= thresholds[2]:
                return 3
            return 4

        cal_colors = [colors["cal_0"], colors["cal_1"], colors["cal_2"], colors["cal_3"], colors["cal_4"]]

        # ── 计算日期 → 格子坐标 ──
        # 找到过去一年第一天是星期几
        today = datetime.now()
        one_year_ago = today - timedelta(days=364)

        # 从那天开始，逐日映射到 (col, row)
        # col = 星期几偏移周数, row = weekday (0=周一)
        day = one_year_ago
        col_map: Dict[str, Tuple[int, int]] = {}
        while day <= today:
            date_key = day.strftime("%Y-%m-%d")
            # Python weekday: 0=周一, 6=周日；GitHub: 0=周日, 6=周六
            row = (day.weekday() + 1) % 7  # 0=周日
            # 计算这是第几周（从 one_year_ago 所在的周日开始算）
            days_since_start = (day - one_year_ago).days
            col = days_since_start // 7
            col_map[date_key] = (col, row)
            day += timedelta(days=1)

        # ── 画格子 ──
        for date_key, count in self._daily.items():
            if date_key not in col_map:
                continue
            col, row = col_map[date_key]
            x = offset_x + col * step
            y = offset_y + row * step
            lvl = _level(count)
            rect = QRectF(x, y, cell_size, cell_size)
            path = QPainterPath()
            path.addRoundedRect(rect, 2, 2)
            painter.fillPath(path, cal_colors[lvl])
            painter.setPen(QPen(colors["cal_border"], 0.5))
            painter.drawPath(path)

        # ── 星期标签（仅显示 3 行节省空间） ──
        label_font = QFont("Microsoft YaHei", 7)
        painter.setFont(label_font)
        painter.setPen(colors["cal_label"])
        day_labels = {0: "日", 2: "二", 4: "四"}
        for row, label in day_labels.items():
            y = offset_y + row * step + (cell_size - 10) / 2
            painter.drawText(
                QRectF(2, y, margin_left - 6, 14),
                Qt.AlignRight | Qt.AlignVCenter,
                label,
            )

        # ── 月份标签 ──
        month_font = QFont("Microsoft YaHei", 7)
        painter.setFont(month_font)
        current_month = -1
        for date_key, (col, row) in col_map.items():
            if row != 0:  # 只在周日行标月份
                continue
            try:
                month = int(date_key[5:7])
                if month != current_month:
                    current_month = month
                    month_names = ["", "1月", "2月", "3月", "4月", "5月", "6月",
                                   "7月", "8月", "9月", "10月", "11月", "12月"]
                    x = offset_x + col * step
                    painter.drawText(
                        QRectF(x, offset_y - 16, step * 4, 14),
                        Qt.AlignLeft | Qt.AlignVCenter,
                        month_names[month],
                    )
            except (ValueError, IndexError):
                pass

        painter.end()


# ============================================================
# Git 日志渲染组件
# ============================================================


class _LogWidget(QWidget):
    """垂直信息展示组件 — 接收纯文本行并渲染为带颜色的列表"""

    def __init__(self, title: str, icon_char: str, parent=None):
        super().__init__(parent)
        self._title = title
        self._icon = icon_char
        self._lines: List[str] = []
        self._is_graph = (icon_char == "🌿")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)

    def set_lines(self, lines: List[str]):
        self._lines = lines
        self._update_height()
        self.update()

    def _update_height(self):
        n = max(1, len(self._lines))
        line_h = 22 if not self._is_graph else 20
        header = 30
        self.setMinimumHeight(header + n * line_h + 8)
        self.setMaximumHeight(header + n * line_h + 8)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        colors = _chart_colors()
        w = self.width()
        h = self.height()

        # ── 背景 ──
        bg_path = QPainterPath()
        bg_path.addRoundedRect(QRectF(2, 2, w - 4, h - 4), 6, 6)
        painter.fillPath(bg_path, colors["card_bg"])

        # ── 标题 ──
        title_font = QFont("Microsoft YaHei", 10, QFont.Bold)
        painter.setFont(title_font)
        painter.setPen(colors["text"])
        painter.drawText(QRectF(12, 6, w - 24, 24), Qt.AlignLeft | Qt.AlignVCenter,
                         f"{self._icon} {self._title}")

        # ── 分隔线 ──
        painter.setPen(QPen(colors["grid"], 1))
        painter.drawLine(QPointF(12, 32), QPointF(w - 12, 32))

        # ── 内容行 ──
        if not self._lines:
            painter.setPen(colors["text_secondary"])
            empty_font = QFont("Microsoft YaHei", 9)
            painter.setFont(empty_font)
            painter.drawText(QRectF(12, 36, w - 24, h - 42), Qt.AlignLeft | Qt.AlignTop,
                             "(暂无数据)")
            painter.end()
            return

        y = 38
        if self._is_graph:
            # 分支图：等宽字体显示，graph 线用青色，hash 用黄色
            graph_font = QFont("Consolas", 9)
            if not graph_font.exactMatch():
                graph_font = QFont("Courier New", 9)
            painter.setFont(graph_font)
            fm = QFontMetrics(graph_font)

            for line in self._lines:
                if y > h - 4:
                    break
                # 分离 graph 字符和提交信息
                # 格式: "*   a1b2c3 feat: xxx" 或 "| * 8d7e6f fix: yyy"
                graph_part = ""
                msg_part = line
                # 找到第一个字母/数字前的 graph 符号
                for i, ch in enumerate(line):
                    if ch.isalnum():
                        graph_part = line[:i]
                        msg_part = line[i:]
                        break

                x = 12
                # 绘制 graph 部分
                if graph_part:
                    painter.setPen(colors["graph_line"])
                    painter.drawText(QPointF(x, y), graph_part)
                    x += fm.width(graph_part)

                # 分隔空格
                msg_part = msg_part.lstrip()

                # 绘制 hash（前 7 字符）
                if msg_part and len(msg_part) >= 7:
                    hash_str = msg_part[:7]
                    painter.setPen(colors["graph_dot"])
                    painter.drawText(QPointF(x, y), hash_str)
                    x += fm.width(hash_str)
                    msg_part = msg_part[7:]

                # 绘制提交信息
                painter.setPen(colors["text"])
                painter.drawText(QPointF(x, y), msg_part)

                y += 20
        else:
            # 普通提交列表
            list_font = QFont("Microsoft YaHei", 9)
            painter.setFont(list_font)
            for line in self._lines:
                if y > h - 4:
                    break
                # 格式: "a1b2c3 feat: message"
                painter.setPen(colors["text"])
                # 用圆点代替 commit dot
                if line:
                    hash_end = line.find(" ")
                    if hash_end > 0:
                        hash_part = line[:hash_end]
                        msg_part = line[hash_end:]

                        # 圆点
                        painter.setPen(colors["success"])
                        painter.drawText(QPointF(12, y), "●")

                        # hash
                        hash_font = QFont("Consolas", 9)
                        painter.setFont(hash_font)
                        painter.setPen(colors["accent"])
                        painter.drawText(QPointF(30, y), hash_part)

                        # 消息
                        painter.setFont(list_font)
                        painter.setPen(colors["text"])
                        painter.drawText(QPointF(30 + painter.fontMetrics().width(hash_part) + 8, y), msg_part)
                    else:
                        painter.setPen(colors["text_secondary"])
                        painter.drawText(QPointF(12, y), line)
                y += 22

        painter.end()


# ============================================================
# GitDashboardCard 主卡片
# ============================================================


class GitDashboardCard(QWidget):
    """Git 仪表盘浮动卡片

    通过 set_context() 接收 project_root，然后异步加载 git 数据并渲染。
    """

    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._context: Dict[str, str] = {}
        self._data: Optional[dict] = None
        self._loading = False
        self._worker: Optional[_GitDataWorker] = None
        self._thread: Optional[QThread] = None

        # 布局
        self._setup_ui()

    def _setup_ui(self):
        self.setObjectName("git-dashboard-card")

        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ── 头部：仓库名 + 分支 + 刷新按钮 ──
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        self._header_widget = QWidget()
        self._header_layout = QHBoxLayout(self._header_widget)
        self._header_layout.setContentsMargins(0, 0, 0, 0)

        # 仓库图标 + 名称
        self._repo_icon = IconWidget(FluentIcon.GITHUB, self)
        self._repo_icon.setFixedSize(20, 20)
        self._header_layout.addWidget(self._repo_icon)

        self._repo_label = StrongBodyLabel("", self)
        self._header_layout.addWidget(self._repo_label)
        self._header_layout.addSpacing(16)

        # 分支
        self._branch_icon = IconWidget(FluentIcon.BRANCH, self)
        self._branch_icon.setFixedSize(16, 16)
        self._header_layout.addWidget(self._branch_icon)

        self._branch_label = QLabel("", self)
        self._branch_label.setStyleSheet(f"color: {_text_color()}; font-size: 13px;")
        self._header_layout.addWidget(self._branch_label)

        self._header_layout.addStretch()

        # 状态消息
        self._status_label = QLabel("", self)
        self._status_label.setStyleSheet(f"color: {_text_color(True)}; font-size: 11px;")
        self._header_layout.addWidget(self._status_label)

        # 刷新按钮
        self._refresh_btn = TransparentToolButton(FluentIcon.SYNC, self)
        self._refresh_btn.setFixedSize(28, 28)
        self._refresh_btn.setToolTip("刷新")
        self._refresh_btn.clicked.connect(self._refresh_data)
        self._header_layout.addWidget(self._refresh_btn)

        layout.addWidget(self._header_widget)

        # ── 滚动区域（主体） ──
        self._scroll = ScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("ScrollArea { border: none; background: transparent; }")

        self._scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_layout.setSpacing(8)

        # 提交日历
        self._calendar = _CalendarWidget(self._scroll_content)
        self._scroll_layout.addWidget(self._calendar)

        # 最近提交
        self._commits_widget = _LogWidget("最近提交", "📜", self._scroll_content)
        self._scroll_layout.addWidget(self._commits_widget)

        # 分支图
        self._graph_widget = _LogWidget("分支图", "🌿", self._scroll_content)
        self._scroll_layout.addWidget(self._graph_widget)

        # 间距
        self._scroll_layout.addStretch()

        self._scroll.setWidget(self._scroll_content)
        layout.addWidget(self._scroll, 1)

        # 初始状态
        self._status_label.setText("等待上下文...")

    def set_context(self, context: dict):
        """由 UIPluginRegistry 注入上下文

        context 包含:
        - project_root: 当前工作目录
        - project_name: 当前项目名
        - session_id: 当前会话 ID
        - window_id: 当前窗口 ID
        """
        self._context = dict(context)
        # 拿到 context 后立即开始加载数据
        self._refresh_data()

    def _refresh_data(self):
        """刷新 git 数据"""
        project_root = self._context.get("project_root", "")
        if not project_root:
            self._status_label.setText("未获取到项目路径")
            return

        if not _is_git_repo(project_root):
            self._status_label.setText("非 Git 仓库")
            self._repo_label.setText(self._context.get("project_name", "(未知)"))
            self._branch_label.setText("⛔ 无仓库")
            return

        if self._loading:
            return

        self._loading = True
        self._status_label.setText("加载中...")
        self._refresh_btn.setEnabled(False)

        # 启动后台线程
        self._thread = QThread()
        self._worker = _GitDataWorker(project_root)
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
        """数据加载完成后刷新 UI"""
        self._data = data
        self._loading = False
        self._refresh_btn.setEnabled(True)
        self._status_label.setText("")

        # ── 头部 ──
        header = data.get("header", {})
        repo_name = header.get("repo_name", "")
        branch = header.get("branch", "")
        ahead = header.get("ahead", 0)
        behind = header.get("behind", 0)

        if repo_name:
            self._repo_label.setText(repo_name)
        else:
            self._repo_label.setText(self._context.get("project_name", "(未知)"))

        branch_text = branch
        if ahead or behind:
            branch_text += f"  ↑{ahead} ↓{behind}"
        self._branch_label.setText(branch_text)

        # ── 提交日历 ──
        self._calendar.set_data(data.get("calendar", {}))

        # ── 最近提交 ──
        self._commits_widget.set_lines(data.get("commits", []))

        # ── 分支图 ──
        self._graph_widget.set_lines(data.get("graph", []))

    def _on_data_error(self, err: str):
        self._loading = False
        self._refresh_btn.setEnabled(True)
        self._status_label.setText("加载失败")
        logger.error(f"[GitDashboard] 数据加载失败: {err}")

    def show_card(self):
        """卡片显示时触发"""
        self.setVisible(True)
        # 如果还没有数据，自动刷新
        if self._data is None and self._context:
            self._refresh_data()

    def hide_card(self):
        """卡片隐藏时触发"""
        self.setVisible(False)
