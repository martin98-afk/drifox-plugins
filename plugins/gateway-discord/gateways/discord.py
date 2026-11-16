# -*- coding: utf-8 -*-
"""
Discord 平台适配器（社区插件，万物即插件 Phase E）

使用 discord.py 库进行消息收发。

本文件原位于 app/gateway/adapters/discord.py（E2 Task 5 迁入）。
适配器实现保持原状（SDK 延迟导入纪律：模块顶层不 eager import 平台 SDK）。
"""

from __future__ import annotations

import os as _os


# 依赖注入已由宿主统一接管：PluginManager 扫描时注入 deps/ 与 deps/<platform>/
# （平台目录优先，见 app/plugins/deps_loader.py），插件组件不再自理 sys.path。
from typing import Any, Dict, List, Optional

from loguru import logger

from app.gateway.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
)

MAX_INBOUND_IMAGES = 10


def _cache_dir():
    """入站图片缓存目录：优先宿主 get_cache_dir，缺失时退回默认数据目录。"""
    try:
        from app.gateway.base import get_cache_dir

        return get_cache_dir("discord")
    except Exception:
        from pathlib import Path

        fallback = Path.home() / ".drifox" / "gateway" / "cache" / "discord"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

# 延迟导入
DISCORD_AVAILABLE = False


def check_discord_requirements() -> bool:
    """检查 Discord 依赖是否可用"""
    global DISCORD_AVAILABLE
    if DISCORD_AVAILABLE:
        return True
    try:
        import discord

        DISCORD_AVAILABLE = True
        return True
    except ImportError:
        logger.error("[Discord] discord.py not installed. Run: pip install discord.py")
        return False


class DiscordAdapter(BasePlatformAdapter):
    """
    Discord 机器人适配器

    支持：
    - 私聊和服务器频道
    - 线程 (Threads)
    - 媒体消息
    - Slash Commands
    """

    MAX_MESSAGE_LENGTH = 2000  # Discord 消息长度限制

    def __init__(self) -> None:
        super().__init__()
        cfg = _config()
        self._token = cfg["token"]
        self._client = None
        self._guilds = {}

        # 群组触发配置
        self._require_mention = cfg["require_mention"]

        # 流式回复状态：chat_id -> {channel, message, last_edit, last_text}
        self._stream_states: Dict[str, Dict[str, Any]] = {}

    async def connect(self) -> bool:
        """连接到 Discord"""
        if not check_discord_requirements():
            logger.error("[Discord] Dependencies not available")
            self._last_error = "依赖不可用"
            return False

        if not self._token:
            logger.error("[Discord] No bot token configured")
            self._last_error = "未配置 Bot Token"
            return False

        try:
            import discord
            from discord import Intents

            # 创建意图
            intents = Intents.default()
            intents.message_content = True  # 需要开启 Message Content Intent
            intents.guilds = True
            intents.messages = True

            # 创建客户端
            self._client = discord.Client(intents=intents)

            # 注册事件
            @self._client.event
            async def on_message(message):
                await self._handle_message(message)

            @self._client.event
            async def on_ready():
                logger.info(f"[Discord] Logged in as {self._client.user}")
                self._connected = True

            # 登录
            await self._client.start(self._token)

        except Exception as e:
            logger.error(f"[Discord] Failed to connect: {e}")
            return False

    async def _handle_message(self, message):
        """处理收到的消息"""
        import discord  # 局部导入：模块顶层不 eager import 平台 SDK

        # 忽略机器人消息
        if message.author.bot:
            return

        # 忽略系统消息
        if message.type not in (
            None,
            discord.MessageType.default,
            discord.MessageType.reply,
        ):
            return

        # 群消息先留档（含没 @机器人 的），被叫住时才有前文可参考
        if getattr(message.channel, "guild", None) is not None:
            self._capture_group_message(message)

        # 检查是否需要 @ 机器人
        if self._require_mention and not self._bot_mentioned(message):
            return

        # 确定消息类型
        if message.content and message.content.startswith("/"):
            msg_type = MessageType.COMMAND
        elif message.attachments:
            if any(a.content_type and a.content_type.startswith("image/") for a in message.attachments):
                msg_type = MessageType.IMAGE
            else:
                msg_type = MessageType.FILE
        else:
            msg_type = MessageType.TEXT

        # 构建事件
        event = self._build_message_event(message, msg_type)
        await self._attach_inbound_media(event, message)
        await self.handle_message(event)

    def _capture_group_message(self, message) -> None:
        """群消息留档到宿主存档（失败不影响消息处理）。"""
        try:
            from app.gateway.group_history import get_group_history_store

            get_group_history_store().capture(
                "discord",
                str(message.channel.id),
                text=message.content or "",
                user_id=str(message.author.id),
                user_name=message.author.display_name or message.author.name,
                message_id=str(message.id),
                chat_type="group",
            )
        except Exception as e:
            logger.debug(f"[Discord] 群消息留档失败: {e}")

    def _bot_mentioned(self, message) -> bool:
        """检查消息是否 @ 机器人"""
        if not self._client or not self._client.user:
            return True  # 没有用户信息，默认处理

        # 检查是否直接回复机器人
        if message.reference:
            replied_msg = message.reference.cached_message
            if replied_msg and replied_msg.author.id == self._client.user.id:
                return True

        # 检查内容是否包含机器人 mention
        if hasattr(message, "mentions") and self._client.user in message.mentions:
            return True

        # 检查是否在 DM 中
        if isinstance(message.channel, discord.DMChannel):
            return True

        return False

    async def _attach_inbound_media(self, event: MessageEvent, message) -> None:
        """把附件下载到本地缓存（宿主只认本地文件，不接受远端 URL）。"""
        paths, kinds = [], []
        for attachment in message.attachments[:MAX_INBOUND_IMAGES]:
            is_image = (getattr(attachment, "content_type", "") or "").startswith("image/")
            try:
                filename = getattr(attachment, "filename", "") or ""
                suffix = _os.path.splitext(filename)[1] or (".png" if is_image else ".bin")
                target = _cache_dir() / f"{getattr(attachment, 'id', 'file')}{suffix}"
                if not target.exists():
                    await attachment.save(target)
                paths.append(str(target))
                kinds.append("image" if is_image else "file")
            except Exception as e:
                logger.warning("[Discord] 入站附件下载失败: {}", e)
        if paths:
            event.media_urls = paths
            event.media_types = kinds

    def _build_message_event(self, message, msg_type: MessageType) -> MessageEvent:
        """构建消息事件"""
        # 媒体由 _attach_inbound_media 下载后填本地路径（远端 URL 宿主无法使用）
        media_urls = []
        media_types = []

        # 用户名
        user_name = message.author.display_name or message.author.name

        return MessageEvent(
            text=message.content or "",
            message_type=msg_type,
            message_id=str(message.id),
            chat_id=str(message.channel.id),
            user_id=str(message.author.id),
            user_name=user_name,
            platform="discord",
            chat_type="dm" if isinstance(message.channel, discord.DMChannel) else "group",
            media_urls=media_urls,
            media_types=media_types,
            metadata={
                "guild_id": str(message.guild.id) if message.guild else "",
                "channel_name": message.channel.name,
            },
        )

    async def disconnect(self) -> None:
        """断开连接"""
        if self._client:
            try:
                await self._client.close()
            except Exception as e:
                logger.warning(f"[Discord] Error during disconnect: {e}")

        self._connected = False
        logger.info("[Discord] Disconnected")

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """发送消息"""
        if not self._client:
            return SendResult(success=False, error="Not connected")

        try:
            channel = self._client.get_channel(int(chat_id))
            if not channel:
                return SendResult(success=False, error=f"Channel {chat_id} not found")

            # 分割长消息
            if len(content) > self.MAX_MESSAGE_LENGTH:
                chunks = self._split_message(content)
            else:
                chunks = [content]

            message_ids = []

            for i, chunk in enumerate(chunks):
                if len(chunks) > 1:
                    chunk = f"[{i + 1}/{len(chunks)}] {chunk}"

                msg = await channel.send(content=chunk)
                message_ids.append(str(msg.id))

            return SendResult(
                success=True,
                message_id=message_ids[0] if message_ids else None,
            )

        except Exception as e:
            logger.error(f"[Discord] Send failed: {e}", exc_info=True)
            return SendResult(success=False, error=str(e))

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

    async def send_image(
        self,
        chat_id: str,
        image_url: str,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """发送图片"""
        if not self._client:
            return SendResult(success=False, error="Not connected")

        try:
            import discord

            channel = self._client.get_channel(int(chat_id))
            if not channel:
                return SendResult(success=False, error=f"Channel {chat_id} not found")

            # Discord embed 格式
            embed = discord.Embed()
            if image_url.startswith("http"):
                embed.set_image(url=image_url)
            else:
                # 本地路径
                embed.set_image(url=f"attachment://{image_url.split('/')[-1]}")

            if caption:
                embed.description = caption

            if image_url.startswith("http"):
                msg = await channel.send(embed=embed)
            else:
                # 本地文件 - 上传为附件
                import discord as dc

                file = dc.File(image_url)
                msg = await channel.send(file=file, embed=embed)

            return SendResult(success=True, message_id=str(msg.id))

        except Exception as e:
            logger.error(f"[Discord] Send image failed: {e}", exc_info=True)
            return SendResult(success=False, error=str(e))

    async def send_file(self, chat_id: str, file_path: str, **kwargs) -> SendResult:
        """发送文件（discord.File 附件上传）"""
        if not self._client:
            return SendResult(success=False, error="Not connected")
        try:
            import discord
            channel = self._client.get_channel(int(chat_id))
            if not channel:
                return SendResult(success=False, error=f"Channel {chat_id} not found")
            msg = await channel.send(file=discord.File(file_path))
            return SendResult(success=True, message_id=str(msg.id))
        except Exception as e:
            logger.error(f"[Discord] Send file failed: {e}", exc_info=True)
            return SendResult(success=False, error=str(e))

    async def send_typing(self, chat_id: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """发送 typing 状态"""
        if self._client:
            try:
                channel = self._client.get_channel(int(chat_id))
                if channel:
                    async with channel.typing():
                        pass
            except Exception:
                pass  # Typing failures are non-fatal

    # ── 流式回复（编辑占位消息，对齐 dsh-im editable-message-stream） ──

    _STREAM_EDIT_INTERVAL = 1.1  # Discord 编辑限流：5 次/5 秒

    def supports_streaming(self, chat_id: str) -> bool:
        """Discord 可编辑自发的消息，所有频道都支持打字机式输出。"""
        return self._client is not None

    async def start_stream(self, chat_id: str) -> Optional[str]:
        """发占位消息，返回 stream_key=``dc:<chat_id>:<message_id>``；失败返回 None。"""
        if not self._client:
            return None
        try:
            channel = self._client.get_channel(int(chat_id))
            if not channel:
                return None
            msg = await channel.send(content="💭 正在思考…")
        except Exception as e:
            logger.warning(f"[Discord] start_stream failed: {e}")
            return None
        self._stream_states[str(chat_id)] = {
            "channel": channel,
            "message": msg,
            "last_edit": 0.0,
            "last_text": "💭 正在思考…",
        }
        return f"dc:{chat_id}:{msg.id}"

    async def update_stream(self, stream_key: str, snapshot: str) -> bool:
        """把可见快照写进占位消息；单次失败不致命（finish 会补最终全文）。"""
        state = self._stream_state(stream_key)
        if state is None:
            return False
        import time as _time

        now = _time.monotonic()
        if now - float(state.get("last_edit") or 0.0) < self._STREAM_EDIT_INTERVAL:
            return True  # 让宿主继续推，最终由 finish_stream 收口
        text = (snapshot or "").strip()
        if not text or text == state.get("last_text"):
            return True
        text = text[: self.MAX_MESSAGE_LENGTH]
        try:
            await state["message"].edit(content=text)
        except Exception as e:
            logger.debug(f"[Discord] stream edit skipped: {e}")
            return True  # 单次编辑失败不放弃整条流，最终 finish 兜底
        state["last_edit"] = now
        state["last_text"] = text
        return True

    async def finish_stream(self, stream_key: str, final: str) -> SendResult:
        """写入最终全文，超长分段补发，然后清理流状态。"""
        state = self._stream_state(stream_key)
        if state is None:
            return SendResult(success=False, error="unknown stream")
        chat_id = str(stream_key.split(":", 2)[1])
        message = state["message"]
        channel = state["channel"]
        try:
            parts = []
            for chunk in self._split_message(final or "（无输出）"):
                while len(chunk) > self.MAX_MESSAGE_LENGTH:
                    parts.append(chunk[: self.MAX_MESSAGE_LENGTH])
                    chunk = chunk[self.MAX_MESSAGE_LENGTH:]
                if chunk:
                    parts.append(chunk)
            await message.edit(content=parts[0])
            last_id = message.id
            for part in parts[1:]:
                msg = await channel.send(content=part)
                last_id = msg.id
            return SendResult(success=True, message_id=str(last_id))
        except Exception as e:
            logger.warning(f"[Discord] finish_stream failed: {e}")
            return SendResult(success=False, error=str(e))
        finally:
            self._stream_states.pop(chat_id, None)

    def _stream_state(self, stream_key: str) -> Optional[Dict[str, Any]]:
        """解析 ``dc:<chat_id>:<message_id>`` 定位流状态。"""
        if not stream_key or not stream_key.startswith("dc:"):
            return None
        parts = stream_key.split(":", 2)
        if len(parts) != 3:
            return None
        return self._stream_states.get(parts[1])

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """获取聊天信息"""
        if not self._client:
            return {"name": "Unknown", "type": "dm"}

        try:
            import discord

            channel = self._client.get_channel(int(chat_id))
            if channel:
                return {
                    "name": channel.name or str(chat_id),
                    "type": "dm" if isinstance(channel, discord.DMChannel) else "group",
                }
        except Exception as e:
            logger.error(f"[Discord] get_chat_info failed: {e}")

        return {"name": str(chat_id), "type": "dm"}


# ── Phase E 插件注册 ────────────────────────────────────
# 配置读写回调走主程序 Settings（存量用户配置零迁移；Task 5 统一切 E1
# PluginConfigStore 时仅改本块闭包，调用方不动）。闭包内延迟 import
# 宿主契约不承载平台配置，避免模块顶层触发 Settings 副作用。


PLUGIN_NAME = "gateway-discord"

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
        "token": values.get("token") or "",
        "require_mention": bool(values.get("require_mention", True)),
    }


def _set_enabled(enabled: bool) -> None:
    writer = _cap("plugin.config.write")
    if writer is not None:
        writer("enabled", bool(enabled))


def _validate() -> tuple:
    cfg = _config()
    return bool(cfg["token"]), "Token 未配置"


def register(registry) -> None:
    from app.plugins.contracts.gateway_platform import GatewayPlatformDef

    registry.register(
        GatewayPlatformDef(
            platform_id="discord",
            display_name="Discord",
            adapter_factory=DiscordAdapter,
            check_requirements=check_discord_requirements,
            is_enabled=lambda: _config()["enabled"],
            set_enabled=_set_enabled,
            validate=_validate,
            ui_order=40,
        )
    )
