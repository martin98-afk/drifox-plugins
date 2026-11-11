# -*- coding: utf-8 -*-
"""meeting-notes 自绘设置卡：识别模型下拉、纪要模型下拉、提示词可视化编辑。

为什么不用 E1 自动卡：
- 「纪要模型」需要按用户实际配置的服务商/模型动态出下拉项，config_schema
  的 select 是静态 JSON，列不出来；
- 「纪要提示词」需要把内置模板直接铺出来让人就地微调，自动卡的空 textarea
  只会显示一行占位符，用户不知道该写什么。

保存策略与自动卡一致：改动即时落盘，无确认按钮。提示词走 600ms 防抖。
"""

from __future__ import annotations

from typing import Any, List, Tuple

from loguru import logger

_UI_AVAILABLE = False
try:
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtWidgets import QHBoxLayout, QWidget
    from qfluentwidgets import (
        BodyLabel,
        ComboBox,
        EditableComboBox,
        ExpandSettingCard,
        FluentIcon,
        HyperlinkButton,
        PasswordLineEdit,
        PushButton,
        SpinBox,
        SwitchButton,
        TextEdit,
    )

    _UI_AVAILABLE = True
except Exception:  # noqa: BLE001
    ExpandSettingCard = None  # type: ignore

PLUGIN_NAME = "meeting-notes"

_LABEL_MIN_WIDTH = 132
_SF_KEY_URL = "https://cloud.siliconflow.cn/account/ak"

# 识别模型（与 config_schema 保持一致）
_ASR_MODELS: List[Tuple[str, str]] = [
    ("XingChenAGI/XingChenASR-Diarize-V3.0", "星尘 ASR 说话人分离（免费，推荐）"),
    ("XingChenAGI/XingChenASR-V3.2", "星尘 ASR V3.2（免费，无说话人）"),
    ("FunAudioLLM/SenseVoiceSmall", "SenseVoice Small（免费，无说话人）"),
    ("Qwen/Qwen3-ASR-1.7B", "Qwen3-ASR（约 0.79 元/小时）"),
]

_FOLLOW_CURRENT = "__current__"


def _save(values: dict) -> None:
    try:
        from app.plugins.managers.plugin_config_store import PluginConfigStore

        PluginConfigStore().set_values(PLUGIN_NAME, values)
    except Exception as e:  # noqa: BLE001 — 配置写失败不崩设置页
        logger.warning(f"[meeting-notes] 保存配置失败: {e}")


def _load(key: str, default: Any = "") -> Any:
    try:
        from app.plugins.managers.plugin_config_store import PluginConfigStore

        value = PluginConfigStore().get(PLUGIN_NAME, key)
    except Exception:  # noqa: BLE001
        return default
    return default if value is None or value == "" else value


if _UI_AVAILABLE:

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

    class _InlineRow(QWidget):
        def __init__(self, control: Any, tail: Any, parent=None):
            super().__init__(parent)
            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            layout.addWidget(control, 1)
            layout.addWidget(tail, 0, Qt.AlignRight | Qt.AlignVCenter)

    class _MeetingNotesConfigCard(ExpandSettingCard):
        """会议纪要配置卡。"""

        def __init__(self, parent=None):
            super().__init__(
                FluentIcon.MICROPHONE,
                "会议纪要配置",
                "识别引擎与纪要模型：识别默认走免费的说话人分离模型，纪要跟随当前对话模型",
                parent,
            )
            self.viewLayout.setContentsMargins(48, 8, 48, 8)
            self.viewLayout.setSpacing(4)

            # ── 硅基流动 Key ──
            self._key = PasswordLineEdit(self.view)
            self._key.setClearButtonEnabled(True)
            self._key.setPlaceholderText("留空则复用「语音输入」插件的 Key")
            self._key.editingFinished.connect(
                lambda: _save({"siliconflow_api_key": self._key.text().strip()})
            )
            link = HyperlinkButton(self.view)
            link.setIcon(FluentIcon.LINK)
            link.setText("获取 Key")
            link.setUrl(_SF_KEY_URL)
            self.viewLayout.addWidget(
                _FieldRow("硅基流动 Key", _InlineRow(self._key, link, self.view), self.view)
            )

            # ── 复用开关 ──
            self._reuse = SwitchButton(self.view)
            self._reuse.checkedChanged.connect(
                lambda checked: _save({"reuse_voice_input_key": bool(checked)})
            )
            self.viewLayout.addWidget(
                _FieldRow("复用语音输入 Key", self._reuse, self.view)
            )

            # ── 识别模型 ──
            self._asr_model = ComboBox(self.view)
            for value, label in _ASR_MODELS:
                self._asr_model.addItem(label, userData=value)
            self._asr_model.currentIndexChanged.connect(self._on_asr_model_changed)
            self.viewLayout.addWidget(_FieldRow("识别模型", self._asr_model, self.view))

            # ── 切片时长 ──
            self._chunk = SpinBox(self.view)
            self._chunk.setRange(10, 60)
            self._chunk.setSingleStep(5)
            self._chunk.setSuffix(" 秒")
            self._chunk.valueChanged.connect(
                lambda v: _save({"chunk_seconds": int(v)})
            )
            self.viewLayout.addWidget(_FieldRow("切片时长", self._chunk, self.view))

            # ── 纪要生成超时 ──
            from .config import SUMMARY_TIMEOUT_MAX, SUMMARY_TIMEOUT_MIN
            self._summary_timeout = SpinBox(self.view)
            self._summary_timeout.setRange(SUMMARY_TIMEOUT_MIN, SUMMARY_TIMEOUT_MAX)
            self._summary_timeout.setSingleStep(30)
            self._summary_timeout.setSuffix(" 秒")
            self._summary_timeout.valueChanged.connect(
                lambda v: _save({"summary_timeout_sec": int(v)})
            )
            self.viewLayout.addWidget(
                _FieldRow("纪要生成超时", self._summary_timeout, self.view)
            )

            # ── 保留录音 ──
            self._keep_audio = SwitchButton(self.view)
            self._keep_audio.checkedChanged.connect(
                lambda checked: _save({"keep_audio": bool(checked)})
            )
            self.viewLayout.addWidget(_FieldRow("保留录音文件", self._keep_audio, self.view))

            # ── 纪要模型（动态枚举服务商/模型）──
            self._summary_model = EditableComboBox(self.view)
            self._summary_model.setPlaceholderText("留空 = 跟随当前对话模型")
            self._summary_model.currentIndexChanged.connect(self._on_summary_model_changed)
            self._summary_model.textChanged.connect(self._on_summary_model_text)
            refresh = PushButton("刷新", self.view)
            refresh.setFixedWidth(72)
            refresh.clicked.connect(self._fill_models)
            self.viewLayout.addWidget(
                _FieldRow(
                    "纪要模型", _InlineRow(self._summary_model, refresh, self.view), self.view
                )
            )

            # ── 纪要提示词 ──
            self._prompt = TextEdit(self.view)
            self._prompt.setMinimumHeight(220)
            self._prompt.setPlaceholderText("留空使用内置模板")
            self._prompt_timer = QTimer(self)
            self._prompt_timer.setSingleShot(True)
            self._prompt_timer.setInterval(600)
            self._prompt_timer.timeout.connect(self._save_prompt)
            self._prompt.textChanged.connect(lambda: self._prompt_timer.start())
            self.viewLayout.addWidget(_FieldRow("纪要提示词", self._prompt, self.view))

            reset_row = QWidget(self.view)
            reset_layout = QHBoxLayout(reset_row)
            reset_layout.setContentsMargins(0, 0, 0, 4)
            reset_layout.addStretch(1)
            self._reset_prompt = PushButton("恢复内置模板", reset_row)
            self._reset_prompt.clicked.connect(self._on_reset_prompt)
            reset_layout.addWidget(self._reset_prompt)
            self.viewLayout.addWidget(reset_row)

            self._echo()

        # ── 回显 ──

        def _echo(self) -> None:
            from .summary import DEFAULT_PROMPT_TEMPLATE

            self._key.blockSignals(True)
            self._key.setText(str(_load("siliconflow_api_key", "")))
            self._key.blockSignals(False)

            self._reuse.blockSignals(True)
            self._reuse.setChecked(bool(_load("reuse_voice_input_key", True)))
            self._reuse.blockSignals(False)

            model = str(_load("asr_model", _ASR_MODELS[0][0]))
            idx = self._asr_model.findData(model)
            self._asr_model.blockSignals(True)
            self._asr_model.setCurrentIndex(idx if idx >= 0 else 0)
            self._asr_model.blockSignals(False)

            self._chunk.blockSignals(True)
            try:
                self._chunk.setValue(int(_load("chunk_seconds", 20)))
            except (TypeError, ValueError):
                self._chunk.setValue(20)
            self._chunk.blockSignals(False)

            from .config import DEFAULT_SUMMARY_TIMEOUT_SEC
            self._summary_timeout.blockSignals(True)
            try:
                self._summary_timeout.setValue(
                    int(_load("summary_timeout_sec", DEFAULT_SUMMARY_TIMEOUT_SEC))
                )
            except (TypeError, ValueError):
                self._summary_timeout.setValue(DEFAULT_SUMMARY_TIMEOUT_SEC)
            self._summary_timeout.blockSignals(False)

            self._keep_audio.blockSignals(True)
            self._keep_audio.setChecked(bool(_load("keep_audio", True)))
            self._keep_audio.blockSignals(False)

            self._fill_models()

            prompt = str(_load("summary_prompt", "") or "")
            self._prompt.blockSignals(True)
            self._prompt.setPlainText(prompt or DEFAULT_PROMPT_TEMPLATE)
            self._prompt.blockSignals(False)

        # ── 纪要模型下拉 ──

        def _fill_models(self) -> None:
            current = str(_load("summary_model", "") or "")
            self._summary_model.blockSignals(True)
            self._summary_model.clear()
            self._summary_model.addItem("跟随当前对话模型", userData=_FOLLOW_CURRENT)
            for value, label in self._models_from_host():
                self._summary_model.addItem(label, userData=value)
            idx = self._summary_model.findData(current)
            if idx >= 0:
                self._summary_model.setCurrentIndex(idx)
            elif current:
                self._summary_model.setText(current)
            else:
                self._summary_model.setCurrentIndex(0)
            self._summary_model.blockSignals(False)
            self._move_cursor(self._summary_model)

        def _models_from_host(self) -> List[Tuple[str, str]]:
            """列宿主已配置的服务商与模型（失败返回空，不影响手填）。"""
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
                    # 展示名优先：display_name 是用户自定义名称，provider_name 是厂商名，
                    # 都拿不到才退回 id（不能直接把 id 摆给用户看）
                    pname = str(
                        provider.get("display_name")
                        or provider.get("provider_name")
                        or pid
                    )
                    try:
                        models = pool["model.enumerate"](pid) or []
                    except Exception as e:  # noqa: BLE001 — 单个服务商失败不影响其他
                        logger.debug(f"[meeting-notes] 枚举 {pid} 模型失败: {e}")
                        continue
                    for m in models:
                        name = str(m.get("name") or "")
                        if name:
                            label = f"{pname} · {name}"
                            out.append((f"{pid}:{name}", label))
                return out
            except Exception as e:  # noqa: BLE001
                logger.debug(f"[meeting-notes] 拉取模型列表失败: {e}")
                return []

        @staticmethod
        def _move_cursor(combo) -> None:
            try:
                combo.setCursorPosition(0)
            except Exception:  # noqa: BLE001 — 不可编辑下拉无光标
                return

        def _on_asr_model_changed(self, _index: int) -> None:
            data = self._asr_model.currentData()
            if data:
                _save({"asr_model": str(data)})

        def _on_summary_model_changed(self, _index: int) -> None:
            data = self._summary_model.currentData()
            if data is None:
                return
            _save({"summary_model": "" if data == _FOLLOW_CURRENT else str(data)})

        def _on_summary_model_text(self, text: str) -> None:
            # 手填模型名时也落盘（可编辑下拉）
            if self._summary_model.currentData() in (None, _FOLLOW_CURRENT):
                _save({"summary_model": (text or "").strip()})

        # ── 提示词 ──

        def _save_prompt(self) -> None:
            from .summary import DEFAULT_PROMPT_TEMPLATE

            text = self._prompt.toPlainText().strip()
            # 与内置模板完全一致时存空，跟随未来版本的内置模板更新
            _save({"summary_prompt": "" if text == DEFAULT_PROMPT_TEMPLATE.strip() else text})

        def _on_reset_prompt(self) -> None:
            from .summary import DEFAULT_PROMPT_TEMPLATE

            self._prompt.blockSignals(True)
            self._prompt.setPlainText(DEFAULT_PROMPT_TEMPLATE)
            self._prompt.blockSignals(False)
            _save({"summary_prompt": ""})
