# -*- coding: utf-8 -*-
"""
dsh-presets Hook Handler — DeepSeek Harness preset 路由

两步注入：
- BuildSystemPrompt  按当前 preset 注入 preset 声明（默认 standard），尾部追加模式名 + 工具集提示
- UserPromptSubmit   解析用户消息中的 /dsh-mode <name> 切换指令（命令型），更新会话级状态；
                     落到 <HOME>/.drifox/memory/dsh-presets-state.json，键 = session_id 或 'default'

设计约束（drifox hooks 以 subprocess 每次全新调用，无内存共享）：
- 状态必须落盘：HOME 绝对路径 ~/.drifox/memory/dsh-presets-state.json
- 原子写：tmp + rename
- 幂等：可重复触发不产生副作用累积
- 单次执行控制在超时（5s）内
- 防缓存污染：消息过短 / 仅闲聊 / 无 /dsh-mode 指令时返回空串（UserPromptSubmit）
"""

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ============================================================
# 常量
# ============================================================

PLUGIN_NAME = "dsh-presets"
VALID_PRESETS = ("standard", "code", "cordis")
DEFAULT_PRESET = "standard"
STATE_FILENAME = "dsh-presets-state.json"

# BuildSystemPrompt：每个 preset 追加的声明（注入到 system prompt 尾部）
PRESET_DECLARATIONS = {
    "standard": (
        "本会话运行在 DeepSeek Harness `standard` preset（dsh-standard）——"
        "通用编码 agent：工具面 read/write/edit/glob/grep/bash 全开；"
        "使用 goal 工具管理长任务，用 subagent 并行处理独立任务；"
        "默认 preset 适用于绝大多数编码场景。"
    ),
    "code": (
        "本会话运行在 DeepSeek Harness `code` preset（dsh-code）——"
        "纯写代码专注模式：步骤预算更高（35 步）、温度更低（0.3）、"
        "产出更收敛；禁止中途切换到计划模式，禁止顺手重构未提及的代码。"
    ),
    "cordis": (
        "本会话运行在 DeepSeek Harness `cordis` preset（dsh-cordis）——"
        "Cordis 插件框架开发专用：HOST composition 与 AGENT PRESET 平面划分；"
        "cordis_* 工作流 inspect → define → run/update/stop/undefine；"
        "pluginId / packageId / pluginRunId / currentPackageId / nextPackageId 身份系统；"
        "高频错误规避（ctx.get/inject、TS/JSX、序列化、副作用清理）；"
        "DriFox 当前无 cordis_* 工具时，明确告知用户需在 DSH GUI 中执行。"
    ),
}

# /dsh-mode 切换指令检测
_DSH_MODE_RE = re.compile(
    r"^/?\s*dsh[-_]mode\s+(?P<preset>standard|code|cordis)\s*\.?$",
    re.IGNORECASE,
)


# ============================================================
# 状态文件路径
# ============================================================


def _state_path() -> Path:
    """统一绝对路径：HOME/.drifox/memory/dsh-presets-state.json"""
    return Path.home() / ".drifox" / "memory" / STATE_FILENAME


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_state() -> dict:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def get_session_id(ctx: dict) -> str:
    """UserPromptSubmit 会话键：优先 ctx.session_id，兜底 'default'。"""
    return ctx.get("session_id", "") or "default"


def get_preset(ctx: dict) -> str:
    """BuildSystemPrompt 优先从 ctx.dsh_preset 读取（前端命令可注入），兜底查状态文件。"""
    preset = ctx.get("dsh_preset", "")
    if preset in VALID_PRESETS:
        return preset
    # 回退到状态文件最近一次记录
    sid = ctx.get("session_id", "") or ctx.get("project_root", "") or "default"
    state = _load_state()
    rec = state.get(sid, {})
    return rec.get("preset", DEFAULT_PRESET) if rec.get("preset") in VALID_PRESETS else DEFAULT_PRESET


# ============================================================
# 事件处理器
# ============================================================


def handle_build_system_prompt(ctx: dict) -> str:
    """BuildSystemPrompt：返回 preset 声明，注入到 system prompt 尾部。"""
    preset = get_preset(ctx)
    return PRESET_DECLARATIONS.get(preset, PRESET_DECLARATIONS[DEFAULT_PRESET])


def handle_user_prompt_submit(ctx: dict) -> str:
    """UserPromptSubmit：检测 /dsh-mode <preset> 切换指令；命中则更新状态文件 + 返回切换确认。"""
    message = ctx.get("message", "")
    if not isinstance(message, str) or not message.strip():
        return ""

    # 匹配 /dsh-mode <preset>
    m = _DSH_MODE_RE.match(message.strip())
    if not m:
        return ""

    new_preset = m.group("preset").lower()
    sid = get_session_id(ctx)
    state = _load_state()
    old_preset = (
        state.get(sid, {}).get("preset", DEFAULT_PRESET)
        if isinstance(state.get(sid, {}), dict)
        else DEFAULT_PRESET
    )
    state[sid] = {
        "preset": new_preset,
        "updated_at": _now_iso(),
        "prev_preset": old_preset,
    }
    _save_state(state)

    return (
        f"<DSH-PRESETS-INSTRUCTION>当前会话已从 `{old_preset}` 切换到 `{new_preset}` preset。"
        f"下次 BuildSystemPrompt 注入将使用 {new_preset} 声明。"
        f"此指令作用于本次会话。</DSH-PRESETS-INSTRUCTION>"
    )


# ============================================================
# Hook 入口（subprocess 调用约定）
# ============================================================


_HANDLER_MAP = {
    "BuildSystemPrompt": handle_build_system_prompt,
    "UserPromptSubmit": handle_user_prompt_submit,
}


def main():
    parser = argparse.ArgumentParser(description="dsh-presets Hook Handler")
    parser.add_argument("--event", required=True, choices=list(_HANDLER_MAP.keys()))
    args = parser.parse_args()

    raw = sys.stdin.read() if not sys.stdin.isatty() else "{}"
    # 兼容 PowerShell 管道注入 UTF-8 BOM（Get-Content -Raw | python 会带 \ufeff）
    if raw.startswith("\ufeff"):
        raw = raw.lstrip("\ufeff")
    try:
        ctx = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        ctx = {}

    result = _HANDLER_MAP[args.event](ctx)
    if isinstance(result, str) and result:
        print(result)


if __name__ == "__main__":
    main()
