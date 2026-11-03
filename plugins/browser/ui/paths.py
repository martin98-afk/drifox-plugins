# -*- coding: utf-8 -*-
"""数据目录 — 用户数据统一落 <app_data>/plugin_data/browser/

纪律（与 jimeng 1.2.0 / bili-scroll 同款）：插件安装目录在升级时会被整体
替换，书签、历史、下载记录、拦截配置、登录态 profile、拾取截图都不能留在
里面，否则更新即丢。落点统一走能力池 ``storage.data_dir``（返回 app_data
根），再自拼 ``plugin_data/browser/``。

旧版路径 ``~/.drifox/plugins/browser/data/``（≤v1.5.2）在首次访问时自动迁移：
复制不删，旧目录留作回滚；全部成功才写迁移标记，避免被文件锁打断后半途而废。

⚠️ 本模块不做任何 Qt / app 内部模块的顶层导入：能力池解析失败时回退
``~/.drifox``，保证 MCP 自动化与纯逻辑测试里也能跑通。
"""

import shutil
from pathlib import Path
from typing import Optional

from loguru import logger

PLUGIN_NAME = "browser"

# 旧版数据目录（随插件安装目录，升级即丢）
LEGACY_DATA_DIR = Path.home() / ".drifox" / "plugins" / "browser" / "data"

_MIGRATION_MARKER = ".migrated-from-plugin-dir"

# 需要迁移的旧数据；cache 可再生，不迁
_LEGACY_ITEMS = ("browser.db", "browser-redirect.json", "picks", "screenshots", "profile")

_cached_dir: Optional[Path] = None


def _app_data_root() -> Path:
    """app_data 根：能力池 storage.data_dir → 回退 ~/.drifox"""
    try:
        from app.plugins.capabilities.resolve import caps_for

        root = caps_for("storage.data_dir")
        if root:
            return Path(str(root)).resolve()
    except Exception:
        pass
    return Path.home() / ".drifox"


def data_dir() -> Path:
    """<app_data>/plugin_data/browser/（首次调用创建目录并迁移旧数据）"""
    global _cached_dir
    if _cached_dir is not None:
        return _cached_dir
    out = _app_data_root() / "plugin_data" / PLUGIN_NAME
    out.mkdir(parents=True, exist_ok=True)
    _migrate_legacy(out)
    _cached_dir = out
    return out


def profile_dir() -> Path:
    return data_dir() / "profile"


def cache_dir() -> Path:
    return data_dir() / "cache"


def picks_dir() -> Path:
    return data_dir() / "picks"


def screenshots_dir() -> Path:
    return data_dir() / "screenshots"


def db_path() -> Path:
    return data_dir() / "browser.db"


def redirect_config_path() -> Path:
    return data_dir() / "browser-redirect.json"


def _migrate_legacy(target: Path) -> None:
    """旧版插件目录数据 → plugin_data（复制不删，幂等）"""
    if (target / _MIGRATION_MARKER).exists():
        return
    if not LEGACY_DATA_DIR.is_dir():
        return

    failed = False
    for name in _LEGACY_ITEMS:
        src = LEGACY_DATA_DIR / name
        dst = target / name
        if not src.exists():
            continue
        if dst.exists() and not (dst.is_dir() and not any(dst.iterdir())):
            continue  # 目标已有内容，不覆盖
        try:
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
            logger.info(f"[browser-data] 已迁移旧数据: {name} → {dst}")
        except OSError as e:
            failed = True
            logger.warning(f"[browser-data] 迁移 {name} 失败（旧数据保留，下次重试）: {e}")

    if failed:
        return
    try:
        (target / _MIGRATION_MARKER).write_text("1", encoding="utf-8")
    except OSError:
        pass
