# -*- coding: utf-8 -*-
"""git-panel 设置卡 — 「Git 提交描述生成」：多行提示词编辑 + 服务商/模型两级下拉 + 恢复默认

实现模式与 vision-proxy._VisionConfigCard 一致（同 card_id 覆盖 E1 自动卡）：
- 保存语义与 PluginConfigStore 一致：空内容 = 清除 → 回默认
- 服务商、模型分开选（对齐 vision-proxy）：服务商下拉换选后重填模型下拉；
  数据源首选 provider.list / model.enumerate（内存态），能力不可用回退磁盘扫描
- 「当前模型」= 两键均空（沿用调用方当前 provider/model）
"""

from typing import Optional

from loguru import logger

try:  # qfluentwidgets 由 DriFox 运行时提供；缺失时降级原生控件
    from qfluentwidgets import BodyLabel, ComboBox, ExpandSettingCard, PushButton, TextEdit
except Exception:  # noqa: BLE001
    ExpandSettingCard = None  # type: ignore
    BodyLabel = None  # type: ignore
    ComboBox = None  # type: ignore
    PushButton = None  # type: ignore
    TextEdit = None  # type: ignore

from PyQt5.QtCore import QEvent, QObject, Qt
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QToolTip,
    QPushButton,
    QWidget,
)

from .llm_config import (
    DEFAULT_COMMIT_PROMPT,
    PLUGIN_NAME,
    load_models_by_tree,
    load_provider_tree,
)

_CONFIG_CARD_BASE = ExpandSettingCard if ExpandSettingCard is not None else object  # type: ignore

_CURRENT_MODEL_LABEL = "当前模型"
_CURRENT_MODEL_VALUE = ""
_MAX_MODEL_VISIBLE_ITEMS = 8
# 标签列宽度（与主程序 PluginConfigCard._FieldRow 一致，全卡字段名对齐）
_LABEL_MIN_WIDTH = 120
_RESET_BTN_WIDTH = 140


def _field_row(label_text: str, control: QWidget, parent=None, valign=Qt.AlignVCenter) -> QWidget:
    """字段行：左侧定宽 label，右侧控件撑满剩余宽度（不固定窄宽、不右对齐）。

    多行控件（TextEdit）传 valign=Qt.AlignTop，标签顶对齐更好看。
    """
    row = QWidget(parent)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 4, 0, 4)
    layout.setSpacing(12)
    label = BodyLabel(label_text, row) if BodyLabel is not None else QLabel(label_text, row)
    label.setMinimumWidth(_LABEL_MIN_WIDTH)
    layout.addWidget(label, 0, Qt.AlignLeft | valign)
    layout.addWidget(control, 1)
    return row


def _reset_row(button: QWidget, parent=None) -> QWidget:
    """重置按钮行：右对齐定宽，不撑满整行。"""
    row = QWidget(parent)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 4, 0, 4)
    button.setFixedWidth(_RESET_BTN_WIDTH)
    layout.addStretch(1)
    layout.addWidget(button)
    return row


class _CommitConfigCard(_CONFIG_CARD_BASE):
    """Git 提交描述生成配置卡：提示词多行编辑 + 服务商/模型两级下拉 + 恢复默认"""

    def __init__(self, parent=None):
        super().__init__(
            __import__("qfluentwidgets", fromlist=["FluentIcon"]).FluentIcon.ROBOT,
            "Git 提交描述生成",
            "生成提示词 + 模型选择（即时保存）",
            parent,
        )
        self.viewLayout.setContentsMargins(48, 8, 48, 8)
        self.viewLayout.setSpacing(4)

        self._edit = TextEdit(self.view) if TextEdit is not None else QPlainTextEdit(self.view)
        self._edit.setPlaceholderText("根据暂存变更生成提交描述的 system 指令，留空回默认")
        self._edit.setMinimumHeight(140)
        self.viewLayout.addWidget(_field_row("生成提示词", self._edit, self.view, Qt.AlignTop))

        self._provider_combo: Optional[ComboBox] = None
        self._model_combo: Optional[ComboBox] = None
        if ComboBox is not None:
            self._providers = load_provider_tree()

            self._provider_combo = ComboBox(self.view)
            self._provider_combo.setMaxVisibleItems(_MAX_MODEL_VISIBLE_ITEMS)
            for label, pid in self._providers:
                self._provider_combo.addItem(label, userData=pid)
            self._provider_combo.setToolTip(
                "生成提交描述用的服务商。选「当前模型」表示沿用当前窗口 provider/model。"
            )
            self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
            self.viewLayout.addWidget(_field_row("服务商", self._provider_combo, self.view))

            self._model_combo = ComboBox(self.view)
            self._model_combo.setMaxVisibleItems(_MAX_MODEL_VISIBLE_ITEMS)
            self._model_combo.setToolTip(
                "生成提交描述用的模型（清单随上方服务商联动）。"
            )
            self._model_combo.currentIndexChanged.connect(self._on_model_changed)
            self.viewLayout.addWidget(_field_row("模型", self._model_combo, self.view))

        self._reset_btn = PushButton("恢复默认", self.view) if PushButton is not None else QPushButton("恢复默认", self.view)
        self._reset_btn.clicked.connect(self._on_reset)
        self.viewLayout.addWidget(_reset_row(self._reset_btn, self.view))

        self._echo()

    def _adjustViewSize(self):
        """空白占位归零：qfluentwidgets 的 setExpand 会先调 _adjustViewSize 把
        spaceWidget 重设为内容等高，导致展开高度 = 内容 + 等高空白。
        与覆写的 setExpand 配套：spaceWidget 恒 0，高度直接在标题卡与
        标题卡+内容之间切换（原版的折叠动画依赖 spaceWidget 滚动余量，
        强制归零后折叠动画失去参考高度，卡片收不回去）。"""
        h = self.viewLayout.sizeHint().height()
        try:
            self.spaceWidget.setFixedHeight(0)
        except Exception:  # noqa: BLE001
            pass
        if self.isExpand:
            self.setFixedHeight(self.card.height() + h)
        else:
            self.setFixedHeight(self.card.height())

    def setExpand(self, isExpand: bool):
        """覆写：不用原版滚动动画（依赖 spaceWidget 占位，已归零），
        直接按展开态切换卡片高度，保证可展开也可折叠。"""
        if self.isExpand == isExpand:
            return
        self.isExpand = isExpand
        self.setProperty("isExpand", isExpand)
        self.setStyle(QApplication.style())
        self.card.expandButton.setExpand(isExpand)
        self._adjustViewSize()

    # ── 回显 / 保存 ──

    def _echo(self) -> None:
        from .llm_config import load_plugin_text_config

        # 提示词编辑框
        while True:
            try:
                self._edit.textChanged.disconnect()
            except TypeError:
                break
        self._edit.setPlainText(load_plugin_text_config("commit_prompt", DEFAULT_COMMIT_PROMPT))
        self._edit.textChanged.connect(self._on_prompt_changed)

        # 服务商下拉
        if self._provider_combo is None:
            return
        from .llm_config import load_plugin_text_config

        stored_provider = load_plugin_text_config("commit_provider", "")
        stored_model = load_plugin_text_config("commit_model", "")
        # 旧格式兼容：「服务商:模型」合并值存过 → 拆开回显，不丢用户配置
        if not stored_provider and ":" in stored_model:
            stored_provider, stored_model = stored_model.split(":", 1)
            stored_provider, stored_model = stored_provider.strip(), stored_model.strip()

        self._provider_combo.blockSignals(True)
        idx = self._provider_combo.findData(stored_provider)
        if idx < 0:
            if stored_provider:
                # 已存值不在清单里（服务商被删/能力降级）：插到首位保住它
                self._provider_combo.insertItem(0, stored_provider, userData=stored_provider)
                idx = 0
            else:
                idx = 0
        self._provider_combo.setCurrentIndex(idx)
        self._provider_combo.blockSignals(False)

        current_pid = str(self._provider_combo.currentData() or "")
        self._fill_models(current_pid, stored_model)

    def _fill_models(self, provider_id: str, selected: str = "") -> None:
        """按服务商重填模型下拉；首项「当前模型」= 空（沿用该服务商默认/当前窗口）。"""
        if self._model_combo is None:
            return
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        self._model_combo.addItem(_CURRENT_MODEL_LABEL, userData=_CURRENT_MODEL_VALUE)
        for name in load_models_by_tree(provider_id):
            self._model_combo.addItem(name, userData=name)
        idx = self._model_combo.findData(selected)
        if idx < 0 and selected:
            # 已存模型不在清单里（服务商模型变更）：插到「当前模型」之后保住它
            self._model_combo.insertItem(1, selected, userData=selected)
            idx = 1
        self._model_combo.setCurrentIndex(max(0, idx))
        self._model_combo.blockSignals(False)

    def _on_prompt_changed(self) -> None:
        self._save({"commit_prompt": self._edit.toPlainText().strip()})

    def _on_provider_changed(self, _index: int) -> None:
        if self._provider_combo is None:
            return
        pid = str(self._provider_combo.currentData() or "")
        self._save({"commit_provider": pid})
        # 换服务商后模型清单全变，清空模型值避免指向不存在的模型
        self._save({"commit_model": ""})
        self._fill_models(pid)

    def _on_model_changed(self, _index: int) -> None:
        if self._model_combo is None:
            return
        value = self._model_combo.currentData() or _CURRENT_MODEL_VALUE
        self._save({"commit_model": str(value)})

    def _on_reset(self) -> None:
        self._save(
            {
                "commit_prompt": DEFAULT_COMMIT_PROMPT,
                "commit_provider": "",
                "commit_model": _CURRENT_MODEL_VALUE,
            }
        )
        self._echo()

    # ── 配置读写（PluginConfigStore 不可用时静默降级为会话内编辑） ──

    @staticmethod
    def _save(values: dict) -> None:
        try:
            from app.plugins.managers.plugin_config_store import PluginConfigStore

            PluginConfigStore().set_values(PLUGIN_NAME, values)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[git-panel] 保存配置失败: {e}")
