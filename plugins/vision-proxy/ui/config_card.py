# -*- coding: utf-8 -*-
"""vision-proxy 设置卡 — 视觉服务商 + 视觉模型两级下拉。

为什么自建卡而不用 config_schema：config_schema 只有 8 种 type（text/password/
bool/select/number/textarea/link/action），没有「模型选择」，且 select 的 options
必须写死在 plugin.json —— 拿不到运行时才存在的服务商与模型清单。

选项来源走新能力 provider.list / model.enumerate（ui surface），不再
json.load(app.config)：密钥模式下磁盘 API_KEY 是密文，且用户刚添加的服务商
可能尚未落盘，内存态才是活的。取值经 caps_for 按插件名解析到活跃窗口。

降级：能力不可用（旧宿主 / 无活跃窗口）时下拉为空，但已存值仍保留在卡片里
不会丢失，用户可切到 E1 自动卡（text 字段）手填。
"""

from typing import Any, Dict, List, Optional

from loguru import logger

try:  # qfluentwidgets 由 DriFox 运行时提供；缺失时降级不注册卡
    from qfluentwidgets import BodyLabel, ComboBox, ExpandSettingCard, FluentIcon
except Exception:  # noqa: BLE001
    BodyLabel = None  # type: ignore
    ComboBox = None  # type: ignore
    ExpandSettingCard = None  # type: ignore
    FluentIcon = None  # type: ignore

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QWidget

PLUGIN_NAME = "vision-proxy"

_CARD_BASE = ExpandSettingCard if ExpandSettingCard is not None else object  # type: ignore

_CURRENT_LABEL = "当前模型（跟随窗口）"
_CURRENT_VALUE = ""
_MAX_VISIBLE_ITEMS = 10


def _caps(name: str) -> Any:
    """取宿主能力（无 ctx 的独立弹窗/设置卡走 caps_for，按插件名解析 host）。"""
    try:
        from app.plugins.sdk import caps_for

        return caps_for(name, plugin=PLUGIN_NAME, surface="ui")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[vision-proxy] 取能力 {name} 失败: {e}")
        return None


def _load_providers() -> List[Dict[str, Any]]:
    """已配置服务商清单；能力不可用返回空列表。"""
    fn = _caps("provider.list")
    if not callable(fn):
        return []
    try:
        items = fn() or []
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[vision-proxy] provider.list 调用失败: {e}")
        return []
    return [p for p in items if isinstance(p, dict)]


def _load_models(provider_id: str) -> List[Dict[str, Any]]:
    """指定服务商的模型列表；能力不可用返回空列表。"""
    if not provider_id:
        return []
    fn = _caps("model.enumerate")
    if not callable(fn):
        return []
    try:
        items = fn(provider_id) or []
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[vision-proxy] model.enumerate 调用失败: {e}")
        return []
    return [m for m in items if isinstance(m, dict)]


def _read_config(key: str, default: str = "") -> str:
    try:
        from app.plugins.managers.plugin_config_store import PluginConfigStore

        value = PluginConfigStore().get(PLUGIN_NAME, key)
    except Exception:  # noqa: BLE001 — 主程序未注入存储时按默认走
        return default
    return str(value) if value not in (None, "") else default


def _save(values: Dict[str, Any]) -> None:
    try:
        from app.plugins.managers.plugin_config_store import PluginConfigStore

        PluginConfigStore().set_values(PLUGIN_NAME, values)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[vision-proxy] 保存配置失败: {e}")


def _field_row(label_text: str, control: QWidget, parent=None) -> QWidget:
    row = QWidget(parent)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 4, 0, 4)
    layout.setSpacing(12)
    label = BodyLabel(label_text, row)
    label.setMinimumWidth(120)
    layout.addWidget(label, 0, Qt.AlignLeft | Qt.AlignVCenter)
    control.setMinimumWidth(280)
    layout.addWidget(control, 1, Qt.AlignRight)
    return row


def _model_text(item: Dict[str, Any]) -> str:
    """模型显示名：视觉能力标记 + 当前标记（看不出能力的模型也照列，用户自己判断）。"""
    name = str(item.get("name") or "")
    marks = []
    if item.get("supports_vision"):
        marks.append("👁 视觉")
    if item.get("is_current"):
        marks.append("当前")
    return f"{name}（{'/'.join(marks)}）" if marks else name


class _VisionConfigCard(_CARD_BASE):
    """图片代理配置卡：服务商下拉 → 模型下拉（即时保存）"""

    def __init__(self, parent=None):
        icon = getattr(FluentIcon, "PHOTO", None) if FluentIcon is not None else None
        super().__init__(
            icon or FluentIcon.SETTING,
            "图片代理（视觉模型）",
            "选择承接图片理解的服务商与模型（即时保存）",
            parent,
        )
        self.viewLayout.setContentsMargins(48, 8, 48, 8)
        self.viewLayout.setSpacing(8)

        self._providers: List[Dict[str, Any]] = _load_providers()
        self._provider_combo: Optional[ComboBox] = self._build_provider_combo()
        self._model_combo: Optional[ComboBox] = self._build_model_combo()

        if self._provider_combo is not None:
            self.viewLayout.addWidget(_field_row("视觉服务商", self._provider_combo, self.view))
        if self._model_combo is not None:
            self.viewLayout.addWidget(_field_row("视觉模型", self._model_combo, self.view))

        if not self._providers:
            hint = BodyLabel(
                "未取到服务商清单（宿主版本较旧或无活跃窗口）。"
                "可改用下方「图片代理（视觉模型）」自动卡手填服务商与模型名。",
                self.view,
            )
            hint.setWordWrap(True)
            self.viewLayout.addWidget(hint)

        self._echo()

    # ── 控件构建 ──

    def _build_provider_combo(self) -> Optional[ComboBox]:
        if ComboBox is None:
            return None
        combo = ComboBox(self.view)
        combo.setMaxVisibleItems(_MAX_VISIBLE_ITEMS)
        for p in self._providers:
            combo.addItem(str(p.get("display_name") or p.get("id") or ""), userData=str(p.get("id") or ""))
        combo.setToolTip("承接图片理解的服务商。选「当前服务商」表示沿用窗口当前选中的服务商。")
        combo.currentIndexChanged.connect(self._on_provider_changed)
        return combo

    def _build_model_combo(self) -> Optional[ComboBox]:
        if ComboBox is None:
            return None
        combo = ComboBox(self.view)
        combo.setMaxVisibleItems(_MAX_VISIBLE_ITEMS)
        combo.setToolTip(
            "承接图片理解的模型。👁 视觉 = 该模型声明支持图像输入；"
            "不带标记的模型看图大概率失败。"
        )
        combo.currentIndexChanged.connect(self._on_model_changed)
        return combo

    # ── 回显 ──

    def _echo(self) -> None:
        stored_provider = _read_config("vision_provider")
        stored_model = _read_config("vision_model")

        if self._provider_combo is None:
            return
        self._provider_combo.blockSignals(True)
        idx = self._provider_combo.findData(stored_provider)
        if idx < 0:
            # 已存值不在清单里（服务商被删 / 能力不可用）：插到首位保住它，
            # 不让用户的配置在回显阶段被静默抹掉
            if stored_provider:
                self._provider_combo.insertItem(0, stored_provider, userData=stored_provider)
                idx = 0
            else:
                idx = self._provider_combo.findData(_CURRENT_VALUE)
                if idx < 0:
                    idx = 0
        self._provider_combo.setCurrentIndex(max(0, idx))
        self._provider_combo.blockSignals(False)

        self._fill_models(str(self._provider_combo.currentData() or ""), stored_model)

    def _fill_models(self, provider_id: str, selected: str = "") -> None:
        """按服务商重填模型下拉；selected 不在列表时插到首位保住已存值。"""
        if self._model_combo is None:
            return
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        self._model_combo.addItem(_CURRENT_LABEL, userData=_CURRENT_VALUE)
        for m in _load_models(provider_id):
            name = str(m.get("name") or "")
            if not name:
                continue
            self._model_combo.addItem(_model_text(m), userData=name)
        idx = self._model_combo.findData(selected)
        if idx < 0 and selected:
            self._model_combo.insertItem(1, selected, userData=selected)
            idx = 1
        self._model_combo.setCurrentIndex(max(0, idx if idx >= 0 else 0))
        self._model_combo.blockSignals(False)

    # ── 保存 ──

    def _on_provider_changed(self, _index: int) -> None:
        if self._provider_combo is None:
            return
        provider_id = str(self._provider_combo.currentData() or "")
        _save({"vision_provider": provider_id})
        # 换服务商后模型清单全变，清空模型值避免指向不存在的模型
        _save({"vision_model": ""})
        self._fill_models(provider_id, "")

    def _on_model_changed(self, _index: int) -> None:
        if self._model_combo is None:
            return
        _save({"vision_model": str(self._model_combo.currentData() or "")})

    # ── 折叠高度（与 git-panel 同款：不用 spaceWidget 滚动动画）──

    def _adjustViewSize(self):
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
        if self.isExpand == isExpand:
            return
        self.isExpand = isExpand
        self.setProperty("isExpand", isExpand)
        self.setStyle(__import__("PyQt5.QtWidgets", fromlist=["QApplication"]).QApplication.style())
        self.card.expandButton.setExpand(isExpand)
        self._adjustViewSize()
