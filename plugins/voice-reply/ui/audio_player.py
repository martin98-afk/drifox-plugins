# -*- coding: utf-8 -*-
"""voice-reply 音频播放：Windows winmm mciSendStringW（主）/ macOS afplay。

为什么不用 winsound.PlaySound（2026-10-12 实测踩坑）：
PlaySound 播放失败时**不抛异常、静默无声**，且对 WAV 兼容面极窄（只吃标准
PCM，服务端返回的 wav 常带额外 chunk 或非 44.1k 采样率即失败）。表现为
「提示播放中但听不到」且日志干净，无法诊断。改用 winmm mciSendStringW：
命令返回码非 0 即失败，可 mciGetErrorStringW 转人话；支持显式 stop/close。

- 纯 ctypes 标准库，零第三方依赖（宿主 PyInstaller 打包，插件源码运行时加载，
  不引入 requests 等）。
- 播放阻塞在 worker 线程内（轮询 `status mode`），主线程 stop() 置
  `threading.Event` 打断，stop/close 命令由播放线程自己发出 —— mci alias
  绑定 open 线程，跨线程发 stop 无效（实测返回 263，音频照常播完）。
- macOS 走 afplay 子进程，stop 即终止进程。
"""

from __future__ import annotations

import os
import struct
import subprocess
import sys
import tempfile

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


def play_wav(path: str, proc_slot: dict, stop_event=None) -> None:
    """阻塞播放一个 wav（在 worker 线程内调用）。失败抛 RuntimeError（人话）。

    proc_slot 用于主线程 stop() 打断：
    - Windows: {"mci_alias": str, "stop_event": threading.Event}
    - macOS:   {"proc": Popen}

    为什么 Windows 不用 `play <alias> wait`（2026-10-18 实测踩坑）：
    mciSendStringW 的 alias 绑定到**发起 open 的那个线程**。`play ... wait`
    阻塞在 worker 线程时，主线程发 `stop <alias>` 返回 263「指定的设备未打开」，
    停不掉，音频整段播完。改为异步 `play` + 本线程轮询 `status <alias> mode`，
    主线程 stop() 只置 stop_event，由本线程发 stop/close（同线程才有效）。
    """
    if sys.platform == "darwin":
        proc = subprocess.Popen(["afplay", path])
        proc_slot["proc"] = proc
        proc.wait()
        return

    if stop_event is None:
        import threading

        stop_event = threading.Event()

    # Windows：winmm mci（有错误码，失败可见）
    _mci_send(f"close {_MCI_ALIAS}")  # 清残留（同 alias 重复 open 会失败）
    code = _mci_send(f'open "{path}" type waveaudio alias {_MCI_ALIAS}')
    if code:
        raise RuntimeError(f"打开音频失败：{_mci_error_text(code)}")
    proc_slot["mci_alias"] = _MCI_ALIAS
    proc_slot["stop_event"] = stop_event
    try:
        code = _mci_send(f"play {_MCI_ALIAS}")  # 异步：立即返回，由下方轮询
        if code:
            raise RuntimeError(f"播放失败：{_mci_error_text(code)}")
        _wait_playback_done(stop_event)
    finally:
        proc_slot.pop("mci_alias", None)
        proc_slot.pop("stop_event", None)
        _mci_send(f"stop {_MCI_ALIAS}")
        _mci_send(f"close {_MCI_ALIAS}")


def _wait_playback_done(stop_event) -> None:
    """轮询播放状态直到自然播完或被要求停止（在播放线程内调用）。

    `status <alias> mode` 返回 "playing"/"paused"/"stopped"/"not ready"。
    空串视为设备已关闭（异常退出）同样跳出，避免死等。
    """
    import ctypes

    buf = ctypes.create_unicode_buffer(64)
    while not stop_event.is_set():
        code = ctypes.windll.winmm.mciSendStringW(
            f"status {_MCI_ALIAS} mode", buf, 64, None
        )
        mode = buf.value if code == 0 else ""
        if mode in ("stopped", "not ready", ""):
            return
        stop_event.wait(0.15)  # 轮询节拍：兼顾响应延迟与 CPU 占用


def stop_playback(proc_slot: dict) -> None:
    """主线程打断播放（mci stop / 终止 afplay 子进程）。

    Windows 侧只置 stop_event：真正的 mci stop/close 必须由播放线程自己发
    （alias 绑定 open 线程，跨线程发无效，实测返回 263）。
    """
    if sys.platform == "darwin":
        proc = proc_slot.get("proc")
        if proc is not None:
            try:
                proc.terminate()
            except Exception:  # noqa: BLE001 — 进程已退出
                pass
        return
    stop_event = proc_slot.get("stop_event")
    if stop_event is not None:
        stop_event.set()


def write_temp_wav(data: bytes) -> str:
    """wav 字节落临时文件，返回路径（调用方负责删除）。"""
    fd, path = tempfile.mkstemp(suffix=".wav", prefix="voice_reply_")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path
