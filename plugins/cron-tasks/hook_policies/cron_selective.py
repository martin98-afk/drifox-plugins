# -*- coding: utf-8 -*-
"""cron-tasks 专属可配置事件白名单 hook 策略（id="cron_selective"，scope="main"）。

每个 hook 节点是否触发由配置文件决定（白名单语义，未列出 = 不触发）：

    <app_data>/plugin_data/cron-tasks/hook_policy.json
    {"SessionStart": true, "PreToolUse": true, "PostToolUse": true}

- mtime 缓存：改文件即时生效，无需重载插件/主程序
- 文件不存在/损坏 → 内置默认（SessionStart + PreToolUse + PostToolUse，
  对无人值守任务最合理的参与面）
- 启用方式：executor 经 create_engine_session 传 hook_policy_id="cron_selective"；
  工具级/Stop 等 worker 侧事件由 worker 按本策略过滤，
  SessionStart 由 EngineSession 会话初始化时按本策略判定触发（需主程序支持）。
"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from app.plugins.contracts.hook_policy import (
    BuildSystemPromptEvent,
    HookDecision,
    HookEvent,
    PluginChangedEvent,
    PostAssistantMessageEvent,
    PostToolUseEvent,
    PostUserMessageEvent,
    PreAssistantMessageEvent,
    PreToolUseEvent,
    PreUserMessageEvent,
    SessionStartEvent,
    StopEvent,
    TeamMailEvent,
)

# 事件类 → hook 事件名（与 hooks.json / 设置页命名一致）
_EVENT_NAMES = {
    SessionStartEvent: "SessionStart",
    BuildSystemPromptEvent: "BuildSystemPrompt",
    PreUserMessageEvent: "PreUserMessage",
    PostUserMessageEvent: "PostUserMessage",
    PreAssistantMessageEvent: "PreAssistantMessage",
    PostAssistantMessageEvent: "PostAssistantMessage",
    PreToolUseEvent: "PreToolUse",
    PostToolUseEvent: "PostToolUse",
    StopEvent: "Stop",
    PluginChangedEvent: "PluginChanged",
    TeamMailEvent: "TeamMail",
}

# 配置文件不存在/损坏时的内置默认（对无人值守任务最合理的参与面）
_DEFAULT_EVENTS = {"SessionStart": True, "PreToolUse": True, "PostToolUse": True}


def _config_path() -> Path:
    from app.utils.utils import get_app_data_dir

    return get_app_data_dir() / "plugin_data" / "cron-tasks" / "hook_policy.json"


class CronSelectiveHookPolicy:
    """cron-tasks 专属可配置事件白名单策略 — 主智能体域"""

    id = "cron_selective"
    scope = "main"

    def __init__(self):
        self._events: dict = {}
        self._mtime: float = -1.0
        self._missing_logged = False

    def _load(self) -> dict:
        """读配置（mtime 缓存，文件变化即时生效）"""
        path = _config_path()
        try:
            mtime = path.stat().st_mtime
        except OSError:
            if not self._missing_logged:
                logger.info("[HookPolicy:cron_selective] 配置文件不存在，使用内置默认白名单")
                self._missing_logged = True
            self._events = dict(_DEFAULT_EVENTS)
            self._mtime = -2.0
            return self._events
        if mtime == self._mtime:
            return self._events
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            self._events = {k: bool(v) for k, v in raw.items()}
            self._mtime = mtime
            logger.info(f"[HookPolicy:cron_selective] 配置加载: {self._events}")
        except Exception as e:
            logger.warning(f"[HookPolicy:cron_selective] 配置读取失败，沿用内置默认: {e}")
            self._events = dict(_DEFAULT_EVENTS)
            self._mtime = -2.0
        return self._events

    def should_trigger(self, event: HookEvent) -> HookDecision:
        name = _EVENT_NAMES.get(type(event))
        if name is None:
            return HookDecision.SKIP
        return HookDecision.TRIGGER if self._load().get(name, False) else HookDecision.SKIP


def register(registry):
    registry.register(CronSelectiveHookPolicy())
