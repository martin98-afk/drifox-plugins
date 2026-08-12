#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ponytail DriFox Hook Handler

复用 Hermes __init__.py 的注入逻辑，适配 DriFox Hook 系统：
- UserPromptSubmit: 检测 /ponytail [lite|full|ultra|off] 命令，切换当前模式
- PreUserMessage: 按当前模式注入 ponytail 规则集（模式过滤后）

模式优先级：内存切换（本次会话）> 环境变量 PONYTAIL_DEFAULT_MODE > config.json defaultMode > full
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

DEFAULT_MODE = "full"
RUNTIME_MODES = {"off", "lite", "full", "ultra"}
CONFIG_MODES = RUNTIME_MODES | {"review"}
SKILL_NAMES = ("ponytail", "ponytail-review")

_current_mode: str | None = None
STATE_FILE = ".ponytail-active"


# ============================================================
# 模式读取
# ============================================================

def _script_dir() -> Path:
    return Path(__file__).resolve().parent


def _plugin_dir() -> Path:
    return _script_dir().parent


def _config_dir() -> Path:
    if os.environ.get("XDG_CONFIG_HOME"):
        return Path(os.environ["XDG_CONFIG_HOME"]) / "ponytail"
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "ponytail"
    return Path.home() / ".config" / "ponytail"


def _state_path() -> Path:
    return _config_dir() / STATE_FILE


def _read_live_mode() -> str | None:
    """读取状态文件中的实时模式（跨 hook 实例共享）。"""
    try:
        return _state_path().read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _write_live_mode(mode: str) -> None:
    """写实时模式到状态文件（跨 hook 实例共享）。"""
    try:
        _state_path().parent.mkdir(parents=True, exist_ok=True)
        _state_path().write_text(mode, encoding="utf-8")
    except OSError:
        pass


def _normalize_config_mode(mode) -> str | None:
    if not isinstance(mode, str):
        return None
    mode = mode.strip().lower()
    return mode if mode in CONFIG_MODES else None


def _normalize_runtime_mode(mode) -> str | None:
    if not isinstance(mode, str):
        return None
    mode = mode.strip().lower()
    return mode if mode in RUNTIME_MODES else None


def _default_mode() -> str:
    env_mode = _normalize_config_mode(os.environ.get("PONYTAIL_DEFAULT_MODE"))
    if env_mode:
        return env_mode
    try:
        data = json.loads((_config_dir() / "config.json").read_text(encoding="utf-8"))
        file_mode = _normalize_config_mode(data.get("defaultMode"))
        if file_mode:
            return file_mode
    except Exception:
        pass
    return DEFAULT_MODE


def _current_or_default() -> str:
    """优先级：状态文件（跨实例）> 内存 > 默认配置。"""
    return _read_live_mode() or _current_mode or _default_mode()


# ============================================================
# 规则构建（复用 __init__.py 逻辑）
# ============================================================

def _strip_frontmatter(text: str) -> str:
    return re.sub(r"^---[\s\S]*?---\s*", "", text or "", count=1)


def _filter_skill_body_for_mode(body: str, mode: str) -> str:
    effective = _normalize_runtime_mode(mode) or DEFAULT_MODE
    lines = []
    for line in _strip_frontmatter(body).splitlines():
        table_label = re.match(r"^\|\s*\*\*(.+?)\*\*\s*\|", line)
        if table_label:
            label_mode = _normalize_runtime_mode(table_label.group(1))
            if label_mode and label_mode != effective:
                continue
        example_label = re.match(r"^-\s*([^:]+):\s*", line)
        if example_label:
            label_mode = _normalize_runtime_mode(example_label.group(1))
            if label_mode and label_mode != effective:
                continue
        lines.append(line)
    return "\n".join(lines)


def _fallback_instructions(mode: str) -> str:
    return (
        f"PONYTAIL MODE ACTIVE — level: {mode}\n\n"
        "You are a lazy senior developer. Lazy means efficient, not careless. "
        "The best code is the code never written.\n\n"
        "Before any code, stop at the first rung that holds: YAGNI, stdlib, "
        "native platform, installed dependency, one line, then minimum code. "
        "No unrequested abstractions, avoidable dependencies, boilerplate, or "
        "speculative scaffolding. Deletion over addition. Boring over clever. "
        "Do not simplify away trust-boundary validation, data-loss handling, "
        "security, accessibility, explicitly requested behavior, or one small "
        "runnable check for non-trivial logic."
    )


def build_injected_context(mode: str | None = None) -> str:
    """返回按模式过滤后的 ponytail 注入上下文（空串=关闭）。"""
    configured = _normalize_config_mode(mode) or _default_mode()
    if configured == "off":
        return ""
    if configured == "review":
        try:
            body = (_plugin_dir() / "skills" / "ponytail-review" / "SKILL.md").read_text(encoding="utf-8")
            return f"PONYTAIL MODE ACTIVE — level: review\n\n{_strip_frontmatter(body)}"
        except OSError:
            return "PONYTAIL MODE ACTIVE — level: review. Review diffs for unnecessary complexity."

    effective = _normalize_runtime_mode(configured) or DEFAULT_MODE
    try:
        body = (_plugin_dir() / "skills" / "ponytail" / "SKILL.md").read_text(encoding="utf-8")
        return f"PONYTAIL MODE ACTIVE — level: {effective}\n\n{_filter_skill_body_for_mode(body, effective)}"
    except OSError:
        return _fallback_instructions(effective)


# ============================================================
# Hook 入口（DriFox 调用：func(event, context) → str）
# ============================================================

def hook_user_prompt_submit(event: str, context: dict) -> str:
    """UserPromptSubmit: 检测 /ponytail 模式命令并切换当前模式（写状态文件）。"""
    global _current_mode
    message = str(context.get("message", "") or context.get("prompt", "") or "").strip()
    if not re.match(r"^[/@$]ponytail(\s|$)", message.lower()):
        return ""
    parts = message.split()
    arg = parts[1].lower() if len(parts) > 1 else ""
    if arg in ("lite", "full", "ultra", "off"):
        _current_mode = arg
        _write_live_mode(arg)
        return f"[ponytail] 模式已切换：{arg}。"
    if arg:
        return "[ponytail] 用法：/ponytail [lite|full|ultra|off]"
    _current_mode = _current_or_default()
    return f"[ponytail] 当前模式：{_current_mode}。"


def hook_pre_user_message(event: str, context: dict) -> str:
    """PreUserMessage: 按当前模式注入 ponytail 规则集。"""
    return build_injected_context(_current_or_default())