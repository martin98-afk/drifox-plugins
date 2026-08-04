# -*- coding: utf-8 -*-
"""pytest 配置：从文件路径加载 ip-switcher 插件模块

插件目录名带连字符（plugins/ip-switcher/），无法用标准 import 导入。
与 DriFox 实际插件加载方式一致（importlib 从文件路径加载，如
browser 插件的 ui_plugin_browser.* 前缀），测试同样走 importlib。

提供 sys.modules 中的模块别名：
- ip_switcher_config   → plugins/ip-switcher/ui/config.py
- ip_switcher_state    → plugins/ip-switcher/ui/state.py
- ip_switcher_proxy_pool → plugins/ip-switcher/ui/proxy_pool.py
"""

import importlib.util
import sys
from pathlib import Path

_UI_DIR = Path(__file__).resolve().parent.parent / "plugins" / "ip-switcher" / "ui"


def _load_module(name: str, file_name: str):
    """从文件路径加载模块并注册到 sys.modules"""
    path = _UI_DIR / file_name
    if not path.exists():
        raise FileNotFoundError(f"模块文件不存在: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# 加载插件模块（幂等：热加载时跳过已注册的）
if "ip_switcher_config" not in sys.modules:
    _load_module("ip_switcher_config", "config.py")
if "ip_switcher_state" not in sys.modules:
    _load_module("ip_switcher_state", "state.py")

# ip_redirect.py 需要先加载 config/state/proxy_pool（同目录），把 ui 目录加入 sys.path
if "ip_switcher_redirect" not in sys.modules:
    # 确保同目录的 config/state/proxy_pool 可被绝对导入找到
    if str(_UI_DIR) not in sys.path:
        sys.path.insert(0, str(_UI_DIR))
    _load_module("ip_switcher_redirect", "ip_redirect.py")
if "ip_switcher_proxy_pool" not in sys.modules:
    _load_module("ip_switcher_proxy_pool", "proxy_pool.py")