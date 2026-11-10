# -*- coding: utf-8 -*-
"""Windows 分片录音器：winmm (mciSendStringW) 一次录一片。

每次 start_chunk() 打开 waveaudio 设备录到内存，stop_chunk() 落盘并关闭。
设备重开总开销实测约 30~80ms（open+record ~50ms，save+close ~20ms），
按 20 秒一片计算丢失率 <0.5%，会议场景可忽略。

采样固定 16kHz/16bit/单声道：云端 ASR 的标准输入，也是体积与准确度的平衡点
（32KB/s，25 分钟 ≈ 48MB，正好卡在硅基流动单次 50MB 上限内）。
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path
from typing import Optional

from loguru import logger

_MCI_OK = 0

# 全拼 samplespersec：缩写 samppersec 在部分驱动上直接 259 拒绝
_MCI_FORMAT_ARGS = (
    "time format ms bitspersample 16 channels 1 samplespersec 16000 "
    "bytespersec 32000 alignment 2"
)

_mci_send = ctypes.windll.winmm.mciSendStringW
_mci_send.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_uint, wintypes.HANDLE]
_mci_send.restype = ctypes.c_uint

_mci_error = ctypes.windll.winmm.mciGetErrorStringW
_mci_error.argtypes = [ctypes.c_uint, wintypes.LPWSTR, ctypes.c_uint]
_mci_error.restype = wintypes.BOOL


def _error_text(code: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    if _mci_error(code, buf, 256):
        return buf.value
    return f"MCI 错误码 {code}"


def _mci(command: str) -> None:
    code = _mci_send(command, None, 0, 0)
    if code != _MCI_OK:
        raise RuntimeError(f"MCI 命令失败: {command.split()[0]}… → {_error_text(code)}")


class WinChunkRecorder:
    """单实例。同一时刻只有一片在录，由上层控制切片节奏。"""

    ALIAS = "drifox_meeting"

    def __init__(self) -> None:
        self._open = False
        self._recording = False
        self._current_path: Optional[Path] = None

    def start_chunk(self, out_path: Path) -> None:
        self._current_path = Path(out_path)
        _mci(f"open new type waveaudio alias {self.ALIAS}")
        self._open = True
        try:
            code = _mci_send(f"set {self.ALIAS} {_MCI_FORMAT_ARGS}", None, 0, 0)
            if code != _MCI_OK:
                # 格式设置失败不等于不能录：降级默认格式继续，事后比对数
                # 发现参数不一致的片会被 WavJoiner 丢弃，日志里能查到原因
                logger.warning(f"[meeting-notes] 采样格式设置失败（降级默认格式）: {_error_text(code)}")
            _mci(f"record {self.ALIAS}")
            self._recording = True
        except Exception:
            self.close()
            raise

    def stop_chunk(self) -> Optional[Path]:
        out_path = self._current_path
        if not self._open or out_path is None:
            return None
        try:
            if self._recording:
                _mci(f"stop {self.ALIAS}")
                self._recording = False
            _mci(f'save {self.ALIAS} "{out_path}"')
        except Exception as e:  # noqa: BLE001 — 单片失败不影响后续片
            logger.error(f"[meeting-notes] 停止录音片失败: {e}")
            return None
        finally:
            self.close()
        return out_path if out_path.exists() else None

    def close(self) -> None:
        if not self._open:
            return
        self._open = False
        self._recording = False
        code = _mci_send(f"close {self.ALIAS}", None, 0, 0)
        if code != _MCI_OK:
            logger.warning(f"[meeting-notes] 关闭录音设备失败（忽略）: {_error_text(code)}")
