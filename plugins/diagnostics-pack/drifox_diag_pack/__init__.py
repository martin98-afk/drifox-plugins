# -*- coding: utf-8 -*-
"""diagnostics-pack 核心：采集 → 脱敏 → 打包。

宿主侧入口（tools / ui）只负责解析数据目录、拿插件启用状态和展示结果，
这里保持纯标准库实现，便于脱离宿主单测。
"""
from __future__ import annotations

from .pack import DEFAULT_KEEP_RUNS, DEFAULT_MAX_MB, build_pack

__all__ = ["build_pack", "DEFAULT_KEEP_RUNS", "DEFAULT_MAX_MB"]
