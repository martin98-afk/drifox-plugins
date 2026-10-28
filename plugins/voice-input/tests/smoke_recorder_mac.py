# -*- coding: utf-8 -*-
"""macOS 录音器回归测试：autorelease pool 必须与 objc 调用同同步块。

背景（0.6.1 崩溃）：recorder_mac 曾把 NSAutoreleasePool 作为实例字段跨事件持有，
start() 建池、stop_and_save() 才 drain。objc 池是栈式的，Qt 每个事件结束都 pop
自己的池，位于其上层的本池被连带销毁，下一次事件 drain 触发
AutoreleasePoolPage::badPop → SIGABRT（宿主直接闪退，Python 日志无痕迹）。

崩溃 report 的判定指纹：栈里有 _CFAutoreleasePoolPop → NSAutoreleasePool drain
→ badPop。

跑法（工作目录 = 仓库根）：
    python plugins/voice-input/tests/smoke_recorder_mac.py

非 macOS 或未授权麦克风时自动 skip（退出码 0）。
测试在子进程里跑录音循环：崩溃是 SIGABRT，会带走整个解释器，无法在进程内断言。
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 子进程脚本：用 objc 手工建/销池，模拟 Qt「每事件 push-pop」语义
_CHILD = textwrap.dedent(
    """
    import ctypes, gc, os, sys, tempfile
    from ctypes import c_char_p, c_void_p

    sys.path.insert(0, sys.argv[1])
    import ui.recorder_mac as M
    from ui.wav_utils import parse_wav_header, wav_duration

    lo = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
    lo.objc_getClass.argtypes = [c_char_p]
    lo.objc_getClass.restype = c_void_p
    lo.sel_registerName.argtypes = [c_char_p]
    lo.sel_registerName.restype = c_void_p
    _new = ctypes.CFUNCTYPE(c_void_p, c_void_p, c_void_p)(("objc_msgSend", lo))
    _drain = ctypes.CFUNCTYPE(None, c_void_p, c_void_p)(("objc_msgSend", lo))
    _POOL = lo.objc_getClass(b"NSAutoreleasePool")
    _NEW = lo.sel_registerName(b"new")
    _DRAIN = lo.sel_registerName(b"drain")

    def event(fn, *args):
        # Qt 语义：进事件 push 池，出事件 pop 池
        pool = _new(_POOL, _NEW)
        try:
            return fn(*args)
        finally:
            _drain(pool, _DRAIN)

    rounds = int(sys.argv[2])
    for rnd in range(rounds):
        fd, wav = tempfile.mkstemp(suffix=".wav", prefix="vi_smoke_")
        os.close(fd)
        rec = M.MacVoiceRecorder(wav)
        event(rec.start)
        # 中间穿插大量事件，模拟浮窗 tick + 宿主其他事件
        for _ in range(200):
            event(lambda: None)
        event(rec.stop_and_save, wav)
        for _ in range(200):
            event(lambda: None)
        # 数据有效性：头合法 + 采到非空数据（防「不崩但录空」的假通过）
        raw = open(wav, "rb").read(8192)
        rate, ch, bits, off = parse_wav_header(raw)
        size = os.path.getsize(wav)
        assert (rate, ch, bits) == (16000, 1, 16), f"round {rnd} 头异常: {(rate, ch, bits)}"
        assert size - off > 1000, f"round {rnd} 数据区过小: {size - off}"
        os.remove(wav)
        del rec
        gc.collect()
    print("recorder_mac ok: %d rounds, no badPop" % rounds)
    """
)


def main() -> int:
    if sys.platform != "darwin":
        print("skip: 非 macOS")
        return 0

    try:
        sys.path.insert(0, _PLUGIN_DIR)
        from ui.recorder_mac import PERM_AUTHORIZED, permission_status

        status = permission_status()
    except Exception as e:  # noqa: BLE001 — 环境不具备（无 AVFoundation 等）
        print(f"skip: 无法探测麦克风权限 ({e})")
        return 0
    if status != PERM_AUTHORIZED:
        print(f"skip: 麦克风未授权（status={status}）")
        return 0

    proc = subprocess.run(
        [sys.executable, "-c", _CHILD, _PLUGIN_DIR, "3"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        print(f"FAIL: 子进程退出码 {proc.returncode}（-6/SIGABRT 即 badPop 崩溃）")
        return proc.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
