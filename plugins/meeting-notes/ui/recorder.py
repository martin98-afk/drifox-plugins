# -*- coding: utf-8 -*-
"""分片录音器门面：按平台分派，接口统一。

    rec = make_recorder()
    rec.start_chunk(path)      # 开始录一片到 path
    p = rec.stop_chunk()       # 收尾，返回实际文件（失败 None）
    rec.close()                # 异常路径兜底释放设备

平台差异被隔离在 recorder_win / recorder_mac 里：Windows 是 MCI（模块顶层
绑定 ctypes.windll，只能按平台延迟导入），macOS 是 AVFoundation，
Linux 是 arecord（alsa-utils）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from loguru import logger


def is_supported() -> bool:
    return sys.platform in ("win32", "darwin", "linux")


def make_recorder():
    """按平台造录音器。不支持的平台抛 RuntimeError。"""
    if sys.platform == "darwin":
        from .recorder_mac import MacChunkRecorder

        return MacChunkRecorder()
    if sys.platform == "win32":
        from .recorder_win import WinChunkRecorder

        return WinChunkRecorder()
    if sys.platform.startswith("linux"):
        from .recorder_linux import LinuxChunkRecorder

        return LinuxChunkRecorder()
    raise RuntimeError(f"当前平台（{sys.platform}）不支持录音")


def mac_permission_hint() -> str:
    """macOS 首次使用时给一句「马上会弹授权框」的提示；其他平台返回空串。"""
    if sys.platform != "darwin":
        return ""
    try:
        from .recorder_mac import PERM_NOT_DETERMINED, permission_status

        if permission_status() == PERM_NOT_DETERMINED:
            return "首次使用需授权麦克风：系统弹窗请点「允许」，并再录一次"
    except Exception as e:  # noqa: BLE001 — 权限探测失败不影响录音主流程
        logger.debug(f"[meeting-notes] 权限探测失败: {e}")
    return ""


def chunk_path(tmp_dir: Path, index: int) -> Path:
    return Path(tmp_dir) / f"chunk_{index:04d}.wav"


def safe_remove(path: Optional[Path]) -> None:
    if not path:
        return
    try:
        if Path(path).exists():
            Path(path).unlink()
    except OSError:
        pass
