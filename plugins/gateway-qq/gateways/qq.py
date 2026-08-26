# -*- coding: utf-8 -*-
"""
QQ 机器人平台适配器（QQ 开放平台）

通过 WebSocket 长连接与 QQ 开放平台 Gateway 通信（群聊 @ 消息 + 单聊消息）。

协议要点:
    - 鉴权: AppID + AppSecret → getAppAccessToken 换 access_token (~7200s)
    - WS 握手: op=10 HELLO → op=2 IDENTIFY(token="QQBot <access_token>", intents)
    - 心跳: op=1 HEARTBEAT(上次 seq) / op=11 HEARTBEAT_ACK
    - 事件: op=0 DISPATCH(t=GROUP_AT_MESSAGE_CREATE / C2C_MESSAGE_CREATE)
    - 回复: OpenAPI POST /v2/groups/{group_openid}/messages 等（msg_id 被动回复）

SDK 延迟导入纪律：模块顶层不 eager import 平台 SDK，复用宿主 aiohttp/httpx。
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, Optional

import aiohttp
from loguru import logger

from app.gateway.base import (
    BasePlatformAdapter,
    ChatInfo,
    MessageEvent,
    MessageType,
    PlatformConfig,
    SendResult,
)

# QQ 开放平台地址
DEFAULT_WS_URL = "wss://api.sgroup.qq.com/websocket"
DEFAULT_API_BASE = "https://api.sgroup.qq.com"
TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"

# OP 协议码
OP_DISPATCH = 0
OP_HEARTBEAT = 1
OP_IDENTIFY = 2
OP_RESUME = 6
OP_RECONNECT = 7
OP_HELLO = 10
OP_HEARTBEAT_ACK = 11

# intents: GROUP_AND_C2C_EVENT（公域群聊 @ 与单聊事件）
INTENTS_GROUP_AND_C2C = 1 << 25

# 配置常量
CONNECT_TIMEOUT = 20.0
REQUEST_TIMEOUT = 15.0
TOKEN_REFRESH_MARGIN = 120.0  # access_token 提前刷新余量（秒）
RECONNECT_BACKOFF = [2, 5, 10, 30, 60]
MAX_MESSAGE_LENGTH = 1800  # QQ 文本消息长度上限（保守值）

# 事件类型 → 聊天类型
EVENT_CHAT_TYPE = {
    "GROUP_AT_MESSAGE_CREATE": "group",
    "C2C_MESSAGE_CREATE": "dm",
}


def check_qq_requirements() -> bool:
    """检查 QQ 网关依赖是否满足"""
    try:
        import aiohttp  # noqa: F401
        import httpx  # noqa: F401

        return True
    except ImportError:
        return False


class QqAdapter(BasePlatformAdapter):
    """
    QQ 开放平台适配器

    通过 WebSocket 长连接与 QQ 机器人 Gateway 通信。

    配置项:
        - appid: 机器人 AppID
        - app_secret: 机器人 AppSecret
        - websocket_url: WebSocket 地址 (可选)
    """

    platform = "qq"  # 第三方平台 id 不经枚举、str 直通（Phase E 契约）
    name = "QQ"
    MAX_MESSAGE_LENGTH = MAX_MESSAGE_LENGTH

    def __init__(self, config: PlatformConfig, **kwargs):
        super().__init__(config, **kwargs)

        self._appid = config.bot_id or ""
        self._app_secret = config.secret or ""
        self._ws_url = config.websocket_url or DEFAULT_WS_URL

        # 连接资源
        self._session: Optional[Any] = None
        self._ws: Optional[Any] = None
        self._http_client: Optional[Any] = None

        # 任务
        self._listen_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False

        # 会话状态
        self._last_seq: Optional[int] = None
        self._session_id: str = ""
        self._heartbeat_interval: float = 30.0

        # access_token 缓存
        self._access_token: str = ""
        self._token_expire_at: float = 0.0
        self._token_lock = asyncio.Lock()

        # 被动回复 msg_id 缓存（chat_id → 最近事件 msg_id）
        self._current_msg_ids: Dict[str, str] = {}

        # 重连退避
        self._backoff_idx = 0

    # ── 连接生命周期 ─────────────────────────────────────

    async def connect(self) -> bool:
        """连接到 QQ 开放平台 WebSocket Gateway"""
        try:
            import aiohttp  # noqa: F401
            import httpx
        except ImportError:
            logger.error("[QQ] aiohttp or httpx not installed. Run: pip install aiohttp httpx")
            return False

        if not self._appid or not self._app_secret:
            logger.error("[QQ] appid and app_secret are required")
            return False

        try:
            # HTTP 客户端（OpenAPI 用）
            import httpx as _httpx

            self._http_client = _httpx.AsyncClient(timeout=30.0)

            # 预取 access_token（IDENTIFY 需要）
            token = await self._get_access_token()
            if not token:
                raise RuntimeError("Failed to get access_token")

            # WebSocket 连接
            self._session = aiohttp.ClientSession(trust_env=True)
            self._ws = await self._session.ws_connect(
                self._ws_url,
                heartbeat=None,  # 心跳走 op 协议自行维护
                timeout=CONNECT_TIMEOUT,
            )

            # HELLO(op=10) → 取心跳间隔
            hello = await self._recv_json()
            if not hello or hello.get("op") != OP_HELLO:
                raise RuntimeError(f"Expected HELLO(op=10), got: {hello}")
            interval_ms = (hello.get("d") or {}).get("heartbeat_interval", 30000)
            self._heartbeat_interval = max(interval_ms / 1000.0, 5.0)

            # IDENTIFY(op=2)
            await self._send_json(
                {
                    "op": OP_IDENTIFY,
                    "d": {
                        "token": f"QQBot {self._access_token}",
                        "intents": INTENTS_GROUP_AND_C2C,
                        "shard": [0, 1],
                    },
                }
            )

            logger.info("[QQ] Connected successfully")

            self._connected = True
            self._running = True
            self._backoff_idx = 0

            # 启动监听和心跳
            self._listen_task = asyncio.create_task(self._listen_loop())
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            return True

        except Exception as e:
            logger.error("[QQ] Connection failed: %s", e, exc_info=True)
            self._last_error = f"连接失败: {e}"
            await self._cleanup()
            return False

    async def disconnect(self) -> None:
        """断开连接"""
        self._running = False

        for task in [self._listen_task, self._heartbeat_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        await self._cleanup()
        logger.info("[QQ] Disconnected")

    async def _cleanup(self) -> None:
        """清理资源"""
        self._connected = False
        self._session_id = ""
        self._last_seq = None

        if self._ws and not self._ws.closed:
            await self._ws.close()
        self._ws = None

        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

        if self._http_client:
            await self._http_client.aclose()
        self._http_client = None

    # ── 收发底层 ─────────────────────────────────────────

    async def _send_json(self, payload: Dict[str, Any]) -> None:
        """发送 JSON 帧"""
        if not self._ws or self._ws.closed:
            raise RuntimeError("WebSocket not connected")
        await self._ws.send_json(payload)

    async def _recv_json(self) -> Optional[Dict[str, Any]]:
        """接收一帧 JSON（忽略非文本帧）"""
        while True:
            msg = await self._ws.receive()
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    return json.loads(msg.data)
                except json.JSONDecodeError:
                    continue
            if msg.type in (
                aiohttp.WSMsgType.CLOSED,
                aiohttp.WSMsgType.CLOSE,
                aiohttp.WSMsgType.CLOSING,
                aiohttp.WSMsgType.ERROR,
            ):
                return None

    # ── access_token 管理 ────────────────────────────────

    async def _get_access_token(self) -> str:
        """获取/刷新 access_token（带锁防并发重复请求）"""
        async with self._token_lock:
            now = time.monotonic()
            if self._access_token and now < self._token_expire_at - TOKEN_REFRESH_MARGIN:
                return self._access_token

            try:
                resp = await self._http_client.post(
                    TOKEN_URL,
                    json={"appId": self._appid, "clientSecret": self._app_secret},
                    headers={"Content-Type": "application/json"},
                )
                data = resp.json()
                token = data.get("access_token", "")
                expires_in = int(data.get("expires_in", 0))
                if not token:
                    logger.error("[QQ] getAppAccessToken failed: %s", data)
                    return ""

                self._access_token = token
                self._token_expire_at = now + max(expires_in, 60)
                logger.info("[QQ] access_token refreshed (expires_in=%ss)", expires_in)
                return token

            except Exception as e:
                logger.error("[QQ] getAppAccessToken error: %s", e, exc_info=True)
                return ""

    # ── 监听与心跳 ───────────────────────────────────────

    async def _listen_loop(self) -> None:
        """监听循环（含断线重连）"""
        try:
            while self._running:
                payload = await self._recv_json()

                if payload is None:
                    logger.warning("[QQ] WebSocket closed by remote")
                    await self._handle_reconnect()
                    continue

                op = payload.get("op")

                if op == OP_DISPATCH:
                    seq = payload.get("s")
                    if seq is not None:
                        self._last_seq = seq
                    event_type = payload.get("t", "")
                    if event_type == "READY":
                        self._session_id = (payload.get("d") or {}).get("session_id", "")
                        logger.info("[QQ] READY (session_id=%s)", self._session_id[:16])
                    else:
                        await self._dispatch_event(event_type, payload.get("d") or {})

                elif op == OP_RECONNECT:
                    logger.info("[QQ] Server requested reconnect")
                    await self._handle_reconnect()

                elif op == OP_HEARTBEAT_ACK:
                    logger.debug("[QQ] Heartbeat ACK")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("[QQ] Listen loop crashed: %s", e, exc_info=True)
            self._last_error = str(e)
            if self._running:
                await self._handle_reconnect()

    async def _handle_reconnect(self) -> None:
        """断线重连（指数退避；token 失效时自动刷新）"""
        was_running = self._running
        await self._cleanup()

        if not was_running:
            return

        while self._running:
            delay = RECONNECT_BACKOFF[min(self._backoff_idx, len(RECONNECT_BACKOFF) - 1)]
            self._backoff_idx += 1
            logger.info("[QQ] Reconnecting in %ss...", delay)
            await asyncio.sleep(delay)

            if await self.connect():
                return

        logger.error("[QQ] Reconnect abandoned (stopped)")

    async def _heartbeat_loop(self) -> None:
        """心跳循环：每 heartbeat_interval 发 op=1"""
        try:
            while self._running:
                await asyncio.sleep(self._heartbeat_interval)
                if self._ws and not self._ws.closed:
                    try:
                        await self._send_json({"op": OP_HEARTBEAT, "d": self._last_seq})
                    except Exception as e:
                        logger.debug("[QQ] Heartbeat failed: %s", e)
        except asyncio.CancelledError:
            pass

    # ── 事件处理 ─────────────────────────────────────────

    async def _dispatch_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """分发消息事件 → 标准化 MessageEvent → handle_message"""
        chat_type = EVENT_CHAT_TYPE.get(event_type)
        if chat_type is None:
            return

        msg_id = data.get("id", "")

        if chat_type == "group":
            group_openid = data.get("group_openid", "")
            sender = ((data.get("group_member_openid") or {}).get("openid")) or group_openid
            chat_id = f"group:{group_openid}"
            user_name = sender
        else:  # dm
            author = data.get("author") or {}
            sender = data.get("user_openid") or author.get("user_openid") or author.get("id", "")
            chat_id = f"dm:{sender}"
            user_name = sender

        text = str(data.get("content") or "").strip()
        if not text:
            logger.debug("[QQ] Empty message skipped (%s)", event_type)
            return

        # 群聊去掉 @机器人 前缀
        if chat_type == "group":
            text = text.lstrip("/@").strip() if text.startswith("@") else text
            import re

            text = re.sub(r"^@\S+\s*", "", text).strip() or text

        event = MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            message_id=msg_id,
            chat_id=chat_id,
            user_id=sender,
            user_name=user_name,
            platform=self.platform,
            chat_type=chat_type,
            metadata={"qq_msg_id": msg_id},
        )
        # 记录被动回复凭据
        if msg_id:
            self._current_msg_ids[chat_id] = msg_id

        await self.handle_message(event)

    # ── 发送 ─────────────────────────────────────────────

    def _parse_chat_id(self, chat_id: str) -> tuple[str, str]:
        """解析内部 chat_id ("group:<openid>" / "dm:<openid>")"""
        if ":" in chat_id:
            prefix, openid = chat_id.split(":", 1)
            return (prefix, openid)
        return ("dm", chat_id)

    def _api_headers(self) -> Dict[str, str]:
        """OpenAPI 请求头"""
        return {"Authorization": f"QQBot {self._access_token}"}

    async def send(self, chat_id: str, content: str, **kwargs) -> SendResult:
        """
        发送文本消息

        被动回复优先复用最近收到的 msg_id（被动消息无额度限制）。
        kwargs 可传 msg_id 显式指定被回复的消息。
        """
        if not self._http_client:
            return SendResult(success=False, error="Not connected", retryable=True)

        try:
            # 确保 token 新鲜（过期自动刷新，避免长连接后 401）
            await self._get_access_token()
            _, openid = self._parse_chat_id(chat_id)
            prefix, _ = self._parse_chat_id(chat_id)
            msg_id = kwargs.get("msg_id") or self._current_msg_ids.get(chat_id, "")
            chunks = self.truncate_message(content)

            ok, err = True, None
            for i, chunk in enumerate(chunks):
                body: Dict[str, Any] = {
                    "content": chunk,
                    "msg_type": 0,
                    "msg_seq": i + 1,
                }
                if msg_id:
                    body["msg_id"] = msg_id

                url = f"{DEFAULT_API_BASE}/v2/users/{openid}/messages"
                if prefix == "group":
                    url = f"{DEFAULT_API_BASE}/v2/groups/{openid}/messages"

                resp = await self._http_client.post(url, json=body, headers=self._api_headers())
                if resp.status_code >= 400:
                    ok = False
                    err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    logger.error("[QQ] Send failed: %s", err)
                    break

            return SendResult(success=ok, error=err)

        except Exception as e:
            logger.error("[QQ] Send failed: %s", e, exc_info=True)
            return SendResult(success=False, error=str(e), retryable=True)

    async def get_chat_info(self, chat_id: str) -> ChatInfo:
        """获取聊天信息（OpenAPI 不提供 openid 反查资料，返回占位信息）"""
        prefix, openid = self._parse_chat_id(chat_id)
        return ChatInfo(
            name=f"QQ {'群' if prefix == 'group' else '用户'} {openid[:12]}…",
            type="group" if prefix == "group" else "dm",
            chat_id=chat_id,
            user_id=openid if prefix != "group" else "",
        )


# ── Phase E 插件注册 ──────────────────────────────
# 配置读写走 PluginConfigStore（E1 契约：插件自包含存储）。闭包内延迟 import，
# 避免模块顶层触发宿主副作用。


def _build_config() -> "PlatformConfig":
    """读 PluginConfigStore 构造 QQ 配置"""
    from app.gateway.base import PlatformConfig
    from app.plugins.managers.plugin_config_store import PluginConfigStore

    store = PluginConfigStore()
    return PlatformConfig(
        enabled=bool(store.get("gateway-qq", "enabled")),
        platform="qq",
        bot_id=store.get("gateway-qq", "appid") or "",
        secret=store.get("gateway-qq", "app_secret") or "",
        websocket_url=(
            store.get("gateway-qq", "websocket_url")
            or "wss://api.sgroup.qq.com/websocket"
        ),
    )


def _write_config(config: "PlatformConfig") -> None:
    from app.plugins.managers.plugin_config_store import PluginConfigStore

    PluginConfigStore().set_values(
        "gateway-qq",
        {
            "enabled": config.enabled,
            "appid": config.bot_id or "",
            "app_secret": config.secret or "",
            "websocket_url": (config.websocket_url or ""),
        },
    )


def _build_config_values(values: dict, old_config) -> "PlatformConfig":
    """设置卡保存回调：表单值 → PluginConfigStore → PlatformConfig。"""
    from app.gateway.base import PlatformConfig
    from app.plugins.managers.plugin_config_store import PluginConfigStore

    store = PluginConfigStore()
    plugin = "gateway-qq"
    enabled = values.get("enabled", store.get(plugin, "enabled"))
    appid = values.get("appid", "")
    app_secret = values.get("app_secret", "")
    websocket_url = values.get("websocket_url", "")
    store.set_values(
        plugin,
        {
            "enabled": bool(enabled),
            "appid": appid,
            "app_secret": app_secret,
            "websocket_url": websocket_url or "wss://api.sgroup.qq.com/websocket",
        },
    )
    return PlatformConfig(
        enabled=bool(enabled),
        platform="qq",
        bot_id=appid,
        secret=app_secret,
        websocket_url=websocket_url or "wss://api.sgroup.qq.com/websocket",
    )


def register(registry) -> None:
    from app.plugins.contracts.gateway_platform import GatewayPlatformDef

    registry.register(
        GatewayPlatformDef(
            platform_id="qq",
            display_name="QQ",
            adapter_factory=lambda cfg: QqAdapter(cfg),
            check_requirements=check_qq_requirements,
            config_builder=_build_config,
            config_writer=_write_config,
            build_config_values=_build_config_values,
            validate_config=lambda cfg: (
                bool(cfg.bot_id and cfg.secret),
                "AppID/AppSecret 未配置",
            ),
            ui_order=9,
        )
    )
