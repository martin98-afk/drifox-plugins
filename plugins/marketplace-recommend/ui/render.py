# -*- coding: utf-8 -*-
"""推荐数据获取与渲染 — 复用 plugin-marketplace 的数据源与安装状态

数据策略：
- 市场全量数据（含 downloads）：内存缓存 + TTL，后台线程刷新，渲染永不阻塞
- 已安装状态：每次渲染实时查 installer（安装/卸载后推荐列表即时变化）
"""

import html
import random
import threading
import time
from typing import Any, Dict, List, Optional

from loguru import logger

from . import mkt_bridge


def _fs(size: int) -> int:
    """字号跟随 DriFox 全局 UI 字号设置（与主程序 scale_font_size 同源）"""
    try:
        from app.utils.design_tokens import scale_font_size

        return scale_font_size(size)
    except Exception:
        return size

_PLUGIN_NAME = "marketplace-recommend"
_ACTION_INSTALL = "mkr-install"
_ACTION_SHUFFLE = "mkr-shuffle"

# 热门池大小：downloads 前 N 进入随机池（避免冷门插件霸屏）
_HOT_POOL = 30
# 默认推荐数量：一行 3 个 × 两行 = 每页 6 个
_RECOMMEND_COUNT = 6
# 单行卡片数（flex basis 配套）
_PER_ROW = 3
# 市场数据内存缓存 TTL（秒）
_DATA_TTL = 600

_state_lock = threading.Lock()
_state: Dict[str, Any] = {
    "plugins": None,  # 市场全量插件列表（缓存）
    "fetched_at": 0.0,
    "fetching": False,
}


def _get_marketplace_data() -> List[Dict[str, Any]]:
    """取市场全量插件列表（缓存优先；未就绪返回 []）

    复用 plugin-marketplace 的 MarketplaceData：内部 1h 文件缓存 +
    失败回退，本函数只做内存层缓存避免每次渲染重复 IO。
    """
    with _state_lock:
        if _state["plugins"] is not None and time.time() - _state["fetched_at"] < _DATA_TTL:
            return _state["plugins"]

    def _fetch():
        with _state_lock:
            _state["fetching"] = True
        try:
            plugins = mkt_bridge.list_marketplace_plugins()
            if plugins:
                with _state_lock:
                    _state["plugins"] = plugins
                    _state["fetched_at"] = time.time()
        except Exception as e:
            logger.warning(f"[{_PLUGIN_NAME}] 拉取市场数据失败: {e}")
        finally:
            with _state_lock:
                _state["fetching"] = False

    threading.Thread(target=_fetch, daemon=True, name=f"{_PLUGIN_NAME}-fetch").start()
    return []


def _installed_names() -> set:
    """当前已安装插件名集合（含禁用目录与系统插件，installer 已封装）"""
    try:
        installer = mkt_bridge.get_bridge_installer()
        if installer is None:
            return set()
        return set(installer.get_installed_map().keys())
    except Exception as e:
        logger.warning(f"[{_PLUGIN_NAME}] 扫描已安装插件失败: {e}")
        return set()


def pick_recommendations(count: int = _RECOMMEND_COUNT) -> List[Dict[str, Any]]:
    """挑选推荐插件：未安装 + downloads 热门池随机抽样

    Returns:
        插件 meta 列表；市场数据未就绪时返回 []
    """
    plugins = _get_marketplace_data()
    if not plugins:
        return []
    installed = _installed_names()
    # 有效条目：有名字、有 source、未安装、非系统内置
    candidates = [
        p
        for p in plugins
        if p.get("name") and p.get("source") and p.get("name") not in installed
    ]
    hot = sorted(candidates, key=lambda p: p.get("downloads", 0) or 0, reverse=True)[:_HOT_POOL]
    if not hot:
        return []
    return random.sample(hot, min(count, len(hot)))


def _fmt_downloads(n: int) -> str:
    if n >= 10000:
        return f"{n / 10000:.1f}w"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def _icon_img(meta: Dict[str, Any], is_dark: bool) -> str:
    """插件图标 <img>（远程 raw URL）；无 icon 或加载失败回退 🧩 emoji"""
    urls = mkt_bridge.resolve_icon_urls(meta) or {}
    v = urls.get("dark" if is_dark else "light")
    if isinstance(v, list):
        v = v[0] if v else None
    if not v:
        return "🧩"
    return (
        f'<img src="{html.escape(str(v), quote=True)}" '
        f'style="width:20px; height:20px; flex-shrink:0; border-radius:5px;" '
        f'onerror="this.style.display=\'none\'">'
    )


def render_recommend(ctx: Dict[str, Any]) -> str:
    """欢迎 tab 渲染入口：返回 HTML 片段（拼进欢迎卡片 markdown 管线）

    样式全内联（插件 HTML 拼进 body，模板 <style> 不可依赖）；
    .context-tag 的 data-type 经主程序派发回本插件（见 actions.py）。
    """
    is_dark = bool(ctx.get("is_dark"))
    card_bg = "rgba(255,255,255,0.04)" if is_dark else "rgba(0,0,0,0.03)"
    card_border = "rgba(255,255,255,0.10)" if is_dark else "rgba(0,0,0,0.10)"
    fg = "#e8e8e8" if is_dark else "#1f1f1f"
    muted = "#9a9a9a" if is_dark else "#7a7a7a"
    accent = "#4f9cf9" if is_dark else "#2b7de9"

    picks = pick_recommendations()
    if not picks:
        # 数据未就绪（首次冷缓存后台拉取中）或市场全已安装
        tip = "正在获取市场数据，稍后切回本页签查看…" if _state.get("fetching") else "市场插件均已安装 🎉"
        return (
            f'<div style="color:{muted}; font-size:{_fs(12)}px; padding:8px 2px;">🧩 插件推荐 · {html.escape(tip)}</div>'
        )

    cards: List[str] = []
    for meta in picks:
        name = html.escape(str(meta.get("name", "")))
        desc = html.escape(str(meta.get("description") or meta.get("summary") or "").strip())
        if len(desc) > 90:
            desc = desc[:90] + "…"
        version = html.escape(str(meta.get("version") or "—"))
        dl = _fmt_downloads(int(meta.get("downloads", 0) or 0))
        cards.append(
            f'<div class="context-tag" data-type="{_ACTION_INSTALL}" data-content="{name}" '
            f'style="flex:1 1 calc({100 // _PER_ROW}% - 8px); box-sizing:border-box; cursor:pointer; '
            f"border:1px solid {card_border}; border-radius:10px; padding:9px 11px; background:{card_bg};\">"
            f'<div style="display:flex; align-items:center; gap:14px; font-weight:600; font-size:{_fs(13)}px; color:{fg}; overflow:hidden;">{_icon_img(meta, is_dark)}<span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{name}</span></div>'
            f'<div style="font-size:{_fs(11)}px; color:{muted}; margin-top:3px; line-height:1.5; '
            f'display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden;">{desc}</div>'
            f'<div style="font-size:{_fs(11)}px; color:{accent}; margin-top:5px;">⬇ {dl} 下载 · v{version} · 点击安装</div>'
            f"</div>"
        )

    # 标题行：左侧标题 + 右侧「换一批」（flex space-between 靠右）
    return (
        f'<div style="display:flex; justify-content:space-between; align-items:baseline; padding:2px;">'
        f'<span style="color:{muted}; font-size:{_fs(12)}px;">🧩 插件推荐 · 来自插件市场</span>'
        f'<span class="context-tag" data-type="{_ACTION_SHUFFLE}" data-content="shuffle" '
        f'style="cursor:pointer; font-size:{_fs(11)}px; color:{accent}; flex-shrink:0;">↻ 换一批</span>'
        f"</div>"
        f'<div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:6px;">{"".join(cards)}</div>'
    )
