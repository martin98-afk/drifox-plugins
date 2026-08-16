# -*- coding: utf-8 -*-
"""
dsh-router Hook — 确定性硬路由（复刻 dsh-router-standard，DriFox 版）

两步注入：
- BuildSystemPrompt  按当前 mode 注入 persona（默认 weak → WEAK_PRO）+ 静态路由说明
- UserPromptSubmit   确定性分类（正则计数）+ 近场引导注入（weak 带 + 复杂度分派 + 闲聊退出）

设计约束（drifox hooks 以 subprocess 每次全新调用，无内存共享）：
- 无状态纯函数优先：分类/引导均由输入文本实时计算
- 会话状态落盘固定绝对路径 <HOME>/.drifox/memory/dsh-router-state.json
  （两事件读写同一文件，键区分会话；原子写 tmp+rename、损坏重建默认、滚动上限 100 键）
- 幂等：可重复触发不产生副作用累积
- 防缓存污染：斜杠命令/闲聊/过短消息返回空串（不注入）
- 单次执行控制在超时（5s）内
"""

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ============================================================
# 正则（素材直译，re.I 编译）
# ============================================================

_REACT_RE = re.compile(
    r"(开发|创建|写一个|生成|从零|做一个|游戏|网页|网站|构建|新项目|搭建|"
    r"实现|做出|上线|落地|脚本|工具|应用|build|create|develop|generate|"
    r"implement|make a|new project)",
    re.I,
)

_SPEC_RE = re.compile(
    r"(修复|修一下|调试|重构|维护|排查|报错|出错|崩溃|优化|审查|review|fix|"
    r"debug|refactor|maintain|repair|broken|break|为什么|异常|故障|迁移|升级|兼容)",
    re.I,
)

_COMPLEX_RE = re.compile(
    r"(重构|架构|全面|详细|设计|系统|优化|分析|survey|overview|architecture|"
    r"refactor|comprehensive|detailed|design|system|optimize|analyze)",
    re.I,
)

_CHAT_RE = re.compile(
    r"^(你好|您好|hello|hi|hey|嗨|哈喽|在吗|谢谢|感谢|thanks|thank you|"
    r"早上好|下午好|晚上好|嗯|好|ok|okay|yes|no|嗯嗯|好的)[!。.!？?~～]*$",
    re.I,
)

# ============================================================
# Persona（素材原文）
# ============================================================

SPEC_PERSONA = "You are a helpful software engineer assistant."

REACT_PERSONA = (
    "You are a hands-on software engineer who delivers working output fast.\n"
    "Work directly: write or edit code, then verify it by reading and running. "
    "Keep the loop tight — produce, verify, fix — and do not build test harnesses, "
    "scaffolding, or ceremony the user did not ask for. "
    "Finish with a usable deliverable and a short summary."
)

MIXED_PERSONA = (
    "You are a helpful software engineer assistant.\n"
    "Work directly: prefer writing or editing code over describing plans. "
    "Verify your changes by reading and running them."
)

WEAK_PRO = (
    "You are a helpful software engineer assistant.\n"
    "Before acting, decide the task type (build or fix) and adopt the matching style: "
    "build → hands-on production; fix → inspect-and-plan."
)

WEAK_FLASH = (
    "You are a helpful assistant.\n"
    "Before acting, decide the task type (build or fix) and adopt the matching style: "
    "build → hands-on production; fix → inspect-and-plan.\n"
    "Before acting, briefly review what you have already done in this session and "
    "continue from where you left off; do not repeat completed steps. "
    "Do not run environment checks (echo, whoami, uname, node --version, date) "
    "or exhaustive grep/glob scans.\n"
    "Think deeply first, then produce."
)

# ============================================================
# 路由引导文本（素材原文）
# ============================================================

GUIDE_WEAK = (
    "\nRouter: classify this task (build or fix) now, then adopt the matching style — "
    "build: direct production; fix: inspect-first. "
    "Think deeply first, then commit and act."
)

GUIDE_DEEP = (
    "\nRouter: classify this task (build or fix) now, then adopt the matching style — "
    "build: direct production; fix: inspect-first. "
    "Think deeply about the architecture, edge cases, and integration points. "
    "Do not spend reasoning on the environment or tooling. "
    "Produce when your information is complete. "
    "End each reasoning block with a decision or an information need."
)

GUIDE_BASE = (
    "\n\nRouter: classify this task (build or fix) now, then adopt the matching style — "
    "build: direct production; fix: inspect-first."
)

GUIDE_BOOST = (
    "\n\nRouter: this is a NEW task, different from the previous ones. "
    "Classify it fresh (build or fix) and adopt the matching style — "
    "build: direct production; fix: inspect-first. "
    "Do not follow the previous task's style."
)

GUIDE_COMMIT = " Think deeply first, then commit and act."

GUIDE_DEEP_TAIL = (
    " Think deeply about the architecture, edge cases, and integration points. "
    "Do not spend reasoning on the environment or tooling. "
    "Produce when your information is complete."
)

GUIDE_CLOSURE = " End each reasoning block with a decision or an information need."

# 注入形态（T-FIX-3）：DriFox hook 输出为独立 user 消息，注入文本必须**自包含**
# （指令声明 + 作用对象）。非 weak 带不再注入 persona 全文，改短分类声明。
_ROUTER_PREFIX = (
    "<ROUTER-INSTRUCTION>这是一条路由指令，作用于本会话的用户任务消息："
    "</ROUTER-INSTRUCTION>"
)

_REACT_INSTRUCTION = (
    "<ROUTER-INSTRUCTION>本会话当前任务已确定性分类为 react（直接执行带）。"
    "请采用 produce-verify-fix 快速交付风格：直接写代码、运行验证、修复、简短总结；"
    "不搭建用户未要求的脚手架或测试框架。此指令作用于本会话的用户任务消息。"
    "</ROUTER-INSTRUCTION>"
)

_SPEC_INSTRUCTION = (
    "<ROUTER-INSTRUCTION>本会话当前任务已确定性分类为 spec（计划优先带）。"
    "请采用 inspect-and-plan 风格：先探索（read/glob/grep）再出计划，确认后再动手改代码。"
    "此指令作用于本会话的用户任务消息。</ROUTER-INSTRUCTION>"
)

_MIXED_INSTRUCTION = (
    "<ROUTER-INSTRUCTION>本会话当前任务已确定性分类为 mixed（平衡带）。"
    "计划与执行混合：简述影响面后直接动手。此指令作用于本会话的用户任务消息。"
    "</ROUTER-INSTRUCTION>"
)

# ============================================================
# 会话状态（memory/dsh-router-state.json）
# 键：稳定会话标识（用 ctx 的 project_root；无则 'default'）。
# ⚠️ 局限：同一项目多个并发会话会共享状态键（drifox hook 无 session_id 保证）。
# ============================================================

_STATE_FILENAME = "dsh-router-state.json"
_ROUND_BOOST = 3  # 第 3 轮起用多轮重分类引导


_MAX_STATE_KEYS = 100  # P2-2: 状态上限，超出清最旧
_VALID_MODES = ("spec", "react", "weak", "mixed")


def get_user_session_id(ctx: dict) -> str:
    """UserPromptSubmit 会话键：优先 ctx.session_id（该事件无 project_root），兜底 'default'。"""
    return ctx.get("session_id", "") or "default"


def get_project_session_id(ctx: dict) -> str:
    """BuildSystemPrompt 会话键：优先 ctx.project_root（该事件无 session_id），兜底 'default'。"""
    return ctx.get("project_root", "") or "default"


# P1-1 修复：状态文件统一固定绝对路径，两事件（UserPromptSubmit 无 project_root /
# BuildSystemPrompt 无 session_id）读写**同一文件**，杜绝 cwd 相对路径分裂与垃圾目录；
# 会话区分靠状态键（见 get_user_session_id / get_project_session_id）。
def _state_path() -> Path:
    return Path.home() / ".drifox" / "memory" / _STATE_FILENAME


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
    # P2-2: 滚动上限——超过 100 键清最旧（按 updated_at，缺失视为最旧）
    if len(state) > _MAX_STATE_KEYS:
        excess = len(state) - _MAX_STATE_KEYS
        ordered = sorted(
            state.items(),
            key=lambda kv: (kv[1] or {}).get("updated_at", "") or "",
        )
        for k, _ in ordered[:excess]:
            state.pop(k, None)
    # 原子写：tmp + rename（避免半截 JSON 毒化下次读取）
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ============================================================
# 判定函数
# ============================================================


def classify_task(text: str) -> str:
    """确定性分类：react/spec 关键词计数比较；相等/无 → weak。"""
    react_count = len(_REACT_RE.findall(text))
    spec_count = len(_SPEC_RE.findall(text))
    if react_count > spec_count:
        return "react"
    if spec_count > react_count:
        return "spec"
    return "weak"


def is_complex(text: str) -> bool:
    """复杂度：文本 >120 字符 或 COMPLEX_RE 命中。"""
    return len(text) > 120 or bool(_COMPLEX_RE.search(text))


def is_chat(text: str) -> bool:
    """闲聊判定（mode-boost 版）。"""
    if not text:
        return True
    if _CHAT_RE.match(text):
        return True
    if len(text) > 24:
        return False
    # 短文本且无任务意图 → 闲聊
    return not (_REACT_RE.search(text) or _SPEC_RE.search(text))


def should_filter(text: str) -> bool:
    """防缓存污染：True=跳过注入返回空串。"""
    text = (text or "").strip()
    if not text:
        return True
    # 斜杠命令不注入（/route /status 由命令侧处理）
    if text.startswith("/"):
        return True
    if is_chat(text):
        return True
    # P2-1: 短文本命中任务关键词（REACT/SPEC）→ 放行注入；纯确认/无意图 → 拦
    if len(text) < 10 and not (_REACT_RE.search(text) or _SPEC_RE.search(text)):
        return True
    return False


def guide_for(round_no: int, text: str) -> str:
    """weak 带引导：round≥3 用多轮重分类；按复杂度追加深思考/收敛尾句。"""
    if round_no >= _ROUND_BOOST:
        guide = GUIDE_BOOST
    else:
        guide = GUIDE_BASE
    if is_complex(text):
        return guide + GUIDE_DEEP_TAIL + GUIDE_CLOSURE
    return guide + GUIDE_COMMIT


def persona_for(mode: str) -> str:
    """按行为带返回 persona 首行/全文。"""
    if mode == "react":
        return REACT_PERSONA
    if mode == "spec":
        return SPEC_PERSONA
    if mode == "mixed":
        return MIXED_PERSONA
    return WEAK_PRO  # weak 默认


# ============================================================
# 事件处理
# ============================================================


def handle_build_system_prompt(ctx: dict) -> str:
    """BuildSystemPrompt：按 state 中 mode 注入 persona。

    ⚠️ persona 降级兜底（P1-1）：主程序事件 ctx 设计限制——UserPromptSubmit ctx 无
    project_root、本事件无 session_id，两键可能不匹配 → 读不到 mode 时回退静态
    WEAK_PRO + 路由说明（静态到头保缓存）。persona 动态化待主程序在 UserPromptSubmit
    ctx 补充 project_root/session 标识后联动（README 已注明）。
    """
    mode = "weak"
    state = _load_state()
    rec = (state or {}).get(get_project_session_id(ctx))
    if not (isinstance(rec, dict) and rec.get("mode") in _VALID_MODES):
        # 会话键回退场景：尝试 'default' 键
        rec = (state or {}).get("default")
        if isinstance(rec, dict) and rec.get("mode") in _VALID_MODES:
            mode = rec["mode"]
    else:
        mode = rec["mode"]
    prefix = (
        "Router: this environment performs deterministic task routing "
        "(build/fix/weak) by keyword classification. "
        "The persona below is active for this session.\n\n"
    )
    return prefix + persona_for(mode)


def handle_user_prompt_submit(ctx: dict) -> str:
    """UserPromptSubmit：确定性分类 + 近场引导注入。

    注入形态（T-FIX-3）：hook 输出为独立 user 消息，注入文本自包含
    （<ROUTER-INSTRUCTION> 指令声明 + 作用对象）——
    - weak 带：前置声明 + 引导（round≥3 BOOST / 复杂度尾句）
    - spec/react/mixed：短分类声明（不再注入 persona 全文）
    """
    message = (ctx or {}).get("message", "")
    if should_filter(message):
        return ""

    mode = classify_task(message)
    # 会话键：UserPromptSubmit 事件用 ctx.session_id（该事件无 project_root）
    session_key = get_user_session_id(ctx)
    # P2-3: round 为 UserPromptSubmit 触发轮次计数；主程序无消息唯一标识，
    # 重复触发（重试/多事件链）可能提前进入 boost 引导——已知局限，不影响分类正确性。
    state = _load_state()
    rec = state.get(session_key) or {}
    round_no = int(rec.get("round", 0)) + 1
    state[session_key] = {
        "first_text": rec.get("first_text", message[:200]),
        "round": round_no,
        "mode": mode,
        "updated_at": _now_iso(),
    }
    _save_state(state)

    if mode == "weak":
        # weak 带：前置声明 + 引导 + 复杂度尾句（自包含）
        return _ROUTER_PREFIX + guide_for(round_no, message)
    # 非 weak：短自包含分类声明（不再注入 persona 全文——独立消息语义割裂）
    if mode == "react":
        return _REACT_INSTRUCTION
    if mode == "mixed":
        return _MIXED_INSTRUCTION
    return _SPEC_INSTRUCTION


# ============================================================
# Python Hook 适配函数（供 hooks.json 派发）
# 签名: (event: str, context: dict) -> str | None
# ============================================================


def hook_build_system_prompt(event: str, context: dict) -> str:
    return handle_build_system_prompt(context)


def hook_user_prompt_submit(event: str, context: dict) -> str:
    return handle_user_prompt_submit(context)


# ============================================================
# CLI 入口（独立调试用）
# 用法:
#   echo '{"message": "修复登录报错"}' | python dsh_router_hook.py --event=UserPromptSubmit
# ============================================================


_HANDLER_MAP = {
    "BuildSystemPrompt": handle_build_system_prompt,
    "UserPromptSubmit": handle_user_prompt_submit,
}


def main():
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="dsh-router Hook Handler")
    parser.add_argument("--event", required=True, choices=list(_HANDLER_MAP.keys()))
    args = parser.parse_args()

    raw = sys.stdin.read() if not sys.stdin.isatty() else "{}"
    try:
        ctx = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        ctx = {}

    result = _HANDLER_MAP[args.event](ctx)
    if isinstance(result, str) and result:
        print(result)


if __name__ == "__main__":
    main()