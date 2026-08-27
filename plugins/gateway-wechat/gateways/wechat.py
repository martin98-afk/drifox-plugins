# -*- coding: utf-8 -*-
"""
微信机器人平台适配器（iLink 官方接口）

通过微信 iLink 官方 Bot 接口通信（纯 HTTP 长轮询，非个人号协议）：
    - 登录: wechat_login 工具扫码（get_bot_qrcode → get_qrcode_status 长轮询）→ bot_token
    - 收消息: POST /ilink/bot/getupdates（40s 长轮询，get_updates_buf 游标）
    - 回复: POST /ilink/bot/sendmessage（需对方 context_token，TTL 24h）

协议参考: openhanako lib/bridge/wechat-adapter.ts（Apache-2.0）与
https://github.com/Tencent/openclaw-weixin（MIT）。

SDK 延迟导入纪律：模块顶层不 eager import 平台 SDK，复用宿主 aiohttp/httpx。
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from app.gateway.base import (
    BasePlatformAdapter,
    ChatInfo,
    MessageEvent,
    MessageType,
    PlatformConfig,
    SendResult,
)

DEFAULT_API_BASE = "https://ilinkai.weixin.qq.com"

# 配置常量
LONG_POLL_TIMEOUT = 45.0  # getupdates 长轮询（服务端 hold 35s + 余量）
REQUEST_TIMEOUT = 15.0
MAX_CONSECUTIVE_FAILURES = 3
BACKOFF_DELAYS = [2, 5, 30]
CONTEXT_TOKEN_TTL = 24 * 3600  # context_token 有效期（秒）
MSG_CHUNK_LIMIT = 4000  # 单条消息文本上限

# iLink 消息类型
ITEM_TEXT = 1
ITEM_IMAGE = 2
ITEM_VOICE = 3
ITEM_FILE = 4
ITEM_VIDEO = 5
MSG_TYPE_BOT = 2
MSG_STATE_FINISH = 2


def check_wechat_requirements() -> bool:
    """检查微信网关依赖是否满足"""
    try:
        import aiohttp  # noqa: F401
        import httpx  # noqa: F401

        return True
    except ImportError:
        return False


class WechatAdapter(BasePlatformAdapter):
    """
    微信 iLink 适配器

    通过官方 iLink Bot 接口长轮询收发单聊消息。
    仅被动回复（对方 24h 内发过消息）；token 失效（errcode -14）后停止等重新扫码。

    配置项:
        - bot_token: iLink bot_token（扫码登录工具自动写入）
    """

    platform = "wechat"
    name = "微信"
    MAX_MESSAGE_LENGTH = MSG_CHUNK_LIMIT

    def __init__(self, config: PlatformConfig, **kwargs):
        super().__init__(config, **kwargs)

        self._bot_token = config.secret or ""

        # 连接资源
        self._http_client: Optional[Any] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._running = False

        # 长轮询游标（持久化，避免重启重复消费）
        self._get_updates_buf: str = ""

        # context_token 缓存（user_id → {token, ts}）被动回复凭据
        self._context_tokens: Dict[str, Dict[str, Any]] = {}

        # 重连退避
        self._backoff_idx = 0

    # ── 连接生命周期 ─────────────────────────────────────

    async def connect(self) -> bool:
        """启动 iLink 长轮询"""
        try:
            import httpx as _httpx
        except ImportError:
            logger.error("[Wechat] httpx not installed. Run: pip install httpx")
            return False

        if not self._bot_token:
            self._last_error = "缺少 bot_token：请在设置卡点「扫码登录」（或让 AI 调 wechat_login 工具）获取"
            logger.warning(f"[Wechat] {self._last_error}")
            return False

        try:
            self._http_client = _httpx.AsyncClient(timeout=LONG_POLL_TIMEOUT)
            self._load_cursor()

            # 探活：一次 getupdates 空轮询验证 token
            ok, expired, err = await self._poll_once()
            if expired:
                self._last_error = f"bot_token 已失效（errcode -14），请重新扫码登录"
                logger.error(f"[Wechat] {self._last_error}")
                await self._cleanup()
                return False
            if err and "HTTP" in str(err):
                self._last_error = f"连接失败: {err}"
                logger.error(f"[Wechat] {self._last_error}")
                await self._cleanup()
                return False

            self._connected = True
            self._running = True
            self._backoff_idx = 0
            self._poll_task = asyncio.create_task(self._poll_loop())
            logger.info("[Wechat] Connected (iLink long-polling)")
            return True

        except Exception as e:
            logger.error(f"[Wechat] Connection failed: {e}", exc_info=True)
            self._last_error = f"连接失败: {e}"
            await self._cleanup()
            return False

    async def disconnect(self) -> None:
        """断开连接"""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        await self._cleanup()
        logger.info("[Wechat] Disconnected")

    async def _cleanup(self) -> None:
        """清理资源"""
        self._connected = False
        self._save_cursor()
        if self._http_client:
            await self._http_client.aclose()
        self._http_client = None

    # ── iLink HTTP API ──────────────────────────────────

    def _api_headers(self) -> Dict[str, str]:
        """iLink 请求头（UIN 随机数照官方参考实现）"""
        import base64
        import os

        uin = base64.b64encode(str(int.from_bytes(os.urandom(4), "big")).encode()).decode()
        return {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "X-WECHAT-UIN": uin,
            "Authorization": f"Bearer {self._bot_token}",
        }

    async def _api_post(self, endpoint: str, body: Dict[str, Any], timeout: float = REQUEST_TIMEOUT) -> Dict[str, Any]:
        """POST iLink 接口；HTTP 非 2xx 或业务 ret!=0 抛异常"""
        url = f"{DEFAULT_API_BASE}/{endpoint}"
        resp = await self._http_client.post(url, json=body, headers=self._api_headers(), timeout=timeout)
        if resp.status_code >= 400:
            raise RuntimeError(f"{endpoint} HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        ret = data.get("ret")
        if ret is not None and ret != 0:
            raise RuntimeError(
                f"{endpoint} ret={ret} errcode={data.get('errcode', '')} errmsg={data.get('errmsg', '')}"
            )
        return data

    @staticmethod
    def _is_session_expired(err: Exception) -> bool:
        """errcode -14：token 失效，不可恢复"""
        msg = str(err)
        return "=-14" in msg or "=-14 " in msg or "errcode=-14" in msg

    # ── 游标持久化 ──────────────────────────────────────

    def _cursor_path(self) -> Path:
        from app.gateway.base import get_cache_dir

        d = get_cache_dir("wechat")
        return d / "cursor.json"

    def _load_cursor(self) -> None:
        try:
            p = self._cursor_path()
            if p.exists():
                self._get_updates_buf = json.loads(p.read_text(encoding="utf-8")).get("get_updates_buf", "")
        except Exception as e:
            logger.debug(f"[Wechat] load cursor failed: {e}")

    def _save_cursor(self) -> None:
        try:
            self._cursor_path().write_text(
                json.dumps({"get_updates_buf": self._get_updates_buf}), encoding="utf-8"
            )
        except Exception as e:
            logger.debug(f"[Wechat] save cursor failed: {e}")

    # ── 长轮询主循环 ────────────────────────────────────

    async def _poll_once(self) -> tuple:
        """一次 getupdates 长轮询。返回 (messages, expired, error)"""
        try:
            data = await self._api_post(
                "ilink/bot/getupdates",
                {"get_updates_buf": self._get_updates_buf, "base_info": {"channel_version": "1.0.0"}},
                timeout=LONG_POLL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            # 长轮询超时属正常（服务端 hold 35s 后空响应）
            return ([], False, None)
        except Exception as e:
            return ([], self._is_session_expired(e), e)

        buf = data.get("get_updates_buf")
        if buf:
            self._get_updates_buf = buf
            self._save_cursor()

        msgs = data.get("msgs") or []
        return (msgs, False, None)

    async def _poll_loop(self) -> None:
        """长轮询循环（指数退避；token 失效即停）"""
        consecutive = 0
        try:
            while self._running:
                msgs, expired, err = await self._poll_once()

                if expired:
                    logger.error("[Wechat] Session expired (errcode -14), polling stopped")
                    self._last_error = "bot_token 已失效，请重新扫码登录"
                    self._connected = False
                    return

                if err is not None:
                    consecutive += 1
                    if consecutive >= MAX_CONSECUTIVE_FAILURES:
                        logger.error(f"[Wechat] Poll failed x{consecutive}: {err}")
                        self._last_error = str(err)[:200]
                    delay = BACKOFF_DELAYS[min(consecutive - 1, len(BACKOFF_DELAYS) - 1)]
                    await asyncio.sleep(delay)
                    continue

                consecutive = 0
                self._backoff_idx = 0
                self._connected = True

                for msg in msgs:
                    try:
                        self._handle_inbound(msg)
                    except Exception as e:
                        logger.error(f"[Wechat] handle_inbound error: {e}", exc_info=True)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[Wechat] Poll loop crashed: {e}", exc_info=True)
            self._last_error = str(e)
            self._connected = False

    # ── 入站消息 ────────────────────────────────────────

    @staticmethod
    def _extract_text(item_list: Optional[List[Dict[str, Any]]]) -> str:
        """提取文本（支持引用回复前缀、语音转文字）"""
        if not item_list:
            return ""
        for item in item_list:
            if item.get("type") == ITEM_TEXT:
                text_item = item.get("text_item") or {}
                text = str(text_item.get("text") or "")
                ref = item.get("ref_msg")
                if not ref:
                    return text
                # 引用消息：拼接 [引用: 标题|正文]
                parts = []
                if ref.get("title"):
                    parts.append(str(ref["title"]))
                ref_item = ref.get("message_item")
                if ref_item:
                    ref_body = WechatAdapter._extract_text([ref_item])
                    if ref_body:
                        parts.append(ref_body)
                if not parts:
                    return text
                return f"[引用: {' | '.join(parts)}]\n{text}"
            if item.get("type") == ITEM_VOICE:
                voice = item.get("voice_item") or {}
                if voice.get("text"):
                    return str(voice["text"])
        return ""

    def _handle_inbound(self, msg: Dict[str, Any]) -> None:
        """处理入站消息 → 标准化 MessageEvent → handle_message"""
        from_user_id = msg.get("from_user_id") or ""
        if not from_user_id or from_user_id.endswith("@im.bot"):
            return

        # 被动回复凭据
        ctx = msg.get("context_token")
        if ctx:
            self._context_tokens[from_user_id] = {"token": ctx, "ts": time.time()}

        text = self._extract_text(msg.get("item_list"))
        if not text.strip():
            logger.debug(f"[Wechat] Non-text message skipped (from={from_user_id[:12]})")
            return

        event = MessageEvent(
            text=text.strip(),
            message_type=MessageType.TEXT,
            message_id=str(msg.get("client_id") or uuid.uuid4()),
            chat_id=f"dm:{from_user_id}",
            user_id=from_user_id,
            user_name=from_user_id.split("@")[0] or "微信用户",
            platform=self.platform,
            chat_type="dm",
        )
        asyncio.get_event_loop().create_task(self.handle_message(event))

    # ── 发送 ────────────────────────────────────────────

    def _get_context_token(self, chat_id: str) -> Optional[str]:
        """取有效 context_token（TTL 内）"""
        _, user_id = chat_id.split(":", 1) if ":" in chat_id else ("dm", chat_id)
        entry = self._context_tokens.get(user_id)
        if not entry:
            return None
        if time.time() - entry["ts"] > CONTEXT_TOKEN_TTL:
            self._context_tokens.pop(user_id, None)
            return None
        return entry["token"]

    async def send(self, chat_id: str, content: str, **kwargs) -> SendResult:
        """发送文本消息（被动回复，需对方 24h 内发过消息）"""
        if not self._http_client:
            return SendResult(success=False, error="Not connected", retryable=True)

        try:
            _, user_id = chat_id.split(":", 1) if ":" in chat_id else ("dm", chat_id)
            ctx = self._get_context_token(chat_id)
            if not ctx:
                return SendResult(
                    success=False,
                    error="需要对方先发消息（24h 被动回复窗口）",
                    retryable=False,
                )

            ok, err = True, None
            for i in range(0, max(len(content), 1), MSG_CHUNK_LIMIT):
                chunk = content[i : i + MSG_CHUNK_LIMIT]
                body = {
                    "msg": {
                        "from_user_id": "",
                        "to_user_id": user_id,
                        "client_id": str(uuid.uuid4()),
                        "message_type": MSG_TYPE_BOT,
                        "message_state": MSG_STATE_FINISH,
                        "item_list": [{"type": ITEM_TEXT, "text_item": {"text": chunk}}],
                        "context_token": ctx,
                    },
                    "base_info": {"channel_version": "1.0.0"},
                }
                try:
                    await self._api_post("ilink/bot/sendmessage", body)
                except Exception as e:
                    ok, err = False, str(e)[:200]
                    logger.error(f"[Wechat] Send failed: {err}")
                    if self._is_session_expired(e):
                        self._last_error = "bot_token 已失效，请重新扫码登录"
                        self._connected = False
                    break

            return SendResult(success=ok, error=err, retryable=(err is None or "HTTP" in str(err)))
        except Exception as e:
            logger.error(f"[Wechat] Send failed: {e}", exc_info=True)
            return SendResult(success=False, error=str(e), retryable=True)

    async def get_chat_info(self, chat_id: str) -> ChatInfo:
        """获取聊天信息（iLink 不提供资料反查，返回占位）"""
        _, user_id = chat_id.split(":", 1) if ":" in chat_id else ("dm", chat_id)
        return ChatInfo(
            name=f"微信用户 {user_id[:10]}…",
            type="dm",
            chat_id=chat_id,
            user_id=user_id,
        )


# ── Phase E 插件注册 ──────────────────────────────
# 配置读写走 PluginConfigStore（E1 契约：插件自包含存储）。闭包内延迟 import，
# 避免模块顶层触发宿主副作用。


def _build_config() -> "PlatformConfig":
    """读 PluginConfigStore 构造微信配置"""
    from app.gateway.base import PlatformConfig
    from app.plugins.managers.plugin_config_store import PluginConfigStore

    store = PluginConfigStore()
    return PlatformConfig(
        enabled=bool(store.get("gateway-wechat", "enabled")),
        platform="wechat",
        bot_id=store.get("gateway-wechat", "bot_token") or "",
        secret=store.get("gateway-wechat", "bot_token") or "",
    )


def _write_config(config: "PlatformConfig") -> None:
    """设置卡保存回调：PlatformConfig → PluginConfigStore"""
    from app.plugins.managers.plugin_config_store import PluginConfigStore

    PluginConfigStore().set_values(
        "gateway-wechat",
        {
            "enabled": config.enabled,
            "bot_token": config.secret or "",
        },
    )


def _build_config_values(values: dict, old_config) -> "PlatformConfig":
    """设置卡保存回调：表单值 → PluginConfigStore → PlatformConfig"""
    from app.gateway.base import PlatformConfig
    from app.plugins.managers.plugin_config_store import PluginConfigStore

    store = PluginConfigStore()
    enabled = values.get("enabled", store.get("gateway-wechat", "enabled"))
    bot_token = values.get("bot_token", "") or store.get("gateway-wechat", "bot_token") or ""
    store.set_values(
        "gateway-wechat",
        {
            "enabled": bool(enabled),
            "bot_token": bot_token,
        },
    )
    return PlatformConfig(
        enabled=bool(enabled),
        platform="wechat",
        bot_id=bot_token,
        secret=bot_token,
    )


def register(registry) -> None:
    from app.plugins.contracts.gateway_platform import GatewayPlatformDef

    registry.register(
        GatewayPlatformDef(
            platform_id="wechat",
            display_name="微信",
            adapter_factory=lambda cfg: WechatAdapter(cfg),
            check_requirements=check_wechat_requirements,
            config_builder=_build_config,
            config_writer=_write_config,
            build_config_values=_build_config_values,
            validate_config=lambda cfg: (
                bool(cfg.secret),
                "缺少 bot_token：请使用 wechat_login 工具扫码登录（或手动粘贴）",
            ),
            ui_order=10,
        )
    )
