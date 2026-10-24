# -*- coding: utf-8 -*-
"""AVFoundation (AVAudioRecorder) 录音器：ctypes 直调 Objective-C 运行时，零第三方依赖。

为什么不用 pyobjc：宿主为 PyInstaller 打包，pyobjc 只收集了 objc / Foundation /
AppKit / CoreFoundation / Quartz，AVFoundation 未打包，import 必失败。ctypes 直调
libobjc + AVFoundation 动态库不依赖打包结果，也不新增任何依赖。

录制 16kHz / 16bit / 单声道 PCM WAV（与 Windows 版参数一致）。生命周期与
recorder.VoiceRecorder 同构：MacVoiceRecorder(wav_path) → start() →
stop_and_save(path) → close()。差异：AVAudioRecorder 在初始化时即绑定目标文件，
故路径由构造函数传入（Windows 版在 stop_and_save 时才给）。

权限：macOS TCC 管控麦克风，宿主 app 的 Info.plist 必须声明
NSMicrophoneUsageDescription，否则 tccd 直接拒绝（不弹窗）且录音全程为数字静音
（peak=0）。被拒时 start() 抛 RuntimeError 带处理指引。

线程：AVAudioRecorder 需在有 run loop 的线程上创建与操作，本模块由 UI 主线程调用。
"""

from __future__ import annotations

import ctypes
import os
from ctypes import (
    c_bool,
    c_char_p,
    c_float,
    c_long,
    c_uint,
    c_void_p,
)

from loguru import logger

from .wav_utils import log_saved

# macOS 只在有 AVFoundation 时可用；非 mac 平台 import 本模块即失败（上层按平台分派）
_libobjc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
_avfoundation = ctypes.CDLL(
    "/System/Library/Frameworks/AVFoundation.framework/AVFoundation"
)

_libobjc.objc_getClass.argtypes = [c_char_p]
_libobjc.objc_getClass.restype = c_void_p
_libobjc.sel_registerName.argtypes = [c_char_p]
_libobjc.sel_registerName.restype = c_void_p

# objc_msgSend 类型化指针缓存：同签名复用，避免每次调用重建 CFUNCTYPE
_MSG_CACHE: dict = {}

# 线性 PCM 格式标识（'lpcm' 四字符码）
_FORMAT_LPCM = 0x6C70636D

# 采样参数（与 Windows 版一致：16kHz / 16bit / 单声道）
_SAMPLE_RATE = 16000.0
_CHANNELS = 1
_BIT_DEPTH = 16

# TCC 麦克风授权状态（AVAuthorizationStatus）
PERM_NOT_DETERMINED = 0
PERM_RESTRICTED = 1
PERM_DENIED = 2
PERM_AUTHORIZED = 3

_DENIED_HINT = (
    "麦克风权限未授权。请到 系统设置 → 隐私与安全性 → 麦克风 勾选 Drifox 后重试"
)


def _msg(restype, *argtypes):
    """取 objc_msgSend 的指定签名函数指针（按签名缓存）。

    前两个参数固定为 (receiver, selector)。
    """
    key = (restype, argtypes)
    fn = _MSG_CACHE.get(key)
    if fn is None:
        fn = ctypes.CFUNCTYPE(restype, c_void_p, c_void_p, *argtypes)(
            ("objc_msgSend", _libobjc)
        )
        _MSG_CACHE[key] = fn
    return fn


def _cls(name: str) -> int:
    """按类名取 Objective-C 类对象指针。"""
    return _libobjc.objc_getClass(name.encode("utf-8"))


def _sel(name: str) -> int:
    """按方法名取 selector 指针。"""
    return _libobjc.sel_registerName(name.encode("utf-8"))


def _const(name: str) -> int:
    """取 AVFoundation 导出常量的地址（如 AVFormatIDKey）。"""
    return c_void_p.in_dll(_avfoundation, name).value


def _nsstr(text: str) -> int:
    """Python str → NSString（autorelease，需在 pool 内调用）。"""
    return _msg(c_void_p, c_char_p)(
        _cls("NSString"), _sel("stringWithUTF8String:"), text.encode("utf-8")
    )


def _num_int(value: int) -> int:
    return _msg(c_void_p, c_long)(_cls("NSNumber"), _sel("numberWithInteger:"), value)


def _num_uint(value: int) -> int:
    return _msg(c_void_p, c_uint)(
        _cls("NSNumber"), _sel("numberWithUnsignedInt:"), value
    )


def _num_float(value: float) -> int:
    return _msg(c_void_p, c_float)(_cls("NSNumber"), _sel("numberWithFloat:"), value)


def _num_bool(value: bool) -> int:
    return _msg(c_void_p, c_bool)(_cls("NSNumber"), _sel("numberWithBool:"), value)


def _nserror_message(err_ptr) -> str:
    """NSError* → 本地化描述；取不到返回空串。"""
    try:
        if not err_ptr or not err_ptr.value:
            return ""
        desc = _msg(c_void_p)(err_ptr.value, _sel("localizedDescription"))
        if not desc:
            return ""
        raw = _msg(c_char_p)(desc, _sel("UTF8String"))
        return raw.decode("utf-8", "ignore") if raw else ""
    except Exception:  # noqa: BLE001 — 错误信息提取失败不影响主错误
        return ""


def permission_status() -> int:
    """当前麦克风授权状态（AVAuthorizationStatus）。无权限框架时返回 -1。"""
    try:
        media = _const("AVMediaTypeAudio")
        return _msg(c_long, c_void_p)(
            _cls("AVCaptureDevice"),
            _sel("authorizationStatusForMediaType:"),
            media,
        )
    except Exception:  # noqa: BLE001 — 探测失败按未知处理，交给录音路径报错
        return -1


class MacVoiceRecorder:
    """单实例录音器（AVAudioRecorder）。同一时刻只允许一个会话（由上层状态机保证）。"""

    def __init__(self, wav_path: str) -> None:
        self._wav_path = wav_path
        self._recorder = None
        self._pool = None
        self._recording = False

    def start(self) -> None:
        """建 recorder 并开始录音。权限被拒 / 设备初始化失败均抛 RuntimeError。"""
        status = permission_status()
        if status in (PERM_DENIED, PERM_RESTRICTED):
            raise RuntimeError(_DENIED_HINT)
        if status == PERM_NOT_DETERMINED:
            # 首次使用：本次 record() 会触发系统授权弹窗，用户允许前录到的是静音
            logger.info("[voice-input] 麦克风权限未决定，本次将触发系统授权弹窗")

        # 自管 autorelease pool：跨事件循环持有，close() 时统一 drain
        self._pool = _msg(c_void_p)(_cls("NSAutoreleasePool"), _sel("new"))
        try:
            self._recorder = self._create_recorder()
            if not _msg(c_bool)(self._recorder, _sel("prepareToRecord")):
                raise RuntimeError("录音设备准备失败")
            if not _msg(c_bool)(self._recorder, _sel("record")):
                raise RuntimeError("录音启动失败")
            self._recording = True
            logger.info("[voice-input] 录音开始（macOS/AVFoundation，16kHz/16bit/mono）")
        except Exception:
            self.close()
            raise

    def _create_recorder(self) -> int:
        """构造 AVAudioRecorder（含 16kHz PCM settings）。"""
        if os.path.exists(self._wav_path):
            # 上层用 mkstemp 预建了空文件；AVAudioRecorder 写入前先清掉，避免续写旧数据
            os.remove(self._wav_path)
        url = _msg(c_void_p, c_void_p)(
            _cls("NSURL"), _sel("fileURLWithPath:"), _nsstr(self._wav_path)
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
            raise RuntimeError(
                f"录音设备初始化失败：{detail}" if detail else "录音设备初始化失败"
            )
        return recorder

    @staticmethod
    def _build_settings() -> int:
        """AVAudioRecorder settings 字典：线性 PCM / 16kHz / 16bit / 单声道。"""
        settings = _msg(c_void_p)(_cls("NSMutableDictionary"), _sel("dictionary"))
        setter = _msg(None, c_void_p, c_void_p)
        put = lambda value, key: setter(  # noqa: E731 — 局部三行，函数化无收益
            settings, _sel("setObject:forKey:"), value, key
        )
        put(_num_uint(_FORMAT_LPCM), _const("AVFormatIDKey"))
        put(_num_float(_SAMPLE_RATE), _const("AVSampleRateKey"))
        put(_num_int(_CHANNELS), _const("AVNumberOfChannelsKey"))
        put(_num_int(_BIT_DEPTH), _const("AVLinearPCMBitDepthKey"))
        put(_num_bool(False), _const("AVLinearPCMIsFloatKey"))
        put(_num_bool(False), _const("AVLinearPCMIsBigEndianKey"))
        return settings

    def stop_and_save(self, wav_path: str = "") -> None:
        """停止录音（stop() 即完成落盘）。wav_path 仅为与 Windows 版接口同构。"""
        if self._recorder is None:
            raise RuntimeError("录音器未打开")
        if self._recording:
            _msg(None)(self._recorder, _sel("stop"))
            self._recording = False
        log_saved(self._wav_path, "AVFoundation")
        self.close()

    def close(self) -> None:
        """释放 recorder 与 autorelease pool。重复调用安全。"""
        if self._recorder is not None:
            if self._recording:
                _msg(None)(self._recorder, _sel("stop"))
                self._recording = False
            _msg(None)(self._recorder, _sel("release"))
            self._recorder = None
        if self._pool is not None:
            _msg(None)(self._pool, _sel("drain"))
            self._pool = None
