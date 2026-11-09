# -*- coding: utf-8 -*-
"""gateway-qq 自绘设置卡：扫码绑定 + 凭据显示 + 网关开关。

为什么自绘：扫码绑定要弹二维码并持续轮询（创建绑定任务 → 展示 → 轮询确认 →
解密回传凭据 → 写配置），宿主 E1 自动卡的 action 字段只能「调一个已注册工具」，
本插件不提供工具组件。priority=1 覆盖 E1 自动卡。

布局口径与 gateway-wechat 同构：label 定宽 120 + 控件撑满，底部按钮右对齐定宽。
"""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

_UI_AVAILABLE = False
try:  # 宿主缺 qfluentwidgets 时整卡退化为占位类，插件其余组件不受影响
    from PyQt5.QtCore import QObject, Qt, QThread, QTimer, pyqtProperty, pyqtSignal
    from PyQt5.QtGui import QPixmap
    from PyQt5.QtWidgets import (
        QApplication,
        QDialog,
        QHBoxLayout,
        QLabel,
        QVBoxLayout,
        QWidget,
    )
    from qfluentwidgets import (
        BodyLabel,
        CaptionLabel,
        ExpandSettingCard,
        FluentIcon,
        IndeterminateProgressBar,
        PasswordLineEdit,
        PrimaryPushButton,
        PushButton,
        SwitchButton,
    )

    _UI_AVAILABLE = True
except Exception:  # noqa: BLE001
    ExpandSettingCard = None  # type: ignore

from .login import (  # noqa: E402 — 须在 _UI_AVAILABLE 探测后导入，避免无 Qt 环境连锁失败
    POLL_INTERVAL,
    PLUGIN_NAME,
    fetch_qr,
    poll_once,
    save_credentials,
    wait_gateway_connected,
)

_LABEL_MIN_WIDTH = 120
_QR_DISPLAY_WIDTH = 420
_SCAN_BTN_WIDTH = 120
_MAX_POLL_SECONDS = 300  # 扫码窗口兜底上限


def _read_config() -> dict:
    from app.plugins.managers.plugin_config_store import PluginConfigStore

    store = PluginConfigStore()
    return {
        "enabled": bool(store.get(PLUGIN_NAME, "enabled")),
        "appid": str(store.get(PLUGIN_NAME, "appid") or ""),
        "app_secret": str(store.get(PLUGIN_NAME, "app_secret") or ""),
    }


def _write_config(values: dict) -> None:
    from app.plugins.managers.plugin_config_store import PluginConfigStore

    PluginConfigStore().set_values(PLUGIN_NAME, values)


def _apply_gateway_toggle(enabled: bool) -> None:
    """开关切换 → 启停本插件注册的网关平台（manager 未初始化时交由启动期兜底）"""
    try:
        from app.gateway.manager import get_platform_manager
        from app.plugins.registries.gateway_platform_registry import GatewayPlatformRegistry

        mgr = get_platform_manager()
        if mgr is None:
            return
        src = f"plugin:{PLUGIN_NAME}"
        for d in GatewayPlatformRegistry.get_instance().list_platforms():
            if d.source != src:
                continue
            if enabled:
                mgr.start_platform_async(d.platform_id)
            else:
                mgr.stop_platform(d.platform_id)
    except Exception as e:  # noqa: BLE001 — 启停失败不阻断配置保存
        logger.warning(f"[{PLUGIN_NAME}] 网关启停失败: {e}")


if _UI_AVAILABLE:

    # 存活的轮询线程强引用（QThread 被 GC 会崩：Destroyed while thread is still running）
    _WORKERS: set = set()

    class _CardHeightDriver(QObject):
        """把动画值写成卡片 fixedHeight（QPropertyAnimation 不能直接驱动 setFixedHeight）。"""

        def __init__(self, card):
            super().__init__(card)
            self._card = card
            self._value = 0

        def _get_value(self) -> int:
            return self._value

        def _set_value(self, value) -> None:
            self._value = int(value)
            try:
                self._card.setFixedHeight(self._value)
            except RuntimeError:  # 卡片已销毁（设置面板关闭）
                pass

        value = pyqtProperty(int, _get_value, _set_value)

    def _animate_card_height(card, target: int, duration: int = 180) -> None:
        from PyQt5.QtCore import QEasingCurve, QPropertyAnimation

        ani = getattr(card, "_expand_height_ani", None)
        if ani is None:
            driver = _CardHeightDriver(card)
            ani = QPropertyAnimation(driver, b"value", card)
            ani.setDuration(duration)
            ani.setEasingCurve(QEasingCurve.OutCubic)
            card._expand_height_driver = driver
            card._expand_height_ani = ani
        ani.stop()
        ani.setStartValue(int(card.height()))
        ani.setEndValue(max(0, int(target)))
        ani.start()

    class _FieldRow(QWidget):
        """字段行：左侧定宽 label，右侧控件撑满剩余宽度。"""

        def __init__(self, label_text: str, control: Any, parent=None):
            super().__init__(parent)
            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 4, 0, 4)
            layout.setSpacing(12)
            label = BodyLabel(label_text, self)
            label.setMinimumWidth(_LABEL_MIN_WIDTH)
            layout.addWidget(label, 0, Qt.AlignLeft | Qt.AlignVCenter)
            layout.addWidget(control, 1)

    class _LoginWorker(QThread):
        """后台扫码流程：创建绑定任务 → 展示二维码 → 轮询直到 COMPLETED/EXPIRED。

        回传的 AppSecret 用本地 bind key 做 AES-256-GCM 端到端解密，
        key 只在本次会话内存中，不落盘。只发信号不碰控件。
        """

        qr_ready = pyqtSignal(bytes)
        status_text = pyqtSignal(str)
        finished_state = pyqtSignal(bool, str)  # (成功, 文案)

        def __init__(self, parent=None):
            super().__init__(parent)
            self._cancelled = False

        def cancel(self) -> None:
            self._cancelled = True

        def run(self) -> None:
            try:
                task_id, key, png = fetch_qr()
            except Exception as e:  # noqa: BLE001 — 取码失败一律人话回显
                self.finished_state.emit(False, f"获取二维码失败：{e}")
                return
            if self._cancelled:
                return
            self.qr_ready.emit(png)
            self.status_text.emit("请用手机 QQ 扫码，并在手机上完成机器人绑定")

            started = time.monotonic()
            failures = 0
            while True:
                if self._cancelled:
                    self.finished_state.emit(False, "已取消")
                    return
                if time.monotonic() - started > _MAX_POLL_SECONDS:
                    self.finished_state.emit(False, "等待超时，请重新点「扫码登录」")
                    return
                try:
                    data = poll_once(task_id, key)
                except Exception as e:  # noqa: BLE001 — 网络/服务端抖动继续下一轮
                    failures += 1
                    logger.debug(f"[{PLUGIN_NAME}] 扫码轮询失败（{failures}）：{e}")
                    if failures >= 10:
                        self.finished_state.emit(False, f"轮询连续失败：{e}")
                        return
                    time.sleep(POLL_INTERVAL)
                    continue
                failures = 0

                status = data["status"]
                if status == "success":
                    try:
                        tip = save_credentials(data["appid"], data["app_secret"])
                    except Exception as e:  # noqa: BLE001 — 写盘/重连失败单独提示
                        self.finished_state.emit(False, f"保存凭据失败：{e}")
                        return
                    # 凭据已落盘；等网关真正连接成功再回成功态（未启用网关时直接成功）
                    self.status_text.emit("凭据已保存，正在连接网关…")
                    if wait_gateway_connected(cancel_check=lambda: self._cancelled):
                        self.finished_state.emit(True, tip)
                    else:
                        self.finished_state.emit(
                            False,
                            "网关连接超时（凭据已保存），可稍后在网关面板查看状态",
                        )
                    return
                if status == "expired":
                    self.finished_state.emit(False, "二维码已过期，请重新点「扫码登录」")
                    return
                # waiting → 继续轮询
                time.sleep(POLL_INTERVAL)

            # pragma: no cover — 循环必经终态返回

    class _LoginDialog(QDialog):
        """二维码弹窗：图片 + 状态文案 + 轮询进度。"""

        _instances: list = []

        def __init__(self, parent=None, on_success=None):
            super().__init__(parent)
            self._on_success = on_success
            self.setWindowTitle("QQ 扫码登录")
            self.setModal(True)
            self.setMinimumWidth(480)

            layout = QVBoxLayout(self)
            layout.setSpacing(10)

            self._image_label = QLabel(self)
            self._image_label.setAlignment(Qt.AlignCenter)
            self._image_label.setMinimumHeight(120)
            self._image_label.setText("正在获取二维码…")
            layout.addWidget(self._image_label)

            self._status = BodyLabel("正在连接 QQ 开放平台…", self)
            self._status.setWordWrap(True)
            layout.addWidget(self._status)

            self._progress = IndeterminateProgressBar(self)
            self._progress.start()
            layout.addWidget(self._progress)

            btn_row = QHBoxLayout()
            btn_row.addStretch(1)
            close_btn = PushButton("关闭", self)
            close_btn.clicked.connect(self._on_close)
            btn_row.addWidget(close_btn)
            layout.addLayout(btn_row)

            self._worker = _LoginWorker()  # 无 parent：弹窗销毁后线程自己跑完退出
            self._worker.qr_ready.connect(self._on_qr)
            self._worker.status_text.connect(self._status.setText)
            self._worker.finished_state.connect(self._on_finished)
            self._worker.finished.connect(self._worker.deleteLater)
            _WORKERS.add(self._worker)
            self._worker.start()

        def _on_qr(self, png: bytes) -> None:
            try:
                pm = QPixmap()
                if pm.loadFromData(png):
                    self._image_label.setPixmap(
                        pm.scaledToWidth(_QR_DISPLAY_WIDTH, Qt.SmoothTransformation)
                    )
                    self.adjustSize()
                    return
            except Exception:  # noqa: BLE001 — 渲染失败退回文字提示
                pass
            self._image_label.setText("二维码渲染失败，请重试")

        def _on_finished(self, ok: bool, message: str) -> None:
            _WORKERS.discard(self._worker)
            self._progress.stop()
            self._progress.hide()
            self._status.setText(message)
            if not ok:
                return
            try:
                if self._on_success is not None:
                    self._on_success()
            except Exception:  # noqa: BLE001 — 回显失败不影响登录结果
                pass
            # 登录成功：短暂展示成功文案后自动关闭弹窗
            QTimer.singleShot(1000, self._auto_close)

        def _auto_close(self) -> None:
            try:
                if self.isVisible():
                    self.accept()
            except RuntimeError:  # 弹窗已销毁（延迟期间用户手动关闭）
                pass

        def _on_close(self) -> None:
            try:
                self._worker.cancel()
            except RuntimeError:  # worker 已销毁
                pass
            self.accept()

        def closeEvent(self, e):
            # accept() 不发 closeEvent（直接 done+hide），点 X 关窗走这里，取消同样幂等
            try:
                self._worker.cancel()
            except RuntimeError:  # worker 已销毁
                pass
            super().closeEvent(e)

        @classmethod
        def open_for(cls, parent, on_success=None) -> None:
            """打开弹窗（同一时刻只保留一个）"""
            for dlg in cls._instances:
                try:
                    if dlg.isVisible():
                        dlg.raise_()
                        return
                except RuntimeError:  # 已销毁
                    continue
            dlg = cls(parent, on_success=on_success)
            cls._instances.append(dlg)

            def _cleanup(*_a) -> None:
                # 不用 list.remove：宿主 AST 审计会把 remove 当删除文件操作告警
                cls._instances = [d for d in cls._instances if d is not dlg]
                dlg.setParent(None)
                dlg.deleteLater()

            dlg.finished.connect(_cleanup)
            dlg.show()

    class QqConfigCard(ExpandSettingCard):
        """QQ 网关配置卡：开关 + 扫码绑定 + 凭据显示。

        构造签名 (parent=None) 满足 register_settings_card 的 widget_class 约定。
        """

        def __init__(self, parent=None):
            super().__init__(
                FluentIcon.PEOPLE,
                "QQ 机器人配置",
                "扫码绑定后打开开关即可收发消息",
                parent,
            )
            self.viewLayout.setContentsMargins(48, 8, 48, 8)
            self.viewLayout.setSpacing(4)

            # ── 开关（挂 header 右侧，与 E1 自动卡一致） ──
            self._switch = SwitchButton(self.card)
            self._switch.setOnText("启用 QQ 网关")
            self._switch.setOffText("启用 QQ 网关")
            self._switch.checkedChanged.connect(self._on_toggle)
            self.card.addWidget(self._switch)

            # ── 扫码登录 ──
            self._scan_btn = PrimaryPushButton("扫码登录", self.view)
            self._scan_btn.setFixedWidth(_SCAN_BTN_WIDTH)
            self._scan_btn.clicked.connect(self._on_scan)
            holder = QWidget(self.view)
            holder_layout = QHBoxLayout(holder)
            holder_layout.setContentsMargins(0, 0, 0, 0)
            holder_layout.setSpacing(12)
            holder_layout.addWidget(self._scan_btn)
            holder_layout.addStretch(1)
            self.viewLayout.addWidget(_FieldRow("登录", holder, self.view))

            # ── 凭据（只读展示：写入只走扫码，避免手填格式错） ──
            self._appid_edit = PasswordLineEdit(self.view)
            self._appid_edit.setPlaceholderText("扫码登录后自动写入")
            self._appid_edit.setEnabled(False)
            self.viewLayout.addWidget(_FieldRow("AppID", self._appid_edit, self.view))

            self._app_secret_edit = PasswordLineEdit(self.view)
            self._app_secret_edit.setPlaceholderText("扫码登录后自动写入")
            self._app_secret_edit.setEnabled(False)
            self.viewLayout.addWidget(_FieldRow("AppSecret", self._app_secret_edit, self.view))

            hint = CaptionLabel(
                "扫码将绑定一个 QQ 机器人并端到端回传凭据（本地解密，不经过第三方）；"
                "也可到 q.qq.com 手动创建后填入。", self.view,
            )
            hint.setWordWrap(True)
            self.viewLayout.addWidget(_FieldRow("", hint, self.view))

            self._echo()

        # ── 回显 ────────────────────────────────────────────

        def _echo(self) -> None:
            cfg = _read_config()
            self._switch.blockSignals(True)
            self._switch.setChecked(cfg["enabled"])
            self._switch.blockSignals(False)
            self._appid_edit.setText(cfg["appid"])
            self._appid_edit.setCursorPosition(0)
            self._app_secret_edit.setText(cfg["app_secret"])
            self._app_secret_edit.setCursorPosition(0)

        # ── 事件 ────────────────────────────────────────────

        def _on_toggle(self, checked: bool) -> None:
            _write_config({"enabled": bool(checked)})
            _apply_gateway_toggle(bool(checked))

        def _on_scan(self) -> None:
            _LoginDialog.open_for(self.window(), on_success=self._on_login_success)

        def _on_login_success(self) -> None:
            self._echo()
            msg_title, msg_body = "QQ 登录成功", "凭据已保存"
            try:
                from app.plugins.sdk import caps_for

                fn = caps_for("ui.notify", plugin=PLUGIN_NAME, surface="ui")
                if callable(fn):
                    fn(msg_title, msg_body, duration=3000)
                    return
            except Exception as e:  # noqa: BLE001 — 能力池不可用走旧自绘
                logger.debug(f"[{PLUGIN_NAME}] ui.notify 不可用: {e}")
            try:
                from qfluentwidgets import InfoBar, InfoBarPosition

                InfoBar.success(
                    msg_title,
                    msg_body,
                    parent=self.window(),
                    position=InfoBarPosition.TOP,
                    duration=3000,
                )
            except Exception:  # noqa: BLE001 — 通知失败不影响登录结果
                pass

        # ── 折叠高度（内联高度动画，插件不能 import 宿主的 expand_height_mixin） ──

        def _target_height(self, is_expand: bool) -> int:
            try:
                self.spaceWidget.setFixedHeight(0)
            except Exception:  # noqa: BLE001 — 旧版宿主无该成员时跳过
                pass
            return self.card.height() + (self.viewLayout.sizeHint().height() if is_expand else 0)

        def _adjustViewSize(self):
            self.setFixedHeight(self._target_height(self.isExpand))

        def setExpand(self, isExpand: bool):
            if self.isExpand == isExpand:
                return
            self.isExpand = isExpand
            self.setProperty("isExpand", isExpand)
            self.setStyle(QApplication.style())
            self.card.expandButton.setExpand(isExpand)
            _animate_card_height(self, self._target_height(isExpand))

else:  # pragma: no cover — 仅在没有 qfluentwidgets 的环境走到

    class QqConfigCard:  # type: ignore[no-redef]
        def __init__(self, parent=None):
            raise RuntimeError("qfluentwidgets 不可用，无法构建 QQ 网关配置卡")
