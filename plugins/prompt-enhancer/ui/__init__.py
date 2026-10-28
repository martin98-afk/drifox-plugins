# -*- coding: utf-8 -*-
"""提示词增强 UI 插件（闭包实现，不修改主程序）。

输入框按钮「优化提示词」：点击后用 LLM（复用主程序当前会话模型配置）把
输入框原文优化为更清晰、结构化、高信息密度的提示词，并追加到原问题之后（保留原问题，不替换）。

体验完善（v0.2.1）：
- 系统配置开放增强指令：注册「提示词增强」设置卡（多行编辑 + 即时保存 + 恢复默认），
  覆盖主程序 E1 自动卡（单行 LineEdit），长指令编辑不再痛苦；
- 防任务积压：同一窗口同时只允许一个优化任务，运行中重复点击给出提示并忽略；
- 进度可感知：优化中按钮图标转为旋转圆环动画（QPainter 自绘，浅色/深色主题自适应），
  并常驻 InfoBar「正在优化提示词…」，完成/失败后恢复并给出结果提示。

实现要点：
- 通过 UI 扩展点 context["main_widget"] 读取输入框（input_area）与当前模型配置；
- 通过 PluginConfigStore 读写插件配置（enhance_prompt / enhance_provider / enhance_model，
  服务商与模型分开存，对齐 vision-proxy）；enhance_model 存旧格式
  「ProviderName:ModelName」时按兼容路径拆分。
- 请求发出走宿主 services["create_engine_session"]（EP3 契约）：经 ModelAdapter /
  Serializer / Transport 三层分派，服务商伪装头、responses 协议、思考参数映射、
  智能重试全部自动生效，插件零协议知识；
- 后台 QRunnable + 信号桥接，结果在主线程注回输入框，避免 UI 卡死。

模型配置来自宿主 services["get_provider_config"]（主程序读内存态已解锁明文，
服务商与模型均未配置时沿用调用方当前 provider/model。"""

import json
import os
import re
import threading
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from PyQt5.QtCore import QObject, QRectF, QRunnable, QThreadPool, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QLabel, QPlainTextEdit, QWidget

from app.plugins.managers.plugin_config_store import PluginConfigStore
from app.plugins.registries.ui_plugin_registry import UIPluginRegistry

try:  # 模块级导入设置卡基类；失败则跳过自定义设置卡注册
    from qfluentwidgets import BodyLabel, ComboBox, ExpandSettingCard, TextEdit
except Exception:  # noqa: BLE001
    ExpandSettingCard = None  # type: ignore
    BodyLabel = None  # type: ignore
    ComboBox = None  # type: ignore
    TextEdit = None  # type: ignore

PLUGIN_NAME = "prompt-enhancer"

# 增强任务的采样/上限（与原一次性调用逐点一致：temperature=0.3 / max_tokens=2000）。
# 思考模式显式关闭：EngineSession 的 model_config_override 是顶层浅合并，
# override 里没有的键会从「当前窗口模型配置」漏进来（思考模式/思考等级等），
# 增强模型不支持思考时会在 extra_body 里塞无效参数 → 特殊服务商 400。
# 交给主程序注入：o1/o3 等拒收 temperature 的模型由 transport 的 skip_params 自动剔除。
_ENHANCE_PARAMS = {"温度": 0.3, "最大Token": 2000, "思考模式": False}
# turn() 内部超时（秒）与硬看门狗缓冲：daemon 线程下内部超时收尾可能整链未发生
# （cron-tasks 实测），超时后放弃等待直接报错，避免按钮永久卡在「优化中」
_TURN_TIMEOUT = 120.0
_WATCHDOG_GRACE = 30.0

DEFAULT_ENHANCE_PROMPT = (
    "你是一个提示词优化专家。请把用户输入的粗略想法改写成清晰、结构化、高信息密度的提示词："
    "明确角色与任务目标，补充必要上下文与约束、规定输出格式，将复杂要求拆解为有序步骤，"
    "消除歧义并保留用户原意，使用简洁专业的表达。"
    "只输出优化后的提示词本身，不要解释、不要用 Markdown 代码块包裹，"
    "不要输出 <think> 等思考过程内容。"
)

# 「提示词增强模型」配置项的空值 = 当前模型（下拉第一项文案）
DEFAULT_ENHANCE_MODEL_LABEL = "当前模型"
DEFAULT_ENHANCE_MODEL_VALUE = ""

# 预设下拉最多直接展示的项数（超出滚动查看，对齐主程序子智能体模板下拉）
MAX_MODEL_VISIBLE_ITEMS = 8

# 同一窗口运行中的优化任务（window_id -> True），防重复点击积压
_busy_windows: Dict[str, bool] = {}
# 当前常驻进度 InfoBar（window_id -> InfoBar 实例），完成/失败时关闭
_progress_bars: Dict[str, Any] = {}
# 按钮转圈动画（window_id -> _RotatingButtonIcon），完成/失败时停止
_button_spinners: Dict[str, Any] = {}

# 输入按钮 tooltip（与 register_input_button 保持一致，用于回查按钮控件）
_BUTTON_TOOLTIP = "优化提示词（LLM 一键增强）"


def _plugin_root() -> str:
    # ui/__init__.py -> 插件根目录
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# 主程序 LLM 配置路径（与 ip-switcher/ui/config.py 中 _get_system_config_path 同约定）
_DEFAULT_SYSTEM_CONFIG_PATHS = (
    # DriFox 运行时的标准位置
    os.path.join(os.path.expanduser("~"), ".drifox", "app.config"),
    # 项目自带调试配置（开发期可能复用）
    os.path.abspath(os.path.join(_plugin_root(), "..", "..", ".drifox", "app.config")),
)


def _resolve_system_config_path() -> Optional[str]:
    """定位主程序 app.config（不存在则返回 None，调用方需容忍空列表）。"""
    for p in _DEFAULT_SYSTEM_CONFIG_PATHS:
        if p and os.path.exists(p):
            return p
    return None


# 模块级 app.config 解析缓存：单次点击触发 3 次读盘，开销忽略但用 mtime 兜底外部修改
_SYSTEM_CONFIG_CACHE: Dict[str, Any] = {"path": None, "mtime": 0.0, "data": None}


def _load_system_config() -> Optional[Dict[str, Any]]:
    """读取并缓存主程序 app.config（按文件 mtime 失效，避免热重载期间读到陈旧快照）。

    ⚠️ 仅供读取**非密钥字段**（provider_name / 模型列表 等用于渲染下拉选项）。
    严禁用它取 API_KEY：密钥模式下磁盘该字段是密文（password 模式 enc:v2:…）
    或空串（keyring 模式），拿它发请求必然 401。要 key 走宿主
    services["get_provider_config"]（见 _get_llm_config）。
    """
    cfg_path = _resolve_system_config_path()
    if not cfg_path:
        return None
    try:
        mtime = os.path.getmtime(cfg_path)
    except OSError as e:
        logger.debug(f"[PromptEnhancer] app.config stat 失败: {e}")
        return None
    cache = _SYSTEM_CONFIG_CACHE
    if cache["path"] == cfg_path and cache["mtime"] == mtime and cache["data"] is not None:
        return cache["data"]
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        logger.debug(f"[PromptEnhancer] 读取主程序 app.config 失败: {e}")
        return None
    cache["path"] = cfg_path
    cache["mtime"] = mtime
    cache["data"] = data
    return data


def _caps(name: str) -> Any:
    """取宿主能力（设置卡无 ctx，走 caps_for 按插件名解析到活跃窗口）。"""
    try:
        from app.plugins.sdk import caps_for

        return caps_for(name, plugin=PLUGIN_NAME, surface="ui")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[PromptEnhancer] 取能力 {name} 失败: {e}")
        return None


def _load_provider_entries() -> List[Dict[str, Any]]:
    """内存态服务商清单（provider.list 能力）；不可用返回 []（调用方回退磁盘扫描）。"""
    fn = _caps("provider.list")
    if not callable(fn):
        return []
    try:
        items = fn() or []
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[PromptEnhancer] provider.list 调用失败: {e}")
        return []
    return [p for p in items if isinstance(p, dict)]


def _load_models_of(provider_id: str) -> List[str]:
    """指定服务商的模型名列表（model.enumerate 能力）；不可用返回 []。"""
    if not provider_id:
        return []
    fn = _caps("model.enumerate")
    if not callable(fn):
        return []
    try:
        items = fn(provider_id) or []
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[PromptEnhancer] model.enumerate 调用失败: {e}")
        return []
    return [str(m.get("name") or "") for m in items if isinstance(m, dict) and m.get("name")]


def _load_provider_tree() -> List[Tuple[str, str]]:
    """服务商两级下拉第一级选项：[(display, config_id)]。

    首选 provider.list（内存态，用户刚加的服务商立即可见）；能力不可用
    （旧宿主 / 无活跃窗口）回退扫描 app.config 非密钥字段。
    """
    out: List[Tuple[str, str]] = []
    for p in _load_provider_entries():
        pid = str(p.get("id") or "")
        if not pid:
            continue
        label = str(p.get("display_name") or pid)
        if p.get("is_current"):
            label = f"{label}（当前）"
        out.append((label, pid))
    if out:
        return out
    # 降级：磁盘扫描（仅非密钥字段，与旧版渲染路径同源）
    data = _load_system_config()
    if data is None:
        return []
    saved = (data.get("LLM") or {}).get("SavedProviders") or {}
    seen: set = set()
    for cid, p in saved.items():
        if not isinstance(p, dict):
            continue
        name = str(p.get("provider_name") or p.get("name") or cid).strip()
        if not cid or not name or cid in seen:
            continue
        seen.add(cid)
        out.append((name, cid))
    out.sort(key=lambda item: item[0].lower())
    return out


def _load_models_by_tree(provider_id: str) -> List[str]:
    """服务商两级下拉第二级选项：模型名列表。首选 model.enumerate，回退磁盘。"""
    models = _load_models_of(provider_id)
    if models:
        return models
    data = _load_system_config()
    if data is None:
        return []
    for cid, p in ((data.get("LLM") or {}).get("SavedProviders") or {}).items():
        if cid != provider_id or not isinstance(p, dict):
            continue
        models = [str(m).strip() for m in (p.get("模型列表") or []) if str(m).strip()]
        if not models and p.get("模型名称"):
            models = [str(p["模型名称"]).strip()]
        return models
    return []


def _parse_enhance_model(value: str) -> Optional[Tuple[str, str]]:
    """解析旧格式「enhance_model」合并值「服务商:模型名」→ (provider, model) 或 None。

    仅用于兼容历史存量配置；有效性由 get_provider_config 五级解析兜底
    （拆开的两键与设置卡新写入的完全同构），不再预校验 SavedProviders。
    """
    if not value or ":" not in value:
        return None
    provider, model = value.split(":", 1)
    provider, model = provider.strip(), model.strip()
    if provider and model:
        return provider, model
    return None


def register_ui(registry: "UIPluginRegistry") -> None:
    icon_path = os.path.join(_plugin_root(), "ui", "icons", "enhance.svg")
    registry.register_input_button(
        PLUGIN_NAME,
        "enhance",
        icon_path=icon_path if os.path.exists(icon_path) else "",
        tooltip=_BUTTON_TOOLTIP,
        on_click=_on_enhance_clicked,
    )
    _register_config_card(registry)


def unload_ui(registry: "UIPluginRegistry") -> None:
    """卸载时停止所有残留转圈动画（任务若仍在跑，按钮恢复原图标）。"""
    for window_id in list(_button_spinners.keys()):
        _stop_button_spinner(window_id)


def _register_config_card(registry: "UIPluginRegistry") -> None:
    """注册多行编辑设置卡，覆盖主程序 E1 自动卡（同 card_id、更高 priority）。

    主程序 PluginConfigCard 将 text 字段渲染为单行 LineEdit，增强指令很长不便编辑；
    插件自带多行 QPlainTextEdit + 即时保存 + 恢复默认，体验更佳。
    注册失败（旧版主程序无此扩展点）时降级为 E1 自动卡，不影响按钮功能。
    """
    try:
        registry.register_settings_card(
            PLUGIN_NAME,
            f"{PLUGIN_NAME}-config",
            "提示词增强",
            _EnhanceConfigCard,
            priority=1,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[PromptEnhancer] 设置卡注册失败（降级 E1 自动卡）: {e}")


_ConfigCardBase = ExpandSettingCard if ExpandSettingCard is not None else object  # type: ignore

# 标签列宽度与重置按钮宽度（与主程序 PluginConfigCard._FieldRow 一致，全卡对齐）
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


class _RotatingButtonIcon(QObject):
    """按钮图标转圈动画：QPainter 自绘圆环，QTimer 驱动旋转。

    样式对齐主程序「执行中」图标：开口圆环 + 圆头笔帽，缺口随角度旋转。
    纯自绘不依赖任何资源文件，主题适配：浅色主题深灰圆环，深色主题浅灰圆环，
    tick 时检测主题切换自动变色。start() 后按钮图标持续旋转，stop() 恢复原图标。
    """

    def __init__(self, button, size: int = 18, parent=None):
        super().__init__(parent)
        self._button = button
        self._size = size
        self._angle = 0
        self._orig_icon = button.icon() if hasattr(button, "icon") else QIcon()
        self._pixmap = QPixmap(size, size)
        self._pixmap.fill(Qt.transparent)
        self._timer = QTimer(self)
        self._timer.setInterval(30)  # 与子智能体一致：30ms/帧
        self._timer.timeout.connect(self._tick)

    @staticmethod
    def _ring_color(light: bool) -> str:
        """圆环颜色：浅色主题深灰（#555555），深色主题浅灰（#e6e6e6）。"""
        return "#555555" if light else "#e6e6e6"

    def start(self):
        self._angle = 0
        self._timer.start()
        self._tick()  # 立即画首帧，避免等待首个 timeout

    def stop(self):
        self._timer.stop()
        # 恢复原始图标
        try:
            self._button.setIcon(self._orig_icon)
        except RuntimeError:
            pass  # 按钮已销毁

    def _tick(self):
        self._angle = (self._angle + 12) % 360
        light = _is_light_theme()
        self._pixmap.fill(Qt.transparent)
        p = QPainter(self._pixmap)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            pen = QPen(QColor(self._ring_color(light)), 2.0)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            # 开口圆环：缺口 60°，随角度旋转
            margin = 3.0
            rect = QRectF(margin, margin, self._size - 2 * margin, self._size - 2 * margin)
            p.drawArc(rect, -self._angle * 16, 300 * 16)
        finally:
            p.end()
        try:
            self._button.setIcon(QIcon(self._pixmap))
        except RuntimeError:
            self._timer.stop()  # 按钮已销毁，停止动画


def _is_light_theme() -> bool:
    """当前是否浅色主题（失败默认深色，对齐主程序 _is_current_theme_light）。"""
    try:
        from app.utils.utils import _is_current_theme_light

        return _is_current_theme_light()
    except Exception:  # noqa: BLE001
        return False


def _find_button(main_widget):
    """按 tooltip 回查输入区插件按钮控件（主程序私有结构 _plugin_input_buttons）。"""
    try:
        for w in getattr(main_widget, "_plugin_input_buttons", []) or []:
            if getattr(w, "toolTip", lambda: "")() == _BUTTON_TOOLTIP:
                return w
    except Exception:  # noqa: BLE001
        return None
    return None


def _start_button_spinner(main_widget, window_id: str):
    """任务开始：把按钮图标切换为旋转圆环动画。"""
    try:
        button = _find_button(main_widget)
        if button is None:
            return
        spinner = _RotatingButtonIcon(button, size=18)
        _button_spinners[window_id] = spinner
        spinner.start()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[PromptEnhancer] 按钮转圈启动失败: {e}")


def _stop_button_spinner(window_id: str):
    """任务结束：停止动画并恢复按钮原图标。"""
    spinner = _button_spinners.pop(window_id, None)
    if spinner is not None:
        try:
            spinner.stop()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[PromptEnhancer] 按钮转圈停止失败: {e}")


class _EnhanceConfigCard(_ConfigCardBase):
    """提示词增强配置卡：多行编辑增强指令 + 提示词增强模型下拉 + 恢复默认。

    构造签名 (parent=None) 满足 register_settings_card 的 widget_class 约定；
    保存语义与 PluginConfigStore 一致：空内容=清除→回默认。
    下拉选项「当前模型」= 空值（沿用调用方当前 provider/model），
    其余选项为「ProviderName:ModelName」（与主程序标题生成/子智能体一致）。
    """

    def __init__(self, parent=None):
        from qfluentwidgets import FluentIcon, PushButton

        super().__init__(FluentIcon.EDIT, "提示词增强", "增强指令 + 模型选择（即时保存）", parent)
        self.viewLayout.setContentsMargins(48, 8, 48, 8)
        self.viewLayout.setSpacing(4)

        self._edit = TextEdit(self.view) if TextEdit is not None else QPlainTextEdit(self.view)
        self._edit.setPlaceholderText("用于优化用户输入的 system 指令，留空回默认")
        self._edit.setMinimumHeight(140)
        self.viewLayout.addWidget(_field_row("增强指令", self._edit, self.view, Qt.AlignTop))

        # ── 提示词增强模型选择（服务商/模型两级联动，对齐 vision-proxy）──
        self._provider_combo: Optional[ComboBox] = None
        self._model_combo: Optional[ComboBox] = None
        if ComboBox is not None:
            self._providers = _load_provider_tree()

            self._provider_combo = ComboBox(self.view)
            self._provider_combo.setMaxVisibleItems(MAX_MODEL_VISIBLE_ITEMS)
            for label, pid in self._providers:
                # 关键字 userData：qfluentwidgets.addItem 第二参数是 icon，
                # 位置传参 userData 会丢失 → currentData() 恒 None → 配置不固化
                self._provider_combo.addItem(label, userData=pid)
            self._provider_combo.setToolTip(
                "执行提示词优化的服务商。两键均空（当前模型）= 沿用调用方当前 provider/model。"
            )
            self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
            self.viewLayout.addWidget(_field_row("服务商", self._provider_combo, self.view))

            self._model_combo = ComboBox(self.view)
            self._model_combo.setMaxVisibleItems(MAX_MODEL_VISIBLE_ITEMS)
            self._model_combo.setToolTip(
                "执行提示词优化的模型（清单随上方服务商联动）。"
            )
            self._model_combo.currentIndexChanged.connect(self._on_model_changed)
            self.viewLayout.addWidget(_field_row("模型", self._model_combo, self.view))

        self._reset_btn = PushButton("恢复默认", self.view)
        self._reset_btn.clicked.connect(self._on_reset)
        self.viewLayout.addWidget(_reset_row(self._reset_btn, self.view))

        self._echo()

    def _adjustViewSize(self):
        """空白占位归零：qfluentwidgets 的 setExpand 会先调 _adjustViewSize 把
        spaceWidget 重设为内容等高，导致展开高度 = 内容 + 等高空白。
        与覆写的 setExpand 配套：spaceWidget 恒 0，高度直接在标题卡与
        标题卡+内容之间切换（原版折叠动画依赖 spaceWidget 滚动余量，
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

    def _echo(self) -> None:
        """回显当前生效值（默认兜底可见）；阻断信号循环。"""
        # 多行编辑框
        while True:
            try:
                self._edit.textChanged.disconnect()
            except TypeError:
                break
        val = PluginConfigStore().get(PLUGIN_NAME, "enhance_prompt")
        text = str(val) if val else DEFAULT_ENHANCE_PROMPT
        self._edit.setPlainText(text)
        self._edit.textChanged.connect(self._on_changed)

        # 服务商/模型两级下拉回显（旧格式「服务商:模型」合并值拆开，不丢配置）
        if self._provider_combo is None:
            return
        stored_provider = str(PluginConfigStore().get(PLUGIN_NAME, "enhance_provider") or "")
        stored_model = str(PluginConfigStore().get(PLUGIN_NAME, "enhance_model") or "")
        if not stored_provider and ":" in stored_model:
            parsed_old = _parse_enhance_model(stored_model)
            if parsed_old is not None:
                stored_provider, stored_model = parsed_old

        self._provider_combo.blockSignals(True)
        idx = self._provider_combo.findData(stored_provider)
        if idx < 0 and stored_provider:
            # 已存值不在清单里（服务商被删/能力降级）：插到首位保住它
            self._provider_combo.insertItem(0, stored_provider, userData=stored_provider)
            idx = 0
        self._provider_combo.setCurrentIndex(max(0, idx))
        self._provider_combo.blockSignals(False)

        self._fill_models(str(self._provider_combo.currentData() or ""), stored_model)

    def _fill_models(self, provider_id: str, selected: str = "") -> None:
        """按服务商重填模型下拉；首项「当前模型」= 空（沿用该服务商默认/当前窗口）。"""
        if self._model_combo is None:
            return
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        self._model_combo.addItem(DEFAULT_ENHANCE_MODEL_LABEL, userData=DEFAULT_ENHANCE_MODEL_VALUE)
        for name in _load_models_by_tree(provider_id):
            self._model_combo.addItem(name, userData=name)
        idx = self._model_combo.findData(selected)
        if idx < 0 and selected:
            # 已存模型不在清单里（服务商模型变更）：插到「当前模型」之后保住它
            self._model_combo.insertItem(1, selected, userData=selected)
            idx = 1
        self._model_combo.setCurrentIndex(max(0, idx))
        self._model_combo.blockSignals(False)

    def _on_changed(self) -> None:
        PluginConfigStore().set_values(PLUGIN_NAME, {"enhance_prompt": self._edit.toPlainText().strip()})

    def _on_provider_changed(self, _index: int) -> None:
        if self._provider_combo is None:
            return
        pid = str(self._provider_combo.currentData() or "")
        PluginConfigStore().set_values(PLUGIN_NAME, {"enhance_provider": pid})
        # 换服务商后模型清单全变，清空模型值避免指向不存在的模型
        PluginConfigStore().set_values(PLUGIN_NAME, {"enhance_model": ""})
        self._fill_models(pid)

    def _on_model_changed(self, _index: int) -> None:
        if self._model_combo is None:
            return
        value = self._model_combo.currentData() or DEFAULT_ENHANCE_MODEL_VALUE
        PluginConfigStore().set_values(PLUGIN_NAME, {"enhance_model": str(value)})

    def _on_reset(self) -> None:
        PluginConfigStore().set_values(
            PLUGIN_NAME,
            {
                "enhance_prompt": DEFAULT_ENHANCE_PROMPT,
                "enhance_provider": "",
                "enhance_model": DEFAULT_ENHANCE_MODEL_VALUE,
            },
        )
        self._echo()


def _get_provider_config_from_memory(
    main_widget, provider: str = "", model: str = ""
) -> Optional[Dict[str, Any]]:
    """从宿主**内存态**取服务商配置（含已解密明文 API_KEY）。

    兜底路径：宿主未提供 services["get_provider_config"]（旧版主程序）时使用。
    严禁读 app.config 文件——密钥模式下磁盘 API_KEY 是密文（enc:v2:…）或空串，
    拿它发请求必然 401。
    """
    valid = getattr(main_widget, "_valid_configs", None)
    if not isinstance(valid, dict) or not valid:
        return None
    if provider:
        # 按 config_id / display_name / provider_name 匹配（与主程序五级解析同序）
        if provider in valid:
            return dict(valid[provider])
        for _cid, info in valid.items():
            if not isinstance(info, dict):
                continue
            if provider in (info.get("display_name"), info.get("provider_name"), info.get("name")):
                return dict(info)
        return None
    name = getattr(main_widget, "_current_provider_name", None) or ""
    cfg = valid.get(name)
    return dict(cfg) if isinstance(cfg, dict) else None


def _get_llm_config(
    main_widget,
    override_provider: Optional[str] = None,
    override_model: Optional[str] = None,
    services: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """取执行本次提示词增强的模型配置（API_KEY / API_URL / 模型名称）。

    取配置的**唯一正确通道**是宿主：
    1. services["get_provider_config"]（主程序公开服务，读内存态已解锁明文，
       并叠加模型默认参数，与主程序发起请求的配置同构）；
    2. 兜底遍历 main_widget._valid_configs（同为内存态，旧版主程序无服务时用）。

    绝不 json.load(app.config)：密钥模式下磁盘 API_KEY 是密文或空串。

    override_provider/override_model 均提供时优先用该服务商；否则沿用调用方
    当前 provider/model。返回 None 表示无可用配置（需提示用户先配置模型）。
    """
    provider = override_provider or ""
    model = override_model or ""

    # 1) 宿主公开服务（首选）
    if isinstance(services, dict):
        get_cfg = services.get("get_provider_config")
        if callable(get_cfg):
            try:
                cfg = get_cfg(provider, model)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[PromptEnhancer] get_provider_config 调用失败: {e}")
                cfg = None
            # 判据是「配置非空」而非「key 非空」：免鉴权服务商（如 OpenCode 免费
            # 模型）API_KEY 本就为空，build_openai_client 会剥掉 Authorization 头
            if isinstance(cfg, dict) and cfg:
                return cfg
            # 服务返回空（provider 不存在 / 宿主未就绪）→ 继续兜底，
            # 显式指名的 provider 失效时不静默串到别的服务商
            if provider:
                return None

    # 2) 内存态兜底（旧版主程序 / 未注入 services 的调用路径）
    cfg = _get_provider_config_from_memory(main_widget, provider, model)
    if not isinstance(cfg, dict):
        return None
    if model:
        cfg["模型名称"] = model
    return cfg


def _resolve_enhance_model(main_widget) -> Optional[Tuple[str, str]]:
    """读取 enhance_provider + enhance_model 配置 → (provider, model) 或 None。

    服务商、模型分开存（对齐 vision-proxy）；enhance_model 存旧格式
    「服务商:模型名」时拆分兼容。两键均空/解析失败 → 回退到调用方当前
    provider/model（保证任务不空跑）；再失败 → None。
    """
    provider = str(PluginConfigStore().get(PLUGIN_NAME, "enhance_provider") or "").strip()
    model = str(PluginConfigStore().get(PLUGIN_NAME, "enhance_model") or "").strip()
    if not provider and ":" in model:
        parsed_old = _parse_enhance_model(model)
        if parsed_old is not None:
            provider, model = parsed_old
    if provider or model:
        return provider, model
    # 兜底：用调用方当前 provider + model（即便解析失败也保证能跑）
    valid = getattr(main_widget, "_valid_configs", None)
    if isinstance(valid, dict):
        cur_name = getattr(main_widget, "_current_provider_name", None) or "系统默认配置"
        cur_cfg = valid.get(cur_name) or {}
        provider = (
            cur_cfg.get("provider_name")
            or cur_cfg.get("name")
            or cur_name
        )
        model = cur_cfg.get("模型名称") or ""
        if provider and model:
            return str(provider), str(model)
    return None


def _on_enhance_clicked(context: Dict[str, Any]) -> None:
    main_widget = context.get("main_widget")
    if main_widget is None:
        return
    input_area = getattr(main_widget, "input_area", None)
    if input_area is None:
        return
    window_id = context.get("window_id") or "default"

    # 防积压：同窗口已有优化任务 → 提示并忽略本次点击
    if _busy_windows.get(window_id):
        _notify(main_widget, "提示词增强", "正在优化中，请稍候…", "warning")
        return

    text = input_area.toPlainText().strip()
    if not text:
        _notify(main_widget, "提示词增强", "输入框为空，无可优化的内容", "warning")
        return

    enhance_prompt = (
        PluginConfigStore().get(PLUGIN_NAME, "enhance_prompt") or DEFAULT_ENHANCE_PROMPT
    ).strip()
    if not enhance_prompt:
        enhance_prompt = DEFAULT_ENHANCE_PROMPT

    # 模型选择：enhance_model 配置优先，否则沿用调用方当前模型
    override = _resolve_enhance_model(main_widget)
    llm_config = _get_llm_config(
        main_widget,
        override_provider=override[0] if override else None,
        override_model=override[1] if override else None,
        services=context.get("services"),
    )
    if not llm_config:
        _notify(main_widget, "提示词增强", "未找到模型配置，请先在设置中配置模型", "warning")
        return
    llm_config = {**llm_config, **_ENHANCE_PARAMS}

    _busy_windows[window_id] = True
    _show_progress(main_widget, window_id, "正在优化提示词…")
    _start_button_spinner(main_widget, window_id)

    signals = _EnhanceSignals()
    signals.done.connect(
        lambda result, _t=text: _on_done(main_widget, input_area, result, window_id, original_text=_t)
    )
    signals.error.connect(lambda err: _on_error(main_widget, err, window_id))

    task = _EnhanceTask(
        text=text,
        enhance_prompt=enhance_prompt,
        llm_config=llm_config,
        signals=signals,
        services=context.get("services"),
    )
    pool = getattr(main_widget, "_gen_thread_pool", None) or QThreadPool.globalInstance()
    pool.start(task)


class _EnhanceSignals(QObject):
    done = pyqtSignal(str)
    error = pyqtSignal(str)


class _EnhanceTask(QRunnable):
    """一次性增强任务 — 经宿主 EngineSession（EP3 契约）驱动。

    原实现自建 openai client 直发 chat.completions.create，绕过
    ModelAdapter / Serializer / Transport 三层分派，导致：
    - 服务商伪装头缺失（CodeBuddy X-Product + 动态 Authorization、
      OpenCode x-opencode-session）→ 401 / 400 MissingSessionID
    - GPT-5 系应走 /v1/responses、Code Assist 应走原生协议 → 400
    - 思考参数映射 / max_tokens 钳制 / 15 次智能重试全部失效

    改走 create_engine_session 后以上链路自动生效，插件零协议知识。
    """

    def __init__(self, text, enhance_prompt, llm_config, signals, services=None):
        super().__init__()
        self.text = text
        self.enhance_prompt = enhance_prompt
        self.llm_config = llm_config
        self.signals = signals
        self.services = services
        self.setAutoDelete(True)

    def run(self):
        holder: Dict[str, Any] = {}
        done = threading.Event()

        def _turn():
            try:
                create = (self.services or {}).get("create_engine_session")
                if not callable(create):
                    holder["error"] = "主程序未提供 create_engine_session 服务，请升级 DriFox 至 0.5.10+"
                    return
                session: Any = create(
                    "prompt-enhancer",
                    model_config_override=self.llm_config,
                    # 全局 hook 全跳过：BuildSystemPrompt 等注入会混进增强指令污染输出
                    hook_policy_id="none",
                )
                try:
                    result = session.turn(
                        system=self.enhance_prompt,
                        user=self.text,
                        tools=[],
                        timeout=_TURN_TIMEOUT,
                    )
                finally:
                    session.cleanup()
                if getattr(result, "timed_out", False):
                    holder["error"] = f"优化超时（>{int(_TURN_TIMEOUT)}s）"
                elif getattr(result, "cancelled", False):
                    holder["error"] = "已取消"
                elif getattr(result, "error", None):
                    holder["error"] = str(result.error)
                else:
                    holder["text"] = getattr(result, "text", "") or ""
            except Exception as e:  # 顶层屏障：后台线程静默死亡比报错更糟
                logger.exception(f"[PromptEnhancer] 增强失败: {e}")
                holder["error"] = f"{type(e).__name__}: {e}"
            finally:
                done.set()

        threading.Thread(target=_turn, daemon=True, name="pe-turn").start()

        # 硬看门狗：不信任 turn() 内部超时（cron-tasks 实测 daemon 线程下超时收尾
        # 可能整链不发生），到期放弃等待直接报错，避免按钮永久卡在「优化中」
        if not done.wait(_TURN_TIMEOUT + _WATCHDOG_GRACE):
            self.signals.error.emit(f"优化超时（>{int(_TURN_TIMEOUT)}s），已放弃等待")
            return
        err = holder.get("error")
        if err:
            self.signals.error.emit(str(err))
        else:
            self.signals.done.emit(_strip_thinking(holder.get("text", "")))


def _strip_thinking(text: str) -> str:
    """移除模型输出中的 <think>…</think> 思考内容（对齐主程序 history_compactor）。"""
    if not text:
        return text
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return text.strip()


def _on_done(main_widget, input_area, result, window_id, original_text=""):
    _close_progress(window_id)
    _stop_button_spinner(window_id)
    _busy_windows.pop(window_id, None)
    if result:
        # 追加增强提示词到原用户问题后面，不替换原问题
        combined = f"{original_text}\n\n{result}".strip()
        input_area.setPlainText(combined)
        _notify(main_widget, "提示词增强", "已优化并追加到输入框（保留原问题）", "success")
    else:
        _notify(main_widget, "提示词增强", "模型返回为空", "warning")


def _on_error(main_widget, err, window_id):
    _close_progress(window_id)
    _stop_button_spinner(window_id)
    _busy_windows.pop(window_id, None)
    _notify(main_widget, "提示词增强", f"增强失败：{err}", "error")


def _show_progress(main_widget, window_id, text):
    """常驻 InfoBar 提示（duration=0 不自动关闭），完成/失败时由 _close_progress 关闭。"""
    try:
        from qfluentwidgets import InfoBar, InfoBarPosition

        bar = InfoBar.info(
            "提示词增强",
            text,
            parent=main_widget,
            duration=0,
            isClosable=False,
            position=InfoBarPosition.BOTTOM,
        )
        _progress_bars[window_id] = bar
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[PromptEnhancer] 进度提示失败: {e}")


def _close_progress(window_id):
    bar = _progress_bars.pop(window_id, None)
    if bar is not None:
        try:
            bar.close()
        except RuntimeError:
            pass


def _notify(main_widget, title, content, kind="info"):
    try:
        from qfluentwidgets import InfoBar, InfoBarPosition

        fn = getattr(InfoBar, kind, InfoBar.info)
        fn(title, content, parent=main_widget, position=InfoBarPosition.BOTTOM)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[PromptEnhancer] InfoBar 失败: {e}")
