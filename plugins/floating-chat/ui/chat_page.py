# -*- coding: utf-8 -*-
"""floating-chat 内容页：状态行 + 纯文本回答区 + 输入区（+ 工具审批条）。

三约定接口（主程序 PluginWindow 调用）：
- ``set_context_provider(provider)``：注入上下文拉模型
- ``show_card()``：数据/主题的唯一加载入口（__init__ 只建骨架）
- ``refresh_theme()``：主题切换时补刷样式
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from loguru import logger
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .engine_bridge import PLUGIN_NAME, ChatController

# 默认/最小几何（register_window 同步使用）
DEFAULT_WIDTH = 420
DEFAULT_HEIGHT = 340
MIN_WIDTH = 340
MIN_HEIGHT = 260

# 输入区自动增高上限
_INPUT_MAX_HEIGHT = 88

# 「◌ 思考中」计时刷新间隔（ms）
_TICK_MS = 500


def _plugin_data_dir() -> Path:
    """插件数据目录（几何记忆落这里，不进插件目录、不随插件分发）"""
    try:
        from app.utils.utils import get_app_data_dir

        return Path(get_app_data_dir()) / "plugin_data" / PLUGIN_NAME
    except Exception:  # noqa: BLE001 — 取不到就落插件同级目录
        return Path(__file__).resolve().parent.parent / ".data"


def _ctx_colors(ctx: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """从 ctx 取色，缺失按深浅 fallback（绝不硬编码单一色）"""
    colors = (ctx or {}).get("colors", {}) or {}
    dark = bool((ctx or {}).get("is_dark", True))
    return {
        "text_primary": colors.get("text_primary")
        or ("rgba(255,255,255,0.90)" if dark else "rgba(0,0,0,0.85)"),
        "text_secondary": colors.get("text_secondary")
        or ("rgba(255,255,255,0.55)" if dark else "rgba(0,0,0,0.45)"),
        "border": colors.get("border") or ("rgba(255,255,255,0.12)" if dark else "rgba(0,0,0,0.12)"),
        "accent": colors.get("accent") or ("#f59e0b" if dark else "#b8791a"),
        "panel_bg": colors.get("card_bg") or ("rgba(255,255,255,0.06)" if dark else "rgba(0,0,0,0.03)"),
        "input_bg": colors.get("content_bg") or ("rgba(0,0,0,0.18)" if dark else "rgba(0,0,0,0.02)"),
    }


class ChatPage(QWidget):
    """悬浮对话内容页"""

    # 请求宿主 MainWidget（线程安全：由 ui/__init__ 注入）
    _host_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._provider: Optional[Callable[[], Dict[str, Any]]] = None
        self._colors = _ctx_colors(None)
        self._font_family = ""
        self._font_size = 0
        self._controller: Optional[ChatController] = None
        self._host = None
        self._pinned = False
        self._pending_permissions: Dict[str, Dict[str, Any]] = {}
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(_TICK_MS)
        self._tick_timer.timeout.connect(self._on_tick)
        self._elapsed_s = 0
        self._streaming = False

        self._build_ui()

    # ── 骨架 ──

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(0)

        # 状态行：模型 chip + 轮数 + 新会话 / 打开完整会话
        meta = QHBoxLayout()
        meta.setSpacing(6)
        self._model_chip = QLabel("—", self)
        self._model_chip.setObjectName("fcModelChip")
        self._round_label = QLabel("", self)
        self._round_label.setObjectName("fcHint")
        meta.addWidget(self._model_chip)
        meta.addWidget(self._round_label)
        meta.addStretch(1)
        self._btn_open_session = self._make_link("打开完整会话")
        self._btn_open_session.clicked.connect(self._on_open_full_session)
        self._btn_new = self._make_link("新会话")
        self._btn_new.clicked.connect(self._on_new_session)
        meta.addWidget(self._btn_open_session)
        meta.addWidget(self._btn_new)
        root.addLayout(meta)
        root.addSpacing(6)

        # 回答区（纯文本：等宽 + 保留换行缩进，不做 Markdown）
        self._answer = QTextEdit(self)
        self._answer.setReadOnly(True)
        self._answer.setLineWrapMode(QTextEdit.WidgetWidth)
        self._answer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._answer.setPlaceholderText("问点什么…")
        root.addWidget(self._answer, 1)
        root.addSpacing(6)

        # 工具审批条（仅 INTERACTIVE 触发时出现）
        self._approve_bar = QWidget(self)
        ab = QHBoxLayout(self._approve_bar)
        ab.setContentsMargins(8, 5, 8, 5)
        ab.setSpacing(6)
        self._approve_label = QLabel("", self._approve_bar)
        self._approve_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        ab.addWidget(self._approve_label)
        self._btn_allow = QPushButton("允许", self._approve_bar)
        self._btn_allow.setFixedHeight(24)
        self._btn_allow.clicked.connect(lambda: self._on_decide(True))
        self._btn_deny = QPushButton("拒绝", self._approve_bar)
        self._btn_deny.setFixedHeight(24)
        self._btn_deny.clicked.connect(lambda: self._on_decide(False))
        ab.addWidget(self._btn_allow)
        ab.addWidget(self._btn_deny)
        self._approve_bar.setVisible(False)
        root.addWidget(self._approve_bar)
        root.addSpacing(4)

        # 输入区
        input_row = QHBoxLayout()
        input_row.setSpacing(6)
        self._input = QTextEdit(self)
        self._input.setPlaceholderText("问点什么…  Enter 发送 / Shift+Enter 换行")
        self._input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._input.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._input.installEventFilter(self)
        self._input.document().documentLayout().documentSizeChanged.connect(self._fit_input_height)
        self._btn_send = QPushButton("↑", self)
        self._btn_send.setFixedSize(28, 28)
        self._btn_send.setObjectName("fcSend")
        self._btn_send.clicked.connect(self._on_send_clicked)
        input_row.addWidget(self._input)
        input_row.addWidget(self._btn_send, 0, Qt.AlignBottom)
        root.addLayout(input_row)

        self._hint = QLabel("Enter 发送 · Shift+Enter 换行 · Esc 隐藏", self)
        self._hint.setObjectName("fcHint")
        self._hint.setAlignment(Qt.AlignRight)
        root.addWidget(self._hint)

    def _make_link(self, text: str) -> QPushButton:
        btn = QPushButton(text, self)
        btn.setObjectName("fcLink")
        btn.setFlat(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(20)
        return btn

    # ── 三约定接口 ──

    def set_context_provider(self, provider: Callable[[], Dict[str, Any]]):
        self._provider = provider

    def show_card(self):
        """打开/激活入口：拉上下文 → 建控制器 → 应用主题

        ⚠️ 几何还原与标题栏钩子必须延后一拍：PluginWindow.__init__ 在
        _build_content（即本方法）**之后**才 resize 到注册尺寸，此处设几何会被覆盖。
        """
        self._apply_theme()
        self._ensure_controller()
        QTimer.singleShot(0, self._on_window_ready)
        QTimer.singleShot(0, self._input.setFocus)

    def _on_window_ready(self):
        """窗口构造完成后的收尾：几何还原 + 标题栏钉住 + 关闭落盘钩子（幂等）"""
        win = self.window()
        if win is None or win is self or getattr(self, "_fc_ready", False):
            return
        self._fc_ready = True
        self._restore_geometry()
        try:
            self.install_pin_button()
            # PluginWindow 静默销毁、无 on_close 通知 → 用事件过滤在 Close 前落盘
            win.installEventFilter(self)
        except Exception as e:  # noqa: BLE001 — 标题栏结构变化时降级，不影响主功能
            logger.debug(f"[{PLUGIN_NAME}] 窗口钩子安装失败: {e}")

    def refresh_theme(self):
        self._apply_theme()

    # ── 主题 ──

    def _apply_theme(self):
        ctx = {}
        if self._provider is not None:
            try:
                ctx = self._provider() or {}
            except Exception as e:  # noqa: BLE001
                logger.debug(f"[{PLUGIN_NAME}] 上下文拉取失败: {e}")
        self._colors = _ctx_colors(ctx)
        self._font_family = str(ctx.get("font_family", "") or "")
        try:
            self._font_size = int(ctx.get("font_size", 0) or 0)
        except (TypeError, ValueError):
            self._font_size = 0

        if self._font_family:
            self.setFont(QFont(self._font_family, self._font_size or 13))
        c = self._colors
        mono = "Consolas, 'Microsoft YaHei Mono', monospace"
        input_font = f"{self._font_family},'Microsoft YaHei'" if self._font_family else "inherit"

        self._answer.setFont(QFont(mono.split(",")[0], max((self._font_size or 13) - 1, 9)))
        self.setStyleSheet(f"""
            QWidget {{ color: {c['text_primary']}; }}
            QLabel#fcHint {{ color: {c['text_secondary']}; font-size: 10px; }}
            QLabel#fcModelChip {{
                color: {c['accent']};
                border: 1px solid {c['border']};
                border-radius: 4px; padding: 1px 6px; font-size: 11px;
            }}
            QTextEdit {{
                background: {c['panel_bg']};
                border: 1px solid {c['border']};
                border-radius: 8px; padding: 8px 10px;
                selection-background-color: {c['accent']};
            }}
            #fcAnswer {{ font-family: {mono}; }}
            #fcInput {{
                font-family: {input_font};
                background: {c['input_bg']};
            }}
            QPushButton#fcLink {{
                color: {c['text_secondary']}; border: none;
                background: transparent; font-size: 11px; padding: 0 4px;
            }}
            QPushButton#fcLink:hover {{ color: {c['accent']}; }}
            QPushButton#fcSend {{
                background: {c['accent']}; color: #101010;
                border: none; border-radius: 7px; font-weight: 600;
            }}
            QPushButton#fcSend:hover {{ background: {c['accent']}; }}
            QPushButton {{
                background: {c['panel_bg']}; color: {c['text_primary']};
                border: 1px solid {c['border']}; border-radius: 5px; padding: 2px 10px;
            }}
        """)
        self._answer.setObjectName("fcAnswer")
        self._input.setObjectName("fcInput")
        self._refresh_meta()

    def _refresh_meta(self):
        if self._controller is None:
            self._model_chip.setText("未连接")
            self._round_label.setText("")
            return
        self._model_chip.setText(self._controller.model_label())
        n = self._controller.round_count()
        self._round_label.setText(f"独立会话 · {n} 轮" if n else "独立会话")

    # ── 控制器 ──

    def _ensure_controller(self) -> bool:
        if self._controller is not None:
            return True
        host = self._resolve_host()
        if host is None:
            self._model_chip.setText("未连接")
            self._append_system("未找到 DriFox 主窗，请先打开主窗再使用悬浮对话。")
            return False
        self._host = host
        self._controller = ChatController(host, self)
        b = self._controller.bridge
        b.thinking.connect(self._on_thinking)
        b.chunk.connect(self._on_chunk)
        b.tool_started.connect(self._on_tool_started)
        b.tool_result.connect(self._on_tool_result)
        b.permission.connect(self._on_permission)
        b.finished.connect(self._on_finished)
        b.error.connect(self._on_error)
        return True

    def _controller_or_none(self) -> Optional[ChatController]:
        """取可用控制器；未初始化则尝试初始化，仍失败返回 None（并已提示用户）"""
        if self._controller is None and not self._ensure_controller():
            return None
        return self._controller

    @staticmethod
    def _resolve_host():
        """取一个存活的 MainWidget（多窗时取首个）"""
        try:
            from app.core.infra.window_registry import alive_window_instances

            for w in alive_window_instances():
                if w is not None and not getattr(w, "_is_destroyed", False):
                    return w
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[{PLUGIN_NAME}] 宿主窗口解析失败: {e}")
        return None

    # ── 流事件 ──

    def _on_thinking(self):
        self._streaming = True
        self._elapsed_s = 0
        self._tick_timer.start()
        self._set_sending(True)
        self._append_system("◌ 思考中…")

    def _on_tick(self):
        self._elapsed_s += _TICK_MS / 1000.0
        self._replace_last_line(f"◌ 思考中… {self._elapsed_s:.1f}s")

    def _on_chunk(self, piece: str):
        if not self._streaming:
            self._streaming = True
            self._tick_timer.stop()
        if self._elapsed_s or self._tick_timer.isActive():
            self._tick_timer.stop()
            self._replace_last_line("")
        self._append_plain(piece)
        self._scroll_bottom()

    def _on_tool_started(self, name: str, round_id: str):
        suffix = f"（第 {round_id} 轮）" if round_id else ""
        self._append_system(f"▸ 调用工具 {name}{suffix}")
        self._scroll_bottom()

    def _on_tool_result(self, name: str, result: str):
        text = " ".join(str(result).split())
        self._append_system(f"  ✓ {name} → {text[:160]}")
        self._scroll_bottom()

    def _on_permission(self, tool_call_id: str, tool_name: str, arguments: dict):
        self._pending_permissions["current"] = {"id": tool_call_id, "name": tool_name}
        self._approve_label.setText(f"工具 {tool_name} 请求执行，允许？")
        self._approve_bar.setVisible(True)

    def _on_decide(self, allow: bool):
        pending = self._pending_permissions.pop("current", None)
        self._approve_bar.setVisible(False)
        if pending is None or self._controller is None:
            return
        self._controller.decide_permission(pending["id"], allow)
        self._append_system(f"{'已允许' if allow else '已拒绝'} {pending['name']}")

    def _on_finished(self):
        self._streaming = False
        self._tick_timer.stop()
        self._set_sending(False)
        self._append_system("")
        if self._controller is not None:
            self._controller.persist_to_history()
        self._refresh_meta()

    def _on_error(self, message: str):
        self._streaming = False
        self._tick_timer.stop()
        self._set_sending(False)
        self._append_system(f"✕ {message}")
        # 不吞输入：用户输入原样留在输入框，可直接改后重发

    # ── 文本操作 ──

    def _append_plain(self, text: str):
        cur = self._answer.textCursor()
        cur.movePosition(cur.End)
        cur.insertText(text)
        self._answer.setTextCursor(cur)

    def _append_system(self, text: str):
        self._append_plain(f"\n{text}" if text else "\n")

    def _replace_last_line(self, text: str):
        """替换回答区最后一行（用于思考计时的原地刷新）"""
        cur = self._answer.textCursor()
        cur.movePosition(cur.End)
        cur.movePosition(cur.StartOfBlock, cur.KeepAnchor)
        cur.insertText(text)
        self._answer.setTextCursor(cur)

    def _scroll_bottom(self):
        sb = self._answer.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _set_sending(self, sending: bool):
        self._btn_send.setText("■" if sending else "↑")
        self._btn_send.setToolTip("停止" if sending else "发送")

    # ── 交互 ──

    def eventFilter(self, obj, event):
        # 窗口关闭前落几何（PluginWindow 无 on_close 通知，Close 事件是最后时机）
        if obj is self.window() and event.type() == event.Close:
            self.dispose()
        elif obj is self._input and event.type() == event.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if event.modifiers() & Qt.ShiftModifier:
                    return False
                self._on_send_clicked()
                return True
            if event.key() == Qt.Key_Escape:
                win = self.window()
                if win is not None:
                    win.hide()
                return True
        return super().eventFilter(obj, event)

    def _fit_input_height(self):
        doc_h = int(self._input.document().size().height()) + 10
        self._input.setFixedHeight(max(30, min(doc_h, _INPUT_MAX_HEIGHT)))

    def _on_send_clicked(self):
        if self._streaming:
            if self._controller is not None:
                self._controller.stop()
            self._streaming = False
            self._tick_timer.stop()
            self._set_sending(False)
            self._append_system("（已停止）")
            return
        ctrl = self._controller_or_none()
        if ctrl is None:
            return
        text = self._input.toPlainText().strip()
        if not text:
            return
        self._input.clear()
        self._append_plain(f"\n你\n{text}\n\n助手\n")
        self._scroll_bottom()
        if not ctrl.send(text):
            self._append_system("✕ 发送失败：已有请求在进行中或模型未配置")

    def _on_new_session(self):
        ctrl = self._controller_or_none()
        if ctrl is None:
            return
        ctrl.reset_session()
        self._answer.clear()
        self._refresh_meta()
        QTimer.singleShot(0, self._input.setFocus)

    def _on_open_full_session(self):
        """拉起主窗并加载当前会话到完整界面"""
        ctrl = self._controller_or_none()
        if ctrl is None:
            return
        sid = ctrl.persist_to_history()
        host = self._host if self._host is not None else self._resolve_host()
        if host is None:
            self._append_system("✕ 未找到 DriFox 主窗")
            return
        # 主窗可能最小化/隐藏：先恢复可见再加载
        try:
            if host.isMinimized():
                host.showNormal()
            elif host.isHidden():
                host.show()
            top = host.window()
            if top is not None:
                top.raise_()
                top.activateWindow()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[{PLUGIN_NAME}] 主窗前置失败: {e}")
        if not sid:
            self._append_system("✕ 会话为空，尚无内容可打开")
            return
        loader = getattr(host, "_load_session_from_record", None)
        if not callable(loader):
            self._append_system("✕ 当前版本主窗不支持直接加载，请在历史面板搜索本会话")
            return
        hm = getattr(host, "history_manager", None)
        record = hm.get_session_by_session_id(sid) if hm is not None else None
        if record is None:
            self._append_system("✕ 会话尚未落库，请稍后再试")
            return
        try:
            loader(record)
            self._append_system("✓ 已在主窗打开该会话")
        except Exception as e:  # noqa: BLE001 — 私有 API 变更时降级，不崩
            logger.warning(f"[{PLUGIN_NAME}] 主窗加载会话失败: {e}")
            self._append_system(f"✕ 打开失败：{e}")

    # ── 钉住 + 几何记忆 ──

    def set_pinned(self, pinned: bool):
        self._pinned = bool(pinned)
        win = self.window()
        if win is None or win is self:
            return
        flags = win.windowFlags()
        win.setWindowFlags(
            flags | Qt.WindowStaysOnTopHint if self._pinned else flags & ~Qt.WindowStaysOnTopHint
        )
        win.show()  # ⚠️ 改 flags 会隐藏窗口，必须补 show

    @property
    def pinned(self) -> bool:
        return self._pinned

    def _geometry_file(self) -> Path:
        return _plugin_data_dir() / "geometry.json"

    def save_geometry(self):
        win = self.window()
        if win is None or win is self:
            return
        data = {
            "x": win.x(),
            "y": win.y(),
            "w": win.width(),
            "h": win.height(),
            "pinned": self._pinned,
        }
        try:
            p = self._geometry_file()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[{PLUGIN_NAME}] 几何写入失败: {e}")

    def _restore_geometry(self):
        """还原上次几何；越界（屏幕外）则居中偏上"""
        data = None
        try:
            p = self._geometry_file()
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[{PLUGIN_NAME}] 几何读取失败: {e}")
        win = self.window()
        if win is None or win is self:
            return
        if isinstance(data, dict):
            self.set_pinned(bool(data.get("pinned", False)))
            try:
                x, y = int(data["x"]), int(data["y"])
                w, h = int(data["w"]), int(data["h"])
            except (KeyError, TypeError, ValueError):
                return
            from PyQt5.QtWidgets import QApplication

            screen = QApplication.primaryScreen()
            geo = screen.availableGeometry() if screen is not None else None
            if geo is None:
                return
            # 越界判定：中心点落在可用区外即视为不可用
            if geo.contains(x + w // 2, y + h // 2):
                win.setGeometry(x, y, max(w, MIN_WIDTH), max(h, MIN_HEIGHT))
                return
        self._center_up(win)

    @staticmethod
    def _center_up(win):
        from PyQt5.QtWidgets import QApplication

        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - DEFAULT_WIDTH) // 2
        y = geo.y() + int(geo.height() * 0.18)
        win.setGeometry(x, y, DEFAULT_WIDTH, DEFAULT_HEIGHT)

    def dispose(self):
        """窗口销毁前：落几何 + 释放引擎"""
        self.save_geometry()
        if self._controller is not None:
            self._controller.dispose()
            self._controller = None

    # ── 标题栏钉住按钮（由 __init__ 注册时机注入）──

    def install_pin_button(self):
        """往主程序标题栏插入「钉住」开关（系统按钮左侧）"""
        win = self.window()
        bar = getattr(win, "titleBar", None) if win is not None else None
        lay = bar.layout() if bar is not None else None
        if lay is None:
            return
        self._pin_btn = QToolButton(bar)
        self._pin_btn.setText("📌")
        self._pin_btn.setToolTip("钉住：窗口常驻最前")
        self._pin_btn.setCheckable(True)
        self._pin_btn.setChecked(self._pinned)
        self._pin_btn.setFixedSize(24, 22)
        self._pin_btn.setCursor(Qt.PointingHandCursor)
        self._pin_btn.toggled.connect(self._on_pin_toggled)
        lay.insertWidget(lay.count() - 3, self._pin_btn)

    def _on_pin_toggled(self, checked: bool):
        self.set_pinned(checked)
        self.save_geometry()
