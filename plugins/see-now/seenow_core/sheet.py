# -*- coding: utf-8 -*-
"""留帧策略与宫格拼图 — 把「值得看的几帧」压进一张图。

## 为什么要纯 Python 拼图

第一版用 QPainter 在 QImage 上画格子和时间码，结果在无 QGuiApplication 的
环境里（后台线程、headless、测试脚本）**直接段错误**：没有平台插件，
字体引擎不可用，`QPainter.drawText` 崩在 C++ 层（实测 exit code 0xC0000005）。

工具 impl 跑在 worker 线程，不能假设一定拿得到 GUI 上下文。所以这里
**完全不用 Qt 画图**：自己拼字节、自己写 PNG（zlib 是标准库）、自己画
一个 5×7 位图字体。代价是零依赖、零崩溃面，且后台线程安全。

缩放仍走 QImage（`capture.py`），那条路径不碰 QPainter，实测正常。

## 排版

硬切 / 积分留下的帧一律等分格子：1 帧整幅、2 帧左右、3~4 帧 2×2、5~6 帧 2×3。
不搞可变档位 bin-packing —— 那套（384 行 DP）是为「看视频」服务的，
桌面操作的帧数少且尺寸一致，等格足够。
"""

from __future__ import annotations

import math
import struct
import zlib
from dataclasses import dataclass
from typing import List, Optional, Sequence

from loguru import logger

# 变化分阈值：低于此值认为「画面没变」，不留帧。
# 依据：静止桌面（只有时钟秒数在跳）实测 0~3 分；滚一屏网页 40~90 分；
# 切窗口 120+ 分。12 分能滤掉光标闪烁和轻微动画，又不会漏掉小弹窗。
DEFAULT_THRESHOLD = 12.0
# 兜底：这么久没出图，无论变没变都给一张（让模型知道「确实没变」）
DEFAULT_FALLBACK_SECONDS = 20.0
# 单张最多几帧
MAX_FRAMES = 6


@dataclass
class KeptFrame:
    """留下来要拼进图的一帧。"""

    rgb: bytes
    width: int
    height: int
    score: float
    at: float  # 相对起点多少秒（拼图角标用）
    reason: str  # "cut"（变化够大） / "fallback"（兜底）


class FrameSelector:
    """决定哪些帧进图。状态只在这个类里。"""

    def __init__(
        self,
        threshold: float = DEFAULT_THRESHOLD,
        fallback_seconds: float = DEFAULT_FALLBACK_SECONDS,
        max_frames: int = MAX_FRAMES,
    ):
        self._threshold = float(threshold)
        self._fallback = float(fallback_seconds)
        self._max_frames = int(max_frames)
        self._kept: List[KeptFrame] = []
        self._origin: Optional[float] = None
        # 上一次留帧的绝对时刻（兜底计时基准）。None = 图刚被取走，下一帧只当计时起点
        self._last_kept_at: Optional[float] = None
        # 「冷启动首帧必留」只在整个选择器的第一次 push 生效一次。
        # 不能拿 _last_kept_at is None 判断首帧：take() 也会把它置 None，
        # 于是每次取空后紧接着的一帧都被当首帧留下，watch 就永远等不到「没变化」。
        self._primed = False

    def reset(self) -> None:
        self._kept.clear()
        self._origin = None
        self._last_kept_at = None
        self._primed = False

    def push(self, rgb: bytes, width: int, height: int, score: float, at: float) -> None:
        """喂一帧。按判据决定留不留。"""
        if self._origin is None:
            self._origin = at
        origin = self._origin

        def _append(reason: str) -> None:
            self._kept.append(
                KeptFrame(rgb=rgb, width=width, height=height, score=score, at=at - origin, reason=reason)
            )
            # 满了先挤掉最旧的一帧（保留最新的，模型更关心刚发生的事）
            if len(self._kept) > self._max_frames:
                self._kept.pop(0)
            self._last_kept_at = at

        if not self._primed:
            # 冷启动首帧必留（否则第一张图可能是空的）
            self._primed = True
            _append("cut")
            return
        if score >= self._threshold:
            _append("cut")
            return
        if self._last_kept_at is None:
            # 上一张图刚被取走：这一帧只当兜底计时起点，不留
            self._last_kept_at = at
            return
        if at - self._last_kept_at >= self._fallback:
            _append("fallback")

    def take(self) -> List[KeptFrame]:
        """取出当前攒的帧并清空（下次出图从头攒）。"""
        frames = self._kept
        self._kept = []
        # 只清兜底计时基准，不清 _primed：取空不代表「从没见过画面」，
        # 下一帧不该再享受首帧必留的待遇。
        self._last_kept_at = None
        # origin 不复位：连续观察时时间轴要接着走，不然每张图都从 0.0s 开始
        return frames

    def pending(self) -> int:
        return len(self._kept)


# ──────────────────── 5×7 位图字体 ────────────────────
# 只画时间码需要的字符：数字、小数点、s。每字符 5 列 × 7 行，1 bit 一像素。
_DIGITS = {
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11111", "00010", "00100", "00010", "00001", "10001", "01110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00010", "01100"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    "s": ("00000", "00000", "01111", "10000", "01110", "00001", "11110"),
    "f": ("00110", "01000", "11100", "01000", "01000", "01000", "01000"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
}


def _measure_text(text: str, scale: int = 2) -> int:
    """位图字实际占宽（与 _blit_text 的步进口径一致）。"""
    if not text:
        return 0
    glyph_w = 5 * scale
    gap = 2 * scale
    return len(text) * glyph_w + (len(text) - 1) * gap


def _blit_text(canvas: bytearray, canvas_w: int, canvas_h: int, x: int, y: int, text: str, scale: int = 2) -> int:
    """在画布上画一行位图字（白字 + 黑描边，保证在任何底色上都可读）。

    返回文字实际占用的宽度（像素），供调用方画底板对齐。
    字间距用 `2 * scale`（第一版用 `scale`，2px 时字符黏成一片糊）。
    """
    glyph_w = 5 * scale
    gap = 2 * scale
    cursor = x
    for ch in text:
        glyph = _DIGITS.get(ch)
        if glyph is None:
            cursor += glyph_w + gap
            continue
        # 先画黑描边（8 邻域偏移 1px），再画白字中心——顺序不能反，
        # 反过来白字会被后画的黑边啃掉一圈。
        for col_r, col_g, col_b, offsets in (
            (0, 0, 0, ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1))),
            (255, 255, 255, ((0, 0),)),
        ):
            for row_idx, row in enumerate(glyph):
                for col_idx, bit in enumerate(row):
                    if bit != "1":
                        continue
                    # 每个位要铺满 scale×scale 的方块（第一版只画了 1 像素，
                    # 于是字看起来是一堆间隔 scale 的点阵，糊成网格）
                    for sub_y in range(scale):
                        for sub_x in range(scale):
                            for dx, dy in offsets:
                                px = cursor + col_idx * scale + sub_x + dx
                                py = y + row_idx * scale + sub_y + dy
                                if 0 <= px < canvas_w and 0 <= py < canvas_h:
                                    off = (py * canvas_w + px) * 3
                                    canvas[off] = col_r
                                    canvas[off + 1] = col_g
                                    canvas[off + 2] = col_b
        cursor += glyph_w + gap
    return cursor - x - gap if cursor > x else 0


def _fill_rect(canvas: bytearray, canvas_w: int, canvas_h: int, x: int, y: int, w: int, h: int, shade: int = 0) -> None:
    """填充纯色矩形（格线用）。"""
    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(canvas_w, x + w)
    y1 = min(canvas_h, y + h)
    if x0 >= x1 or y0 >= y1:
        return
    row = bytes((shade, shade, shade)) * (x1 - x0)
    for py in range(y0, y1):
        off = (py * canvas_w + x0) * 3
        canvas[off : off + len(row)] = row


def _fill_rect_alpha(
    canvas: bytearray,
    canvas_w: int,
    canvas_h: int,
    x: int,
    y: int,
    w: int,
    h: int,
    shade: int = 0,
    alpha: float = 0.5,
) -> None:
    """半透明填充矩形（时间码底板用）。按 alpha 与底色混合。"""
    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(canvas_w, x + w)
    y1 = min(canvas_h, y + h)
    if x0 >= x1 or y0 >= y1:
        return
    keep = 1.0 - float(alpha)
    target = int(shade)
    for py in range(y0, y1):
        base = (py * canvas_w) * 3
        for px in range(x0, x1):
            off = base + px * 3
            canvas[off] = int(canvas[off] * keep + target * alpha)
            canvas[off + 1] = int(canvas[off + 1] * keep + target * alpha)
            canvas[off + 2] = int(canvas[off + 2] * keep + target * alpha)


def _blit_cover(
    canvas: bytearray,
    canvas_w: int,
    canvas_h: int,
    frame: KeptFrame,
    dst_x: int,
    dst_y: int,
    dst_w: int,
    dst_h: int,
) -> None:
    """把一帧**填满**指定矩形（cover 模式：按较大比例放大后裁掉超出部分）。

    为什么不用 contain（留黑边）：格子比例与源比例一致时两者等价；
    不一致时 contain 会留大片黑边，模型看到的是「一堆黑框里的小图」，
    视觉信息密度骤降。cover 宁可裁掉边缘也要填满。
    """
    if dst_w <= 0 or dst_h <= 0:
        return
    src_w, src_h = frame.width, frame.height
    if src_w <= 0 or src_h <= 0:
        return

    # 放大到能盖住目标矩形
    scale = max(dst_w / src_w, dst_h / src_h)
    draw_w = max(dst_w, int(src_w * scale + 0.5))
    draw_h = max(dst_h, int(src_h * scale + 0.5))
    # 居中裁剪的偏移（源坐标）
    crop_x = (draw_w - dst_w) // 2
    crop_y = (draw_h - dst_h) // 2

    for row in range(dst_h):
        py = dst_y + row
        if not (0 <= py < canvas_h):
            continue
        sy = min(src_h - 1, max(0, int((row + crop_y) * src_h / draw_h)))
        src_row = sy * src_w
        base = (py * canvas_w) * 3
        for col in range(dst_w):
            px = dst_x + col
            if not (0 <= px < canvas_w):
                continue
            sx = min(src_w - 1, max(0, int((col + crop_x) * src_w / draw_w)))
            s = (src_row + sx) * 3
            d = base + px * 3
            canvas[d] = frame.rgb[s]
            canvas[d + 1] = frame.rgb[s + 1]
            canvas[d + 2] = frame.rgb[s + 2]


def _png_encode(width: int, height: int, rgb: bytes) -> bytes:
    """RGB 字节 → PNG 字节（标准库 zlib，无外部依赖）。"""
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)  # filter type 0 (None)
        raw += rgb[y * stride : (y + 1) * stride]
    compressed = zlib.compress(bytes(raw), 6)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8bit truecolor
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")


def compose_sheet(frames: Sequence[KeptFrame], sheet_w: int = 800) -> Optional[bytes]:
    """把若干帧拼成一张宫格 PNG（返回 PNG 字节）。

    **格子一律 16:9**（与源画面比例一致，cover 模式零裁剪），整图高度按行数算：
    1 帧 → 800×450；2 帧 → 2×1 各 400×225；3~4 帧 → 2×2 各 400×225（总 800×450）；
    5~6 帧 → 3×2 各 267×150（总 800×300）。

    做法是先定格子尺寸再算整图高度，而不是先定整图再除格子——后者会让格子
    比例随帧数漂移，画面被压扁或留黑边（第一版就是这么错的）。

    每格左上角烧时间码（如 `12.4s`），让模型能把话对到某一格上。
    """
    if not frames:
        return None
    count = len(frames)
    if count == 1:
        cols, rows = 1, 1
    elif count == 2:
        cols, rows = 2, 1
    elif count <= 4:
        cols, rows = 2, 2
    else:
        cols, rows = 3, 2

    cell_w = sheet_w // cols
    cell_h = int(cell_w * 9 / 16)  # 16:9
    # 宽度不能整除时（如 3 列 → 266×3 = 798），最后一列补足余数，
    # 否则右边留 2px 黑边；补足量写在 cell_w_last 里统一用。
    cell_w_last = sheet_w - cell_w * (cols - 1)
    sheet_h = cell_h * rows

    canvas = bytearray(sheet_w * sheet_h * 3)  # 全黑底
    for idx, frame in enumerate(frames):
        row = idx // cols
        col = idx % cols
        x = col * cell_w
        y = row * cell_h
        w = cell_w_last if col == cols - 1 else cell_w
        _blit_cover(canvas, sheet_w, sheet_h, frame, x, y, w, cell_h)

        label = f"{frame.at:.1f}s"
        # 时间码：小字 + 半透明黑底，底板宽度按文字实际宽度算
        text_w = _measure_text(label, scale=2)
        _fill_rect_alpha(canvas, sheet_w, sheet_h, x + 5, y + 5, text_w + 10, 20, shade=0, alpha=0.6)
        _blit_text(canvas, sheet_w, sheet_h, x + 4, y + 6, label, scale=2)
        # 格线（1px 中灰），让格子边界清楚
        if col > 0:
            _fill_rect(canvas, sheet_w, sheet_h, x, y, 1, cell_h, shade=45)

    try:
        return _png_encode(sheet_w, sheet_h, bytes(canvas))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[see-now] PNG 编码失败: {e}")
        return None


def sheet_size(frames: int, sheet_w: int = 800) -> tuple[int, int]:
    """帧数 → 成品图尺寸（宽, 高）。与 compose_sheet 的内部算法保持一致。"""
    if frames <= 1:
        cols, rows = 1, 1
    elif frames == 2:
        cols, rows = 2, 1
    elif frames <= 4:
        cols, rows = 2, 2
    else:
        cols, rows = 3, 2
    cell_w = sheet_w // cols
    return (sheet_w, int(cell_w * 9 / 16) * rows)


def grid_shape(count: int) -> tuple[int, int]:
    """帧数 → (cols, rows)。用于给模型描述「这几帧怎么排的」。"""
    if count <= 1:
        return (1, 1)
    if count == 2:
        return (2, 1)
    if count <= 4:
        return (2, 2)
    return (3, 2)


def estimate_tokens(width: int = 800, height: int = 450) -> int:
    """粗估一张图的 token 成本（按 14px patch 向上对齐）。

    注意：这是 DSH / DeepSeek-V4 的口径，**DriFox 的实际视觉编码不同**，
    这个数字只能当量级参考。真要算准需要用实际模型跑一次。
    """
    patch = 14
    rows = math.ceil(height / patch / 3)
    cols = math.ceil(width / patch / 3)
    return rows * (cols + 1) + 2
