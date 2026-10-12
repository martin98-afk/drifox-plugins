# -*- coding: utf-8 -*-
"""voice-reply UI 插件：消息卡片页脚「朗读」按钮 → 播报本条 AI 回复。

交互：助手卡片页脚扬声器按钮（hover 出现，与内置复制/分支同排）→ 点击朗读
本条消息纯文本 → 播放中（在线引擎）再次点击停止。本地引擎为即时播报、
再次点击打断并重播（SAPI5 异步队列 / say 进程重建）。

双引擎（设置 → 语音播报配置 可选）：
- 本地系统语音（默认）：Windows SAPI5（win32com）/ macOS `say`，免费零配置
- 在线 API：OpenAI 兼容 POST /audio/speech（默认预填硅基流动 CosyVoice2，
  极低价；也可指向自部署免费服务如 openai-edge-tts），wav 落临时文件，
  Windows winsound / macOS afplay 播放
"""

from __future__ import annotations

import re
import sys
from typing import Any, Dict

from loguru import logger

PLUGIN_NAME = "voice-reply"
_ACTION_ID = f"{PLUGIN_NAME}:speak"
_TOOLTIP = "朗读本条回复"

# 播报文本上限（字），避免语音队列/合成请求过长
_MAX_TEXT_LEN = 500

# 在线引擎默认端点（OpenAI 兼容；极低价，也可改为任意兼容服务）
_DEFAULT_API_URL = "https://api.siliconflow.cn/v1/audio/speech"
_DEFAULT_API_MODEL = "FunAudioLLM/CosyVoice2-0.5B"
_DEFAULT_API_VOICE = "FunAudioLLM/CosyVoice2-0.5B:alex"

# 在线 worker 单例（合成+播放期间 busy）
_worker = None  # ApiTtsWorker
# macOS 本地 say 进程（新播报杀旧进程）
_say_proc = None
# Windows SAPI5 引擎（主线程懒创建，主线程调用 COM 安全）
_sapi_voice = None


def _icons_dir():
    from pathlib import Path

    return Path(__file__).resolve().parent / "icons"


def _notify(main_widget, kind: str, title: str, msg: str) -> None:
    """提示统一走 InfoBar（QToolTip 在 DriFox 内不可靠），失败静默降级。"""
    try:
        from qfluentwidgets import InfoBar, InfoBarPosition

        factory = {
            "success": InfoBar.success,
            "warning": InfoBar.warning,
            "error": InfoBar.error,
            "info": InfoBar.info,
        }[kind]
        factory(
            title,
            msg,
            parent=main_widget,
            position=InfoBarPosition.BOTTOM,
            duration=3000,
        )
    except Exception as e:  # noqa: BLE001 — 提示失败不影响主流程
        logger.warning(f"[voice-reply] InfoBar 提示失败: {e}")


def _read_config() -> Dict[str, str]:
    """读插件配置。主程序未注入配置系统/读取失败时按默认值降级。"""
    try:
        from app.plugins.managers.plugin_config_store import PluginConfigStore

        store = PluginConfigStore()
        return {
            "engine": str(store.get(PLUGIN_NAME, "engine") or "local").strip(),
            "api_url": str(store.get(PLUGIN_NAME, "api_url") or "").strip()
            or _DEFAULT_API_URL,
            "api_model": str(store.get(PLUGIN_NAME, "api_model") or "").strip()
            or _DEFAULT_API_MODEL,
            "api_voice": str(store.get(PLUGIN_NAME, "api_voice") or "").strip()
            or _DEFAULT_API_VOICE,
            "api_key": str(store.get(PLUGIN_NAME, "api_key") or "").strip(),
        }
    except Exception as e:  # noqa: BLE001 — 配置不可用走默认值
        logger.warning(f"[voice-reply] 读取插件配置失败，按默认: {e}")
        return {"engine": "local", "api_url": "", "api_model": "", "api_voice": "", "api_key": ""}


_MARKDOWN_PATTERNS = [
    (re.compile(r"```.*?```", re.S), "，代码略，"),  # 代码块整体略读
    (re.compile(r"`([^`]*)`"), r"\1"),  # 行内代码去反引号
    (re.compile(r"!\[([^\]]*)\]\([^)]*\)"), r"\1"),  # 图片留 alt
    (re.compile(r"\[([^\]]*)\]\([^)]*\)"), r"\1"),  # 链接留文字
    (re.compile(r"(\*\*|__)(.*?)\1"), r"\2"),  # 粗体
    (re.compile(r"(\*|_)(.*?)\1"), r"\2"),  # 斜体
    (re.compile(r"^#{1,6}\s*", re.M), ""),  # 标题井号
    (re.compile(r"^\s*[-*+]\s+", re.M), ""),  # 列表符号
    (re.compile(r"\|"), "，"),  # 表格竖线
    (re.compile(r"\n{2,}"), "。\n"),  # 多空行收成句号停顿
]


def _clean_for_tts(text: str) -> str:
    """轻度清洗 markdown 标记，避免朗读器读出符号。"""
    for pattern, repl in _MARKDOWN_PATTERNS:
        text = pattern.sub(repl, text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"，{2,}", "，", text)  # 表格竖线等替换产生的连续逗号
    return text.strip()


# ============================================================
# 本地引擎（Windows SAPI5 / macOS say）
# ============================================================


def _get_sapi_voice():
    """主线程懒创建 SAPI SpVoice（优先中文语音）。失败返回 None。"""
    global _sapi_voice
    if _sapi_voice is not None:
        return _sapi_voice
    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()  # Qt 主线程默认无 COM 初始化
        engine = win32com.client.Dispatch("SAPI.SpVoice")
        try:
            voices = engine.GetVoices()
            for i in range(voices.Count):
                if "Chinese" in voices.Item(i).GetDescription():
                    engine.Voice = voices.Item(i)
                    break
        except Exception:  # noqa: BLE001 — 无中文语音时用系统默认
            pass
        try:
            engine.Rate = 1
        except Exception:  # noqa: BLE001
            pass
        _sapi_voice = engine
        return engine
    except Exception as e:  # noqa: BLE001 — 非 win/缺 win32com
        logger.warning(f"[voice-reply] SAPI5 引擎不可用: {e}")
        return None


def _speak_local(text: str, main_widget) -> None:
    """本地引擎即时播报：再次点击打断并重播。"""
    global _say_proc
    if sys.platform == "darwin":
        try:
            from PyQt5.QtCore import QProcess

            if _say_proc is not None:
                _say_proc.kill()
            _say_proc = QProcess()
            _say_proc.start("say", [text])
            return
        except Exception as e:  # noqa: BLE001
            _notify(main_widget, "error", "语音播报", f"本地播报失败：{e}")
            return
    engine = _get_sapi_voice()
    if engine is None:
        _notify(main_widget, "error", "语音播报", "本地语音引擎不可用（SAPI5/win32com）")
        return
    try:
        engine.Skip("Sentence", 9999)  # 清空旧播报队列，实现打断重播
        engine.Speak(text, 1)  # SVSFlagsAsync = 1，立即返回不阻塞 UI
    except Exception as e:  # noqa: BLE001
        _notify(main_widget, "error", "语音播报", f"播报失败：{e}")


# ============================================================
# 在线引擎（OpenAI 兼容 /audio/speech）
# ============================================================


def _stop_api() -> None:
    """停止在线合成/播放。"""
    global _worker
    if _worker is None:
        return
    worker, _worker = _worker, None
    worker.stop()
    worker.wait(2000)


def _start_api(cfg: Dict[str, str], text: str, ctx: Dict[str, Any]) -> None:
    """启动在线合成 worker。"""
    global _worker
    if not cfg.get("api_key"):
        _notify(ctx.get("main_widget"), "warning", "语音播报", "未配置 API Key，请到 设置 → 语音播报配置 填写")
        return
    from .tts_engine import ApiTtsWorker

    worker = ApiTtsWorker(
        cfg["api_url"], cfg["api_model"], cfg["api_voice"], cfg["api_key"], text
    )
    mw = ctx.get("main_widget")

    def _on_status(msg: str) -> None:
        _notify(mw, "info", "语音播报", msg)

    def _on_failed(msg: str) -> None:
        _reset_worker(worker)
        _notify(mw, "error", "语音播报", msg)

    def _on_done() -> None:
        _reset_worker(worker)

    worker.status.connect(_on_status)
    worker.failed.connect(_on_failed)
    worker.finished_ok.connect(_on_done)
    worker.finished.connect(lambda: _reset_worker(worker))
    _worker = worker
    worker.start()


def _reset_worker(worker) -> None:
    """worker 收尾：仅当仍是当前 worker 时清引用（幂等）。"""
    global _worker
    if _worker is worker:
        _worker = None


# ============================================================
# 按钮回调 + 注册
# ============================================================


def _on_click(ctx: Dict[str, Any]) -> None:
    """页脚按钮回调：取本条消息纯文本播报。"""
    card = ctx.get("card")
    try:
        text = (card.get_plain_text() if card is not None else "") or ""
    except Exception:  # noqa: BLE001 — 卡片接口异常按空文本处理
        text = ""
    text = _clean_for_tts(text.strip())
    if len(text) < 3:
        _notify(ctx.get("main_widget"), "warning", "语音播报", "本条消息没有可朗读的文本")
        return
    if len(text) > _MAX_TEXT_LEN:
        text = text[:_MAX_TEXT_LEN] + "……"

    cfg = _read_config()
    if cfg.get("engine") == "api":
        if _worker is not None:
            _stop_api()
            return
        _start_api(cfg, text, ctx)
        return
    _speak_local(text, ctx.get("main_widget"))


def register_ui(registry) -> None:
    """注册消息卡片页脚「朗读」按钮。热重载时主程序重新调用本函数。"""
    # 热重载兼容：清理旧子模块缓存（避免 Python 用旧 sys.modules 引用）
    prefix = "ui_plugin_voice_reply."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    icons = _icons_dir()
    registry.register_footer_action(
        plugin_name=PLUGIN_NAME,
        action_id=_ACTION_ID,
        icon_path=str(icons / "speaker.svg"),
        icon_light_path=str(icons / "speaker_light.svg"),
        tooltip=_TOOLTIP,
        on_click=_on_click,
        priority=0,
    )
    logger.info("[voice-reply] 消息卡片页脚按钮已注册（朗读本条回复）")
