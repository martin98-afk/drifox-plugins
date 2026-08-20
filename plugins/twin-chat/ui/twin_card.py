# -*- coding: utf-8 -*-
"""twin-chat 浮动卡片 — 内嵌第二对话窗口实例

复用主程序 OpenAIChatToolWindow（复制模式 source_window）：
- 继承当前活跃窗口的项目上下文 / 模型选择
- 独立 backend + SessionManager → 与主对话并行生成，互不阻塞
- 卡片即唯一实例（registry per-window 懒创建单例）
- 隐藏=保留会话状态，再次 /twin-chat 显示继续对话

复刻链路参照 app/main_widget.py `_duplicate_window`（branch=False 路径），
但不进 TabManagerWindow 标签列表，改为嵌入卡片容器。
"""

from loguru import logger
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget


class TwinChatCard(QWidget):
    """并发对话浮动卡片：内嵌 OpenAIChatToolWindow 复制实例"""

    closed = pyqtSignal()

    # 类级实例句柄（供 unload_ui 清理，与 workbuddy ArtifactPanelCard._instance 同模式）
    _instance = None

    def __init__(self, parent=None):
        super().__init__(parent)
        TwinChatCard._instance = self
        self._context_provider = None
        self._chat_window = None  # 内嵌的第二对话窗口实例

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._chat_window = self._create_twin_window()
        if self._chat_window is not None:
            layout.addWidget(self._chat_window)
        else:
            # 无活跃窗口兜底：提示卡片（正常流程不会走到，Tab 模式总有窗口）
            hint = QLabel("无活跃对话窗口，请先打开一个对话标签页后重试")
            hint.setWordWrap(True)
            hint.setStyleSheet("color: #888; padding: 24px;")
            layout.addWidget(hint)

    # ── registry 注入接口（拉模型，与 browser 卡片同约定）──

    def set_context_provider(self, provider):
        self._context_provider = provider

    def show_card(self):
        """卡片显示时回调（registry 调用）"""
        if self._chat_window is not None:
            self._chat_window.show()

    # ── 内嵌窗口创建 ──

    def _create_twin_window(self):
        """创建第二对话窗口（复制当前窗口上下文，独立会话）

        Returns:
            OpenAIChatToolWindow 或 None（无活跃窗口时）
        """
        try:
            from app.main_widget import OpenAIChatToolWindow
            from app.widgets.tab_manager_window import TabManagerWindow

            tm = TabManagerWindow.get_instance()
            source = tm.get_current_window() if tm is not None else None
            if source is None:
                logger.warning("[twin-chat] 无活跃对话窗口，无法创建并发对话")
                return None

            # 复制模式构造：__init__ 内 setup_ui 据此跳过 git 子进程等冗余初始化
            win = OpenAIChatToolWindow(source.homepage, source_window=source)

            # ── 上下文复制（对齐 _duplicate_window 核心步骤）──
            win._current_project = source._current_project
            win.backend._current_project = source._current_project
            if win.backend.tool_executor is not None:
                win.backend.tool_executor.set_current_project(source._current_project)

            # 模型选择复制（避免新窗口从全局 cfg 读到错位的最新选择）
            if getattr(source, "_current_provider_name", ""):
                win._current_provider_name = source._current_provider_name
                win._current_model_name = source._current_model_name
                win._user_manually_selected_model = getattr(
                    source, "_user_manually_selected_model", False
                )
                win._valid_configs = dict(source._valid_configs)
                if hasattr(win, "_update_model_selector_btn"):
                    win._update_model_selector_btn()

            # 新空白会话（showEvent 的 duplicate 分支据此走 _create_new_session）
            win._skip_restore_history = True
            win.setWindowTitle("⚡ 并发对话")
            logger.info(f"[twin-chat] 已创建并发对话窗口（源: {source._current_project}）")
            return win
        except Exception:
            logger.exception("[twin-chat] 创建并发对话窗口失败")
            return None

    # ── 生命周期 ──

    def cleanup(self):
        """显式清理内嵌窗口（插件卸载/热重载时由 unload_ui 调用）

        走 close() 触发 OpenAIChatToolWindow.closeEvent 的完整清理链：
        断开引用环 / 信号闭包 / 标记 _is_destroyed。
        """
        if self._chat_window is not None:
            try:
                self._chat_window.close()
            except RuntimeError:
                pass  # C++ 对象已销毁
            except Exception:
                logger.exception("[twin-chat] 清理内嵌窗口失败")
            self._chat_window = None
        TwinChatCard._instance = None
