# -*- coding: utf-8 -*-
"""Linux 分片录音器：调用系统 arecord（alsa-utils）录一片、收一片。

为什么用外部命令而不是 ctypes 调 ALSA：libasound 的设备/参数协商用 ctypes
写起来远比 winmm/AVFoundation 长，且各发行版 PCM 设备名差异大；arecord 是
alsa-utils 标配，参数稳定。

依赖：系统需装 alsa-utils（Debian/Ubuntu: alsa-utils，Fedora: alsa-utils，
Arch: alsa-utils）。缺了就在 start_chunk 里明确报错，不静默失败。

⚠ 未在 Linux 实机验证（开发机是 Windows）。接口与 Windows/macOS 版一致：
start_chunk(path) → stop_chunk() → close()。
"""

from __future__ import annotations

import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Optional

from loguru import logger

_ARECORD = "arecord"


class LinuxChunkRecorder:
    """单实例分片录音。每片一个 arecord 进程，SIGINT 收尾（会写完整 WAV 头）。"""

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._current: Optional[Path] = None

    @staticmethod
    def available() -> bool:
        return shutil.which(_ARECORD) is not None

    def start_chunk(self, out_path: Path) -> None:
        if not self.available():
            raise RuntimeError(
                "Linux 录音需要 alsa-utils 的 arecord，请先安装（如 sudo apt install alsa-utils）"
            )
        self._current = Path(out_path)
        self._proc = subprocess.Popen(
            [
                _ARECORD,
                "-q",
                "-f",
                "S16_LE",
                "-r",
                "16000",
                "-c",
                "1",
                "-t",
                "wav",
                str(out_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        # 给设备打开留一点时间：立刻 poll 才能抓到「设备被占用」这类立即失败
        time.sleep(0.2)
        if self._proc.poll() is not None:
            detail = ""
            try:
                detail = (self._proc.stderr.read() or b"").decode("utf-8", "ignore")[:200]
            except Exception:  # noqa: BLE001 — 读不到 stderr 不影响主错误
                pass
            self._proc = None
            raise RuntimeError(f"arecord 启动失败：{detail.strip() or '未知错误'}")

    def stop_chunk(self, out_path: Optional[Path] = None) -> Optional[Path]:
        path = out_path or self._current
        proc, self._proc = self._proc, None
        self._current = None
        if proc is None:
            return None
        try:
            proc.send_signal(signal.SIGINT)  # arecord 收到 SIGINT 会正常补 WAV 头
            proc.wait(timeout=5)
        except Exception as e:  # noqa: BLE001 — 收尾失败也要把进程清掉
            logger.warning(f"[meeting-notes] arecord 收尾失败: {e}")
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass
        if path and Path(path).exists() and Path(path).stat().st_size > 44:
            return Path(path)
        return None

    def close(self) -> None:
        self.stop_chunk()
