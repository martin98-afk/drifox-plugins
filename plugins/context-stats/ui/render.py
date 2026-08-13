# -*- coding: utf-8 -*-
"""渲染层 — 欢迎卡片「📊 用量」tab 的 HTML 片段生成

render_func 返回 markdown 片段（含 ```echarts 代码块），
拼进欢迎卡片 body 后走主程序 markdown 管线渲染：
- ```echarts 代码块 → _wrap_code_blocks_with_copy_button_web
  转成 echarts-container div（data-echarts-json=base64）
- 骨架 JS `if (window.echarts)` → echarts.init 渲染

设计约束：
- 不导入 app.core 或 app.widgets 内部的任何模块
- 主线程同步调用，只做轻量 JSON 组装（数据来自 data.get_stats() 缓存）
- 明暗适配读 ctx["is_dark"]（跟随 Qt 主题），ctx 缺失时回退 OS
- 两曲线合并为单个 echarts 实例（单坐标系 + 双 Y 轴：左 token / 右 消息）
- 数字缩写 8M/1.2k：Python 侧缩放数据 + 字符串模板 formatter（JSON 无法携带函数）
"""

import json
from typing import Optional

from .data import get_stats


# ── 明暗色板 ─────────────────────────────────────────────


def _palette(is_dark: bool) -> dict:
    """按明暗返回 echarts option 色板"""
    if is_dark:
        return {
            "text": "#e6e6e6",
            "text_muted": "#8a8a8a",
            "grid": "rgba(255,255,255,0.12)",
            "split": "rgba(255,255,255,0.08)",
            "accent": "#62a0ea",
            "accent_gradient": ["rgba(98,160,234,0.35)", "rgba(98,160,234,0)"],
            "success": "#50e3c2",
            "tooltip_bg": "rgba(30,34,42,0.92)",
            "tooltip_border": "rgba(98,160,234,0.5)",
        }
    return {
        "text": "#333333",
        "text_muted": "#999999",
        "grid": "rgba(0,0,0,0.10)",
        "split": "rgba(0,0,0,0.06)",
        "accent": "#2878dc",
        "accent_gradient": ["rgba(40,120,220,0.30)", "rgba(40,120,220,0)"],
        "success": "#00a888",
        "tooltip_bg": "rgba(255,255,255,0.96)",
        "tooltip_border": "rgba(40,120,220,0.45)",
    }


def _fmt_k(n: int) -> str:
    """数字缩写：8000000 → '8M'，1234 → '1.2k'（整数去尾 .0）"""
    if n >= 1_000_000:
        v = n / 1_000_000
        return f"{v:.1f}M" if v != int(v) else f"{int(v)}M"
    if n >= 1_000:
        v = n / 1_000
        return f"{v:.1f}k" if v != int(v) else f"{int(v)}k"
    return str(n)


def _scale_unit(values: list) -> tuple:
    """按数据最大值选择显示单位，返回 (缩放因子, 单位后缀)

    8000000 → (1_000_000, 'M')；8000 → (1_000, 'k')；800 → (1, '')
    供 y 轴刻度与 tooltip 共用：数据除以因子后配字符串模板 formatter。
    """
    mx = max(values, default=0)
    if mx >= 1_000_000:
        return 1_000_000, "M"
    if mx >= 1_000:
        return 1_000, "k"
    return 1, ""


def _axis_style(p: dict, show_label: bool) -> dict:
    """xAxis 公共样式"""
    return {
        "type": "category",
        "axisLine": {"lineStyle": {"color": p["split"]}},
        "axisTick": {"show": False},
        "axisLabel": {
            "color": p["text_muted"],
            "fontSize": 11,
            "show": show_label,
        },
    }


def _combined_option(daily_tokens: list, daily_messages: list, p: dict) -> dict:
    """合并图表 — 单坐标系双 Y 轴（左 token 面积图 + 右 消息柱状图）

    单个 echarts 实例、共享 x 轴，两条曲线在同一坐标系：
    - yAxis[0] 左轴：token 用量（line 面积图）
    - yAxis[1] 右轴：消息量（bar 柱状图）
    - 数字缩写：数据在 Python 侧按各自单位缩放（echarts JSON 走 base64 +
      JSON.parse，无法携带 JS 函数），axisLabel/tooltip 用字符串模板补后缀
      （8000000 → 8M / 8000 → 8k）
    """
    days = [label for label, _ in daily_tokens]
    token_vals = [v for _, v in daily_tokens]
    msg_vals = [v for _, v in daily_messages]

    tok_factor, tok_unit = _scale_unit(token_vals)
    msg_factor, msg_unit = _scale_unit(msg_vals)

    return {
        "backgroundColor": "transparent",
        "textStyle": {"fontFamily": "inherit", "color": p["text"]},
        "tooltip": {
            "trigger": "axis",
            "backgroundColor": p["tooltip_bg"],
            "borderColor": p["tooltip_border"],
            "borderWidth": 1,
            "textStyle": {"color": p["text"], "fontSize": 12},
            "axisPointer": {"type": "line", "lineStyle": {"color": p["grid"]}},
            # {a0}/{a1} = series 名，{c0}/{c1} = 缩放后值（已除 tok_factor/msg_factor）
            "formatter": (
                "{b}<br/>{a0}: {c0}"
                + tok_unit
                + " tokens<br/>{a1}: {c1}"
                + msg_unit
                + " 条"
            ),
        },
        "grid": [
            {"left": 10, "right": 16, "top": 34, "bottom": 20, "containLabel": True}
        ],
        "title": [
            {
                "text": "📊 上下文用量 · 消息量",
                "left": 10,
                "top": 6,
                "textStyle": {"fontSize": 12, "color": p["text"], "fontWeight": "bold"},
            }
        ],
        "xAxis": [
            {
                **_axis_style(p, show_label=True),
                "data": days,
                "boundaryGap": False,
            }
        ],
        "yAxis": [
            {
                "type": "value",
                "position": "left",
                "min": 0,
                "splitLine": {"lineStyle": {"color": p["split"]}},
                "axisLabel": {
                    "color": p["text_muted"],
                    "fontSize": 10,
                    "formatter": "{value}" + tok_unit,
                },
            },
            {
                "type": "value",
                "position": "right",
                "min": 0,
                # 右轴关闭网格线，避免与左轴重叠
                "splitLine": {"show": False},
                "axisLabel": {
                    "color": p["text_muted"],
                    "fontSize": 10,
                    "formatter": "{value}" + msg_unit,
                },
            },
        ],
        "series": [
            {
                "name": "Token 用量",
                "type": "line",
                "yAxisIndex": 0,
                "smooth": True,
                "symbol": "circle",
                "symbolSize": 6,
                "showSymbol": False,
                "lineStyle": {"color": p["accent"], "width": 2},
                "itemStyle": {"color": p["accent"]},
                "areaStyle": {
                    "color": {
                        "type": "linear",
                        "x": 0,
                        "y": 0,
                        "x2": 0,
                        "y2": 1,
                        "colorStops": [
                            {"offset": 0, "color": p["accent_gradient"][0]},
                            {"offset": 1, "color": p["accent_gradient"][1]},
                        ],
                    }
                },
                "data": [v / tok_factor for v in token_vals],
            },
            {
                "name": "消息数",
                "type": "bar",
                "yAxisIndex": 1,
                "barWidth": "45%",
                "itemStyle": {"color": p["success"], "borderRadius": [4, 4, 0, 0]},
                "data": [v / msg_factor for v in msg_vals],
            },
        ],
    }


def _build_html(ctx: Optional[dict]) -> str:
    """组装欢迎 tab 的 markdown 片段（含单个合并 echarts 代码块）"""
    data = get_stats()
    if data.get("error"):
        return f"> ⚠️ 用量数据加载失败：{data['error'][:80]}\n"

    # 明暗判断：is_dark is not None 区分「未注入」与「浅色」
    is_dark = ctx.get("is_dark") if isinstance(ctx, dict) else None
    if is_dark is None:
        # ctx 缺失（旧主程序）→ 默认暗色（DriFox 默认深色主题）
        is_dark = True
    p = _palette(is_dark)

    daily_tokens = data.get("daily_tokens", [])
    daily_messages = data.get("daily_messages", [])
    total_tokens = data.get("total_tokens", 0)
    total_messages = data.get("total_messages", 0)

    if not any(v for _, v in daily_tokens) and not any(v for _, v in daily_messages):
        return "📊 暂无会话数据，开始对话后将自动生成用量统计。\n"

    parts = []

    # 概要行（纯 markdown，无 echarts 依赖）
    parts.append(
        f"**近 14 天** · 估算 Token **{_fmt_k(total_tokens)}** · 消息 **{_fmt_k(total_messages)}** 条\n"
    )

    # 单个合并 echarts 实例（上下双面板）
    # separators 压缩 JSON 空白 → 减小 base64 体积与渲染管线处理量
    parts.append(
        "```echarts\n"
        + json.dumps(
            _combined_option(daily_tokens, daily_messages, p),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n```\n"
    )

    return "\n".join(parts)


def render_welcome_tab(ctx: Optional[dict] = None) -> str:
    """register_welcome_tab 的 render_func 实现

    Args:
        ctx: 主程序注入的上下文（含 is_dark），签名必须接收 ctx
    """
    return _build_html(ctx)
