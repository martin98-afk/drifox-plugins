# -*- coding: utf-8 -*-
"""winmm (mciSendStringW) 录音器：ctypes 标准库调用，零第三方依赖。

录制 16kHz / 16bit / 单声道 PCM WAV。生命周期：
start() 开始录音 → stop_and_save(path) 收尾保存 → close() 释放设备。
异常路径必须 close()，否则 waveaudio 设备被占用，后续录音全挂。
"""

from __future__ import annotations

import array
import ctypes
import os
import wave
from ctypes import wintypes

from loguru import logger

_MCI_OK = 0

# winmm 录音参数：16kHz 16bit 单声道（SAPI5 识别推荐采样率）。
# 采样率关键词必须是全拼 samplespersec：samppersec 缩写在本机驱动直接 259 拒绝
_MCI_FORMAT_ARGS = "time format ms bitspersample 16 channels 1 samplespersec 16000 bytespersec 32000 alignment 2"

_mci_send = ctypes.windll.winmm.mciSendStringW
_mci_send.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_uint, wintypes.HANDLE]
_mci_send.restype = ctypes.c_uint

_mci_error = ctypes.windll.winmm.mciGetErrorStringW
_mci_error.argtypes = [ctypes.c_uint, wintypes.LPWSTR, ctypes.c_uint]
_mci_error.restype = wintypes.BOOL


def _mci_error_text(code: int) -> str:
    """MCI 错误码 → 人话描述（失败返回码本身）。"""
    buf = ctypes.create_unicode_buffer(256)
    if _mci_error(code, buf, 256):
        return buf.value
    return f"MCI 错误码 {code}"


def _mci(command: str) -> None:
    """执行一条 MCI 命令，非零返回码抛 RuntimeError（带描述）。"""
    code = _mci_send(command, None, 0, 0)
    if code != _MCI_OK:
        raise RuntimeError(
            f"MCI 命令失败: {command.split()[0]}… → {_mci_error_text(code)}"
        )


def _wav_duration(path: str) -> float:
    """读 WAV 头算实际时长（秒）。读取失败返回 -1，不阻断保存流程。"""
    try:
        with wave.open(path, "rb") as w:
            rate = w.getframerate() or 1
            return w.getnframes() / float(rate)
    except Exception:  # noqa: BLE001 — 诊断日志失败不影响主流程
        return -1.0


def _wav_level(path: str) -> tuple[float, float]:
    """返回 (rms, peak)，16bit PCM 归一化 0~1。读取失败/非 16bit 返回 (-1, -1)。

    判读：peak<0.01≈数字静音（录到没声音）；peak>0.1 正常说话音量。
    """
    try:
        with wave.open(path, "rb") as w:
            if w.getsampwidth() != 2:
                return -1.0, -1.0
            frames = w.readframes(w.getnframes())
    except Exception:  # noqa: BLE001 — 诊断日志失败不影响主流程
        return -1.0, -1.0
    samples = array.array("h")  # WAV 小端，x86/ARM Windows 平台序一致
    samples.frombytes(frames)
    if not samples:
        return 0.0, 0.0
    peak = max(abs(s) for s in samples) / 32768.0
    rms = (sum(s * s for s in samples) / len(samples)) ** 0.5 / 32768.0
    return rms, peak


class VoiceRecorder:
    """单实例录音器。同一时刻只允许一个会话（由上层状态机保证）。"""

    def __init__(self, alias: str = "drifox_voice_input") -> None:
        self._alias = alias
        self._opened = False
        self._recording = False

    def start(self) -> None:
        """打开 waveaudio 设备并开始录音。格式设置失败降级默认格式继续录。"""
        _mci(f"open new type waveaudio alias {self._alias}")
        self._opened = True
        try:
            code = _mci_send(f"set {self._alias} {_MCI_FORMAT_ARGS}", None, 0, 0)
            if code != _MCI_OK:
                logger.warning(
                    f"[voice-input] 采样格式设置失败（降级默认格式）: {_mci_error_text(code)}"
                )
            _mci(f"record {self._alias}")
            self._recording = True
            logger.info("[voice-input] 录音开始（16kHz/16bit/mono）")
        except Exception:
            self.close()
            raise

    def stop_and_save(self, wav_path: str) -> None:
        """停止录音并保存到 wav_path（路径含空格自动加引号）。"""
        if not self._opened:
            raise RuntimeError("录音器未打开")
        if self._recording:
            _mci(f"stop {self._alias}")
            self._recording = False
        _mci(f'save {self._alias} "{wav_path}"')
        dur = _wav_duration(wav_path)
        size = os.path.getsize(wav_path) if os.path.exists(wav_path) else -1
        rms, peak = _wav_level(wav_path)
        if dur >= 0:
            logger.info(
                f"[voice-input] 录音已保存: {wav_path}（{dur:.1f} 秒, {size} 字节, "
                f"电平 rms={rms:.4f}/peak={peak:.4f}）"
            )
        else:
            logger.info(f"[voice-input] 录音已保存: {wav_path}（时长读取失败）")
        self.close()

    def close(self) -> None:
        """释放设备。重复调用安全；设备已坏静默吞掉（C 侧状态不可恢复）。"""
        if not self._opened:
            return
        self._opened = False
        self._recording = False
        code = _mci_send(f"close {self._alias}", None, 0, 0)
        if code != _MCI_OK:
            logger.warning(
                f"[voice-input] 关闭录音设备失败（忽略）: {_mci_error_text(code)}"
            )
