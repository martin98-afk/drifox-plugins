# -*- coding: utf-8 -*-
"""voice-input UI 插件：输入框按钮 → 录音 → 离线识别 → 文本插入输入框光标处。

交互流：点按钮开始录音（右下角浮窗反馈）→ 再点结束 → 识别 → 文本插入
input_area 光标处（不自动发送）。浮窗取消 / Esc 丢弃录音。单实例状态机：
idle → recording → recognizing → idle，识别中再点只提示不叠加。

识别引擎：默认自动选择 —— 优先本地 Whisper（faster-whisper，准确率高），
依赖缺失或失败时自动回退 Windows SAPI5（recognizer.py），插件永不失效。
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

# 状态机
_state = "idle"  # idle | recording | recognizing
_recorder = None  # VoiceRecorder
_overlay = None  # RecordingOverlay
_worker = None  # RecognizeWorker
_wav_path = ""
_token_id = ""
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
    """开始录音：检测中文引擎 → winmm 录音 → 弹浮窗 + 超时看门狗。"""
    global _state, _recorder, _overlay, _wav_path, _token_id, _max_timer
    main_widget = context.get("main_widget")
    try:
        from .recognizer import find_zh_recognizer_id
        from .recorder import VoiceRecorder
        from .overlay import RecordingOverlay
    except Exception as e:  # noqa: BLE001 — 子模块加载失败（热重载竞态等）
        logger.error(f"[voice-input] 模块加载失败: {e}")
        return

    try:
        token_id = find_zh_recognizer_id()
        if not token_id:
            logger.error("[voice-input] 未找到中文语音识别引擎")
            _notify(
                main_widget,
                "error",
                "语音听写",
                "系统未安装中文语音识别引擎（zh-CN），无法使用",
            )
            return
        _token_id = token_id

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
        from PyQt5.QtCore import QTimer

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
            except Exception:  # noqa: BLE001
                pass
        _close_overlay()
        _reset_state()
        _notify(main_widget, "error", "语音听写", f"录音启动失败：{e}")


def _stop_and_recognize(context: Dict[str, Any]) -> None:
    """停止录音 → 保存 WAV → 按引擎可用性启动识别，浮窗转识别态。"""
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

    if _overlay is not None:
        _overlay.enter_recognizing()
    _state = "recognizing"

    try:
        from .whisper_recognizer import (
            WhisperRecognizeWorker,
            faster_whisper_available,
            is_model_present,
            model_hint_mb,
        )
    except Exception as e:  # noqa: BLE001 — Whisper 模块自身异常则走 SAPI5
        logger.warning(f"[voice-input] Whisper 模块加载失败，回退 SAPI5: {e}")
        _start_sapi5_worker(context)
        return

    if not faster_whisper_available():
        _start_sapi5_worker(context)
        return

    # Whisper 可用：首次识别前提示将自动下载模型
    if not is_model_present():
        _notify(
            main_widget,
            "info",
            "语音听写",
            f"首次使用高精度识别：需先下载语音模型（约 {model_hint_mb()}MB），"
            "仅此一次，下载完成后自动识别",
        )

    worker = WhisperRecognizeWorker(_wav_path)
    worker.finished_ok.connect(lambda text: _on_recognized(context, text))
    worker.failed.connect(lambda err: _on_failed(context, err))
    worker.unavailable.connect(lambda msg: _on_whisper_unavailable(context, msg))
    worker.status.connect(_on_whisper_status)
    worker.start()
    _set_worker(worker)


def _start_sapi5_worker(context: Dict[str, Any]) -> None:
    """用 SAPI5 识别当前 _wav_path（默认路径 / Whisper 回退路径）。"""
    main_widget = context.get("main_widget")
    try:
        from .recognizer import RecognizeWorker

        if not _token_id:
            _notify(main_widget, "error", "语音听写", "系统中文识别引擎不可用")
            _close_overlay()
            _reset_state()
            return
        worker = RecognizeWorker(_wav_path, _token_id)
        worker.finished_ok.connect(lambda text: _on_recognized(context, text))
        worker.failed.connect(lambda err: _on_failed(context, err))
        worker.start()
        _set_worker(worker)
    except Exception as e:  # noqa: BLE001 — 兜底：回滚整个会话
        logger.error(f"[voice-input] SAPI5 识别启动失败: {e}")
        _close_overlay()
        _reset_state()
        _notify(main_widget, "error", "语音听写", f"识别启动失败：{e}")


def _set_worker(worker) -> None:
    global _worker
    _worker = worker


def _on_whisper_unavailable(context: Dict[str, Any], msg: str) -> None:
    """Whisper 依赖/模型缺失 → 自动回退 SAPI5，会话不中断。"""
    main_widget = context.get("main_widget")
    logger.warning(f"[voice-input] Whisper 不可用，回退 SAPI5: {msg}")
    _notify(main_widget, "warning", "语音听写", msg)
    _start_sapi5_worker(context)


def _on_whisper_status(text: str) -> None:
    """Whisper worker 阶段文案 → 浮窗状态标签（下载模型/识别中…）。"""
    if _overlay is not None:
        _overlay.set_status(text)


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


def _on_failed(context: Dict[str, Any], err: str) -> None:
    main_widget = context.get("main_widget")
    _close_overlay()
    _reset_state()
    _notify(main_widget, "error", "语音听写", f"识别失败：{err}")


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
