# -*- coding: utf-8 -*-
"""plugin-marketplace 桥接 — 复用官方市场插件的数据源与安装器

做法：把市场插件的 ui 目录注册为独立包（不执行其 __init__，避免拉起
cards.py 的重依赖），子模块交给 import 机制按需加载。独立包名 + sys.modules
缓存保证：不依赖市场插件自身的加载时序，热重载也不会重复加载多份。

复用能力：
- data.get_marketplace().list_plugins()  市场数据（1h 文件缓存 + 多源合并 + 失败回退）
- installer.get_installer()               已安装扫描 / install()（source 识别 + deps + 热重载触发）
"""

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

_BRIDGE_PKG = "mkt_reuse_bridge"
_MARKETPLACE_DIR = "plugin-marketplace"


def _locate_marketplace_ui() -> Optional[Path]:
    """定位 plugin-marketplace 的 ui 目录（系统插件根 plugins/ 下）"""
    for base in Path(__file__).resolve().parents:
        cand = base / "plugins" / _MARKETPLACE_DIR / "ui"
        if (cand / "__init__.py").exists():
            return cand
    # PyInstaller 打包：系统插件随解包目录
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        cand = Path(meipass) / "plugins" / _MARKETPLACE_DIR / "ui"
        if (cand / "__init__.py").exists():
            return cand
    return None


def _ensure_bridge() -> bool:
    """注册桥接包（幂等）。仅注册包本体，不执行市场插件的 __init__"""
    if _BRIDGE_PKG in sys.modules:
        return True
    ui_dir = _locate_marketplace_ui()
    if ui_dir is None:
        logger.warning(f"[{_BRIDGE_PKG}] 未找到 {_MARKETPLACE_DIR} 插件目录")
        return False
    spec = importlib.util.spec_from_file_location(
        _BRIDGE_PKG,
        ui_dir / "__init__.py",
        submodule_search_locations=[str(ui_dir)],
    )
    if spec is None or spec.loader is None:
        return False
    module = importlib.util.module_from_spec(spec)
    sys.modules[_BRIDGE_PKG] = module
    return True


def list_marketplace_plugins() -> List[Dict[str, Any]]:
    """市场全量插件列表（含 downloads / source / version）"""
    try:
        if not _ensure_bridge():
            return []
        data = importlib.import_module(f"{_BRIDGE_PKG}.data")
        return data.get_marketplace().list_plugins()
    except Exception as e:
        logger.warning(f"[{_BRIDGE_PKG}] 市场数据获取失败: {e}")
        return []


def get_bridge_installer() -> Optional[Any]:
    """市场插件安装器单例（已安装扫描 / install）"""
    try:
        if not _ensure_bridge():
            return None
        installer_mod = importlib.import_module(f"{_BRIDGE_PKG}.installer")
        return installer_mod.get_installer()
    except Exception as e:
        logger.warning(f"[{_BRIDGE_PKG}] 安装器获取失败: {e}")
        return None


def resolve_icon_urls(meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """市场 meta → 图标 URL（{"light": url|候选list, "dark": url|候选list}）

    复用市场插件的 resolve_remote_icon_urls（GitHub raw + icon 字段兼容两套规范）。
    """
    try:
        if not _ensure_bridge():
            return None
        avatar = importlib.import_module(f"{_BRIDGE_PKG}._squircle_avatar")
        return avatar.resolve_remote_icon_urls(meta)
    except Exception as e:
        logger.warning(f"[{_BRIDGE_PKG}] icon URL 解析失败: {e}")
        return None
