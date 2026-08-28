# -*- coding: utf-8 -*-
"""
Telegram 平台适配器（社区插件，万物即插件 Phase E）

使用 python-telegram-bot 库进行消息收发。

本文件原位于 app/gateway/adapters/telegram.py（E2 Task 4 迁入）。
适配器实现保持原状（SDK 延迟导入纪律：模块顶层不 eager import 平台 SDK）。
"""

from __future__ import annotations


# ── 插件自包含依赖注入：优先加载本插件 deps/ 目录 ────────────────
# 平台 SDK（python-telegram-bot 及其传递依赖）vendor 到插件根 deps/（即
# gateways/ 的上一级）：本插件为社区插件，依赖自包含于 <plugin>/deps/；顶层只注入
# 路径，SDK 本体仍在函数内延迟导入。注意：__file__ 在 gateways/ 内，需 .. 回退到插件根再进 deps。
import os as _os, sys as _sys
_deps = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', 'deps'))
if _deps not in _sys.path:
    _sys.path.insert(0, _deps)
import asyncio
from typing import Any, Dict, List, Optional

from loguru import logger

from app.gateway.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    Platform,
    PlatformConfig,
    SendResult,
)

# 延迟导入避免在没有安装时崩溃
TELEGRAM_AVAILABLE = False
Application = None
Update = None
Bot = None
Message = None


def check_telegram_requirements() -> bool:
    """检查 Telegram 依赖是否可用"""
    global TELEGRAM_AVAILABLE, Application, Update, Bot, Message
    if TELEGRAM_AVAILABLE:
        return True
    try:
        from telegram import Bot, Message, Update
        from telegram.constants import ChatType, ParseMode
        from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler
        from telegram.request import HTTPXRequest
        TELEGRAM_AVAILABLE = True
        return True
    except ImportError:
        logger.error("[Telegram] python-telegram-bot not installed. Run: pip install python-telegram-bot")
        return False


class TelegramAdapter(BasePlatformAdapter):
    """
    Telegram 机器人适配器
    
    支持：
    - 私聊和群组消息
    - 论坛主题 (Forum Topics)
    - 媒体消息 (照片、视频、音频、文件)
    - 命令处理 (/start, /help 等)
    """

    MAX_MESSAGE_LENGTH = 4096  # Telegram 消息长度限制

    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform.TELEGRAM)
        self._app = None
        self._bot = None
        self._polling_task = None
        self._update_id = None

        # 群组触发配置
        self._require_mention = config.extra.get("require_mention", True)

    async def connect(self) -> bool:
        """连接到 Telegram Bot API"""
        if not check_telegram_requirements():
            logger.error("[Telegram] Dependencies not available")
            self._last_error = "依赖不可用"
            return False

        if not self.config.token:
            logger.error("[Telegram] No bot token configured")
            self._last_error = "未配置 Bot Token"
            return False

        try:
            from telegram.ext import Application, MessageHandler

            # 创建应用
            self._app = Application.builder().token(self.config.token).build()
            self._bot = self._app.bot

            # 注册处理器
            self._app.add_handler(MessageHandler(
                None,  # 所有消息
                self._handle_message
            ))

            # 启动轮询
            await self._app.initialize()
            await self._app.start()

            # 在后台任务中运行轮询
            self._polling_task = asyncio.create_task(self._run_polling())

            self._connected = True
            logger.info("[Telegram] Connected successfully (long polling)")
            return True

        except Exception as e:
            logger.error(f"[Telegram] Failed to connect: {e}")
            return False

    async def _run_polling(self):
        """轮询接收消息"""
        try:
            await self._app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        except Exception as e:
            logger.error(f"[Telegram] Polling error: {e}")
            self._connected = False

    async def _handle_message(self, update, context):
        """处理收到的消息"""
        if not update.message:
            return

        msg = update.message

        # 检查群组触发规则
        if self._is_group_chat(msg) and self._require_mention:
            if not self._message_mentions_bot(msg):
                return

        # 确定消息类型
        if msg.text:
            msg_type = MessageType.COMMAND if msg.text.startswith('/') else MessageType.TEXT
        elif msg.photo:
            msg_type = MessageType.IMAGE
        elif msg.video:
            msg_type = MessageType.VIDEO
        elif msg.voice:
            msg_type = MessageType.AUDIO
        elif msg.audio:
            msg_type = MessageType.AUDIO
        elif msg.document:
            msg_type = MessageType.FILE
        else:
            msg_type = MessageType.TEXT

        # 构建事件
        event = self._build_message_event(msg, msg_type)
        await self.handle_message(event)

    def _is_group_chat(self, message) -> bool:
        """检查是否为群组聊天"""
        chat = getattr(message, "chat", None)
        if not chat:
            return False
        chat_type = str(getattr(chat, "type", "")).lower()
        return chat_type in {"group", "supergroup"}

    def _message_mentions_bot(self, message) -> bool:
        """检查消息是否 @ 机器人"""
        if not self._bot:
            return False

        bot_username = getattr(self._bot, "username", None)
        if not bot_username:
            return False

        text = getattr(message, "text", "") or ""
        entities = getattr(message, "entities", []) or []

        # 检查实体中的 mention
        for entity in entities:
            if str(getattr(entity, "type", "")).lower() == "mention":
                offset = getattr(entity, "offset", 0)
                length = getattr(entity, "length", 0)
                mention_text = text[offset:offset+length] if text else ""
                if mention_text.lower() == f"@{bot_username}".lower():
                    return True

        return False

    def _build_message_event(self, message, msg_type: MessageType) -> MessageEvent:
        """从 Telegram 消息构建 MessageEvent"""
        chat = message.chat
        user = message.from_user

        chat_type = "dm"
        if self._is_group_chat(message):
            chat_type = "group"

        # 处理论坛主题
        thread_id = getattr(message, "message_thread_id", None)
        thread_id_str = str(thread_id) if thread_id else None

        return MessageEvent(
            text=getattr(message, "text", "") or getattr(message, "caption", "") or "",
            message_type=msg_type,
            message_id=str(getattr(message, "message_id", "")),
            chat_id=str(getattr(chat, "id", "")),
            user_id=str(getattr(user, "id", "")) if user else "",
            user_name=getattr(user, "full_name", "") if user else "",
            platform=Platform.TELEGRAM,
            chat_type=chat_type,
            media_urls=self._extract_media_urls(message),
            media_types=self._extract_media_types(message),
            metadata={"thread_id": thread_id_str} if thread_id_str else {},
        )

    def _extract_media_urls(self, message) -> List[str]:
        """提取媒体 URL"""
        urls = []

        if hasattr(message, "photo") and message.photo:
            # 使用最大尺寸的照片
            photo = message.photo[-1]
            if hasattr(photo, "file_id"):
                urls.append(f"file://telegram_photo:{photo.file_id}")

        if hasattr(message, "video") and message.video:
            if hasattr(message.video, "file_id"):
                urls.append(f"file://telegram_video:{message.video.file_id}")

        if hasattr(message, "voice") and message.voice:
            if hasattr(message.voice, "file_id"):
                urls.append(f"file://telegram_voice:{message.voice.file_id}")

        return urls

    def _extract_media_types(self, message) -> List[str]:
        """提取媒体类型"""
        types = []

        if hasattr(message, "photo") and message.photo:
            types.append("image/jpeg")
        if hasattr(message, "video") and message.video:
            types.append("video/mp4")
        if hasattr(message, "voice") and message.voice:
            types.append("audio/ogg")

        return types

    async def disconnect(self) -> None:
        """断开连接"""
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass

        if self._app:
            try:
                await self._app.stop()
                await self._app.shutdown()
            except Exception as e:
                logger.warning(f"[Telegram] Error during disconnect: {e}")

        self._connected = False
        logger.info("[Telegram] Disconnected")

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """发送消息"""
        if not self._bot:
            return SendResult(success=False, error="Not connected")

        try:
            from telegram.constants import ParseMode

            # Telegram 上限 4096：分片发送（末片附 continue 提示语除外，顺序保证）
            parts = self._split_telegram(content, 3800)
            last_msg_id = None
            for i, part in enumerate(parts):
                formatted = self._format_telegram_text(part)
                kwargs = {
                    "chat_id": int(chat_id),
                    "text": formatted,
                    "parse_mode": ParseMode.HTML,
                }
                if reply_to and i == 0:
                    kwargs["reply_to_message_id"] = int(reply_to)
                if metadata and metadata.get("thread_id"):
                    kwargs["message_thread_id"] = int(metadata["thread_id"])
                msg = await self._bot.send_message(**kwargs)
                last_msg_id = str(msg.message_id)
            return SendResult(success=True, message_id=last_msg_id)

        except Exception as e:
            logger.error(f"[Telegram] Send failed: {e}")
            return SendResult(success=False, error=str(e))

    @staticmethod
    def _split_telegram(text: str, limit: int) -> list:
        """按换行边界分片（超限单行硬切）"""
        if len(text) <= limit:
            return [text]
        parts, buf = [], ""
        for line in text.split("\n"):
            candidate = (buf + "\n" + line) if buf else line
            if len(candidate) > limit and buf:
                parts.append(buf)
                buf = line
            else:
                buf = candidate
            while len(buf) > limit:  # 单行超限硬切
                parts.append(buf[:limit])
                buf = buf[limit:]
        if buf:
            parts.append(buf)
        return parts

    _HTML_ESCAPES = (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"))

    @classmethod
    def _format_telegram_text(cls, content: str) -> str:
        """Markdown → Telegram HTML（对齐 openhanako telegram-format 思路）。

        映射：**粗**→<b>、*斜*/_斜_→<i>、`code`→<code>、```块→<pre>、
        [文](url)→<a>、# 标题→<b>行</b>、- 列表→• ；非标记的 <>& 转义保安全。
        替代旧 MARKDOWN_V2+全量转义方案（那会把所有标记杀成字面量反斜杠）。
        """
        import re

        if not content:
            return content

        def esc(t: str) -> str:
            for ch, rep in cls._HTML_ESCAPES:
                t = t.replace(ch, rep)
            return t

        # 行内处理：先提取代码段保护，再转换义，再还原标记
        code_spans = []

        def _stash_code(m):
            code_spans.append(m.group(1))
            return f"\x00{len(code_spans) - 1}\x00"

        # 先 stash 代码块（三反引号），再 stash 行内 code，再 esc，最后还原
        pre_blocks = []

        def _stash_pre(m):
            pre_blocks.append(m.group(1))
            return f"\x01{len(pre_blocks) - 1}\x01"

        text = re.sub(r"```[a-zA-Z0-9_+-]*\n?([\s\S]*?)```", _stash_pre, content)
        text = re.sub(r"`([^`\n]+)`", _stash_code, text)
        text = esc(text)

        text = re.sub(r"\*\*([^*\n]+)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", text)
        text = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"<i>\1</i>", text)
        text = re.sub(r"~~([^~\n]+)~~", r"<s>\1</s>", text)
        text = re.sub(
            r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)",
            lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>',
            text,
        )
        text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.M)
        text = re.sub(r"^[-*+]\s+(.+)$", r"• \1", text, flags=re.M)

        def _unstash(m):
            return f"<code>{esc(code_spans[int(m.group(1))])}</code>"

        text = re.sub(r"\x00(\d+)\x00", _unstash, text)

        # 代码块还原为 <pre>（内部已 esc）
        text = re.sub(r"\x01(\d+)\x01", lambda m: f"<pre>{esc(pre_blocks[int(m.group(1))])}</pre>", text)
        return text

    async def send_image(
        self,
        chat_id: str,
        image_url: str,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """发送图片"""
        if not self._bot:
            return SendResult(success=False, error="Not connected")

        try:
            kwargs = {
                "chat_id": int(chat_id),
                "photo": image_url,
            }
            if caption:
                kwargs["caption"] = caption[:1024]
            if reply_to:
                kwargs["reply_to_message_id"] = int(reply_to)
            if metadata and metadata.get("thread_id"):
                kwargs["message_thread_id"] = int(metadata["thread_id"])

            msg = await self._bot.send_photo(**kwargs)
            return SendResult(success=True, message_id=str(msg.message_id))

        except Exception as e:
            logger.error(f"[Telegram] Send image failed: {e}")
            return SendResult(success=False, error=str(e))

    async def send_document(
        self,
        chat_id: str,
        file_path: str,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """发送文件"""
        if not self._bot:
            return SendResult(success=False, error="Not connected")

        try:
            with open(file_path, "rb") as f:
                kwargs = {
                    "chat_id": int(chat_id),
                    "document": f,
                }
                if caption:
                    kwargs["caption"] = caption[:1024]
                if reply_to:
                    kwargs["reply_to_message_id"] = int(reply_to)
                if metadata and metadata.get("thread_id"):
                    kwargs["message_thread_id"] = int(metadata["thread_id"])

                msg = await self._bot.send_document(**kwargs)
                return SendResult(success=True, message_id=str(msg.message_id))

        except Exception as e:
            logger.error(f"[Telegram] Send document failed: {e}")
            return SendResult(success=False, error=str(e))

    async def send_typing(self, chat_id: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """发送 typing 状态"""
        if self._bot:
            try:
                kwargs = {"chat_id": int(chat_id), "action": "typing"}
                if metadata and metadata.get("thread_id"):
                    kwargs["message_thread_id"] = int(metadata["thread_id"])
                await self._bot.send_chat_action(**kwargs)
            except Exception:
                pass  # Typing failures are non-fatal

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """获取聊天信息"""
        if not self._bot:
            return {"name": "Unknown", "type": "dm"}

        try:
            chat = await self._bot.get_chat(int(chat_id))
            return {
                "name": chat.title or chat.full_name or str(chat_id),
                "type": "dm" if chat.type == "private" else "group",
            }
        except Exception as e:
            logger.error(f"[Telegram] get_chat_info failed: {e}")
            return {"name": str(chat_id), "type": "dm"}


# ── Phase E 插件注册 ────────────────────────────────────
# 配置读写回调走主程序 Settings（存量用户配置零迁移；Task 5 统一切 E1
# PluginConfigStore 时仅改本块闭包，调用方不动）。闭包内延迟 import
# Settings/PlatformConfig，避免模块顶层触发 PySide6 / Settings 副作用。


def _build_config() -> "PlatformConfig":
    """读 PluginConfigStore 构造 Telegram 配置（E1 契约：插件自包含存储）。

    字段键：enabled / token / require_mention（plugin.json config_schema 声明）。
    require_mention 在 extra dict 中保持原样（适配器 ``config.extra.get(...)``
    已做 bool 兜底）。"""
    from app.gateway.base import Platform, PlatformConfig
    from app.plugins.managers.plugin_config_store import PluginConfigStore

    store = PluginConfigStore()
    return PlatformConfig(
        enabled=bool(store.get("gateway-telegram", "enabled")),
        platform=Platform.TELEGRAM,
        token=store.get("gateway-telegram", "token") or "",
        extra={"require_mention": bool(store.get("gateway-telegram", "require_mention"))},
    )


def _write_config(config: "PlatformConfig") -> None:
    from app.plugins.managers.plugin_config_store import PluginConfigStore

    PluginConfigStore().set_values(
        "gateway-telegram",
        {
            "enabled": config.enabled,
            "token": config.token or "",
            "require_mention": (
                bool(config.extra.get("require_mention", True))
                if config.extra
                else True
            ),
        },
    )


def _build_config_values(values: dict, old_config) -> "PlatformConfig":
    """设置卡保存回调：表单值 → PluginConfigStore → PlatformConfig。

    enabled / require_mention 在主仓表单无对应输入控件（启用开关在状态行，
    require_mention 仅插件自管 UI 才用），由 PluginConfigStore 兜底当前值：
    values 缺则读 store 现有值（无则 schema 默认）。
    """
    from app.gateway.base import Platform, PlatformConfig
    from app.plugins.managers.plugin_config_store import PluginConfigStore

    store = PluginConfigStore()
    plugin = "gateway-telegram"
    enabled = values.get("enabled", store.get(plugin, "enabled"))
    require_mention = values.get(
        "require_mention", store.get(plugin, "require_mention")
    )
    token = values.get("token", "")
    # 先落盘（让后续 store.get 即时可见新值；空串被 store 视为清除）
    store.set_values(
        plugin,
        {
            "enabled": bool(enabled),
            "token": token,
            "require_mention": _truthy(require_mention),
        },
    )
    extra = dict(old_config.extra) if old_config and old_config.extra else {}
    extra["require_mention"] = _truthy(require_mention)
    return PlatformConfig(
        enabled=bool(enabled),
        platform=Platform.TELEGRAM,
        token=token,
        extra=extra,
    )


def _truthy(v) -> bool:
    """表单 truthy 判定（QLineEdit 文本 'true'/'false' → bool）。"""
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def register(registry) -> None:
    from app.plugins.contracts.gateway_platform import GatewayPlatformDef

    registry.register(
        GatewayPlatformDef(
            platform_id="telegram",
            display_name="Telegram",
            adapter_factory=lambda cfg: TelegramAdapter(cfg),
            check_requirements=check_telegram_requirements,
            config_builder=_build_config,
            config_writer=_write_config,
            build_config_values=_build_config_values,
            validate_config=lambda cfg: (bool(cfg.token), "Token 未配置"),
            ui_order=30,
        )
    )