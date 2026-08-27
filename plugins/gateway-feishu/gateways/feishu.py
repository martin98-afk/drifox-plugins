# -*- coding: utf-8 -*-
"""
飞书 (Feishu/Lark) 适配器（社区插件，万物即插件 Phase E）

使用 lark_oapi SDK WebSocket 模式进行消息收发。

本文件原位于 app/gateway/adapters/feishu.py（E2 Task 5 迁入）。
适配器实现保持原状（SDK 延迟导入纪律：模块顶层不 eager import 平台 SDK）。
"""

from __future__ import annotations


# ── 插件自包含依赖注入：优先加载本插件 deps/ 目录 ────────────────
# 平台 SDK（lark-oapi 及传递依赖）vendor 到插件根 deps/（即 gateways/ 的上一级）：
# 本插件为社区插件，依赖自包含于 <plugin>/deps/；顶层只注入路径，SDK 本体仍在
# 函数内延迟导入。注意：__file__ 在 gateways/ 内，需 .. 回退到插件根再进 deps。
import os as _os, sys as _sys
_deps = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', 'deps'))
if _deps not in _sys.path:
    _sys.path.insert(0, _deps)
import asyncio
import json
import logging
import threading
from typing import Any, Dict, List, Optional

from app.gateway.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    Platform,
    PlatformConfig,
    SendResult,
)

logger = logging.getLogger(__name__)

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

    MAX_MESSAGE_LENGTH = 2000

    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform.FEISHU)

        self._app_id = config.extra.get("app_id") or ""
        self._app_secret = config.extra.get("app_secret") or ""
        self._encrypt_key = config.extra.get("encrypt_key") or ""
        self._verification_token = config.extra.get("verification_token") or ""

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

        # 从配置重新获取（确保最新）
        from app.gateway.config import get_gateway_config

        cfg = get_gateway_config().get_platform_config(Platform.FEISHU)
        self._app_id = cfg.extra.get("app_id") or ""
        self._app_secret = cfg.extra.get("app_secret") or ""
        self._encrypt_key = cfg.extra.get("encrypt_key") or ""
        self._verification_token = cfg.extra.get("verification_token") or ""

        if not self._app_id or not self._app_secret:
            logger.error("[Feishu] app_id and app_secret are required")
            self._last_error = "缺少 app_id 或 app_secret"
            return False

        try:
            import lark_oapi as lark
            from lark_oapi.core.const import FEISHU_DOMAIN
            from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
            from lark_oapi.ws import Client as FeishuWSClient

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

            # 在独立线程中运行客户端
            self._feishu_thread = threading.Thread(
                target=self._run_feishu_client,
                name="FeishuWSClient",
                daemon=True,
            )
            self._feishu_thread.start()

            self._running = True
            self._connected = True

            logger.info("[Feishu] Connected successfully (WebSocket)")
            return True

        except Exception as e:
            logger.error("[Feishu] Failed to connect: %s", e)
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
                    logger.error("[Feishu] Client error: %s", e)
                else:
                    logger.debug("[Feishu] Client stopped (expected): %s", e)
            finally:
                self._ws_loop = None
                loop.close()

        except Exception as e:
            logger.error("[Feishu] Thread error: %s", e)

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

            # 提取字段
            message_id = str(getattr(message, "message_id", "") or "")
            chat_id = str(getattr(message, "chat_id", "") or "")
            chat_type = str(getattr(message, "chat_type", "p2p") or "p2p")

            # EventMessage 使用 message_type（而不是 msg_type），content 是 JSON 字符串
            msg_type = str(getattr(message, "message_type", "text") or "text")
            content_str = str(getattr(message, "content", "") or "")

            # 解析 content JSON 字符串
            text = ""
            try:
                if content_str:
                    content_data = json.loads(content_str)
                    if isinstance(content_data, dict):
                        text = content_data.get("text", "") or content_data.get("content", "") or ""
            except (json.JSONDecodeError, TypeError):
                # 如果不是 JSON，直接作为文本
                text = content_str

            # @提及处理：飞书群聊 @机器人 发命令时 text 形如 "@_user_1 /model"
            # （机器占位符格式），前缀会让宿主 startswith("/") 判定失败、命令被
            # 当普通对话送给 AI。只剥指向机器人自己（mentioned_type="app"）的
            # 占位符；@人的占位符换成 @真实名字（语义不丢）。
            import re as _re

            mentions = getattr(message, "mentions", None) or []
            bot_keys = {
                m.key
                for m in mentions
                if getattr(m, "key", None) and getattr(m, "mentioned_type", "") == "app"
            }
            name_by_key = {
                m.key: f"@{m.name}" for m in mentions if getattr(m, "key", None)
            }
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

            # 提取 sender_id
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

            # 跳过空消息
            if not text and not message_id:
                logger.debug("[Feishu] Empty message skipped")
                return

            # 构建 MessageEvent
            event = MessageEvent(
                text=text,
                message_type=MessageType.TEXT if msg_type == "text" else MessageType.FILE,
                message_id=message_id,
                chat_id=chat_id,
                user_id=sender_id,
                user_name=sender_id,
                platform=Platform.FEISHU,
                chat_type="group" if chat_type == "group" else "dm",
                media_urls=[],
                media_types=[],
            )

            if self._message_handler:
                try:
                    # 重要：WS client 回调运行在 WS 线程的事件循环中，
                    # 不能在此调用 asyncio.run()，会触发 RuntimeError。
                    # 使用独立的 handler_loop 来调度消息处理。
                    loop = self._handler_loop
                    if loop is not None and loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            self._message_handler(event),
                            loop,
                        )
                    else:
                        logger.error("[Feishu] Handler loop not running, dropping message")
                except Exception as e:
                    logger.error("[Feishu] Handle message error: %s", e)

        except Exception as e:
            logger.error("[Feishu] Parse message error: %s", e)
            import traceback

            traceback.print_exc()

    # ==================== 卡片按钮回传（card.action.trigger） ====================

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
            cmd = value.get("drifox_cmd", "") if isinstance(value, dict) else ""
            cmd = str(cmd).strip()
            if not cmd.startswith("/"):
                return self._card_toast("error", "未知按钮指令")

            context = getattr(event, "context", None)
            chat_id = str(getattr(context, "open_chat_id", "") or "") if context else ""
            if not chat_id:
                return self._card_toast("error", "缺少会话上下文")

            operator = getattr(event, "operator", None)
            operator_id = str(getattr(operator, "open_id", "") or "card_user") if operator else "card_user"

            ev = MessageEvent(
                text=cmd,
                message_type=MessageType.TEXT,
                message_id="",
                chat_id=chat_id,
                user_id=operator_id,
                user_name=operator_id,
                platform=Platform.FEISHU,
                chat_type="dm",
                media_urls=[],
                media_types=[],
            )

            if self._message_handler:
                loop = self._handler_loop
                if loop is not None and loop.is_running():
                    asyncio.run_coroutine_threadsafe(self._message_handler(ev), loop)
                    logger.info("[Feishu] Card action injected: %s", cmd[:80])
                    return self._card_toast("success", f"⏳ 已执行 {cmd[:40]}")
                logger.error("[Feishu] Handler loop not running, card action dropped")
                return self._card_toast("error", "处理循环不可用")

            return self._card_toast("error", "消息处理器未就绪")

        except Exception as e:
            logger.error("[Feishu] Card action error: %s", e)
            return self._card_toast("error", "处理失败")

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
                logger.debug("[Feishu] Disconnect note: %s", e)

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
                logger.debug("[Feishu] Stop ws loop note: %s", e)

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
                        "[Feishu] Card send fallback to text: HTTP %s code=%s",
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
            logger.error("[Feishu] Send failed: %s", e)
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
            logger.warning("[Feishu] Command card detect failed, fallback: %s", e)
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
            logger.error("[Feishu] Failed to get access token: %s", e)
            return None

    def _split_message(self, content: str) -> List[str]:
        """分割消息"""
        if len(content) <= self.MAX_MESSAGE_LENGTH:
            return [content]

        chunks = []
        paragraphs = content.split("\n\n")
        current = ""

        for para in paragraphs:
            if len(current) + len(para) + 2 <= self.MAX_MESSAGE_LENGTH:
                current += ("\n\n" if current else "") + para
            else:
                if current:
                    chunks.append(current)
                current = para

        if current:
            chunks.append(current)

        return chunks if chunks else [content]

    async def send_image(self, chat_id: str, image_path: str, **kwargs) -> SendResult:
        """发送图片"""
        return SendResult(success=False, error="Not implemented")

    async def send_file(self, chat_id: str, file_path: str, **kwargs) -> SendResult:
        """发送文件"""
        return SendResult(success=False, error="Not implemented")

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """获取聊天信息"""
        return {"name": chat_id, "type": "dm"}


# ── Phase E 插件注册 ────────────────────────────────────
# 配置读写回调走主程序 Settings（存量用户配置零迁移；Task 5 统一切 E1
# PluginConfigStore 时仅改本块闭包，调用方不动）。闭包内延迟 import
# Settings/PlatformConfig，避免模块顶层触发 PyQt5 / Settings 副作用。


def _build_config() -> "PlatformConfig":
    """读 PluginConfigStore 构造飞书配置（E1 契约：插件自包含存储）"""
    from app.gateway.base import Platform, PlatformConfig
    from app.plugins.managers.plugin_config_store import PluginConfigStore

    store = PluginConfigStore()
    return PlatformConfig(
        enabled=bool(store.get("gateway-feishu", "enabled")),
        platform=Platform.FEISHU,
        extra={
            "app_id": store.get("gateway-feishu", "app_id") or "",
            "app_secret": store.get("gateway-feishu", "app_secret") or "",
        },
    )


def _write_config(config: "PlatformConfig") -> None:
    from app.plugins.managers.plugin_config_store import PluginConfigStore

    PluginConfigStore().set_values(
        "gateway-feishu",
        {
            "enabled": config.enabled,
            "app_id": (config.extra or {}).get("app_id") or "",
            "app_secret": (config.extra or {}).get("app_secret") or "",
        },
    )


def _build_config_values(values: dict, old_config) -> "PlatformConfig":
    """设置卡保存回调：表单值 → PluginConfigStore → PlatformConfig。"""
    from app.gateway.base import Platform, PlatformConfig
    from app.plugins.managers.plugin_config_store import PluginConfigStore

    store = PluginConfigStore()
    plugin = "gateway-feishu"
    enabled = values.get("enabled", store.get(plugin, "enabled"))
    app_id = values.get("app_id", "")
    app_secret = values.get("app_secret", "")
    store.set_values(
        plugin,
        {
            "enabled": bool(enabled),
            "app_id": app_id,
            "app_secret": app_secret,
        },
    )
    extra = dict(old_config.extra) if old_config and old_config.extra else {}
    if app_id:
        extra["app_id"] = app_id
    if app_secret:
        extra["app_secret"] = app_secret
    return PlatformConfig(
        enabled=bool(enabled),
        platform=Platform.FEISHU,
        extra=extra,
    )


def register(registry) -> None:
    from app.plugins.contracts.gateway_platform import GatewayPlatformDef

    registry.register(
        GatewayPlatformDef(
            platform_id="feishu",
            display_name="飞书",
            adapter_factory=lambda cfg: FeishuAdapter(cfg),
            check_requirements=check_feishu_requirements,
            config_builder=_build_config,
            config_writer=_write_config,
            build_config_values=_build_config_values,
            validate_config=lambda cfg: (
                bool(cfg.extra.get("app_id") and cfg.extra.get("app_secret")),
                "AppID/Secret 未配置",
            ),
            ui_order=50,
        )
    )
