# -*- coding: utf-8 -*-
"""工具 schema 注册表：bili_tools 注册时填充，round_runner 组值班轮名单时取用。

放 core 而不是 tools/，避免 round_runner 反向 import tools 子目录
（tools/*.py 由宿主 loader 独立加载，不是常规包）。
"""
from __future__ import annotations

from typing import Any, Dict

TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {}
