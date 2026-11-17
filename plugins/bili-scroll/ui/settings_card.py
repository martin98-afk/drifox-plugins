# -*- coding: utf-8 -*-
"""bili-scroll 自绘设置卡（priority>0，完整覆盖 E1 自动卡）。

为什么要自绘：
- 「值班模型」需要按用户实际配置的服务商/模型动态出下拉项，config_schema 的
  select 是静态 JSON，只能让用户手拼「服务商:模型名」；
- 账号登录要按钮 + 后台轮询扫码结果 + 在线校验 cookie 是否仍有效；
- 自动卡把 12 个字段平铺，长标签被截断、没有分组，读起来很乱。

布局口径遵循 docs/settings-card.md：分组卡片 + 「label 最小宽 120 + 控件撑满」，
不适用字段整行置灰（不隐藏）。保存策略同自动卡：改动即时落盘。
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from loguru import logger

try:
    from PyQt5.QtCore import QObject, QThread, Qt, QTimer, pyqtSignal
    from PyQt5.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget
    from qfluentwidgets import (
        BodyLabel,
        CaptionLabel,
        ComboBox,
        EditableComboBox,
        FluentIcon,
        LineEdit,
        PrimaryPushButton,
        PushButton,
        SpinBox,
        SwitchButton,
        TextEdit,
        ToolButton,
    )

    _UI_AVAILABLE = True
except Exception:  # noqa: BLE001 — headless 环境不阻断插件加载
    _UI_AVAILABLE = False
    QObject = object  # type: ignore

PLUGIN_NAME = "bili-scroll"
_LABEL_MIN_WIDTH = 120
_FOLLOW_CURRENT = "__current__"
_NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)
_REPORT_MODES = [("full", "完整：标题 / UP 主 / 为什么值得"), ("thin", "精简：只列标题与链接"), ("none", "只判重，不写日报")]
_DELIVERIES = [("comment", "只发公开评论"), ("dm_only", "只发私信"), ("both", "公开评论 + 私信")]


# ── 配置读写 ────────────────────────────────────────────
def _load_all() -> Dict[str, Any]:
    try:
        from app.plugins.managers.plugin_config_store import PluginConfigStore

        return PluginConfigStore().get_all(PLUGIN_NAME) or {}
    except Exception:  # noqa: BLE001 — 读失败按默认值
        return {}


def _save(values: Dict[str, Any]) -> None:
    try:
        from app.plugins.managers.plugin_config_store import PluginConfigStore

        PluginConfigStore().set_values(PLUGIN_NAME, values)
    except Exception as e:  # noqa: BLE001 — 写失败不崩设置页
        logger.warning(f"[bili-scroll] 保存配置失败: {e}")


# ── 凭证与在线校验 ──────────────────────────────────────
def credential_path() -> Optional[Path]:
    try:
        from biliscroll_core.bili_impl import _cred_path

        return Path(_cred_path())
    except Exception:  # noqa: BLE001 — 回退规范路径
        try:
            from biliscroll_core.paths import plugin_data_root

            root = plugin_data_root()
            return (Path(root) / "bili_credential.json") if root else None
        except Exception:
            return None


def read_credential() -> Dict[str, Any]:
    path = credential_path()
    if not path or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 — 损坏按无凭证
        return {}


def check_online(cred: Dict[str, Any]) -> Tuple[bool, str]:
    """请求导航接口判断 cookie 是否仍有效。返回 (是否有效, 展示文案)。"""
    sessdata = str(cred.get("sessdata") or "").strip()
    if not sessdata:
        return False, "未登录：点右侧按钮扫码"
    request = urllib.request.Request(
        _NAV_URL,
        headers={
            "Cookie": f"SESSDATA={sessdata}",
            "User-Agent": _UA,
            "Referer": "https://www.bilibili.com/",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as resp:  # noqa: S310 — 固定 https 域名
            payload = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001 — 网络失败与未登录分开表述
        return False, f"无法校验（网络问题：{type(e).__name__}）"
    data = payload.get("data") or {}
    if payload.get("code") == 0 and data.get("isLogin"):
        name = str(data.get("uname") or "").strip() or "已登录"
        return True, f"已登录：{name}（UID {data.get('mid', '?')}）"
    return False, "凭证已失效，请重新扫码登录"


def _login_once() -> str:
    from .mcp_handler import mcp_handle

    result = mcp_handle({"name": "bili_login", "arguments": {}})
    text = str(result.get("text") or "")
    if result.get("isError"):
        raise RuntimeError(text or "生成二维码失败")
    return text


def _login_check() -> Tuple[bool, str]:
    from .mcp_handler import mcp_handle

    result = mcp_handle({"name": "bili_login_check", "arguments": {}})
    text = str(result.get("text") or "")
    if result.get("isError"):
        raise RuntimeError(text or "检查登录状态失败")
    try:
        payload = json.loads(text)
    except Exception:  # noqa: BLE001 — 非 JSON 视为未完成
        return False, text
    return str(payload.get("status") or "") in ("done", "success", "logged_in"), text


# ── 后台任务 ────────────────────────────────────────────
class _Fn(QObject):
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            self.done.emit(self._fn())
        except Exception as e:  # noqa: BLE001 — 错误回主线程展示
            self.failed.emit(f"{type(e).__name__}: {e}")


def _left(widget: QWidget, parent: QWidget) -> QWidget:
    """定宽控件包一层，保证贴左而不是被 stretch 推到行尾。"""
    box = QWidget(parent)
    line = QHBoxLayout(box)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(8)
    line.addWidget(widget, 0, Qt.AlignLeft)
    line.addStretch(1)
    return box


def _row(label: str, widget: QWidget, parent: QWidget, hint: str = "") -> QWidget:
    """一行：label 最小宽 + 控件撑满 + 可选说明。"""
    row = QWidget(parent)
    outer = QVBoxLayout(row)
    outer.setContentsMargins(0, 6, 0, 6)
    outer.setSpacing(4)
    line = QHBoxLayout()
    line.setSpacing(12)
    text = BodyLabel(label, row)
    text.setMinimumWidth(_LABEL_MIN_WIDTH)
    line.addWidget(text, 0, Qt.AlignVCenter)
    line.addWidget(widget, 1)
    outer.addLayout(line)
    if hint:
        tip = CaptionLabel(hint, row)
        tip.setWordWrap(True)
        tip.setContentsMargins(_LABEL_MIN_WIDTH + 12, 0, 0, 0)
        outer.addWidget(tip)
    return row


def _group(title: str, parent: QWidget) -> Tuple[QFrame, QVBoxLayout]:
    """分组容器：标题 + 细边框卡片，内部可放任意行控件。

    不用 SettingCardGroup：它只接受 SettingCard 子类（普通行控件无高度语义），
    且稳定可用的写入接口是 addSettingCard，没有 viewLayout。
    """
    frame = QFrame(parent)
    frame.setObjectName("biliSettingsGroup")
    frame.setAttribute(Qt.WA_StyledBackground, True)
    try:
        from qfluentwidgets import isDarkTheme

        dark = isDarkTheme()
    except Exception:  # noqa: BLE001
        dark = True
    frame.setStyleSheet(
        "QFrame#biliSettingsGroup {"
        f" background: {'rgba(255,255,255,0.03)' if dark else 'rgba(255,255,255,0.72)'};"
        f" border: 1px solid {'rgba(255,255,255,0.09)' if dark else 'rgba(0,0,0,0.08)'};"
        " border-radius: 10px; }"
    )
    outer = QVBoxLayout(frame)
    outer.setContentsMargins(16, 12, 16, 14)
    outer.setSpacing(2)
    head = BodyLabel(title, frame)
    head.setStyleSheet("font-size: 14px; font-weight: 650;")
    outer.addWidget(head)
    outer.addSpacing(2)
    return frame, outer


# ── 卡片 ────────────────────────────────────────────────
class BiliSettingsCard(QWidget):
    """设置 → 插件 → B站日报：账号、模型、筛选、自动化、评论。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._thread: Optional[QThread] = None
        self._worker: Optional[_Fn] = None
        self._poll_timer: Optional[QTimer] = None
        self._poll_left = 0
        self._polling = False
        self._cfg = _load_all()
        self._setup_ui()
        self._fill_account()
        self._fill_models()

    # ── 组装 ────────────────────────────────────────────
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 8, 0, 8)
        root.setSpacing(14)

        # 账号
        account, account_layout = _group("账号", self)
        self._status_lb = CaptionLabel("正在检查登录状态…", self)
        self._status_lb.setWordWrap(True)
        self._login_btn = PrimaryPushButton("扫码登录", self)
        self._login_btn.setFixedWidth(120)
        self._login_btn.clicked.connect(self.start_login)
        self._refresh_btn = ToolButton(FluentIcon.SYNC, self)
        self._refresh_btn.setToolTip("重新校验登录有效性")
        self._refresh_btn.clicked.connect(self.refresh_status)
        status_box = QWidget(self)
        status_line = QHBoxLayout(status_box)
        status_line.setContentsMargins(0, 0, 0, 0)
        status_line.setSpacing(8)
        status_line.addWidget(self._status_lb, 1)
        status_line.addWidget(self._refresh_btn, 0)
        status_line.addWidget(self._login_btn, 0)
        account_layout.addWidget(_row("登录状态", status_box, self))
        self._account_group = account
        root.addWidget(account)

        # 值班模型
        model_group, model_layout = _group("值班模型", self)
        self._model_combo = EditableComboBox(self)
        self._model_combo.setPlaceholderText("跟随当前对话模型")
        self._model_combo.currentIndexChanged.connect(self._on_model_changed)
        self._model_combo.textChanged.connect(self._on_model_text)
        refresh_models = PushButton("刷新列表", self)
        refresh_models.setFixedWidth(96)
        refresh_models.clicked.connect(self._fill_models)
        model_box = QWidget(self)
        model_line = QHBoxLayout(model_box)
        model_line.setContentsMargins(0, 0, 0, 0)
        model_line.setSpacing(8)
        model_line.addWidget(self._model_combo, 1)
        model_line.addWidget(refresh_models, 0)
        model_layout.addWidget(
            _row(
                "使用模型",
                model_box,
                self,
                "留空则跟随当前对话模型；下拉项来自已配置的服务商，也支持手填「服务商:模型名」",
            )
        )
        root.addWidget(model_group)

        # 内容筛选
        pick_group, pick_layout = _group("内容筛选", self)
        self._keywords = TextEdit(self)
        self._keywords.setMinimumHeight(88)
        self._keywords.setPlaceholderText("一行一个关键词；留空则刷账号首页推荐流")
        self._keywords.textChanged.connect(lambda: self._debounce(lambda: self._save_text("keywords", self._keywords.toPlainText())))
        pick_layout.addWidget(_row("关注关键词", self._keywords, self))
        self._quota = SpinBox(self)
        self._quota.setRange(0, 50)
        self._quota.setSuffix(" 条 / 天")
        self._quota.setFixedWidth(180)
        self._quota.valueChanged.connect(lambda v: _save({"daily_quota": int(v)}))
        pick_layout.addWidget(_row("每天最多挑几条", _left(self._quota, self), self, "0 表示只在手动点「跑一轮」时才挑"))
        self._report_mode = ComboBox(self)
        for value, label in _REPORT_MODES:
            self._report_mode.addItem(label, userData=value)
        self._report_mode.currentIndexChanged.connect(
            lambda _i: _save({"report_mode": self._report_mode.currentData()})
        )
        pick_layout.addWidget(_row("日报详细程度", self._report_mode, self))
        root.addWidget(pick_group)

        # 自动运行
        auto_group, auto_layout = _group("自动运行", self)
        self._peak_noon = SwitchButton(self)
        self._peak_noon.setOnText("开")
        self._peak_noon.setOffText("关")
        self._peak_noon.checkedChanged.connect(lambda v: _save({"peak_noon": bool(v)}))
        auto_layout.addWidget(_row("午间窗口（12:00–14:00）", _left(self._peak_noon, self), self))
        self._peak_night = SwitchButton(self)
        self._peak_night.setOnText("开")
        self._peak_night.setOffText("关")
        self._peak_night.checkedChanged.connect(lambda v: _save({"peak_night": bool(v)}))
        auto_layout.addWidget(_row("夜间窗口（18:00–次日 09:00）", _left(self._peak_night, self), self))
        root.addWidget(auto_group)

        # 自动评论
        comment_group, comment_layout = _group("自动评论", self)
        self._auto_comment = SwitchButton(self)
        self._auto_comment.setOnText("开")
        self._auto_comment.setOffText("关")
        self._auto_comment.checkedChanged.connect(self._on_auto_comment)
        comment_layout.addWidget(
            _row("自动评论并 @ 我", _left(self._auto_comment, self), self, "用你的账号发言，默认关闭；关闭时下面两项置灰")
        )
        self._comment_quota = SpinBox(self)
        self._comment_quota.setRange(1, 20)
        self._comment_quota.setSuffix(" 条 / 轮")
        self._comment_quota.setFixedWidth(180)
        self._comment_quota.valueChanged.connect(lambda v: _save({"comment_quota": int(v)}))
        self._comment_quota_row = _row("每轮最多几条", _left(self._comment_quota, self), self)
        comment_layout.addWidget(self._comment_quota_row)
        self._delivery = ComboBox(self)
        for value, label in _DELIVERIES:
            self._delivery.addItem(label, userData=value)
        self._delivery.currentIndexChanged.connect(
            lambda _i: _save({"delivery": self._delivery.currentData()})
        )
        self._delivery_row = _row("投递方式", self._delivery, self)
        comment_layout.addWidget(self._delivery_row)
        self._uid = LineEdit(self)
        self._uid.setPlaceholderText("自动评论 @ 与私信投递的目标 UID")
        self._uid.textChanged.connect(lambda: self._debounce(lambda: self._save_text("my_uid", self._uid.text())))
        self._uid_row = _row("我的 B站 UID", self._uid, self)
        comment_layout.addWidget(self._uid_row)
        self._reply_comments = SwitchButton(self)
        self._reply_comments.setOnText("开")
        self._reply_comments.setOffText("关")
        self._reply_comments.checkedChanged.connect(lambda v: _save({"reply_comments": bool(v)}))
        comment_layout.addWidget(_row("回复别人对我的回复", _left(self._reply_comments, self), self))
        root.addWidget(comment_group)

        # 说话风格
        style_group, style_layout = _group("说话风格", self)
        self._persona = TextEdit(self)
        self._persona.setMinimumHeight(88)
        self._persona.setPlaceholderText("留空按中性口吻，例如：简短、具体、不吹捧")
        self._persona.textChanged.connect(lambda: self._debounce(lambda: self._save_text("persona", self._persona.toPlainText())))
        style_layout.addWidget(_row("它按什么说话", self._persona, self))
        root.addWidget(style_group)

        root.addStretch(1)
        self._json_timer: Optional[QTimer] = None
        self._pending_save: Optional[Callable[[], None]] = None
        self._apply_values()

    # ── 回显 ────────────────────────────────────────────
    def _apply_values(self):
        cfg = self._cfg
        widgets = [
            (self._keywords, cfg.get("keywords", "")),
            (self._persona, cfg.get("persona", "")),
            (self._uid, cfg.get("my_uid", "")),
        ]
        for widget, value in widgets:
            widget.blockSignals(True)
            widget.setPlainText(str(value or "")) if isinstance(value, str) and isinstance(widget, TextEdit) else widget.setText(str(value or ""))
            widget.blockSignals(False)
        numeric = [
            (self._quota, cfg.get("daily_quota", 5) or 0),
            (self._comment_quota, cfg.get("comment_quota", 1) or 1),
        ]
        for widget, value in numeric:
            widget.blockSignals(True)
            widget.setValue(int(float(value or 0)))
            widget.blockSignals(False)
        switches = [
            (self._peak_noon, cfg.get("peak_noon")),
            (self._peak_night, cfg.get("peak_night")),
            (self._auto_comment, cfg.get("auto_comment")),
            (self._reply_comments, cfg.get("reply_comments")),
        ]
        for widget, value in switches:
            widget.blockSignals(True)
            widget.setChecked(str(value).lower() in ("1", "true", "yes", "on"))
            widget.blockSignals(False)
        for combo, value in (
            (self._report_mode, cfg.get("report_mode") or "full"),
            (self._delivery, cfg.get("delivery") or "comment"),
        ):
            index = combo.findData(value)
            combo.blockSignals(True)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)
        self._sync_comment_enabled()

    def _debounce(self, fn: Callable[[], None]):
        """文本框改动 500ms 防抖写盘；只保留最后一次回调，避免连接累积。"""
        if self._json_timer is None:
            self._json_timer = QTimer(self)
            self._json_timer.setSingleShot(True)
            self._json_timer.setInterval(500)
            self._json_timer.timeout.connect(self._flush_pending)
        self._pending_save = fn
        self._json_timer.start()

    def _flush_pending(self):
        fn = getattr(self, "_pending_save", None)
        self._pending_save = None
        if callable(fn):
            fn()

    def _save_text(self, key: str, text: str):
        _save({key: (text or "").strip()})

    def _on_auto_comment(self, checked: bool):
        _save({"auto_comment": bool(checked)})
        self._sync_comment_enabled()

    def _sync_comment_enabled(self):
        enabled = self._auto_comment.isChecked()
        for row in (self._comment_quota_row, self._delivery_row, self._uid_row):
            row.setEnabled(enabled)
            row.setStyleSheet("" if enabled else "color: rgba(128,128,128,0.6);")

    # ── 账号 ────────────────────────────────────────────
    def _fill_account(self):
        self.refresh_status()

    def refresh_status(self):
        self._status_lb.setText("正在检查登录状态…")
        cred = read_credential()
        self._start(lambda: check_online(cred), self._on_status)

    def _on_status(self, result):
        ok, text = result
        self._status_lb.setText(text)
        self._status_lb.setStyleSheet("color: #2ea043;" if ok else "color: #d29922;")
        self._login_btn.setText("重新扫码" if ok else "扫码登录")

    def start_login(self):
        if self._polling:
            return
        self._polling = True
        self._login_btn.setEnabled(False)
        self._login_btn.setText("等待扫码")
        self._status_lb.setText("二维码已弹出，请用 B站 App 扫码")
        self._start(_login_once, lambda _t: self._begin_poll())

    def _begin_poll(self):
        self._poll_left = 60
        if self._poll_timer is None:
            self._poll_timer = QTimer(self)
            self._poll_timer.setInterval(2000)
            self._poll_timer.timeout.connect(self._poll_once)
        self._poll_timer.start()
        self._poll_once()

    def _poll_once(self):
        if not self._polling:
            return
        self._poll_left -= 1
        if self._poll_left <= 0:
            self._finish_login("扫码超时，请重新点「扫码登录」", False)
            return
        if self._thread is not None:
            return
        self._start(_login_check, self._on_login_check)

    def _on_login_check(self, result):
        done, text = result
        if done:
            self._finish_login("登录成功，正在校验有效性…", True)
        elif "timeout" in text.lower() or "expired" in text.lower():
            self._finish_login("二维码已过期，请重新扫码", False)

    def _finish_login(self, message: str, success: bool):
        self._polling = False
        if self._poll_timer is not None:
            self._poll_timer.stop()
        self._login_btn.setEnabled(True)
        self._status_lb.setText(message)
        if success:
            self.refresh_status()
        else:
            self._login_btn.setText("扫码登录")

    # ── 模型下拉 ────────────────────────────────────────
    def _models_from_host(self) -> List[Tuple[str, str]]:
        try:
            from app.plugins.sdk import pool_for

            pool = pool_for(plugin=PLUGIN_NAME, surface="ui")
            if pool is None or "provider.list" not in pool or "model.enumerate" not in pool:
                return []
            out: List[Tuple[str, str]] = []
            for provider in pool["provider.list"]() or []:
                pid = str(provider.get("id") or "")
                if not pid:
                    continue
                pname = str(provider.get("display_name") or provider.get("provider_name") or pid)
                try:
                    models = pool["model.enumerate"](pid) or []
                except Exception as e:  # noqa: BLE001 — 单个服务商失败不影响其他
                    logger.debug(f"[bili-scroll] 枚举 {pid} 模型失败: {e}")
                    continue
                for model in models:
                    name = str(model.get("name") or "")
                    if name:
                        out.append((f"{pid}:{name}", f"{pname} · {name}"))
            return out
        except Exception as e:  # noqa: BLE001 — 拉取失败退化为手填
            logger.debug(f"[bili-scroll] 拉取模型列表失败: {e}")
            return []

    def _fill_models(self, *_args):
        current = str(_load_all().get("duty_model") or "")
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        self._model_combo.addItem("跟随当前对话模型", userData=_FOLLOW_CURRENT)
        for value, label in self._models_from_host():
            self._model_combo.addItem(label, userData=value)
        index = self._model_combo.findData(current)
        if index >= 0:
            self._model_combo.setCurrentIndex(index)
        elif current:
            # 存的是「配置ID:模型名」时，尽量显示成可读的服务商名
            self._model_combo.setText(current)
        else:
            self._model_combo.setCurrentIndex(0)
        self._model_combo.blockSignals(False)
        try:
            self._model_combo.setCursorPosition(0)
        except Exception:  # noqa: BLE001 — 不可编辑时无光标
            pass

    def _on_model_changed(self, _index: int):
        data = self._model_combo.currentData()
        if data is None:
            return
        _save({"duty_model": "" if data == _FOLLOW_CURRENT else str(data)})

    def _on_model_text(self, text: str):
        if self._model_combo.currentData() in (None, _FOLLOW_CURRENT):
            _save({"duty_model": (text or "").strip()})

    # ── 线程 ────────────────────────────────────────────
    def _start(self, fn, on_done):
        worker = _Fn(fn)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(lambda value: self._on_done(value, on_done))
        worker.failed.connect(self._on_failed)
        worker.done.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.done.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(lambda: self._cleanup(thread))
        self._worker, self._thread = worker, thread
        thread.start()

    def _on_done(self, value, on_done):
        try:
            on_done(value)
        except Exception as e:  # noqa: BLE001 — 回调异常不阻断轮询
            logger.exception(f"[bili-scroll] 设置卡回调失败: {e}")

    def _on_failed(self, message: str):
        logger.warning(f"[bili-scroll] 账号操作失败: {message}")
        if self._polling:
            self._finish_login(f"操作失败：{message}", False)
        else:
            self._status_lb.setText(f"操作失败：{message}")
            self._login_btn.setEnabled(True)
            self._login_btn.setText("扫码登录")

    def _cleanup(self, thread):
        if self._thread is thread:
            self._thread = None
            self._worker = None
        thread.deleteLater()
