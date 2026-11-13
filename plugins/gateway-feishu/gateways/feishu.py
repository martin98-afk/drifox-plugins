# -*- coding: utf-8 -*-
"""
飞书 (Feishu/Lark) 适配器（社区插件，万物即插件 Phase E）

使用 lark_oapi SDK WebSocket 模式进行消息收发。

本文件原位于 app/gateway/adapters/feishu.py（E2 Task 5 迁入）。
适配器实现保持原状（SDK 延迟导入纪律：模块顶层不 eager import 平台 SDK）。
"""

from __future__ import annotations


# 依赖注入已由宿主统一接管：PluginManager 扫描时注入 deps/ 与 deps/<platform>/
# （平台目录优先，见 app/plugins/deps_loader.py），插件组件不再自理 sys.path。
import asyncio
import json
import logging
import threading
from typing import Any, Dict, List, Optional, Tuple

from app.gateway.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
)

# 入站图片上限（超过直接跳过并记日志，不阻断整条消息）
MAX_INBOUND_IMAGES = 10
MAX_INBOUND_IMAGE_BYTES = 30 * 1024 * 1024


def _cache_dir():
    """入站图片缓存目录：优先宿主 get_cache_dir，缺失时退回默认数据目录。"""
    try:
        from app.gateway.base import get_cache_dir

        return get_cache_dir("feishu")
    except Exception:
        from pathlib import Path

        fallback = Path.home() / ".drifox" / "gateway" / "cache" / "feishu"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def _safe_file_name(name: str) -> str:
    """保留扩展名的安全文件名（去掉路径分隔符与控制字符）。"""
    import re as _re

    base = str(name or "").replace("\\", "/").split("/")[-1].strip()
    base = _re.sub(r"[\x00-\x1f\x7f]", "", base)
    return base[:80]


def _image_ext(data: bytes) -> str:
    """按魔数判图片扩展名（.png/.jpg/.gif/.webp，默认 .jpg）。"""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"GIF8"):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ".jpg"

# 走 loguru：宿主的日志系统只给 loguru 配 sink，标准 logging 的输出会被丢弃，
# 导致本插件的 [Feishu] 运行日志完全不落盘（连接/消息/handler 丢失均不可见）。
from loguru import logger  # noqa: E402


def _bridge_lark_logging() -> None:
    """把 lark SDK 的标准 logging 记录转发进 loguru（幂等）。

    lark_oapi 用 logging.getLogger("Lark") 记录连接诊断（尤其是
    "connect failed, err: ..."）。宿主只给 loguru 配 sink，标准 logging
    输出被丢弃 → 连接失败时日志完全空白，排查只能盲猜。此桥接让 SDK
    的诊断落进 gateway.log / all.log。
    """
    import logging as _logging

    _root = _logging.getLogger()
    if getattr(_root, "_drifox_lark_bridge_installed", False):
        return

    class _LoguruForwarder(_logging.Handler):
        def emit(self, record: _logging.LogRecord) -> None:
            try:
                # lark 的 logger 名形如 Lark / Lark.xxx，只转发这一族，
                # 避免把第三方库的噪音全量灌进日志
                if not record.name.startswith("Lark"):
                    return
                msg = record.getMessage()
                level = record.levelname
                if level in ("ERROR", "CRITICAL"):
                    logger.error("[Lark] {}", msg)
                elif level == "WARNING":
                    logger.warning("[Lark] {}", msg)
                elif level == "DEBUG":
                    # DEBUG 保留（连接诊断关键：connected to / ping success）；
                    # sink 级别为 DEBUG，降到 TRACE 会被过滤
                    logger.debug("[Lark] {}", msg)
                else:
                    logger.info("[Lark] {}", msg)
            except Exception:
                pass

    _root.addHandler(_LoguruForwarder())
    _root._drifox_lark_bridge_installed = True  # type: ignore[attr-defined]


_bridge_lark_logging()


def _ensure_ca_bundle() -> None:
    """确保 OpenSSL 能找到可用的 CA bundle（宿主打包环境自愈）。

    症状：宿主里所有 HTTPS/wss 握手失败，报
    ``[SSL: CERTIFICATE_VERIFY_FAILED] self-signed certificate in certificate
    chain``。飞书 WS 在 TLS 阶段即挂，长连接从未建立，消息静默丢失。

    成因：DriFox 是 PyInstaller 打包，OpenSSL 的默认 CA 路径
    （``ssl.get_default_verify_paths()``）在打包环境下可能指向不存在/为空的
    文件 → 内置 CA 列表为空，任何证书都验证不过。企业网络里代理插入的自签
    CA 也需要走系统信任库才认。

    分层兜底（幂等、不越权）：
    1. ``SSL_CERT_FILE`` 已设 → 尊重既有配置，不动
    2. 默认 bundle 可加载出证书 → 无需介入
    3. 有 truststore → 记为待用（websockets 侧经 _ssl_context() 消费）
    4. 否则回退 certifi 的 cacert.pem，写 ``SSL_CERT_FILE``

    注：truststore 无法经环境变量注入，只能显式建 SSLContext 传给库；
    websockets 走 ``_ssl_context()``，urllib 等走 ``SSL_CERT_FILE``。
    """
    import os
    import ssl

    global _TRUSTSTORE_AVAILABLE
    # 探测 truststore（系统信任库：macOS 钥匙串/Windows 证书存储/Linux CA 目录）
    try:
        import truststore  # noqa: F401

        _TRUSTSTORE_AVAILABLE = True
    except Exception:
        _TRUSTSTORE_AVAILABLE = False

    if os.environ.get("SSL_CERT_FILE"):
        return  # 已有显式配置，尊重之
    try:
        ctx = ssl.create_default_context()
        if ctx.get_ca_certs():
            return  # 默认 bundle 可用，无需兜底
    except Exception:
        pass  # 加载失败 → 继续走兜底
    if _TRUSTSTORE_AVAILABLE:
        # truststore 可用：SSLContext 由 _ssl_context() 显式提供，
        # 无需（也不应）写 SSL_CERT_FILE —— 写了反而覆盖系统信任库行为
        logger.info("[Feishu] 宿主默认 CA 不可用，改用 truststore 系统信任库")
        return
    try:
        import certifi

        ca = certifi.where()
        if ca and os.path.exists(ca):
            os.environ["SSL_CERT_FILE"] = ca
            logger.info("[Feishu] 宿主默认 CA 不可用，已回退 certifi: {}", ca)
        else:
            logger.warning("[Feishu] certifi cacert.pem 不存在，HTTPS 可能不可用")
    except Exception as e:
        logger.warning("[Feishu] CA bundle 兜底失败（HTTPS 可能不可用）: {}", e)


def _ssl_context():
    """建立 WS 连接用的 SSLContext；无法改进默认行为时返回 None。

    websockets 的 ``ssl`` 参数接受 SSLContext。返回 None 表示让库走默认
    验证（此时 ``SSL_CERT_FILE`` 已由 _ensure_ca_bundle 兜底）。
    """
    if not _TRUSTSTORE_AVAILABLE:
        return None
    try:
        import ssl

        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        return None


def _patch_lark_ws_connect() -> None:
    """给 lark SDK 的 WS 连接注入自建 SSLContext（幂等）。

    SDK 的 ``_ws_connect_kwargs()`` 硬编码只返回 ``{"proxy": None}``，不暴露
    ssl 入口，调用方无法传入自定义 SSLContext。而宿主打包环境下默认 CA
    列表可能为空，且企业代理的自签 CA 只认系统信任库 —— 唯一解法是换成
    truststore 的 SSLContext。

    做法：包装模块级 ``_ws_connect_kwargs``，在原有返回值上补 ``ssl`` 键。
    websockets 15 从 ``**kwargs`` 取 ``kwargs["ssl"]``（asyncio/client.py
    的 ``kwargs.setdefault("ssl", True)`` 分支），显式传入即生效。

    未探测到 truststore 时不介入，保持 SDK 原行为。
    """
    ctx = _ssl_context()
    if ctx is None:
        return
    try:
        import lark_oapi.ws.client as _wsc

        if getattr(_wsc, "_drifox_ssl_patched", False):
            return
        _orig = _wsc._ws_connect_kwargs

        def _with_ssl():
            kwargs = dict(_orig())
            kwargs["ssl"] = ctx
            return kwargs

        _wsc._ws_connect_kwargs = _with_ssl
        _wsc._drifox_ssl_patched = True  # type: ignore[attr-defined]
    except Exception as e:
        logger.debug("[Feishu] lark SDK ssl 注入跳过: {}", e)


_TRUSTSTORE_AVAILABLE = False
_ensure_ca_bundle()
# [PERF] _patch_lark_ws_connect() 延迟到 connect() 内调用：其内部 import
# lark_oapi.ws.client 实测 ~5.7s（SDK 模块树巨大，文件缓存热也慢），模块级执行
# 会让宿主启动预热的 warmup.gateways 扫描整段卡死 5.8s。补丁本身幂等，
# 在 SDK 可用后、建连前打即可。

# 延迟导入
LARK_AVAILABLE = False


def check_feishu_requirements() -> bool:
    """检查飞书依赖是否可用"""
    global LARK_AVAILABLE
    if LARK_AVAILABLE:
        return True
    try:
        import lark_oapi
        from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
        from lark_oapi.ws import Client as FeishuWSClient

        LARK_AVAILABLE = True
        return True
    except ImportError:
        logger.warning("[Feishu] lark_oapi not installed. Run: pip install lark-oapi")
        return False


class FeishuAdapter(BasePlatformAdapter):
    """
    飞书 (Feishu/Lark) 适配器

    使用飞书开放平台 WebSocket 模式进行消息收发。
    需要安装 lark-oapi: pip install lark-oapi
    """

    platform_id = "feishu"
    MAX_MESSAGE_LENGTH = 6000

    def __init__(self) -> None:
        super().__init__()
        cfg = _config()

        self._app_id = cfg["app_id"]
        self._app_secret = cfg["app_secret"]
        self._encrypt_key = cfg["encrypt_key"]
        self._verification_token = cfg["verification_token"]
        # 群聊响应策略：默认只在被 @机器人 时回复（对齐 dsh-im mention 模式）
        self._require_mention = cfg["require_mention"]

        self._ws_client = None
        self._running = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5
        self._message_handler = None
        self._feishu_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # ws 线程内运行 lark SDK 的事件循环引用（disconnect 需经它调度断连/停止）
        self._ws_loop: Optional[asyncio.AbstractEventLoop] = None

        # 独立的事件循环，用于执行消息处理（不与 WS client 的循环冲突）
        self._handler_loop: Optional[asyncio.AbstractEventLoop] = None
        self._handler_loop_thread: Optional[threading.Thread] = None

        # Token 缓存：tenant_access_token 有效期 2 小时，缓存避免每次 send 都请求
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

        # 共享 HTTP 客户端：连接复用，避免每次 send 新建 AsyncClient
        self._http_client: Optional[httpx.AsyncClient] = None

        # 流式回复状态：stream_key(message_id) -> {chat_id, ts}
        self._stream_states: Dict[str, Dict[str, Any]] = {}

    def set_message_handler(self, handler) -> None:
        """设置消息处理器"""
        self._message_handler = handler

    async def connect(self) -> bool:
        """连接到飞书 WebSocket"""
        # 重入防御：上一轮 ws 线程仍存活（stop 未完成/异常路径残留）时先彻底断开，
        # 否则会叠出第二个 ws 线程 + 第二条长连接（历史 bug：连接泄漏越启越多）
        if self._feishu_thread is not None and self._feishu_thread.is_alive():
            logger.warning("[Feishu] Previous WS thread still alive, disconnecting before reconnect")
            await self.disconnect()

        if not check_feishu_requirements():
            logger.error("[Feishu] Dependencies not available. Run: pip install lark-oapi")
            self._last_error = "依赖不可用"
            return False

        # 从配置重新获取（确保最新）：走本插件配置读取，不依赖宿主配置结构
        cfg = _config()
        self._app_id = cfg["app_id"]
        self._app_secret = cfg["app_secret"]
        self._encrypt_key = cfg["encrypt_key"]
        self._verification_token = cfg["verification_token"]

        if not self._app_id or not self._app_secret:
            logger.error("[Feishu] app_id and app_secret are required")
            self._last_error = "缺少 app_id 或 app_secret"
            return False

        try:
            import lark_oapi as lark
            from lark_oapi.core.const import FEISHU_DOMAIN
            from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
            from lark_oapi.ws import Client as FeishuWSClient

            # ssl 补丁：SDK 已可用，建连前注入（幂等，见模块级注释）
            _patch_lark_ws_connect()

            # 创建事件处理器
            # 关键：直接传递 encrypt_key 和 verification_token（即使是空字符串）
            # 不要传 dummy 值！SDK 的 _do_without_validation 方法（WebSocket 使用）
            # 会跳过验证/解密，所以空值完全 OK
            handler = (
                EventDispatcherHandler.builder(
                    self._encrypt_key or "",
                    self._verification_token or "",
                )
                .register_p2_im_message_receive_v1(self._on_feishu_message)
                # 卡片回传交互（依赖 vendor ws client 的 CARD 帧分发补丁）
                .register_p2_card_action_trigger(self._on_card_action)
                .build()
            )

            # 创建 WebSocket 客户端 - 传入 domain 参数
            self._ws_client = FeishuWSClient(
                app_id=self._app_id,
                app_secret=self._app_secret,
                event_handler=handler,
                domain=FEISHU_DOMAIN,
                log_level=lark.LogLevel.DEBUG,
            )

            # 启动独立 handler loop
            self._start_handler_loop()

            # 重置重连计数：connect() 是全新一次连接（用户开关 / 启动期补启），
            # 不是被动断线后的续接，不应继承上一轮的 attempts
            self._reconnect_attempts = 0
            self._spawn_ws_thread()

            self._running = True
            self._connected = True

            logger.info("[Feishu] Connected successfully (WebSocket)")
            return True

        except Exception as e:
            logger.error("[Feishu] Failed to connect: {}", e)
            self._last_error = f"连接失败: {e}"
            import traceback

            traceback.print_exc()
            return False

    def _start_handler_loop(self) -> None:
        """启动独立的事件循环线程，用于调度消息处理回调"""
        if self._handler_loop is not None:
            return
        self._handler_loop = asyncio.new_event_loop()
        self._handler_loop_thread = threading.Thread(
            target=self._run_handler_loop,
            name="FeishuHandlerLoop",
            daemon=True,
        )
        self._handler_loop_thread.start()

    def _run_handler_loop(self) -> None:
        """运行消息处理事件循环"""
        asyncio.set_event_loop(self._handler_loop)
        self._handler_loop.run_forever()

    def _spawn_ws_thread(self) -> None:
        """拉起 ws 客户端线程（首次 connect 与被动断线重连共用）。

        抽成独立方法的原因：重连路径需在旧线程内换新线程，若在
        _run_feishu_client 里直接递归调用自身会线程套线程、无法退出。
        """
        self._last_error = None  # 新一次连接尝试：旧错误作废，失败会重新写入
        self._feishu_thread = threading.Thread(
            target=self._run_feishu_client,
            name="FeishuWSClient",
            daemon=True,
        )
        self._feishu_thread.start()

    def _run_feishu_client(self) -> None:
        """在独立线程中运行飞书客户端

        参考 hermes-agent 的 _run_official_feishu_ws_client 实现。
        关键：
        1. 创建独立事件循环并设置到线程
        2. 同时设置 lark_oapi.ws.client 模块的 loop 变量
           （WS 客户端的 _reconnect / _ping_loop 等方法依赖此变量）
        """
        try:
            import lark_oapi.ws.client as ws_client_module

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._ws_loop = loop

            # 关键！设置 ws 模块的全局 loop，否则 WS client 内部会使用
            # 模块导入时的原始事件循环（可能是主线程的），导致事件循环冲突
            ws_client_module.loop = loop

            # 运行客户端
            try:
                self._ws_client.start()
            except asyncio.CancelledError:
                # disconnect() 停止 loop 时会 cancel 所有任务，属正常退出路径
                logger.debug("[Feishu] WS client cancelled (expected on stop)")
            except Exception as e:
                msg = str(e).lower()
                if "event loop" not in msg and "running" not in msg:
                    logger.error("[Feishu] Client error: {}", e)
                else:
                    logger.debug("[Feishu] Client stopped (expected): {}", e)
            finally:
                self._ws_loop = None
                loop.close()

            # 被动断线自愈：非主动停止 + 仍标记运行中 → 退避重连
            if not self._stop_event.is_set() and self._running:
                self._schedule_ws_reconnect()

        except Exception as e:
            logger.error("[Feishu] Thread error: {}", e)

    def _schedule_ws_reconnect(self) -> None:
        """ws 线程被动退出后的补偿重连（退避 + 次数上限）。

        背景：lark SDK 的 auto_reconnect 只覆盖自身驱动协程内的重连窗口，
        驱动协程一旦退出 start() 即返回、本线程结束、loop 关闭，而
        _connected 仍为 True 无人复位 → 宿主停在「假连接」，消息静默丢失
        直到重启。此处做补偿。

        在旧 ws 线程内 sleep 后经 _spawn_ws_thread 换新线程，不递归自身。
        """
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error(
                "[Feishu] 被动断线重连达上限 {} 次，停止重连（需重启或重开关插件）",
                self._max_reconnect_attempts,
            )
            self._last_error = (
                f"断线重连 {self._max_reconnect_attempts} 次仍失败，请手动重连"
            )
            self._connected = False
            self._running = False
            return
        self._reconnect_attempts += 1
        # 线性退避 2s/4s/6s/8s/10s，给对端与网络恢复留时间
        delay = min(2 * self._reconnect_attempts, 10)
        logger.warning(
            "[Feishu] 连接意外断开，{}s 后第 {}/{} 次重连",
            delay,
            self._reconnect_attempts,
            self._max_reconnect_attempts,
        )
        # 可被 stop_event 打断：用户主动停时不必等满 delay
        if self._stop_event.wait(delay):
            logger.debug("[Feishu] 重连等待期内收到停止信号，取消重连")
            return
        try:
            self._spawn_ws_thread()
        except Exception as e:
            logger.error("[Feishu] 重连失败: {}", e)
            self._last_error = f"重连失败: {e}"
            self._connected = False
            self._running = False

    def _on_feishu_message(self, data: Any) -> None:
        """处理接收到的飞书消息

        注意：lark_oapi SDK 的 WebSocket 模式通过 _do_without_validation 分发事件，
        回调接收到的 data 是 P2ImMessageReceiveV1 对象，结构为:
            data.event          -> P2ImMessageReceiveV1Data
                .message       -> EventMessage
                    .message_id, .chat_id, .chat_type, .message_type,
                    .content (JSON 字符串, 如 '{"text":"hello"}')
                .sender        -> EventSender
                    .sender_id  -> UserId {open_id, user_id, union_id}
                    .sender_type, .tenant_key
        """
        try:
            # 获取 event 包装层 (P2ImMessageReceiveV1Data)
            event_wrapper = getattr(data, "event", None)
            if event_wrapper is None:
                logger.debug("[Feishu] No event wrapper in callback data")
                return

            # 获取消息对象
            message = getattr(event_wrapper, "message", None)
            sender = getattr(event_wrapper, "sender", None)

            if message is None:
                logger.debug("[Feishu] No message in callback data")
                return
            logger.info(
                "[Feishu] 收到原始消息: message_id={} chat_id={} chat_type={} msg_type={}",
                getattr(message, "message_id", ""),
                getattr(message, "chat_id", ""),
                getattr(message, "chat_type", ""),
                getattr(message, "message_type", ""),
            )

            # 提取字段
            message_id = str(getattr(message, "message_id", "") or "")
            chat_id = str(getattr(message, "chat_id", "") or "")
            chat_type = str(getattr(message, "chat_type", "p2p") or "p2p")

            # EventMessage 使用 message_type（而不是 msg_type），content 是 JSON 字符串
            msg_type = str(getattr(message, "message_type", "text") or "text")
            content_str = str(getattr(message, "content", "") or "")

            # 解析 content JSON：文本 + 图片 key（单图 image 消息、post 富文本混排）
            text, image_keys, file_items = self._parse_message_content(content_str)

            # @提及处理：飞书群聊 @机器人 发命令时 text 形如 "@_user_1 /model"
            # （机器占位符格式），前缀会让宿主 startswith("/") 判定失败、命令被
            # 当普通对话送给 AI。只剥指向机器人自己（mentioned_type="app"）的
            # 占位符；@人的占位符换成 @真实名字（语义不丢）。
            import re as _re

            # 提取 sender_id（群消息留档与事件构造都要用，故前置）
            sender_id = ""
            if sender is not None:
                sender_id_obj = getattr(sender, "sender_id", None)
                if sender_id_obj is not None:
                    sender_id = (
                        getattr(sender_id_obj, "open_id", "")
                        or getattr(sender_id_obj, "user_id", "")
                        or getattr(sender_id_obj, "union_id", "")
                        or ""
                    )

            mentions = getattr(message, "mentions", None) or []
            bot_keys = {
                m.key
                for m in mentions
                if getattr(m, "key", None) and getattr(m, "mentioned_type", "") == "app"
            }
            name_by_key = {
                m.key: f"@{m.name}" for m in mentions if getattr(m, "key", None)
            }
            if str(getattr(message, "chat_type", "p2p") or "p2p") == "group":
                # 群消息先留档（含没 @机器人 的），被叫住时才有前文可参考
                self._capture_group_message(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=_re.sub(r"@_user_\d+", "", text).strip(),
                    user_id=sender_id,
                )
                if self._require_mention and not bot_keys:
                    # 群里没 @机器人：不响应，避免抢话（与 telegram/discord 一致）
                    logger.debug("[Feishu] 群消息未 @机器人，跳过: chat_id={}", chat_id)
                    return
            lead = _re.match(r"^(@_user_\d+)\s*", text)
            if lead and (not mentions or lead.group(1) in bot_keys):
                # 开头的机器人提及剥掉（mentions 缺失时防御性剥，@_user_N
                # 为机器格式不会自然出现在正文）
                text = text[lead.end():]
            if name_by_key:
                text = _re.sub(
                    r"@\S+", lambda mm: name_by_key.get(mm.group(0), mm.group(0)), text
                )
            text = text.strip()

            # 宽松命令提取：@<任意提及> + 斜杠命令 → 剥成纯命令。
            # 覆盖三种透传形态：@_user_1 /model（机器占位符）、@drifox /model
            # （机器人名直书）、@_user_1 机器人名 /model（占位符已被上文
            # mention 替换）。仅当剥离结果以 "/" 开头才生效——普通 @人消息
            # （"@张三 你好"）不匹配、零误伤。
            _m = _re.match(r"^@\S+\s+(/\S+.*)$", text)
            if _m:
                text = _m.group(1).strip()

            # 跳过空消息（无文本、无图片、无文件，如表情包/语音）
            if not text and not image_keys and not file_items:
                logger.debug("[Feishu] Empty message skipped: msg_type={}", msg_type)
                return

            # 构建 MessageEvent
            event = MessageEvent(
                text=text,
                message_type=(
                    MessageType.IMAGE
                    if image_keys
                    else MessageType.FILE
                    if file_items
                    else MessageType.TEXT
                    if msg_type == "text"
                    else MessageType.FILE
                ),
                message_id=message_id,
                chat_id=chat_id,
                user_id=sender_id,
                user_name=sender_id,
                platform="feishu",
                chat_type="group" if chat_type == "group" else "dm",
                media_urls=[],
                media_types=[],
            )

            logger.info(
                "[Feishu] 消息待分发: text={!r} images={} handler_set={} loop_running={}",
                text[:50],
                len(image_keys),
                self._message_handler is not None,
                (self._handler_loop is not None and self._handler_loop.is_running()),
            )
            if self._message_handler:
                try:
                    # 重要：WS client 回调运行在 WS 线程的事件循环中，
                    # 不能在此调用 asyncio.run()，会触发 RuntimeError。
                    # 下载图片与消息处理都投递到独立 handler_loop。
                    loop = self._handler_loop
                    if loop is not None and loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            self._download_and_dispatch(event, message_id, image_keys, file_items),
                            loop,
                        )
                        logger.info(
                            "[Feishu] 已投递至宿主 handler: message_id={}",
                            message_id,
                        )
                    else:
                        logger.error("[Feishu] Handler loop not running, dropping message")
                except Exception as e:
                    logger.error("[Feishu] Handle message error: {}", e)

        except Exception as e:
            logger.error("[Feishu] Parse message error: {}", e)
            import traceback

            traceback.print_exc()

    def _capture_group_message(self, **fields) -> None:
        """群消息留档到宿主存档（失败不影响消息处理）。"""
        try:
            from app.gateway.group_history import get_group_history_store

            get_group_history_store().capture(
                "feishu", fields.pop("chat_id"), chat_type="group", **fields
            )
        except Exception as e:
            logger.debug("[Feishu] 群消息留档失败: {}", e)

    # ==================== 卡片按钮回传（card.action.trigger） ====================

    # ==================== 入站图片 ====================

    @staticmethod
    def _parse_message_content(content_str: str) -> Tuple[str, List[str], List[Tuple[str, str]]]:
        """解析消息 content（JSON 字符串）→ (文本, 图片 key 列表, 文件列表)。

        文件列表元素为 ``(file_key, file_name)``。

        覆盖 ``image`` 单图消息、``post`` 富文本混排（img/text/a 元素），
        其余类型退化为纯文本；解析失败按原文当文本处理（旧行为）。
        """
        if not content_str:
            return "", [], []
        try:
            data = json.loads(content_str)
        except (json.JSONDecodeError, TypeError):
            return content_str, [], []
        if not isinstance(data, dict):
            return "", [], []

        image_key = data.get("image_key")
        if isinstance(image_key, str) and image_key:
            text = data.get("text")
            return (text if isinstance(text, str) else ""), [image_key], []

        file_key = data.get("file_key")
        if isinstance(file_key, str) and file_key:
            name = data.get("file_name")
            return "", [], [(file_key, name if isinstance(name, str) else "")]

        blocks = data.get("content")
        if isinstance(blocks, list):
            lines: List[str] = []
            keys: List[str] = []
            title = data.get("title")
            if isinstance(title, str) and title.strip():
                lines.append(title.strip())
            for paragraph in blocks:
                if not isinstance(paragraph, list):
                    continue
                segment: List[str] = []
                for element in paragraph:
                    if not isinstance(element, dict):
                        continue
                    tag = str(element.get("tag") or "").lower()
                    if tag == "img":
                        key = element.get("image_key")
                        if isinstance(key, str) and key:
                            keys.append(key)
                    elif tag in ("text", "a", "link"):
                        segment.append(str(element.get("text") or ""))
                line = "".join(segment).strip()
                if line:
                    lines.append(line)
            return "\n".join(lines), keys, []

        text = data.get("text")
        return (text if isinstance(text, str) else ""), [], []

    async def _download_and_dispatch(
        self,
        event: MessageEvent,
        message_id: str,
        image_keys: List[str],
        file_items: Optional[List[Tuple[str, str]]] = None,
    ) -> None:
        """下载入站图片并填充 media_urls，再交给宿主 handler。

        下载失败不阻断消息：文本照常送，图片缺哪张记哪张。
        """
        if image_keys:
            try:
                for key in image_keys[:MAX_INBOUND_IMAGES]:
                    path = await self._download_resource(message_id, key, "image")
                    if path:
                        event.media_urls.append(path)
                        event.media_types.append("image")
            except Exception as e:
                logger.warning("[Feishu] 入站图片下载失败: {}", e)
        if file_items:
            try:
                for file_key, file_name in file_items[:MAX_INBOUND_IMAGES]:
                    path = await self._download_resource(
                        message_id, file_key, "file", display_name=file_name
                    )
                    if path:
                        event.media_urls.append(path)
                        event.media_types.append("file")
            except Exception as e:
                logger.warning("[Feishu] 入站文件下载失败: {}", e)
        if self._message_handler:
            try:
                await self._message_handler(event)
            except Exception as e:
                logger.error("[Feishu] Handle message error: {}", e)

    async def _download_resource(
        self,
        message_id: str,
        file_key: str,
        resource_type: str = "image",
        display_name: str = "",
    ) -> Optional[str]:
        """下载消息资源到本地缓存，返回路径；失败返回 None。

        需要租户权限 ``im:message:readonly``（拉取单聊/群组消息资源）。
        飞书未提供仅限图片的更窄权限，文件下载走同一接口（type=file）。
        """
        if not message_id or not file_key:
            return None
        token = await self._get_access_token()
        if not token:
            logger.warning("[Feishu] 下载资源失败：无 access token")
            return None

        client = self._http_client
        owns_client = client is None
        if client is None:
            import httpx

            client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        try:
            response = await client.get(
                f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{file_key}",
                params={"type": resource_type},
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code != 200:
                logger.warning(
                    "[Feishu] 资源下载失败 HTTP {}: {}",
                    response.status_code,
                    response.text[:200],
                )
                return None
            data = response.content
            if not data:
                return None
            if len(data) > MAX_INBOUND_IMAGE_BYTES:
                logger.warning(
                    "[Feishu] 图片超过 {}MB，已跳过: {}",
                    MAX_INBOUND_IMAGE_BYTES // (1024 * 1024),
                    len(data),
                )
                return None
            import hashlib

            digest = hashlib.sha1(data).hexdigest()[:16]
            safe_name = _safe_file_name(display_name)
            if safe_name:
                path = _cache_dir() / f"{digest[:8]}_{safe_name}"
            else:
                path = _cache_dir() / f"{digest}{_image_ext(data)}"
            if not path.exists():
                path.write_bytes(data)
            return str(path)
        except Exception as e:
            logger.warning("[Feishu] 资源下载异常: {}", e)
            return None
        finally:
            if owns_client:
                await client.aclose()

    def _on_card_action(self, data: Any) -> Any:
        """处理交互卡片按钮点击：取出按钮携带的命令并注入消息回环。

        与手敲命令完全同路（_message_handler → 宿主 GatewayEngine.process），
        命令结果由宿主作为新消息发回会话。
        """
        from app.gateway.base import MessageEvent, MessageType

        try:
            event = getattr(data, "event", None)
            if event is None:
                return self._card_toast("error", "无效的卡片回调")

            action = getattr(event, "action", None)
            value = getattr(action, "value", None)
            if not isinstance(value, dict):
                return self._card_toast("error", "未知按钮指令")
            # 两类按钮：提问卡作答（drifox_answer）与命令卡（drifox_cmd）
            answer = str(value.get("drifox_answer", "") or "").strip()
            cmd = str(value.get("drifox_cmd", "") or "").strip()
            if answer:
                text = answer
                toast = f"✅ 已选择 {answer[:30]}"
            elif cmd.startswith("/"):
                text = cmd
                toast = f"⏳ 已执行 {cmd[:40]}"
            else:
                return self._card_toast("error", "未知按钮指令")

            context = getattr(event, "context", None)
            chat_id = str(getattr(context, "open_chat_id", "") or "") if context else ""
            if not chat_id:
                return self._card_toast("error", "缺少会话上下文")

            operator = getattr(event, "operator", None)
            operator_id = str(getattr(operator, "open_id", "") or "card_user") if operator else "card_user"

            ev = MessageEvent(
                text=text,
                message_type=MessageType.TEXT,
                message_id="",
                chat_id=chat_id,
                user_id=operator_id,
                user_name=operator_id,
                platform="feishu",
                chat_type="dm",
                media_urls=[],
                media_types=[],
            )

            if self._message_handler:
                loop = self._handler_loop
                if loop is not None and loop.is_running():
                    asyncio.run_coroutine_threadsafe(self._message_handler(ev), loop)
                    logger.info("[Feishu] Card action injected: {}", text[:80])
                    if answer:
                        # 作答卡点击后退役按钮：否则重复点会被当成新的用户消息再发一轮
                        msg_id = str(getattr(context, "open_message_id", "") or "")
                        if msg_id:
                            asyncio.run_coroutine_threadsafe(
                                self._retire_question_card(msg_id, answer), loop
                            )
                    return self._card_toast("success", toast)
                logger.error("[Feishu] Handler loop not running, card action dropped")
                return self._card_toast("error", "处理循环不可用")

            return self._card_toast("error", "消息处理器未就绪")

        except Exception as e:
            logger.error("[Feishu] Card action error: {}", e)
            return self._card_toast("error", "处理失败")

    async def _retire_question_card(self, message_id: str, answer: str) -> None:
        """把已作答的提问卡替换成静态回执（尽力而为，失败只记 debug）。

        不退役的话卡片按钮仍然可点，重复点击会作为新消息再触发一轮对话。
        """
        try:
            card = {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": "✅ 已作答"},
                    "template": "green",
                },
                "elements": [
                    {"tag": "markdown", "content": f"你的选择：**{answer}**"},
                ],
            }
            await self._api_request(
                "PATCH",
                f"im/v1/messages/{message_id}",
                {"content": json.dumps(card, ensure_ascii=False)},
            )
        except Exception as e:
            logger.debug("[Feishu] 提问卡退役失败（忽略）: {}", e)

    @staticmethod
    def _card_toast(toast_type: str, msg: str):
        """构建卡片回调响应（点击后的轻提示）"""
        from lark_oapi.event.callback.model.p2_card_action_trigger import (
            P2CardActionTriggerResponse,
        )

        return P2CardActionTriggerResponse({"toast": {"type": toast_type, "content": msg}})

    async def disconnect(self) -> None:
        """断开连接（幂等）：真正关闭 ws 连接、停止线程与事件循环

        lark_oapi ws Client 没有任何公开停止机制（无 stop()/close()/_running，
        start() 永久阻塞在 run_until_complete(_select())，ping/receive 均为
        while True，auto_reconnect 默认无限重连）。历史 bug：旧实现靠
        hasattr 探测 stop/close/_running 三个分支全部落空 → 连接/线程/loop
        永生，每次 stop/热重载/开关泄漏一条长连接。

        正确关闭序列：
        1. 禁用 SDK 自动重连（否则断连后 SDK 会无限重连回来）
        2. 经 ws 线程自己的 loop 调度 client._disconnect() 真正关闭连接
        3. cancel loop 上全部任务并停 loop（run_until_complete 返回，线程退出）
        4. join ws 线程（带超时，防卡死）
        5. 停 handler loop 并 join 线程
        """
        self._running = False
        self._connected = False
        self._stop_event.set()

        # 先取走引用再清理（防并发重入 connect 双写状态）
        client = self._ws_client
        ws_loop = self._ws_loop
        ws_thread = self._feishu_thread
        self._ws_client = None
        self._ws_loop = None
        self._feishu_thread = None

        # 1+2. 禁自动重连 + 在 ws loop 上真正关闭连接
        if client is not None and ws_loop is not None and ws_loop.is_running():
            try:
                client._auto_reconnect = False
            except Exception:
                pass
            try:
                fut = asyncio.run_coroutine_threadsafe(client._disconnect(), ws_loop)
                fut.result(timeout=3)
            except Exception as e:
                logger.debug("[Feishu] Disconnect note: {}", e)

        # 3+4. 两阶段优雅关闭 ws loop，等待 ws 线程退出。
        # lark SDK 的 ws 线程阻塞在 run_until_complete(<驱动协程>)（常驻为
        # _select；重连窗口为 _reconnect），驱动协程被 cancel 时其完成回调
        # 会立即 stop loop。若一次回调里 cancel 全部任务再 stop：业务任务
        # （ping/receive）停在 cancelling 态到不了终态 → loop.close() 后 GC
        # 报 "Task was destroyed but it is pending"。
        # 两阶段：①cancel 业务任务（排除驱动），0.15s 内全部到达终态；
        # ②再 cancel 驱动任务 → run_until_complete 以 CancelledError 返回 →
        # _run_feishu_client except CancelledError 静默退出 → finally close，
        # 此时无 pending 任务，零警告。
        if ws_loop is not None and ws_loop.is_running():

            def _cancel_and_stop(loop: asyncio.AbstractEventLoop) -> None:
                # run_until_complete 正在驱动的协程名（lark ws client.py）
                _DRIVERS = {"_select", "_reconnect"}
                driver = None
                for task in asyncio.all_tasks(loop):
                    coro_name = getattr(task.get_coro(), "__name__", "")
                    if coro_name in _DRIVERS and not task.done():
                        driver = task
                        continue
                    task.cancel()

                def _stop_driver() -> None:
                    if driver is not None and not driver.done():
                        driver.cancel()
                    else:
                        loop.stop()

                loop.call_later(0.15, _stop_driver)

            try:
                ws_loop.call_soon_threadsafe(_cancel_and_stop, ws_loop)
            except Exception as e:
                logger.debug("[Feishu] Stop ws loop note: {}", e)

        if ws_thread is not None and ws_thread.is_alive():
            ws_thread.join(timeout=3)
            if ws_thread.is_alive():
                logger.warning("[Feishu] WS client thread did not exit in 3s (may leak)")

        # 5. 停止 handler loop（join 后再清引用，消除"Handler loop not running"竞态窗口）
        handler_loop = self._handler_loop
        handler_thread = self._handler_loop_thread
        if handler_loop is not None and handler_loop.is_running():
            try:
                handler_loop.call_soon_threadsafe(handler_loop.stop)
            except Exception:
                pass
        if handler_thread is not None and handler_thread.is_alive():
            handler_thread.join(timeout=2)
        self._handler_loop = None
        self._handler_loop_thread = None

        # 关闭共享 HTTP 客户端
        if self._http_client is not None:
            try:
                await self._http_client.aclose()
            except Exception:
                pass
            self._http_client = None

        # 清除 token 缓存
        self._token = None
        self._token_expiry = 0.0

        logger.info("[Feishu] Disconnected")

    # ==================== 流式回复（CardKit 卡片） ====================

    # CardKit 流式卡片模板：固定 element_id=stream_md，供逐次追加内容
    _STREAM_CARD_TEMPLATE = {
        "schema": "2.0",
        "config": {"streaming_mode": True, "update_multi": True},
        "body": {
            "elements": [
                {"tag": "markdown", "element_id": "stream_md", "content": ""},
            ]
        },
    }
    _STREAM_CONTENT_LIMIT = 30000  # cardkit 元素内容上限内留余量

    def supports_streaming(self, chat_id: str) -> bool:
        """飞书走 CardKit 流式卡片：过程可见，不必等全量生成完再发。"""
        return True

    async def start_stream(self, chat_id: str) -> Optional[str]:
        """建流式卡片并发出，返回 stream_key=``cardkit:<card_id>``；失败返回 None。"""
        try:
            created = await self._api_request(
                "POST",
                "cardkit/v1/cards",
                {
                    "type": "card_json",
                    "data": json.dumps(self._STREAM_CARD_TEMPLATE, ensure_ascii=False),
                },
            )
            card_id = str((created.get("data") or {}).get("card_id") or "")
            if not card_id:
                raise RuntimeError("cardkit 未返回 card_id")
            await self._api_request(
                "POST",
                "im/v1/messages?receive_id_type=chat_id",
                {
                    "receive_id": chat_id,
                    "msg_type": "interactive",
                    "content": json.dumps({"type": "card", "data": {"card_id": card_id}}),
                },
            )
            await self._api_request(
                "PATCH",
                f"cardkit/v1/cards/{card_id}/settings",
                {"settings": json.dumps({"config": {"streaming_mode": True, "update_multi": True}}, ensure_ascii=False), "sequence": 1},
            )
        except Exception as e:
            logger.warning("[Feishu] start_stream failed: {}", e)
            return None
        self._stream_states[chat_id] = {"card_id": card_id, "sequence": 1}
        return f"cardkit:{card_id}"

    async def update_stream(self, stream_key: str, snapshot: str) -> bool:
        """把可见快照写进卡片；连续失败即熔断，返回 False 让上层放弃流式。"""
        state_key, state = self._resolve_stream_state(stream_key)
        if state is None or state.get("failed"):
            return False
        sequence = int(state.get("sequence") or 0) + 1
        try:
            await self._api_request(
                "PUT",
                f"cardkit/v1/cards/{state['card_id']}/elements/stream_md/content",
                {"content": snapshot[: self._STREAM_CONTENT_LIMIT], "sequence": sequence},
            )
        except Exception as e:
            state["failed"] = True
            logger.debug("[Feishu] stream update failed, fallback to final send: {}", e)
            return False
        state["sequence"] = sequence
        return True

    async def finish_stream(self, stream_key: str, final: str) -> SendResult:
        """写入最终全文并关闭流式模式，然后清理状态。"""
        state_key, state = self._resolve_stream_state(stream_key)
        if state is None:
            return SendResult(success=False, error="unknown stream")
        card_id = state["card_id"]
        sequence = int(state.get("sequence") or 0) + 1
        try:
            await self._api_request(
                "PUT",
                f"cardkit/v1/cards/{card_id}/elements/stream_md/content",
                {"content": (final or "")[: self._STREAM_CONTENT_LIMIT], "sequence": sequence},
            )
            sequence += 1
            await self._api_request(
                "PATCH",
                f"cardkit/v1/cards/{card_id}/settings",
                {"settings": json.dumps({"config": {"streaming_mode": False, "update_multi": True}}, ensure_ascii=False), "sequence": sequence},
            )
        except Exception as e:
            logger.warning("[Feishu] finish_stream failed: {}", e)
            self._stream_states.pop(state_key, None)
            return SendResult(success=False, error=str(e))
        self._stream_states.pop(state_key, None)
        return SendResult(success=True, message_id=stream_key)

    def _resolve_stream_state(self, key: str):
        """按 chat_id 或 ``cardkit:<card_id>`` 定位流状态，兼容两种调用口径。"""
        state = self._stream_states.get(key)
        if state is not None:
            return key, state
        if key.startswith("cardkit:"):
            card_id = key.split(":", 1)[1]
            for state_key, candidate in self._stream_states.items():
                if candidate.get("card_id") == card_id:
                    return state_key, candidate
        return key, None

    async def _api_request(self, method: str, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """调用飞书 OpenAPI，返回解析后的 JSON；非 0 code 抛异常。

        统一出口便于测试替换，也避免每处重复拼 token 与 header。
        """
        token = await self._get_access_token()
        if not token:
            raise RuntimeError("no access token")
        client = self._http_client
        owns_client = client is None
        if client is None:
            import httpx

            client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        try:
            response = await client.request(
                method,
                f"https://open.feishu.cn/open-apis/{endpoint}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            data = response.json() if response.content else {}
            if response.status_code != 200 or data.get("code") not in (0, None):
                raise RuntimeError(
                    f"HTTP {response.status_code} code={data.get('code')} msg={data.get('msg')}"
                )
            return data
        finally:
            if owns_client:
                await client.aclose()

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """发送消息"""
        if not self._connected:
            return SendResult(success=False, error="Not connected")

        try:
            # 获取 token
            token = await self._get_access_token()
            if not token:
                return SendResult(success=False, error="Failed to get access token")

            # 分割长消息
            if len(content) > self.MAX_MESSAGE_LENGTH:
                chunks = self._split_message(content)
            else:
                chunks = [content]

            message_ids = []

            client = self._http_client
            if client is None:
                import httpx

                client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))

            for i, chunk in enumerate(chunks):
                if len(chunks) > 1:
                    chunk = f"[{i + 1}/{len(chunks)}]\n{chunk}"

                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                }

                # 命令响应 → 专属交互卡片（含按钮）；其余 → 通用 Markdown 卡片。
                # 两者失败均自动回退纯文本（下方卡片失败回退逻辑）
                card = self._detect_command_card(chunk) or self._build_markdown_card(chunk)
                json_data = {
                    "receive_id": chat_id,
                    "msg_type": "interactive",
                    "content": json.dumps(card),
                }

                if reply_to and i == 0:
                    endpoint = f"https://open.feishu.cn/open-apis/im/v1/messages/{reply_to}/reply"
                else:
                    endpoint = "https://open.feishu.cn/open-apis/im/v1/messages"

                response = await client.post(
                    endpoint,
                    params={"receive_id_type": "chat_id"},
                    headers=headers,
                    json=json_data,
                )

                # 卡片失败回退纯文本（部分应用未开通卡片消息权限）
                if response.status_code != 200 or response.json().get("code") not in (0, None):
                    logger.warning(
                        "[Feishu] Card send fallback to text: HTTP {} code={}",
                        response.status_code,
                        response.json().get("code"),
                    )
                    json_data = {
                        "receive_id": chat_id,
                        "msg_type": "text",
                        "content": json.dumps({"text": chunk}),
                    }
                    response = await client.post(
                        endpoint,
                        params={"receive_id_type": "chat_id"},
                        headers=headers,
                        json=json_data,
                    )

                if response.status_code == 200:
                    resp_data = response.json()
                    if resp_data.get("code") == 0:
                        message_ids.append(resp_data.get("data", {}).get("message_id", ""))

            return SendResult(
                success=True,
                message_id=message_ids[0] if message_ids else None,
            )

        except Exception as e:
            logger.error("[Feishu] Send failed: {}", e)
            return SendResult(success=False, error=str(e))

    @staticmethod
    def _build_markdown_card(content: str) -> dict:
        """Markdown 文本 → 飞书 interactive 卡片（msg_type=interactive）。

        首行 # 标题提为 header；其余进 Markdown 元素（飞书原生支持
        加粗/斜体/链接/代码块/列表/图片语法，无需转换）。
        """
        import re

        title = ""
        body = content
        m = re.match(r"^\s*#\s+(.+)\n", content)
        if m:
            title = m.group(1).strip()
            body = content[m.end():]

        elements = [
            {
                "tag": "markdown",
                "content": body.strip() or "（空）",
            }
        ]
        card = {"elements": elements}
        if title:
            card["header"] = {
                "title": {"tag": "plain_text", "content": title},
                "template": "blue",
            }
        return card

    # ==================== Gateway 命令输出的专属交互卡片 ====================
    #
    # 识别宿主 GatewayEngine 命令（/help /model /session /agent）的输出文案，
    # 构建带按钮的交互卡片；按钮点击经 card.action.trigger 回传（见
    # _on_card_action），注入命令与手敲完全同路。
    # 文案格式对齐宿主 app/core/engines/gateway/engine.py；宿主改版导致解析
    # 失败时回退 _build_markdown_card，功能不劣化。

    @staticmethod
    def _btn(label: str, cmd: str, btn_type: str = "default", disabled: bool = False) -> dict:
        """交互卡片按钮（回传交互型：value 随 card.action.trigger 返回）"""
        btn = {
            "tag": "button",
            "text": {"tag": "plain_text", "content": label},
            "type": btn_type,
            "value": {"drifox_cmd": cmd},
        }
        if disabled:
            btn["disabled"] = True
        return btn

    @staticmethod
    def _detect_command_card(content: str) -> Optional[dict]:
        """命令输出识别入口：命中返回专属卡片，未命中返回 None"""
        try:
            if content.startswith("🤖 **DriFox Gateway 命令**"):
                return FeishuAdapter._build_help_card()
            if content.startswith("📋 **可用模型**"):
                providers = FeishuAdapter._parse_model_list(content)
                return FeishuAdapter._build_model_card(providers) if providers else None
            if content.startswith("📋 **Gateway 会话**"):
                sessions = FeishuAdapter._parse_session_list(content)
                return FeishuAdapter._build_session_card(sessions) if sessions else None
            if content.startswith("📋 **可用 Agent**"):
                agents = FeishuAdapter._parse_agent_list(content)
                return FeishuAdapter._build_agent_card(agents) if agents else None
        except Exception as e:
            logger.warning("[Feishu] Command card detect failed, fallback: {}", e)
        return None

    @staticmethod
    def _build_help_card() -> dict:
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "🤖 DriFox Gateway 命令"},
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": "**会话管理**\n`/new` `/reset` 重置会话 · `/clear` 清空记录\n`/session` 列出 / 切换历史会话",
                },
                {
                    "tag": "markdown",
                    "content": "**模型 & Agent**\n`/model` 查看 / 切换服务商与模型\n`/agent` 查看 / 切换 Agent",
                },
                {"tag": "hr"},
                {
                    "tag": "action",
                    "actions": [
                        FeishuAdapter._btn("🔄 新会话", "/new", "primary"),
                        FeishuAdapter._btn("📋 模型", "/model"),
                        FeishuAdapter._btn("💬 会话", "/session"),
                        FeishuAdapter._btn("🤖 Agent", "/agent"),
                    ],
                },
                {
                    "tag": "note",
                    "elements": [{"tag": "plain_text", "content": "点按钮直达 · Gateway 会话与桌面端完全隔离"}],
                },
            ],
        }

    @staticmethod
    def _parse_model_list(content: str) -> List[dict]:
        """解析宿主 /model 无参输出 → [{display, current, session, default_model, models[]}]"""
        import re

        providers: List[dict] = []
        cur: Optional[dict] = None
        for line in content.splitlines():
            line = line.rstrip()
            m = re.match(r"^\*\*(.+?)\*\*(.*?)(?: — `(.+?)`)?$", line)
            if m and not line.startswith("  "):
                cur = {
                    "display": m.group(1),
                    "current": "◀" in (m.group(2) or ""),
                    "session": "⚡" in (m.group(2) or ""),
                    "default_model": m.group(3) or "",
                    "models": [],
                }
                providers.append(cur)
                continue
            if cur is None:
                continue
            m2 = re.match(r"^  模型: `(.+?)`$", line)
            if m2:
                cur["default_model"] = m2.group(1)
                continue
            m3 = re.match(r"^  可选: (.+)$", line)
            if m3:
                cur["models"] = re.findall(r"`([^`]+)`", m3.group(1))
        return providers

    @staticmethod
    def _build_model_card(providers: List[dict]) -> dict:
        elements: List[dict] = []
        for p in providers:
            flags = []
            if p["current"]:
                flags.append("◀ 当前服务商")
            if p["session"]:
                flags.append("⚡ 会话覆盖")
            title = f"**{p['display']}**" + (f" {' '.join(flags)}" if flags else "")
            body = title
            if p["default_model"]:
                body += f"\n当前模型: `{p['default_model']}`"
            elements.append({"tag": "markdown", "content": body})

            # 服务商名含空格时宿主命令解析歧义（split(maxsplit=1)），不生成按钮
            has_space = " " in p["display"]
            btn_models = p["models"][:8]
            if not btn_models and p["default_model"] and not has_space:
                btn_models = [p["default_model"]]
            if btn_models and not has_space:
                default = p["default_model"]
                elements.append({
                    "tag": "action",
                    "actions": [
                        FeishuAdapter._btn(
                            m,
                            f"/model {p['display']} {m}",
                            disabled=(m == default and p["current"]),
                        )
                        for m in btn_models
                    ],
                })
            elif p["models"] or p["default_model"]:
                opts = p["models"][:8] or ([p["default_model"]] if p["default_model"] else [])
                elements.append({
                    "tag": "markdown",
                    "content": f"可选: {', '.join(f'`{m}`' for m in opts)}\n*服务商名含空格，暂不支持按钮切换*",
                })
            elements.append({"tag": "hr"})

        if elements and elements[-1].get("tag") == "hr":
            elements.pop()
        elements.append({
            "tag": "note",
            "elements": [{"tag": "plain_text", "content": "点模型按钮立即切换（仅当前 Gateway 会话生效）"}],
        })
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "📋 可用模型"},
                "template": "blue",
            },
            "elements": elements,
        }

    @staticmethod
    def _parse_session_list(content: str) -> List[dict]:
        """解析宿主 /session 无参输出 → [{sid, name, count, current}]"""
        import re

        sessions: List[dict] = []
        for line in content.splitlines():
            m = re.match(r"^- `([^`\s]+)`\.\.\. \*\*(.+?)\*\* \((\d+) 条\)(.*)$", line)
            if m:
                sessions.append({
                    "sid": m.group(1),
                    "name": m.group(2),
                    "count": int(m.group(3)),
                    "current": "◀" in (m.group(4) or ""),
                })
        return sessions

    @staticmethod
    def _build_session_card(sessions: List[dict]) -> dict:
        elements: List[dict] = []
        for s in sessions:
            title = f"**{s['name']}** · {s['count']} 条" + (" ◀ 当前" if s["current"] else "")
            elements.append({
                "tag": "markdown",
                "content": f"{title}\n`{s['sid']}...`",
            })
            elements.append({
                "tag": "action",
                "actions": [
                    FeishuAdapter._btn(
                        "✅ 切换到该会话" if not s["current"] else "当前会话",
                        f"/session {s['sid']}",
                        "primary" if not s["current"] else "default",
                        disabled=s["current"],
                    )
                ],
            })
            elements.append({"tag": "hr"})

        if elements and elements[-1].get("tag") == "hr":
            elements.pop()
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "💬 Gateway 会话"},
                "template": "blue",
            },
            "elements": elements,
        }

    @staticmethod
    def _parse_agent_list(content: str) -> List[dict]:
        """解析宿主 /agent 无参输出 → [{name, desc, current}]"""
        import re

        agents: List[dict] = []
        for line in content.splitlines():
            m = re.match(r"^- \*\*(.+?)\*\*(.*?): (.+)$", line)
            if m:
                agents.append({
                    "name": m.group(1),
                    "desc": m.group(3),
                    "current": "◀" in (m.group(2) or ""),
                })
        return agents

    @staticmethod
    def _build_agent_card(agents: List[dict]) -> dict:
        elements: List[dict] = []
        for a in agents:
            title = f"**{a['name']}**" + (" ◀ 当前" if a["current"] else "")
            elements.append({
                "tag": "markdown",
                "content": f"{title}\n{a['desc']}",
            })
            elements.append({
                "tag": "action",
                "actions": [
                    FeishuAdapter._btn(
                        "✅ 使用该 Agent" if not a["current"] else "使用中",
                        f"/agent {a['name']}",
                        "primary" if not a["current"] else "default",
                        disabled=a["current"],
                    )
                ],
            })
            elements.append({"tag": "hr"})

        if elements and elements[-1].get("tag") == "hr":
            elements.pop()
        elements.append({
            "tag": "note",
            "elements": [{"tag": "plain_text", "content": "点按钮切换 Agent（仅当前 Gateway 会话生效）"}],
        })
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "🤖 可用 Agent"},
                "template": "blue",
            },
            "elements": elements,
        }

    async def _get_access_token(self) -> Optional[str]:
        """获取 tenant access token（带缓存，有效期 2 小时，提前 5 分钟刷新）"""
        import time

        now = time.time()
        if self._token and (now < self._token_expiry - 300):
            return self._token

        try:
            client = self._http_client
            if client is None:
                import httpx

                client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))

            response = await client.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={
                    "app_id": self._app_id,
                    "app_secret": self._app_secret,
                },
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    self._token = data.get("tenant_access_token")
                    self._token_expiry = now + data.get("expire", 7200)
                    return self._token

            return None

        except Exception as e:
            logger.error("[Feishu] Failed to get access token: {}", e)
            return None

    def _split_message(self, content: str) -> List[str]:
        """分割消息（自然边界优先，平台限制内尽量少切）

        宿主不再提供文本分片工具（E2 平台迁出方向），网关自包含实现：
        切点优先换行，其次空格，都不行才硬切，且不早于 55% 上限以防孤片。
        """
        limit = self.MAX_MESSAGE_LENGTH
        body = (content or "").strip()
        if not body:
            return []
        if limit <= 0 or len(body) <= limit:
            return [body]

        floor = int(limit * 0.55)
        chunks: List[str] = []
        remaining = body
        while len(remaining) > limit:
            cut = remaining.rfind("\n", 0, limit)
            if cut < floor:
                cut = remaining.rfind(" ", 0, limit)
            if cut < floor:
                cut = limit
            chunk = remaining[:cut].strip()
            if chunk:
                chunks.append(chunk)
            remaining = remaining[cut:].lstrip()
        if remaining:
            chunks.append(remaining)
        return chunks

    async def send_question(
        self, chat_id: str, question: dict, index: int, total: int
    ) -> SendResult:
        """把交互提问渲染成带按钮的卡片（点按钮即作答）。

        按钮回传走 ``card.action.trigger``（``_on_card_action``），value 里带
        ``drifox_answer``，与手敲文本同路进入宿主的待答状态机。
        多选题卡片无法表达「多选后提交」，直接返回失败让宿主退回文本选项。
        """
        if question.get("multiple"):
            return SendResult(success=False, error="多选题目走文本作答")
        options = [
            opt
            for opt in (question.get("options") or [])
            if str((opt or {}).get("label") or "").strip()
        ][:4]
        if not options:
            return SendResult(success=False, error="无选项，走文本作答")
        title = "🙋 需要你补充信息"
        if total > 1:
            title += f"（{index + 1}/{total}）"
        body_parts = []
        header = str(question.get("header") or "").strip()
        if header:
            body_parts.append(f"**{header}**")
        body_parts.append(str(question.get("question") or "").strip())
        detail = str(question.get("detail") or "").strip()
        if detail:
            body_parts.append(detail)

        actions = []
        for opt in options:
            label = str(opt.get("label") or "").strip()
            actions.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": label},
                    "type": "default",
                    "value": {"drifox_answer": label},
                }
            )

        card = {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": title}, "template": "blue"},
            "elements": [
                {"tag": "markdown", "content": "\n\n".join(body_parts)},
                {"tag": "hr"},
                {"tag": "action", "actions": actions},
                {
                    "tag": "note",
                    "elements": [
                        {"tag": "plain_text", "content": "点按钮直接作答，也可以回复文字或其他内容。"}
                    ],
                },
            ],
        }
        return await self._send_card(chat_id, card)

    async def _send_card(self, chat_id: str, card: dict) -> SendResult:
        """发送 interactive 卡片（提问卡与命令卡共用出口）。"""
        try:
            resp = await self._api_request(
                "POST",
                "im/v1/messages?receive_id_type=chat_id",
                {
                    "receive_id": chat_id,
                    "msg_type": "interactive",
                    "content": json.dumps(card, ensure_ascii=False),
                },
            )
            message_id = (resp.get("data") or {}).get("message_id")
            return SendResult(success=True, message_id=message_id)
        except Exception as e:
            logger.warning("[Feishu] 卡片发送失败: {}", e)
            return SendResult(success=False, error=str(e), retryable=True)

    async def send_image(self, chat_id: str, image_path: str, **kwargs) -> SendResult:
        """发送图片（im/v1/images 上传 → image 消息）"""
        return await self._send_artifact(chat_id, image_path, kind="image")

    async def send_file(self, chat_id: str, file_path: str, **kwargs) -> SendResult:
        """发送文件（im/v1/files 上传 → file 消息）"""
        return await self._send_artifact(chat_id, file_path, kind="file")

    async def _send_artifact(self, chat_id: str, file_path: str, kind: str) -> SendResult:
        """上传本地文件到飞书并发送为 image/file 原生消息。

        协议参考 dsh-im feishu-channel.mjs：图片走 im/v1/images（image_type=message），
        文件走 im/v1/files（file_type=stream），再用返回的 image_key/file_key
        发对应 msg_type 消息。230049 是「结果不确定」错误码，官方建议同 uuid 重试一次。
        """
        from pathlib import Path

        if not self._connected:
            return SendResult(success=False, error="Not connected", retryable=True)
        p = Path(file_path)
        if not p.is_file():
            return SendResult(success=False, error=f"文件不存在: {file_path}", retryable=False)
        token = await self._get_access_token()
        if not token:
            return SendResult(success=False, error="Failed to get access token", retryable=True)
        client = self._http_client
        owns_client = client is None
        if client is None:
            import httpx

            client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
        headers = {"Authorization": f"Bearer {token}"}
        try:
            data = p.read_bytes()
            if kind == "image":
                upload = await client.post(
                    "https://open.feishu.cn/open-apis/im/v1/images",
                    headers=headers,
                    data={"image_type": "message"},
                    files={"image": (p.name, data, "application/octet-stream")},
                )
            else:
                upload = await client.post(
                    "https://open.feishu.cn/open-apis/im/v1/files",
                    headers=headers,
                    data={"file_type": "stream", "file_name": p.name},
                    files={"file": (p.name, data, "application/octet-stream")},
                )
            upload_data = upload.json() if upload.content else {}
            if upload.status_code != 200 or upload_data.get("code") != 0:
                return SendResult(
                    success=False,
                    error=f"上传失败 HTTP {upload.status_code} code={upload_data.get('code')} msg={upload_data.get('msg')}",
                    retryable=upload.status_code >= 500,
                )
            payload = upload_data.get("data") or {}
            key = payload.get("image_key") if kind == "image" else payload.get("file_key")
            if not key:
                return SendResult(success=False, error="上传响应缺少 image_key/file_key", retryable=False)
            content = json.dumps({"image_key": key} if kind == "image" else {"file_key": key})
            body = {"receive_id": chat_id, "msg_type": kind, "content": content}
            url = "https://open.feishu.cn/open-apis/im/v1/messages"
            resp = await client.post(
                url, params={"receive_id_type": "chat_id"}, headers=headers, json=body
            )
            resp_data = resp.json() if resp.content else {}
            if resp_data.get("code") == 230049:
                # 官方文档：结果不确定，同 payload 重试一次由服务端去重
                logger.warning("[Feishu] 消息发送结果不确定（230049），重试一次")
                resp = await client.post(
                    url, params={"receive_id_type": "chat_id"}, headers=headers, json=body
                )
                resp_data = resp.json() if resp.content else {}
            if resp.status_code != 200 or resp_data.get("code") not in (0, None):
                return SendResult(
                    success=False,
                    error=f"发送失败 HTTP {resp.status_code} code={resp_data.get('code')} msg={resp_data.get('msg')}",
                    retryable=True,
                )
            message_id = (resp_data.get("data") or {}).get("message_id")
            logger.info("[Feishu] {} 已发送: {}", "图片" if kind == "image" else "文件", p.name)
            return SendResult(success=True, message_id=message_id)
        except Exception as e:
            logger.error("[Feishu] Send artifact failed: {}", e, exc_info=True)
            return SendResult(success=False, error=str(e), retryable=True)
        finally:
            if owns_client:
                await client.aclose()

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """获取聊天信息"""
        return {"name": chat_id, "type": "dm"}


# ── Phase E 插件注册 ────────────────────────────────────
# 配置由本插件自管（plugin.config.read/write 能力），宿主契约只留行为回调。


PLUGIN_NAME = "gateway-feishu"

_CAPS: dict = {}


def _cap(cap_id: str):
    """取宿主能力（按 manifest capabilities 裁剪；后台线程无 ctx 也可用）。"""
    cap = _CAPS.get(cap_id)
    if cap is None:
        from app.plugins.sdk import caps_for

        cap = caps_for(cap_id, plugin=PLUGIN_NAME, surface="ui")
        if cap is None:
            logger.warning(f"[{PLUGIN_NAME}] 能力不可用: {cap_id}（检查 manifest capabilities）")
            return None
        _CAPS[cap_id] = cap
    return cap


def _config() -> dict:
    """读本插件配置（plugin.config.read 能力，一次取全量）。"""
    reader = _cap("plugin.config.read")
    values = (reader() if reader else {}) or {}
    return {
        "enabled": bool(values.get("enabled")),
        "app_id": values.get("app_id") or "",
        "app_secret": values.get("app_secret") or "",
        "encrypt_key": values.get("encrypt_key") or "",
        "verification_token": values.get("verification_token") or "",
        "require_mention": bool(values.get("require_mention", True)),
    }


def _set_enabled(enabled: bool) -> None:
    writer = _cap("plugin.config.write")
    if writer is not None:
        writer("enabled", bool(enabled))


def _validate() -> tuple:
    cfg = _config()
    return bool(cfg["app_id"] and cfg["app_secret"]), "AppID/Secret 未配置"


def register(registry) -> None:
    from app.plugins.contracts.gateway_platform import GatewayPlatformDef

    registry.register(
        GatewayPlatformDef(
            platform_id="feishu",
            display_name="飞书",
            adapter_factory=FeishuAdapter,
            check_requirements=check_feishu_requirements,
            is_enabled=lambda: _config()["enabled"],
            set_enabled=_set_enabled,
            validate=_validate,
            ui_order=50,
        )
    )
