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

from dataclasses import dataclass, field

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

# 流式合并（单聊 stream_messages append 模式）
STREAM_MIN_INTERVAL = 1.2  # 分片最小间隔（官方建议 ≥500ms，留限流余量）
STREAM_IDLE_TIMEOUT = 30.0  # 无后续内容自动收尾（秒）
STREAM_MAX_CHUNK = 1800  # 单分片内容上限
STREAM_UPDATE_MIN_INTERVAL = 0.6  # replace 打字机更新最小间隔（宿主已节流 300ms，插件侧再保险）

# 工具进度前缀（宿主 backend.py 推送）：进度消息只追加不终流；
# 无前缀消息（最终正文）发结束片
PROGRESS_MARKERS = ("🤔", "🔧", "✅")

# 事件类型 → 聊天类型
EVENT_CHAT_TYPE = {
    "GROUP_AT_MESSAGE_CREATE": "group",
    "C2C_MESSAGE_CREATE": "dm",
}


@dataclass
class _StreamState:
    """单聊流式合并状态：
    - mode=append：宿主思考占位/工具进度折叠为一条追加式消息（打字机）
    - mode=replace：宿主全量快照打字机（AI 增量 + 工具进度，单调追加）
    """

    msg_id: str = ""
    mode: str = "append"
    stream_msg_id: str = ""  # 首片响应返回，后续分片携带
    index: int = 0
    buffer: list = field(default_factory=list)  # 待拼接的内容段（append 模式）
    last_snapshot: str = ""  # 最近一次已下发快照（replace 模式）
    last_flush: float = 0.0
    last_activity: float = 0.0
    debounce_task: Optional[asyncio.Task] = None
    watchdog_task: Optional[asyncio.Task] = None
    flushing: bool = False
    prefix_errors: int = 0  # 连续 40007（前缀不一致）计数，≥2 放弃流
    dead: bool = False  # 已放弃（40007 连发 / 接口不可用）


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
        # msg_id → 已用 msg_seq（同一 msg_id 多轮回复需递增，重置会被 QQ 去重吞掉）
        self._msg_seq_counters: Dict[str, int] = {}
        # 单聊流式合并状态（chat_id → _StreamState）；接口不可用时置 False 全部回退普通发送
        self._streams: Dict[str, _StreamState] = {}
        self._stream_available = True
        # RESUME 待确认标记（发过 RESUME 但未收到 READY/RESUMED）
        self._resume_pending: bool = False

        # 重连退避
        self._backoff_idx = 0

    # ── 连接生命周期 ─────────────────────────────────────

    async def connect(self, resume: bool = False) -> bool:
        """连接到 QQ 开放平台 WebSocket Gateway

        resume=True 时优先用已存 session_id/seq 恢复会话（RESUME），
        避免断线期间事件丢失；失败时由 _handle_reconnect 回退全新 IDENTIFY。
        """
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

            # IDENTIFY(op=2) 或 RESUME(op=6)
            if resume and self._session_id and self._last_seq is not None:
                self._resume_pending = True
                await self._send_json(
                    {
                        "op": OP_RESUME,
                        "d": {
                            "token": f"QQBot {self._access_token}",
                            "session_id": self._session_id,
                            "seq": self._last_seq,
                        },
                    }
                )
                logger.info(
                    "[QQ] RESUME sent (session_id=%s, seq=%s)",
                    self._session_id[:16],
                    self._last_seq,
                )
            else:
                self._session_id = ""
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
            # 保留 session_id/seq 供下次 RESUME 尝试
            await self._cleanup(keep_session=True)
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

    async def _cleanup(self, keep_session: bool = False) -> None:
        """清理资源（keep_session=True 保留会话凭据供 RESUME）"""
        self._connected = False
        if not keep_session:
            self._session_id = ""
            self._last_seq = None
        # 清理全部流式任务，避免句柄泄漏
        for st in self._streams.values():
            self._cancel_stream_tasks(st)
        self._streams.clear()

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
                        self._resume_pending = False
                        logger.info("[QQ] READY (session_id=%s)", self._session_id[:16])
                    elif event_type == "RESUMED":
                        self._resume_pending = False
                        logger.info("[QQ] RESUMED (session_id=%s)", self._session_id[:16])
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
        """断线重连（指数退避；优先 RESUME 恢复会话，失败回退 IDENTIFY）"""
        was_running = self._running
        # 上次 RESUME 未获确认 → 会话已失效，放弃恢复
        if self._resume_pending:
            logger.warning("[QQ] RESUME not confirmed, falling back to IDENTIFY")
            self._resume_pending = False
            self._session_id = ""
            self._last_seq = None
        await self._cleanup(keep_session=True)

        if not was_running:
            return

        while self._running:
            delay = RECONNECT_BACKOFF[min(self._backoff_idx, len(RECONNECT_BACKOFF) - 1)]
            self._backoff_idx += 1
            logger.info("[QQ] Reconnecting in %ss...", delay)
            await asyncio.sleep(delay)

            can_resume = bool(self._session_id) and self._last_seq is not None
            if await self.connect(resume=can_resume):
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

        # 群聊去掉 @机器人 前缀（保留 / 命令前缀；兼容 <@!BOT_ID> 官方 mention）
        if chat_type == "group":
            import re

            cleaned = re.sub(r"^(?:<@!\w+>|@\S+)\s*", "", text).strip()
            text = cleaned or text

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
        # 记录被动回复凭据；新 msg_id 到达时同步清理旧计数器，并强制收尾旧流
        if msg_id:
            old_msg_id = self._current_msg_ids.get(chat_id)
            if old_msg_id and old_msg_id != msg_id:
                self._msg_seq_counters.pop(old_msg_id, None)
                self._finalize_stream_force(chat_id)
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
        单聊：宿主的思考占位/工具进度/最终回复折叠为一条流式消息（打字机）；
        群聊：无流式接口，逐条普通发送。
        """
        if not self._http_client:
            return SendResult(success=False, error="Not connected", retryable=True)

        try:
            # 确保 token 新鲜（过期自动刷新，避免长连接后 401）
            await self._get_access_token()
            prefix, openid = self._parse_chat_id(chat_id)
            msg_id = kwargs.get("msg_id") or self._current_msg_ids.get(chat_id, "")

            if (
                prefix == "dm"
                and self._stream_available
                and msg_id
                and not kwargs.get("skip_stream")
            ):
                # replace 打字机流存活期间，普通推送（如错误提示）并入快照，避免两条流交错
                st = self._streams.get(chat_id)
                if st and st.mode == "replace" and not st.dead:
                    return await self._append_to_replace(chat_id, openid, st, content)
                return await self._send_stream(chat_id, openid, msg_id, content)

            return await self._send_plain_chunks(openid, prefix, msg_id, content)

        except Exception as e:
            logger.error("[QQ] Send failed: %s", e, exc_info=True)
            return SendResult(success=False, error=str(e), retryable=True)

    async def _send_plain_chunks(
        self, openid: str, prefix: str, msg_id: str, content: str
    ) -> SendResult:
        """普通逐条发送（分片，msg_seq 递增防判重）"""
        chunks = self.truncate_message(content)

        ok, err = True, None
        # 同一 msg_id 的多轮回复 msg_seq 必须递增，重置会被 QQ 判重吞掉
        seq_start = self._msg_seq_counters.get(msg_id, 0) if msg_id else 0
        for i, chunk in enumerate(chunks):
            body: Dict[str, Any] = {
                "content": chunk,
                "msg_type": 0,
                "msg_seq": seq_start + i + 1,
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

        if ok and msg_id:
            self._msg_seq_counters[msg_id] = seq_start + len(chunks)

        return SendResult(success=ok, error=err)

    # ── 打字机流式钩子（宿主 BasePlatformAdapter 契约） ──

    def supports_streaming(self, chat_id: str) -> bool:
        """单聊支持打字机流式（群聊无 stream_messages 接口）"""
        return (
            self._stream_available
            and self._parse_chat_id(chat_id)[0] == "dm"
            and bool(self._current_msg_ids.get(chat_id))
        )

    async def start_stream(self, chat_id: str) -> Optional[str]:
        """开始 replace 打字机流（幂等；不发网络请求，首片等真实内容）"""
        if not self.supports_streaming(chat_id):
            return None
        st = self._streams.get(chat_id)
        if st and st.mode == "replace":
            return chat_id
        # 旧 append 流（如占位消息）强制收尾，独立成一条小消息
        if st and st.buffer:
            _, openid = self._parse_chat_id(chat_id)
            await self._flush_stream(chat_id, openid, final=True)
        elif st:
            self._finalize_stream_force(chat_id)
        self._streams[chat_id] = _StreamState(
            msg_id=self._current_msg_ids.get(chat_id, ""), mode="replace"
        )
        self._restart_watchdog(chat_id)
        return chat_id

    async def update_stream(self, stream_key: str, snapshot: str) -> bool:
        """推送全量快照（replace 续片）。返回 False 表示流已放弃，宿主应回退普通发送。"""
        chat_id = stream_key
        st = self._streams.get(chat_id)
        if not st or st.mode != "replace" or st.dead:
            return False
        st.last_activity = time.monotonic()

        # 节流：距上次下发太近则跳过本帧（中间帧丢失无害，finish 会补全）
        now = time.monotonic()
        if st.stream_msg_id and now - st.last_flush < STREAM_UPDATE_MIN_INTERVAL:
            return True

        _, openid = self._parse_chat_id(chat_id)
        return await self._send_replace(chat_id, openid, st, snapshot, final=False)

    async def finish_stream(self, stream_key: str, final: str) -> SendResult:
        """结束打字机流（replace 结束片全量收尾）"""
        chat_id = stream_key
        st = self._streams.get(chat_id)
        if not st or st.mode != "replace":
            _, openid = self._parse_chat_id(chat_id)
            msg_id = st.msg_id if st else self._current_msg_ids.get(chat_id, "")
            return await self._send_plain_chunks(openid, "dm", msg_id, final)

        self._cancel_stream_tasks(st)

        if st.dead or not st.stream_msg_id:
            # 流从未发出任何片（AI 极快/全被节流）→ 普通分片发全文
            self._streams.pop(chat_id, None)
            _, openid = self._parse_chat_id(chat_id)
            return await self._send_plain_chunks(openid, "dm", st.msg_id, final)

        _, openid = self._parse_chat_id(chat_id)
        ok = await self._send_replace(chat_id, openid, st, final, final=True)
        self._streams.pop(chat_id, None)
        if not ok:
            # 结束片失败（含 40007）→ 兜底普通分片
            return await self._send_plain_chunks(openid, "dm", st.msg_id, final)
        return SendResult(success=True)

    async def _append_to_replace(
        self, chat_id: str, openid: str, st: _StreamState, content: str
    ) -> SendResult:
        """replace 流存活期间，普通 send 推送并入快照末尾（保持前缀单调）"""
        snapshot = st.last_snapshot + ("\n\n" if st.last_snapshot else "") + content.strip()
        is_progress = content.startswith(PROGRESS_MARKERS)
        ok = await self._send_replace(chat_id, openid, st, snapshot, final=not is_progress)
        if not is_progress:
            self._streams.pop(chat_id, None)
        return SendResult(success=ok)

    async def _send_replace(
        self, chat_id: str, openid: str, st: _StreamState, snapshot: str, final: bool
    ) -> bool:
        """发一个 replace 分片；40007 前缀不一致时跳帧，连续 2 次放弃流。"""
        # 超长内容不进流：结束片发引导语，全文普通分片（由调用方处理）
        overflow = ""
        content = snapshot
        if len(content) > STREAM_MAX_CHUNK:
            if not final:
                return True  # 中间帧超长直接跳过，等 finish 收尾
            overflow = content
            content = "思考完成，完整回复如下 👇"

        body: Dict[str, Any] = {
            "input_mode": "replace",
            "input_state": 10 if final else 1,
            "index": st.index,
            "content_type": "text",
            "content_raw": content,
            "msg_id": st.msg_id,
            "msg_seq": 1,
        }
        if st.stream_msg_id:
            body["stream_msg_id"] = st.stream_msg_id

        try:
            url = f"{DEFAULT_API_BASE}/v2/users/{openid}/stream_messages"
            resp = await self._http_client.post(url, json=body, headers=self._api_headers())
        except Exception as e:
            logger.error("[QQ] replace flush error: %s", e)
            return False

        if resp.status_code >= 400:
            code = ""
            try:
                code = str(resp.json().get("code", ""))
            except Exception:
                code = resp.text[:100]
            logger.error("[QQ] replace flush failed: HTTP %s code=%s", resp.status_code, code)
            if resp.status_code == 400 and "40007" in str(code):
                # 快照前缀跳变（如未闭合标签被清洗）→ 跳帧；连续 2 次放弃
                st.prefix_errors += 1
                if st.prefix_errors >= 2:
                    st.dead = True
                    logger.warning("[QQ] stream abandoned (prefix mismatch x2)")
                    return False
                return True  # 假成功：跳过本帧，后续快照仍有机会对齐
            if resp.status_code in (403, 404) or "50002" in str(code):
                # 接口不可用/限流：放弃流回退普通发送
                st.dead = True
                self._stream_available = False
                return False
            return False

        data = resp.json()
        if not st.stream_msg_id:
            st.stream_msg_id = data.get("id", "")
        st.index += 1
        st.last_flush = time.monotonic()
        st.last_activity = time.monotonic()
        st.last_snapshot = snapshot
        st.prefix_errors = 0

        if overflow:
            await self._send_plain_chunks(openid, "dm", st.msg_id, overflow)
        return True

    # ── 单聊流式合并（stream_messages append 模式） ───────

    async def _send_stream(self, chat_id: str, openid: str, msg_id: str, content: str) -> SendResult:
        """把宿主推的思考占位/工具进度折叠为一条打字机消息（旧宿主链路）。

        - 进度消息（🤔/🔧/✅ 开头）追加续片
        - 无前缀消息（最终正文）立即发结束片（input_state=10）
        - 超长正文不进流，结束片发引导语后普通分片发送
        """
        is_progress = content.startswith(PROGRESS_MARKERS)
        st = self._streams.get(chat_id)
        if st is None or st.msg_id != msg_id:
            # 新会话流：若存在旧流（不同 msg_id），先静默丢弃
            self._cancel_stream_tasks(st)
            st = _StreamState(msg_id=msg_id)
            self._streams[chat_id] = st

        st.buffer.append(content.strip())
        st.last_activity = time.monotonic()
        self._restart_watchdog(chat_id)

        now = time.monotonic()
        if not is_progress or not st.stream_msg_id or now - st.last_flush >= STREAM_MIN_INTERVAL:
            self._cancel_debounce(st)
            return await self._flush_stream(chat_id, openid, final=not is_progress)

        # 未到间隔：合并缓冲，调度定时 flush
        self._schedule_debounce(chat_id, openid, STREAM_MIN_INTERVAL - (now - st.last_flush))
        return SendResult(success=True)

    def _schedule_debounce(self, chat_id: str, openid: str, delay: float) -> None:
        st = self._streams.get(chat_id)
        if not st:
            return
        self._cancel_debounce(st)

        async def _run():
            await asyncio.sleep(max(delay, 0.05))
            s2 = self._streams.get(chat_id)
            if s2 and s2.buffer and not s2.flushing:
                await self._flush_stream(chat_id, openid, final=False)

        st.debounce_task = asyncio.create_task(_run())

    def _restart_watchdog(self, chat_id: str) -> None:
        st = self._streams.get(chat_id)
        if not st:
            return
        self._cancel_watchdog(st)

        async def _run():
            await asyncio.sleep(STREAM_IDLE_TIMEOUT)
            s2 = self._streams.get(chat_id)
            if not s2 or s2.flushing:
                return
            if time.monotonic() - s2.last_activity >= STREAM_IDLE_TIMEOUT - 0.5:
                logger.warning("[QQ] Stream idle timeout, force final flush (chat=%s)", chat_id)
                prefix, openid = self._parse_chat_id(chat_id)
                if s2.mode == "replace":
                    # 宿主崩溃未收尾：已下发过则发结束片，否则静默丢弃
                    self._cancel_stream_tasks(s2)
                    if s2.stream_msg_id and not s2.dead:
                        ok = await self._send_replace(chat_id, openid, s2, s2.last_snapshot, final=True)
                        if not ok:
                            await self._send_plain_chunks(openid, "dm", s2.msg_id, s2.last_snapshot)
                    self._streams.pop(chat_id, None)
                else:
                    await self._flush_stream(chat_id, openid, final=True)

        st.watchdog_task = asyncio.create_task(_run())

    def _cancel_debounce(self, st: Optional[_StreamState]) -> None:
        if st and st.debounce_task and st.debounce_task is not asyncio.current_task():
            st.debounce_task.cancel()
            st.debounce_task = None

    def _cancel_watchdog(self, st: Optional[_StreamState]) -> None:
        if st and st.watchdog_task and st.watchdog_task is not asyncio.current_task():
            st.watchdog_task.cancel()
            st.watchdog_task = None

    def _cancel_stream_tasks(self, st: Optional[_StreamState]) -> None:
        self._cancel_debounce(st)
        self._cancel_watchdog(st)

    def _finalize_stream_force(self, chat_id: str) -> None:
        """新 msg_id 到达时强制丢弃旧流（不发送，避免乱序）"""
        st = self._streams.pop(chat_id, None)
        if st:
            self._cancel_stream_tasks(st)

    async def _flush_stream(self, chat_id: str, openid: str, final: bool) -> SendResult:
        """把缓冲内容发一个分片（首片拿 stream_msg_id；final=True 发结束片）"""
        st = self._streams.get(chat_id)
        if not st or not st.buffer:
            return SendResult(success=True)

        content = "\n\n".join(st.buffer)
        st.buffer = []

        # 超长最终正文：结束片只发引导语，正文普通分片（流式单片长度有限）
        overflow = ""
        if final and len(content) > STREAM_MAX_CHUNK:
            overflow = content
            content = "思考完成，完整回复如下 👇"

        body: Dict[str, Any] = {
            "input_mode": "append",
            "input_state": 10 if final else 1,
            "index": st.index,
            "content_type": "text",
            "content_raw": content,
            "msg_id": st.msg_id,
            "msg_seq": 1,
        }
        if st.stream_msg_id:
            body["stream_msg_id"] = st.stream_msg_id

        st.flushing = True
        try:
            url = f"{DEFAULT_API_BASE}/v2/users/{openid}/stream_messages"
            resp = await self._http_client.post(url, json=body, headers=self._api_headers())

            if resp.status_code >= 400:
                err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                logger.error("[QQ] Stream flush failed: %s", err)
                # 接口不可用：永久回退普通发送，本次内容补发
                self._stream_available = False
                self._streams.pop(chat_id, None)
                self._cancel_stream_tasks(st)
                fallback = content if not overflow else overflow
                result = await self._send_plain_chunks(openid, "dm", st.msg_id, fallback)
                return result

            data = resp.json()
            if not st.stream_msg_id:
                st.stream_msg_id = data.get("id", "")
            st.index += 1
            st.last_flush = time.monotonic()

            if final:
                self._streams.pop(chat_id, None)
                self._cancel_stream_tasks(st)
            elif st.buffer:
                # flush 期间又积累了内容：补一次 debounce
                self._schedule_debounce(chat_id, openid, STREAM_MIN_INTERVAL)

            # 结束片已发，超长正文普通分片补发
            if overflow:
                await self._send_plain_chunks(openid, "dm", st.msg_id, overflow)

            return SendResult(success=True)
        finally:
            st.flushing = False

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
