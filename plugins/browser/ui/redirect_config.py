# -*- coding: utf-8 -*-
"""浏览器拦截配置 — 控制系统软件打开浏览器/URL/HTML 的拦截行为

配置存储：~/.drifox/plugins/browser/data/browser-redirect.json
（与收藏/历史/下载 browser.db 同数据目录，随 profile 一并保留）

配置项（DEFAULT_CONFIG 说明）：
- enabled         全局总开关：False 时所有拦截全部失效（走原系统逻辑）
- intercept_web   拦截「打开网页」（http/https，覆盖全部入口：
                  webbrowser.open / QDesktopServices / os.startfile / bash start）
                  → 内置浏览器
- intercept_html  拦截「打开本地 html 文件」（file:// / os.startfile /
                  磁盘 .html 路径）→ 内置浏览器

（v1.3.2 及之前为 intercept_system / intercept_shell / intercept_html 三开关，
 本版按需求收敛为「网页 / HTML」两类语义开关；旧配置文件加载时自动迁移：
 intercept_web = intercept_system OR intercept_shell，任一开则网页拦截保持开。）

⚠️ 热重载陷阱（v1.3.3 修复「拦截失效」的根因）：external_open 的代理函数
不再顶层 from .redirect_config import should_intercept —— 顶层 import 会在
热重载后冻结为旧模块实例，旧模块的 ConfigStore 单例不再从磁盘 reload，
导致设置弹窗里的开关怎么改都不生效。代理函数改为调用时动态解析当前模块。

线程安全 + 原子写，模式与 ip-switcher/ui/config.py 一致，但存储目录改为
插件自身数据目录（用户明确选择，不走 user-custom）。
"""

import json
import re
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

# ── 默认配置 ──────────────────────────────────────────────

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    # 拦截打开网页（http/https，system / shell / startfile 全入口统一开关）
    "intercept_web": True,
    # 拦截打开本地 html 文件（file:// / os.startfile / 磁盘 .html 路径）
    "intercept_html": True,
}

# 旧版（≤v1.3.2）配置键 → 迁移来源；加载时自动折算进 intercept_web
_LEGACY_WEB_KEYS = ("intercept_system", "intercept_shell")

# 配置文件的固定相对路径（运行时按用户目录解析）
_CONFIG_REL = Path(".drifox") / "plugins" / "browser" / "data" / "browser-redirect.json"


def _get_config_path() -> Path:
    """定位配置文件：~/.drifox/plugins/browser/data/browser-redirect.json"""
    return Path.home() / _CONFIG_REL


class ConfigStore:
    """浏览器拦截配置存储（线程安全 + 原子写）"""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or _get_config_path()
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = dict(DEFAULT_CONFIG)
        self.load()

    def load(self) -> None:
        """从磁盘加载，与默认值合并（缺字段补默认）+ 旧配置键迁移

        旧键迁移（≤v1.3.2）：intercept_system / intercept_shell 任一为 True
        → intercept_web=True（保持网页拦截开启，宁可多拦不可漏拦）。
        迁移结果落盘（下次加载即为新格式）。
        """
        try:
            if self.path.exists():
                with self.path.open("r", encoding="utf-8") as f:
                    saved = json.load(f)
                if isinstance(saved, dict):
                    merged = dict(DEFAULT_CONFIG)
                    merged.update(
                        {k: v for k, v in saved.items() if k in DEFAULT_CONFIG}
                    )
                    # 旧配置键迁移（仅当新键未显式保存过）
                    if "intercept_web" not in saved:
                        legacy_on = any(
                            bool(saved.get(k, True)) for k in _LEGACY_WEB_KEYS
                        )
                        merged["intercept_web"] = legacy_on
                    with self._lock:
                        self._data = merged
                    if any(k in saved for k in _LEGACY_WEB_KEYS) and "intercept_web" not in saved:
                        self.save()  # 迁移结果落盘
                    return
        except (OSError, ValueError) as e:
            logger.warning(f"[browser-redirect] 配置加载失败，使用默认值: {e}")
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
            logger.error(f"[browser-redirect] 配置保存失败: {e}")

    # ── 读取 / 写入 ──

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def get_all(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._data)

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


# 模块级单例（热重载时重建）
_store: Optional[ConfigStore] = None


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


# ── 拦截决策（供 external_open 调用）─────────────────────

_HTML_SUFFIX_RE = re.compile(r"\.(?:html?|xhtml)$", re.IGNORECASE)


_URL_SCHEMES = ("http", "https", "file", "ftp", "sftp", "ws", "wss")


def _normalize_to_str(url: Any) -> str:
    """把 str / os.PathLike / QUrl / Path 等统一规范成字符串

    - 字符串 → 原样（去空白）
    - os.PathLike（pathlib.Path 等）→ str()；但 Windows Path 会把 ``://``
      改成 ``\\``（如 ``Path("http://x.com")`` → ``WindowsPath('http:/x.com')``），
      此时若还原后第一个冒号前是已知 URL scheme，则还原成 ``scheme://rest``。
      （不能用更激进的启发式：``C:\test.html`` 也含冒号，会被误判为 scheme）
    - Qt QUrl → toString()，本地路径走 toLocalFile() 补 file://
    - 其他对象 → str(url)

    返回空串表示无意义输入（None / 转换异常）。
    """
    if url is None:
        return ""
    if isinstance(url, str):
        return url.strip()
    # os.PathLike 优先（pathlib.Path 在 Windows 上即属于此）
    try:
        import os as _os

        if isinstance(url, _os.PathLike):
            as_str = str(url).strip()
            if "://" not in as_str:
                # 检查第一个冒号前是否是已知 URL scheme，是则还原
                head, sep, rest = as_str.partition(":")
                if sep and head.lower() in _URL_SCHEMES and (rest.startswith("\\") or rest.startswith("/")):
                    return f"{head}://{rest.lstrip('\\/')}"
            return as_str
    except Exception:
        pass
    # QUrl / QtCore.QUrl：本地文件需走 toLocalFile → file:// 再 toString
    try:
        from PyQt5.QtCore import QUrl as _QUrl  # type: ignore

        if isinstance(url, _QUrl):
            if url.isLocalFile():
                local = url.toLocalFile()
                try:
                    return Path(local).resolve().as_uri()
                except OSError:
                    return local
            return url.toString().strip()
    except Exception:
        pass
    try:
        return str(url).strip()
    except Exception:
        return ""


def _is_http(url: str) -> bool:
    """仅 http/https（scheme 大小写不敏感）"""
    u = url.strip().lower()
    return u.startswith("http://") or u.startswith("https://")


def _is_local_html(url: str) -> bool:
    """是否为本地 html 文件（file:// 协议或磁盘 .html 路径）

    判定：
    - file:// 开头（含 file:/// 与 file://server/）→ 看后缀
    - 其余（本地路径 D:/x.html、/home/x.html、UNC 路径）→ 看后缀
    - http/https 链接即使带 .html 后缀也不算本地文件（避免把网页 URL 当本地）
    """
    u = url.strip()
    if not u:
        return False
    if _is_http(u):
        return False
    if u.lower().startswith("file://"):
        return bool(_HTML_SUFFIX_RE.search(u))
    # 无协议字符串（本地路径/相对文件名）：带 html 后缀即视为本地文件。
    # 排除带 scheme:// 的（ftp://x/a.html 等仍走原逻辑；http/https 已在前面剔除）
    if not _HTML_SUFFIX_RE.search(u):
        return False
    return not bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", u))


def to_browser_url(url: Any) -> str:
    """把任意目标转成内置浏览器可加载的 URL

    - file:// 协议 → 原样
    - 本地 html 路径（D:/x.html 等）→ 转成 file:/// 形式
    - http/https → 原样
    - QUrl 本地文件 → 走 toLocalFile 转 file://
    - pathlib.Path / PathLike → 转 file:// 绝对路径
    """
    u = _normalize_to_str(url)
    if not u:
        return u
    if u.lower().startswith("file://"):
        return u
    if _is_http(u):
        return u
    # 本地路径 → file:// 绝对路径
    try:
        p = Path(u)
        if p.is_absolute() or u.startswith(("/", "\\")):
            return p.resolve().as_uri()
        # 相对路径：基于当前工作目录补全
        return (Path.cwd() / p).resolve().as_uri()
    except (OSError, ValueError) as e:
        logger.debug(f"[browser-redirect] 路径转 file:// 失败({u}): {e}")
        return u


def should_intercept(url: Any, entry: str = "") -> bool:
    """按配置判断是否应拦截该 URL

    entry（保留参数，便于调用方日志溯源，不再参与分支）：
    - "system"    webbrowser.open / QDesktopServices.openUrl
    - "shell"     bash start/explorer 命令
    - "startfile" os.startfile 入口

    规则（两类语义开关，全局 enabled 关闭一律不拦）：
    - 本地 html 文件 → intercept_html
    - http/https 网页 → intercept_web（全入口统一，不再区分 system/shell）
    - 其余（file 非 html / mailto / 本地可执行文件等）→ 不拦

    接受 str / PathLike / QUrl 输入（非字符串输入也能拦截）。
    """
    cfg = get_config()
    if not cfg.get("enabled", True):
        return False
    u = _normalize_to_str(url)
    if not u:
        return False
    if _is_local_html(u):
        return bool(cfg.get("intercept_html", True))
    if _is_http(u):
        return bool(cfg.get("intercept_web", True))
    return False


def config_summary() -> str:
    """返回当前配置的简短文字描述（用于状态栏显示拦截状态）

    例：拦截:开 [网页·开 HTML·开]
        拦截:关
    """
    cfg = get_config()
    if not cfg.get("enabled", True):
        return "拦截:关"
    parts = []
    for k, label in (("intercept_web", "网页"), ("intercept_html", "HTML")):
        parts.append(f"{label}·{'开' if cfg.get(k, True) else '关'}")
    return "拦截:开 [" + " ".join(parts) + "]"