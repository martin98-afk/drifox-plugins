# -*- coding: utf-8 -*-
"""
钉钉平台适配器（社区插件，万物即插件 Phase E）

使用钉钉 Stream Mode SDK 进行实时消息接收。

本文件原位于 app/gateway/adapters/dingtalk.py（E2 Task 5 迁入）。
适配器实现保持原状（SDK 延迟导入纪律：模块顶层不 eager import 平台 SDK）。
"""

from __future__ import annotations


# 依赖注入已由宿主统一接管：PluginManager 扫描时注入 deps/ 与 deps/<platform>/
# （平台目录优先，见 app/plugins/deps_loader.py），插件组件不再自理 sys.path。
import asyncio
import json
import uuid
from typing import Any, Dict, Optional

from loguru import logger

from app.gateway.base import (
    BasePlatformAdapter,
    ChatInfo,
    MessageEvent,
    MessageType,
    SendResult,
    get_cache_dir,
)

# 钉钉 SDK 组件占位（真正延迟导入：见 check_dingtalk_requirements() 与 connect()）
ChatbotHandler = None
ChatbotMessage = None
AckMessage = None
# _IncomingHandler 类占位：在 check_dingtalk_requirements() 成功后才通过
# _build_incoming_handler_class() 动态构建，以避免模块顶层就依赖 dingtalk_stream
IncomingHandler = None


def _patch_dingtalk_stream_logging():
    """
    Monkey-patch dingtalk_stream.stream.DingTalkStreamClient.start()

    修复三方库 stream.py:89 的日志错误：
        self.logger.exception('unknown exception', e)
            # TypeError: not all arguments converted during string formatting
    修改为:
        self.logger.exception('unknown exception', exc_info=e)
    """
    import asyncio.exceptions
    from urllib.parse import quote_plus

    import dingtalk_stream.stream as dstream
    import websockets

    original_start = dstream.DingTalkStreamClient.start

    async def patched_start(self):
        """Fixed version of DingTalkStreamClient.start()"""
        self.pre_start()
        while True:
            try:
                connection = self.open_connection()
                if not connection:
                    self.logger.error("open connection failed")
                    await asyncio.sleep(10)
                    continue
                self.logger.info("endpoint is %s", connection)

                uri = f"{connection['endpoint']}?ticket={quote_plus(connection['ticket'])}"
                async with websockets.connect(uri) as websocket:
                    self.websocket = websocket
                    asyncio.create_task(self.keepalive(websocket))
                    async for raw_message in websocket:
                        json_message = json.loads(raw_message)
                        asyncio.create_task(self.background_task(json_message))
            except KeyboardInterrupt:
                break
            except (asyncio.exceptions.CancelledError, websockets.exceptions.ConnectionClosedError) as e:
                self.logger.error("[start] network exception, error=%s", e)
                await asyncio.sleep(10)
                continue
            except Exception as e:
                await asyncio.sleep(3)
                # 🔧 FIXED: exc_info=e 而非作为位置参数传入
                self.logger.exception("unknown exception", exc_info=e)
                continue
            finally:
                pass

    dstream.DingTalkStreamClient.start = patched_start


# 注意：原文件此处曾在模块顶层预调用 _ensure_dingtalk_imports() / _patch_dingtalk_stream_logging()，
# 导致 import 在 dingtalk-stream 未安装时抛 ModuleNotFoundError，牵连整个 gateway 加载。
# 现已删除：依赖检测统一在 check_dingtalk_requirements()，monkey patch 仅在 connect() 调用一次。


# 消息类型映射
DINGTALK_TYPE_MAPPING = {
    "picture": "image",
    "voice": "audio",
}

# 重连退避
RECONNECT_BACKOFF = [2, 5, 10, 30, 60]
MAX_MESSAGE_LENGTH = 20000
MAX_INBOUND_IMAGES = 10


class DingTalkAdapter(BasePlatformAdapter):
    """
    钉钉 chatbot 适配器 (Stream Mode)

    使用 dingtalk-stream SDK 维持 WebSocket 长连接。

    配置项:
        - client_id: 应用 AppKey
        - client_secret: 应用 AppSecret
    """

    platform_id = "dingtalk"
    name = "DingTalk"
    MAX_MESSAGE_LENGTH = MAX_MESSAGE_LENGTH

    def __init__(self) -> None:
        super().__init__()

        cfg = _config()
        self._client_id = cfg["client_id"]
        self._client_secret = cfg["client_secret"]

        # Stream 客户端
        self._stream_client: Optional[Any] = None
        self._stream_task: Optional[asyncio.Task] = None
        self._http_client: Optional[Any] = None
        self._access_token: Optional[str] = None
        self._access_token_expiry: float = 0.0

        # Session webhook 缓存
        self._session_webhooks: Dict[str, tuple] = {}  # chat_id -> (webhook, expire_time)

        # 重连退避
        self._backoff_idx = 0

        # 流式回复：chat_id -> dm/group（决定卡片投放空间）
        self._chat_types: Dict[str, str] = {}
        # 流式状态：chat_id -> {out_track_id, chat_type, last_edit, last_text}
        self._stream_states: Dict[str, Dict[str, Any]] = {}

    async def connect(self) -> bool:
        """连接到钉钉 Stream"""
        if not self._client_id or not self._client_secret:
            logger.error("[DingTalk] client_id and client_secret are required")
            return False

        try:
            import httpx
            from dingtalk_stream import (
                Credential,
                DingTalkStreamClient,
            )

            # 应用 monkey-patch 修复（仅在 SDK 已确认可用后执行一次）
            _patch_dingtalk_stream_logging()

            # 连接池参数本地定义：宿主 app.gateway.platforms._http_client_limits
            # 已在主程序死代码清理中删除，插件不再跨层引用宿主私有模块
            limits = httpx.Limits(
                max_keepalive_connections=20,
                max_connections=100,
                keepalive_expiry=30.0,
            )
            self._http_client = httpx.AsyncClient(
                timeout=30.0,
                limits=limits,
            )

            # 创建 Stream 客户端
            credential = Credential(self._client_id, self._client_secret)
            self._stream_client = DingTalkStreamClient(credential)

            # 注册处理器 - 使用字符串 topic
            # IncomingHandler 由 check_dingtalk_requirements() 构建；此 connect() 路径
            # 已被 manager.py:122 的 `if check_dingtalk_requirements():` 守护，理论上
            # 不会走到这里；保险起见若未构建则立即构建。
            if IncomingHandler is None:
                _build_incoming_handler_class()
            handler = IncomingHandler(self)
            self._stream_client.register_callback_handler(
                "/v1.0/im/bot/messages/get",  # 机器人消息 topic
                handler,
            )

            # 启动
            self._stream_task = asyncio.create_task(self._run_stream())

            # 标记为已连接
            self._connected = True

            logger.info("[DingTalk] Connected successfully")
            return True

        except Exception as e:
            logger.error(f"[DingTalk] Connection failed: {e}", exc_info=True)
            await self._cleanup()
            return False

    async def _run_stream(self) -> None:
        """运行 Stream 客户端"""
        self._backoff_idx = 0
        _consecutive_timeouts = 0

        while self._running:
            try:
                await self._stream_client.start()
            except asyncio.CancelledError:
                return
            except (TimeoutError, asyncio.TimeoutError) as e:
                if not self._running:
                    return
                _consecutive_timeouts += 1
                if _consecutive_timeouts == 1:
                    logger.warning(
                        "[DingTalk] WebSocket connection timed out — check network / firewall. "
                        "DingTalk server may be unreachable."
                    )
                else:
                    logger.warning(f"[DingTalk] Timeout again ({_consecutive_timeouts}x): {e}")
            except Exception as e:
                if not self._running:
                    return
                _consecutive_timeouts = 0
                logger.warning(f"[DingTalk] Stream error: {e}")

            if not self._running:
                return

            delay = RECONNECT_BACKOFF[min(self._backoff_idx, len(RECONNECT_BACKOFF) - 1)]
            self._backoff_idx += 1

            logger.info(f"[DingTalk] Reconnecting in {delay}s...")
            await asyncio.sleep(delay)

    async def disconnect(self) -> None:
        """断开连接"""
        self._running = False

        if self._stream_task:
            self._stream_task.cancel()
            try:
                await asyncio.wait_for(self._stream_task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        await self._cleanup()
        logger.info("[DingTalk] Disconnected")

    async def _cleanup(self) -> None:
        """清理资源"""
        self._session_webhooks.clear()

        if self._http_client:
            await self._http_client.aclose()
        self._http_client = None

        self._stream_client = None

    async def _on_message(self, message: Any) -> None:
        """处理收到的消息"""
        msg_id = getattr(message, "message_id", None) or ""
        if not msg_id:
            # 钉钉 SDK 通常会提供 message_id（对应 msgId），
            # 如果缺失则用 conversation_id + sender_id + text 组合作为去重键
            sender_id = getattr(message, "sender_id", "") or ""
            text = self._extract_text(message) or ""
            msg_id = f"{sender_id}:{text[:50]}"
        conversation_id = getattr(message, "conversation_id", "") or ""
        conversation_type = getattr(message, "conversation_type", "1")
        is_group = str(conversation_type) == "2"

        sender_id = getattr(message, "sender_id", "") or ""
        sender_nick = getattr(message, "sender_nick", "") or sender_id

        chat_id = conversation_id or sender_id
        chat_type = "group" if is_group else "dm"
        if chat_id:
            self._chat_types[chat_id] = chat_type

        # 存储 session webhook
        session_webhook = getattr(message, "session_webhook", None) or ""
        session_webhook_expired_time = getattr(message, "session_webhook_expired_time", 0) or 0

        if session_webhook and chat_id:
            self._session_webhooks[chat_id] = (session_webhook, session_webhook_expired_time)
            logger.debug(f"[DingTalk] Stored webhook for {str(chat_id)[:30]}: {str(session_webhook)[:50]}")

        # 提取文本
        text = self._extract_text(message)

        # 提取媒体
        msg_type, media_urls, media_types = self._extract_media(message)

        if not text and not media_urls:
            logger.debug("[DingTalk] Empty message skipped")
            return

        # 构建消息事件
        event = MessageEvent(
            text=text,
            message_type=msg_type,
            message_id=msg_id,
            chat_id=chat_id,
            user_id=sender_id,
            user_name=sender_nick,
            platform="dingtalk",
            chat_type=chat_type,
            media_urls=media_urls,
            media_types=media_types,
        )

        await self._dispatch_event(event, media_urls, media_types)

    def _on_message_sync(self, message: Any) -> None:
        """同步处理收到的消息（供 ChatbotHandler 调用）"""
        msg_id = getattr(message, "message_id", None) or ""
        if not msg_id:
            sender_id = getattr(message, "sender_id", "") or ""
            text = self._extract_text(message) or ""
            msg_id = f"{sender_id}:{text[:50]}"
        conversation_id = getattr(message, "conversation_id", "") or ""
        conversation_type = getattr(message, "conversation_type", "1")
        is_group = str(conversation_type) == "2"

        sender_id = getattr(message, "sender_id", "") or ""
        sender_nick = getattr(message, "sender_nick", "") or sender_id

        chat_id = conversation_id or sender_id
        chat_type = "group" if is_group else "dm"
        if chat_id:
            self._chat_types[chat_id] = chat_type

        # 存储 session webhook
        session_webhook = getattr(message, "session_webhook", None) or ""
        session_webhook_expired_time = getattr(message, "session_webhook_expired_time", 0) or 0

        if session_webhook and chat_id:
            self._session_webhooks[chat_id] = (session_webhook, session_webhook_expired_time)

        # 提取文本
        text = self._extract_text(message)

        # 提取媒体
        msg_type, media_urls, media_types = self._extract_media(message)

        if not text and not media_urls:
            logger.debug("[DingTalk] Empty message skipped")
            return

        # 构建消息事件
        event = MessageEvent(
            text=text,
            message_type=msg_type,
            message_id=msg_id,
            chat_id=chat_id,
            user_id=sender_id,
            user_name=sender_nick,
            platform="dingtalk",
            chat_type=chat_type,
            media_urls=media_urls,
            media_types=media_types,
        )

        # 在已有或新的事件循环中运行异步处理
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            # 当前线程已有运行中的事件循环 → 创建任务
            asyncio.create_task(self._dispatch_event(event, media_urls, media_types))
        except RuntimeError:
            # 当前线程无运行中的事件循环 → 用 asyncio.run 驱动
            asyncio.run(self._dispatch_event(event, media_urls, media_types))

    async def _dispatch_event(self, event: MessageEvent, download_codes, media_types=None) -> None:
        """下载入站图片后再交给宿主（钉钉给的是 downloadCode，不是 URL）。"""
        types = list(media_types or [])
        codes = [
            (code, "image" if index >= len(types) or types[index] == "image" else "file")
            for index, code in enumerate(download_codes or [])
        ]
        if codes:
            try:
                paths, kinds = await self._download_by_codes(codes)
                if paths:
                    event.media_urls = paths
                    event.media_types = kinds
            except Exception as e:
                logger.warning("[DingTalk] 入站图片下载失败: {}", e)
        await self.handle_message(event)

    async def _get_access_token(self) -> Optional[str]:
        """获取钉钉企业内应用 accessToken（缓存至过期前 5 分钟）。"""
        import time

        now = time.time()
        if self._access_token and now < self._access_token_expiry - 300:
            return self._access_token
        if not self._http_client or not self._client_id or not self._client_secret:
            return None
        response = await self._http_client.post(
            "https://api.dingtalk.com/v1.0/oauth2/accessToken",
            json={"appKey": self._client_id, "appSecret": self._client_secret},
        )
        data = response.json() if response.content else {}
        token = data.get("accessToken")
        if response.status_code == 200 and token:
            self._access_token = token
            self._access_token_expiry = now + int(data.get("expireIn") or 7200)
            return token
        logger.warning("[DingTalk] 获取 accessToken 失败: HTTP {} {}", response.status_code, data)
        return None

    async def _download_by_codes(self, codes) -> tuple:
        """downloadCode → downloadUrl → 本地文件。返回 (路径列表, 类型列表)。"""
        if not self._http_client:
            return [], []
        token = await self._get_access_token()
        if not token:
            return []
        import hashlib

        cache = get_cache_dir("dingtalk")
        paths, kinds = [], []
        for code, kind in codes[:MAX_INBOUND_IMAGES]:
            if not isinstance(code, str) or not code:
                continue
            response = await self._http_client.post(
                "https://api.dingtalk.com/v1.0/robot/messageFiles/download",
                headers={"x-acs-dingtalk-access-token": token},
                json={"downloadCode": code, "robotCode": self._client_id},
            )
            data = response.json() if response.content else {}
            url = data.get("downloadUrl")
            if not url:
                logger.warning("[DingTalk] 换取下载地址失败: {}", data)
                continue
            file_response = await self._http_client.get(url, timeout=30)
            if file_response.status_code != 200 or not file_response.content:
                logger.warning("[DingTalk] 图片下载失败 HTTP {}", file_response.status_code)
                continue
            digest = hashlib.sha1(code.encode("utf-8")).hexdigest()[:16]
            suffix = ".jpg" if kind == "image" else ".bin"
            target = cache / f"{digest}{suffix}"
            if not target.exists():
                target.write_bytes(file_response.content)
            paths.append(str(target))
            kinds.append(kind)
        return paths, kinds

    def _extract_text(self, message: Any) -> str:
        """提取文本内容"""
        text = getattr(message, "text", None) or ""

        # 处理 TextContent 对象
        if hasattr(text, "content"):
            content = (text.content or "").strip()
        elif isinstance(text, dict):
            content = text.get("content", "").strip()
        else:
            content = str(text).strip()

        if not content:
            rich_text = getattr(message, "rich_text_content", None) or getattr(message, "rich_text", None)
            if rich_text:
                rich_list = getattr(rich_text, "rich_text_list", None) or rich_text
                if isinstance(rich_list, list):
                    parts = []
                    for item in rich_list:
                        if isinstance(item, dict):
                            t = item.get("text") or item.get("content") or ""
                            if t:
                                parts.append(t)
                        elif hasattr(item, "text") and item.text:
                            parts.append(item.text)
                    content = " ".join(parts).strip()

        return content

    def _extract_media(self, message: Any) -> tuple:
        """提取媒体信息"""
        msg_type = MessageType.TEXT
        media_urls = []
        media_types = []

        # 图片
        image_content = getattr(message, "image_content", None)
        if image_content:
            download_code = getattr(image_content, "download_code", None)
            if download_code:
                media_urls.append(download_code)
                media_types.append("image")
                msg_type = MessageType.IMAGE

        # 富文本中的媒体
        rich_text = getattr(message, "rich_text_content", None) or getattr(message, "rich_text", None)
        if rich_text:
            rich_list = getattr(rich_text, "rich_text_list", None) or rich_text
            if isinstance(rich_list, list):
                for item in rich_list:
                    if isinstance(item, dict):
                        dl_code = item.get("downloadCode") or item.get("download_code") or ""
                        item_type = item.get("type", "")
                        if dl_code:
                            mapped = DINGTALK_TYPE_MAPPING.get(item_type, "file")
                            media_urls.append(dl_code)
                            media_types.append(mapped)
                            if mapped == "image":
                                msg_type = MessageType.IMAGE
                            elif mapped == "audio":
                                msg_type = MessageType.AUDIO

        return msg_type, media_urls, media_types

    # ── 流式回复（AI Card：v1.0/card/instances/createAndDeliver + v1.0/card/streaming） ──

    # 钉钉官方 AI 卡片模板（dsh-im 同款公共模板），无需用户在后台自建
    _AI_CARD_TEMPLATE_ID = "02fcf2f4-5e02-4a85-b672-46d1f715543e.schema"
    _STREAM_EDIT_INTERVAL = 0.8
    _CARD_CONTENT_LIMIT = 20000

    def supports_streaming(self, chat_id: str) -> bool:
        """收到过该会话的消息才有投放目标（私聊 senderId / 群 openConversationId）。"""
        return chat_id in self._chat_types

    async def start_stream(self, chat_id: str) -> Optional[str]:
        """创建并投放 AI 卡片（带思考文案），返回 stream_key=``dd:<chat_id>:<outTrackId>``。

        卡片接口需要额外权限，任何失败都返回 None，由宿主回退普通消息。
        """
        chat_type = self._chat_types.get(chat_id)
        if not chat_type:
            return None
        token = await self._get_access_token()
        if not token or not self._http_client:
            return None

        out_track_id = f"drifox_{uuid.uuid4().hex}"
        initial_text = "💭 正在思考…"
        body = {
            "outTrackId": out_track_id,
            "userIdType": 1,
            "cardTemplateId": self._AI_CARD_TEMPLATE_ID,
            "cardData": self._card_data(initial_text, "2"),
            "callbackType": "STREAM",
            "imGroupOpenSpaceModel": {"supportForward": True},
            "imRobotOpenSpaceModel": {"supportForward": True},
        }
        if chat_type == "group":
            body["openSpaceId"] = f"dtv1.card//IM_GROUP.{chat_id}"
            body["imGroupOpenDeliverModel"] = {"robotCode": self._client_id}
        else:
            body["openSpaceId"] = f"dtv1.card//IM_ROBOT.{chat_id}"
            body["imRobotOpenDeliverModel"] = {
                "spaceType": "IM_ROBOT",
                "robotCode": self._client_id,
                "extension": {"dynamicSummary": "true"},
            }
        try:
            response = await self._http_client.post(
                "https://api.dingtalk.com/v1.0/card/instances/createAndDeliver",
                headers={"x-acs-dingtalk-access-token": token},
                json=body,
            )
            if response.status_code != 200:
                logger.debug(
                    "[DingTalk] AI 卡片不可用，回退普通消息: HTTP {} {}",
                    response.status_code,
                    response.text[:200],
                )
                return None
        except Exception as e:
            logger.debug("[DingTalk] AI 卡片创建失败，回退普通消息: {}", e)
            return None

        self._stream_states[chat_id] = {
            "out_track_id": out_track_id,
            "chat_type": chat_type,
            "last_edit": 0.0,
            "last_text": initial_text,
        }
        return f"dd:{chat_id}:{out_track_id}"

    async def update_stream(self, stream_key: str, snapshot: str) -> bool:
        """把可见快照推给 AI 卡片；单次失败不致命（finish 会发最终全文）。"""
        state = self._stream_state(stream_key)
        if state is None:
            return False
        import time as _time

        now = _time.monotonic()
        if now - float(state.get("last_edit") or 0.0) < self._STREAM_EDIT_INTERVAL:
            return True
        text = (snapshot or "").strip()
        if not text or text == state.get("last_text"):
            return True
        try:
            await self._push_card_stream(state, text, finalize=False)
        except Exception as e:
            logger.debug("[DingTalk] 卡片流式更新跳过: {}", e)
            return True
        state["last_edit"] = now
        state["last_text"] = text
        return True

    async def finish_stream(self, stream_key: str, final: str) -> SendResult:
        """关闭流式组件并落最终态（flowStatus=3），然后清理状态。"""
        state = self._stream_state(stream_key)
        if state is None:
            return SendResult(success=False, error="unknown stream")
        chat_id = str(stream_key.split(":", 2)[1])
        text = (final or "（无输出）").strip() or "（无输出）"
        try:
            await self._push_card_stream(state, text, finalize=True)
            # 落最终态：模板的 finished 样式与完整内容
            token = await self._get_access_token()
            if token and self._http_client:
                await self._http_client.put(
                    "https://api.dingtalk.com/v1.0/card/instances",
                    headers={"x-acs-dingtalk-access-token": token},
                    json={
                        "outTrackId": state["out_track_id"],
                        "cardData": self._card_data(text, "3"),
                        "cardUpdateOptions": {"updateCardDataByKey": True},
                    },
                )
            return SendResult(success=True, message_id=state["out_track_id"])
        except Exception as e:
            logger.warning("[DingTalk] finish_stream failed: {}", e)
            return SendResult(success=False, error=str(e))
        finally:
            self._stream_states.pop(chat_id, None)

    async def _push_card_stream(self, state: Dict[str, Any], text: str, finalize: bool) -> None:
        """推一帧 v1.0/card/streaming（全量内容）。"""
        token = await self._get_access_token()
        if not token or not self._http_client:
            raise RuntimeError("no access token")
        response = await self._http_client.put(
            "https://api.dingtalk.com/v1.0/card/streaming",
            headers={"x-acs-dingtalk-access-token": token},
            json={
                "outTrackId": state["out_track_id"],
                "guid": uuid.uuid4().hex,
                "key": "msgContent",
                "content": text[: self._CARD_CONTENT_LIMIT],
                "isFull": True,
                "isFinalize": finalize,
                "isError": False,
            },
        )
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")

    @staticmethod
    def _card_data(text: str, flow_status: str) -> Dict[str, Any]:
        """AI 卡片模板数据（msgContent 只放正文，order 固定单元素）。"""
        return {
            "cardParamMap": {
                "flowStatus": flow_status,
                "msgContent": text,
                "staticMsgContent": "",
                "sys_full_json_obj": json.dumps({"order": ["msgContent"]}),
                "config": json.dumps({"autoLayout": True}),
            }
        }

    def _stream_state(self, stream_key: str) -> Optional[Dict[str, Any]]:
        """解析 ``dd:<chat_id>:<outTrackId>`` 定位流状态。"""
        if not stream_key or not stream_key.startswith("dd:"):
            return None
        parts = stream_key.split(":", 2)
        if len(parts) != 3:
            return None
        return self._stream_states.get(parts[1])

    async def send(self, chat_id: str, content: str, **kwargs) -> SendResult:
        """发送消息"""
        logger.debug(
            "[DingTalk] send() called, chat_id="
            + chat_id[:20]
            + f", content_len={len(content)}, webhooks={list(self._session_webhooks.keys())}"
        )

        webhook_info = self._session_webhooks.get(chat_id)
        if not webhook_info:
            logger.warning(f"[DingTalk] No session webhook for chat_id={chat_id[:30]}")
            return SendResult(success=False, error="No session webhook available", retryable=True)

        webhook, expired_time = webhook_info

        if not self._http_client:
            return SendResult(success=False, error="HTTP client not initialized", retryable=False)

        try:
            # 钉钉 session_webhook API 格式
            payload = {"msg": {"msgtype": "markdown", "markdown": {"title": "DriFox", "text": content}}}

            response = await self._http_client.post(webhook, json=payload)

            if response.status_code == 200:
                return SendResult(success=True)
            else:
                return SendResult(
                    success=False,
                    error=f"HTTP {response.status_code}: {response.text}",
                    retryable=response.status_code >= 500,
                )

        except asyncio.TimeoutError:
            return SendResult(success=False, error="Request timeout", retryable=True)
        except Exception as e:
            logger.error(f"[DingTalk] Send failed: {e}", exc_info=True)
            return SendResult(success=False, error=str(e), retryable=True)

    async def send_image(self, chat_id: str, image_path: str, **kwargs) -> SendResult:
        """发送图片"""
        webhook_info = self._session_webhooks.get(chat_id)
        if not webhook_info:
            return SendResult(success=False, error="No session webhook available", retryable=True)

        webhook, _ = webhook_info

        try:
            from pathlib import Path

            import httpx

            image_path = str(image_path)

            # 如果是 URL，先下载到本地缓存
            # 副作用：image_path 会被重写为本地 UUID 文件名，
            # 后续 text 消息的 content 用本地文件名（避免泄漏原始 URL）。
            if image_path.startswith("http"):
                cache_dir = get_cache_dir("images")
                cache_dir.mkdir(parents=True, exist_ok=True)

                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(image_path)
                    response.raise_for_status()

                    ext = ".jpg"
                    if "." in image_path:
                        ext = "." + image_path.rsplit(".", 1)[-1].split("?")[0]

                    filename = f"img_{uuid.uuid4().hex[:12]}{ext}"
                    filepath = cache_dir / filename
                    filepath.write_bytes(response.content)
                    image_path = str(filepath)

            # TODO(dingtalk-media-upload): 真实图片发送需要先调钉钉 media API
            # 上传文件获取 media_id，再构造 msgtype=image 的消息体。
            # 当前实现是降级占位：直接发文本消息显示文件名。
            # 参考文档: https://open.dingtalk.com/document/orgapp-server/upload-media-files
            payload = {"msg": {"msgtype": "text", "text": {"content": f"🖼️ Image: {Path(image_path).name}"}}}

            response = await self._http_client.post(webhook, json=payload)

            if response.status_code == 200:
                return SendResult(success=True)
            else:
                return SendResult(
                    success=False, error=f"HTTP {response.status_code}", retryable=response.status_code >= 500
                )

        except Exception as e:
            logger.error(f"[DingTalk] Send image failed: {e}", exc_info=True)
            return SendResult(success=False, error=str(e), retryable=True)

    async def send_file(self, chat_id: str, file_path: str, **kwargs) -> SendResult:
        """发送文件"""
        webhook_info = self._session_webhooks.get(chat_id)
        if not webhook_info:
            return SendResult(success=False, error="No session webhook available", retryable=True)

        webhook, _ = webhook_info

        try:
            from pathlib import Path

            payload = {"msg": {"msgtype": "text", "text": {"content": f"📎 File: {Path(file_path).name}"}}}

            response = await self._http_client.post(webhook, json=payload)

            if response.status_code == 200:
                return SendResult(success=True)
            else:
                return SendResult(success=False, error=f"HTTP {response.status_code}")

        except Exception as e:
            logger.error("[DingTalk] Send file failed: {}", e, exc_info=True)
            return SendResult(success=False, error=str(e), retryable=True)

    async def get_chat_info(self, chat_id: str) -> ChatInfo:
        """获取聊天信息"""
        return ChatInfo(
            name=chat_id,
            type="dm",
            chat_id=chat_id,
        )


# 注意：原文件此处曾在模块顶层定义 `class _IncomingHandler(ChatbotHandler)`。
# 当 ChatbotHandler=None（缺包）时，该类继承会立即抛 TypeError。
# 现已改为：模块顶层只暴露 IncomingHandler 占位变量，
# 实际类由 _build_incoming_handler_class() 在 SDK 确认可用后动态构建。


def _build_incoming_handler_class():
    """
    构建 _IncomingHandler 动态类。

    必须在 check_dingtalk_requirements() 成功（即 ChatbotHandler 已就绪）后调用。
    类定义延迟至此，避免模块顶层对 dingtalk_stream 的强依赖。
    """
    global IncomingHandler
    if IncomingHandler is not None:
        return IncomingHandler

    class _IncomingHandler(ChatbotHandler):
        """
        钉钉消息处理器

        继承自 dingtalk_stream.ChatbotHandler，处理机器人消息。
        """

        def __init__(self, adapter: "DingTalkAdapter"):
            from dingtalk_stream import ChatbotMessage

            super().__init__()
            self._adapter = adapter
            self._ChatbotMessage = ChatbotMessage

        async def process(self, callback) -> tuple:
            """
            处理消息回调

            Args:
                callback: 钉钉 SDK 的回调消息

            Returns:
                (status_code, response)
            """
            try:
                from dingtalk_stream import AckMessage

                # 获取消息数据
                data = callback.data if hasattr(callback, "data") else callback

                # 创建 ChatbotMessage
                message = self._ChatbotMessage.from_dict(data)

                # 异步处理消息
                await self._adapter._on_message(message)

                # 返回成功状态
                return AckMessage.STATUS_OK, "OK"

            except Exception as e:
                logger.error("[DingTalk] Handler process error: {}", e, exc_info=True)
                from dingtalk_stream import AckMessage

                return AckMessage.STATUS_FAIL, str(e)

    IncomingHandler = _IncomingHandler
    return IncomingHandler


def check_dingtalk_requirements() -> bool:
    """
    检查钉钉依赖是否满足。

    成功时同时设置模块级 SDK 占位全局变量（ChatbotHandler/ChatbotMessage/AckMessage），
    并通过 _build_incoming_handler_class() 构建 IncomingHandler 类。
    此函数被调用前，模块顶层 import 是安全的（不依赖 dingtalk_stream）。
    """
    global ChatbotHandler, ChatbotMessage, AckMessage
    if ChatbotHandler is not None:
        # 已就绪：幂等返回 True（同时确保 IncomingHandler 已构建）
        _build_incoming_handler_class()
        return True
    try:
        import httpx  # noqa: F401  # 显式依赖 httpx，缺包时也归类到钉钉缺失
        from dingtalk_stream import (
            AckMessage as AM,
        )
        from dingtalk_stream import (
            ChatbotHandler as CH,
        )
        from dingtalk_stream import (
            ChatbotMessage as CM,
        )

        ChatbotHandler = CH
        ChatbotMessage = CM
        AckMessage = AM
        _build_incoming_handler_class()
        return True
    except ImportError:
        logger.error("[DingTalk] dingtalk-stream not installed. Run: pip install 'drifox[gateway]'")
        return False


# ── Phase E 插件注册 ────────────────────────────────────
# 配置读写回调走主程序 Settings（存量用户配置零迁移；Task 5 统一切 E1
# PluginConfigStore 时仅改本块闭包，调用方不动）。闭包内延迟 import
# 宿主契约不承载平台配置，避免模块顶层触发 Settings 副作用。


PLUGIN_NAME = "gateway-dingtalk"

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
        "client_id": values.get("client_id") or "",
        "client_secret": values.get("client_secret") or "",
    }


def _set_enabled(enabled: bool) -> None:
    writer = _cap("plugin.config.write")
    if writer is not None:
        writer("enabled", bool(enabled))


def _validate() -> tuple:
    cfg = _config()
    return bool(cfg["client_id"] and cfg["client_secret"]), "ClientID/Secret 未配置"


def register(registry) -> None:
    from app.plugins.contracts.gateway_platform import GatewayPlatformDef

    registry.register(
        GatewayPlatformDef(
            platform_id="dingtalk",
            display_name="钉钉",
            adapter_factory=DingTalkAdapter,
            check_requirements=check_dingtalk_requirements,
            is_enabled=lambda: _config()["enabled"],
            set_enabled=_set_enabled,
            validate=_validate,
            ui_order=20,
        )
    )
