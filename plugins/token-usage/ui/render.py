# -*- coding: utf-8 -*-
"""渲染层 — 欢迎卡片「🔢 用量」tab 的 HTML 片段生成

版式照 GitHub 个人主页的贡献热力图：
- 顶部标题行「🔢 Token 用量」+ 右侧「刷新用量」（点 context-tag 触发重采）
- 30 天窗口的四指标：总 Token / 输入 Token / 输出 Token / 请求次数
- 365 天 GitHub 风格活动热力图（按周分列，7 行 = 周一至周日）

渲染约束（宿主 QWebEngine = Chromium 83，Qt 5.15.2）：
- 不用 flex `gap`（83 不支持）→ 间距一律走 margin / border-spacing
- 不用 `aspect-ratio`（84+ 才有）→ 格子用固定 px 尺寸 + flex 容器
- 不用 `min()` / `clamp()`（83 不支持）→ 尺寸全用 px
- <style> 可用（welcome body 拼进主文档，与 marketplace-recommend 同款）

色阶：按当日总 Token 的分位数分 5 档（抗单日尖峰，避免满屏只剩一格深色）。
"""

import html
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from .data import sum_window

# ── 指标窗口 ──────────────────────────────────────────────
_METRIC_DAYS = 30
_HEATMAP_DAYS = 365

_ACTION_REFRESH = "tu-refresh"


def _fs(size: int) -> int:
    """字号跟随 DriFox 全局 UI 字号设置（宿主 scale_font_size）"""
    try:
        from app.utils.design_tokens import scale_font_size

        return scale_font_size(size)
    except Exception:
        return size


def _palette(is_dark: bool) -> dict:
    """明暗色板

    tooltip 的底色/边框直接取自 context-stats（echarts tooltip_bg/border），
    两个插件的悬停提示观感保持一致。
    """
    if is_dark:
        return {
            "text": "#e6e6e6",
            "muted": "#8a8a8a",
            "faint": "#7d7d7d",
            "border": "rgba(255,255,255,0.12)",
            "panel": "rgba(255,255,255,0.035)",
            "accent": "#5aa2f5",
            "tooltip_bg": "rgba(30,34,42,0.92)",
            "tooltip_border": "rgba(98,160,234,0.5)",
            "empty": "rgba(255,255,255,0.07)",
            # 5 档色阶：与浅色同语义 —— 越深代表用量越多（用户 2026-10-14 要求）
            # ⚠️ 深色底上的固有约束：越深越接近背景（#1e1e1e，亮度 30），
            # 最高档必须留足亮度差才不「沉进背景」。本组档5 #1f4a86 亮度 69，
            # 与背景差 39（≈2.3 倍），既明确最深又可辨；档间差约 25 保证 5 档分得开。
            "levels": [
                "#8ab4e8",
                "#6d9bd4",
                "#527fbd",
                "#3964a3",
                "#1f4a86",
            ],
        }
    return {
        "text": "#1f1f1f",
        "muted": "#7a7a7a",
        "faint": "#b0b0b0",
        "border": "rgba(0,0,0,0.09)",
        "panel": "rgba(0,0,0,0.025)",
        "accent": "#2b7de9",
        "tooltip_bg": "rgba(255,255,255,0.96)",
        "tooltip_border": "rgba(40,120,220,0.45)",
        "empty": "rgba(0,0,0,0.055)",
        "levels": [
            "rgba(43,125,233,0.22)",
            "rgba(43,125,233,0.42)",
            "rgba(43,125,233,0.64)",
            "rgba(33,105,215,0.85)",
            "rgba(20,80,180,1)",
        ],
    }


def _fmt_k(n: int) -> str:
    """数字缩写：130000 → '130K'，50600 → '50.6K'，1234 → '1.2K'

    截图用的是 130K / 50.5K / 4.9K 这种风格（K 大写、整数去尾 .0）。
    """
    if n >= 1_000_000_000:
        v = n / 1_000_000_000
        return f"{v:.1f}B" if v != int(v) else f"{int(v)}B"
    if n >= 1_000_000:
        v = n / 1_000_000
        return f"{v:.1f}M" if v != int(v) else f"{int(v)}M"
    if n >= 1_000:
        v = n / 1_000
        return f"{v:.1f}K" if v != int(v) else f"{int(v)}K"
    return str(n)


def _level_of(value: int, thresholds: List[int]) -> int:
    """按分位阈值定色阶（0 = 无数据）"""
    if value <= 0:
        return 0
    for i, t in enumerate(thresholds):
        if value <= t:
            return i + 1
    return len(thresholds) + 1


def _thresholds(totals: List[int], levels: int = 4) -> List[int]:
    """按分位数取色阶阈值（抗单日尖峰）

    只对有活动的日期取分位（无活动日为 0，会把分位全部压到 0）。
    样本不足时退化为等距切分。
    """
    vals = sorted(t for t in totals if t > 0)
    if not vals:
        return []
    # 需要足够的样本量才让分位数有意义
    if len(vals) < 8:
        step = max(1, vals[-1] // max(1, levels))
        return [step * i for i in range(1, levels + 1)]
    cuts = []
    for i in range(1, levels + 1):
        idx = min(len(vals) - 1, int(round(len(vals) * i / (levels + 1))) - 1)
        cuts.append(vals[max(0, idx)])
    # 去重 + 保序（大量同日同量级时分位可能重复）
    out: List[int] = []
    for c in cuts:
        if not out or c > out[-1]:
            out.append(c)
    return out


# ── 热力图几何 ────────────────────────────────────────────


def _heatmap_cells(daily: Dict[str, list], end: date, days: int) -> Tuple[List[List[dict]], List[Tuple[int, str]]]:
    """生成热力图格子矩阵（按周分列）

    Returns:
        (weeks, month_labels)
        - weeks: [[7 个格子 dict], ...]，每周从周一开始（ISO 惯例）
        - month_labels: [(列索引, "10月")]
    """
    # 起点回退到 days 之前最近的周一，让首列从周一开始
    start = end - timedelta(days=days - 1)
    grid_start = start - timedelta(days=start.weekday())

    weeks: List[List[dict]] = []
    month_labels: List[Tuple[int, str]] = []
    cur = grid_start
    last_month = None
    while cur <= end:
        # 月标签：每月第一个进入窗口的列打一次标
        if last_month is None or cur.month != last_month:
            month_labels.append((len(weeks), f"{cur.month}月"))
            last_month = cur.month
        col = []
        for _ in range(7):
            d = cur.isoformat()
            in_range = start <= cur <= end
            slot = daily.get(d) if in_range else None
            if in_range and slot:
                total = slot[0] + slot[1]
                req = slot[2]
            else:
                total = 0
                req = 0
            col.append({"date": d, "total": total, "requests": req, "in_range": in_range})
            cur += timedelta(days=1)
        weeks.append(col)
    return weeks, month_labels


def _month_label_spans(labels: List[Tuple[int, str]], n_cols: int) -> List[str]:
    """月标签行：每个标签占「本月起始周 → 下月起始周」的比例宽度

    纯 CSS 实现，不依赖容器宽度（render_func 产出静态 HTML，卡片宽度运行时才定）：
    每个标签独占一段 flex 宽度，空间由布局保证，窄容器下相邻标签不会压字。

    宽窄两态：数字与「月」后缀分两个 span，窄容器（media query ≤560px）隐藏后缀，
    只留「10」这样的两字符，避免「10月11月」粘连。
    """
    spans: List[str] = []
    for i, (idx, text) in enumerate(labels):
        end = labels[i + 1][0] if i + 1 < len(labels) else n_cols
        grow = max(1, end - idx)
        num = text.removesuffix("月")
        spans.append(
            f'<span class="tu-month" style="flex:{grow} 1 0;">'
            f'{html.escape(num)}<span class="tu-month-suffix">月</span></span>'
        )
    return spans


def _render_heatmap(daily: Dict[str, list], end: date, days: int, p: dict) -> str:
    """GitHub 风格年度热力图（HTML flex 网格，非 SVG / 非 echarts）

    自适应：格子用「宽度自适应 + padding-bottom:100%」构成正方形（Chromium 83
    不支持 aspect-ratio），列宽 flex:1 1 0 均分容器 → 窗口任意宽度下都不横向
    溢出（卡片宽度是动态的：主程序按 parent_width - 20 算）。

    tooltip：走 `data-tip` + CSS `::after content:attr(data-tip)`，不用原生
    `title` —— 原生 tooltip 由 OS 绘制，浅色下是黑底 + 系统默认大字号，
    样式完全不可控（Chromium 83 无 `::-webkit-tooltip` 可用）。
    """
    weeks, month_labels = _heatmap_cells(daily, end, days)
    thresholds = _thresholds([c["total"] for w in weeks for c in w if c["in_range"]], 4)
    n_cols = max(1, len(weeks))

    label_html = '<div class="tu-months">' + "".join(_month_label_spans(month_labels, n_cols)) + "</div>"

    # 格子矩阵：每列一个 flex 列（周一起共 7 格）
    cells_html: List[str] = []
    for col in weeks:
        cells_html.append('<div class="tu-week">')
        for c in col:
            lvl = _level_of(c["total"], thresholds) if c["in_range"] else 0
            color = p["empty"] if lvl == 0 else p["levels"][min(lvl, len(p["levels"])) - 1]
            tip = f"{c['date']} · 总 {_fmt_k(c['total'])} · {c['requests']} 次请求"
            cells_html.append(
                f'<span class="tu-cell" data-tip="{html.escape(tip, quote=True)}" '
                f'style="background:{color};"></span>'
            )
        cells_html.append("</div>")

    legend_w = 10
    return (
        '<div class="tu-heat">'
        + label_html
        + '<div class="tu-grid">'
        + "".join(cells_html)
        + "</div>"
        '<div class="tu-legend">'
        '<span class="tu-legend-label">少</span>'
        + "".join(
            f'<span class="tu-cell tu-legend-cell" style="width:{legend_w}px;'
            f'height:{legend_w}px;margin-left:2px;background:{c};"></span>'
            for c in [p["empty"]] + p["levels"]
        )
        + '<span class="tu-legend-label">多</span>'
        "</div></div>"
    )


# ── 指标区 ────────────────────────────────────────────────


def _render_metrics(summary: dict, p: dict) -> str:
    """30 天四指标：总 Token / 输入 Token / 输出 Token / 请求次数"""
    items = [
        ("总 Token", _fmt_k(summary["total"])),
        ("输入 Token", _fmt_k(summary["input"])),
        ("输出 Token", _fmt_k(summary["output"])),
        ("请求次数", f"{summary['requests']:,}"),
    ]
    cells = []
    for label, value in items:
        cells.append(
            f'<div class="tu-metric">'
            f'<div class="tu-metric-label">{html.escape(label)}</div>'
            f'<div class="tu-metric-value">{html.escape(value)}</div>'
            f"</div>"
        )
    return f'<div class="tu-metrics">{"".join(cells)}</div>'


# ── 入口 ──────────────────────────────────────────────────


def _loading_html(is_dark: bool) -> str:
    p = _palette(is_dark)
    return (
        f'<div class="tu-wrap tu-loading" style="color:{p["muted"]};">'
        f'<div style="font-size:{_fs(13)}px; font-weight:600; margin-bottom:4px;">'
        f"🔢 Token 用量</div>"
        f'<div style="font-size:{_fs(12)}px;">正在统计 API 用量…</div>'
        f'<div style="font-size:{_fs(11)}px; margin-top:6px; opacity:0.75;">'
        f"首次需解压会话数据，约 1 秒</div></div>"
    )


def _error_html(err: str, is_dark: bool) -> str:
    p = _palette(is_dark)
    return (
        f'<div class="tu-wrap" style="color:{p["muted"]}; font-size:{_fs(12)}px;">'
        f"⚠️ 用量统计失败：{html.escape(err[:120])}</div>"
    )


def _empty_html(is_dark: bool) -> str:
    p = _palette(is_dark)
    return (
        f'<div class="tu-wrap" style="color:{p["muted"]};">'
        f'<div style="font-size:{_fs(13)}px; font-weight:600; margin-bottom:6px;">🔢 Token 用量</div>'
        f'<div style="font-size:{_fs(12)}px;">暂无 API 用量记录</div>'
        f'<div style="font-size:{_fs(11)}px; margin-top:6px;">'
        f"用支持 usage 返回的模型对话后，这里会出现输入/输出 Token 统计</div></div>"
    )


_CSS_TEMPLATE = """
.tu-wrap { font-family: inherit; padding: 2px 0 4px; }
.tu-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 10px; }
.tu-title { font-size: {fs_title}px; font-weight: 700; color: {text}; }
.tu-refresh { font-size: {fs_small}px; color: {accent}; cursor: pointer; flex-shrink: 0; }
.tu-refresh:hover { text-decoration: underline; }
.tu-panel { border: 1px solid {border}; border-radius: 10px; background: {panel}; padding: 12px 14px 14px; }
.tu-window { font-size: {fs_base}px; color: {muted}; margin-bottom: 12px; }
.tu-metrics { display: flex; margin: 0 -8px; }
.tu-metric { flex: 1 1 0; padding: 0 8px; min-width: 0; }
.tu-metric-label { font-size: {fs_small}px; color: {faint}; white-space: nowrap; }
.tu-metric-value { font-size: {fs_value}px; font-weight: 600; color: {text}; margin-top: 2px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tu-divider { height: 1px; background: {border}; margin: 14px 0 12px; }
.tu-heat-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; }
.tu-heat-title { font-size: {fs_base}px; font-weight: 600; color: {text}; }
.tu-heat-range { font-size: {fs_small}px; color: {muted}; }
.tu-heat { margin-top: 2px; }
.tu-months { display: flex; height: 15px; overflow: hidden; }
.tu-month { font-size: {fs_tiny}px; color: {muted}; white-space: nowrap;
  overflow: hidden; min-width: 0; }
/* 窄容器只留数字：卡片宽度是动态的（parent_width - 20），只能靠视口媒体查询
   近似判断；数字两字符约 12px，中间月跨度 4~5 列在 420px 下约 32px，够放 */
@media (max-width: 560px) { .tu-month-suffix { display: none; } }
.tu-grid { display: flex; }
/* 列宽均分容器；格子用 padding-bottom:100% 撑成正方形（Chromium 83 无 aspect-ratio），
   间距用 margin 实现（Chromium 83 无 flex gap） */
.tu-week { flex: 1 1 0; min-width: 0; margin-right: 2px; }
.tu-cell { display: block; width: 100%; padding-bottom: 100%; border-radius: 2px;
  margin-bottom: 2px; box-sizing: border-box; }
.tu-week:last-child { margin-right: 0; }
.tu-legend { display: flex; align-items: center; justify-content: flex-end; margin-top: 8px; }
.tu-legend-label { font-size: {fs_tiny}px; color: {muted}; margin: 0 3px; }
.tu-legend-cell { width: 10px; height: 10px; padding-bottom: 0; margin-bottom: 0; }
/* tooltip：纯 CSS（::after + attr），不用原生 title —— 原生由 OS 绘制，
   浅色下是黑底 + 系统大字号，样式不可控（Chromium 83 无 ::-webkit-tooltip）。
   配色取自 context-stats 的 echarts tooltip_bg / tooltip_border，两插件观感一致。 */
.tu-cell { position: relative; }
.tu-cell:hover::after {
  content: attr(data-tip);
  position: absolute; bottom: 130%; left: 50%; transform: translateX(-50%);
  background: {tooltip_bg}; border: 1px solid {tooltip_border}; color: {text};
  font-size: {fs_tiny}px; line-height: 1.5; white-space: nowrap;
  padding: 4px 7px; border-radius: 5px; z-index: 20; pointer-events: none;
  box-shadow: 0 2px 6px rgba(0,0,0,0.18);
}
/* 右边缘列的 tooltip 会被容器裁掉，翻到左侧展开 */
.tu-week:nth-last-child(-n+3) .tu-cell:hover::after {
  left: auto; right: 0; transform: none;
}
"""


def _css(is_dark: bool) -> str:
    """填充 CSS 模板（单花括号占位，直接 .format 会与 CSS 自身的大括号冲突）"""
    p = _palette(is_dark)
    out = _CSS_TEMPLATE
    for key, value in (
        ("border", p["border"]),
        ("panel", p["panel"]),
        ("text", p["text"]),
        ("muted", p["muted"]),
        ("faint", p["faint"]),
        ("accent", p["accent"]),
        ("tooltip_bg", p["tooltip_bg"]),
        ("tooltip_border", p["tooltip_border"]),
        ("fs_title", _fs(15)),
        ("fs_value", _fs(19)),
        ("fs_base", _fs(12)),
        ("fs_small", _fs(11)),
        ("fs_tiny", _fs(10)),
    ):
        out = out.replace("{" + key + "}", str(value))
    return out


def render_html(ctx: Optional[dict], data: dict) -> str:
    """数据就绪时渲染完整版式"""
    is_dark = bool(ctx.get("is_dark")) if isinstance(ctx, dict) else False
    p = _palette(is_dark)
    today = date.today()

    daily = data.get("daily") or {}
    has_usage = any(slot[2] > 0 for slot in daily.values())
    if not has_usage:
        return _empty_html(is_dark) + f"<style>{_css(is_dark)}</style>"

    summary = sum_window(daily, _METRIC_DAYS, today)

    return (
        f'<div class="tu-wrap">'
        f'<div class="tu-head">'
        f'<span class="tu-title">🔢 Token 用量</span>'
        f'<span class="context-tag tu-refresh" data-type="{_ACTION_REFRESH}" data-content="refresh">刷新用量</span>'
        f"</div>"
        f'<div class="tu-panel">'
        f'<div class="tu-window">过去 {_METRIC_DAYS} 天 · '
        f"{summary['active_days']} 天有活动 · 覆盖 {data.get('sessions', 0)} 个会话</div>"
        f"{_render_metrics(summary, p)}"
        f'<div class="tu-divider"></div>'
        f'<div class="tu-heat-head">'
        f'<span class="tu-heat-title">每日活动</span>'
        f'<span class="tu-heat-range">过去一年</span>'
        f"</div>"
        f"{_render_heatmap(daily, today, _HEATMAP_DAYS, p)}"
        f"</div></div>"
        f"<style>{_css(is_dark)}</style>"
    )


def render_tab(ctx: Optional[dict] = None) -> str:
    """register_welcome_tab 的 render_func

    Args:
        ctx: 主程序注入的上下文（含 is_dark）
    """
    from . import collector

    is_dark = bool(ctx.get("is_dark")) if isinstance(ctx, dict) else False
    cached = collector.get_cached()
    if cached is not None:
        if cached.get("error"):
            return _error_html(cached["error"], is_dark) + f"<style>{_css(is_dark)}</style>"
        return render_html(ctx, cached)

    # 未命中：起后台采集，本轮先返回加载占位
    collector.get_collector().start()
    return _loading_html(is_dark) + f"<style>{_css(is_dark)}</style>"