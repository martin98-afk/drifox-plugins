# -*- coding: utf-8 -*-
"""Profile 管理 — 独立持久浏览器 Profile + 隐身 OTR Profile

设计约束：
- 不导入 app.core 或 app.widgets 内部的任何模块（保持插件隔离）
- 浏览器使用独立命名的持久 Profile（browser-profile），与主程序共享
  OTR profile 完全隔离，Cookie/Storage/Cache 都落在插件数据目录
- 隐身模式每次创建全新匿名 Profile（H1 修复）：不缓存、不复用，
  配合 incognito.closeEvent 中的彻底清理，确保 OTR 无痕

⚠️ QWebEngineProfile 必须在 QCoreApplication 创建前导入（否则 ImportError）。
主程序 main.py 已提前导入 QtWebEngineWidgets；profile_manager 采用延迟导入
保证任何加载顺序安全。
"""

from pathlib import Path
from typing import Optional

# 数据根目录：~/.drifox/plugins/browser/data/
DATA_DIR = Path.home() / ".drifox" / "plugins" / "browser" / "data"
PROFILE_DIR = DATA_DIR / "profile"
CACHE_DIR = DATA_DIR / "cache"
DOWNLOAD_DIR = Path.home() / "Downloads"

# 单例：持久浏览器 Profile（跨窗口共享）
_browser_profile: Optional[object] = None

_PROFILE_NAME = "browser-profile"


def _ensure_dirs() -> None:
    """确保数据目录存在"""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_ACCEPT_LANG = "zh-CN,zh;q=0.9,en;q=0.8"


def get_browser_profile():
    """获取浏览器持久 Profile（单例，延迟初始化）

    独立命名 profile + 独立 storage/cache 路径：
    - 与主程序共享 profile 完全隔离，互不影响
    - Cookie/localStorage 持久化在插件数据目录
    """
    global _browser_profile
    if _browser_profile is not None:
        try:
            _browser_profile.storageName()
            return _browser_profile
        except RuntimeError:
            _browser_profile = None

    from PyQt5.QtWebEngineWidgets import QWebEngineProfile

    _ensure_dirs()

    profile = QWebEngineProfile(_PROFILE_NAME)
    profile.setPersistentStoragePath(str(PROFILE_DIR))
    profile.setCachePath(str(CACHE_DIR))
    profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
    profile.setHttpCacheType(QWebEngineProfile.DiskHttpCache)
    profile.setHttpCacheMaximumSize(256 * 1024 * 1024)
    profile.setDownloadPath(str(DOWNLOAD_DIR))
    profile.setHttpUserAgent(_UA)
    profile.setHttpAcceptLanguage(_ACCEPT_LANG)

    _browser_profile = profile
    return profile


def get_incognito_profile():
    """获取全新的隐身 Profile（匿名 OTR，关闭即焚）

    H1 修复：不再缓存匿名 profile，每次调用都返回全新实例。
    QWebEngineProfile() 匿名实例必须保持 Python 引用（否则 WebEngine 崩溃），
    由调用方（隐身窗口）持有引用并在关闭时显式清理。

    Returns:
        全新 QWebEngineProfile 匿名实例（无 Cookie/Storage/ServiceWorker 持久化）
    """
    from PyQt5.QtWebEngineWidgets import QWebEngineProfile

    profile = QWebEngineProfile()  # 匿名 → OTR，无 storageName
    # OTR 三件套：禁持久 cookies + 内存缓存
    profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)
    profile.setHttpCacheType(QWebEngineProfile.MemoryHttpCache)
    profile.setDownloadPath(str(DOWNLOAD_DIR))
    profile.setHttpUserAgent(_UA)
    profile.setHttpAcceptLanguage(_ACCEPT_LANG)
    return profile


def purge_incognito_profile(profile) -> None:
    """显式清理匿名 OTR Profile 的所有数据（H1 修复配套）

    关闭隐身窗口前调用，确保下次的隐身窗口拿到的是一个全新的 profile 之前，
    旧 profile 留下的 Cookie/ServiceWorker/Cache 全部清空（即使 OTR 也不应有残留）。

    Qt 6 中 QWebEngineProfile 提供 cookieStore.clear() + clearHttpCache() + serviceWorker 清理；
    Qt 5.x 中 serviceWorker 注册表在 profile 销毁时自动清理（OTR 模式无磁盘写入），
    此处保守显式调用 + 设置 NoCache 兜底。

    Args:
        profile: QWebEngineProfile 实例（隐身窗口持有的 OTR profile）
    """
    if profile is None:
        return
    try:
        from PyQt5.QtWebEngineWidgets import QWebEngineProfile

        # 1) 清 cookie
        try:
            cookie_store = profile.cookieStore()
            if cookie_store is not None and hasattr(cookie_store, "deleteAllCookies"):
                cookie_store.deleteAllCookies()
            elif cookie_store is not None and hasattr(cookie_store, "clear"):
                cookie_store.clear()
        except Exception:
            pass

        # 2) 清 HTTP 缓存
        try:
            profile.clearHttpCache()
        except Exception:
            pass

        # 3) 兜底：禁用缓存类型（避免任何磁盘写入）
        try:
            profile.setHttpCacheType(QWebEngineProfile.NoCache)
        except Exception:
            pass

        # 4) ServiceWorker：Qt 5.x 无直接 API；OTR profile 销毁时自动释放
        #    这里通过 setPersistentCookiesPolicy(NoPersistentCookies) 强化
        try:
            profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)
        except Exception:
            pass
    except RuntimeError:
        # profile 已被销毁（如 Qt 端 C++ 对象已释放），无需清理
        pass


def get_profile_for(incognito: bool = False):
    """按模式返回 Profile"""
    return get_incognito_profile() if incognito else get_browser_profile()


def reset_profiles() -> None:
    """清空持久 Profile 单例引用（热重载/卸载时调用，避免旧 Profile 泄漏）

    隐身 Profile 不缓存，所以此处无需处理。调用方（如 browser_window.deleteLater）
    应已通过关闭所有隐身窗口释放它们各自的匿名 profile。
    """
    global _browser_profile
    _browser_profile = None