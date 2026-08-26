# -*- coding: utf-8 -*-
"""taskboard 专用 Hook 策略 — 仅跳过 Stop hook（id="taskboard_skip_stop", scope="main"）

设计动机：
- taskboard worker 自建对话栈跑在主域（main scope），每任务独立一次完整对话；
- 列智能体完成本列职责后由响应末尾的去留信号（TASK_ADVANCE/HOLD/DROP）
  决定去留，不依赖外部 Stop hook 的续命/拦截；
- 若外部 hook（如团队邮件触发器、归档流水线等）在 Stop 时介入，会干扰
  列内决策并可能与 taskboard 自身的状态机冲突；
- 其他 hook（PreAssistantMessage / PostAssistantMessage / PreToolUse /
  PostToolUse 等）照常触发：保证助理消息级注入（系统提示扩展、消息打标等）
  与工具级安全审查类 hook 仍生效。

注册路径：RuntimeComponentLoader 扫到 plugins/taskboard/hook_policies/*.py
自动调用本模块 register(registry) 注入 HookPolicyRegistry。
"""

from __future__ import annotations

from typing import Any

from app.plugins.contracts.hook_policy import (
    HookDecision,
    HookEvent,
    HookPolicy,
    StopEvent,
)


class TaskboardSkipStopHookPolicy:
    """任务看板 hook 策略 — 仅 Stop 跳过，其余照常触发"""

    id = "taskboard_skip_stop"
    scope = "main"

    def should_trigger(self, event: HookEvent) -> HookDecision:
        if isinstance(event, StopEvent):
            return HookDecision.SKIP
        return HookDecision.TRIGGER


def register(registry: Any) -> None:
    registry.register(TaskboardSkipStopHookPolicy())
