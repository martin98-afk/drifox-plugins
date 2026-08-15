# -*- coding: utf-8 -*-
"""
编辑快照与应用 — 陈旧检测 / bottom-up 应用 / no-op 循环检测 / 新锚点块

设计（对齐任务决策）：
- 校验基准 = 当前文件实时计算的行哈希（即 pre-edit 快照）
- 所有编辑**先全部校验通过**，再**自底向上应用**（按 pos 行号降序）
- 陈旧锚点（hash 不匹配）→ E_STALE_ANCHOR，绝不静默移位
- lines 含显示前缀/diff 标记 → E_INVALID_PATCH 拒绝
- 连续 3 次相同 no-op 编辑 → E_NOOP_LOOP
- 状态池放 window_state（无则模块级降级），键 `hashline_noop`

注意：本文件是核心逻辑模块，`register()` 为占位实现（满足仓库校验器
「tools/*.py 必须定义顶层 register(registry)」的要求），不注册任何工具。
"""
import json
from typing import Optional

from hashline_engine import (
    DEFAULT_WIDTH,
    format_anchors_block,
    hash_all,
    parse_anchor,
    validate_line_content,
)

# 错误码（LLM 可识别前缀）
E_STALE_ANCHOR = "E_STALE_ANCHOR"
E_INVALID_PATCH = "E_INVALID_PATCH"
E_NOOP_LOOP = "E_NOOP_LOOP"

# no-op 循环阈值（连续 3 次相同 no-op 编辑报错）
NOOP_LIMIT = 3

# 模块级 no-op 状态（无 window_state 时降级）
_noop_state: dict = {}

_OPERATIONS = ("replace", "append", "prepend", "replace_text")


def _noop_state(tool_ctx) -> dict:
    """no-op 状态字典：window_state 优先，模块级降级（共享引用原地修改）"""
    try:
        ws = (tool_ctx or {}).get("services", {}).get("window_state")
        if ws is not None:
            d = ws["get"]("hashline_noop")
            if d is None:
                d = {}
                ws["set"]("hashline_noop", d)
            return d
    except Exception:
        pass
    return _noop_state


def _edit_sig(edits) -> str:
    """编辑请求指纹（no-op 循环检测用）：规范化 JSON 序列化"""
    return json.dumps(edits, ensure_ascii=False, sort_keys=True, default=str)


def _parse_replace_pair(content):
    """replace_text 的 content 解析：{"old": ..., "new": ...}

    支持 dict 或 JSON 字符串。非法返回错误消息（str）。
    """
    if isinstance(content, dict):
        pair = content
    elif isinstance(content, str):
        try:
            pair = json.loads(content)
        except json.JSONDecodeError:
            return f"replace_text 的 content 必须是 JSON 字符串 {{\"old\":..,\"new\":..}}，当前为 {content[:40]!r}"
    else:
        return f"replace_text 的 content 必须是对象或 JSON 字符串，当前为 {content!r}"
    if not isinstance(pair, dict):
        return "replace_text 的 content 必须是 {\"old\":..,\"new\":..} 对象"
    old = pair.get("old")
    new = pair.get("new")
    if not isinstance(old, str) or not isinstance(new, str):
        return "replace_text 的 content 需要字符串字段 old 和 new"
    if not old:
        return "replace_text 的 old 不允许为空字符串"
    if "\n" in old or "\n" in new:
        return "replace_text 的 old/new 不允许包含换行（单行内替换）"
    return (old, new)


def validate_edit(edit: dict, lines: list, hashes: list, width: int = DEFAULT_WIDTH) -> Optional[str]:
    """校验单条编辑（基于 pre-edit lines+hashes）。返回错误消息或 None。

    校验通过 ≠ 内容必变（可能 no-op），应用阶段统一判断。
    """
    op = edit.get("op", "")
    if op not in _OPERATIONS:
        return f"{E_INVALID_PATCH}: 未知 op {op!r}（可选 {'/'.join(_OPERATIONS)}）"
    try:
        lineno, anchor_hash = parse_anchor(edit.get("pos", ""))
    except ValueError as e:
        return f"{E_INVALID_PATCH}: {e}"
    if lineno < 1 or lineno > len(lines):
        return (
            f"{E_STALE_ANCHOR}: 锚点 {lineno}#{anchor_hash} 行号超出文件范围"
            f"（文件共 {len(lines)} 行），文件可能已变化，请重新 read 拿最新锚点"
        )
    if hashes[lineno - 1] != anchor_hash:
        return (
            f"{E_STALE_ANCHOR}: 锚点 {lineno}#{anchor_hash} 已失效"
            f"（当前 {lineno}#{hashes[lineno - 1]}），文件可能已被修改，"
            f"请重新 read 拿最新锚点后再编辑"
        )
    # textHint 第二因子（可选）：目标行内容前缀
    hint = edit.get("textHint")
    if hint is not None and not str(hint):
        return f"{E_INVALID_PATCH}: textHint 不允许为空"
    if hint is not None and not lines[lineno - 1].startswith(str(hint)):
        return (
            f"{E_STALE_ANCHOR}: 锚点 {lineno}#{anchor_hash} 内容与 textHint 不匹配"
            f"（当前行开头 {lines[lineno - 1][:30]!r}），请重新 read 确认"
        )

    if op == "replace":
        end = edit.get("end")
        if end is not None:
            try:
                end_lineno, end_hash = parse_anchor(end)
            except ValueError as e:
                return f"{E_INVALID_PATCH}: {e}"
            if end_lineno < lineno or end_lineno > len(lines):
                return f"{E_INVALID_PATCH}: 区间 end 行号必须在 pos 之后且不超出文件范围"
            if hashes[end_lineno - 1] != end_hash:
                return (
                    f"{E_STALE_ANCHOR}: 区间结束锚点 {end_lineno}#{end_hash} 已失效，"
                    f"请重新 read 拿最新锚点"
                )
        new_lines = edit.get("lines")
        if not isinstance(new_lines, list):
            return f"{E_INVALID_PATCH}: replace 需要 lines 列表（新行内容；空列表=删除该行/区间）"
        for text in new_lines:
            if not isinstance(text, str):
                return f"{E_INVALID_PATCH}: lines 元素必须是字符串，当前为 {text!r}"
            err = validate_line_content(text)
            if err:
                return f"{E_INVALID_PATCH}: {err}"
    else:
        content = edit.get("content")
        if not isinstance(content, str) or not content:
            return f"{E_INVALID_PATCH}: {op} 需要非空 content 字符串"
        if "\n" in content or "\r" in content:
            return f"{E_INVALID_PATCH}: {op} 的 content 不允许包含换行（单行内操作）"
        err = validate_line_content(content)
        if err:
            return f"{E_INVALID_PATCH}: {err}"
        if op == "replace_text":
            pair = _parse_replace_pair(content)
            if isinstance(pair, str):
                return f"{E_INVALID_PATCH}: {pair}"
            old, _new = pair
            line_text = lines[lineno - 1]
            count = line_text.count(old)
            if count == 0:
                return f"{E_INVALID_PATCH}: replace_text 的 old {old!r} 在目标行中不存在"
            if count > 1:
                return (
                    f"{E_INVALID_PATCH}: replace_text 的 old {old!r} 在目标行中出现 {count} 次，"
                    f"不唯一，请提供更多上下文"
                )
    return None


def _affected_after(edit: dict, lineno: int, new_len: int, old_len: int) -> tuple:
    """计算单条编辑应用后的受影响行窗口（1 起始闭区间 [lo, hi]）

    三行窗口语义：编辑行 N 只影响 N-1/N/N+1 锚点；行数变化时行号偏移。
    """
    op = edit.get("op")
    if op == "replace":
        k = len(edit.get("lines") or [])
        end_lineno = lineno
        if edit.get("end") is not None:
            try:
                end_lineno = parse_anchor(edit.get("end"))[0]
            except ValueError:
                end_lineno = lineno
        delta = k - (end_lineno - lineno + 1)  # 新行数 - 旧区间行数
        hi_old = end_lineno + 1
        hi_new = hi_old + delta
        return (max(1, lineno - 1), min(new_len, hi_new))
    # append/prepend/replace_text：单行内容变化，行数不变
    return (max(1, lineno - 1), min(new_len, lineno + 1))


def apply_edits(lines: list, edits: list, width: int = DEFAULT_WIDTH) -> tuple:
    """全部校验 → 自底向上应用 → 返回 (new_lines, meta)

    meta: {
        "errors": [..],        # 非空 = 校验失败，new_lines 恒等于原 lines（不写文件）
        "noop": bool,          # 应用后内容是否无变化
        "affected": (lo, hi),  # 受影响行窗口（1 起始闭区间），成功时有效
        "applied": [..],       # 应用成功的编辑序号（0 起始）
    }
    """
    meta = {"errors": [], "noop": False, "affected": None, "applied": []}
    if not isinstance(edits, list) or not edits:
        meta["errors"] = [f"{E_INVALID_PATCH}: edits 必须是非空数组"]
        return lines, meta

    # 1) 全部校验（基于 pre-edit 快照）
    hashes = hash_all(lines, width)
    for i, edit in enumerate(edits):
        err = validate_edit(edit, lines, hashes, width)
        if err:
            meta["errors"].append(f"Edit #{i + 1} ({edit.get('op', '?')} @ {edit.get('pos', '?')}): {err}")
    if meta["errors"]:
        return lines, meta

    # 2) 自底向上应用（pos 行号降序；区间 replace 按 pos 排序）
    def _order(edit):
        try:
            return parse_anchor(edit.get("pos", ""))[0]
        except ValueError:
            return -1

    new_lines = list(lines)
    old_len = len(lines)
    applied = []
    affected_lo, affected_hi = old_len + 1, 0
    for i, edit in sorted(enumerate(edits), key=lambda t: _order(t[1]), reverse=True):
        lineno = parse_anchor(edit["pos"])[0]
        idx = lineno - 1
        op = edit["op"]
        if op == "replace":
            new_rows = list(edit["lines"])
            if edit.get("end") is not None:
                end_lineno = parse_anchor(edit["end"])[0]
                new_lines[idx:end_lineno] = new_rows
            else:
                new_lines[idx:idx + 1] = new_rows
        elif op == "append":
            new_lines[idx] = new_lines[idx] + edit["content"]
        elif op == "prepend":
            new_lines[idx] = edit["content"] + new_lines[idx]
        elif op == "replace_text":
            pair = _parse_replace_pair(edit["content"])
            if isinstance(pair, str):  # 校验阶段已拦截，理论不可达
                continue
            old, new = pair
            new_lines[idx] = new_lines[idx].replace(old, new, 1)
        applied.append(i)
        lo, hi = _affected_after(edit, lineno, len(new_lines), old_len)
        affected_lo = min(affected_lo, lo)
        affected_hi = max(affected_hi, hi)

    meta["applied"] = applied
    meta["noop"] = (new_lines == lines)
    if applied:
        meta["affected"] = (affected_lo, affected_hi)
    return new_lines, meta


def note_noop(tool_ctx, full_path, sig: str) -> Optional[str]:
    """no-op 编辑计数（同 sig 连续累计；跨 sig 重置）。

    返回 None = 允许（第 1/2 次，已计入）；返回错误消息 = 达到阈值 E_NOOP_LOOP。
    """
    state = _noop_state(tool_ctx)
    key = str(full_path)
    cur = state.get(key)
    if cur is not None and cur.get("sig") == sig:
        cur["count"] += 1
    else:
        cur = {"sig": sig, "count": 1}
    state[key] = cur
    if cur["count"] >= NOOP_LIMIT:
        return (
            f"{E_NOOP_LOOP}: 连续 {NOOP_LIMIT} 次相同的 no-op 编辑（内容未产生任何变化）。"
            f"请先 read 确认文件当前内容，再给出有实际变更的编辑。"
        )
    return None


def reset_noop(tool_ctx, full_path) -> None:
    """成功编辑后重置 no-op 计数"""
    try:
        _noop_state(tool_ctx).pop(str(full_path), None)
    except Exception:
        pass


def build_anchors(lines: list, affected: tuple, width: int = DEFAULT_WIDTH) -> str:
    """生成链式编辑新锚点块：`--- Anchors A-B ---` + 受影响行锚点"""
    hashes = hash_all(lines, width)
    lo, hi = affected
    return format_anchors_block(lo, hi, lines, hashes)


def register(registry):
    """占位入口：核心逻辑模块不注册工具（满足仓库校验器要求）。"""
    return None
