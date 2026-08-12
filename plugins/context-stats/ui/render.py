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
    """数字缩写：1234 → '1.2k'"""
    if n >= 1000000:
        return f"{n / 1000000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def _base_option(p: dict) -> dict:
    """echarts option 公共骨架"""
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
        },
        "grid": {"left": 10, "right": 16, "top": 32, "bottom": 8, "containLabel": True},
        "xAxis": {
            "type": "category",
            "boundaryGap": True,
            "axisLine": {"lineStyle": {"color": p["split"]}},
            "axisTick": {"show": False},
            "axisLabel": {"color": p["text_muted"], "fontSize": 11},
        },
        "yAxis": {
            "type": "value",
            "splitLine": {"lineStyle": {"color": p["split"]}},
            "axisLabel": {
                "color": p["text_muted"],
                "fontSize": 11,
            },
        },
    }


def _token_option(daily_tokens: list, p: dict) -> dict:
    """上下文用量趋势 — 面积图"""
    opt = _base_option(p)
    opt["xAxis"]["data"] = [label for label, _ in daily_tokens]
    opt["xAxis"]["boundaryGap"] = False
    opt["tooltip"]["formatter"] = "{b}<br/>{a}: {c} tokens"
    opt["series"] = [
        {
            "name": "Token 用量",
            "type": "line",
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
            "data": [v for _, v in daily_tokens],
        }
    ]
    return opt


def _message_option(daily_messages: list, p: dict) -> dict:
    """每日消息量趋势 — 柱状图"""
    opt = _base_option(p)
    opt["xAxis"]["data"] = [label for label, _ in daily_messages]
    opt["series"] = [
        {
            "name": "消息数",
            "type": "bar",
            "barWidth": "55%",
            "itemStyle": {
                "color": p["success"],
                "borderRadius": [4, 4, 0, 0],
            },
            "data": [v for _, v in daily_messages],
        }
    ]
    return opt


def _build_html(ctx: Optional[dict]) -> str:
    """组装欢迎 tab 的 markdown 片段（含两个 echarts 代码块）"""
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

    if any(v for _, v in daily_tokens):
        parts.append("### 🔤 上下文用量趋势\n")
        parts.append(
            "```echarts\n"
            + json.dumps(_token_option(daily_tokens, p), ensure_ascii=False)
            + "\n```\n"
        )

    if any(v for _, v in daily_messages):
        parts.append("### 📈 每日消息量趋势\n")
        parts.append(
            "```echarts\n"
            + json.dumps(_message_option(daily_messages, p), ensure_ascii=False)
            + "\n```\n"
        )

    return "\n".join(parts)


def render_welcome_tab(ctx: Optional[dict] = None) -> str:
    """register_welcome_tab 的 render_func 实现

    Args:
        ctx: 主程序注入的上下文（含 is_dark），签名必须接收 ctx
    """
    return _build_html(ctx)
