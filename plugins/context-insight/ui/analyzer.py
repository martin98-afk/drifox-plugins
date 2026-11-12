# -*- coding: utf-8 -*-
"""上下文分析层 —— 把会话消息投影成可解释的组成、趋势、台账与事件。

口径说明（重要，避免 UI 数字各说各话）：
- 输入侧组成：系统提示 + 工具定义 + 前缀消息分类（用户/注入/技能/助手/推理/
  工具调用/工具结果）。工具定义份额优先用宿主实时工具 schema；历史会话用
  「最后一次 API prompt_tokens − 内容估算」的差额桶，标为“工具定义/协议开销”。
- 计费组成：输入组成 + 本次输出（按助手回答/推理/工具调用参数占比分摊）。
- 仅对带 token_usage 的步骤使用 API 精确值；其余步骤按前缀估算，UI 标注 ≈。
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple


from .store import SessionMeta

# ── 分类元数据 ─────────────────────────────────────────────
# (key, 中文名, 色相)。色相固定但明度由 UI 按主题调整。
CATEGORY_META: Tuple[Tuple[str, str, str], ...] = (
    ("system", "系统提示", "#5aa9ff"),
    ("tools", "工具定义", "#8b7cf6"),
    ("user", "用户消息", "#34d399"),
    ("injected", "注入上下文", "#fb923c"),
    ("skill", "技能注入", "#f472b6"),
    ("assistant", "助手回答", "#fbbf24"),
    ("reasoning", "推理", "#22d3ee"),
    ("tool_calls", "工具调用", "#c084fc"),
    ("tool_results", "工具结果", "#a78bfa"),
    ("overhead", "协议开销", "#94a3b8"),
)
CATEGORY_LABELS = {k: label for k, label, _ in CATEGORY_META}
CATEGORY_COLORS = {k: color for k, _, color in CATEGORY_META}
CATEGORY_ORDER = [k for k, _, _ in CATEGORY_META]

_HOOK_INJECTED_EVENTS = {
    "PreUserMessage",
    "Stop",
    "SessionStart",
    "TeamMail",
    "PluginChanged",
    "vision_inject",
    "SubAgentFinished",
}
_INJECTED_PREFIXES = ("<system-reminder>", "📨 **来自", "子智能体全部完成")
_SKILL_MARK = "技能发起了请求"
_COMMAND_MARK = "命令发起了请求"

from .tokens import estimate_text as _local_estimate


def _text_estimate(text: str, model: str = "gpt-4") -> int:
    return _local_estimate(text)



def _content_text(content: Any) -> str:
    """消息 content → 纯文本（text 块拼接；图片按固定 85 token 计入）。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, (int, float)):
        return str(content)
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                btype = block.get("type")
                if btype in (None, "text") and isinstance(block.get("text"), str):
                    parts.append(block["text"])
                elif btype == "image_url":
                    parts.append("\x00IMG\x00" * 85)
                elif btype == "image_ref":
                    parts.append("\x00IMG\x00" * 85)
                elif isinstance(block.get("content"), str):
                    parts.append(block["content"])
        return "".join(parts)
    return str(content)


def _content_tokens(content: Any, model: str) -> int:
    text = _content_text(content)
    if not text:
        return 0
    if "\x00IMG\x00" in text:
        imgs = text.count("\x00IMG\x00") // 85
        text = text.replace("\x00IMG\x00" * 85, "")
        return _text_estimate(text, model) + imgs * 85
    return _text_estimate(text, model)


def _json_loads(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _int_of(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float_of(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _is_real_user_message(msg: Dict[str, Any]) -> bool:
    """真实用户消息：排除 hook 注入、团队邮件、子智能体回执。"""
    if str(msg.get("role") or "") != "user":
        return False
    text = _content_text(msg.get("content")).lstrip()
    if not text:
        return False
    if msg.get("_hook_event") == "TeamMail":
        return True
    if msg.get("_hook_event") in _HOOK_INJECTED_EVENTS:
        return False
    if text.startswith(_INJECTED_PREFIXES):
        return False
    return True


def _classify_user(msg: Dict[str, Any]) -> str:
    text = _content_text(msg.get("content")).lstrip()
    if _SKILL_MARK in text[:160] and text.startswith("用户通过 /"):
        return "skill"
    if _COMMAND_MARK in text[:160] and text.startswith("用户通过 /"):
        return "injected"
    if msg.get("_hook_event") == "TeamMail":
        return "user"
    if msg.get("_hook_event") in _HOOK_INJECTED_EVENTS:
        return "injected"
    if text.startswith(_INJECTED_PREFIXES):
        return "injected"
    return "user"


def _message_categories(
    msg: Dict[str, Any], model: str
) -> Tuple[Dict[str, int], int]:
    """单条消息按类别拆 token，返回 (分类表, 消息总 token)。"""
    role = str(msg.get("role") or "")
    out: Dict[str, int] = {}
    if role == "user":
        key = _classify_user(msg)
        out[key] = _content_tokens(msg.get("content"), model)
    elif role == "assistant":
        answer = _content_tokens(msg.get("content"), model)
        reasoning = _content_tokens(msg.get("reasoning_content"), model)
        args_tokens = 0
        for call in msg.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            fn = call.get("function") or {}
            args = fn.get("arguments")
            args_tokens += _text_estimate(args if isinstance(args, str) else json.dumps(args, ensure_ascii=False), model)
        if answer:
            out["assistant"] = answer
        if reasoning:
            out["reasoning"] = reasoning
        if args_tokens:
            out["tool_calls"] = args_tokens
    elif role == "tool":
        out["tool_results"] = _content_tokens(msg.get("content"), model)
    elif role == "system":
        out["system"] = _content_tokens(msg.get("content"), model)
    total = sum(out.values()) + 4 + _text_estimate(role, model)
    return out, total


@dataclass
class ToolCallRecord:
    call_id: str
    name: str
    args: Dict[str, Any]
    ts: str
    args_tokens: int = 0
    result_tokens: int = 0
    success: Optional[bool] = None
    duration_ms: float = 0.0
    step_index: int = 0


@dataclass
class Step:
    index: int  # assistant 消息下标
    turn_index: int
    ts: str
    model: str
    input_tokens: int
    output_tokens: int
    has_usage: bool
    estimated: bool
    elapsed_ms: float
    ttft_ms: float
    context_composition: Dict[str, int] = field(default_factory=dict)
    billed_composition: Dict[str, int] = field(default_factory=dict)
    delta_tokens: int = 0
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    preview: str = ""
    message_count: int = 0


@dataclass
class Turn:
    index: int
    start_ts: str
    user_text: str
    steps: List[Step] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_ms: float = 0.0
    tool_ms: float = 0.0
    tool_calls: int = 0


@dataclass
class Event:
    ts: str
    kind: str
    title: str
    detail: str = ""
    delta_tokens: int = 0
    step_index: int = -1


@dataclass
class FileActivity:
    path: str
    actions: set = field(default_factory=set)
    count: int = 0
    last_ts: str = ""
    tokens: int = 0


@dataclass
class SessionAnalysis:
    meta: SessionMeta
    messages: List[Dict[str, Any]]
    steps: List[Step]
    turns: List[Turn]
    events: List[Event]
    tool_counts: Counter
    skill_counts: Counter
    command_counts: Counter
    command_status: Dict[str, Tuple[int, int]]
    file_ops: Dict[str, FileActivity]
    usage: Dict[str, int]
    timing: Dict[str, float]
    daily: Dict[str, List[int]]
    context_latest: Dict[str, int]
    context_total: Dict[str, int]
    tools_tokens: int
    tools_source: str
    budget_tokens: int
    used_tokens: int
    percent: int
    cost_usd: float
    cost_known: bool
    models: List[str]
    cache_hit_rate: Optional[float] = None
    msg_categories: List[Dict[str, int]] = field(default_factory=list)
    msg_tokens: List[int] = field(default_factory=list)
    msg_models: List[str] = field(default_factory=list)
    system_tokens: int = 0


# ── 定价（延迟导入，避免循环） ─────────────────────────────
def _price_for(model: str) -> Tuple[float, float, bool]:
    try:
        from .pricing import price_for

        return price_for(model)
    except Exception:
        return 0.0, 0.0, False


def _parse_ts(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def _first_arg(args: Dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _tool_target(name: str, args: Dict[str, Any]) -> Tuple[str, str]:
    """工具调用 → (kind, target)。kind: command/file_read/file_write/file_search/tool。"""
    lname = (name or "").lower()
    if lname in ("bash", "shell", "run_command", "execute_command"):
        cmd = _first_arg(args, ("command", "cmd", "script", "code"))
        return "command", cmd
    if lname in ("read", "read_file", "view", "cat"):
        return "file_read", _first_arg(args, ("file_path", "path", "file", "target_file"))
    if lname in ("write", "write_file", "create_file", "edit", "multi_edit", "multiedit", "apply_patch"):
        return "file_write", _first_arg(args, ("file_path", "path", "file", "target_file"))
    if lname in ("grep", "glob", "list", "ls", "search", "codegraph_explore", "codegraph_search"):
        return "file_search", _first_arg(args, ("path", "file_path", "glob", "pattern"))
    if lname == "skill":
        return "skill", _first_arg(args, ("name", "skill", "skill_name"))
    return "tool", ""


_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")
_WRAPPERS = {"sudo", "env", "command", "time", "nohup", "exec"}


def _command_program(command: str) -> str:
    """从 shell 命令里取主程序名（去掉 env 赋值、sudo、管道后的部分）。"""
    text = (command or "").strip()
    if not text:
        return ""
    first_line = text.splitlines()[0]
    # 取第一个管道/分号前的片段
    segment = re.split(r"[|;]|&&|\|\|", first_line, maxsplit=1)[0].strip()
    try:
        import shlex

        tokens = shlex.split(segment, posix=True)
    except Exception:
        tokens = segment.split()
    for token in tokens:
        base = token.rsplit("/", 1)[-1]
        if not base or _ENV_ASSIGN.match(base) or base in _WRAPPERS:
            continue
        if base in ("-c", "--"):
            continue
        return base
    return tokens[0].rsplit("/", 1)[-1] if tokens else ""


def _merge_comp(target: Dict[str, int], part: Dict[str, int]) -> None:
    for key, value in part.items():
        if value:
            target[key] = target.get(key, 0) + int(value)


def _scale_comp(comp: Dict[str, int], target_total: int, fixed: Optional[Dict[str, int]] = None) -> Dict[str, int]:
    """把分类表等比缩放到 target_total；fixed 为不参与缩放的固定份额。"""
    fixed = fixed or {}
    fixed_total = sum(fixed.values())
    content_total = sum(comp.values())
    out: Dict[str, int] = {}
    if target_total <= 0:
        return {k: int(v) for k, v in fixed.items() if v > 0}
    if fixed_total > target_total and fixed_total > 0:
        # 固定份额已超过目标总量（罕见：输入比工具定义还小）→ 按比例压缩固定份额
        for key, value in fixed.items():
            if value > 0:
                out[key] = max(1, int(value * target_total / fixed_total))
        return out
    out = {k: int(v) for k, v in fixed.items() if v > 0}
    remain = max(0, target_total - fixed_total)
    if content_total <= 0:
        if remain:
            out["overhead"] = out.get("overhead", 0) + remain
        return out
    scale = remain / content_total
    for key, value in comp.items():
        if value > 0:
            out[key] = out.get(key, 0) + max(1, int(value * scale))
    # 修正取整误差到最后一项
    diff = target_total - sum(out.values())
    if diff and out:
        last = max(out, key=lambda k: out[k])
        out[last] = max(0, out[last] + diff)
    return out


def analyze_session(
    meta: SessionMeta,
    messages: List[Dict[str, Any]],
    *,
    tools_tokens_hint: int = 0,
    tools_source_hint: str = "live",
    pruned_tokens: int = 0,
    cache_hit_rate: Optional[float] = None,
    live_budget_tokens: int = 0,
    live_used_tokens: int = 0,
) -> SessionAnalysis:
    """把单个会话投影成全量分析结果（纯函数，可在后台线程调用）。"""
    model_default = meta.token_calibration_model or "gpt-4"
    system_raw = _text_estimate(meta.system_prompt or "", model_default)

    # ── 逐条消息分类 ──
    msg_cats: List[Dict[str, int]] = []
    msg_totals: List[int] = []
    msg_models: List[str] = []
    msg_text: List[str] = []
    for msg in messages:
        model = str(msg.get("model_name") or model_default)
        cats, total = _message_categories(msg, model)
        msg_cats.append(cats)
        msg_totals.append(total)
        msg_models.append(model)
        msg_text.append(_content_text(msg.get("content")))

    # ── 前缀累计（system 固定在 0 号位置，不计入消息前缀变量） ──
    prefix_cats: List[Dict[str, int]] = []
    running: Dict[str, int] = {}
    for cats in msg_cats:
        prefix_cats.append(dict(running))
        _merge_comp(running, cats)

    # ── 步骤：每条 assistant 消息是一次模型调用（可能带 usage） ──
    steps: List[Step] = []
    turns: List[Turn] = []
    turn_index = 0
    current_turn: Optional[Turn] = None
    tool_by_call: Dict[str, ToolCallRecord] = {}
    tool_result_by_call: Dict[str, Dict[str, Any]] = {}

    for idx, msg in enumerate(messages):
        role = str(msg.get("role") or "")
        if role == "user" and _is_real_user_message(msg):
            turn_index += 1
            current_turn = Turn(
                index=turn_index,
                start_ts=str(msg.get("timestamp") or ""),
                user_text=_content_text(msg.get("content"))[:160],
            )
            turns.append(current_turn)
        elif role == "tool":
            call_id = str(msg.get("tool_call_id") or "")
            if call_id:
                tool_result_by_call[call_id] = msg
            continue
        if role != "assistant":
            continue
        if current_turn is None:
            turn_index += 1
            current_turn = Turn(index=turn_index, start_ts=str(msg.get("timestamp") or ""), user_text="")
            turns.append(current_turn)

        usage = msg.get("token_usage") if isinstance(msg.get("token_usage"), dict) else {}
        has_usage = bool(usage)
        model = str(msg.get("model_name") or model_default)
        input_tokens = _int_of(usage.get("input")) if has_usage else 0
        output_tokens = _int_of(usage.get("output")) if has_usage else 0
        elapsed_ms = _float_of(msg.get("elapsed_ms") or (msg.get("elapsed") or 0) * 1000)
        ttft_ms = _float_of(msg.get("ttft_ms"))

        step = Step(
            index=idx,
            turn_index=turn_index,
            ts=str(msg.get("timestamp") or ""),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            has_usage=has_usage,
            estimated=not has_usage,
            elapsed_ms=elapsed_ms,
            ttft_ms=ttft_ms,
            preview=_content_text(msg.get("content"))[:120],
            message_count=idx,
        )
        # 工具调用
        for call in msg.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            fn = call.get("function") or {}
            name = str(fn.get("name") or "")
            args = _json_loads(fn.get("arguments")) or {}
            if not isinstance(args, dict):
                args = {"value": args}
            rec = ToolCallRecord(
                call_id=str(call.get("id") or ""),
                name=name,
                args=args,
                ts=step.ts,
                args_tokens=_text_estimate(
                    fn.get("arguments") if isinstance(fn.get("arguments"), str) else json.dumps(args, ensure_ascii=False),
                    model,
                ),
                step_index=idx,
            )
            step.tool_calls.append(rec)
            if rec.call_id:
                tool_by_call[rec.call_id] = rec
        steps.append(step)
        current_turn.steps.append(step)

    # ── 工具结果回填（token / success / 耗时） ──
    for call_id, rec in tool_by_call.items():
        result = tool_result_by_call.get(call_id)
        if not result:
            continue
        rec.result_tokens = _content_tokens(result.get("content"), model_default)
        success = result.get("success")
        if isinstance(success, bool):
            rec.success = success
        phases = result.get("trace_phases")
        if isinstance(phases, dict):
            # trace_phases.total 单位是毫秒（实测 7.8 / 3544.4，与 elapsed_ms 同量级）
            rec.duration_ms = _float_of(phases.get("total"))

    # ── 工具定义份额 ──
    tools_tokens = max(0, int(tools_tokens_hint or 0))
    tools_source = tools_source_hint if tools_tokens else "none"
    usage_inputs = [s.input_tokens for s in steps if s.has_usage and s.input_tokens > 0]
    tiny_input = min(usage_inputs) if usage_inputs else 0
    # 工具 schema 是请求前缀里的大块固定开销，但历史会话的工具集与当前 schema
    # 可能不同；用最小 API 输入做个上限，避免出现“工具定义 > 整段上下文”。
    if tools_tokens > 0 and tiny_input > 0:
        tools_tokens = min(tools_tokens, max(1, int(tiny_input * 0.5)))
    if tools_tokens <= 0:
        last_usage_step = next((s for s in reversed(steps) if s.has_usage and s.input_tokens > 0), None)
        if last_usage_step is not None:
            raw_prefix = system_raw + sum(msg_totals[: last_usage_step.index])
            residual = last_usage_step.input_tokens - raw_prefix
            if residual > 0:
                tools_tokens = min(residual, 400_000)
                tools_source = "residual"

    # ── 估算步骤的校准比 ──
    # 存储里的工具结果可能远大于实际发送量（system-context 会先落盘/截断再投影），
    # 因此无 usage 的步骤不能直接用原始消息估算；用带 usage 步骤的
    # input / (原始前缀 + 工具定义) 中位数校准，避免趋势出现假回落。
    ratios: List[float] = []
    for step in steps:
        if not (step.has_usage and step.input_tokens > 0):
            continue
        raw_prefix = system_raw + sum(msg_totals[: step.index])
        denom = raw_prefix + tools_tokens
        if denom > 0:
            ratios.append(step.input_tokens / denom)
    ratios.sort()
    median_ratio = ratios[len(ratios) // 2] if ratios else 1.0
    median_ratio = max(0.05, min(3.0, median_ratio))

    # ── 逐步骤组成 + 输出分摊 ──
    prev_input = 0
    prev_turn = 0
    for step in steps:
        prefix_raw = system_raw + sum(msg_totals[: step.index])
        content_comp: Dict[str, int] = {}
        if system_raw:
            content_comp["system"] = system_raw
        _merge_comp(content_comp, prefix_cats[step.index])
        fixed = {"tools": tools_tokens} if tools_tokens else {}
        target_input = step.input_tokens
        if target_input <= 0:
            target_input = int((prefix_raw + tools_tokens) * median_ratio)
            target_input = max(1, target_input)
            step.estimated = True
        # 估算步骤在同一轮内不应无故回落（真实回落来自压缩/剪枝，会落在
        # 带 usage 的 API 步骤上）。避免趋势图出现锯齿状假事件。
        if not step.has_usage and prev_input and step.turn_index == prev_turn:
            target_input = max(target_input, prev_input)
        step.context_composition = _scale_comp(content_comp, target_input, fixed=fixed)
        step.input_tokens = target_input
        step.delta_tokens = target_input - prev_input if prev_input else 0
        prev_input = target_input
        prev_turn = step.turn_index

        # 输出分摊：本次 assistant 消息的各类原始 token
        output_raw = dict(msg_cats[step.index]) if step.index < len(msg_cats) else {}
        if not step.has_usage or step.output_tokens <= 0:
            output_total = sum(output_raw.values())
            step.billed_composition = dict(step.context_composition)
            _merge_comp(step.billed_composition, output_raw)
        else:
            output_total = step.output_tokens
            attributed = _scale_comp(output_raw, output_total) if output_raw else {"assistant": output_total}
            step.billed_composition = dict(step.context_composition)
            _merge_comp(step.billed_composition, attributed)

    # ── 轮次汇总 ──
    for turn in turns:
        if not turn.steps:
            continue
        turn.input_tokens = max((s.input_tokens for s in turn.steps), default=0)
        turn.output_tokens = sum(s.output_tokens for s in turn.steps)
        turn.elapsed_ms = max((s.elapsed_ms for s in turn.steps), default=0.0)
        turn.tool_calls = sum(len(s.tool_calls) for s in turn.steps)
        turn.tool_ms = sum(
            rec.duration_ms
            for s in turn.steps
            for rec in s.tool_calls
            if rec.duration_ms > 0
        )

    # ── 台账 ──
    tool_counts: Counter = Counter()
    skill_counts: Counter = Counter()
    command_counts: Counter = Counter()
    command_status: Dict[str, Tuple[int, int]] = {}
    file_ops: Dict[str, FileActivity] = {}
    models: List[str] = []

    for step in steps:
        if step.model and step.model not in models:
            models.append(step.model)
        for rec in step.tool_calls:
            tool_counts[rec.name] += 1
            kind, target = _tool_target(rec.name, rec.args)
            if kind == "command":
                program = _command_program(target) or "(未知)"
                command_counts[program] += 1
                ok = 1 if rec.success is not False else 0
                fail = 1 if rec.success is False else 0
                prev = command_status.get(program, (0, 0))
                command_status[program] = (prev[0] + ok, prev[1] + fail)
            elif kind == "skill":
                if target:
                    skill_counts[target] += 1
            elif kind in ("file_read", "file_write", "file_search"):
                path = target or "(未指定)"
                activity = file_ops.get(path)
                if activity is None:
                    activity = FileActivity(path=path, last_ts=rec.ts)
                    file_ops[path] = activity
                action = {"file_read": "read", "file_write": "write", "file_search": "search"}[kind]
                activity.actions.add(action)
                activity.count += 1
                activity.last_ts = rec.ts or activity.last_ts
                activity.tokens += rec.args_tokens + rec.result_tokens

    # ── 事件 ──
    events: List[Event] = []
    compaction = meta.compaction_state or {}
    if compaction.get("active"):
        summarized = _int_of(compaction.get("summarized_count"))
        kept = _int_of(compaction.get("kept_count"))
        note = str(compaction.get("note") or compaction.get("kind") or "")
        events.append(
            Event(
                ts=meta.updated_at,
                kind="compaction",
                title="上下文压缩",
                detail=f"压缩 {summarized} 条 / 保留 {kept} 条" + (f" · {note}" if note else ""),
            )
        )
    for i, step in enumerate(steps):
        if i == 0 or step.delta_tokens >= 0:
            continue
        drop = -step.delta_tokens
        if drop < 2000:
            continue
        prev = steps[i - 1].input_tokens if i else 0
        ratio = drop / prev if prev else 0
        if ratio >= 0.25:
            events.append(
                Event(
                    ts=step.ts,
                    kind="drop",
                    title="上下文回落",
                    detail=f"{prev:,} → {step.input_tokens:,}（-{drop:,}）",
                    delta_tokens=-drop,
                    step_index=step.index,
                )
            )
    if pruned_tokens > 0:
        events.append(
            Event(
                ts=meta.updated_at,
                kind="prune",
                title="工具结果剪枝",
                detail=f"本轮投影剪掉 {pruned_tokens:,} tokens",
                delta_tokens=-pruned_tokens,
            )
        )
    # 大跃升（>20k）标一下，便于解释上下文为何突然变大
    for i, step in enumerate(steps):
        if i == 0 or step.delta_tokens <= 20000:
            continue
        events.append(
            Event(
                ts=step.ts,
                kind="jump",
                title="上下文跃升",
                detail=f"+{step.delta_tokens:,} tokens",
                delta_tokens=step.delta_tokens,
                step_index=step.index,
            )
        )
    events.sort(key=lambda e: e.ts)

    # ── 汇总 ──
    usage_input = sum(s.input_tokens for s in steps if s.has_usage)
    usage_output = sum(s.output_tokens for s in steps if s.has_usage)
    usage_requests = sum(1 for s in steps if s.has_usage)
    if usage_requests == 0:
        usage_input = meta.last_api_prompt_tokens or meta.context_usage or 0
        usage_output = 0
    context_total: Dict[str, int] = {}
    for step in steps:
        _merge_comp(context_total, step.billed_composition)
    latest_step = next((s for s in reversed(steps) if s.input_tokens > 0), None)
    context_latest = dict(latest_step.context_composition) if latest_step else {}

    timing = {
        "total_ms": sum(t.elapsed_ms for t in turns),
        "tool_ms": sum(t.tool_ms for t in turns),
        "ttft_ms": sum(s.ttft_ms for s in steps if s.ttft_ms > 0),
        "steps": float(len(steps)),
    }
    timing["model_ms"] = max(0.0, timing["total_ms"] - timing["tool_ms"])
    timing["overhead_ms"] = 0.0

    daily: Dict[str, List[int]] = {}
    for step in steps:
        if not step.has_usage:
            continue
        day = step.ts[:10]
        if len(day) != 10:
            continue
        slot = daily.setdefault(day, [0, 0, 0])
        slot[0] += step.input_tokens
        slot[1] += step.output_tokens
        slot[2] += 1

    cost = 0.0
    cost_known = True
    for step in steps:
        if not step.has_usage:
            continue
        in_price, out_price, known = _price_for(step.model)
        if not known:
            cost_known = False
        cost += step.input_tokens / 1_000_000 * in_price
        cost += step.output_tokens / 1_000_000 * out_price

    budget = int(live_budget_tokens or 0)
    used = int(live_used_tokens or 0)
    if used <= 0:
        used = latest_step.input_tokens if latest_step else (meta.last_api_prompt_tokens or meta.context_usage or 0)
    if budget <= 0:
        limit_model = (latest_step.model if latest_step else "") or meta.token_calibration_model
        try:
            from .pricing import context_limit_for

            budget = int(context_limit_for(limit_model) or 0)
        except Exception:
            budget = 0
    # 未知模型不伪造上限：budget=0、percent=0，UI 显示“未知上限”而不是 100%。
    percent = max(0, min(100, int(used / budget * 100))) if budget > 0 else 0

    return SessionAnalysis(
        meta=meta,
        messages=messages,
        steps=steps,
        turns=turns,
        events=events,
        tool_counts=tool_counts,
        skill_counts=skill_counts,
        command_counts=command_counts,
        command_status=command_status,
        file_ops=file_ops,
        usage={
            "input": usage_input,
            "output": usage_output,
            "total": usage_input + usage_output,
            "requests": usage_requests,
            "turns": len([t for t in turns if t.user_text]),
            "steps": len(steps),
        },
        timing=timing,
        daily=daily,
        context_latest=context_latest,
        context_total=context_total,
        tools_tokens=tools_tokens,
        tools_source=tools_source,
        budget_tokens=budget,
        used_tokens=used,
        percent=percent,
        cost_usd=cost,
        cost_known=cost_known,
        models=models,
        cache_hit_rate=cache_hit_rate,
        msg_categories=msg_cats,
        msg_tokens=msg_totals,
        msg_models=msg_models,
        system_tokens=system_raw,
    )


def summarize_for_index(analysis: SessionAnalysis) -> Dict[str, Any]:
    """跨会话索引摘要：只保留洞察页需要的聚合值（可 JSON 持久化）。"""
    meta = analysis.meta
    return {
        "version": 2,
        "session_id": meta.session_id,
        "title": meta.title,
        "project": meta.project,
        "worktree_path": meta.worktree_path,
        "created_at": meta.created_at,
        "updated_at": meta.updated_at,
        "message_count": meta.message_count,
        "agent_name": meta.agent_name,
        "team_run_id": meta.team_run_id,
        "team_name": meta.team_name,
        "team_members": meta.team_members,
        "fingerprint": meta.fingerprint,
        "usage": dict(analysis.usage),
        "cost_usd": round(analysis.cost_usd, 6),
        "cost_known": analysis.cost_known,
        "context_latest": dict(analysis.context_latest),
        "context_total": dict(analysis.context_total),
        "tools_tokens": analysis.tools_tokens,
        "used_tokens": analysis.used_tokens,
        "budget_tokens": analysis.budget_tokens,
        "percent": analysis.percent,
        "tool_counts": dict(analysis.tool_counts),
        "skill_counts": dict(analysis.skill_counts),
        "command_counts": dict(analysis.command_counts),
        "file_count": len(analysis.file_ops),
        "daily": {k: list(v) for k, v in analysis.daily.items()},
        "models": list(analysis.models),
    }
