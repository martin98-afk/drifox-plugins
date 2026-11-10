# -*- coding: utf-8 -*-
"""macOS 分片录音器：AVFoundation (AVAudioRecorder) ctypes 直调。

为什么不用 pyobjc：宿主 PyInstaller 只收集了 objc/Foundation/AppKit/CoreFoundation/
Quartz，AVFoundation 未打包，import 必失败。ctypes 直调不影响打包结果。

每片新建一个 AVAudioRecorder 指向新文件，stop_chunk() 即落盘。与 Windows 版接口
完全一致（start_chunk / stop_chunk / close），上层无平台分支。

权限：macOS TCC 管麦克风，宿主 Info.plist 已声明 NSMicrophoneUsageDescription
（voice-input 依赖同一条）。被拒时 start_chunk() 抛 RuntimeError 带处理指引。
"""

from __future__ import annotations

import ctypes
import os
from contextlib import contextmanager
from ctypes import c_bool, c_char_p, c_float, c_long, c_uint, c_void_p
from pathlib import Path
from typing import Optional

from loguru import logger

_libobjc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
_avfoundation = ctypes.CDLL("/System/Library/Frameworks/AVFoundation.framework/AVFoundation")

_libobjc.objc_getClass.argtypes = [c_char_p]
_libobjc.objc_getClass.restype = c_void_p
_libobjc.sel_registerName.argtypes = [c_char_p]
_libobjc.sel_registerName.restype = c_void_p

_MSG_CACHE: dict = {}

_FORMAT_LPCM = 0x6C70636D
_SAMPLE_RATE = 16000.0
_CHANNELS = 1
_BIT_DEPTH = 16

PERM_NOT_DETERMINED = 0
PERM_RESTRICTED = 1
PERM_DENIED = 2
PERM_AUTHORIZED = 3

_DENIED_HINT = "麦克风权限未授权。请到 系统设置 → 隐私与安全性 → 麦克风 勾选 Drifox 后重试"


def _msg(restype, *argtypes):
    key = (restype, argtypes)
    fn = _MSG_CACHE.get(key)
    if fn is None:
        fn = ctypes.CFUNCTYPE(restype, c_void_p, c_void_p, *argtypes)(("objc_msgSend", _libobjc))
        _MSG_CACHE[key] = fn
    return fn


def _cls(name: str) -> int:
    return _libobjc.objc_getClass(name.encode("utf-8"))


def _sel(name: str) -> int:
    return _libobjc.sel_registerName(name.encode("utf-8"))


def _const(name: str) -> int:
    return c_void_p.in_dll(_avfoundation, name).value


def _nsstr(text: str) -> int:
    return _msg(c_void_p, c_char_p)(_cls("NSString"), _sel("stringWithUTF8String:"), text.encode("utf-8"))


def _num_int(value: int) -> int:
    return _msg(c_void_p, c_long)(_cls("NSNumber"), _sel("numberWithInteger:"), value)


def _num_uint(value: int) -> int:
    return _msg(c_void_p, c_uint)(_cls("NSNumber"), _sel("numberWithUnsignedInt:"), value)


def _num_float(value: float) -> int:
    return _msg(c_void_p, c_float)(_cls("NSNumber"), _sel("numberWithFloat:"), value)


def _num_bool(value: bool) -> int:
    return _msg(c_void_p, c_bool)(_cls("NSNumber"), _sel("numberWithBool:"), value)


def _nserror_message(err_ptr) -> str:
    try:
        if not err_ptr or not err_ptr.value:
            return ""
        desc = _msg(c_void_p)(err_ptr.value, _sel("localizedDescription"))
        if not desc:
            return ""
        raw = _msg(c_char_p)(desc, _sel("UTF8String"))
        return raw.decode("utf-8", "ignore") if raw else ""
    except Exception:  # noqa: BLE001
        return ""


@contextmanager
def _autorelease_pool():
    """同步块内的 autorelease pool。禁止跨事件持有：Qt 每个事件会 pop 自己的池，
    位于其上层的本池会被连带销毁 → 下次 drain 触发 badPop 崩溃。"""
    pool = _msg(c_void_p)(_cls("NSAutoreleasePool"), _sel("new"))
    try:
        yield
    finally:
        _msg(None)(pool, _sel("drain"))


def permission_status() -> int:
    try:
        media = _const("AVMediaTypeAudio")
        return _msg(c_long, c_void_p)(
            _cls("AVCaptureDevice"), _sel("authorizationStatusForMediaType:"), media
        )
    except Exception:  # noqa: BLE001
        return -1


class MacChunkRecorder:
    """单实例分片录音。每片一个新文件。"""

    def __init__(self) -> None:
        self._recorder = None
        self._current_path: Optional[Path] = None
        self._recording = False

    def start_chunk(self, out_path: Path) -> None:
        status = permission_status()
        if status in (PERM_DENIED, PERM_RESTRICTED):
            raise RuntimeError(_DENIED_HINT)
        if status == PERM_NOT_DETERMINED:
            logger.info("[meeting-notes] 麦克风权限未决定，本次将触发系统授权弹窗")

        try:
            with _autorelease_pool():
                self._recorder = self._create_recorder(out_path)
                self._current_path = out_path
                if not _msg(c_bool)(self._recorder, _sel("prepareToRecord")):
                    raise RuntimeError("录音设备准备失败")
                if not _msg(c_bool)(self._recorder, _sel("record")):
                    raise RuntimeError("录音启动失败")
                self._recording = True
        except Exception:
            self.close()
            raise

    def _create_recorder(self, out_path: Path) -> int:
        if out_path.exists():
            os.remove(out_path)
        url = _msg(c_void_p, c_void_p)(
            _cls("NSURL"), _sel("fileURLWithPath:"), _nsstr(str(out_path))
        )
        err = c_void_p()
        recorder = _msg(c_void_p, c_void_p, c_void_p, ctypes.POINTER(c_void_p))(
            _msg(c_void_p)(_cls("AVAudioRecorder"), _sel("alloc")),
            _sel("initWithURL:settings:error:"),
            url,
            self._build_settings(),
            ctypes.byref(err),
        )
        if not recorder:
            detail = _nserror_message(err)
            raise RuntimeError(f"录音设备初始化失败：{detail}" if detail else "录音设备初始化失败")
        return recorder

    @staticmethod
    def _build_settings() -> int:
        settings = _msg(c_void_p)(_cls("NSMutableDictionary"), _sel("dictionary"))
        setter = _msg(None, c_void_p, c_void_p)

        def put(value, key):
            setter(settings, _sel("setObject:forKey:"), value, key)

        put(_num_uint(_FORMAT_LPCM), _const("AVFormatIDKey"))
        put(_num_float(_SAMPLE_RATE), _const("AVSampleRateKey"))
        put(_num_int(_CHANNELS), _const("AVNumberOfChannelsKey"))
        put(_num_int(_BIT_DEPTH), _const("AVLinearPCMBitDepthKey"))
        put(_num_bool(False), _const("AVLinearPCMIsFloatKey"))
        put(_num_bool(False), _const("AVLinearPCMIsBigEndianKey"))
        return settings

    def stop_chunk(self, out_path: Optional[Path] = None) -> Optional[Path]:
        path = out_path or self._current_path
        if self._recorder is None:
            return None
        self.close()
        if path and Path(path).exists():
            return Path(path)
        return None

    def close(self) -> None:
        with _autorelease_pool():
            if self._recorder is not None:
                if self._recording:
                    _msg(None)(self._recorder, _sel("stop"))
                    self._recording = False
                _msg(None)(self._recorder, _sel("release"))
                self._recorder = None
