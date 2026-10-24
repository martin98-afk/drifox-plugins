# -*- coding: utf-8 -*-
"""WAV 头解析与电平统计：Windows / macOS 录音器共用。

打包约束：宿主为 PyInstaller 打包，标准库 wave / array 未被主程序静态引用、
PyInstaller 分析不到就不收集，插件 import 会 ModuleNotFoundError。
故 WAV 头解析与电平统计一律手解字节，不引入任何新 import。
"""

from __future__ import annotations

import os

# 头读取字节数：AVAudioRecorder 会在 fmt 前插入 JUNK/FLLR 填充块，
# 实测 data 块偏移可达 4096 字节，读 64 字节找不到；8KB 留足余量
_HEADER_READ = 8192

# 标准 RIFF WAVE 头（44 字节）关键字段偏移
_RIFF_MAGIC = b"RIFF"
_WAVE_MAGIC = b"WAVE"
_FMT_MAGIC = b"fmt "
_DATA_MAGIC = b"data"
_HEADER_MIN = 12
_FMT_MIN = 16


def parse_wav_header(raw: bytes) -> tuple[int, int, int, int]:
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
        if body >= end:  # 数据不足一个块头，收尾
            break
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


def wav_duration(path: str) -> float:
    """读 WAV 头算实际时长（秒）。读取失败或头不合法返回 -1，不阻断保存流程。"""
    try:
        with open(path, "rb") as f:
            raw = f.read(_HEADER_READ)
        rate, channels, bits, data_off = parse_wav_header(raw)
        if rate <= 0 or channels <= 0 or bits <= 0 or data_off <= 0:
            return -1.0
        data_size = os.path.getsize(path) - data_off
        if data_size <= 0:
            return -1.0
        return data_size / float(rate * channels * (bits // 8))
    except Exception:  # noqa: BLE001 — 诊断日志失败不影响主流程
        return -1.0


def wav_level(path: str) -> tuple[float, float]:
    """返回 (rms, peak)，16bit PCM 归一化 0~1。读取失败/非 16bit 返回 (-1, -1)。

    判读：peak<0.01≈数字静音（录到没声音）；peak>0.1 正常说话音量。
    60 秒音频约 96 万采样，纯 Python 循环约 0.3 秒，仅在停止录音时跑一次。
    """
    try:
        with open(path, "rb") as f:
            raw = f.read(_HEADER_READ)
            rate, channels, bits, data_off = parse_wav_header(raw)
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


def log_saved(wav_path: str, tag: str) -> None:
    """录音保存后统一打日志（时长 + 字节数 + 电平），供两平台录音器复用。"""
    from loguru import logger

    dur = wav_duration(wav_path)
    size = os.path.getsize(wav_path) if os.path.exists(wav_path) else -1
    rms, peak = wav_level(wav_path)
    if dur >= 0:
        logger.info(
            f"[voice-input] 录音已保存({tag}): {wav_path}（{dur:.1f} 秒, {size} 字节, "
            f"电平 rms={rms:.4f}/peak={peak:.4f}）"
        )
    else:
        logger.info(f"[voice-input] 录音已保存({tag}): {wav_path}（时长读取失败）")
