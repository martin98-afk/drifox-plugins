# -*- coding: utf-8 -*-
"""project-dashboard UI 组件入口 — 欢迎卡片「📊 项目看板」tab

render_func 返回 markdown 片段（概要行 + ```echarts 代码块），
经欢迎卡片 markdown → CodeWebViewer(QWebEngineView) 管线渲染，
与 context-stats 插件同款模式：无 iframe、无独立 HTML 文件。

数据采集全部异步（QThread）：首次打开显示「加载中」占位，
后台采集完成自动重渲染欢迎卡片，不阻塞 UI 主线程。
"""

import sys
from pathlib import Path

from loguru import logger


def _get_project_root() -> str:
    """获取当前项目 git 根（返回 git toplevel，保证是 git 仓库）

    候选链（逐个用 find_git_root 验证，返回第一个有效 git 根）：
    1. 活跃窗口 provider 的 project_root
    2. 遍历全部窗口 provider（主程序 welcome tab 渲染时不传 project_root，
       且活跃窗口可能在多窗口/欢迎卡片场景下解析失败）
    3. 全局兼容 provider
    全部无效返回空串（调用方显示友好提示，不启动采集）。

    【修复】不再用 os.getcwd() 兜底：软件启动目录（源码根/exe 目录）
    本身可能是 git 仓库（如 D:/work/DriFox），会把启动目录误当项目根展示其 git 信息。
    """
    candidates: list = []
    try:
        from app.plugins.registries.ui_plugin_registry import UIPluginRegistry

        reg = UIPluginRegistry.get_instance()
        # 1. 活跃窗口
        provider = reg._resolve_active_window_provider()
        if provider is not None:
            try:
                root = provider().get("project_root")
                if root:
                    candidates.append(root)
            except Exception:
                pass
        # 2. 全部窗口 provider（欢迎卡片可能渲染在非活跃窗口/初始阶段）
        for p in list(getattr(reg, "_context_providers", {}).values()):
            try:
                root = p().get("project_root")
                if root:
                    candidates.append(root)
            except Exception:
                pass
        # 3. 全局兼容 provider
        gp = getattr(reg, "_context_provider", None)
        if gp is not None:
            try:
                root = gp().get("project_root")
                if root:
                    candidates.append(root)
            except Exception:
                pass
    except Exception:
        pass
    # 【修复】移除 os.getcwd() 兜底：软件启动目录（源码根/exe 目录）本身可能是
    # git 仓库（如 D:/work/DriFox），会把启动目录误当项目根展示其 git 信息。
    # 全部候选无效时返回空串，由调用方显示"未检测到 git 项目"友好提示。
    seen = set()
    for cand in candidates:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        try:
            from dashboard import find_git_root

            git_root = find_git_root(cand)
            if git_root:
                return git_root
        except Exception:
            pass
    return ""


def _render_welcome_tab(ctx: dict = None) -> str:
    """welcome tab render_func：概要行 + echarts 代码块

    - 缓存命中：直接返回已采集数据的图表
    - 未命中：返回「加载中」占位 + 启动后台采集（完成后自动重渲染）
    """
    is_dark = ctx.get("is_dark") if isinstance(ctx, dict) else None
    if is_dark is None:
        is_dark = True  # DriFox 默认深色主题

    root = _get_project_root()
    if not root:
        # 候选链全部无效（registry 未就绪 / 无任何窗口提供项目）→ 不采集，下次渲染重试
        return "> ⚠️ 未检测到 git 项目，请在对话窗口打开项目后重试\n"

    from collector import build_cache_key, get_collector

    collector = get_collector()
    cache_key = build_cache_key(root)
    data = collector.get_cached(cache_key)

    if data is None:
        # 未命中：启动后台采集，先显示加载占位
        collector.start(root, is_dark, cache_key)
        return "📊 正在采集项目数据…\n\n*首次生成需数秒，完成后自动显示*"

    if data.get("error"):
        return f"> ⚠️ {data['error']}\n"

    # 概要行
    import json

    from dashboard import build_options

    repo = data.get("repo_name", "")
    branch = data.get("branch", "")
    generated = data.get("generated_at", "")
    total = data.get("total_commits", 0)
    summary = f"**{repo}** · `{branch}` · 生成于 {generated} · 近 30 天 **{total}** commits"

    # 2 个 echarts 代码块（双 grid 合并，各 400px）
    options = build_options(data, is_dark)
    parts = [summary, ""]
    for opt in options:
        parts.append("```echarts")
        parts.append(json.dumps(opt, ensure_ascii=False))
        parts.append("```")
        parts.append("")
    return "\n".join(parts)


def register_ui(registry):
    """注册 project-dashboard 的 UI 组件"""
    # 清理旧子模块缓存（热重载兼容）
    prefix = "ui_plugin_project_dashboard."
    stale = [k for k in sys.modules if k.startswith(prefix)]
    for k in stale:
        del sys.modules[k]

    # 确保 ui 目录在 sys.path（相对导入 dashboard / async）
    ui_dir = str(Path(__file__).resolve().parent)
    if ui_dir not in sys.path:
        sys.path.insert(0, ui_dir)

    registry.register_welcome_tab(
        plugin_name="project-dashboard",
        mode_key="project-dashboard",
        label="📊 项目看板",
        render_func=_render_welcome_tab,
        priority=0,
    )
    logger.info("[project-dashboard] UI components registered")
