# -*- coding: utf-8 -*-
"""pytest 配置：从文件路径加载 ip-switcher 插件模块

插件目录名带连字符（plugins/ip-switcher/），无法用标准 import 导入。
与 DriFox 实际插件加载方式一致（importlib 从文件路径加载，如
browser 插件的 ui_plugin_browser.* 前缀），测试同样走 importlib。

提供 sys.modules 中的模块别名：
- ip_switcher_config   → plugins/ip-switcher/ui/config.py
- ip_switcher_state    → plugins/ip-switcher/ui/state.py
- ip_switcher_proxy_pool → plugins/ip-switcher/ui/proxy_pool.py
- ip_switcher_redirect → plugins/ip-switcher/ui/ip_redirect.py

加载失败（CI 轻量环境缺 PyQt5 / 三方包）不打断收集：
对应测试文件按「别名是否在 sys.modules」模块级 skip。
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

def _try_load(name: str, file_name: str) -> bool:
    """加载失败（缺依赖）返回 False 而非抛错，保证 pytest 可收集其余测试"""
    if name in sys.modules:
        return True
    try:
        _load_module(name, file_name)
        return True
    except ImportError:
        # 清掉 exec 半程留下的空壳模块，否则「别名存在但为空」会骗过守卫判断
        sys.modules.pop(name, None)
        return False

# 加载插件模块（幂等：热加载时跳过已注册的）
_try_load("ip_switcher_config", "config.py")
_try_load("ip_switcher_state", "state.py")

# ip_redirect.py 需要先加载 config/state/proxy_pool（同目录），把 ui 目录加入 sys.path
if str(_UI_DIR) not in sys.path:
    sys.path.insert(0, str(_UI_DIR))
_try_load("ip_switcher_redirect", "ip_redirect.py")
_try_load("ip_switcher_proxy_pool", "proxy_pool.py")
