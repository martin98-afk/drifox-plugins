# -*- coding: utf-8 -*-
"""GitPanelCard 浮动卡片 — Git 控制面板

功能：
- 文件变更列表（已暂存 / 未暂存）
- 暂存 / 取消暂存 / 放弃修改
- 提交（含 --amend）
- Stash 创建 / 列表 / 应用 / 弹出 / 删除
- 分支切换 / 创建 / 删除
- 提交历史（Graph 图）
- Diff 预览对话框

设计约束（闭包）：
- 不导入 app.core 或 app.widgets 内部的任何模块
- 所有 Git 操作通过 subprocess 完成，在 QThread 中异步执行
"""

import re
import subprocess
import traceback
from typing import Callable, List, Optional, Tuple

from PyQt5.QtCore import QObject, QPoint, QRectF, QSize, QThread, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QScrollArea as QWScrollArea,
)
from qfluentwidgets import (
    FluentIcon,
    FluentLabelBase,
    IconWidget,
    PrimaryPushButton,
    ScrollArea,
    StrongBodyLabel,
    ToolButton,
    TransparentToolButton,
    isDarkTheme,
)
from loguru import logger

PLUGIN_NAME = "git-panel"
GIT_TIMEOUT = 15

# ── 图标常量（避免拼写错误） ──
_ICONS = {
    "git": None,
    "branch": None,
    "refresh": FluentIcon.SYNC,
    "close": FluentIcon.CLOSE,
    "add": FluentIcon.ADD,
    "delete": FluentIcon.DELETE,
    "accept": FluentIcon.ACCEPT,
    "cancel": FluentIcon.CANCEL,
}


# ========================================================================
# 1. 主题色辅助
# ========================================================================


def _resolve_colors(context: Optional[dict] = None) -> dict:
    """从上下文解析颜色字典"""
    if context and context.get("colors"):
        return context["colors"]
    return _fallback_colors()


def _fallback_colors() -> dict:
    """无上下文时的 fallback 颜色"""
    dark = isDarkTheme()
    if dark:
        return {
            "text_primary": "rgba(255,255,255,0.9)",
            "text_secondary": "rgba(255,255,255,0.55)",
            "border": "rgba(255,255,255,0.1)",
            "accent": "#62a0ea",
            "success": "#50e3c2",
            "card_bg": "rgba(33,33,38,240)",
        }
    return {
        "text_primary": "rgba(0,0,0,0.85)",
        "text_secondary": "rgba(0,0,0,0.45)",
        "border": "rgba(0,0,0,0.1)",
        "accent": "#2878dc",
        "success": "#10b981",
        "card_bg": "rgba(255,255,255,240)",
    }


def _text_color(secondary: bool = False) -> str:
    """fallback 文字颜色"""
    if isDarkTheme():
        return "rgba(255,255,255,0.55)" if secondary else "rgba(255,255,255,0.9)"
    return "rgba(0,0,0,0.45)" if secondary else "rgba(0,0,0,0.85)"


def _ctx_font(ctx: dict) -> Tuple[str, int]:
    ff = ctx.get("font_family", "Microsoft YaHei")
    fs = ctx.get("font_size", 14)
    return ff, fs


def _ctx_text_color(ctx: dict, secondary: bool = False) -> str:
    colors = ctx.get("colors", {})
    key = "text_secondary" if secondary else "text_primary"
    val = colors.get(key, "")
    return val if val else _text_color(secondary)


def _ctx_border_color(ctx: dict) -> str:
    return ctx.get("colors", {}).get("border", "rgba(128,128,128,0.15)")


def _make_style(color: str, font_family: str = "", font_size: int = 0, extra: str = "") -> str:
    parts = [f"color: {color};"]
    if font_family:
        parts.append(f"font-family: '{font_family}';")
    if font_size:
        parts.append(f"font-size: {font_size}px;")
    if extra:
        parts.append(extra)
    return " ".join(parts)


# ========================================================================
# 2. Git 工具函数
# ========================================================================


def _run_git(cwd: str, *args: str) -> Tuple[str, str, int]:
    """执行 git 命令，返回 (stdout, stderr, returncode)"""
    try:
        r = subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
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


def _get_branch(cwd: str) -> str:
    stdout, _, code = _run_git(cwd, "branch", "--show-current")
    if code == 0 and stdout:
        return stdout
    stdout, _, _ = _run_git(cwd, "rev-parse", "--short", "HEAD")
    if stdout:
        return f"(detached @ {stdout})"
    return ""


def _get_ahead_behind(cwd: str) -> Tuple[int, int]:
    stdout, _, _ = _run_git(cwd, "rev-list", "--left-right", "--count", "HEAD...@{u}")
    if stdout:
        parts = stdout.split()
        if len(parts) == 2:
            try:
                return int(parts[0]), int(parts[1])
            except ValueError:
                pass
    return 0, 0


def _get_status(cwd: str) -> List[dict]:
    """获取文件变更列表，返回 [{"path": str, "status": str, "staged": bool}, ...]

    git status --porcelain 格式：XY PATH
    - X = 暂存区状态，Y = 工作区状态
    - "??" = 未跟踪文件（优先级最高，先处理避免重复）
    """
    stdout, _, code = _run_git(cwd, "status", "--porcelain", "-u")
    if code != 0 or not stdout:
        return []
    result = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        x = line[0]
        y = line[1]
        path = line[3:].strip()

        # 1. 未跟踪文件（??）
        if x == "?" and y == "?":
            result.append({"path": path, "status": "??", "staged": False})
            continue

        # 2. 暂存区变更（X != ' '）
        if x != " ":
            result.append({"path": path, "status": x, "staged": True})

        # 3. 工作区变更（Y != ' '）
        if y != " ":
            result.append({"path": path, "status": y, "staged": False})
    return result


def _get_diff(cwd: str, path: str, staged: bool = False) -> str:
    """获取单个文件的 diff"""
    args = ["diff", "--cached", "--"] if staged else ["diff", "--"]
    stdout, _, _ = _run_git(cwd, *args, path)
    return stdout


def _get_stashes(cwd: str) -> List[dict]:
    """获取 stash 列表"""
    stdout, _, code = _run_git(cwd, "stash", "list")
    if code != 0 or not stdout:
        return []
    result = []
    for line in stdout.splitlines():
        parts = line.split(": ", 1)
        ref = parts[0] if len(parts) > 0 else ""
        msg = parts[1] if len(parts) > 1 else ""
        # Extract index from ref like "stash@{0}"
        idx = 0
        m = re.search(r"stash@\{(\d+)\}", ref)
        if m:
            idx = int(m.group(1))
        result.append({"ref": ref, "message": msg, "index": idx})
    return result


def _get_branches(cwd: str) -> List[dict]:
    """获取分支列表"""
    stdout, _, code = _run_git(cwd, "branch")
    if code != 0 or not stdout:
        return []
    current_branch = _get_branch(cwd)
    result = []
    for line in stdout.splitlines():
        is_current = line.startswith("*")
        name = line[2:].strip()
        result.append({"name": name, "current": is_current})
    return result


def _get_log(cwd: str, n: int = 30) -> List[dict]:
    """获取提交历史"""
    fmt = "--format=%h%x1f%an%x1f%ai%x1f%s%x1f%D"
    stdout, _, code = _run_git(cwd, "log", f"-n{n}", fmt, "--all")
    if code != 0 or not stdout:
        return []
    result = []
    for line in stdout.splitlines():
        parts = line.split("\x1f")
        hash_ = parts[0] if len(parts) > 0 else ""
        author = parts[1] if len(parts) > 1 else ""
        date_raw = parts[2] if len(parts) > 2 else ""
        subject = parts[3] if len(parts) > 3 else ""
        refs = parts[4] if len(parts) > 4 else ""
        # Format date to YYYY-MM-DD HH:MM
        date = date_raw
        if date_raw and len(date_raw) >= 10:
            date = date_raw[:10]
        result.append({
            "hash": hash_,
            "author": author,
            "date": date,
            "subject": subject,
            "refs": refs,
        })
    return result


# ========================================================================
# 3. 异步 Worker
# ========================================================================


class _Worker(QObject):
    """后台执行任意阻塞操作，通过信号返回结果"""

    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            result = self._fn(*self._args, **self._kwargs)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(f"{e}\n{traceback.format_exc()}")


# ========================================================================
# 4. 文件变更行控件
# ========================================================================

_STATUS_MAP = {
    "M": ("📝", "#e2c08d", "修改"),
    "A": ("➕", "#50e3c2", "新增"),
    "D": ("🗑", "#f14c4c", "删除"),
    "R": ("🔁", "#62a0ea", "重命名"),
    "C": ("📋", "#62a0ea", "复制"),
    "??": ("❓", "#f0a030", "未跟踪"),
    "U": ("⚠️", "#f0a030", "冲突"),
}


class _FileRowWidget(QWidget):
    """单个文件变更行"""

    staged_changed = pyqtSignal()  # 暂存/取消暂存后触发刷新
    diff_requested = pyqtSignal(str, bool)  # (path, staged)

    def __init__(self, file_info: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("FileRow")
        self._info = file_info
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedHeight(32)
        self.setStyleSheet(
            "#FileRow { background: transparent; }"
            "#FileRow:hover { background: rgba(128,128,128,0.06); border-radius: 4px; }"
        )

        ly = QHBoxLayout(self)
        ly.setContentsMargins(8, 0, 8, 0)
        ly.setSpacing(6)

        # 状态图标
        st = self._info["status"]
        icon_text, color, desc = _STATUS_MAP.get(st, ("❔", "#888", "未知"))
        status_lb = QLabel(icon_text, self)
        status_lb.setFixedWidth(22)
        status_lb.setStyleSheet("background: transparent; font-size: 13px;")
        status_lb.setToolTip(f"{desc} ({st})")
        ly.addWidget(status_lb)

        # 文件路径
        path_lb = QLabel(self._info["path"], self)
        path_lb.setStyleSheet(
            f"background: transparent; color: {_text_color()}; "
            f"font-size: 13px;"
        )
        path_lb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        path_lb.setCursor(Qt.PointingHandCursor)
        path_lb.mousePressEvent = lambda e: self.diff_requested.emit(
            self._info["path"], self._info["staged"]
        )
        ly.addWidget(path_lb)

        # 暂存/取消暂存按钮
        if self._info["staged"]:
            btn = TransparentToolButton(FluentIcon.CANCEL, self)
            btn.setFixedSize(22, 22)
            btn.setToolTip("取消暂存")
            btn.clicked.connect(self._on_unstage)
        else:
            btn = TransparentToolButton(FluentIcon.ADD, self)
            btn.setFixedSize(22, 22)
            btn.setToolTip("暂存")
            btn.clicked.connect(self._on_stage)
        ly.addWidget(btn)

        # 放弃修改按钮
        discard_btn = QPushButton("↩", self)
        discard_btn.setFixedSize(22, 22)
        discard_btn.setToolTip("放弃修改")
        discard_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; "
            f"color: {_text_color(secondary=True)}; font-size: 12px; "
            "padding: 0; }"
            "QPushButton:hover { color: #f14c4c; }"
        )
        discard_btn.clicked.connect(self._on_discard)
        ly.addWidget(discard_btn)

    def _get_repo_path(self) -> str:
        p = self
        while p:
            if hasattr(p, "_repo_path"):
                return p._repo_path
            p = p.parent()
        return ""

    def _on_stage(self):
        repo = self._get_repo_path()
        if repo:
            _, _, code = _run_git(repo, "add", self._info["path"])
            if code == 0:
                self.staged_changed.emit()
            else:
                logger.error(f"[git-panel] stage failed: {self._info['path']}")

    def _on_unstage(self):
        repo = self._get_repo_path()
        if repo:
            _, _, code = _run_git(repo, "restore", "--staged", self._info["path"])
            if code == 0:
                self.staged_changed.emit()

    def _on_discard(self):
        path = self._info["path"]
        st = self._info["status"]
        if not _ConfirmDialog.ask("确认放弃修改", f"确定要放弃 {path} 的所有修改吗？\n此操作不可恢复！", self):
            return
        repo = self._get_repo_path()
        if repo:
            # 未跟踪文件用 git clean，已跟踪文件用 git checkout
            if st == "??":
                _, _, code = _run_git(repo, "clean", "-f", "--", path)
            elif st == "D":
                _, _, code = _run_git(repo, "checkout", "--", path)
            else:
                _, _, code = _run_git(repo, "checkout", "--", path)
            if code == 0:
                self.staged_changed.emit()
            else:
                logger.error(f"[git-panel] discard failed: {path} (status={st})")


# ========================================================================
# 5. Diff 预览对话框
# ========================================================================


class _DiffDialog(QDialog):
    """Diff 预览对话框"""

    def __init__(self, repo_path: str, file_path: str, staged: bool, parent=None):
        super().__init__(parent)
        self._repo_path = repo_path
        self._file_path = file_path
        self._staged = staged
        self.setWindowTitle(f"Diff — {file_path}")
        self.setMinimumSize(700, 450)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._setup_ui()
        self._load_diff()

    def _setup_ui(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(16, 16, 16, 16)
        ly.setSpacing(8)

        # 头部
        hdr = QWidget(self)
        hdr.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(0, 0, 0, 0)

        title = StrongBodyLabel(f"📄 {self._file_path}", hdr)
        hl.addWidget(title)
        hl.addStretch(1)

        status_text = "已暂存" if self._staged else "工作区"
        status_lb = QLabel(f"[{status_text}]", hdr)
        status_lb.setStyleSheet(f"color: {_text_color(secondary=True)}; background: transparent;")
        hl.addWidget(status_lb)

        # Diff 内容
        self._diff_area = QTextEdit(self)
        self._diff_area.setReadOnly(True)
        self._diff_area.setStyleSheet(
            "QTextEdit { background: rgba(0,0,0,0.2); border: 1px solid rgba(128,128,128,0.15); "
            "border-radius: 6px; padding: 8px; font-family: 'Consolas', 'Courier New', monospace; "
            f"color: {_text_color()}; font-size: 13px; }}"
        )
        ly.addWidget(hdr)
        ly.addWidget(self._diff_area, 1)

        # 关闭按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        close_btn = QPushButton("关闭", self)
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        ly.addLayout(btn_row)

    def _load_diff(self):
        try:
            if self._staged:
                stdout, _, _ = _run_git(self._repo_path, "diff", "--cached", "--", self._file_path)
            else:
                stdout, _, _ = _run_git(self._repo_path, "diff", "--", self._file_path)

            if not stdout:
                self._diff_area.setPlainText("(无差异)")
                return

            # 对 diff 进行语法着色
            colored = self._colorize_diff(stdout)
            self._diff_area.setHtml(colored)
        except Exception as e:
            self._diff_area.setPlainText(f"加载 diff 失败: {e}")

    def _colorize_diff(self, diff_text: str) -> str:
        """将 diff 文本转为带颜色的 HTML"""
        lines = diff_text.splitlines()
        html_parts = ['<pre style="margin:0; white-space:pre-wrap;">']
        for line in lines:
            escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if line.startswith("+"):
                html_parts.append(f'<span style="color:#50e3c2;">{escaped}</span>\n')
            elif line.startswith("-"):
                html_parts.append(f'<span style="color:#f14c4c;">{escaped}</span>\n')
            elif line.startswith("@@"):
                html_parts.append(f'<span style="color:#62a0ea;font-weight:bold;">{escaped}</span>\n')
            elif line.startswith("diff --git") or line.startswith("index ") or line.startswith("---") or line.startswith("+++"):
                html_parts.append(f'<span style="color:{_text_color(secondary=True)};">{escaped}</span>\n')
            else:
                html_parts.append(f'<span style="color:{_text_color()};">{escaped}</span>\n')
        html_parts.append("</pre>")
        return "".join(html_parts)


# ========================================================================
# 5.5 确认弹窗（Fluent 风格，替代 QMessageBox）
# ========================================================================


class _ConfirmDialog(QDialog):
    """Fluent 风格确认弹窗"""

    def __init__(self, title: str, message: str, parent=None):
        super().__init__(parent)
        self._confirmed = False
        self.setWindowTitle(title)
        self.setFixedSize(360, 180)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._setup_ui(title, message)

    def _setup_ui(self, title: str, message: str):
        colors = _resolve_colors()
        bg = colors.get("card_bg", "rgba(33,33,38,240)")
        if isinstance(bg, str):
            bg_rgba = bg
        else:
            bg_rgba = f"rgba({bg.red()}, {bg.green()}, {bg.blue()}, {bg.alpha()})"
        tc = colors.get("text_primary", _text_color())
        tcs = colors.get("text_secondary", _text_color(secondary=True))
        border = colors.get("border", "rgba(128,128,128,0.15)")

        self.setStyleSheet(f"""
            _ConfirmDialog {{ background: transparent; }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QWidget(self)
        card.setObjectName("confirmCard")
        card.setStyleSheet(f"""
            #confirmCard {{
                background: {bg_rgba};
                border: 1px solid {border};
                border-radius: 12px;
            }}
        """)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(24, 20, 24, 16)
        cl.setSpacing(12)

        # 标题
        title_lb = QLabel(title, card)
        title_lb.setStyleSheet(
            f"color: {tc}; font-size: 15px; font-weight: 600; background: transparent;"
        )
        cl.addWidget(title_lb)

        # 消息
        msg_lb = QLabel(message, card)
        msg_lb.setWordWrap(True)
        msg_lb.setStyleSheet(
            f"color: {tcs}; font-size: 13px; background: transparent;"
        )
        cl.addWidget(msg_lb, 1)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        cancel_btn = QPushButton("取消", card)
        cancel_btn.setFixedSize(80, 32)
        cancel_btn.setStyleSheet(
            f"QPushButton {{ background: rgba(128,128,128,0.12); border: none; border-radius: 6px; "
            f"color: {tc}; font-size: 13px; }}"
            "QPushButton:hover { background: rgba(128,128,128,0.22); }"
        )
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        confirm_btn = QPushButton("确定", card)
        confirm_btn.setFixedSize(80, 32)
        confirm_btn.setStyleSheet(
            "QPushButton { background: rgba(98,160,234,0.2); border: none; border-radius: 6px; "
            f"color: #62a0ea; font-size: 13px; font-weight: 600; }}"
            "QPushButton:hover { background: rgba(98,160,234,0.35); }"
        )
        confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(confirm_btn)

        cl.addLayout(btn_row)
        root.addWidget(card)

    def _on_confirm(self):
        self._confirmed = True
        self.accept()

    @staticmethod
    def ask(title: str, message: str, parent=None) -> bool:
        dlg = _ConfirmDialog(title, message, parent)
        dlg.exec_()
        return dlg._confirmed


# ========================================================================
# 6. 可折叠区域控件
# ========================================================================


class _CollapsibleSection(QWidget):
    """可折叠的区块容器"""

    def __init__(self, title: str, count: int = 0, collapsed: bool = False, parent=None):
        super().__init__(parent)
        self._collapsed = collapsed
        self._title = title
        self._count = count
        self._content: Optional[QWidget] = None
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("background: transparent;")
        ly = QVBoxLayout(self)
        ly.setContentsMargins(0, 2, 0, 2)
        ly.setSpacing(0)

        # 头部（可点击）
        self._header = QWidget(self)
        self._header.setCursor(Qt.PointingHandCursor)
        self._header.setStyleSheet(
            "QWidget { background: transparent; }"
            "QWidget:hover { background: rgba(128,128,128,0.06); border-radius: 6px; }"
        )
        self._header.mousePressEvent = lambda e: self._toggle()
        hl = QHBoxLayout(self._header)
        hl.setContentsMargins(10, 7, 10, 7)
        hl.setSpacing(6)

        self._arrow_lb = QLabel("▶" if self._collapsed else "▼", self._header)
        self._arrow_lb.setFixedWidth(14)
        self._arrow_lb.setStyleSheet(
            f"background: transparent; color: {_text_color(secondary=True)}; font-size: 10px;"
        )
        hl.addWidget(self._arrow_lb)

        self._title_lb = StrongBodyLabel(
            f"{self._title} ({self._count})", self._header
        )
        self._title_lb.setStyleSheet(f"color: {_text_color()}; background: transparent;")
        hl.addWidget(self._title_lb)
        hl.addStretch(1)

        # 操作按钮容器（留给外部填充）
        self._action_widget = QWidget(self._header)
        self._action_widget.setStyleSheet("background: transparent;")
        self._action_layout = QHBoxLayout(self._action_widget)
        self._action_layout.setContentsMargins(0, 0, 0, 0)
        self._action_layout.setSpacing(4)
        hl.addWidget(self._action_widget)

        ly.addWidget(self._header)

        # 内容容器
        self._content_widget = QWidget(self)
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(4, 2, 4, 2)
        self._content_layout.setSpacing(0)
        self._content_widget.setVisible(not self._collapsed)
        ly.addWidget(self._content_widget)

    def _toggle(self):
        self._collapsed = not self._collapsed
        self._arrow_lb.setText("▶" if self._collapsed else "▼")
        self._content_widget.setVisible(not self._collapsed)

    def set_content(self, widget: QWidget):
        """设置内部内容控件"""
        self._content = widget
        self._content_layout.addWidget(widget)

    def set_count(self, count: int):
        self._count = count
        self._title_lb.setText(f"{self._title} ({count})")

    def add_action_button(self, btn: QWidget):
        self._action_layout.addWidget(btn)

    def content_layout(self) -> QVBoxLayout:
        return self._content_layout


# ========================================================================
# 7. Stash 行控件
# ========================================================================


class _StashRowWidget(QWidget):
    """单个 stash 条目"""

    action_requested = pyqtSignal(str, str)  # (action, ref)

    def __init__(self, stash_info: dict, parent=None):
        super().__init__(parent)
        self._info = stash_info
        self.setFixedHeight(32)
        self.setObjectName("StashRow")
        self.setStyleSheet(
            "#StashRow { background: transparent; }"
            "#StashRow:hover { background: rgba(128,128,128,0.06); border-radius: 4px; }"
        )
        ly = QHBoxLayout(self)
        ly.setContentsMargins(16, 0, 8, 0)
        ly.setSpacing(6)

        # 图标
        icon = QLabel("📦", self)
        icon.setFixedWidth(20)
        icon.setStyleSheet("background: transparent; font-size: 12px;")
        ly.addWidget(icon)

        # 描述
        msg_lb = QLabel(f"{stash_info['ref']}: {stash_info['message']}", self)
        msg_lb.setStyleSheet(
            f"background: transparent; color: {_text_color()}; font-size: 12px;"
        )
        msg_lb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        msg_lb.setWordWrap(True)
        ly.addWidget(msg_lb)

        # 应用
        apply_btn = QPushButton("应用", self)
        apply_btn.setFixedSize(40, 22)
        apply_btn.setStyleSheet(
            "QPushButton { background: rgba(98,160,234,0.15); border: none; border-radius: 4px; "
            f"color: {_text_color()}; font-size: 11px; padding: 0 4px; }}"
            "QPushButton:hover { background: rgba(98,160,234,0.3); }"
        )
        apply_btn.clicked.connect(lambda: self.action_requested.emit("apply", stash_info["ref"]))
        ly.addWidget(apply_btn)

        # 弹出
        pop_btn = QPushButton("弹出", self)
        pop_btn.setFixedSize(40, 22)
        pop_btn.setStyleSheet(
            "QPushButton { background: rgba(80,227,194,0.15); border: none; border-radius: 4px; "
            f"color: {_text_color()}; font-size: 11px; padding: 0 4px; }}"
            "QPushButton:hover { background: rgba(80,227,194,0.3); }"
        )
        pop_btn.clicked.connect(lambda: self.action_requested.emit("pop", stash_info["ref"]))
        ly.addWidget(pop_btn)

        # 删除
        del_btn = QPushButton("删除", self)
        del_btn.setFixedSize(40, 22)
        del_btn.setStyleSheet(
            "QPushButton { background: rgba(241,76,76,0.15); border: none; border-radius: 4px; "
            f"color: {_text_color()}; font-size: 11px; padding: 0 4px; }}"
            "QPushButton:hover { background: rgba(241,76,76,0.3); }"
        )
        del_btn.clicked.connect(lambda: self.action_requested.emit("drop", stash_info["ref"]))
        ly.addWidget(del_btn)


# ========================================================================
# 8. 分支行控件
# ========================================================================


class _BranchRowWidget(QWidget):
    """单个分支行"""

    switch_requested = pyqtSignal(str)  # branch_name
    delete_requested = pyqtSignal(str)  # branch_name

    def __init__(self, branch_info: dict, parent=None):
        super().__init__(parent)
        self._info = branch_info
        self.setFixedHeight(30)
        self.setObjectName("BranchRow")
        self.setStyleSheet(
            "#BranchRow { background: transparent; }"
            "#BranchRow:hover { background: rgba(128,128,128,0.06); border-radius: 4px; }"
        )
        ly = QHBoxLayout(self)
        ly.setContentsMargins(16, 0, 8, 0)
        ly.setSpacing(6)

        # 图标
        marker = "●" if branch_info["current"] else "○"
        marker_color = "#50e3c2" if branch_info["current"] else _text_color(secondary=True)
        icon = QLabel(marker, self)
        icon.setFixedWidth(14)
        icon.setStyleSheet(f"background: transparent; color: {marker_color}; font-size: 14px;")
        ly.addWidget(icon)

        # 分支名
        text = branch_info["name"]
        if branch_info["current"]:
            text += " (当前)"
        name_lb = QLabel(text, self)
        name_lb.setStyleSheet(
            f"background: transparent; color: {_text_color()}; font-size: 12px;"
        )
        if branch_info["current"]:
            name_lb.setStyleSheet(
                "background: transparent; color: #50e3c2; font-size: 12px; font-weight: 600;"
            )
        name_lb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        ly.addWidget(name_lb)

        # 切换按钮（非当前分支）
        if not branch_info["current"]:
            switch_btn = QPushButton("切换", self)
            switch_btn.setFixedSize(40, 22)
            switch_btn.setStyleSheet(
                "QPushButton { background: rgba(98,160,234,0.15); border: none; border-radius: 4px; "
                f"color: {_text_color()}; font-size: 11px; padding: 0 4px; }}"
                "QPushButton:hover { background: rgba(98,160,234,0.3); }"
            )
            switch_btn.clicked.connect(lambda: self.switch_requested.emit(branch_info["name"]))
            ly.addWidget(switch_btn)

            del_btn = QPushButton("删除", self)
            del_btn.setFixedSize(40, 22)
            del_btn.setStyleSheet(
                "QPushButton { background: rgba(241,76,76,0.15); border: none; border-radius: 4px; "
                f"color: {_text_color()}; font-size: 11px; padding: 0 4px; }}"
                "QPushButton:hover { background: rgba(241,76,76,0.3); }"
            )
            del_btn.clicked.connect(lambda: self.delete_requested.emit(branch_info["name"]))
            ly.addWidget(del_btn)


# ========================================================================
# 9. 提交历史行控件
# ========================================================================


class _CommitRowWidget(QWidget):
    """单个提交行"""

    def __init__(self, commit_info: dict, parent=None):
        super().__init__(parent)
        self._info = commit_info
        self.setFixedHeight(26)
        self.setObjectName("CommitRow")
        self.setStyleSheet(
            "#CommitRow { background: transparent; }"
            "#CommitRow:hover { background: rgba(128,128,128,0.06); border-radius: 4px; }"
        )
        ly = QHBoxLayout(self)
        ly.setContentsMargins(16, 0, 8, 0)
        ly.setSpacing(6)

        # 点
        dot = QLabel("*", self)
        dot.setFixedWidth(12)
        dot.setStyleSheet("background: transparent; color: #62a0ea; font-size: 12px;")
        ly.addWidget(dot)

        # Hash
        hash_lb = QLabel(commit_info["hash"], self)
        hash_lb.setStyleSheet(
            "background: transparent; color: #62a0ea; font-size: 11px; font-family: 'Consolas', monospace;"
        )
        hash_lb.setFixedWidth(80)
        ly.addWidget(hash_lb)

        # 日期
        date_lb = QLabel(commit_info["date"], self)
        date_lb.setStyleSheet(
            f"background: transparent; color: {_text_color(secondary=True)}; font-size: 11px;"
        )
        date_lb.setFixedWidth(80)
        ly.addWidget(date_lb)

        # 提交信息
        subject_lb = QLabel(commit_info["subject"], self)
        subject_lb.setStyleSheet(
            f"background: transparent; color: {_text_color()}; font-size: 12px;"
        )
        subject_lb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        ly.addWidget(subject_lb)

        # Ref 标签
        refs = commit_info.get("refs", "")
        if refs:
            ref_lb = QLabel(refs, self)
            ref_lb.setStyleSheet(
                "background: rgba(98,160,234,0.12); color: #62a0ea; "
                "font-size: 10px; padding: 1px 4px; border-radius: 3px;"
            )
            ly.addWidget(ref_lb)


# ========================================================================
# 10. GitPanelCard 主卡片
# ========================================================================


class GitPanelCard(QWidget):
    """Git 控制面板浮动卡片"""

    closed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._context_provider: Optional[Callable[[], dict]] = None
        self._repo_path: str = ""
        self._is_loading = False
        self._worker_thread: Optional[QThread] = None
        self._worker: Optional[_Worker] = None

        # 缓存上下文
        self._cached_tc = _text_color()
        self._cached_tcs = _text_color(secondary=True)
        self._cached_border = "rgba(128,128,128,0.15)"
        self._cached_ff = "Microsoft YaHei"
        self._cached_fs = 14

        self._setup_ui()

    # ── 上下文注入 ──

    def set_context_provider(self, provider: Callable[[], dict]):
        self._context_provider = provider

    def show_card(self):
        self._apply_latest_theme()
        self._async_refresh()
        self.setVisible(True)

    def _apply_latest_theme(self):
        if self._context_provider is None:
            return
        try:
            ctx = self._context_provider()
        except Exception:
            return
        font_family, font_size = _ctx_font(ctx)
        tc = _ctx_text_color(ctx)
        tcs = _ctx_text_color(ctx, secondary=True)
        border_c = _ctx_border_color(ctx)
        self._cached_tc = tc
        self._cached_tcs = tcs
        self._cached_border = border_c
        self._cached_ff = font_family
        self._cached_fs = font_size

        if font_family:
            self.setFont(QFont(font_family, font_size if font_size else 14))

        self._retheme()

        # 从上下文获取 repo_path
        self._repo_path = ctx.get("project_root", "")

        # 更新 header 样式
        self._header_widget.setStyleSheet("background: transparent;")

    def _retheme(self):
        tc = self._cached_tc
        ff = self._cached_ff
        fs = self._cached_fs
        tcs = self._cached_tcs
        border_c = self._cached_border

        # 卡片背景
        colors = _resolve_colors()
        bg = colors.get("card_bg", "rgba(33,33,38,240)")
        if isinstance(bg, str):
            bg_rgba = bg
        else:
            bg_rgba = f"rgba({bg.red()}, {bg.green()}, {bg.blue()}, {bg.alpha()})"
        self._content_widget.setStyleSheet(f"""
            QWidget#cardContent {{
                background: {bg_rgba};
                border: 1px solid {border_c};
                border-radius: 12px;
            }}
        """)

        # 分隔线
        self._separator.setStyleSheet(
            f"QFrame {{ border: none; border-top: 1px solid {border_c}; margin: 0; max-height: 1px; }}"
        )

        # 标题
        self._title_lb.setStyleSheet(
            f"color: {tc}; background: transparent; font-weight: 600; "
            f"font-family: '{ff}'; font-size: {fs}px;"
        )

        # 分支标签
        self._branch_lb.setStyleSheet(
            f"background: transparent; color: {tcs}; font-family: '{ff}'; font-size: {fs - 2}px;"
        )

        # 状态标签
        self._status_lb.setStyleSheet(
            f"background: transparent; color: {tcs}; font-family: '{ff}'; font-size: {fs - 2}px;"
        )

        # 提交输入框
        self._commit_input.setStyleSheet(
            "QLineEdit { background: rgba(128,128,128,0.08); border: 1px solid rgba(128,128,128,0.15); "
            "border-radius: 6px; padding: 7px 10px; "
            f"color: {tc}; font-family: '{ff}'; font-size: {fs - 1}px; }}"
            "QLineEdit:focus { border-color: #62a0ea; }"
        )

        # 提交按钮
        self._commit_btn.setStyleSheet(
            f"QPushButton {{ background: rgba(98,160,234,0.18); border: none; border-radius: 5px; "
            f"color: {tc}; font-family: '{ff}'; font-size: {fs - 2}px; padding: 5px 14px; }}"
            "QPushButton:hover { background: rgba(98,160,234,0.3); }"
            "QPushButton:pressed { background: rgba(98,160,234,0.4); }"
        )

        # Amend 按钮
        btn_base = (
            f"QPushButton {{ background: rgba(128,128,128,0.1); border: none; border-radius: 5px; "
            f"color: {tc}; font-family: '{ff}'; font-size: {fs - 3}px; padding: 4px 10px; }}"
            "QPushButton:hover { background: rgba(128,128,128,0.2); }"
            "QPushButton:pressed { background: rgba(128,128,128,0.3); }"
        )
        self._amend_btn.setStyleSheet(btn_base)
        if hasattr(self, '_stash_btn'):
            self._stash_btn.setStyleSheet(btn_base)
        if hasattr(self, '_new_branch_btn'):
            self._new_branch_btn.setStyleSheet(btn_base)

        # 滚动条
        sh_hex = "rgba(255,255,255,0.12)" if isDarkTheme() else "rgba(0,0,0,0.12)"
        sh_hover = "rgba(255,255,255,0.22)" if isDarkTheme() else "rgba(0,0,0,0.22)"
        self._scroll.setStyleSheet(
            "ScrollArea { background: transparent; border: none; }"
            "ScrollArea > QWidget > QWidget { background: transparent; }"
            f"QScrollBar:vertical {{ width: 6px; background: transparent; }}"
            f"QScrollBar::handle:vertical {{ background: {sh_hex}; border-radius: 3px; min-height: 30px; }}"
            f"QScrollBar::handle:vertical:hover {{ background: {sh_hover}; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

        # Labels 样式更新
        for child in self.findChildren(QLabel):
            try:
                from qfluentwidgets import FluentLabelBase
                if isinstance(child, FluentLabelBase) and ff:
                    child.setFont(QFont(ff, fs))

                ss = child.styleSheet()
                if not ss:
                    continue
                new_ss = re.sub(r"color:\s*[^;]+;", f"color: {tc};", ss)
                if fs:
                    new_ss = re.sub(r"font-size:\s*[^;]+;", f"font-size: {fs}px;", new_ss)
                if ff and f"font-family: '{ff}'" not in new_ss:
                    new_ss += f" font-family: '{ff}';"
                child.setStyleSheet(new_ss)
            except RuntimeError:
                pass

    # ── 界面 ──

    def _setup_ui(self):
        self.setMinimumHeight(0)
        self.setAttribute(Qt.WA_StyledBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 卡片背景容器
        self._content_widget = QWidget(self)
        self._content_widget.setObjectName("cardContent")
        content = QVBoxLayout(self._content_widget)
        content.setContentsMargins(16, 12, 16, 12)
        content.setSpacing(0)

        self._build_header(content)

        # 分隔线
        self._separator = QFrame(self)
        self._separator.setFrameShape(QFrame.HLine)
        self._separator.setFrameShadow(QFrame.Sunken)
        self._separator.setMaximumHeight(1)
        content.addWidget(self._separator)

        self._build_toolbar(content)
        self._build_body(content)
        self._build_empty_state(content)

        root.addWidget(self._content_widget)

    def _build_header(self, root: QVBoxLayout):
        """头部：图标 + 标题 + 分支信息 + 操作按钮"""
        self._header_widget = QWidget(self)
        self._header_widget.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(self._header_widget)
        hl.setContentsMargins(16, 10, 16, 6)
        hl.setSpacing(8)

        # Git 图标
        self._repo_icon = QLabel("🔀", self._header_widget)
        self._repo_icon.setFixedSize(22, 22)
        self._repo_icon.setStyleSheet("background: transparent; font-size: 18px;")
        hl.addWidget(self._repo_icon)

        # 标题
        self._title_lb = StrongBodyLabel("Git 面板", self._header_widget)
        self._title_lb.setStyleSheet(f"color: {self._cached_tc}; background: transparent; font-weight: 600;")
        hl.addWidget(self._title_lb)

        # 分支名
        self._branch_lb = QLabel("", self._header_widget)
        self._branch_lb.setStyleSheet(
            f"background: transparent; color: {_text_color(secondary=True)}; font-size: 12px;"
        )
        hl.addWidget(self._branch_lb)

        hl.addStretch(1)

        # 状态
        self._status_lb = QLabel("", self._header_widget)
        self._status_lb.setStyleSheet(
            f"background: transparent; color: {self._cached_tcs}; font-size: 12px;"
        )
        hl.addWidget(self._status_lb)

        # 刷新
        self._refresh_btn = ToolButton(FluentIcon.SYNC, self._header_widget)
        self._refresh_btn.setFixedSize(28, 28)
        self._refresh_btn.setToolTip("刷新")
        self._refresh_btn.clicked.connect(self._async_refresh)
        hl.addWidget(self._refresh_btn)

        # 关闭
        close_btn = TransparentToolButton(FluentIcon.CLOSE, self._header_widget)
        close_btn.setFixedSize(28, 28)
        close_btn.setToolTip("关闭")
        close_btn.clicked.connect(self._on_close)
        hl.addWidget(close_btn)

        root.addWidget(self._header_widget)

    def _build_toolbar(self, root: QVBoxLayout):
        """工具栏：提交消息输入 + 提交 / Stash / 新建分支"""
        tb = QWidget(self)
        tb.setStyleSheet("background: transparent;")
        tly = QHBoxLayout(tb)
        tly.setContentsMargins(0, 8, 0, 6)
        tly.setSpacing(6)

        # 提交消息输入
        self._commit_input = QLineEdit(tb)
        self._commit_input.setPlaceholderText("提交描述...")
        self._commit_input.setMinimumHeight(30)
        self._commit_input.returnPressed.connect(self._on_commit)
        tly.addWidget(self._commit_input, 1)

        # 提交按钮
        self._commit_btn = PrimaryPushButton("提交", tb)
        self._commit_btn.setFixedHeight(30)
        self._commit_btn.clicked.connect(self._on_commit)
        tly.addWidget(self._commit_btn)

        # Amend 按钮
        self._amend_btn = QPushButton("Amend", tb)
        self._amend_btn.setFixedSize(52, 28)
        self._amend_btn.setToolTip("修改上次提交（--amend）")
        self._amend_btn.setCursor(Qt.PointingHandCursor)
        self._amend_btn.clicked.connect(self._on_amend)
        tly.addWidget(self._amend_btn)

        # Stash 按钮
        self._stash_btn = QPushButton("↻ Stash", tb)
        self._stash_btn.setFixedHeight(28)
        self._stash_btn.setCursor(Qt.PointingHandCursor)
        self._stash_btn.setToolTip("保存当前工作进度")
        self._stash_btn.clicked.connect(self._on_stash)
        tly.addWidget(self._stash_btn)

        # 新建分支按钮
        self._new_branch_btn = QPushButton("🌿 新建分支", tb)
        self._new_branch_btn.setFixedHeight(28)
        self._new_branch_btn.setCursor(Qt.PointingHandCursor)
        self._new_branch_btn.setToolTip("创建并切换到新分支")
        self._new_branch_btn.clicked.connect(self._on_create_branch)
        tly.addWidget(self._new_branch_btn)

        root.addWidget(tb)

    def _build_body(self, root: QVBoxLayout):
        """主体内容：滚动区域内的所有区块"""
        self._scroll = ScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._content = QWidget(self._scroll)
        self._content.setStyleSheet("background: transparent;")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 4, 0, 4)
        self._content_layout.setSpacing(6)
        self._content_layout.setAlignment(Qt.AlignTop)
        self._scroll.setWidget(self._content)
        root.addWidget(self._scroll, 1)

    def _build_empty_state(self, root: QVBoxLayout):
        """空状态提示"""
        self._empty = QLabel("输入命令 /git-panel 打开 Git 控制面板", self)
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setStyleSheet(
            f"color: {_text_color(secondary=True)}; background: transparent; "
            "font-size: 13px; padding: 40px;"
        )
        self._empty.setVisible(False)
        root.addWidget(self._empty)

    # ── 比例高度 ──

    def sizeHint(self):
        from PyQt5.QtCore import QSize
        base = super().sizeHint()
        win = self.window()
        if win and win.height() > 0:
            return QSize(max(base.width(), 200), int(win.height() * 0.85))
        return base

    def showEvent(self, event):
        super().showEvent(event)
        win = self.window()
        if win:
            win.installEventFilter(self)
            self.updateGeometry()

    def eventFilter(self, obj, event):
        from PyQt5.QtCore import QEvent
        if obj is self.window() and event.type() == QEvent.Resize:
            self.updateGeometry()
        return super().eventFilter(obj, event)

    # ── 异步刷新 ──

    def _async_refresh(self):
        """后台获取所有 Git 数据"""
        self._set_loading(True)
        self._cleanup_worker()

        w = _Worker(self._fetch_all_data)
        t = QThread(self)
        w.moveToThread(t)
        t.started.connect(w.run)
        w.finished.connect(self._on_refresh_done)
        w.error.connect(self._on_refresh_error)
        w.finished.connect(t.quit)
        w.error.connect(t.quit)
        w.finished.connect(w.deleteLater)
        w.error.connect(w.deleteLater)
        t.finished.connect(t.deleteLater)
        self._worker, self._worker_thread = w, t
        t.start()

    def _fetch_all_data(self) -> dict:
        """同步函数：后台线程执行，收集所有 Git 信息"""
        repo = self._repo_path
        if not repo:
            return {"error": "未获取到项目路径"}
        if not _is_git_repo(repo):
            return {"error": "当前项目不是 Git 仓库"}

        branch = _get_branch(repo)
        ahead, behind = _get_ahead_behind(repo)
        status = _get_status(repo)
        stashes = _get_stashes(repo)
        branches = _get_branches(repo)
        log = _get_log(repo)

        return {
            "branch": branch,
            "ahead": ahead,
            "behind": behind,
            "status": status,
            "stashes": stashes,
            "branches": branches,
            "log": log,
        }

    def _on_refresh_done(self, data: dict):
        self._set_loading(False)

        if data.get("error"):
            self._empty.setText(data["error"])
            self._empty.setVisible(True)
            self._status_lb.setText("")
            self._branch_lb.setText("")
            self._content.setVisible(False)
            return

        self._empty.setVisible(False)
        self._content.setVisible(True)
        self._render_content(data)

    def _on_refresh_error(self, err: str):
        self._set_loading(False)
        self._empty.setText(f"加载失败: {err[:80]}")
        self._empty.setVisible(True)
        self._content.setVisible(False)
        logger.error(f"[git-panel] 数据加载失败: {err}")

    def _set_loading(self, loading: bool):
        self._is_loading = loading
        self._refresh_btn.setEnabled(not loading)
        if loading:
            self._status_lb.setText("加载中…")
        else:
            self._status_lb.setText("")

    # ── 渲染内容 ──

    def _render_content(self, data: dict):
        """渲染所有区块到内容区"""
        # 清空旧内容
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 更新头部
        branch = data.get("branch", "")
        ahead = data.get("ahead", 0)
        behind = data.get("behind", 0)
        bt = branch
        if ahead or behind:
            bt += f"  ↑{ahead}  ↓{behind}"
        self._branch_lb.setText(bt)

        self._commit_input.setText("")

        # ── 1. 文件变更 ──
        status_items = data.get("status", [])
        staged = [s for s in status_items if s["staged"]]
        unstaged = [s for s in status_items if not s["staged"]]
        total_changes = len(staged) + len(unstaged)

        changes_section = _CollapsibleSection(
            "变更", count=total_changes, collapsed=False
        )
        changes_content = QWidget()
        changes_content.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(changes_content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        # 全部暂存/全部取消暂存按钮
        if total_changes > 0:
            action_bar = self._make_changes_action_bar(staged, unstaged)
            cl.addWidget(action_bar)

        # 已暂存标题
        if staged:
            staged_title = QLabel(f"  ─ 已暂存 ({len(staged)})", changes_content)
            staged_title.setStyleSheet(
                "background: transparent; color: #50e3c2; font-size: 11px; "
                "padding: 4px 12px;"
            )
            cl.addWidget(staged_title)
            for item in staged:
                row = _FileRowWidget(item)
                row._repo_path = self._repo_path
                row.staged_changed.connect(self._async_refresh)
                row.diff_requested.connect(self._on_diff_request)
                cl.addWidget(row)

        # 未暂存标题
        if unstaged:
            unstaged_title = QLabel(f"  ─ 未暂存 ({len(unstaged)})", changes_content)
            unstaged_title.setStyleSheet(
                f"background: transparent; color: {self._cached_tcs}; font-size: 11px; "
                "padding: 4px 12px;"
            )
            cl.addWidget(unstaged_title)
            for item in unstaged:
                row = _FileRowWidget(item)
                row._repo_path = self._repo_path
                row.staged_changed.connect(self._async_refresh)
                row.diff_requested.connect(self._on_diff_request)
                cl.addWidget(row)

        if total_changes == 0:
            no_changes = QLabel("  工作区干净，无变更", changes_content)
            no_changes.setStyleSheet(
                f"background: transparent; color: {self._cached_tcs}; font-size: 12px; "
                "padding: 12px 16px;"
            )
            cl.addWidget(no_changes)

        changes_section.set_content(changes_content)
        self._content_layout.addWidget(changes_section)

        # ── 2. Stash ──
        stashes = data.get("stashes", [])
        stash_section = _CollapsibleSection(
            "Stash", count=len(stashes), collapsed=False
        )
        stash_content = QWidget()
        stash_content.setStyleSheet("background: transparent;")
        sl = QVBoxLayout(stash_content)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)

        if stashes:
            for item in stashes:
                row = _StashRowWidget(item)
                row.action_requested.connect(self._on_stash_action)
                sl.addWidget(row)
        else:
            no_stash = QLabel("  无 stash", stash_content)
            no_stash.setStyleSheet(
                f"background: transparent; color: {self._cached_tcs}; font-size: 12px; "
                "padding: 12px 16px;"
            )
            sl.addWidget(no_stash)

        stash_section.set_content(stash_content)
        self._content_layout.addWidget(stash_section)

        # ── 3. 分支 ──
        branches = data.get("branches", [])
        branch_section = _CollapsibleSection(
            "分支", count=len(branches), collapsed=False
        )
        branch_content = QWidget()
        branch_content.setStyleSheet("background: transparent;")
        bl = QVBoxLayout(branch_content)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)

        if branches:
            for item in branches:
                row = _BranchRowWidget(item)
                row.switch_requested.connect(self._on_switch_branch)
                row.delete_requested.connect(self._on_delete_branch)
                bl.addWidget(row)
        else:
            no_branch = QLabel("  无分支", branch_content)
            no_branch.setStyleSheet(
                f"background: transparent; color: {self._cached_tcs}; font-size: 12px; "
                "padding: 12px 16px;"
            )
            bl.addWidget(no_branch)

        branch_section.set_content(branch_content)
        self._content_layout.addWidget(branch_section)

        # ── 4. 提交历史 ──
        log = data.get("log", [])
        log_section = _CollapsibleSection(
            "提交历史", count=len(log), collapsed=True
        )
        log_content = QWidget()
        log_content.setStyleSheet("background: transparent;")
        ll = QVBoxLayout(log_content)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)

        if log:
            for item in log:
                row = _CommitRowWidget(item)
                ll.addWidget(row)
        else:
            no_log = QLabel("  无提交记录", log_content)
            no_log.setStyleSheet(
                f"background: transparent; color: {self._cached_tcs}; font-size: 12px; "
                "padding: 12px 16px;"
            )
            ll.addWidget(no_log)

        log_section.set_content(log_content)
        self._content_layout.addWidget(log_section)

        # 刷新主题
        self._apply_latest_theme()

    def _make_changes_action_bar(self, staged: list, unstaged: list) -> QWidget:
        """创建变更区域的操作栏"""
        bar = QWidget()
        bar.setStyleSheet("background: transparent;")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(12, 4, 8, 4)
        bl.setSpacing(6)

        if unstaged:
            stage_all_btn = QPushButton("全部暂存", bar)
            stage_all_btn.setFixedHeight(24)
            stage_all_btn.setStyleSheet(
                "QPushButton { background: rgba(80,227,194,0.12); border: none; border-radius: 4px; "
                f"color: {self._cached_tc}; font-size: 11px; padding: 0 10px; }}"
                "QPushButton:hover { background: rgba(80,227,194,0.25); }"
            )
            stage_all_btn.clicked.connect(self._on_stage_all)
            bl.addWidget(stage_all_btn)

        if staged:
            unstage_all_btn = QPushButton("全部取消暂存", bar)
            unstage_all_btn.setFixedHeight(24)
            unstage_all_btn.setStyleSheet(
                "QPushButton { background: rgba(241,76,76,0.12); border: none; border-radius: 4px; "
                f"color: {self._cached_tc}; font-size: 11px; padding: 0 10px; }}"
                "QPushButton:hover { background: rgba(241,76,76,0.25); }"
            )
            unstage_all_btn.clicked.connect(self._on_unstage_all)
            bl.addWidget(unstage_all_btn)

            discard_all_btn = QPushButton("放弃所有修改", bar)
            discard_all_btn.setFixedHeight(24)
            discard_all_btn.setStyleSheet(
                "QPushButton { background: rgba(241,76,76,0.08); border: none; border-radius: 4px; "
                f"color: {self._cached_tcs}; font-size: 11px; padding: 0 10px; }}"
                "QPushButton:hover { background: rgba(241,76,76,0.2); }"
            )
            discard_all_btn.clicked.connect(self._on_discard_all)
            bl.addWidget(discard_all_btn)

        bl.addStretch(1)
        return bar

    # ── Git 操作 ──

    def _on_commit(self):
        """执行提交"""
        msg = self._commit_input.text().strip()
        if not msg:
            self._status_lb.setText("提交信息不能为空")
            QTimer.singleShot(3000, lambda: self._reset_status())
            return
        self._status_lb.setText("提交中…")
        self._run_git_async(
            lambda: _run_git(self._repo_path, "commit", "-m", msg),
            lambda: self._on_commit_done(),
        )

    def _on_amend(self):
        """修改上次提交"""
        msg = self._commit_input.text().strip()
        args = ["commit", "--amend", "--no-edit"]
        if msg:
            args = ["commit", "--amend", "-m", msg]
        if not _ConfirmDialog.ask("确认 Amend", "确定要修改上次提交吗？", self):
            return
        self._status_lb.setText("Amend 中…")
        self._run_git_async(
            lambda: _run_git(self._repo_path, *args),
            lambda: self._on_commit_done(),
        )

    def _on_commit_done(self, result: Optional[Tuple[str, str, int]] = None):
        if result:
            stdout, stderr, code = result
            if code == 0:
                self._status_lb.setText("✅ 提交成功")
            else:
                self._status_lb.setText(f"❌ 提交失败: {stderr[:50]}")
                QTimer.singleShot(3000, lambda: self._reset_status())
                return
        else:
            self._status_lb.setText("✅ 提交成功")
        self._commit_input.setText("")
        QTimer.singleShot(1000, self._async_refresh)

    def _on_stash(self):
        """创建 stash"""
        msg = self._commit_input.text().strip() or "WIP"
        if not _ConfirmDialog.ask("确认 Stash", f"确定要 stash 当前修改吗？\n消息: {msg}", self):
            return
        self._status_lb.setText("Stash 中…")
        self._run_git_async(
            lambda: _run_git(self._repo_path, "stash", "push", "-m", msg),
            lambda r: self._on_op_done("Stash 成功", r),
        )

    def _on_stash_action(self, action: str, ref: str):
        """处理 stash 操作"""
        if action == "drop":
            if not _ConfirmDialog.ask("确认删除 Stash", f"确定要删除 {ref} 吗？", self):
                return
        elif action == "pop":
            if not _ConfirmDialog.ask("确认弹出 Stash", f"确定要弹出 {ref} 吗？\n此操作会应用并删除该 stash。", self):
                return
        self._status_lb.setText(f"{action} {ref}…")
        cmd = ["stash", action, ref]
        self._run_git_async(
            lambda: _run_git(self._repo_path, *cmd),
            lambda r: self._on_op_done(f"{action.capitalize()} 成功", r),
        )

    def _on_switch_branch(self, name: str):
        """切换分支"""
        self._status_lb.setText(f"切换到 {name}…")
        self._run_git_async(
            lambda: _run_git(self._repo_path, "checkout", name),
            lambda r: self._on_op_done(f"已切换到 {name}", r),
        )

    def _on_delete_branch(self, name: str):
        """删除分支"""
        if not _ConfirmDialog.ask("确认删除分支", f"确定要删除分支「{name}」吗？", self):
            return
        self._status_lb.setText(f"删除 {name}…")
        self._run_git_async(
            lambda: _run_git(self._repo_path, "branch", "-d", name),
            lambda r: self._on_op_done(f"已删除 {name}", r),
        )

    def _on_create_branch(self):
        """创建新分支"""
        name, ok = QInputDialog.getText(self, "新建分支", "输入分支名:")
        if not ok or not name.strip():
            return
        branch_name = name.strip()
        self._status_lb.setText(f"创建分支 {branch_name}…")
        self._run_git_async(
            lambda: _run_git(self._repo_path, "checkout", "-b", branch_name),
            lambda r: self._on_op_done(f"已创建并切换到 {branch_name}", r),
        )

    def _on_stage_all(self):
        """全部暂存"""
        self._status_lb.setText("暂存中…")
        self._run_git_async(
            lambda: _run_git(self._repo_path, "add", "-A"),
            lambda r: self._on_op_done("已暂存所有修改", r),
        )

    def _on_unstage_all(self):
        """全部取消暂存"""
        self._status_lb.setText("取消暂存中…")
        self._run_git_async(
            lambda: _run_git(self._repo_path, "restore", "--staged", "."),
            lambda r: self._on_op_done("已取消暂存所有修改", r),
        )

    def _on_discard_all(self):
        """放弃所有修改"""
        if not _ConfirmDialog.ask("确认放弃所有修改", "确定要放弃所有工作区修改吗？\n此操作不可恢复！", self):
            return
        self._status_lb.setText("放弃中…")
        self._run_git_async(
            lambda: _run_git(self._repo_path, "checkout", "--", "."),
            lambda r: self._on_op_done("已放弃所有修改", r),
        )

    def _on_diff_request(self, path: str, staged: bool):
        """打开 Diff 预览对话框"""
        dialog = _DiffDialog(self._repo_path, path, staged, self)
        dialog.exec_()

    def _on_op_done(self, msg: str, result: Optional[Tuple[str, str, int]] = None):
        """操作完成后的公共处理，检查 git 返回码"""
        if result:
            _, stderr, code = result
            if code != 0:
                err_msg = stderr[:80] if stderr else "未知错误"
                self._status_lb.setText(f"❌ 失败: {err_msg}")
                QTimer.singleShot(4000, lambda: self._reset_status())
                return
        self._status_lb.setText(f"✅ {msg}")
        QTimer.singleShot(2000, lambda: self._reset_status())
        QTimer.singleShot(300, self._async_refresh)

    def _reset_status(self):
        if not self._is_loading:
            self._status_lb.setText("")

    def _run_git_async(self, fn, on_done):
        """在后台线程执行一个 git 操作"""
        if self._is_loading:
            return
        self._cleanup_worker()

        w = _Worker(fn)
        t = QThread(self)
        w.moveToThread(t)
        t.started.connect(w.run)
        w.finished.connect(on_done)
        w.error.connect(self._on_refresh_error)
        w.finished.connect(t.quit)
        w.error.connect(t.quit)
        w.finished.connect(w.deleteLater)
        w.error.connect(w.deleteLater)
        t.finished.connect(t.deleteLater)
        self._worker, self._worker_thread = w, t
        t.start()

    # ── 关闭 ──

    def _on_close(self):
        self.setVisible(False)
        self.closed.emit()

    def _cleanup_worker(self):
        if self._worker_thread is not None:
            try:
                self._worker_thread.quit()
                self._worker_thread.wait(500)
            except RuntimeError:
                pass
            self._worker_thread = None
        self._worker = None

    def deleteLater(self):
        self._cleanup_worker()
        super().deleteLater()
