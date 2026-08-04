# -*- coding: utf-8 -*-
"""ip-switcher monkey patch — 白名单模型走代理池 + 429 自动换 IP 重试

原理（对齐 browser/external_open.py 模式）：
- patch ``openai.OpenAI.__init__`` / ``AsyncOpenAI.__init__``：
  白名单命中 → 注入带本地代理的 ``http_client``
- patch ``chat.completions.create`` / ``acreate``：
  捕获 RateLimitError(429) → 换 IP → 自动重试（默认 3 次）
- 幂等：热重载时 register_ui 再次执行，通过标记避免重复嵌套
- 线程安全：429 可能发生在 worker 线程，经 _MainThreadDispatcher 回主线程换 IP
"""

import re
import threading
import time
from typing import Any, Optional

from loguru import logger
from PyQt5.QtCore import QObject, pyqtSignal

# 绝对导入（与 conftest.py 加载方式一致：sys.path 含 ui 目录）
from config import get_config
from proxy_pool import get_manager
from state import get_state

# ── 幂等标记 ──────────────────────────────────────────────
_installed = False
_orig_openai_init: Any = None
_orig_async_openai_init: Any = None
_orig_chat_create: Any = None
_orig_chat_acreate: Any = None

# 429 错误文本关键词（防止误判其他异常）
_RATE_LIMIT_KEYWORDS = (
    "rate limit",
    "rate_limit",
    "quota",
    "额度",
    "limit exceeded",
    "too many requests",
    "429",
)


def _is_rate_limit_error(exc: BaseException) -> bool:
    """判断异常是否为限流（429 或错误文本命中）"""
    # openai.RateLimitError 是 429 专用异常
    try:
        import openai

        if isinstance(exc, openai.RateLimitError):
            return True
    except Exception:
        pass
    # 错误文本关键词匹配
    msg = str(getattr(exc, "message", "") or exc).lower()
    return any(kw in msg for kw in _RATE_LIMIT_KEYWORDS)


def _is_whitelisted(model: str = "", base_url: str = "") -> bool:
    """白名单判定：model 名或 base_url 命中任一即可"""
    cfg = get_config()
    if model and cfg.is_whitelisted_model(model):
        return True
    if base_url and cfg.is_whitelisted_base_url(base_url):
        return True
    return False


class _MainThreadDispatcher(QObject):
    """跨线程派发器：信号 AutoConnection 自动投递到主线程事件循环"""

    _requested = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self._requested.connect(self._handle)

    def _handle(self, fn):
        try:
            fn()
        except Exception:
            logger.exception("[ip-switcher] 主线程派发任务异常")

    def call(self, fn):
        self._requested.emit(fn)


_dispatcher: Optional[_MainThreadDispatcher] = None


def _get_dispatcher() -> Optional[_MainThreadDispatcher]:
    """获取主线程派发器（须在主线程创建）"""
    global _dispatcher
    if _dispatcher is None:
        try:
            from PyQt5.QtCore import QThread
            from PyQt5.QtWidgets import QApplication

            app = QApplication.instance()
            if app is None or QThread.currentThread() != app.thread():
                return None
            _dispatcher = _MainThreadDispatcher()
        except Exception:
            return None
    return _dispatcher


def _switch_ip_threadsafe(timeout: float = 20.0) -> Optional[str]:
    """线程安全换 IP：非 UI 线程 → 派发到主线程同步等待结果"""
    import threading as _t

    try:
        from PyQt5.QtCore import QThread
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None and QThread.currentThread() != app.thread():
            dispatcher = _get_dispatcher()
            if dispatcher is None:
                logger.warning("[ip-switcher] 派发器不可用且非主线程，跳过换 IP")
                return None
            event = _t.Event()
            result: dict = {"ip": None}

            def _do():
                try:
                    result["ip"] = _do_switch_ip()
                finally:
                    event.set()

            dispatcher.call(_do)
            event.wait(timeout)
            return result["ip"]
    except Exception:
        pass
    return _do_switch_ip()


def _do_switch_ip() -> Optional[str]:
    """执行换 IP（主线程）：代理池 rotate → 验证出口 IP → 更新 state"""
    state = get_state()
    if not state.is_auto_switch():
        logger.info("[ip-switcher] 自动切换已暂停，跳过换 IP")
        return None
    old_ip = state.current_ip()
    manager = get_manager()
    new_proxy = manager.rotate()
    if not new_proxy:
        logger.warning("[ip-switcher] 代理池换 IP 失败（可能池子为空）")
        state.set_pool_state("error")
        return None
    # 验证出口 IP
    outbound = manager.get_outbound_ip()
    new_ip = outbound or new_proxy.split(":")[0]
    state.record_switch("ratelimit" if old_ip != "未使用" else "startup", old_ip, new_ip)
    state.set_pool_state("ok")
    logger.info(f"[ip-switcher] 已切换 IP: {old_ip} → {new_ip}")
    return new_ip


def _make_proxied_http_client(proxy_url: str):
    """构建带代理的 httpx.Client（openai SDK http_client 参数）"""
    import httpx

    return httpx.Client(proxy=proxy_url, timeout=httpx.Timeout(60.0, connect=10.0))


def _patched_openai_init(self, *args, **kwargs):
    """OpenAI.__init__ 代理：白名单命中注入代理 http_client"""
    cfg = get_config()
    base_url = kwargs.get("base_url") or ""
    model = kwargs.get("model") or ""
    if cfg.get("enabled") and _is_whitelisted(model=model, base_url=base_url):
        if "http_client" not in kwargs:
            try:
                port = cfg.get("proxy_pool_port", 8082)
                kwargs["http_client"] = _make_proxied_http_client(f"http://127.0.0.1:{port}")
                logger.debug(f"[ip-switcher] 白名单命中注入代理 client: base={base_url} model={model}")
            except Exception as e:
                logger.warning(f"[ip-switcher] 注入代理 client 失败，回退直连: {e}")
    return _orig_openai_init(self, *args, **kwargs)


def _patched_async_openai_init(self, *args, **kwargs):
    """AsyncOpenAI.__init__ 代理（同 OpenAI）"""
    cfg = get_config()
    base_url = kwargs.get("base_url") or ""
    model = kwargs.get("model") or ""
    if cfg.get("enabled") and _is_whitelisted(model=model, base_url=base_url):
        if "http_client" not in kwargs:
            try:
                port = cfg.get("proxy_pool_port", 8082)
                import httpx

                kwargs["http_client"] = httpx.AsyncClient(
                    proxy=f"http://127.0.0.1:{port}",
                    timeout=httpx.Timeout(60.0, connect=10.0),
                )
                logger.debug(f"[ip-switcher] 白名单命中注入异步代理 client: base={base_url}")
            except Exception as e:
                logger.warning(f"[ip-switcher] 注入异步代理 client 失败，回退直连: {e}")
    return _orig_async_openai_init(self, *args, **kwargs)


def _wrap_chat_create(orig_create):
    """包装 chat.completions.create：429 → 换 IP → 重试"""

    def _wrapped(self, *args, **kwargs):
        cfg = get_config()
        model = kwargs.get("model") or getattr(self, "_model", "")
        base_url = str(getattr(self, "base_url", "") or "")
        if not (cfg.get("enabled") and _is_whitelisted(model=model, base_url=base_url)):
            return orig_create(self, *args, **kwargs)  # 非白名单零开销

        retry_limit = int(cfg.get("retry_limit", 3))
        backoff = float(cfg.get("retry_backoff_seconds", 2))
        last_exc: Optional[BaseException] = None
        for attempt in range(retry_limit + 1):
            try:
                return orig_create(self, *args, **kwargs)
            except Exception as e:
                if not _is_rate_limit_error(e):
                    raise  # 非限流错误直接抛
                last_exc = e
                logger.warning(f"[ip-switcher] 429 限流 (第 {attempt + 1} 次)，换 IP 后重试")
                if attempt >= retry_limit:
                    break
                new_ip = _switch_ip_threadsafe()
                if new_ip is None:
                    logger.warning("[ip-switcher] 换 IP 失败，不再重试")
                    break
                time.sleep(backoff)  # 等 IP 生效
        raise last_exc  # 重试耗尽 → 抛原始异常

    return _wrapped


def _wrap_chat_acreate(orig_acreate):
    """包装 chat.completions.acreate（异步版）"""

    async def _wrapped(self, *args, **kwargs):
        cfg = get_config()
        model = kwargs.get("model") or getattr(self, "_model", "")
        base_url = str(getattr(self, "base_url", "") or "")
        if not (cfg.get("enabled") and _is_whitelisted(model=model, base_url=base_url)):
            return await orig_acreate(self, *args, **kwargs)

        retry_limit = int(cfg.get("retry_limit", 3))
        backoff = float(cfg.get("retry_backoff_seconds", 2))
        last_exc: Optional[BaseException] = None
        for attempt in range(retry_limit + 1):
            try:
                return await orig_acreate(self, *args, **kwargs)
            except Exception as e:
                if not _is_rate_limit_error(e):
                    raise
                last_exc = e
                logger.warning(f"[ip-switcher] 429 限流 (异步, 第 {attempt + 1} 次)，换 IP 后重试")
                if attempt >= retry_limit:
                    break
                new_ip = _switch_ip_threadsafe()
                if new_ip is None:
                    break
                await __import__("asyncio").sleep(backoff)
        raise last_exc

    return _wrapped


def install_redirect() -> bool:
    """安装 monkey patch（register_ui 时调用）。返回是否完成注入。"""
    global _installed, _orig_openai_init, _orig_async_openai_init
    global _orig_chat_create, _orig_chat_acreate

    if _installed:
        return True
    try:
        import openai
    except Exception:
        logger.warning("[ip-switcher] openai SDK 不可用，跳过 patch")
        return False

    # 幂等：热重载遗留代理检测
    if getattr(openai.OpenAI.__init__, "_drifox_ip_switch", False):
        _installed = True
        return True

    try:
        # 1) patch OpenAI.__init__
        _orig_openai_init = openai.OpenAI.__init__
        _patched_openai_init._drifox_ip_switch = True  # type: ignore[attr-defined]
        openai.OpenAI.__init__ = _patched_openai_init  # type: ignore[assignment]

        # 2) patch AsyncOpenAI.__init__
        if hasattr(openai, "AsyncOpenAI"):
            _orig_async_openai_init = openai.AsyncOpenAI.__init__
            _patched_async_openai_init._drifox_ip_switch = True  # type: ignore[attr-defined]
            openai.AsyncOpenAI.__init__ = _patched_async_openai_init  # type: ignore[assignment]

        # 3) patch chat.completions.create
        from openai.resources.chat.completions import Completions

        _orig_chat_create = Completions.create
        Completions.create = _wrap_chat_create(_orig_chat_create)  # type: ignore[assignment]

        # 4) patch chat.completions.acreate
        if hasattr(Completions, "acreate"):
            _orig_chat_acreate = Completions.acreate
            Completions.acreate = _wrap_chat_acreate(_orig_chat_acreate)  # type: ignore[assignment]

        # 5) 预创建主线程派发器（register_ui 在主线程执行）
        _get_dispatcher()

        _installed = True
        logger.info("[ip-switcher] monkey patch 已安装 (OpenAI.__init__ + chat.create)")
        return True
    except Exception:
        logger.exception("[ip-switcher] monkey patch 安装失败")
        return False


def uninstall_redirect() -> None:
    """卸载 patch（插件卸载/禁用时调用）"""
    global _installed, _orig_openai_init, _orig_async_openai_init
    global _orig_chat_create, _orig_chat_acreate
    try:
        import openai

        if _orig_openai_init is not None:
            openai.OpenAI.__init__ = _orig_openai_init  # type: ignore[assignment]
        if _orig_async_openai_init is not None and hasattr(openai, "AsyncOpenAI"):
            openai.AsyncOpenAI.__init__ = _orig_async_openai_init  # type: ignore[assignment]
        if _orig_chat_create is not None:
            from openai.resources.chat.completions import Completions

            Completions.create = _orig_chat_create  # type: ignore[assignment]
        if _orig_chat_acreate is not None:
            from openai.resources.chat.completions import Completions

            Completions.acreate = _orig_chat_acreate  # type: ignore[assignment]
    except Exception as e:
        logger.warning(f"[ip-switcher] 卸载 patch 异常: {e}")
    _installed = False
    _orig_openai_init = _orig_async_openai_init = None
    _orig_chat_create = _orig_chat_acreate = None