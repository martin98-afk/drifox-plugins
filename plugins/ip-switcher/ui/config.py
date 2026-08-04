# -*- coding: utf-8 -*-
"""ip-switcher 配置 — 存于 user-custom 插件目录（随云端备份恢复）

路径：.drifox/plugins/user-custom/ip-switcher/ip-switcher.json
"""

import json
import threading
from pathlib import Path
from typing import Any, Dict

from loguru import logger

# 默认配置（与设计文档 §9 一致）
DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "whitelist_models": [],
    "whitelist_base_urls": [],
    "proxy_pool_port": 8082,
    "retry_limit": 3,
    "retry_backoff_seconds": 2,
    "auto_switch": True,
    "switch_fail_threshold": 3,
}


def _get_user_custom_dir() -> Path:
    """定位 user-custom 插件目录（随云端备份恢复）"""
    # 优先环境变量（测试注入）
    env = __import__("os").environ.get("IP_SWITCHER_CUSTOM_DIR")
    if env:
        return Path(env)
    # 开发环境：项目根/.drifox/plugins/user-custom
    # 打包环境：~/.drifox/plugins/user-custom
    import sys

    if not hasattr(sys, "_MEIPASS") and not getattr(sys, "frozen", False):
        return Path(".drifox") / "plugins" / "user-custom"
    return Path.home() / ".drifox" / "plugins" / "user-custom"


class ConfigStore:
    """ip-switcher 配置存储（线程安全 + 原子写）"""

    _lock = threading.RLock()

    def __init__(self, path: Path | None = None):
        self.path = path or (
            _get_user_custom_dir() / "ip-switcher" / "ip-switcher.json"
        )
        self._data: Dict[str, Any] = dict(DEFAULT_CONFIG)
        self.load()

    def load(self) -> None:
        """从磁盘加载，与默认值合并（缺字段补默认）"""
        try:
            if self.path.exists():
                with self.path.open("r", encoding="utf-8") as f:
                    saved = json.load(f)
                if isinstance(saved, dict):
                    merged = dict(DEFAULT_CONFIG)
                    merged.update(
                        {k: v for k, v in saved.items() if k in DEFAULT_CONFIG}
                    )
                    with self._lock:
                        self._data = merged
                    return
        except (OSError, ValueError) as e:
            logger.warning(f"[ip-switcher] 配置加载失败，使用默认值: {e}")
        with self._lock:
            self._data = dict(DEFAULT_CONFIG)

    def save(self) -> None:
        """原子写回磁盘（先写 tmp 再 rename）"""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            tmp.replace(self.path)
        except OSError as e:
            logger.error(f"[ip-switcher] 配置保存失败: {e}")

    # ── 读取 ──

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def get_all(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._data)

    # ── 写入 ──

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
        self.save()

    def update(self, changes: Dict[str, Any]) -> None:
        with self._lock:
            for k, v in changes.items():
                if k in DEFAULT_CONFIG:
                    self._data[k] = v
        self.save()

    # ── 白名单快捷方法 ──

    def is_whitelisted_model(self, model: str) -> bool:
        """模型名命中白名单"""
        if not model:
            return False
        with self._lock:
            return model in self._data.get("whitelist_models", [])

    def is_whitelisted_base_url(self, base_url: str) -> bool:
        """API 地址命中白名单（精确匹配，容错去掉尾部斜杠）"""
        if not base_url:
            return False
        norm = base_url.rstrip("/")
        with self._lock:
            return any(
                str(u).rstrip("/") == norm
                for u in self._data.get("whitelist_base_urls", [])
            )


# 模块级单例（热重载时重建）
_store: ConfigStore | None = None


def get_config() -> ConfigStore:
    """获取全局配置单例"""
    global _store
    if _store is None:
        _store = ConfigStore()
    return _store


def reset_config_for_test(path: Path) -> ConfigStore:
    """测试辅助：重置单例指向指定路径"""
    global _store
    _store = ConfigStore(path)
    return _store
