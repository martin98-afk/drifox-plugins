# -*- coding: utf-8 -*-
"""BuildSystemPrompt Hook —— 把「上下文洞察偏好」里的系统提示前缀/后缀注入。

只读插件自己的 config.json（由宿主设置卡写入），不 import 主程序模块。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_PLUGIN = "context-insight"


def _data_root() -> Path:
    env_dir = os.environ.get("DRIFOX_DATA_DIR")
    candidates = []
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.extend(
        [
            Path(".drifox"),
            Path.home() / ".drifox",
            Path.home() / "Library" / "Application Support" / "Drifox" / ".drifox",
        ]
    )
    for root in candidates:
        if (root / "plugins").exists() or (root / "plugin_data").exists():
            return root
    return Path.home() / ".drifox"


def _read_config() -> dict:
    path = _data_root() / "plugin_data" / _PLUGIN / "config.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _read(key: str) -> str:
    value = _read_config().get(key)
    return str(value or "").strip()


def hook(event: str, context: dict) -> str:
    """返回注入块；无配置时返回空串（宿主会跳过空输出）。"""
    if event != "BuildSystemPrompt":
        return ""
    prefix = _read("system_prompt_prefix")
    suffix = _read("system_prompt_suffix")
    if not prefix and not suffix:
        return ""
    parts = ["<context_insight_affix>"]
    if prefix:
        parts.append("<prefix>\n" + prefix + "\n</prefix>")
    if suffix:
        parts.append("<suffix>\n" + suffix + "\n</suffix>")
    parts.append("</context_insight_affix>")
    return "\n".join(parts)
