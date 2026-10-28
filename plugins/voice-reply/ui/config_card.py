# -*- coding: utf-8 -*-
"""voice-reply 自绘设置卡：引擎 / 服务商 / 地址 / 模型 / 音色 / API Key。

为什么不用主程序 E1 自动卡（plugin.json config_schema）：
宿主 PluginConfigCard 只把字段渲染成 text/password/bool/select/number/textarea，
其中 select 是不可编辑的 ComboBox，text 是纯 LineEdit。「既能下拉选、又能手填」
需要 EditableComboBox，主程序当前没有对应字段类型（FIELD_TYPES 闭集），
故按 prompt-enhancer 的范式自绘设置卡，用更高 priority 覆盖 E1 自动卡。

布局口径（与宿主 PluginConfigCard 一致）：每行「定宽 label + 控件撑满剩余宽度」，
控件不再右对齐限宽，避免长模型名/平台名被裁成一截。

「服务商」是纯粹的界面辅助行，不落盘：选中即把端点填进「API 地址」（仍可手改），
并联动 API Key 行的「获取 Key」链接（跳到该平台控制台的密钥管理页）。
地址被手改成已知平台域名时，服务商下拉自动跟随；认不出则显示「自定义」并收起链接。
"""

from __future__ import annotations

from typing import Any, List

from loguru import logger

from .voice_presets import (
    DEFAULT_API_URL,
    DEFAULT_MODEL,
    DEFAULT_VOICE_NAME,
    ENDPOINT_PRESETS,
    MODEL_PRESETS,
    VoicePreset,
    default_voice_value,
    find_endpoint,
    find_model,
    split_voice,
)

_UI_AVAILABLE = False
try:  # 宿主可能未装 qfluentwidgets（理论上必然有），缺失时降级不注册卡
    from PyQt5.QtCore import Qt, QThread, pyqtSignal
    from PyQt5.QtWidgets import QHBoxLayout, QWidget
    from qfluentwidgets import (
        BodyLabel,
        ComboBox,
        EditableComboBox,
        ExpandSettingCard,
        FluentIcon,
        HyperlinkButton,
        LineEdit,
        PasswordLineEdit,
        PushButton,
    )

    _UI_AVAILABLE = True
except Exception:  # noqa: BLE001 — 导入失败时 _ConfigCardBase 退化为空基类
    ExpandSettingCard = None  # type: ignore

# 标签列宽度（与主程序 PluginConfigCard._FieldRow 的 120 一致，视觉对齐）
_LABEL_MIN_WIDTH = 120
# 底部动作按钮宽度（定宽，不撑满整行）
_TEST_BTN_WIDTH = 110
_RESET_BTN_WIDTH = 120
# 自定义服务商项的标识（userData 为空串）
_CUSTOM_PROVIDER = ""


if _UI_AVAILABLE:

    class _FieldRow(QWidget):
        """字段行：左侧定宽 label，右侧控件撑满剩余宽度。"""

        def __init__(self, label_text: str, control: Any, parent=None):
            super().__init__(parent)
            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 4, 0, 4)
            layout.setSpacing(12)
            label = BodyLabel(label_text, self)
            label.setObjectName("fieldLabel")
            label.setMinimumWidth(_LABEL_MIN_WIDTH)
            layout.addWidget(label, 0, Qt.AlignLeft | Qt.AlignVCenter)
            layout.addWidget(control, 1)

    class _InlineRow(QWidget):
        """一行放两个控件：主轴控件撑满，尾部控件固定宽（API Key + 获取链接）。"""

        def __init__(self, control: Any, tail: Any, parent=None):
            super().__init__(parent)
            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            layout.addWidget(control, 1)
            layout.addWidget(tail, 0, Qt.AlignRight | Qt.AlignVCenter)

    class _TtsProbeWorker(QThread):
        """连通性探测：用当前配置真实合成一句短文本（真埋请求，能确认 key/端点/模型/音色）。

        只用合成不播放：拿到 RIFF 字节即算可用，不骚扰扬声器。
        """

        done = pyqtSignal(bool, str)

        def __init__(self, url: str, model: str, voice: str, key: str, parent=None):
            super().__init__(parent)
            self._url = url
            self._model = model
            self._voice = voice
            self._key = key

        def run(self) -> None:
            import time

            from .tts_engine import synthesize_wav

            started = time.monotonic()
            try:
                data = synthesize_wav(self._url, self._model, self._voice, self._key, "测试")
            except Exception as e:  # noqa: BLE001 — 失败原因一律人话展示
                self.done.emit(False, str(e))
                return
            elapsed = int((time.monotonic() - started) * 1000)
            self.done.emit(True, f"可用 · {elapsed} ms · {len(data) / 1024:.0f} KB")

    class _VoiceConfigCard(ExpandSettingCard):
        """语音播报配置卡：引擎 + 服务商 + 端点 + 模型 + 音色 + API Key。

        保存语义与主程序 PluginConfigStore 一致：空内容 = 清除 → 回退默认。
        构造签名 (parent=None) 满足 register_settings_card 的 widget_class 约定。
        """

        def __init__(self, parent=None):
            super().__init__(
                FluentIcon.VOLUME,
                "语音播报配置",
                "本地引擎零配置；在线引擎按服务商填 Key（可一键跳转获取）",
                parent,
            )
            self.viewLayout.setContentsMargins(48, 8, 48, 8)
            self.viewLayout.setSpacing(4)

            # 在线引擎专属行：本地引擎时整行置灰，避免「一堆填了没用的空框」
            self._api_rows: List[QWidget] = []

            # ── 语音引擎 ──
            self._engine_combo = ComboBox(self.view)
            self._engine_combo.addItem("本地系统语音（免费，Windows SAPI5 / macOS say）", userData="local")
            self._engine_combo.addItem("在线 API（OpenAI 兼容 /audio/speech）", userData="api")
            self._engine_combo.currentIndexChanged.connect(self._on_engine_changed)
            self.viewLayout.addWidget(_FieldRow("语音引擎", self._engine_combo, self.view))

            # ── 服务商（界面辅助：填地址 + 决定 Key 链接） ──
            self._provider_combo = ComboBox(self.view)
            for preset in ENDPOINT_PRESETS:
                self._provider_combo.addItem(preset.label, userData=preset.url)
            self._provider_combo.addItem("自定义（手填地址）", userData=_CUSTOM_PROVIDER)
            self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
            self._api_rows.append(_FieldRow("服务商", self._provider_combo, self.view))

            # ── API 地址（纯输入框：显示真实 URL，服务商下拉负责预填） ──
            self._url_edit = LineEdit(self.view)
            self._url_edit.setPlaceholderText("OpenAI 兼容 /audio/speech 端点")
            self._url_edit.setClearButtonEnabled(True)
            self._url_edit.editingFinished.connect(self._on_url_finished)
            self._api_rows.append(_FieldRow("API 地址", self._url_edit, self.view))

            # ── 模型（可编辑下拉：显示真实模型名，可手填） ──
            self._model_combo = EditableComboBox(self.view)
            self._model_combo.setPlaceholderText(DEFAULT_MODEL)
            for preset in MODEL_PRESETS:
                self._model_combo.addItem(preset.model, userData=preset.model)
            self._model_combo.setToolTip(
                "可手填任意模型名。预置：" + "；".join(p.model + " — " + p.label for p in MODEL_PRESETS)
            )
            self._model_combo.currentIndexChanged.connect(self._on_model_changed)
            self._model_combo.textChanged.connect(self._on_model_text_changed)
            self._api_rows.append(_FieldRow("模型", self._model_combo, self.view))

            # ── 音色（可编辑下拉：随模型换批 + 手填） ──
            self._voice_combo = EditableComboBox(self.view)
            self._voice_combo.setPlaceholderText(default_voice_value())
            self._voice_combo.textChanged.connect(self._on_voice_changed)
            self._api_rows.append(_FieldRow("音色", self._voice_combo, self.view))

            # ── API Key（行尾挂「获取 Key」外链，随服务商联动） ──
            self._key_edit = PasswordLineEdit(self.view)
            self._key_edit.setClearButtonEnabled(True)
            self._key_edit.setPlaceholderText("仅在线引擎需要")
            self._key_edit.editingFinished.connect(self._on_key_finished)
            self._key_link = HyperlinkButton(self.view)
            self._key_link.setIcon(FluentIcon.LINK)
            self._key_link.setText("获取 Key")
            self._key_link.setVisible(False)
            self._api_rows.append(_FieldRow("API Key", _InlineRow(self._key_edit, self._key_link, self.view), self.view))

            for row in self._api_rows:
                self.viewLayout.addWidget(row)

            # ── 底部：测试连接（左） + 结果（中） + 恢复默认（右） ──
            action_row = QWidget(self.view)
            action_layout = QHBoxLayout(action_row)
            action_layout.setContentsMargins(0, 4, 0, 4)
            action_layout.setSpacing(12)
            self._test_btn = PushButton("测试连接", action_row)
            self._test_btn.setFixedWidth(_TEST_BTN_WIDTH)
            self._test_btn.clicked.connect(self._on_test)
            self._test_result = BodyLabel("", action_row)
            self._reset_btn = PushButton("恢复默认", action_row)
            self._reset_btn.setFixedWidth(_RESET_BTN_WIDTH)
            self._reset_btn.clicked.connect(self._on_reset)
            action_layout.addWidget(self._test_btn)
            action_layout.addWidget(self._test_result, 1)
            action_layout.addWidget(self._reset_btn)
            self.viewLayout.addWidget(action_row)

            self._probe = None
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
                (self._model_combo, model),
            ):
                combo.blockSignals(True)
                self._select_or_set_text(combo, value)
                combo.blockSignals(False)
            self._move_cursor_to_start(self._engine_combo)
            self._move_cursor_to_start(self._model_combo)

            self._url_edit.blockSignals(True)
            self._url_edit.setText(url)
            self._url_edit.blockSignals(False)
            self._sync_provider_from_url()

            # 音色：先按模型重建选项，再选中（存储值里音色名可能不在新模型音色包中）
            _model, voice_name = split_voice(voice)
            self._rebuild_voices(model, select_name=voice_name or DEFAULT_VOICE_NAME)
            self._voice_combo.blockSignals(True)
            self._select_or_set_text(self._voice_combo, voice_name or voice)
            self._voice_combo.blockSignals(False)
            self._move_cursor_to_start(self._voice_combo)

            self._key_edit.blockSignals(True)
            self._key_edit.setText(api_key)
            self._key_edit.blockSignals(False)

            self._apply_engine_state()

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

        @staticmethod
        def _move_cursor_to_start(combo) -> None:
            """可编辑下拉的文本超出可视宽时，默认光标停在末尾会显示成「后半截」。

            回显后把光标拨到开头：长模型名（FunAudioLLM/CosyVoice2-0.5B）能读到前缀。
            EditableComboBox 自身就是 QLineEdit，普通 ComboBox 没有 setCursorPosition。
            """
            try:
                combo.setCursorPosition(0)
            except Exception:  # noqa: BLE001 — 不可编辑下拉没有光标概念
                return

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

        # ── 服务商 / Key 链接 ───────────────────────────────

        def _set_provider_index(self, url: str) -> None:
            """按地址定位服务商项（认不出则落到「自定义」），不触发写盘。"""
            preset = find_endpoint(url or DEFAULT_API_URL)
            target = preset.url if preset else _CUSTOM_PROVIDER
            index = self._provider_combo.findData(target)
            self._provider_combo.blockSignals(True)
            self._provider_combo.setCurrentIndex(index if index >= 0 else 0)
            self._provider_combo.blockSignals(False)

        def _sync_provider_from_url(self) -> None:
            """地址 → 服务商 + Key 链接（用户手改地址后调用）。"""
            self._set_provider_index(self._url_edit.text())
            self._update_key_link()

        def _update_key_link(self) -> None:
            """Key 链接跟随当前地址所属平台；认不出平台（自部署端点）时收起。

            地址为空 = 运行时回退默认端点，链接也按默认平台展示。
            """
            preset = find_endpoint(self._url_edit.text().strip() or DEFAULT_API_URL)
            if preset is None:
                self._key_link.setVisible(False)
                return
            self._key_link.setUrl(preset.key_url)
            self._key_link.setText("获取 Key")
            self._key_link.setToolTip(f"{preset.key_label}\n{preset.key_url}")
            self._key_link.setVisible(True)

        # ── 引擎状态 ────────────────────────────────────────

        def _apply_engine_state(self) -> None:
            """本地引擎时置灰在线相关行（配置结构仍可见，避免布局跳动）。"""
            online = str(self._engine_combo.currentData() or "local") == "api"
            for row in self._api_rows:
                row.setEnabled(online)
            self._test_btn.setEnabled(online)

        # ── 事件 ────────────────────────────────────────────

        def _on_engine_changed(self, _index: int) -> None:
            self._save("engine", str(self._engine_combo.currentData() or "local"))
            self._apply_engine_state()

        def _on_provider_changed(self, _index: int) -> None:
            url = str(self._provider_combo.currentData() or "")
            if url:
                self._url_edit.blockSignals(True)
                self._url_edit.setText(url)
                self._url_edit.blockSignals(False)
                self._save("api_url", url)
            self._update_key_link()

        def _on_url_finished(self) -> None:
            """地址编辑完成：保存真实 URL，并让服务商与链接跟着走。"""
            url = self._url_edit.text().strip()
            if url:
                self._save("api_url", url)
            self._sync_provider_from_url()

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
            """选中或手填音色：存完整 voice 值（模型名:音色名）。

            从下拉选中时 lineEdit 文本是 label（「沉稳男声 alex」），真正的音色名在
            userData；手填时 currentIndex 为 -1，只能解析文本。优先取 userData，
            否则会把 label 整串当音色名存进配置，请求时报「音色不存在」。
            """
            data = self._voice_combo.currentData()
            if data:
                name = str(data)
            else:
                value = text.strip()
                if not value:
                    return
                _, name = split_voice(value)
                name = name or value
            self._save("api_voice", f"{self._current_model()}:{name}")

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

        # ── 连通性测试 ────────────────────────────────────

        def _current_voice(self) -> str:
            """当前音色值（模型名:音色名），手填与下拉两种情形都补齐模型前缀。"""
            data = self._voice_combo.currentData()
            if data:
                return f"{self._current_model()}:{data}"
            _model, name = split_voice(self._voice_combo.text().strip())
            return f"{self._current_model()}:{name or DEFAULT_VOICE_NAME}"

        def _on_test(self) -> None:
            """测试连接：用卡里当前值（不是已存值）真发一次合成请求。"""
            key = self._key_edit.text().strip()
            if not key:
                self._show_probe(False, "未填写 API Key")
                return
            url = self._url_edit.text().strip() or DEFAULT_API_URL
            self._test_btn.setEnabled(False)
            self._test_btn.setText("测试中…")
            self._test_result.setText("")
            self._probe = _TtsProbeWorker(
                url, self._current_model(), self._current_voice(), key, self
            )
            self._probe.done.connect(self._on_probe_done)
            self._probe.start()

        def _on_probe_done(self, ok: bool, message: str) -> None:
            self._test_btn.setEnabled(True)
            self._test_btn.setText("测试连接")
            self._show_probe(ok, message)

        def _show_probe(self, ok: bool, message: str) -> None:
            """结果行：卡片内一行短结论 + tooltip 全文，不弹窗不遮界面。"""
            short = message if len(message) <= 44 else message[:44] + "…"
            self._test_result.setText(("✓ " if ok else "✗ ") + short)
            self._test_result.setToolTip(message)
            self._test_result.setStyleSheet("color: #3ea76a;" if ok else "color: #e5484d;")

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
            h = self.viewLayout.sizeHint().height()
            try:
                self.spaceWidget.setFixedHeight(0)
            except Exception:  # noqa: BLE001 — 旧版宿主无该成员时跳过
                pass
            self.setFixedHeight(self.card.height() + (h if self.isExpand else 0))

        def setExpand(self, isExpand: bool):
            if self.isExpand == isExpand:
                return
            self.isExpand = isExpand
            self.setProperty("isExpand", isExpand)
            from PyQt5.QtWidgets import QApplication

            self.setStyle(QApplication.style())
            self.card.expandButton.setExpand(isExpand)
            self._adjustViewSize()

else:  # pragma: no cover — 仅在没有 qfluentwidgets 的环境走到

    class _VoiceConfigCard:  # type: ignore[no-redef]
        def __init__(self, parent=None):
            raise RuntimeError("qfluentwidgets 不可用，无法构建语音播报配置卡")
