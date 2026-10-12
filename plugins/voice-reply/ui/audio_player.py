# -*- coding: utf-8 -*-
"""voice-reply 音频播放：Windows winmm mciSendStringW（主）/ macOS afplay。

为什么不用 winsound.PlaySound（2026-10-12 实测踩坑）：
PlaySound 播放失败时**不抛异常、静默无声**，且对 WAV 兼容面极窄（只吃标准
PCM，服务端返回的 wav 常带额外 chunk 或非 44.1k 采样率即失败）。表现为
「提示播放中但听不到」且日志干净，无法诊断。改用 winmm mciSendStringW：
命令返回码非 0 即失败，可 mciGetErrorStringW 转人话；支持显式 stop/close。

- 纯 ctypes 标准库，零第三方依赖（宿主 PyInstaller 打包，插件源码运行时加载，
  不引入 requests 等）。
- 播放阻塞在 worker 线程内（`play <alias> wait`），主线程 stop() 用
  `stop <alias>` 打断 —— mci alias 是进程级，跨线程命令有效。
- macOS 走 afplay 子进程，stop 即终止进程。
"""

from __future__ import annotations

import os
import struct
import subprocess
import sys
import tempfile

from loguru import logger

# mci alias（进程级；同 alias 重复 open 会失败，故每次播放前先 close）
_MCI_ALIAS = "drifox_voice_reply"


def _mci_send(cmd: str) -> int:
    """发一条 mci 命令，返回错误码（0 = 成功）。仅 Windows。"""
    import ctypes

    return int(ctypes.windll.winmm.mciSendStringW(cmd, None, 0, None))


def _mci_error_text(code: int) -> str:
    """mci 错误码转人话（失败时至少给出码）。"""
    import ctypes

    buf = ctypes.create_unicode_buffer(256)
    try:
        ctypes.windll.winmm.mciGetErrorStringW(code, buf, 256)
        return buf.value or f"错误码 {code}"
    except Exception:  # noqa: BLE001
        return f"错误码 {code}"


def describe_wav(data: bytes) -> str:
    """解析 wav 头 → 人话摘要（采样率/声道/位深/格式码/时长）。诊断用。"""
    if len(data) < 44 or data[:4] != b"RIFF":
        return f"非 RIFF 数据（{len(data)} 字节，前 4 字节 {data[:4]!r}）"
    try:
        fmt_code, channels, rate = struct.unpack("<HHI", data[20:28])
        bits = struct.unpack("<H", data[34:36])[0]
        # data chunk 大小：从 36 字节起找 "data"
        pos = 36
        data_size = 0
        while pos + 8 <= len(data):
            cid = data[pos : pos + 4]
            csize = struct.unpack("<I", data[pos + 4 : pos + 8])[0]
            if cid == b"data":
                data_size = csize
                break
            pos += 8 + csize + (csize & 1)  # chunk 按字对齐
        dur = data_size / (rate * channels * (bits // 8)) if rate and channels and bits else 0
        kinds = {1: "PCM", 3: "IEEE-Float", 6: "a-law", 7: "mu-law", 17: "IMA-ADPCM"}
        return (
            f"{rate}Hz/{channels}ch/{bits}bit/{kinds.get(fmt_code, f'fmt={fmt_code}')}"
            f"，{len(data)} 字节，约 {dur:.1f} 秒"
        )
    except Exception as e:  # noqa: BLE001 — 头解析失败不影响播放尝试
        return f"wav 头解析失败（{len(data)} 字节）：{e}"


def play_wav(path: str, proc_slot: dict) -> None:
    """阻塞播放一个 wav（在 worker 线程内调用）。失败抛 RuntimeError（人话）。

    proc_slot 用于主线程 stop() 打断：
    - Windows: {"mci_alias": str, "playing": bool}
    - macOS:   {"proc": Popen}
    """
    if sys.platform == "darwin":
        proc = subprocess.Popen(["afplay", path])
        proc_slot["proc"] = proc
        proc.wait()
        return

    # Windows：winmm mci（有错误码，失败可见）
    _mci_send(f"close {_MCI_ALIAS}")  # 清残留（同 alias 重复 open 会失败）
    code = _mci_send(f'open "{path}" type waveaudio alias {_MCI_ALIAS}')
    if code:
        raise RuntimeError(f"打开音频失败：{_mci_error_text(code)}")
    proc_slot["mci_alias"] = _MCI_ALIAS
    try:
        code = _mci_send(f"play {_MCI_ALIAS} wait")  # wait = 阻塞到播完
        if code:
            raise RuntimeError(f"播放失败：{_mci_error_text(code)}")
    finally:
        proc_slot.pop("mci_alias", None)
        _mci_send(f"close {_MCI_ALIAS}")


def stop_playback(proc_slot: dict) -> None:
    """主线程打断播放（mci stop / 终止 afplay 子进程）。"""
    if sys.platform == "darwin":
        proc = proc_slot.get("proc")
        if proc is not None:
            try:
                proc.terminate()
            except Exception:  # noqa: BLE001 — 进程已退出
                pass
        return
    if proc_slot.get("mci_alias"):
        code = _mci_send(f"stop {_MCI_ALIAS}")
        if code:
            logger.warning(f"[voice-reply] 停止播放失败: {_mci_error_text(code)}")
        _mci_send(f"close {_MCI_ALIAS}")


def write_temp_wav(data: bytes) -> str:
    """wav 字节落临时文件，返回路径（调用方负责删除）。"""
    fd, path = tempfile.mkstemp(suffix=".wav", prefix="voice_reply_")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path
