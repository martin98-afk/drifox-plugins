"""macOS 系统级快捷键：仅注册指定组合，不监听其他按键。"""

import ctypes as c
import sys

from PyQt5.QtCore import QObject, pyqtSignal


def fourcc(value):
    return int.from_bytes(value, "big")


class EventType(c.Structure):
    _fields_ = [("event_class", c.c_uint32), ("kind", c.c_uint32)]


class HotKeyID(c.Structure):
    _fields_ = [("signature", c.c_uint32), ("id", c.c_uint32)]


Handler = c.CFUNCTYPE(c.c_int32, c.c_void_p, c.c_void_p, c.c_void_p)


class Hotkey(QObject):
    pressed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.api = None
        self.handler = c.c_void_p()
        self.key = c.c_void_p()
        self.callback = Handler(self.dispatch)
        self.token = HotKeyID(fourcc(b"Dnch"), 1)
        self.label = ""
        self.reason = ""
        self.candidates = (("⌃⌥K", 40, 0x1800), ("⌃⌥J", 38, 0x1800), ("⌃⌥空格", 49, 0x1800))

    def register(self):
        if self.key.value:
            return True
        if sys.platform != "darwin":
            return False
        try:
            api = c.CDLL("/System/Library/Frameworks/Carbon.framework/Carbon")
            self.api = api
            ptr, u32, status = c.c_void_p, c.c_uint32, c.c_int32
            signatures = {
                "GetApplicationEventTarget": (ptr, []),
                "InstallEventHandler": (status, [ptr, Handler, u32, c.POINTER(EventType), ptr, c.POINTER(ptr)]),
                "RegisterEventHotKey": (status, [u32, u32, HotKeyID, ptr, u32, c.POINTER(ptr)]),
                "GetEventParameter": (status, [ptr, u32, u32, ptr, u32, ptr, ptr]),
                "UnregisterEventHotKey": (status, [ptr]),
                "RemoveEventHandler": (status, [ptr]),
            }
            for name, (result, args) in signatures.items():
                fn = getattr(api, name)
                fn.restype, fn.argtypes = result, args
            target = api.GetApplicationEventTarget()
            if not target:
                return False
            event = EventType(fourcc(b"keyb"), 5)
            status = api.InstallEventHandler(
                target, self.callback, 1, c.byref(event), None, c.byref(self.handler)
            )
            if status:
                self.reason = f"安装回调失败 {status}"
                self.close()
                return False
            for label, code, mods in self.candidates:
                status = api.RegisterEventHotKey(code, mods, self.token, target, 0, c.byref(self.key))
                if not status:
                    self.label = label
                    return True
                self.reason = f"{label} 已被占用"
        except (OSError, AttributeError) as exc:
            self.reason = type(exc).__name__
        self.close()
        return False

    def dispatch(self, _next, event, _data):
        token = HotKeyID()
        error = self.api.GetEventParameter(event, fourcc(b"----"), fourcc(b"hkid"), None,
                                           c.sizeof(token), None, c.byref(token))
        if error or (token.signature, token.id) != (self.token.signature, self.token.id):
            return -9874
        self.pressed.emit()
        return 0

    def close(self):
        if self.api is None:
            return
        if self.key.value:
            self.api.UnregisterEventHotKey(self.key)
            self.key = c.c_void_p()
        if self.handler.value:
            self.api.RemoveEventHandler(self.handler)
            self.handler = c.c_void_p()
