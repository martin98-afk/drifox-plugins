# -*- coding: utf-8 -*-
"""voice-input UI 插件：输入框按钮 → 录音 → 云端识别 → 文本插入输入框光标处。

交互流：点按钮开始录音（右下角浮窗反馈）→ 再点结束 → 识别 → 文本插入
input_area 光标处（不自动发送）。浮窗取消 / Esc 丢弃录音。单实例状态机：
idle → recording → recognizing → idle，识别中再点只提示不叠加。

识别引擎（设置 → 语音听写配置 可选）：纯云端双链 ——
- 硅基流动（默认优先）：免费 ASR 模型（Qwen3-ASR 等），国内直连
- MiniMax：asr-1.0，按量计费
自动模式下硅基流动失败（限流/超时/key 无效）自动转 MiniMax，两个都配才互为备用；
仅选单引擎时失败即报错。云端全部失败不落本地识别。
"""

from __future__ import annotations

import os
import sys
import tempfile
from typing import Any, Dict

from loguru import logger

PLUGIN_NAME = "voice-input"
_BUTTON_ID = "voice-input"
_TOOLTIP = "语音听写（点击开始，再点结束，文字插入输入框）"

# 单次录音上限（秒），超时自动结束并识别
_MAX_RECORD_SEC = 60

# 云端引擎端点（协议同构：multipart 上传 + Bearer + {"text": ...}）
_SILICONFLOW_URL = "https://api.siliconflow.cn/v1/audio/transcriptions"
_MINIMAX_URL = "https://api.minimaxi.com/v1/speech_to_text"
_MINIMAX_MODEL = "asr-1.0"
_SILICONFLOW_DEFAULT_MODEL = "Qwen/Qwen3-ASR-1.7B"

# 状态机
_state = "idle"  # idle | recording | recognizing
_recorder = None  # VoiceRecorder
_overlay = None  # RecordingOverlay
_worker = None  # CloudRecognizeWorker
_wav_path = ""
_max_timer = None  # QTimer，60 秒自动停


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
        logger.warning(f"[voice-input] InfoBar 提示失败: {e}")


def _cleanup_wav() -> None:
    """删除临时 WAV（失败忽略：%TEMP% 文件系统会兜底清理）。"""
    global _wav_path
    if _wav_path and os.path.exists(_wav_path):
        try:
            os.remove(_wav_path)
        except OSError as e:
            logger.warning(f"[voice-input] 临时 WAV 删除失败（忽略）: {e}")
    _wav_path = ""


def _read_config() -> Dict[str, str]:
    """读插件配置。主程序未注入配置系统/读取失败时返回空 dict（调用方拦截并提示）。"""
    try:
        from app.plugins.managers.plugin_config_store import PluginConfigStore

        store = PluginConfigStore()
        return {
            "provider": str(store.get(PLUGIN_NAME, "provider") or "auto"),
            "sf_key": str(store.get(PLUGIN_NAME, "siliconflow_api_key") or "").strip(),
            "sf_model": str(store.get(PLUGIN_NAME, "siliconflow_model") or "").strip()
            or _SILICONFLOW_DEFAULT_MODEL,
            "mm_key": str(store.get(PLUGIN_NAME, "minimax_api_key") or "").strip(),
        }
    except Exception as e:  # noqa: BLE001 — 配置不可用不崩，交给调用方提示
        logger.warning(f"[voice-input] 读取插件配置失败: {e}")
        return {}


def _build_chain(cfg: Dict[str, str]) -> list:
    """按引擎选择生成识别链 [(url, model, key, 名称), ...]，头部优先。

    - auto：硅基流动优先，MiniMax（配了 key）作备用；
    - siliconflow / minimax：仅用对应单引擎。
    """
    p = cfg.get("provider", "auto")
    chain: list = []
    if p in ("auto", "siliconflow") and cfg.get("sf_key"):
        chain.append((_SILICONFLOW_URL, cfg["sf_model"], cfg["sf_key"], "硅基流动"))
    if p in ("auto", "minimax") and cfg.get("mm_key"):
        chain.append((_MINIMAX_URL, _MINIMAX_MODEL, cfg["mm_key"], "MiniMax"))
    return chain


def _reset_state() -> None:
    """回 idle：清引用、停定时器、删临时文件。"""
    global _state, _recorder, _overlay, _worker, _max_timer
    _state = "idle"
    _recorder = None
    _overlay = None
    _worker = None
    if _max_timer is not None:
        _max_timer.stop()
        _max_timer = None
    _cleanup_wav()


def _close_overlay() -> None:
    global _overlay
    if _overlay is not None:
        try:
            _overlay.close()
        except RuntimeError:
            pass  # C++ 对象已被 Qt 销毁
        _overlay = None


def _insert_text(main_widget, text: str) -> bool:
    """文本插入输入框光标处。输入框控件缺失（异构窗口）返回 False。"""
    area = getattr(main_widget, "input_area", None)
    if area is None:
        logger.warning("[voice-input] main_widget 无 input_area，无法插入")
        return False
    cursor = area.textCursor()
    cursor.insertText(text)
    area.setTextCursor(cursor)
    area.setFocus()
    return True


def _on_button_clicked(context: Dict[str, Any]) -> None:
    """按钮点击：按状态机分派 开始 / 结束识别 / 提示等待。"""
    main_widget = context.get("main_widget")
    if _state == "idle":
        _start_recording(context)
    elif _state == "recording":
        _stop_and_recognize(context)
    else:
        _notify(main_widget, "info", "语音听写", "正在识别中，请稍候")


def _start_recording(context: Dict[str, Any]) -> None:
    """开始录音：读配置判可用性 → winmm 录音 → 弹浮窗 + 超时看门狗。"""
    global _state, _recorder, _overlay, _wav_path, _max_timer
    main_widget = context.get("main_widget")
    try:
        from .recorder import VoiceRecorder
        from .overlay import RecordingOverlay
    except Exception as e:  # noqa: BLE001 — 子模块加载失败（热重载竞态等）
        logger.error(f"[voice-input] 模块加载失败: {e}")
        return

    try:
        chain = _build_chain(_read_config())
        if not chain:
            logger.warning("[voice-input] 未配置任何云端识别 Key，无法使用")
            _notify(
                main_widget,
                "error",
                "语音听写",
                "请先到 设置 → 语音听写配置 填写云端识别 API Key",
            )
            return

        fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="drifox_voice_")
        os.close(fd)
        _wav_path = wav_path

        recorder = VoiceRecorder()
        recorder.start()
        _recorder = recorder

        overlay = RecordingOverlay()
        overlay.stop_requested.connect(lambda: _stop_and_recognize(context))
        overlay.cancelled.connect(_on_cancelled)
        overlay.start_recording()
        _overlay = overlay

        # 60 秒看门狗：到点自动结束并识别
        from PySide6.QtCore import QTimer

        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: _stop_and_recognize(context))
        timer.start(_MAX_RECORD_SEC * 1000)
        _max_timer = timer

        _state = "recording"
        logger.info("[voice-input] 语音听写开始")
    except Exception as e:  # noqa: BLE001 — 启动失败必须完整回滚，不留设备占用/浮窗残留
        logger.error(f"[voice-input] 启动录音失败: {e}")
        if _recorder is not None:
            try:
                _recorder.close()
            except Exception:  # noqa: BLE001 — 设备已坏也要走完清理
                pass
        _close_overlay()
        _reset_state()
        _notify(main_widget, "error", "语音听写", f"录音启动失败：{e}")


def _stop_and_recognize(context: Dict[str, Any]) -> None:
    """停止录音 → 保存 WAV → 按识别链启动云端识别，浮窗转识别态。"""
    global _state
    if _state != "recording":
        return
    main_widget = context.get("main_widget")
    try:
        assert _recorder is not None
        _recorder.stop_and_save(_wav_path)
    except Exception as e:  # noqa: BLE001 — 停止失败回滚整个会话
        logger.error(f"[voice-input] 结束录音失败: {e}")
        _close_overlay()
        _reset_state()
        _notify(main_widget, "error", "语音听写", f"识别启动失败：{e}")
        return

    chain = _build_chain(_read_config())
    if not chain:
        _close_overlay()
        _reset_state()
        _notify(main_widget, "error", "语音听写", "未配置云端识别 API Key")
        return

    if _overlay is not None:
        _overlay.enter_recognizing()
    _state = "recognizing"
    _start_cloud(context, chain)


def _start_cloud(context: Dict[str, Any], chain: list) -> None:
    """启动识别链头部引擎；失败时 _on_cloud_failed 自动转后续引擎。"""
    main_widget = context.get("main_widget")
    url, model, key, name = chain[0]
    try:
        from .cloud_recognizer import CloudRecognizeWorker

        worker = CloudRecognizeWorker(_wav_path, url, model, key)
        worker.finished_ok.connect(lambda text: _on_recognized(context, text))
        worker.failed.connect(
            lambda err, rest=chain[1:], n=name: _on_cloud_failed(context, err, rest, n)
        )
        worker.status.connect(_on_worker_status)
        worker.start()
        _set_worker(worker)
    except Exception as e:  # noqa: BLE001 — 启动失败回滚整个会话
        logger.error(f"[voice-input] 云端识别启动失败: {e}")
        _close_overlay()
        _reset_state()
        _notify(main_widget, "error", "语音听写", f"识别启动失败：{e}")


def _on_cloud_failed(context: Dict[str, Any], err: str, rest: list, tried: str) -> None:
    """链内引擎失败：有备用自动转（本次录音不丢），否则报错收场。"""
    main_widget = context.get("main_widget")
    logger.warning(f"[voice-input] {tried} 识别失败: {err}")
    if rest:
        fallback_name = rest[0][3]
        _notify(main_widget, "warning", "语音听写", f"{tried}识别失败，转用{fallback_name}")
        _start_cloud(context, rest)
        return
    _close_overlay()
    _reset_state()
    _notify(main_widget, "error", "语音听写", f"云端识别失败：{err}")


def _set_worker(worker) -> None:
    global _worker
    _worker = worker


def _on_worker_status(text: str) -> None:
    """识别 worker 阶段文案 → 浮窗状态标签。"""
    if _overlay is not None:
        _overlay.set_status(text)


def _on_cancelled() -> None:
    """浮窗取消 / Esc：丢弃录音，不留临时文件。"""
    global _recorder
    if _recorder is not None:
        try:
            _recorder.close()
        except Exception:  # noqa: BLE001 — 设备已坏也要走完清理
            pass
        _recorder = None
    _close_overlay()
    _reset_state()
    logger.info("[voice-input] 语音听写已取消")


def _on_recognized(context: Dict[str, Any], text: str) -> None:
    """识别成功：插入 input_area 光标处，InfoBar 反馈。"""
    main_widget = context.get("main_widget")
    _close_overlay()
    _reset_state()
    if not text:
        _notify(
            main_widget, "warning", "语音听写", "未识别到语音内容，请靠近麦克风重试"
        )
        return
    if _insert_text(main_widget, text):
        preview = text if len(text) <= 24 else text[:24] + "…"
        _notify(main_widget, "success", "语音听写", f"已插入：{preview}")
    else:
        _notify(main_widget, "error", "语音听写", "当前窗口不支持插入文本")


def register_ui(registry) -> None:
    """注册输入框按钮。热重载时主程序重新调用本函数。"""
    # 热重载兼容：清理旧子模块缓存（避免 Python 用旧 sys.modules 引用）
    prefix = "ui_plugin_voice_input."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    icons = _icons_dir()
    registry.register_input_button(
        PLUGIN_NAME,
        _BUTTON_ID,
        icon_path=str(icons / "mic.svg"),
        icon_light_path=str(icons / "mic_light.svg"),
        tooltip=_TOOLTIP,
        on_click=_on_button_clicked,
        # 锚定截图按钮右侧；未装 quick-screenshot 时自动降级工具栏末尾
        position="after:quick-screenshot",
    )
    logger.info("[voice-input] 输入框按钮已注册（麦克风听写）")
