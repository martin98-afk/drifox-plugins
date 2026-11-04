# -*- coding: utf-8 -*-
"""采集 — 唯一碰屏幕的地方。

用 mss 而不用 QScreen.grabWindow，原因是线程约束：

| 路径 | 单帧 p50 | 线程约束 |
|---|---|---|
| `QScreen.grabWindow(0)` | 60~180 ms（随负载波动） | **必须主线程**（Windows） |
| mss.grab 全屏 | 39~178 ms（波动大） | 任意线程 |

把 ms 级成本放在主线程＝每抓一帧就卡一次 UI，所以用 mss 跑后台线程。

## 实测基线（1920×1080 / Win11，含打分，2026-11-04）

| 环节 | p50 |
|---|---|
| mss.grab 全屏 | **40~178 ms**（波动极大，取决于桌面合成器负载） |
| QImage.scaled(800,450, Smooth) | 9.8 ms |
| QImage.scaled(800,450, Fast) | 8.5 ms |
| 64×36 采样（扁平表） | 5.5 ms |
| HSV 打分 | 6.9 ms |
| **全链路** | **约 104 ms** |

抓屏本身占了 90%+。所以 **fps 不能定高**：默认 1 fps（占空比约 10%），
可在「设置 → 插件 → 看屏幕」调到 6 fps（约 62% 单核，不建议）。上游用 12 fps
是因为它走 ffmpeg 的 ddagrab（GPU 桌面复制 API，0.28 核），Python 侧拿不到那条路。

**依赖自包含**：mss 与 six 已复制进本插件 `deps/`（246KB），与
desktop-automation 各持一份，互不依赖（插件间不共享 deps 是项目约定）。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Optional, Tuple

from loguru import logger

# 插件自包含依赖注入：优先加载本插件 deps/ 目录
_DEPS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "deps"))
if os.path.isdir(_DEPS) and _DEPS not in sys.path:
    sys.path.insert(0, _DEPS)

TARGET_W = 800
TARGET_H = 450  # 出图尺寸（16:9）


@dataclass
class Frame:
    """一帧采集结果（只留缩放后的像素，原始全屏不留——内存压力太大）。"""

    at: float  # time.monotonic()
    rgb: bytes  # 目标尺寸的 RGB 字节（3 字节/像素）
    width: int
    height: int
    score: float = 0.0  # 与上一帧的变化分，首帧为 0


class ScreenGrabber:
    """mss 采集 + 缩放到目标尺寸。任意线程可用（每次 grab 现开 mss 实例）。"""

    def __init__(self, target_w: int = TARGET_W, target_h: int = TARGET_H):
        self._target_w = target_w
        self._target_h = target_h
        self._sct = None
        self._monitor: Optional[dict] = None

    def is_available(self) -> bool:
        try:
            return self._ensure() is not None
        except Exception:  # noqa: BLE001
            return False

    def _ensure(self):
        if self._sct is not None:
            return self._sct
        import mss

        self._sct = mss.mss()
        self._monitor = dict(self._sct.monitors[1])  # 主显示器
        return self._sct

    def screen_size(self) -> Tuple[int, int]:
        if self._monitor is None:
            try:
                self._ensure()
            except Exception:  # noqa: BLE001
                return (0, 0)
        if not self._monitor:
            return (0, 0)
        return (self._monitor["width"], self._monitor["height"])

    def grab_scaled(self) -> Optional[Tuple[bytes, int, int]]:
        """抓全屏并缩到目标尺寸，返回 (rgb, w, h)。失败返回 None。

        缩放走 Qt 的 QImage.scaled（C++ 侧，实测 <1ms）。虽然引入了 Qt 依赖，
        但只在后台线程对本进程内的 QImage 对象操作，不碰 QWidget，线程安全。
        """
        try:
            sct = self._ensure()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[see-now] 初始化 mss 失败: {e}")
            return None
        try:
            raw = sct.grab(self._monitor)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[see-now] 抓屏失败: {e}")
            # 句柄可能已失效，下次重建
            self._close()
            return None
        # 缩放走 Qt 的 QImage.scaled（C++ 侧）。Smooth 比 Fast 只贵 1.3ms
        # （9.8 vs 8.5），但文字清晰度差很多——看屏幕就是要读字，用 Smooth。
        try:
            return _resize(raw.rgb, raw.width, raw.height, self._target_w, self._target_h)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[see-now] 缩放失败: {e}")
            return None

    def _close(self) -> None:
        try:
            if self._sct is not None:
                self._sct.close()
        except Exception:  # noqa: BLE001
            pass
        self._sct = None
        self._monitor = None

    def close(self) -> None:
        self._close()


def _resize(rgb: bytes, width: int, height: int, target_w: int, target_h: int) -> Tuple[bytes, int, int]:
    """整帧缩放到目标尺寸。

    优先用 QImage（C++ 实现，快且质量好）；Qt 不可用时退回最近邻（纯 Python，
    慢但能用，只在极端环境触达）。
    """
    if width == target_w and height == target_h:
        return rgb, width, height
    try:
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QImage

        # mss 的 .rgb 实为 BGRA 步长（见 scoring.py 说明），用 Format_RGB32 读再转
        img = QImage(rgb, width, height, width * 3, QImage.Format_RGB888)
        scaled = img.scaled(target_w, target_h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        fmt = scaled.convertToFormat(QImage.Format_RGB888)
        ptr = fmt.constBits()
        ptr.setsize(fmt.byteCount())
        buf = bytes(ptr)
        stride = fmt.bytesPerLine()
        row_bytes = target_w * 3
        if stride == row_bytes:
            return buf, target_w, target_h
        out = bytearray(row_bytes * target_h)
        for y in range(target_h):
            src = y * stride
            out[y * row_bytes : (y + 1) * row_bytes] = buf[src : src + row_bytes]
        return bytes(out), target_w, target_h
    except Exception:  # noqa: BLE001 - Qt 不可用时退回最近邻
        return _resize_nearest(rgb, width, height, target_w, target_h)


def _resize_nearest(rgb: bytes, width: int, height: int, target_w: int, target_h: int) -> Tuple[bytes, int, int]:
    """最近邻缩放（纯 Python 兜底）。"""
    out = bytearray(target_w * target_h * 3)
    xs = [min(width - 1, int(x * width / target_w)) for x in range(target_w)]
    for y in range(target_h):
        sy = min(height - 1, int(y * height / target_h))
        src_row = sy * width
        dst_row = y * target_w
        for x in range(target_w):
            s = (src_row + xs[x]) * 3
            d = (dst_row + x) * 3
            out[d] = rgb[s]
            out[d + 1] = rgb[s + 1]
            out[d + 2] = rgb[s + 2]
    return bytes(out), target_w, target_h
