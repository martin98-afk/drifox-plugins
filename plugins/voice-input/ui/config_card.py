# -*- coding: utf-8 -*-
"""voice-input 自绘设置卡：听写引擎 + 双平台 Key/模型 + 连通性测试。

为什么不用 E1 自动卡（plugin.json config_schema）：
自动卡只有 text/password/select/link 等字段，塞不进「测试连接」按钮——
而这一卡的配置全是外部服务凭据，填完不验证，用户只能等到真说话时才发现
Key 无效或模型名写错。自绘卡按更高 priority 覆盖自动卡，config_schema 里
两条 link 字段（获取 Key）在本卡内以行尾外链形式补回。

测试语义（真实请求，不耗余额可忽略）：
- 生成 1 秒 440Hz 音调 WAV → 上传到当前引擎的识别端点
- HTTP 200 且无错误字段即判可用；识别文本为空属正常（测试音频不是人声）
- auto 模式下按链依次试，任一成功即通过，全失败时合并展示两条原因
"""

from __future__ import annotations

from typing import Any, List, Tuple

from loguru import logger

_UI_AVAILABLE = False
try:  # 宿主必然装有 qfluentwidgets；缺失时降级不注册卡
    from PyQt5.QtCore import Qt, QObject, QThread, pyqtProperty, pyqtSignal
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
    )

    _UI_AVAILABLE = True
except Exception:  # noqa: BLE001
    ExpandSettingCard = None  # type: ignore

PLUGIN_NAME = "voice-input"

_LABEL_MIN_WIDTH = 120
_TEST_BTN_WIDTH = 110
_RESET_BTN_WIDTH = 120

# 语音识别模型预设（与 config_schema 保持一致）
_MODEL_PRESETS: List[Tuple[str, str]] = [
    ("Qwen/Qwen3-ASR-1.7B", "Qwen3-ASR（推荐）"),
    ("FunAudioLLM/SenseVoiceSmall", "SenseVoice-Small"),
    ("XingChenAGI/XingChenASR-V3.2", "星尘 ASR V3.2"),
    ("XingChenAGI/XingChenASR-V3.2-Ultra", "星尘 ASR V3.2 Ultra"),
    ("XingChenAGI/XingChenASR-Diarize-V3.0", "星尘 ASR 说话人分离"),
]
_DEFAULT_MODEL = "Qwen/Qwen3-ASR-1.7B"

# Key 获取页（与 config_schema 的 link 字段同源）
_SF_KEY_URL = "https://cloud.siliconflow.cn/account/ak"
_MM_KEY_URL = "https://platform.minimaxi.com/user-center/basic-information/interface-key"


if _UI_AVAILABLE:

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
        """展开/折叠高度动画：逐帧写 fixedHeight，避免高度瞬移。"""
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

    class _InlineRow(QWidget):
        """一行两控件：主轴撑满，尾部固定宽（Key 输入框 + 获取链接）。"""

        def __init__(self, control: Any, tail: Any, parent=None):
            super().__init__(parent)
            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            layout.addWidget(control, 1)
            layout.addWidget(tail, 0, Qt.AlignRight | Qt.AlignVCenter)

    class _AsrProbeWorker(QThread):
        """连通性探测：按引擎链依次发真实上传请求。"""

        done = pyqtSignal(bool, str)

        def __init__(self, chain: List[Tuple[str, str, str, str]], parent=None):
            super().__init__(parent)
            self._chain = list(chain)

        def run(self) -> None:  # noqa: C901 — 单链短流程，拆开反而碎
            import os
            import time

            from .cloud_recognizer import make_probe_wav, probe_asr

            if not self._chain:
                self.done.emit(False, "未配置任何引擎的 API Key")
                return

            errors: List[str] = []
            for url, model, key, name in self._chain:
                wav = ""
                started = time.monotonic()
                try:
                    wav = make_probe_wav()
                    detail = probe_asr(url, model, key, wav)
                except Exception as e:  # noqa: BLE001 — 逐条收集，最后合并展示
                    errors.append(f"{name}：{e}")
                    continue
                finally:
                    if wav:
                        try:
                            os.remove(wav)
                        except OSError:
                            pass
                elapsed = int((time.monotonic() - started) * 1000)
                self.done.emit(True, f"{name} {detail} · {elapsed} ms")
                return
            self.done.emit(False, "；".join(errors))

    class _VoiceInputConfigCard(ExpandSettingCard):
        """语音听写配置卡：引擎 + 双平台 Key/模型 + 测试连接 + 恢复默认。"""

        def __init__(self, parent=None):
            super().__init__(
                getattr(FluentIcon, "MICROPHONE", None) or FluentIcon.SETTING,
                "语音听写配置",
                "硅基流动免费模型默认；两个引擎都配 Key 才会互为备用",
                parent,
            )
            self.viewLayout.setContentsMargins(48, 8, 48, 8)
            self.viewLayout.setSpacing(4)

            self._probe = None
            self._sf_rows: List[QWidget] = []
            self._mm_rows: List[QWidget] = []

            # ── 识别引擎 ──
            self._provider_combo = ComboBox(self.view)
            self._provider_combo.addItem("自动（硅基流动优先，失败转 MiniMax）", userData="auto")
            self._provider_combo.addItem("仅硅基流动（免费）", userData="siliconflow")
            self._provider_combo.addItem("仅 MiniMax", userData="minimax")
            self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
            self.viewLayout.addWidget(_FieldRow("识别引擎", self._provider_combo, self.view))

            # ── 硅基流动 ──
            self._sf_key = PasswordLineEdit(self.view)
            self._sf_key.setClearButtonEnabled(True)
            self._sf_key.setPlaceholderText("免费模型不消耗余额")
            self._sf_key.editingFinished.connect(
                lambda: self._save("siliconflow_api_key", self._sf_key.text().strip())
            )
            sf_link = HyperlinkButton(self.view)
            sf_link.setIcon(FluentIcon.LINK)
            sf_link.setText("获取 Key")
            sf_link.setUrl(_SF_KEY_URL)
            sf_link.setToolTip("前往硅基流动创建 API Key")
            self._sf_rows.append(
                _FieldRow("硅基流动 Key", _InlineRow(self._sf_key, sf_link, self.view), self.view)
            )

            self._sf_model = EditableComboBox(self.view)
            for value, label in _MODEL_PRESETS:
                self._sf_model.addItem(label, userData=value)
            self._sf_model.setToolTip("可手填任意硅基流动 ASR 模型名；预置项均为免费模型")
            self._sf_model.currentIndexChanged.connect(self._on_sf_model_changed)
            self._sf_model.textChanged.connect(self._on_sf_model_text_changed)
            self._sf_rows.append(_FieldRow("硅基流动模型", self._sf_model, self.view))

            # ── MiniMax ──
            self._mm_key = PasswordLineEdit(self.view)
            self._mm_key.setClearButtonEnabled(True)
            self._mm_key.setPlaceholderText("自动模式下作为备用引擎")
            self._mm_key.editingFinished.connect(
                lambda: self._save("minimax_api_key", self._mm_key.text().strip())
            )
            mm_link = HyperlinkButton(self.view)
            mm_link.setIcon(FluentIcon.LINK)
            mm_link.setText("获取 Key")
            mm_link.setUrl(_MM_KEY_URL)
            mm_link.setToolTip("前往 MiniMax 开放平台创建 API Key")
            self._mm_rows.append(
                _FieldRow("MiniMax Key", _InlineRow(self._mm_key, mm_link, self.view), self.view)
            )

            for row in self._sf_rows + self._mm_rows:
                self.viewLayout.addWidget(row)

            # ── 底部：测试连接 + 结果 + 恢复默认 ──
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

            self._echo()

        # ── 回显 ────────────────────────────────────────────

        def _echo(self) -> None:
            from app.plugins.managers.plugin_config_store import PluginConfigStore

            store = PluginConfigStore()
            provider = str(store.get(PLUGIN_NAME, "provider") or "auto")
            sf_key = str(store.get(PLUGIN_NAME, "siliconflow_api_key") or "")
            sf_model = str(store.get(PLUGIN_NAME, "siliconflow_model") or "") or _DEFAULT_MODEL
            mm_key = str(store.get(PLUGIN_NAME, "minimax_api_key") or "")

            index = self._provider_combo.findData(provider)
            self._provider_combo.blockSignals(True)
            self._provider_combo.setCurrentIndex(index if index >= 0 else 0)
            self._provider_combo.blockSignals(False)

            self._sf_key.blockSignals(True)
            self._sf_key.setText(sf_key)
            self._sf_key.blockSignals(False)
            self._mm_key.blockSignals(True)
            self._mm_key.setText(mm_key)
            self._mm_key.blockSignals(False)

            self._sf_model.blockSignals(True)
            model_index = self._sf_model.findData(sf_model)
            if model_index >= 0:
                self._sf_model.setCurrentIndex(model_index)
            else:
                self._sf_model.setText(sf_model)
            self._sf_model.blockSignals(False)
            self._move_cursor_to_start(self._sf_model)

            self._apply_engine_state()

        @staticmethod
        def _move_cursor_to_start(combo) -> None:
            """可编辑下拉回显后光标在末尾，长模型名会只显示后半截。"""
            try:
                combo.setCursorPosition(0)
            except Exception:  # noqa: BLE001 — 不可编辑下拉无光标概念
                return

        def _current_model(self) -> str:
            data = self._sf_model.currentData()
            if data:
                return str(data)
            return self._sf_model.text().strip() or _DEFAULT_MODEL

        # ── 引擎联动 ────────────────────────────────────────

        def _apply_engine_state(self) -> None:
            """按引擎选择置灰无关平台（保持布局稳定，不隐藏）。"""
            provider = str(self._provider_combo.currentData() or "auto")
            for row in self._sf_rows:
                row.setEnabled(provider in ("auto", "siliconflow"))
            for row in self._mm_rows:
                row.setEnabled(provider in ("auto", "minimax"))

        # ── 事件 ────────────────────────────────────────────

        def _on_provider_changed(self, _index: int) -> None:
            self._save("provider", str(self._provider_combo.currentData() or "auto"))
            self._apply_engine_state()

        def _on_sf_model_changed(self, _index: int) -> None:
            data = str(self._sf_model.currentData() or "")
            if data:
                self._save("siliconflow_model", data)

        def _on_sf_model_text_changed(self, text: str) -> None:
            value = text.strip()
            if value:
                self._save("siliconflow_model", value)

        # ── 连通性测试 ──────────────────────────────────────

        def _probe_chain(self) -> List[Tuple[str, str, str, str]]:
            """按当前 UI 值（不是已存值）组装探测链：[(url, model, key, 名称), ...]。"""
            from . import _MINIMAX_MODEL, _MINIMAX_URL, _SILICONFLOW_URL

            provider = str(self._provider_combo.currentData() or "auto")
            chain: List[Tuple[str, str, str, str]] = []
            sf_key = self._sf_key.text().strip()
            mm_key = self._mm_key.text().strip()
            if provider in ("auto", "siliconflow") and sf_key:
                chain.append((_SILICONFLOW_URL, self._current_model(), sf_key, "硅基流动"))
            if provider in ("auto", "minimax") and mm_key:
                chain.append((_MINIMAX_URL, _MINIMAX_MODEL, mm_key, "MiniMax"))
            return chain

        def _on_test(self) -> None:
            chain = self._probe_chain()
            if not chain:
                self._show_probe(False, "当前引擎未填写 API Key")
                return
            self._test_btn.setEnabled(False)
            self._test_btn.setText("测试中…")
            self._test_result.setText("")
            self._probe = _AsrProbeWorker(chain, self)
            self._probe.done.connect(self._on_probe_done)
            self._probe.start()

        def _on_probe_done(self, ok: bool, message: str) -> None:
            self._test_btn.setEnabled(True)
            self._test_btn.setText("测试连接")
            self._show_probe(ok, message)

        def _show_probe(self, ok: bool, message: str) -> None:
            short = message if len(message) <= 44 else message[:44] + "…"
            self._test_result.setText(("✓ " if ok else "✗ ") + short)
            self._test_result.setToolTip(message)
            self._test_result.setStyleSheet("color: #3ea76a;" if ok else "color: #e5484d;")

        # ── 恢复默认 / 存储 ─────────────────────────────────

        def _on_reset(self) -> None:
            from app.plugins.managers.plugin_config_store import PluginConfigStore

            PluginConfigStore().set_values(
                PLUGIN_NAME,
                {
                    "provider": "",
                    "siliconflow_api_key": "",
                    "siliconflow_model": "",
                    "minimax_api_key": "",
                },
            )
            self._test_result.setText("")
            self._echo()

        @staticmethod
        def _save(key: str, value: str) -> None:
            try:
                from app.plugins.managers.plugin_config_store import PluginConfigStore

                PluginConfigStore().set_values(PLUGIN_NAME, {key: value})
            except Exception as e:  # noqa: BLE001 — 写盘失败不影响界面操作
                logger.warning(f"[voice-input] 配置保存失败({key}): {e}")

        # ── 折叠高度（对齐主程序 PluginConfigCard） ──

        def _target_height(self, is_expand: bool) -> int:
            try:
                self.spaceWidget.setFixedHeight(0)
            except Exception:  # noqa: BLE001 — 旧版宿主无该成员时跳过
                pass
            return self.card.height() + (self.viewLayout.sizeHint().height() if is_expand else 0)

        def _adjustViewSize(self):
            """内容尺寸变化后直接定格（不动画，供基类/回显后调用）。"""
            self.setFixedHeight(self._target_height(self.isExpand))

        def setExpand(self, isExpand: bool):
            if self.isExpand == isExpand:
                return
            self.isExpand = isExpand
            self.setProperty("isExpand", isExpand)
            from PyQt5.QtWidgets import QApplication

            self.setStyle(QApplication.style())
            self.card.expandButton.setExpand(isExpand)
            _animate_card_height(self, self._target_height(isExpand))

else:  # pragma: no cover — 仅在没有 qfluentwidgets 的环境走到

    class _VoiceInputConfigCard:  # type: ignore[no-redef]
        def __init__(self, parent=None):
            raise RuntimeError("qfluentwidgets 不可用，无法构建语音听写配置卡")
