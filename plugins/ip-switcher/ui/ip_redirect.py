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

import time
from typing import Any, Optional

from loguru import logger

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


def _is_connection_error(exc: BaseException) -> bool:
    """判断异常是否为连接类错误（代理不可用 / 网络断连）

    白名单请求全走本地代理池，连接失败大概率是选中代理已死或上游断连，
    与限流一样应触发换 IP 重试。
    """
    try:
        import openai

        if isinstance(exc, openai.APIConnectionError):
            return True
    except Exception:
        pass
    try:
        import httpx

        if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
            return True
    except Exception:
        pass
    try:
        import httpcore

        if isinstance(exc, (httpcore.ConnectError, httpcore.ConnectTimeout)):
            return True
    except Exception:
        pass
    return False


def _is_switch_trigger_error(exc: BaseException) -> bool:
    """是否应触发换 IP：限流（429）或连接类错误（死代理）"""
    return _is_rate_limit_error(exc) or _is_connection_error(exc)


def _is_opencode_free(model: str = "", base_url: str = "") -> bool:
    """opencode 免费模型判定：model 名或 base_url 命中系统内置 opencode 免费 provider"""
    cfg = get_config()
    if model and cfg.is_opencode_free_model(model):
        return True
    if base_url and cfg.is_opencode_free_base_url(base_url):
        return True
    return False


def _switch_ip_threadsafe(
    trigger: str = "manual", timeout: float = 20.0
) -> Optional[str]:
    """执行换 IP（可在任意线程调用，不阻塞主线程）

    换 IP 全程是 IO 操作（rotate 控制台请求 + 出口 IP 验证），
    不应派发到主线程执行（会冻结 UI）。调用方负责在后台线程调用：
    - 429 路径：worker 线程（openai SDK 调用线程）
    - 手动路径：卡片按钮起后台线程
    完成后通过 state 信号（AutoConnection）自动投递主线程刷新 UI。

    Args:
        trigger: 触发类型 "manual"（手动按钮）或 "ratelimit"（429 自动）
    """
    return _do_switch_ip(trigger)


def _do_switch_ip(trigger: str = "manual") -> Optional[str]:
    """执行换 IP（可在任意线程调用）：代理池 rotate → 验证出口 IP → 更新 state

    IO 操作（rotate / 出口验证）在调用线程执行，不在主线程跑；
    state 写入线程安全（RLock + 信号 AutoConnection 投递主线程刷新 UI）。

    Args:
        trigger: "manual"（手动按钮）或 "ratelimit"（429 自动）
    """
    state = get_state()
    if not state.is_auto_switch() and trigger == "ratelimit":
        logger.info("[ip-switcher] 自动切换已暂停，跳过换 IP")
        return None
    old_ip = state.current_ip()
    manager = get_manager()
    # rotate + 出口验证：验证失败（死代理）自动再 rotate，最多 2 轮
    # （每轮 get_outbound_ip 3s 超时，全程后台线程执行不阻塞 UI）
    new_proxy: Optional[str] = None
    outbound: Optional[str] = None
    for _attempt in range(2):
        new_proxy = manager.rotate()
        if not new_proxy:
            logger.warning("[ip-switcher] 代理池换 IP 失败（可能池子为空）")
            state.set_pool_state("error")
            return None
        outbound = manager.get_outbound_ip()
        if outbound:
            break
        logger.warning(f"[ip-switcher] 出口验证失败，尝试更换代理 ({_attempt + 1}/2)")
    # 出口验证失败时用代理 host 兜底（换绑仍记录，连接错误会再触发换 IP）
    new_ip = outbound or new_proxy.split(":")[0]
    if old_ip == "未使用":
        effective_trigger = "startup"
    else:
        effective_trigger = trigger  # manual / ratelimit 如实记录
    state.record_switch(effective_trigger, old_ip, new_ip)
    state.set_pool_state("ok")
    logger.info(f"[ip-switcher] 已切换 IP ({effective_trigger}): {old_ip} → {new_ip}")
    return new_ip


def _make_proxied_http_client(proxy_url: str):
    """构建带代理的 httpx.Client（openai SDK http_client 参数）

    verify=False：免费代理转发 https 常做 MITM（自签名证书），
    与 get_outbound_ip 的 http 端点处理一致，避免 CERTIFICATE_VERIFY_FAILED。
    """
    import httpx

    return httpx.Client(
        proxy=proxy_url,
        timeout=httpx.Timeout(60.0, connect=10.0),
        verify=False,
    )


def _patched_openai_init(self, *args, **kwargs):
    """OpenAI.__init__ 代理：白名单命中注入代理 http_client

    仅当代理池正在运行时注入；用户停止代理后新 client 直接回退直连，
    避免指向已死的 8082 端口。
    """
    cfg = get_config()
    base_url = kwargs.get("base_url") or ""
    model = kwargs.get("model") or ""
    if (
        cfg.get("enabled")
        and get_manager().is_running()
        and _is_opencode_free(model=model, base_url=base_url)
    ):
        if "http_client" not in kwargs:
            try:
                port = cfg.get("proxy_pool_port", 8082)
                kwargs["http_client"] = _make_proxied_http_client(
                    f"http://127.0.0.1:{port}"
                )
                logger.debug(
                    f"[ip-switcher] 白名单命中注入代理 client: base={base_url} model={model}"
                )
            except Exception as e:
                logger.warning(f"[ip-switcher] 注入代理 client 失败，回退直连: {e}")
    return _orig_openai_init(self, *args, **kwargs)


def _patched_async_openai_init(self, *args, **kwargs):
    """AsyncOpenAI.__init__ 代理（同 OpenAI）"""
    cfg = get_config()
    base_url = kwargs.get("base_url") or ""
    model = kwargs.get("model") or ""
    if (
        cfg.get("enabled")
        and get_manager().is_running()
        and _is_opencode_free(model=model, base_url=base_url)
    ):
        if "http_client" not in kwargs:
            try:
                port = cfg.get("proxy_pool_port", 8082)
                import httpx

                kwargs["http_client"] = httpx.AsyncClient(
                    proxy=f"http://127.0.0.1:{port}",
                    timeout=httpx.Timeout(60.0, connect=10.0),
                    verify=False,  # 免费代理 MITM 自签名证书
                )
                logger.debug(
                    f"[ip-switcher] 白名单命中注入异步代理 client: base={base_url}"
                )
            except Exception as e:
                logger.warning(f"[ip-switcher] 注入异步代理 client 失败，回退直连: {e}")
    return _orig_async_openai_init(self, *args, **kwargs)


def _wrap_chat_create(orig_create):
    """包装 chat.completions.create：限流(429)/连接错误 → 换 IP → 重试"""

    def _wrapped(self, *args, **kwargs):
        cfg = get_config()
        model = kwargs.get("model") or getattr(self, "_model", "")
        base_url = str(getattr(self, "base_url", "") or "")
        # 代理池未运行 → 直接透传（停止代理后不换 IP 不重试）
        if not (
            cfg.get("enabled")
            and get_manager().is_running()
            and _is_opencode_free(model=model, base_url=base_url)
        ):
            return orig_create(self, *args, **kwargs)  # 非白名单/池停零开销

        retry_limit = int(cfg.get("retry_limit", 3))
        backoff = float(cfg.get("retry_backoff_seconds", 2))
        last_exc: Optional[BaseException] = None
        for attempt in range(retry_limit + 1):
            try:
                return orig_create(self, *args, **kwargs)
            except Exception as e:
                if not _is_switch_trigger_error(e):
                    raise  # 非限流/非连接错误直接抛
                last_exc = e
                reason = "429 限流" if _is_rate_limit_error(e) else "连接错误"
                logger.warning(
                    f"[ip-switcher] {reason} (第 {attempt + 1} 次)，换 IP 后重试"
                )
                if attempt >= retry_limit:
                    break
                new_ip = _switch_ip_threadsafe(trigger="ratelimit")
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
        # 代理池未运行 → 直接透传（停止代理后不换 IP 不重试）
        if not (
            cfg.get("enabled")
            and get_manager().is_running()
            and _is_opencode_free(model=model, base_url=base_url)
        ):
            return await orig_acreate(self, *args, **kwargs)

        retry_limit = int(cfg.get("retry_limit", 3))
        backoff = float(cfg.get("retry_backoff_seconds", 2))
        last_exc: Optional[BaseException] = None
        for attempt in range(retry_limit + 1):
            try:
                return await orig_acreate(self, *args, **kwargs)
            except Exception as e:
                if not _is_switch_trigger_error(e):
                    raise
                last_exc = e
                reason = "429 限流" if _is_rate_limit_error(e) else "连接错误"
                logger.warning(
                    f"[ip-switcher] {reason} (异步, 第 {attempt + 1} 次)，换 IP 后重试"
                )
                if attempt >= retry_limit:
                    break
                new_ip = _switch_ip_threadsafe(trigger="ratelimit")
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

    # 幂等：热重载遗留代理检测。
    # ⚠️ 此时原始方法引用必须从已 patch 的函数对象上取回（_orig 属性），
    # 不能依赖本模块的 _orig_*（热重载后新模块里它们是 None）！
    if getattr(openai.OpenAI.__init__, "_drifox_ip_switch", False):
        _orig_openai_init = getattr(openai.OpenAI.__init__, "_orig", None)
        if hasattr(openai, "AsyncOpenAI"):
            _orig_async_openai_init = getattr(
                openai.AsyncOpenAI.__init__, "_orig", None
            )
        try:
            from openai.resources.chat.completions import Completions

            _orig_chat_create = getattr(Completions.create, "_orig", None)
            if hasattr(Completions, "acreate"):
                _orig_chat_acreate = getattr(Completions.acreate, "_orig", None)
        except Exception:
            pass
        _installed = True
        return True

    try:
        # 1) patch OpenAI.__init__（原始方法挂到函数对象，热重载后仍可找回）
        _orig_openai_init = openai.OpenAI.__init__
        _patched_openai_init._drifox_ip_switch = True  # type: ignore[attr-defined]
        _patched_openai_init._orig = _orig_openai_init  # type: ignore[attr-defined]
        openai.OpenAI.__init__ = _patched_openai_init  # type: ignore[assignment]

        # 2) patch AsyncOpenAI.__init__
        if hasattr(openai, "AsyncOpenAI"):
            _orig_async_openai_init = openai.AsyncOpenAI.__init__
            _patched_async_openai_init._drifox_ip_switch = True  # type: ignore[attr-defined]
            _patched_async_openai_init._orig = _orig_async_openai_init  # type: ignore[attr-defined]
            openai.AsyncOpenAI.__init__ = _patched_async_openai_init  # type: ignore[assignment]

        # 3) patch chat.completions.create
        from openai.resources.chat.completions import Completions

        _orig_chat_create = Completions.create
        _wrapped = _wrap_chat_create(_orig_chat_create)
        _wrapped._drifox_ip_switch = True  # type: ignore[attr-defined]
        _wrapped._orig = _orig_chat_create  # type: ignore[attr-defined]
        Completions.create = _wrapped  # type: ignore[assignment]

        # 4) patch chat.completions.acreate
        if hasattr(Completions, "acreate"):
            _orig_chat_acreate = Completions.acreate
            _wrapped_async = _wrap_chat_acreate(_orig_chat_acreate)
            _wrapped_async._drifox_ip_switch = True  # type: ignore[attr-defined]
            _wrapped_async._orig = _orig_chat_acreate  # type: ignore[attr-defined]
            Completions.acreate = _wrapped_async  # type: ignore[assignment]

        _installed = True
        logger.info("[ip-switcher] monkey patch 已安装 (OpenAI.__init__ + chat.create)")
        return True
    except Exception:
        logger.exception("[ip-switcher] monkey patch 安装失败")
        return False


def uninstall_redirect() -> None:
    """卸载 patch（插件卸载/禁用时调用）

    优先从当前被 patch 的函数对象上取回原始方法（_orig 属性），
    兼容热重载后本模块 _orig_* 为 None 的情况。
    """
    global _installed, _orig_openai_init, _orig_async_openai_init
    global _orig_chat_create, _orig_chat_acreate
    try:
        import openai

        # OpenAI.__init__：从 patch 函数对象取原始引用
        cur = openai.OpenAI.__init__
        orig = getattr(cur, "_orig", None)
        if orig is not None:
            openai.OpenAI.__init__ = orig  # type: ignore[assignment]
        elif _orig_openai_init is not None:
            openai.OpenAI.__init__ = _orig_openai_init  # type: ignore[assignment]

        # AsyncOpenAI.__init__
        if hasattr(openai, "AsyncOpenAI"):
            cur_a = openai.AsyncOpenAI.__init__
            orig_a = getattr(cur_a, "_orig", None)
            if orig_a is not None:
                openai.AsyncOpenAI.__init__ = orig_a  # type: ignore[assignment]
            elif _orig_async_openai_init is not None:
                openai.AsyncOpenAI.__init__ = _orig_async_openai_init  # type: ignore[assignment]

        # chat.completions.create / acreate
        from openai.resources.chat.completions import Completions

        cur_c = Completions.create
        orig_c = getattr(cur_c, "_orig", None)
        if orig_c is not None:
            Completions.create = orig_c  # type: ignore[assignment]
        elif _orig_chat_create is not None:
            Completions.create = _orig_chat_create  # type: ignore[assignment]

        if hasattr(Completions, "acreate"):
            cur_ac = Completions.acreate
            orig_ac = getattr(cur_ac, "_orig", None)
            if orig_ac is not None:
                Completions.acreate = orig_ac  # type: ignore[assignment]
            elif _orig_chat_acreate is not None:
                Completions.acreate = _orig_chat_acreate  # type: ignore[assignment]
    except Exception as e:
        logger.warning(f"[ip-switcher] 卸载 patch 异常: {e}")
    _installed = False
    _orig_openai_init = _orig_async_openai_init = None
    _orig_chat_create = _orig_chat_acreate = None
