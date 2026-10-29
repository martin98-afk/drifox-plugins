# -*- coding: utf-8 -*-
"""数据目录解析与布局。

值班产物（唯一数据根，jimeng 1.2.0 范式）：
<app_data>/plugin_data/bili-scroll/   → out/ seen.tsv digest/ 调度状态
纪律：宿主进程内取路径一律走能力池（storage.data_dir）或 tool_ctx.env
（app_data_dir），禁止复刻宿主目录探测逻辑。

MCP 子进程侧（宿主进程外，拿不到能力池）凭证与 duty 隔离区落在插件
安装目录 data/ 下（bootstrap 以 __file__ 推 PLUGIN_ROOT，重装即弃、
重新扫码即可）——与值班产物是两棵树，互不干扰。
"""
from __future__ import annotations

from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_NAME = "bili-scroll"


def plugin_data_root(app_data: str | Path | None = None) -> Path | None:
    """<app_data>/plugin_data/bili-scroll/；不存在则创建。

    app_data 显式传（tool_ctx.env.app_data_dir，可能相对路径须 resolve）；
    未传走能力池（storage.data_dir）。全失败返回 None。
    """
    base: Path | None = None
    if app_data:
        base = Path(str(app_data)).resolve()
    else:
        try:
            from app.plugins.capabilities.resolve import caps_for

            root = caps_for("storage.data_dir")
            base = Path(str(root)).resolve() if root else None
        except Exception:
            base = None
    if not base:
        return None
    out = base / "plugin_data" / PLUGIN_NAME
    out.mkdir(parents=True, exist_ok=True)
    return out
