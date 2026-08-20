# -*- coding: utf-8 -*-
"""提示词增强 UI 插件（闭包实现，不修改主程序）。

输入框按钮「优化提示词」：点击后用 LLM（复用主程序当前会话模型配置）把
输入框原文优化为更清晰、结构化、高信息密度的提示词，并注回输入框。

体验完善（v0.2.0）：
- 系统配置开放增强指令：注册「提示词增强」设置卡（多行编辑 + 即时保存 + 恢复默认），
  覆盖主程序 E1 自动卡（单行 LineEdit），长指令编辑不再痛苦；
- 防任务积压：同一窗口同时只允许一个优化任务，运行中重复点击给出提示并忽略；
- 进度可感知：运行中常驻 InfoBar「正在优化提示词…」，完成/失败后关闭并给出结果提示。

实现要点：
- 通过 UI 扩展点 context["main_widget"] 读取输入框（input_area）与当前模型配置；
- 通过 PluginConfigStore 读写插件配置（enhance_prompt）；
- 一次性对话范式复用 app.utils.http_client.build_openai_client（参考 topic_summary.py）；
- 后台 QRunnable + 信号桥接，结果在主线程注回输入框，避免 UI 卡死。

模型配置来自 main_widget._valid_configs（私有状态，非公开 API），用户已确认接受复用。
"""

import os
from typing import Any, Dict, Optional

from loguru import logger
from PyQt5.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt5.QtWidgets import QPlainTextEdit

from app.plugins.managers.plugin_config_store import PluginConfigStore
from app.plugins.registries.ui_plugin_registry import UIPluginRegistry

try:  # 模块级导入设置卡基类；失败则跳过自定义设置卡注册
    from qfluentwidgets import ExpandSettingCard
except Exception:  # noqa: BLE001
    ExpandSettingCard = None  # type: ignore

PLUGIN_NAME = "prompt-enhancer"

DEFAULT_ENHANCE_PROMPT = (
    "你是一个提示词优化专家。请把用户输入的粗略想法改写成清晰、结构化、高信息密度的提示词："
    "明确角色与任务目标，补充必要上下文与约束、规定输出格式，将复杂要求拆解为有序步骤，"
    "消除歧义并保留用户原意，使用简洁专业的表达。"
    "只输出优化后的提示词本身，不要解释、不要用 Markdown 代码块包裹。"
)

# 同一窗口运行中的优化任务（window_id -> True），防重复点击积压
_busy_windows: Dict[str, bool] = {}
# 当前常驻进度 InfoBar（window_id -> InfoBar 实例），完成/失败时关闭
_progress_bars: Dict[str, Any] = {}


def _plugin_root() -> str:
    # ui/__init__.py -> 插件根目录
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def register_ui(registry: "UIPluginRegistry") -> None:
    icon_path = os.path.join(_plugin_root(), "ui", "icons", "enhance.svg")
    registry.register_input_button(
        PLUGIN_NAME,
        "enhance",
        icon_path=icon_path if os.path.exists(icon_path) else "",
        tooltip="优化提示词（LLM 一键增强）",
        on_click=_on_enhance_clicked,
    )
    _register_config_card(registry)


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


class _EnhanceConfigCard(_ConfigCardBase):
    """提示词增强配置卡：多行编辑增强指令 + 恢复默认。

    构造签名 (parent=None) 满足 register_settings_card 的 widget_class 约定；
    保存语义与 PluginConfigStore 一致：空内容=清除→回默认。
    """

    def __init__(self, parent=None):
        from qfluentwidgets import FluentIcon, PushButton

        super().__init__(FluentIcon.EDIT, "提示词增强", "增强指令（多行编辑，即时保存）", parent)
        self.viewLayout.setContentsMargins(48, 8, 48, 8)
        self.viewLayout.setSpacing(8)

        self._edit = QPlainTextEdit(self.view)
        self._edit.setPlaceholderText("用于优化用户输入的 system 指令，留空回默认")
        self._edit.setMinimumHeight(140)
        self.viewLayout.addWidget(self._edit)

        self._reset_btn = PushButton("恢复默认", self.view)
        self._reset_btn.clicked.connect(self._on_reset)
        self.viewLayout.addWidget(self._reset_btn)

        self._echo()

    def _echo(self) -> None:
        """回显当前生效值（默认兜底可见）；阻断 textChanged 循环。"""
        while True:
            try:
                self._edit.textChanged.disconnect()
            except TypeError:
                break
        val = PluginConfigStore().get(PLUGIN_NAME, "enhance_prompt")
        text = str(val) if val else DEFAULT_ENHANCE_PROMPT
        self._edit.setPlainText(text)
        self._edit.textChanged.connect(self._on_changed)

    def _on_changed(self) -> None:
        PluginConfigStore().set_values(PLUGIN_NAME, {"enhance_prompt": self._edit.toPlainText().strip()})

    def _on_reset(self) -> None:
        PluginConfigStore().set_values(PLUGIN_NAME, {"enhance_prompt": DEFAULT_ENHANCE_PROMPT})
        self._echo()


def _get_llm_config(main_widget) -> Optional[Dict[str, Any]]:
    """复用主程序当前会话模型配置（私有状态，非公开 API；用户已确认接受）。"""
    valid = getattr(main_widget, "_valid_configs", None)
    if not isinstance(valid, dict):
        return None
    name = getattr(main_widget, "_current_provider_name", None) or "系统默认配置"
    return valid.get(name)


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

    llm_config = _get_llm_config(main_widget)
    if not llm_config:
        _notify(main_widget, "提示词增强", "未找到模型配置，请先在设置中配置模型", "warning")
        return

    _busy_windows[window_id] = True
    _show_progress(main_widget, window_id, "正在优化提示词…")

    signals = _EnhanceSignals()
    signals.done.connect(lambda result: _on_done(main_widget, input_area, result, window_id))
    signals.error.connect(lambda err: _on_error(main_widget, err, window_id))

    task = _EnhanceTask(
        text=text,
        enhance_prompt=enhance_prompt,
        llm_config=llm_config,
        signals=signals,
    )
    pool = getattr(main_widget, "_gen_thread_pool", None) or QThreadPool.globalInstance()
    pool.start(task)


class _EnhanceSignals(QObject):
    done = pyqtSignal(str)
    error = pyqtSignal(str)


class _EnhanceTask(QRunnable):
    def __init__(self, text, enhance_prompt, llm_config, signals):
        super().__init__()
        self.text = text
        self.enhance_prompt = enhance_prompt
        self.llm_config = llm_config
        self.signals = signals
        self.setAutoDelete(True)

    def run(self):
        try:
            from app.utils.http_client import build_openai_client

            client = build_openai_client(
                api_key=self.llm_config.get("API_KEY", ""),
                base_url=self.llm_config.get("API_URL"),
            )
            resp = client.chat.completions.create(
                model=self.llm_config.get("模型名称", "gpt-4o"),
                messages=[
                    {"role": "system", "content": self.enhance_prompt},
                    {"role": "user", "content": self.text},
                ],
                temperature=0.3,
                max_tokens=2000,
            )
            result = resp.choices[0].message.content.strip()
            self.signals.done.emit(result)
        except Exception as e:
            logger.exception(f"[PromptEnhancer] 增强失败: {e}")
            self.signals.error.emit(str(e))


def _on_done(main_widget, input_area, result, window_id):
    _close_progress(window_id)
    _busy_windows.pop(window_id, None)
    if result:
        input_area.setPlainText(result)
        _notify(main_widget, "提示词增强", "已优化并填入输入框", "success")
    else:
        _notify(main_widget, "提示词增强", "模型返回为空", "warning")


def _on_error(main_widget, err, window_id):
    _close_progress(window_id)
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
