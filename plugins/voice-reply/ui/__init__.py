# -*- coding: utf-8 -*-
"""voice-reply UI 插件：消息卡片页脚「朗读」按钮 → 播报本条 AI 回复。

交互：助手卡片页脚扬声器按钮（与内置复制/分支同排，常显）→ 点击朗读本条
消息纯文本，按钮切换为 pause 图标 → 播放中再次点击停止播放 / 打断重播，
按钮复位为扬声器。播报自然结束后按钮自动复位
（Windows 轮询 SAPI5 RunningState，macOS 接 QProcess.finished）。

按钮图标切换：宿主 MessageCard 构建页脚按钮时不暴露按钮实例
（message_card.py 用注册快照构造），故按 tooltip 锚点在卡片子树里定位
本插件按钮（首次定位后缓存 QPointer），再 setIcon 换图。

双引擎（设置 → 语音播报配置 可选）：
- 本地系统语音（默认）：Windows SAPI5（win32com）/ macOS `say`，免费零配置
- 在线 API：OpenAI 兼容 POST /audio/speech（默认预填硅基流动 CosyVoice2，
  极低价；也可指向自部署免费服务如 openai-edge-tts），wav 落临时文件，
  Windows winmm mci / macOS afplay 播放

朗读文本策略（ui/tts_text.py，纯函数便于单测）：只取正文 text 块 —— 思考过程、
工具调用与结果、自定义渲染块、图片块一律不进朗读；再清洗 markdown 标记、
URL、data URI、超长 base64 串、HTML 标签、emoji 等朗读器会读成符号或乱码的
内容；最后截断至 2000 字。
"""

from __future__ import annotations

import sys
from typing import Any, Dict

from loguru import logger

from .tts_text import build_speakable_text

PLUGIN_NAME = "voice-reply"
_ACTION_ID = f"{PLUGIN_NAME}:speak"
_TOOLTIP_IDLE = "朗读本条回复"
_TOOLTIP_PLAYING = "停止播放"
# 按钮定位锚点：宿主按注册快照设 tooltip，改图标时用它认领按钮。
# 两张卡可同时挂载按钮，播放态锚点唯一（同时只有一条在播）。
_TOOLTIPS = (_TOOLTIP_IDLE, _TOOLTIP_PLAYING)

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

# 当前处于播放态的按钮（QPointer，卡片销毁后自动置空）
_playing_button = None
# 本地播放结束轮询定时器（Windows SAPI5 无完成信号，只能轮询 RunningState）
_local_watch = None
# 轮询目标引擎（模块变量：单例 timer 只 connect 一次，闭包会绑死旧实例）
_watch_engine = None


def _icons_dir():
    from pathlib import Path

    return Path(__file__).resolve().parent / "icons"


def _icon_pair(playing: bool) -> tuple:
    """按当前主题返回 (深色图标, 浅色图标)。theme_manager 不可用回退深色。"""
    icons = _icons_dir()
    name = "pause" if playing else "speaker"
    return str(icons / f"{name}.svg"), str(icons / f"{name}_light.svg")


def _is_light_theme() -> bool:
    try:
        from app.utils.theme_manager import theme_manager

        return bool(theme_manager.is_light_theme())
    except Exception:  # noqa: BLE001 — 主题不可用回退深色图标
        return False


def _find_card_button(card):
    """在卡片子树里按 tooltip 认领本插件页脚按钮。

    宿主构建页脚按钮时不暴露实例（注册快照构造），只能按 tooltip 反查。
    返回 QToolButton 或 None（卡片无按钮 / 已销毁）。
    """
    if card is None:
        return None
    try:
        from PyQt5.QtWidgets import QToolButton

        for btn in card.findChildren(QToolButton):
            if btn.toolTip() in _TOOLTIPS:
                return btn
    except Exception as e:  # noqa: BLE001 — 卡片 C++ 侧已销毁等场景按未找到处理
        logger.debug(f"[{PLUGIN_NAME}] 定位页脚按钮失败: {e}")
    return None


def _is_playing_button(btn) -> bool:
    """判断给定按钮是否正处于播放态（pause 图标）。"""
    global _playing_button
    cur = _playing_button
    if cur is None or btn is None:
        return False
    try:
        cur = cur.data() if hasattr(cur, "data") else cur  # QPointer 解引用
    except Exception:  # noqa: BLE001 — C++ 侧已销毁
        _playing_button = None
        return False
    if cur is None:
        _playing_button = None
        return False
    try:
        return cur is btn
    except RuntimeError:  # btn 已被 C++ 销毁，is 比较也会抛
        return False


def _set_button_playing(btn, playing: bool) -> None:
    """切换按钮图标与 tooltip（播放态=pause + 停止播放）。"""
    global _playing_button
    if btn is None:
        return
    try:
        from PyQt5.QtGui import QIcon

        dark, light = _icon_pair(playing)
        path = light if (_is_light_theme() and light) else dark
        btn.setIcon(QIcon(str(path)))
        btn.setToolTip(_TOOLTIP_PLAYING if playing else _TOOLTIP_IDLE)
    except Exception as e:  # noqa: BLE001 — 换图标失败不影响播报
        logger.warning(f"[{PLUGIN_NAME}] 切换按钮图标失败: {e}")
        return
    if btn is not None and playing:
        try:
            from PyQt5.QtCore import QPointer

            btn = QPointer(btn)  # 卡片销毁后自动置空，避免野指针
        except Exception:  # noqa: BLE001 — QPointer 不可用则直接存裸引用
            pass
    _playing_button = btn if playing else None


def _reset_playing_button() -> None:
    """把播放态按钮复位为扬声器（播报自然结束 / 打断 / 失败均走这里）。"""
    global _playing_button
    btn = _playing_button
    if btn is None:
        return
    try:
        btn = btn.data() if hasattr(btn, "data") else btn  # QPointer 解引用
    except Exception:  # noqa: BLE001
        btn = None
    _playing_button = None
    if btn is not None:
        _set_button_playing(btn, False)


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


def _stop_local() -> None:
    """本地引擎打断：Windows Skip 清空播报队列，macOS 杀 say 进程。"""
    global _say_proc
    if _local_watch is not None:
        _local_watch.stop()
    if sys.platform == "darwin":
        if _say_proc is not None:
            try:
                _say_proc.kill()
            except Exception:  # noqa: BLE001 — 进程已退出
                pass
        _say_proc = None
        return
    engine = _get_sapi_voice()
    if engine is not None:
        try:
            engine.Skip("Sentence", 9999)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[{PLUGIN_NAME}] 打断本地播报失败: {e}")


def _watch_local_end(engine) -> None:
    """Windows：轮询 SAPI5 RunningState（1=done）→ 播完后复位按钮。

    engine 存模块变量而非闭包捕获：单例 timer 只 connect 一次，闭包会绑死首次
    的 engine 实例，引擎重建后轮询的是旧对象（永不到 done → 按钮卡在 pause）。
    """
    global _local_watch, _watch_engine
    try:
        from PyQt5.QtCore import QTimer

        _watch_engine = engine
        if _local_watch is None:
            _local_watch = QTimer()
            _local_watch.setInterval(300)
            _local_watch.timeout.connect(_check_local_done)
        _local_watch.start()
    except Exception as e:  # noqa: BLE001 — 定时器不可用则按钮停在 pause 态
        logger.warning(f"[{PLUGIN_NAME}] 播报结束监听不可用: {e}")


def _check_local_done() -> None:
    """轮询节拍：SAPI5 播完（RunningState=1）或 COM 异常 → 停轮询并复位按钮。"""
    engine = _watch_engine
    try:
        if engine is not None and int(engine.Status.RunningState) != 1:  # 1 = SRSEDone
            return
    except Exception:  # noqa: BLE001 — COM 异常视作播报结束
        pass
    if _local_watch is not None:
        _local_watch.stop()
    _reset_playing_button()


def _speak_local(text: str, main_widget, btn) -> None:
    """本地引擎即时播报：再次点击打断并重播，播完自动复位按钮。"""
    global _say_proc
    if sys.platform == "darwin":
        try:
            from PyQt5.QtCore import QProcess

            if _say_proc is not None:
                _say_proc.kill()
            _say_proc = QProcess()
            _say_proc.finished.connect(lambda *a: _reset_playing_button())
            _say_proc.start("say", [text])
            _set_button_playing(btn, True)
            return
        except Exception as e:  # noqa: BLE001
            _notify(main_widget, "error", "语音播报", f"本地播报失败：{e}")
            _reset_playing_button()
            return
    engine = _get_sapi_voice()
    if engine is None:
        _notify(main_widget, "error", "语音播报", "本地语音引擎不可用（SAPI5/win32com）")
        return
    try:
        engine.Skip("Sentence", 9999)  # 清空旧播报队列，实现打断重播
        engine.Speak(text, 1)  # SVSFlagsAsync = 1，立即返回不阻塞 UI
        _set_button_playing(btn, True)
        _watch_local_end(engine)
    except Exception as e:  # noqa: BLE001
        _notify(main_widget, "error", "语音播报", f"播报失败：{e}")
        _reset_playing_button()


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
    _reset_playing_button()


def _start_api(cfg: Dict[str, str], text: str, ctx: Dict[str, Any], btn) -> None:
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
        _reset_playing_button()
        _notify(mw, "error", "语音播报", msg)

    def _on_done() -> None:
        _reset_worker(worker)
        _reset_playing_button()

    worker.status.connect(_on_status)
    worker.failed.connect(_on_failed)
    worker.finished_ok.connect(_on_done)
    worker.finished.connect(lambda: _reset_worker(worker))
    _worker = worker
    _set_button_playing(btn, True)
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
    """页脚按钮回调：取本条消息正文播报；播放中再点停止。

    播放态判定：在线引擎看 worker 是否存活；本地引擎看按钮是否处于 pause 态
    （本地播完即复位，无跨请求状态）。
    """
    card = ctx.get("card")
    btn = _find_card_button(card)

    cfg = _read_config()
    if cfg.get("engine") == "api":
        if _worker is not None:
            _stop_api()
            return
    elif _is_playing_button(btn):
        _stop_local()
        _reset_playing_button()
        return

    text = build_speakable_text(card)
    if len(text) < 3:
        _notify(ctx.get("main_widget"), "warning", "语音播报", "本条消息没有可朗读的正文")
        return

    if cfg.get("engine") == "api":
        _start_api(cfg, text, ctx, btn)
        return
    _speak_local(text, ctx.get("main_widget"), btn)


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
        tooltip=_TOOLTIP_IDLE,
        on_click=_on_click,
        priority=0,
    )
    logger.info("[voice-reply] 消息卡片页脚按钮已注册（朗读本条回复）")
