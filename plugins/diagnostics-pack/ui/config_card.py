# -*- coding: utf-8 -*-
"""诊断包设置卡：选项 + 立即导出 + 打开目录。

自绘而非 E1 自动卡：选项少但需要「导出 / 打开目录」动作与结果回显，
自动卡的 action 字段只能调已注册工具，且无法展示导出结果路径。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from .settings_store import load_settings, save_settings

PLUGIN_NAME = "diagnostics-pack"
_LABEL_MIN_WIDTH = 120
_BTN_WIDTH = 120

_UI_AVAILABLE = False
try:  # 缺 qfluentwidgets 时整卡退化为占位类，插件其余组件不受影响
    from PyQt5.QtCore import Qt, QUrl
    from PyQt5.QtGui import QDesktopServices
    from PyQt5.QtWidgets import QApplication, QHBoxLayout, QWidget
    from qfluentwidgets import (
        BodyLabel,
        CaptionLabel,
        ExpandSettingCard,
        FluentIcon,
        PrimaryPushButton,
        PushButton,
        SpinBox,
        SwitchButton,
    )

    _UI_AVAILABLE = True
except Exception:  # noqa: BLE001
    ExpandSettingCard = None  # type: ignore


def _notify(title: str, message: str, kind: str = "success") -> None:
    try:
        from app.plugins.sdk import caps_for

        notify = caps_for("ui.notify", plugin=PLUGIN_NAME, surface="ui")
        if notify is not None:
            notify(title, message, kind=kind, duration=5000)
            return
    except Exception as exc:  # noqa: BLE001 — 通知失败只影响提示
        logger.debug(f"[diagnostics-pack] ui.notify 不可用: {exc}")
    logger.info(f"[diagnostics-pack] {title}: {message}")


def _fmt_size(num: int) -> str:
    if num >= 1024 ** 2:
        return f"{num / 1024 ** 2:.1f} MB"
    return f"{max(1, num // 1024)} KB"


if _UI_AVAILABLE:

    class _FieldRow(QWidget):
        """字段行：定宽 label + 控件撑满（与宿主设置卡口径一致）。"""

        def __init__(self, label_text: str, control: Any, parent=None):
            super().__init__(parent)
            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 4, 0, 4)
            layout.setSpacing(12)
            label = BodyLabel(label_text, self)
            label.setMinimumWidth(_LABEL_MIN_WIDTH)
            layout.addWidget(label, 0, Qt.AlignLeft | Qt.AlignVCenter)
            layout.addWidget(control, 1)

    class DiagnosticsCard(ExpandSettingCard):
        """诊断包配置卡（构造签名必须是 (parent=None)）。"""

        def __init__(self, parent=None):
            icon = getattr(FluentIcon, "DEVELOPER_TOOLS", None) or getattr(FluentIcon, "SETTING")
            super().__init__(
                icon,
                "诊断包",
                "打包最近日志、崩溃现场、系统与插件清单、脱敏配置；排查异常时先导一份",
                parent,
            )
            self.viewLayout.setContentsMargins(48, 8, 48, 8)
            self.viewLayout.setSpacing(4)

            from drifox_diag_pack.host_env import resolve_data_dir

            self._data_dir = resolve_data_dir("ui")
            self._settings = load_settings(self._data_dir)
            self._worker = None
            self._last_path = ""

            # ── 包含崩溃 dump ──
            self._dumps_switch = SwitchButton(self.view)
            self._dumps_switch.setChecked(bool(self._settings["include_crash_dumps"]))
            self._dumps_switch.setToolTip("minidump 体积较大，且可能含崩溃瞬间的内存片段")
            self._dumps_switch.checkedChanged.connect(self._on_option_changed)
            self.viewLayout.addWidget(_FieldRow("包含崩溃 dump", self._dumps_switch, self.view))

            # ── 体积上限 ──
            self._max_spin = SpinBox(self.view)
            self._max_spin.setRange(5, 1000)
            self._max_spin.setSuffix(" MB")
            self._max_spin.setValue(int(self._settings["max_mb"]))
            self._max_spin.setToolTip("未压缩体积预算，超出部分跳过并在包内 metadata.json 记录原因")
            self._max_spin.valueChanged.connect(self._on_option_changed)
            self.viewLayout.addWidget(_FieldRow("单包体积上限", self._max_spin, self.view))

            # ── 保留份数 ──
            self._keep_spin = SpinBox(self.view)
            self._keep_spin.setRange(1, 50)
            self._keep_spin.setSuffix(" 份")
            self._keep_spin.setValue(int(self._settings["keep_runs"]))
            self._keep_spin.setToolTip("只清理本插件生成的包，按时间保留最新若干份")
            self._keep_spin.valueChanged.connect(self._on_option_changed)
            self.viewLayout.addWidget(_FieldRow("历史包保留", self._keep_spin, self.view))

            # ── 动作行 ──
            actions = QWidget(self.view)
            action_layout = QHBoxLayout(actions)
            action_layout.setContentsMargins(0, 8, 0, 0)
            action_layout.setSpacing(12)
            action_layout.addStretch(1)
            self._open_btn = PushButton("打开导出目录", actions)
            self._open_btn.setFixedWidth(_BTN_WIDTH + 20)
            self._open_btn.clicked.connect(self._on_open_dir)
            self._export_btn = PrimaryPushButton("立即导出", actions)
            self._export_btn.setFixedWidth(_BTN_WIDTH)
            self._export_btn.clicked.connect(self._on_export)
            action_layout.addWidget(self._open_btn)
            action_layout.addWidget(self._export_btn)
            self.viewLayout.addWidget(actions)

            # ── 状态与隐私提示 ──
            self._status = CaptionLabel("尚未导出", self.view)
            self._status.setStyleSheet("color: #8a8a8a;")
            self.viewLayout.addWidget(self._status)

            privacy = CaptionLabel(
                "包内含本机路径、用户名与日志片段；配置与日志已按常见密钥形态脱敏，"
                "公开上传前仍建议先检查。",
                self.view,
            )
            privacy.setWordWrap(True)
            privacy.setStyleSheet("color: #8a8a8a;")
            self.viewLayout.addWidget(privacy)
            self._adjustViewSize()

        # ── 选项持久化 ──
        def _current_options(self) -> dict[str, Any]:
            return {
                "include_crash_dumps": bool(self._dumps_switch.isChecked()),
                "max_mb": int(self._max_spin.value()),
                "keep_runs": int(self._keep_spin.value()),
            }

        def _on_option_changed(self, *_args) -> None:
            self._settings = self._current_options()
            try:
                save_settings(self._data_dir, self._settings)
            except OSError as exc:
                logger.warning(f"[diagnostics-pack] 选项保存失败: {exc}")

        # ── 导出 ──
        def _on_export(self) -> None:
            if self._worker is not None and self._worker.isRunning():
                return
            self._export_btn.setEnabled(False)
            self._export_btn.setText("导出中…")
            self._status.setText("正在打包…")
            self._status.setStyleSheet("color: #8a8a8a;")
            from .export_runner import start_export

            self._worker = start_export(
                self,
                data_dir=self._data_dir,
                options=self._current_options(),
                on_done=self._on_export_done,
            )

        def _on_export_done(self, result: dict) -> None:
            self._export_btn.setEnabled(True)
            self._export_btn.setText("立即导出")
            if not result.get("ok"):
                message = str(result.get("error") or "未知错误")
                self._status.setText(f"导出失败：{message}")
                self._status.setStyleSheet("color: #e5484d;")
                _notify("诊断包导出失败", message, kind="error")
                return

            path = str(result["path"])
            self._last_path = path
            name = Path(path).name
            self._status.setText(
                f"已导出 {name} · {_fmt_size(int(result['size']))} · "
                f"{result['entries']} 条目 · 脱敏 {result['masked_hits']} 处 · "
                f"{result['duration_ms']} ms"
            )
            self._status.setToolTip(path)
            self._status.setStyleSheet("color: #3ea76a;")
            _notify("诊断包已生成", f"{name}（{_fmt_size(int(result['size']))}）", kind="success")

        def _on_open_dir(self) -> None:
            out_dir = self._data_dir / "diagnostics"
            out_dir.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(out_dir)))

        # ── 展开高度（对齐 settings-card.md 口径） ──
        def _adjustViewSize(self) -> None:
            height = self.viewLayout.sizeHint().height()
            try:
                self.spaceWidget.setFixedHeight(0)
            except Exception:  # noqa: BLE001 — 旧宿主无该成员
                pass
            self.setFixedHeight(self.card.height() + (height if self.isExpand else 0))

        def setExpand(self, isExpand: bool) -> None:
            if self.isExpand == isExpand:
                return
            self.isExpand = isExpand
            self.setProperty("isExpand", isExpand)
            self.setStyle(QApplication.style())
            self.card.expandButton.setExpand(isExpand)
            self._adjustViewSize()

else:

    class DiagnosticsCard:  # type: ignore[no-redef]
        def __init__(self, parent=None):
            raise RuntimeError("qfluentwidgets 不可用，无法构建诊断包设置卡")
