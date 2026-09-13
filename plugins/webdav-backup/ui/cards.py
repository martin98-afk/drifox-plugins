# -*- coding: utf-8 -*-
"""webdav-backup 卡片组件 — 备份中心卡（full 覆盖对话区）

布局参考 cron-tasks / autoloop cards.py（design_tokens 配色 + ElevatedCardWidget 分组）。
线程纪律：所有网络/文件 IO 经 QThread + _Worker(QObject)，信号 queued 回主线程渲染；
worker 内禁止触碰任何 UI 对象。
"""

from __future__ import annotations

import traceback
from datetime import datetime
from typing import Any, Callable, List, Optional

from loguru import logger
from PyQt5.QtCore import QObject, QThread, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import (
    CaptionLabel,
    CheckBox,
    ElevatedCardWidget,
    FluentIcon,
    IconWidget,
    LineEdit,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    TransparentToolButton,
    isDarkTheme,
)
from qfluentwidgets.components.widgets.card_widget import CardSeparator

from webdavbackup_core import config as cfg_mod
from webdavbackup_core import engine

# 主程序设计令牌缺失时回退到硬编码主题色（插件自包含保证）
try:
    from app.utils.design_tokens import Colors, font_size_css
except Exception:
    Colors = None

    def font_size_css(px: int) -> str:  # type: ignore[misc]
        return f"font-size: {px}px;"


try:
    from app.utils.utils import get_font_family_css
except Exception:
    def get_font_family_css() -> str:  # type: ignore[misc]
        return "font-family: 'Microsoft YaHei';"


def _color(name: str, light: str, dark: str = "") -> str:
    """取设计令牌色；不可用时按当前主题返回硬编码色"""
    if Colors is not None:
        return getattr(Colors, name)
    return dark if (dark and isDarkTheme()) else light


FONT_CSS = get_font_family_css()


# ============================================================
#  样式辅助
# ============================================================


def _hero_title_css() -> str:
    return f"color: {_color('TEXT_PRIMARY', 'rgba(0,0,0,0.9)', 'rgba(255,255,255,0.9)')}; {font_size_css(20)} {FONT_CSS}; font-weight: 600;"


def _section_title_css() -> str:
    return f"color: {_color('TEXT_PRIMARY', 'rgba(0,0,0,0.9)', 'rgba(255,255,255,0.9)')}; {font_size_css(13)} {FONT_CSS}; font-weight: 600;"


def _caption_css() -> str:
    return f"color: {_color('TEXT_SECONDARY', 'rgba(0,0,0,0.55)', 'rgba(255,255,255,0.6)')}; {font_size_css(12)} {FONT_CSS};"


def _name_css() -> str:
    return f"color: {_color('TEXT_PRIMARY', 'rgba(0,0,0,0.9)', 'rgba(255,255,255,0.9)')}; {font_size_css(13)} {FONT_CSS};"


def _make_section_card() -> ElevatedCardWidget:
    card = ElevatedCardWidget()
    card.setBorderRadius(12)
    return card


def _format_size(n: int) -> str:
    if n >= 1048576:
        return f"{n / 1048576:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


def _format_time(iso: str) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso.replace("T", " ")[:16]


# ============================================================
#  异步 Worker（QObject + QThread 范式；信号跨线程自动 queued）
# ============================================================


class _Worker(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, fn: Callable[[], Any], parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            self.finished.emit(self._fn())
        except Exception as e:  # 兜底：engine 层已屏障，此处防御未来回归
            logger.error(f"[webdav-backup] worker 异常: {e}\n{traceback.format_exc()}")
            self.error.emit(str(e))


# ============================================================
#  云端备份行
# ============================================================


class CloudFileRow(QFrame):
    """单条云端备份：文件名 + 大小/时间 + 恢复/删除（两段式内联确认）"""

    restore_clicked = pyqtSignal(str)
    delete_clicked = pyqtSignal(str)

    _CONFIRM_MS = 3000

    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self._name: str = item.get("name", "")
        self._confirming: Optional[str] = None  # "restore" | "delete"
        self._confirm_timer = QTimer(self)
        self._confirm_timer.setSingleShot(True)
        self._confirm_timer.timeout.connect(self._reset_buttons)

        self.setStyleSheet("QFrame { background: transparent; }")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 6, 4, 6)
        lay.setSpacing(8)

        info = QVBoxLayout()
        info.setSpacing(2)
        name = QLabel(self._name)
        name.setStyleSheet(_name_css())
        meta_parts = []
        if item.get("size"):
            meta_parts.append(_format_size(int(item["size"])))
        if item.get("modified"):
            meta_parts.append(_format_time(str(item["modified"])))
        meta = QLabel(" · ".join(meta_parts) if meta_parts else "")
        meta.setStyleSheet(_caption_css())
        info.addWidget(name)
        if meta_parts:
            info.addWidget(meta)
        lay.addLayout(info, 1)

        self._restore_btn = PushButton("恢复")
        self._restore_btn.setFixedHeight(30)
        self._restore_btn.clicked.connect(lambda: self._on_restore())
        lay.addWidget(self._restore_btn, 0, Qt.AlignVCenter)

        self._delete_btn = TransparentToolButton(FluentIcon.DELETE)
        self._delete_btn.setToolTip("删除此备份")
        self._delete_btn.setFixedSize(30, 30)
        self._delete_btn.clicked.connect(lambda: self._on_delete())
        lay.addWidget(self._delete_btn, 0, Qt.AlignVCenter)

    # ── 两段式确认 ──────────────────────────────────────

    def _on_restore(self):
        if self._confirming == "restore":
            self._confirming = None
            self._reset_buttons()
            self.restore_clicked.emit(self._name)
            return
        self._confirming = "restore"
        self._restore_btn.setText("确认恢复？")
        self._delete_btn.setEnabled(False)
        self._confirm_timer.start(self._CONFIRM_MS)

    def _on_delete(self):
        if self._confirming == "delete":
            self._confirming = None
            self._reset_buttons()
            self.delete_clicked.emit(self._name)
            return
        self._confirming = "delete"
        self._restore_btn.setEnabled(False)
        self._delete_btn.setToolTip("再次点击确认删除")
        self._delete_btn.setStyleSheet(
            f"TransparentToolButton {{ background: {_color('ERROR', '#ef4444', '#ef4444')}; border-radius: 4px; }}"
        )
        self._confirm_timer.start(self._CONFIRM_MS)

    def _reset_buttons(self):
        self._confirming = None
        self._restore_btn.setText("恢复")
        self._restore_btn.setEnabled(True)
        self._delete_btn.setEnabled(True)
        self._delete_btn.setToolTip("删除此备份")
        self._delete_btn.setStyleSheet("")

    def set_busy(self, busy: bool):
        self._confirm_timer.stop()
        self._restore_btn.setEnabled(not busy)
        self._delete_btn.setEnabled(not busy)
        if not busy:
            self._reset_buttons()


# ============================================================
#  主卡片
# ============================================================


class WebDavBackupCard(QFrame):
    """WebDAV 备份中心卡"""

    closed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._context_provider: Optional[Callable[[], dict]] = None
        self._thread: Optional[QThread] = None
        self._worker: Optional[_Worker] = None
        self._busy = False
        self._rows: List[CloudFileRow] = []
        self._scheduler_connected = False

        self._setup_ui()
        self._refresh_info_only()

    # ── 上下文注入（由 UIPluginRegistry 调用） ──────────

    def set_context_provider(self, provider: Callable[[], dict]):
        self._context_provider = provider

    def show_card(self):
        self._apply_plugin_icon()
        if not self._scheduler_connected:
            try:
                from webdavbackup_core.scheduler import BackupScheduler

                BackupScheduler.get_instance().backup_finished.connect(self._on_scheduler_result)
                self._scheduler_connected = True
            except Exception as e:
                logger.warning(f"[webdav-backup] 连接调度器信号失败: {e}")
        self._refresh_scope_ui()
        self.refresh_all()
        self.setVisible(True)

    def _apply_plugin_icon(self):
        if self._context_provider is None or self._header_icon is None:
            return
        try:
            ctx = self._context_provider()
            icon_info = ctx.get("plugin_icon", {})
            theme = "dark" if isDarkTheme() else "light"
            icon_path = icon_info.get(theme, "")
            if icon_path:
                self._header_icon.setIcon(QIcon(icon_path))
        except Exception:
            pass

    # ── 界面搭建 ────────────────────────────────────────

    def _setup_ui(self):
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("WebDavBackupCard { background: transparent; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 20, 16)
        root.setSpacing(14)

        # ── Hero header ──
        hero = QHBoxLayout()
        hero.setSpacing(12)
        self._header_icon = IconWidget(FluentIcon.CLOUD)
        self._header_icon.setFixedSize(40, 40)
        hero.addWidget(self._header_icon, 0, Qt.AlignVCenter)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        self._title_label = StrongBodyLabel("WebDAV 备份")
        self._title_label.setStyleSheet(_hero_title_css())
        self._subtitle_label = CaptionLabel("正在读取配置…")
        self._subtitle_label.setStyleSheet(_caption_css())
        titles.addWidget(self._title_label)
        titles.addWidget(self._subtitle_label)
        hero.addLayout(titles, 1)

        close_btn = TransparentToolButton(FluentIcon.CLOSE)
        close_btn.setFixedSize(32, 32)
        close_btn.clicked.connect(self._on_close)
        hero.addWidget(close_btn, 0, Qt.AlignVCenter)
        root.addLayout(hero)

        # ── 操作卡 ──
        ops = _make_section_card()
        ops_lay = QVBoxLayout(ops)
        ops_lay.setContentsMargins(16, 14, 16, 14)
        ops_lay.setSpacing(10)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._backup_btn = PrimaryPushButton(FluentIcon.CLOUD, "立即备份")
        self._backup_btn.setFixedHeight(34)
        self._backup_btn.clicked.connect(self._on_backup)
        btn_row.addWidget(self._backup_btn)

        self._test_btn = PushButton(FluentIcon.SYNC, "测试连接")
        self._test_btn.setFixedHeight(34)
        self._test_btn.clicked.connect(self._on_test)
        btn_row.addWidget(self._test_btn)

        self._test_result = CaptionLabel("")
        self._test_result.setStyleSheet(_caption_css())
        btn_row.addWidget(self._test_result)

        # 恢复完成后显示（走主程序重启逻辑：拉起新进程 + 优雅退出）
        self._restart_btn = PrimaryPushButton(FluentIcon.SYNC, "重启 DriFox")
        self._restart_btn.setFixedHeight(34)
        self._restart_btn.clicked.connect(self._on_restart)
        self._restart_btn.hide()
        btn_row.addWidget(self._restart_btn)

        self._refresh_btn = PushButton(FluentIcon.SYNC, "刷新列表")
        self._refresh_btn.setFixedHeight(34)
        self._refresh_btn.clicked.connect(self.refresh_all)
        btn_row.addWidget(self._refresh_btn)
        btn_row.addStretch(1)
        ops_lay.addLayout(btn_row)

        self._summary_label = CaptionLabel("")
        self._summary_label.setStyleSheet(_caption_css())
        self._summary_label.setWordWrap(True)
        ops_lay.addWidget(self._summary_label)
        root.addWidget(ops)

        # ── 备份范围卡（勾选即存；连接配置在设置卡，此处只管范围） ──
        root.addWidget(self._build_scope_card())

        # ── 云端备份卡 ──
        hist = _make_section_card()
        hist_lay = QVBoxLayout(hist)
        hist_lay.setContentsMargins(16, 14, 16, 14)
        hist_lay.setSpacing(8)

        hist_head = QHBoxLayout()
        hist_title = StrongBodyLabel("云端备份")
        hist_title.setStyleSheet(_section_title_css())
        hist_head.addWidget(hist_title)
        hist_head.addStretch(1)
        self._count_label = CaptionLabel("")
        self._count_label.setStyleSheet(_caption_css())
        hist_head.addWidget(self._count_label)
        hist_lay.addLayout(hist_head)

        hist_lay.addWidget(CardSeparator())

        from qfluentwidgets import ScrollArea

        self._list_scroll = ScrollArea(self)
        self._list_scroll.setWidgetResizable(True)
        self._list_scroll.setStyleSheet(
            "ScrollArea { background: transparent; border: none; }"
            "ScrollArea > QWidget > QWidget { background: transparent; }"
            "QScrollBar:vertical { width: 6px; background: transparent; }"
        )
        self._list_container = QWidget()
        self._list_lay = QVBoxLayout(self._list_container)
        self._list_lay.setContentsMargins(0, 4, 0, 4)
        self._list_lay.setSpacing(2)
        self._list_lay.addStretch(1)
        self._list_scroll.setWidget(self._list_container)
        self._list_scroll.setMinimumHeight(220)
        hist_lay.addWidget(self._list_scroll, 1)

        self._empty_label = CaptionLabel("暂无云端备份")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setStyleSheet(_caption_css())
        hist_lay.addWidget(self._empty_label)
        root.addWidget(hist, 1)

        # ── 状态行 ──
        self._status_label = CaptionLabel("")
        self._status_label.setStyleSheet(_caption_css())
        self._status_label.setWordWrap(True)
        root.addWidget(self._status_label)

    # ── 备份范围卡 ──────────────────────────────────────

    def _build_scope_card(self) -> QWidget:
        card = _make_section_card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        head = QHBoxLayout()
        title = StrongBodyLabel("备份范围")
        title.setStyleSheet(_section_title_css())
        head.addWidget(title)
        head.addStretch(1)
        self._scope_hint = CaptionLabel("")
        self._scope_hint.setStyleSheet(_caption_css())
        head.addWidget(self._scope_hint)
        lay.addLayout(head)

        self._scope_checks: dict = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        for i, (field, dirname) in enumerate(cfg_mod.INCLUDE_FIELDS.items()):
            cb = CheckBox(f"{cfg_mod.INCLUDE_LABELS[dirname]} ({dirname})")
            cb.toggled.connect(self._on_scope_changed)
            grid.addWidget(cb, i // 2, i % 2)
            self._scope_checks[field] = (cb, dirname)
        lay.addLayout(grid)

        extra_row = QHBoxLayout()
        extra_label = CaptionLabel("额外包含")
        extra_label.setStyleSheet(_caption_css())
        extra_row.addWidget(extra_label)
        self._scope_extra = LineEdit()
        self._scope_extra.setPlaceholderText("目录名，逗号分隔，如：memory, gateway")
        self._scope_extra.setClearButtonEnabled(True)
        self._scope_extra.editingFinished.connect(self._on_scope_changed)
        extra_row.addWidget(self._scope_extra, 1)
        lay.addLayout(extra_row)

        # 外部绝对路径（数据目录之外的自定义备份目标）
        ext_row = QHBoxLayout()
        ext_label = CaptionLabel("外部路径")
        ext_label.setStyleSheet(_caption_css())
        ext_label.setToolTip("数据目录之外的本地文件/目录，每行一个绝对路径，随备份包上传并恢复到原位")
        ext_row.addWidget(ext_label)
        self._scope_paths = PlainTextEdit()
        self._scope_paths.setPlaceholderText("每行一个绝对路径，如：D:\\work\\my-notes")
        self._scope_paths.setFixedHeight(64)
        self._scope_paths.textChanged.connect(self._on_paths_changed)
        self._paths_timer = QTimer(self)
        self._paths_timer.setSingleShot(True)
        self._paths_timer.setInterval(600)
        self._paths_timer.timeout.connect(self._save_paths)
        ext_row.addWidget(self._scope_paths, 1)
        lay.addLayout(ext_row)

        self._scope_hint_timer = QTimer(self)
        self._scope_hint_timer.setSingleShot(True)
        self._scope_hint_timer.timeout.connect(lambda: self._scope_hint.setText(""))

        self._refresh_scope_ui()
        return card

    def _refresh_scope_ui(self):
        """从配置回显勾选（仅构造/显示时调用，不覆盖用户编辑中状态）"""
        try:
            cfg = cfg_mod.load_config()
        except Exception:
            return
        dirs = cfg.get("include_dirs", set())
        for cb, dirname in self._scope_checks.values():
            cb.blockSignals(True)
            cb.setChecked(dirname in dirs)
            cb.blockSignals(False)
        self._scope_extra.blockSignals(True)
        self._scope_extra.setText(", ".join(cfg.get("include_extra", [])))
        self._scope_extra.blockSignals(False)
        self._scope_paths.blockSignals(True)
        self._scope_paths.setPlainText("\n".join(cfg.get("include_paths", [])))
        self._scope_paths.blockSignals(False)

    def _on_scope_changed(self, *args):
        """勾选/额外项变更：合并写存储（只落范围键，不碰账号密码）"""
        try:
            from webdavbackup_core.host_compat import get_config_store

            values = {f: cb.isChecked() for f, (cb, _) in self._scope_checks.items()}
            values["include_extra"] = self._scope_extra.text().strip()
            get_config_store().set_values(cfg_mod.PLUGIN_NAME, values)
            from datetime import datetime

            self._scope_hint.setText(f"已保存 {datetime.now().strftime('%H:%M:%S')}")
            self._scope_hint_timer.start(3000)
            self._refresh_info_only()
        except Exception as e:
            self._scope_hint.setText(f"保存失败: {e}")

    # ── 数据与渲染 ──────────────────────────────────────

    def _refresh_info_only(self):
        """同步读本地配置与 state（无网络），更新摘要行与副标题"""
        try:
            cfg = cfg_mod.load_config()
            state = cfg_mod.load_state()
            if not cfg_mod.is_configured(cfg):
                self._subtitle_label.setText("未配置：请先在 设置 → 插件 → WebDAV 备份 完成配置")
                self._set_actions_enabled(False)
                self._summary_label.setText(
                    "支持坚果云 / Nextcloud 等 WebDAV 网盘。坚果云需使用「应用密码」"
                    "（网页端 账户信息 → 安全选项 → 添加）。"
                )
            else:
                self._subtitle_label.setText(f"服务器：{cfg.get('server_url', '')}")
                self._set_actions_enabled(True)
                parts = []
                parts.append("自动备份 开" if cfg.get("auto_backup") else "自动备份 关")
                parts.append(f"每 {cfg.get('interval_hours', 24)} 小时")
                parts.append(f"保留 {cfg.get('keep_versions', 10)} 份")
                parts.append("已启用加密" if (cfg.get("encryption_password") or "").strip() else "未加密")
                parts.append(f"范围：{cfg_mod.describe_scope(cfg)}")
                last_at = state.get("last_backup_at", "")
                if last_at:
                    status = state.get("last_backup_status", "")
                    mark = "成功" if status == "success" else "失败"
                    parts.append(f"上次备份 {mark} {_format_time(str(last_at))}")
                self._summary_label.setText(" · ".join(parts))
        except Exception as e:
            self._subtitle_label.setText(f"读取配置失败: {e}")

    def refresh_all(self):
        """摘要 + 云端列表一起刷新"""
        self._refresh_info_only()
        cfg = cfg_mod.load_config()
        if not cfg_mod.is_configured(cfg):
            self._render_list([])
            self._set_status("尚未配置 WebDAV，配置后即可备份")
            return
        self._set_status("正在获取云端备份列表…")
        self._run_async(lambda: engine.run_list(), self._on_list_done)

    def _render_list(self, items: List[dict]):
        # 清旧行（含同步断开信号，避免 queued 回调打到已销毁行）
        for row in self._rows:
            try:
                row.restore_clicked.disconnect()
                row.delete_clicked.disconnect()
            except (TypeError, RuntimeError):
                pass
            row.setParent(None)
            row.deleteLater()
        self._rows.clear()

        # 移除末尾 stretch 再加行，最后补回
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(1)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for it in items:
            row = CloudFileRow(it)
            row.restore_clicked.connect(self._on_restore)
            row.delete_clicked.connect(self._on_delete)
            self._list_lay.insertWidget(self._list_lay.count() - 1, row)
            self._rows.append(row)

        self._empty_label.setVisible(not items)
        self._count_label.setText(f"{len(items)} 份" if items else "")

    # ── 异步执行 ────────────────────────────────────────

    def _run_async(self, fn: Callable[[], Any], on_done: Callable[[Any], None]):
        if self._busy:
            self._set_status("有操作进行中，请稍候…")
            return
        self._busy = True
        self._set_actions_enabled(False)
        self._thread = QThread(self)
        self._worker = _Worker(fn)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(on_done)
        self._worker.error.connect(self._on_worker_error)
        self._worker.finished.connect(self._on_worker_done)
        self._worker.error.connect(self._on_worker_done)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._cleanup_worker_refs)
        self._thread.start()

    def _on_worker_done(self):
        self._busy = False
        self._set_actions_enabled(True)
        self._refresh_info_only()

    def _cleanup_worker_refs(self):
        self._thread = None
        self._worker = None

    def _on_worker_error(self, err: str):
        self._set_status(f"操作失败: {err}")

    # ── 操作 ────────────────────────────────────────────

    def _on_backup(self):
        self._set_status("正在备份，视数据量可能需要几十秒…")
        self._run_async(lambda: engine.run_backup(), self._on_backup_done)

    def _on_backup_done(self, result: dict):
        ok = bool(result.get("ok"))
        self._set_status(("✓ " if ok else "✗ ") + str(result.get("message", "")))
        if ok:
            self._run_async(lambda: engine.run_list(), self._on_list_done)

    def _on_test(self):
        self._test_result.setText("测试中…")
        self._run_async(lambda: engine.run_test(), self._on_test_done)

    def _on_test_done(self, result: dict):
        self._test_result.setText(("✓ " if result.get("ok") else "✗ ") + str(result.get("message", "")))

    def _on_list_done(self, result: dict):
        items = result.get("items", []) if isinstance(result, dict) else []
        self._render_list(items)
        if result.get("ok"):
            self._set_status(f"云端共 {len(items)} 份备份")
        else:
            self._set_status(f"获取列表失败: {result.get('message', '')}")

    def _on_restore(self, name: str):
        if not self._confirm_encrypted_ok(name):
            return
        self._set_status(f"正在恢复 {name}，完成后需重启 DriFox…")
        self._run_async(lambda: engine.run_restore(name), self._on_restore_done)

    def _confirm_encrypted_ok(self, name: str) -> bool:
        """加密包在未设密码时提前拦截，避免白下载一次"""
        if not name.endswith(".dvp"):
            return True
        cfg = cfg_mod.load_config()
        if (cfg.get("encryption_password") or "").strip():
            return True
        self._set_status("该备份包已加密：请先在 设置 → 插件 → WebDAV 备份 填写备份加密密码")
        return False

    def _on_restore_done(self, result: dict):
        ok = bool(result.get("ok"))
        msg = str(result.get("message", ""))
        rb = result.get("rollback_dir")
        if ok and rb:
            msg += f" 回滚副本：{rb}"
        self._set_status(msg)
        if ok:
            self._restart_btn.show()

    def _on_delete(self, name: str):
        self._set_status(f"正在删除 {name}…")

        def _do_delete():
            from webdavbackup_core.webdav import WebDAVError

            try:
                cfg = cfg_mod.load_config()
                client = engine._make_client(cfg)
                client.delete(f"{engine._remote_dir(cfg)}/{name}")
                return {"ok": True, "message": f"已删除 {name}"}
            except WebDAVError as e:
                return {"ok": False, "message": str(e)}

        self._run_async(_do_delete, self._on_delete_done)

    def _on_delete_done(self, result: dict):
        ok = bool(result.get("ok"))
        self._set_status(("✓ " if ok else "✗ ") + str(result.get("message", "")))
        if ok:
            self._run_async(lambda: engine.run_list(), self._on_list_done)

    # ── 调度器联动（信号来自后台线程，queued 到主线程） ──

    def _on_scheduler_result(self, result: dict):
        ok = bool(result.get("ok"))
        self._set_status(("✓ " if ok else "✗ ") + f"自动备份：{result.get('message', '')}")
        self.refresh_all()

    # ── 杂项 ────────────────────────────────────────────

    def _set_actions_enabled(self, enabled: bool):
        for b in (self._backup_btn, self._test_btn, self._refresh_btn):
            b.setEnabled(enabled)
        for row in self._rows:
            row.set_busy(not enabled)

    def _on_paths_changed(self, *args):
        """外部路径输入防抖 600ms 后保存"""
        self._paths_timer.start()

    def _save_paths(self):
        try:
            from webdavbackup_core.host_compat import get_config_store

            get_config_store().set_values(
                cfg_mod.PLUGIN_NAME, {"include_paths": self._scope_paths.toPlainText().strip()}
            )
            from datetime import datetime

            self._scope_hint.setText(f"已保存 {datetime.now().strftime('%H:%M:%S')}")
            self._scope_hint_timer.start(3000)
        except Exception as e:
            self._scope_hint.setText(f"保存失败: {e}")

    def _on_restart(self):
        """重启：优先主程序官方逻辑，主程序不可用时自包含拉起新进程"""
        try:
            from webdavbackup_core.host_compat import restart_app

            ok, err = restart_app()
            if not ok:
                self._set_status(f"重启失败：{err}（请手动退出后重新打开 DriFox）")
        except Exception as e:
            self._set_status(f"重启失败: {e}（请手动重启）")

    def _set_status(self, text: str):
        self._status_label.setText(text)

    def _on_close(self):
        self.closed.emit()

    def deleteLater(self):  # noqa: D102
        self._cleanup_worker_refs()
        super().deleteLater()
