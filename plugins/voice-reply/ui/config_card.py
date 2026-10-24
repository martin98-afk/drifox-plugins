# -*- coding: utf-8 -*-
"""voice-reply 自绘设置卡：模型 / 音色可编辑下拉（qfluentwidgets EditableComboBox）。

为什么不用主程序 E1 自动卡（plugin.json config_schema）：
宿主 PluginConfigCard 只把字段渲染成 text/password/bool/select/number/textarea，
其中 select 是不可编辑的 ComboBox，text 是纯 LineEdit。「既能下拉选、又能手填」
需要 EditableComboBox，主程序当前没有对应字段类型（FIELD_TYPES 闭集），
故按 prompt-enhancer 的范式自绘设置卡，用更高 priority 覆盖 E1 自动卡。

音色联动：切模型 → 音色下拉整体换一批（各模型预置音色名一致，voice 值前缀不同）。
"""

from __future__ import annotations

from typing import Any, List

from loguru import logger

from .voice_presets import (
    DEFAULT_MODEL,
    DEFAULT_VOICE_NAME,
    ENDPOINT_PRESETS,
    MODEL_PRESETS,
    VoicePreset,
    default_voice_value,
    find_model,
    split_voice,
)

try:  # 宿主可能未装 qfluentwidgets（理论上必然有），缺失时降级不注册卡
    from qfluentwidgets import (
        BodyLabel,
        ComboBox,
        EditableComboBox,
        ExpandSettingCard,
        FluentIcon,
        PasswordLineEdit,
        PushButton,
    )
except Exception:  # noqa: BLE001 — 导入失败时 _ConfigCardBase 退化为空基类
    ExpandSettingCard = None  # type: ignore

_ConfigCardBase = ExpandSettingCard if ExpandSettingCard is not None else type("_CardBase", (), {})

# 输入区最小宽度：模型/音色字符串较长（FunAudioLLM/CosyVoice2-0.5B:alex 约 40 字符），
# 默认 LineEdit 宽度会截断显示，故显式放宽。
_FIELD_MIN_WIDTH = 320

# 标签列宽度（与主程序 PluginConfigCard._FieldRow 的 120 一致，视觉对齐）
_LABEL_MIN_WIDTH = 120


class _FieldRow:
    """字段行：左侧 label，右侧控件。无 Qt 时退化为占位（不会走到）。"""

    def __new__(cls, label_text: str, control: Any, parent: Any = None):  # noqa: N804
        if ExpandSettingCard is None:
            return None
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QHBoxLayout, QWidget

        row = QWidget(parent)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(12)
        label = BodyLabel(label_text, row)
        label.setObjectName("fieldLabel")
        label.setMinimumWidth(_LABEL_MIN_WIDTH)
        layout.addWidget(label, 0, Qt.AlignLeft | Qt.AlignVCenter)
        control.setMinimumWidth(_FIELD_MIN_WIDTH)
        layout.addWidget(control, 1, Qt.AlignRight)
        return row


class _VoiceConfigCard(_ConfigCardBase):
    """语音播报配置卡：引擎 + 端点 + 模型 + 音色（均可编辑下拉）+ API Key。

    保存语义与主程序 PluginConfigStore 一致：空内容 = 清除 → 回退默认。
    构造签名 (parent=None) 满足 register_settings_card 的 widget_class 约定。
    """

    def __init__(self, parent=None):
        if ExpandSettingCard is None:
            raise RuntimeError("qfluentwidgets 不可用，无法构建语音播报配置卡")
        super().__init__(
            FluentIcon.VOLUME,
            "语音播报配置",
            "本地引擎零配置；在线引擎需填 API Key",
            parent,
        )
        self.viewLayout.setContentsMargins(48, 8, 48, 8)
        self.viewLayout.setSpacing(4)

        # ── 语音引擎 ──
        self._engine_combo = ComboBox(self.view)
        self._engine_combo.addItem("本地系统语音（免费，Windows SAPI5 / macOS say）", userData="local")
        self._engine_combo.addItem("在线 API（OpenAI 兼容 /audio/speech）", userData="api")
        self._engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        self.viewLayout.addWidget(_FieldRow("语音引擎", self._engine_combo, self.view))

        # ── API 地址（可编辑下拉：端点预设 + 手填） ──
        self._url_combo = EditableComboBox(self.view)
        self._url_combo.setPlaceholderText("OpenAI 兼容 /audio/speech 端点")
        for url, label in ENDPOINT_PRESETS:
            self._url_combo.addItem(label, userData=url)
        self._url_combo.textChanged.connect(self._on_url_changed)
        self.viewLayout.addWidget(_FieldRow("API 地址", self._url_combo, self.view))

        # ── 模型（可编辑下拉：模型预设 + 手填） ──
        self._model_combo = EditableComboBox(self.view)
        self._model_combo.setPlaceholderText(DEFAULT_MODEL)
        for preset in MODEL_PRESETS:
            self._model_combo.addItem(preset.label, userData=preset.model)
        self._model_combo.currentIndexChanged.connect(self._on_model_changed)
        self._model_combo.textChanged.connect(self._on_model_text_changed)
        self.viewLayout.addWidget(_FieldRow("模型", self._model_combo, self.view))

        # ── 音色（可编辑下拉：随模型换批 + 手填） ──
        self._voice_combo = EditableComboBox(self.view)
        self._voice_combo.setPlaceholderText(default_voice_value())
        self._voice_combo.textChanged.connect(self._on_voice_changed)
        self.viewLayout.addWidget(_FieldRow("音色", self._voice_combo, self.view))

        # ── API Key ──
        self._key_edit = PasswordLineEdit(self.view)
        self._key_edit.setClearButtonEnabled(True)
        self._key_edit.setPlaceholderText("仅在线引擎需要")
        self._key_edit.editingFinished.connect(self._on_key_finished)
        self.viewLayout.addWidget(_FieldRow("API Key", self._key_edit, self.view))

        # ── 恢复默认 ──
        self._reset_btn = PushButton("恢复默认", self.view)
        self._reset_btn.clicked.connect(self._on_reset)
        self.viewLayout.addWidget(self._reset_btn)

        self._echo()

    # ── 回显 ────────────────────────────────────────────

    def _echo(self) -> None:
        """回显当前生效值（默认兜底可见）；blockSignals 阻断写盘循环。"""
        from app.plugins.managers.plugin_config_store import PluginConfigStore

        store = PluginConfigStore()
        engine = str(store.get("voice-reply", "engine") or "local")
        url = str(store.get("voice-reply", "api_url") or "")
        model = str(store.get("voice-reply", "api_model") or "") or DEFAULT_MODEL
        voice = str(store.get("voice-reply", "api_voice") or "") or default_voice_value(model)
        api_key = str(store.get("voice-reply", "api_key") or "")

        for combo, value in (
            (self._engine_combo, engine),
            (self._url_combo, url),
            (self._model_combo, model),
        ):
            combo.blockSignals(True)
            self._select_or_set_text(combo, value)
            combo.blockSignals(False)

        # 音色：先按模型重建选项，再选中（存储值里音色名可能不在新模型音色包中）
        _model, voice_name = split_voice(voice)
        self._rebuild_voices(model, select_name=voice_name or DEFAULT_VOICE_NAME)
        self._voice_combo.blockSignals(True)
        self._select_or_set_text(self._voice_combo, voice_name or voice)
        self._voice_combo.blockSignals(False)

        self._key_edit.blockSignals(True)
        self._key_edit.setText(api_key)
        self._key_edit.blockSignals(False)

    @staticmethod
    def _select_or_set_text(combo, value: str) -> None:
        """下拉里有该项则选中，否则直接填文本（手填值回显）。

        EditableComboBox.findData 只在预设项里找，找不到时 setText 让用户看到
        自己的历史值，避免回显把配置「洗」成第一项。
        """
        index = combo.findData(value) if value else -1
        if index >= 0:
            combo.setCurrentIndex(index)
        else:
            combo.setText(value or "")

    # ── 音色包重建 ──────────────────────────────────────

    def _rebuild_voices(self, model: str, select_name: str = "") -> None:
        """按模型重建音色下拉项（该模型无预置音色时清空，仅留手填）。"""
        preset = find_model(model)
        voices: List[VoicePreset] = preset.voices if preset else []
        self._voice_combo.blockSignals(True)
        self._voice_combo.clear()
        for vp in voices:
            self._voice_combo.addItem(vp.label, userData=vp.value)
        if voices:
            # 预置音色的 userData 存短名（alex），选中后按当前模型拼 voice 值
            target = select_name if select_name in [v.value for v in voices] else voices[0].value
            index = self._voice_combo.findData(target)
            self._voice_combo.setCurrentIndex(index if index >= 0 else 0)
        self._voice_combo.blockSignals(False)

    # ── 事件 ────────────────────────────────────────────

    def _on_engine_changed(self, _index: int) -> None:
        self._save("engine", str(self._engine_combo.currentData() or "local"))

    def _on_url_changed(self, text: str) -> None:
        """URL 变更：仅手填内容与当前预设项不同时写盘。

        EditableComboBox.textChanged 在回显 setText 时也会触发，_echo 已用
        blockSignals 拦住；用户选中预设项时 currentData 即目标值，直接写完整 URL。
        """
        index = self._url_combo.currentIndex()
        preset_url = str(self._url_combo.itemData(index)) if index >= 0 else ""
        value = text.strip() or preset_url
        if value:
            self._save("api_url", value)

    def _on_model_changed(self, _index: int) -> None:
        model = str(self._model_combo.currentData() or "")
        if not model:
            return
        self._save("api_model", model)
        self._rebuild_voices(model)
        # 切模型后音色值的前缀必须跟着换，否则 API 用旧模型音色名报错
        voice_name = str(self._voice_combo.currentData() or DEFAULT_VOICE_NAME)
        self._save("api_voice", f"{model}:{voice_name}")

    def _on_model_text_changed(self, text: str) -> None:
        """手填模型名：同步写盘（与 currentIndexChanged 互补，覆盖非预设值）。"""
        value = text.strip()
        if value:
            self._save("api_model", value)

    def _on_voice_changed(self, text: str) -> None:
        """手填/选择音色：存完整 voice 值（模型名:音色名）。

        textChanged 在手填时拿到的是用户输入（可能只写了音色短名，也可能写了
        完整值），统一按当前模型补齐前缀，兼容两种输入。
        """
        value = text.strip()
        if not value:
            return
        _, name = split_voice(value)
        self._save("api_voice", f"{self._current_model()}:{name or value}")

    def _current_model(self) -> str:
        """当前生效模型名：选中预设项取 userData，手填文本取输入内容。

        手填时 EditableComboBox.currentIndex 为 -1、currentData() 返回 None，
        若直接 fallback 到默认模型，会把用户自填的模型名洗掉，voice 前缀跟着错。
        """
        data = self._model_combo.currentData()
        if data:
            return str(data)
        return self._model_combo.text().strip() or DEFAULT_MODEL

    def _on_key_finished(self) -> None:
        self._save("api_key", self._key_edit.text().strip())

    def _on_reset(self) -> None:
        from app.plugins.managers.plugin_config_store import PluginConfigStore

        store = PluginConfigStore()
        store.set_values(
            "voice-reply",
            {
                "engine": "",
                "api_url": "",
                "api_model": "",
                "api_voice": "",
                "api_key": "",
            },
        )
        self._echo()

    # ── 存储 ────────────────────────────────────────────

    @staticmethod
    def _save(key: str, value: str) -> None:
        try:
            from app.plugins.managers.plugin_config_store import PluginConfigStore

            PluginConfigStore().set_values("voice-reply", {key: value})
        except Exception as e:  # noqa: BLE001 — 写盘失败不影响界面操作
            logger.warning(f"[voice-reply] 配置保存失败({key}): {e}")

    # ── 折叠动画（对齐主程序 PluginConfigCard 的处理） ──

    def _adjustViewSize(self):
        """空白占位置零，展开高度 = 内容高度，避免卡片关不上。"""
        if ExpandSettingCard is None:
            return
        h = self.viewLayout.sizeHint().height()
        try:
            self.spaceWidget.setFixedHeight(0)
        except Exception:  # noqa: BLE001 — 旧版宿主无该成员时跳过
            pass
        self.setFixedHeight(self.card.height() + (h if self.isExpand else 0))

    def setExpand(self, isExpand: bool):
        if ExpandSettingCard is None or self.isExpand == isExpand:
            return
        self.isExpand = isExpand
        self.setProperty("isExpand", isExpand)
        from PySide6.QtWidgets import QApplication

        self.setStyle(QApplication.style())
        self.card.expandButton.setExpand(isExpand)
        self._adjustViewSize()
