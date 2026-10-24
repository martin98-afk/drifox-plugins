# -*- coding: utf-8 -*-
"""token-usage UI 组件入口 — 欢迎卡片「🔢 用量」tab

通过 register_welcome_tab 注册为欢迎卡片的新 tab：
- mode_key="token-usage"（避开系统内置 sessions/projects 与其他插件 tab）
- render_func 返回 HTML 片段（全内联样式，无 echarts 依赖）

另注册一个欢迎动作（register_welcome_action）承接页签里「刷新用量」按钮：
HTML 上挂 .context-tag data-type="tu-refresh"，主程序点击后经
dispatch_welcome_action 派发回本插件，丢弃缓存并后台重采。

采集在 QThread 跑：全库解压扫描 sessions.messages（实测 227MB 库 535 会话，
collect 期间 RSS +57.6MB / tracemalloc 瞬态尖峰 774MB，尖峰源 data.collect
的 fetchall 全表加载），主线程同步会卡 UI。首次打开显示「加载中」占位，
采集完成自动重渲染。

预热策略（懒化，#22）：register_ui 不再无条件启动采集（旧实现装机即扫全库，
实测 4.4s 后台占用）——采集由 render_tab 在页签首次打开时触发（缓存未命中
路径自带 start()），没人打开页签就零开销。
"""

import sys

from loguru import logger

_PREFIX = "token-usage."

_ACTION_REFRESH = "tu-refresh"


def _on_refresh(content: str, ctx: dict) -> None:
    """「刷新用量」点击处理：丢弃缓存 + 后台重采 + 通知卡片重渲染"""
    from . import collector

    collector.refresh(force=True)
    logger.info("[token-usage] 手动刷新用量")


def register_ui(registry):
    """注册 token-usage 的 UI 组件（欢迎卡片 tab + 刷新动作）

    热重载兼容：清理 sys.modules 中残留的子模块缓存，
    确保 Python 重新从 .py 源文件编译。
    """
    stale = [k for k in sys.modules if k.startswith(_PREFIX)]
    for k in stale:
        del sys.modules[k]

    from .render import render_tab

    registry.register_welcome_tab(
        plugin_name="token-usage",
        mode_key="token-usage",
        label="🔢 用量",
        render_func=render_tab,
        priority=0,
        metadata={"description": "30 天 Token 四指标 + 一年活动热力图（真实 API usage）"},
    )

    if hasattr(registry, "register_welcome_action"):
        registry.register_welcome_action(
            plugin_name="token-usage",
            action=_ACTION_REFRESH,
            handler=_on_refresh,
        )
    else:
        # 旧主程序无 welcome action 扩展点：页签照常显示，
        # 「刷新用量」按钮点击无响应（缓存 key 含 db mtime，切会话后自动更新）
        logger.warning(
            "[token-usage] 主程序缺少 register_welcome_action 扩展点，"
            "「刷新用量」按钮不可用——请升级并重启 DriFox"
        )

    # 预热已移除（#22 懒化）：采集由 render_tab 在页签首次打开时触发
    # （缓存未命中路径自带 collector.get_collector().start()）。
    # 旧实现注册即后台扫全库（227MB sessions.db 实测 4.4s / RSS +57.6MB /
    # tracemalloc 瞬态尖峰 774MB），用户不打开用量页签时纯属浪费。
    # TODO: 全量扫库改增量扫描（按会话 mtime 只解析新增），成本较高本轮不做。

    logger.info("[token-usage] welcome tab registered (collect on first open)")