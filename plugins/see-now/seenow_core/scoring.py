# -*- coding: utf-8 -*-
"""画面变化分 — 逐帧比较，输出 0~255 的变化强度。

算法口径照抄上游 see-now 的 `cuts.js`（其本身来自 dsh-video-storyboard 的
`scan.js`，同一段测试片 9/9 命中切点，而 `ffmpeg scdet` 只 4/9 —— scdet 算的是
亮度类 MAFD，对「同亮度换色」失明）。

两处与上游一致的关键设计：

1. **先在 64×36 网格上做降采样**，每格取 4 个采样点求平均。这既降噪，
   又把逐像素比较的规模压到 9216 次读——实测单帧 0.77ms。
2. **色相按环形处理，且用低饱和侧的饱和度降权**。纯黑白的像素色相无意义，
   不加权会让「灰色换灰色」被误判成大变化。

mss 的 `.rgb` 属性名有误导：实测 len = w*h*3，但字节序其实是 **BGRA**（4 通道，
`.rgb` 只取前 3 个）。`ScreenShot.bgra` 的长度是 w*h*4。移植时按 3 字节步长读，
与上游 rgb24 的假设一致（验证方法见 README「实测基线」）。
"""

from __future__ import annotations

SCAN_W = 64
SCAN_H = 36
_SAMPLES = 4  # 每格 4 个采样点（2x2）


def grid_rgb(rgb: bytes, width: int, height: int, bpp: int = 3) -> list[float]:
    """把整帧 RGB 缓冲降采样成 64×36 网格，每格 4 点求平均。

    返回**扁平**列表 [r0,g0,b0, r1,g1,b1, ...]，长度 = SCAN_W * SCAN_H * 3。
    用扁平表而不是 (r,g,b) 元组列表：每帧 2304 个元组分配实测多花 3~4ms，
    扁平表直接写 float 省掉对象开销。
    """
    out = [0.0] * (SCAN_W * SCAN_H * 3)
    sx = width / SCAN_W
    sy = height / SCAN_H
    idx = 0
    for gy in range(SCAN_H):
        y0 = int((gy + 0.25) * sy)
        y1 = int((gy + 0.75) * sy)
        if y1 >= height:
            y1 = height - 1
        r0 = y0 * width
        r1 = y1 * width
        for gx in range(SCAN_W):
            x0 = int((gx + 0.25) * sx)
            x1 = int((gx + 0.75) * sx)
            if x1 >= width:
                x1 = width - 1
            a = (r0 + x0) * bpp
            b = (r0 + x1) * bpp
            c = (r1 + x0) * bpp
            d = (r1 + x1) * bpp
            out[idx] = (rgb[a] + rgb[b] + rgb[c] + rgb[d]) * 0.25
            out[idx + 1] = (rgb[a + 1] + rgb[b + 1] + rgb[c + 1] + rgb[d + 1]) * 0.25
            out[idx + 2] = (rgb[a + 2] + rgb[b + 2] + rgb[c + 2] + rgb[d + 2]) * 0.25
            idx += 3
    return out


def score_pair(prev: list[float], cur: list[float]) -> float:
    """两帧网格的加权绝对差均值，0~255。

    色相按环形处理（|Δh| 与 255-|Δh| 取小），并用两个像素里**较低的饱和度**
    作为色相权重——低饱和像素的色相不可靠，不该贡献分数。
    饱和度与明度直接取绝对差，不加权。
    """
    n = len(cur) // 3
    if n == 0:
        return 0.0
    total = 0.0
    for i in range(0, len(cur), 3):
        h1, s1, v1 = _rgb_to_hsv_scaled(cur[i], cur[i + 1], cur[i + 2])
        h2, s2, v2 = _rgb_to_hsv_scaled(prev[i], prev[i + 1], prev[i + 2])
        dh = h1 - h2
        if dh < 0:
            dh = -dh
        if 255.0 - dh < dh:
            dh = 255.0 - dh
        hue_weight = (s1 if s1 < s2 else s2) * (1.0 / 255.0)
        ds = s1 - s2
        if ds < 0:
            ds = -ds
        dv = v1 - v2
        if dv < 0:
            dv = -dv
        total += dh * hue_weight + ds + dv
    return total / (n * 3.0)


def _rgb_to_hsv_scaled(r: float, g: float, b: float) -> tuple[float, float, float]:
    """RGB → HSV，各通道归一到 0~255（H 按 360 度缩放到 0~255，与上游一致）。"""
    rn = r * (1.0 / 255.0)
    gn = g * (1.0 / 255.0)
    bn = b * (1.0 / 255.0)
    mx = rn if rn > gn else gn
    if bn > mx:
        mx = bn
    mn = rn if rn < gn else gn
    if bn < mn:
        mn = bn
    d = mx - mn
    if d == 0.0:
        hue = 0.0
    elif mx == rn:
        hue = ((gn - bn) / d) % 6.0
    elif mx == gn:
        hue = (bn - rn) / d + 2.0
    else:
        hue = (rn - gn) / d + 4.0
    hue *= 60.0
    if hue < 0.0:
        hue += 360.0
    sat = 0.0 if mx == 0.0 else (d / mx) * 255.0
    return (hue * (255.0 / 360.0)), sat, mx * 255.0
