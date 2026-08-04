# -*- coding: utf-8 -*-
"""ip-switcher 配置 — 存于 user-custom 插件目录（随云端备份恢复）

路径：.drifox/plugins/user-custom/ip-switcher/ip-switcher.json

系统模型自动发现：
- 首次运行时若白名单为空，自动从 DriFox 主配置（.drifox/app.config）
  的 LLM.SavedProviders 中发现"免费"provider（名字含 免费/free 或
  模型名含 -free），将其模型列表 + API_URL 自动填入白名单，实现
  "装上就能用"，无需手改配置。
"""

import json
import threading
from pathlib import Path
from typing import Any, Dict, List

from loguru import logger

# 默认配置（与设计文档 §9 一致）
DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
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


# ── 系统模型自动发现 ──────────────────────────────────────


def _get_system_config_path() -> Path:
    """定位 DriFox 主应用配置（.drifox/app.config）"""
    env = __import__("os").environ.get("IP_SWITCHER_SYSTEM_CONFIG")
    if env:
        return Path(env)
    import sys

    if not hasattr(sys, "_MEIPASS") and not getattr(sys, "frozen", False):
        return Path(".drifox") / "app.config"
    return Path.home() / ".drifox" / "app.config"


def discover_system_providers() -> List[Dict[str, Any]]:
    """扫描 DriFox 主配置的 LLM.SavedProviders，返回 provider 信息列表

    返回：[{name, provider_name, url, models: [str, ...], is_free: bool}]
    is_free：provider 名含 免费/free 或任一模型名含 -free 判定为免费。
    读取失败 / 配置不存在 → 返回空列表（不抛异常）。
    """
    cfg_path = _get_system_config_path()
    if not cfg_path.exists():
        return []
    try:
        with cfg_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        providers = (data.get("LLM", {}) or {}).get("SavedProviders", {}) or {}
        result: List[Dict[str, Any]] = []
        for cid, p in providers.items():
            if not isinstance(p, dict):
                continue
            name = p.get("name") or p.get("provider_name") or cid
            url = p.get("API_URL") or ""
            models = list(p.get("模型列表") or []) or (
                [p.get("模型名称")] if p.get("模型名称") else []
            )
            is_free = ("免费" in str(name)) or ("free" in str(name).lower()) or any(
                "-free" in str(m).lower() for m in models
            )
            result.append(
                {
                    "name": name,
                    "provider_name": p.get("provider_name") or name,
                    "url": url,
                    "models": models,
                    "is_free": is_free,
                }
            )
        return result
    except (OSError, ValueError) as e:
        logger.debug(f"[ip-switcher] 系统配置读取失败: {e}")
        return []


def discover_opencode_free_provider() -> Optional[Dict[str, Any]]:
    """发现系统自带的 opencode 免费模型 provider（软件初始化内置）

    判定：provider name 同时包含 "opencode"（忽略大小写）和 "免费"。
    命中则返回 {name, url, models: [...]}，否则返回 None。
    """
    providers = discover_system_providers()
    for p in providers:
        name = str(p.get("name") or "")
        if "opencode" in name.lower() and "免费" in name:
            return {
                "name": name,
                "url": p.get("url", ""),
                "models": list(p.get("models", []) or []),
            }
    return None


def get_opencode_free_models() -> List[str]:
    """系统内置 opencode 免费模型列表（供卡片展示）"""
    p = discover_opencode_free_provider()
    if not p:
        return []
    return p["models"]


def get_opencode_free_urls() -> List[str]:
    """系统内置 opencode 免费 API 地址列表"""
    p = discover_opencode_free_provider()
    if not p:
        return []
    return [p["url"]] if p.get("url") else []


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

    # ── opencode 免费模型判定（内置，无需用户配置） ──

    def is_opencode_free_model(self, model: str) -> bool:
        """模型名是否属于系统内置 opencode 免费模型"""
        if not model:
            return False
        with self._lock:
            return model in get_opencode_free_models()

    def is_opencode_free_base_url(self, base_url: str) -> bool:
        """API 地址是否匹配系统内置 opencode 免费 API（容错尾部斜杠）"""
        if not base_url:
            return False
        norm = base_url.rstrip("/")
        with self._lock:
            return any(str(u).rstrip("/") == norm for u in get_opencode_free_urls())


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
