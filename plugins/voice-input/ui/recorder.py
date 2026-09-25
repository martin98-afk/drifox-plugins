# -*- coding: utf-8 -*-
"""winmm (mciSendStringW) 录音器：ctypes 标准库调用，零第三方依赖。

录制 16kHz / 16bit / 单声道 PCM WAV。生命周期：
start() 开始录音 → stop_and_save(path) 收尾保存 → close() 释放设备。
异常路径必须 close()，否则 waveaudio 设备被占用，后续录音全挂。

打包约束：宿主为 PyInstaller 打包，标准库 wave / array 未被主程序静态引用、
PyInstaller 不收集，import 必 ModuleNotFoundError。故 WAV 头解析与电平统计
一律手解字节（见 _parse_wav_header / _wav_level），不引入任何新 import。
"""

from __future__ import annotations

import ctypes
import os
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

# 标准 RIFF WAVE 头（44 字节）关键字段偏移
_RIFF_MAGIC = b"RIFF"
_WAVE_MAGIC = b"WAVE"
_FMT_MAGIC = b"fmt "
_DATA_MAGIC = b"data"
_HEADER_MIN = 12
_FMT_MIN = 16


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


def _parse_wav_header(raw: bytes) -> tuple[int, int, int, int]:
    """解析 WAV 头 → (采样率, 声道数, 位深, 数据区偏移)。

    非标准布局（缺 fmt/data 块、头过短）返回全 0，调用方降级处理。
    """
    if (
        len(raw) < _HEADER_MIN
        or raw[0:4] != _RIFF_MAGIC
        or raw[8:12] != _WAVE_MAGIC
    ):
        return 0, 0, 0, 0

    rate = channels = bits = 0
    pos = _HEADER_MIN
    end = len(raw)
    while pos + 8 <= end:
        chunk_id = raw[pos : pos + 4]
        size = int.from_bytes(raw[pos + 4 : pos + 8], "little", signed=False)
        body = pos + 8
        if body + size > end:  # 声明长度越界，截断到实际
            size = end - body
        if chunk_id == _FMT_MAGIC and size >= _FMT_MIN:
            channels = int.from_bytes(raw[body + 2 : body + 4], "little")
            rate = int.from_bytes(raw[body + 4 : body + 8], "little")
            bits = int.from_bytes(raw[body + 14 : body + 16], "little")
        elif chunk_id == _DATA_MAGIC:
            return rate, channels, bits, body
        # 块长度为奇数时按 RIFF 规范补一个填充字节
        pos = body + size + (size & 1)
    return rate, channels, bits, 0


def _wav_duration(path: str) -> float:
    """读 WAV 头算实际时长（秒）。读取失败或头不合法返回 -1，不阻断保存流程。"""
    try:
        with open(path, "rb") as f:
            raw = f.read(64)
        rate, channels, bits, data_off = _parse_wav_header(raw)
        if rate <= 0 or channels <= 0 or bits <= 0 or data_off <= 0:
            return -1.0
        data_size = os.path.getsize(path) - data_off
        if data_size <= 0:
            return -1.0
        return data_size / float(rate * channels * (bits // 8))
    except Exception:  # noqa: BLE001 — 诊断日志失败不影响主流程
        return -1.0


def _wav_level(path: str) -> tuple[float, float]:
    """返回 (rms, peak)，16bit PCM 归一化 0~1。读取失败/非 16bit 返回 (-1, -1)。

    判读：peak<0.01≈数字静音（录到没声音）；peak>0.1 正常说话音量。
    60 秒音频约 96 万采样，纯 Python 循环约 0.3 秒，仅在停止录音时跑一次。
    """
    try:
        with open(path, "rb") as f:
            raw = f.read(64)
            rate, channels, bits, data_off = _parse_wav_header(raw)
            if bits != 16 or data_off <= 0:
                return -1.0, -1.0
            f.seek(data_off)
            frames = f.read()
    except Exception:  # noqa: BLE001 — 诊断日志失败不影响主流程
        return -1.0, -1.0

    n = len(frames) - (len(frames) % 2)
    if n <= 0:
        return 0.0, 0.0
    # 隔 3 采样抽稀：电平统计无需全量，精度足够判静音
    step = 6
    count = 0
    sum_sq = 0
    peak = 0
    for i in range(0, n, step):
        s = int.from_bytes(frames[i : i + 2], "little", signed=True)
        abs_s = -s if s < 0 else s
        if abs_s > peak:
            peak = abs_s
        sum_sq += s * s
        count += 1
    if not count:
        return 0.0, 0.0
    return (sum_sq / count) ** 0.5 / 32768.0, peak / 32768.0


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
