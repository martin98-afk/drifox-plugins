#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bench_hashline_vs_oldstring.py — hashline 锚点编辑 vs oldString 纯文本编辑基准

对比「本插件 hashline 锚点模式（operations/anchor）」与「系统 file_tools.edit
oldString 模式」在 LLM 不完美输出下的编辑成功率与 token 消耗。独立基准脚本，
不修改插件功能代码，仅 import hashline_engine/snapshot 用于锚点计算与应用验证。

用法:
    python tools/bench/bench_hashline_vs_oldstring.py                 # 默认配置
    python tools/bench/bench_hashline_vs_oldstring.py --seed 7 --runs 20
    python tools/bench/bench_hashline_vs_oldstring.py --noise-old 0.2 --noise-anchor 0.1
    python tools/bench/bench_hashline_vs_oldstring.py --out report.md

测试集（7 类，每类 ≥10 用例，总 ≥70）：
    1. 单行小替换（<20 字符）     2. 单行长替换（>80 字符）
    3. 多行替换（2-5 行）         4. 大段替换（>5 行）
    5. 含特殊空白（tab/连续空格/行尾空格）
    6. CRLF 行尾文件              7. 重复行文件（oldString 歧义）
    1-4 类从本仓库真实代码文件提取；5-7 类在真实内容基础上合成。

噪声注入（模拟 LLM 复制型输出误差）：
    - oldString：多余空白/缺失换行/缩进错误/大小写错误/字符误抄（默认 p=0.15）
    - hashline：anchor 字符误抄/行号误抄（默认 p=0.05，复制短串误差率低）
    - 失败 → 重试（默认最多 3 次）；hashline 锚点失效 → 重读文件再试

token 口径（可复现）：1 token ≈ 4 字符（OpenAI 经验值，测试集为 ASCII 代码）。
统计三部分：模型输出（edit 参数文本） + 工具回传（成功=unified_diff，
hashline 另含 anchors 块；失败=错误消息/重读 read 输出） × 重试次数。

输出：控制台 Markdown 表格 + 报告文件（默认 tools/bench/report_hashline_vs_oldstring.md）
      + 原始数据 JSON（同目录 *_data.json）。
"""
from __future__ import annotations

import argparse
import difflib
import importlib.util
import json
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# ============================================================
# 路径与插件加载（独立脚本：importlib 加载插件模块）
# ============================================================

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PLUGIN_TOOLS = REPO_ROOT / "plugins" / "hashline-edit" / "tools"

if str(PLUGIN_TOOLS) not in sys.path:
    sys.path.insert(0, str(PLUGIN_TOOLS))


def _load(name: str, filename: str):
    path = PLUGIN_TOOLS / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_engine = _load("hashline_engine", "hashline_engine.py")
_snapshot = _load("snapshot", "snapshot.py")
hash_all = _engine.hash_all
ALPHABET = _engine.ALPHABET
DEFAULT_WIDTH = _engine.DEFAULT_WIDTH
apply_edits = _snapshot.apply_edits
build_anchors = _snapshot.build_anchors

# ============================================================
# 配置
# ============================================================


@dataclass
class BenchConfig:
    seed: int = 42
    runs: int = 10            # 每用例蒙特卡洛次数
    max_attempts: int = 3     # 重试上限（含首次）
    noise_old: float = 0.15   # oldString 噪声概率
    noise_anchor: float = 0.05  # anchor 噪声概率
    out: str = "report_hashline_vs_oldstring.md"

    def as_dict(self) -> dict:
        return {
            "seed": self.seed, "runs": self.runs, "max_attempts": self.max_attempts,
            "noise_old": self.noise_old, "noise_anchor": self.noise_anchor,
        }


# 真实源码文件（测试集提取来源）
SOURCE_FILES = {
    "edit_tool": REPO_ROOT / "plugins/hashline-edit/tools/edit_tool.py",
    "snapshot": REPO_ROOT / "plugins/hashline-edit/tools/snapshot.py",
    "engine": REPO_ROOT / "plugins/hashline-edit/tools/hashline_engine.py",
    "example": REPO_ROOT / "plugins/example-plugin/tools/example_tool.py",
}

# ============================================================
# 用例
# ============================================================


@dataclass
class EditCase:
    category: str
    file_lines: list          # 文件内容（行列表，无行尾 \n；CRLF 场景含 \r）
    target_start: int         # 1 起始目标区块起点
    target_end: int           # 1 起始目标区块终点（含）
    new_content: list         # 替换后的新行内容
    desc: str = ""

    @property
    def old_string(self) -> str:
        """oldString 模式的旧文本（目标区块原文）"""
        nl = "\r\n" if any("\r" in ln for ln in self.file_lines) else "\n"
        return nl.join(self.file_lines[self.target_start - 1:self.target_end])

    @property
    def new_string(self) -> str:
        nl = "\r\n" if any("\r" in ln for ln in self.file_lines) else "\n"
        return nl.join(self.new_content)

    @property
    def multi(self) -> bool:
        return self.target_end > self.target_start


def _extract_from_sources(cat: str, lines: list, start: int, end: int, new_content: list,
                          src_name: str, idx: int) -> EditCase:
    """从源码文件构造用例（目标区块 = [start, end] 1 起始）"""
    return EditCase(
        category=cat,
        file_lines=list(lines),
        target_start=start,
        target_end=end,
        new_content=new_content,
        desc=f"{src_name}:L{start}-{end}",
    )


def build_all_cases(seed: int = 42) -> list:
    """构造完整测试集（7 类 × ≥10 = ≥70 用例）。真实文件提取 + 合成。"""
    rng = random.Random(seed)
    cases: list = []

    # ---- 载入真实源码行池 ----
    pools = {}
    for name, path in SOURCE_FILES.items():
        text = path.read_text(encoding="utf-8")
        pools[name] = text.split("\n")
    # all_lines 未使用（已删）

    # ---- 1. 单行小替换（<20 字符） ----
    small = [(i, ln) for lines in pools.values() for i, ln in enumerate(lines)
             if 1 < len(ln.strip()) < 20 and not ln.strip().startswith(("#", "//", "*"))]
    rng.shuffle(small)
    for src_name, _ in [("small", None)]:  # noqa
        pass
    picked = small[:12]
    for (lineno, line) in picked:
        src = _which_file(pools, lineno, line)
        cases.append(_extract_from_sources(
            "单行小替换", pools[src], lineno, lineno,
            [line + "  # edited"], src, lineno))

    # ---- 2. 单行长替换（>80 字符） ----
    long = [(i, ln) for lines in pools.values() for i, ln in enumerate(lines) if len(ln) > 80]
    rng.shuffle(long)
    for (lineno, line) in long[:12]:
        src = _which_file(pools, lineno, line)
        cases.append(_extract_from_sources(
            "单行长替换", pools[src], lineno, lineno,
            [line.rstrip() + "  # edited"], src, lineno))

    # ---- 3. 多行替换（2-5 行） ----
    added_multi = 0
    for src, lines in pools.items():
        max_start = max(2, len(lines) - 4)
        starts = rng.sample(range(1, max_start + 1), min(4, max_start))
        for s in starts:
            span = rng.randint(2, 5)
            e = min(len(lines), s + span - 1)
            if e > s:
                block = list(lines[s - 1:e])
                block[-1] = block[-1].rstrip() + "  # edited"
                if not _safe_block(block):
                    continue
                cases.append(_extract_from_sources("多行替换", lines, s, e, block, src, s))
                added_multi += 1
    # 补齐到 12
    while added_multi < 12:
        src = rng.choice(list(pools))
        lines = pools[src]
        s = rng.randint(1, max(1, len(lines) - 2))
        e = min(len(lines), s + rng.randint(2, 5) - 1)
        if e > s:
            block = list(lines[s - 1:e])
            block[-1] = block[-1].rstrip() + "  # edited"
            if not _safe_block(block):
                continue
            cases.append(_extract_from_sources("多行替换", lines, s, e, block, src, s))
            added_multi += 1

    # ---- 4. 大段替换（>5 行，6-8 行） ----
    added_big = 0
    for src, lines in pools.items():
        max_start = max(2, len(lines) - 8)
        starts = rng.sample(range(1, max_start + 1), min(3, max_start))
        for s in starts:
            e = min(len(lines), s + rng.randint(6, 8) - 1)
            if e > s + 4:
                block = list(lines[s - 1:e])
                block[-1] = block[-1].rstrip() + "  # edited"
                if not _safe_block(block):
                    continue
                cases.append(_extract_from_sources("大段替换", lines, s, e, block, src, s))
                added_big += 1
    while added_big < 10:
        src = rng.choice(list(pools))
        lines = pools[src]
        s = rng.randint(1, max(1, len(lines) - 8))
        e = min(len(lines), s + rng.randint(6, 8) - 1)
        if e > s + 4:
            block = list(lines[s - 1:e])
            block[-1] = block[-1].rstrip() + "  # edited"
            if not _safe_block(block):
                continue
            cases.append(_extract_from_sources("大段替换", lines, s, e, block, src, s))
            added_big += 1

    # ---- 5. 含特殊空白（tab/连续空格/行尾空格） ----
    base = [ln for lines in pools.values() for ln in lines if 5 < len(ln) < 60]
    rng.shuffle(base)
    for i, line in enumerate(base[:10]):
        # 目标行注入特殊空白
        target = line
        kind = i % 3
        if kind == 0:
            target = "\t" + target.lstrip()          # 行首 tab
        elif kind == 1:
            target = re.sub(r"\s{2,}", "  " * 2, target) + "  "  # 连续空格 + 行尾空格
        else:
            target = target + " \t "                  # 行尾混合空白
        lines = ["header_line", target, "tail_line"]
        cases.append(EditCase(
            category="含特殊空白", file_lines=lines, target_start=2, target_end=2,
            new_content=[target.rstrip() + "  # edited"],
            desc=f"special-whitespace-{i}",
        ))

    # ---- 6. CRLF 行尾文件 ----
    for i, line in enumerate(base[10:20]):
        src_lines = ["import os", line, "def main():", "    pass"]
        crlf_lines = [ln + "\r" for ln in src_lines]   # 行尾 \r（join 用 \n → CRLF）
        target_lineno = 2
        new_content = [line.rstrip() + "  # edited" + "\r"]
        cases.append(EditCase(
            category="CRLF 行尾", file_lines=crlf_lines, target_start=target_lineno,
            target_end=target_lineno, new_content=new_content,
            desc=f"crlf-{i}",
        ))

    # ---- 7. 重复行文件（oldString 歧义） ----
    for i in range(10):
        dup = f"duplicate_line_{i:03d}  # same content"
        lines = ["# header", dup, "middle", dup, "tail"]  # dup 出现 2 次
        target = 2  # 第一处
        cases.append(EditCase(
            category="重复行", file_lines=lines, target_start=target, target_end=target,
            new_content=[dup + "  # edited"],
            desc=f"dup-{i}",
        ))

    return cases


def _safe_block(block: list) -> bool:
    """区块作为 replace lines 是否安全：任一行含 diff 标记/锚点前缀则跳过

    对齐插件 E_INVALID_PATCH 注入检测（真实系统同样拒绝此类内容写入）。
    """
    return all(_engine.validate_line_content(ln) is None for ln in block)


def _which_file(pools: dict, lineno: int, line: str) -> str:
    """定位行所属源文件（行号+内容双因子）"""
    for name, lines in pools.items():
        if 1 <= lineno <= len(lines) and lines[lineno - 1] == line:
            return name
    # 兜底（提取时行号已对齐）
    for name, lines in pools.items():
        if line in lines:
            return name
    return "engine"


# ============================================================
# 噪声注入（模拟 LLM 复制型输出误差）
# ============================================================


def inject_noise_oldstring(s: str, rng: random.Random, p: float) -> tuple:
    """oldString 复制噪声：按概率 p 注入一种误差。返回 (带噪声文本, 是否注入)"""
    if not s or rng.random() >= p:
        return s, False
    kind = rng.choice(["space", "newline", "indent", "case", "typo"])
    if kind == "space":
        return (" " + s, True) if rng.random() < 0.5 else (s + " ", True)
    if kind == "newline":
        if "\n" in s:
            idxs = [j for j, c in enumerate(s) if c == "\n"]
            i = rng.choice(idxs)
            return s[:i] + " " + s[i + 1:], True
        return s + "\n", True
    if kind == "indent":
        lead = len(s) - len(s.lstrip(" "))
        if lead > 0:
            delta = -1 if rng.random() < 0.5 else 1
            return " " * (lead + delta) + s[lead:], True
        return " " + s, True
    if kind == "case":
        idxs = [i for i, c in enumerate(s) if c.isalpha()]
        if idxs:
            i = rng.choice(idxs)
            return s[:i] + s[i].swapcase() + s[i + 1:], True
        return s + " ", True
    # typo：字符误抄（字母/数字 → 相邻字符）
    idxs = [i for i, c in enumerate(s) if c.isalnum()]
    if idxs:
        i = rng.choice(idxs)
        c = s[i]
        return s[:i] + chr(ord(c) + rng.choice([-1, 1])) + s[i + 1:], True
    return s + "x", True


def inject_noise_anchor(a: str, rng: random.Random, p: float) -> tuple:
    """anchor 复制噪声（LINE#HASH）：误抄 hash 字符或行号。返回 (带噪声anchor, 是否注入)"""
    if rng.random() >= p:
        return a, False
    lineno, h = a.split("#")
    if h and rng.random() < 0.7:
        i = rng.randrange(len(h))
        others = [c for c in ALPHABET if c != h[i]]
        new_h = h[:i] + rng.choice(others) + h[i + 1:]
        return f"{lineno}#{new_h}", True
    new_lineno = max(1, int(lineno) + rng.choice([-1, 1]))
    return f"{new_lineno}#{h}", True


# ============================================================
# token 估算
# ============================================================

CHARS_PER_TOKEN = 4  # OpenAI 经验值：1 token ≈ 4 字符（ASCII 代码）


def _tokens(chars: int) -> int:
    return max(1, -(-chars // CHARS_PER_TOKEN))  # ceil


def _diff_text(old_lines: list, new_lines: list, path: str = "t.txt") -> str:
    old_text = "\n".join(old_lines) + ("\n" if old_lines else "")
    new_text = "\n".join(new_lines) + ("\n" if new_lines else "")
    dl = list(difflib.unified_diff(
        old_text.splitlines(), new_text.splitlines(),
        fromfile=path, tofile=path, lineterm="",
    ))
    return "\n".join(dl)


def build_read_output(lines: list) -> str:
    """模拟 hashline read 回传（#File 头 + 全行锚点）"""
    hashes = hash_all(lines, DEFAULT_WIDTH)
    header = f"#File: t.txt (Lines 1-{len(lines)} of {len(lines)})"
    body = [f"{i + 1}#{hashes[i]}: {lines[i]}" for i in range(len(lines))]
    return header + ("\n" + "\n".join(body) if body else "")


def _args_json(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


# ============================================================
# 模式执行模拟
# ============================================================


def simulate_oldstring(case: EditCase, rng: random.Random, cfg: BenchConfig) -> dict:
    """模拟系统 file_tools.edit（oldString 精确匹配 + count 唯一性）"""
    content = "\n".join(case.file_lines) + ("\n" if case.file_lines else "")
    attempts = 0
    out_chars = 0
    back_chars = 0
    for _ in range(cfg.max_attempts):
        attempts += 1
        old, _noised = inject_noise_oldstring(case.old_string, rng, cfg.noise_old)
        args = _args_json({"path": "t.txt", "oldString": old, "newString": case.new_string})
        out_chars += len(args)
        count = content.count(old)
        if count == 1:
            new_content = content.replace(old, case.new_string, 1)
            back_chars += len(_diff_text(content.splitlines(), new_content.splitlines()))
            return {"success": True, "attempts": attempts,
                    "tokens": _tokens(out_chars + back_chars),
                    "out_tokens": _tokens(out_chars), "back_tokens": _tokens(back_chars)}
        elif count == 0:
            back_chars += len("The specified 'oldString' was not found in the file. Ensure exact match including whitespace and indentation.")
        else:
            back_chars += len(
                f"The 'oldString' appears {count} times in the file. Please provide a more specific context to ensure uniqueness, or set replaceAll=True."
            )
    return {"success": False, "attempts": attempts,
            "tokens": _tokens(out_chars + back_chars),
            "out_tokens": _tokens(out_chars), "back_tokens": _tokens(back_chars)}


def simulate_hashline(case: EditCase, rng: random.Random, cfg: BenchConfig) -> dict:
    """模拟插件 edit（operations/anchor 锚点校验 + E_STALE_ANCHOR 重读重试）"""
    lines = list(case.file_lines)
    hashes = hash_all(lines, DEFAULT_WIDTH)
    start, end = case.target_start, case.target_end
    anchor = f"{start}#{hashes[start - 1]}"
    end_anchor = f"{end}#{hashes[end - 1]}" if end != start else None

    attempts = 0
    out_chars = 0
    back_chars = 0

    for _ in range(cfg.max_attempts):
        attempts += 1
        # 首次 read（拿锚点）为两种模式的共同前置成本（oldString 同样需先了解文件），
        # 不计入对比；锚点失效后的重读为 hashline 特有额外成本，计入回传。
        a2, _noised = inject_noise_anchor(anchor, rng, cfg.noise_anchor)
        op = {"op": "replace", "anchor": a2, "lines": case.new_content}
        if end_anchor:
            op["end"] = end_anchor
        args = _args_json({"path": "t.txt", "operations": [op]})
        out_chars += len(args)
        if a2 == anchor:
            # 成功：回传 anchors 块 + diff
            edits = [{"op": "replace", "anchor": anchor, "lines": case.new_content}]
            if end_anchor:
                edits[0]["end"] = end_anchor
            new_lines, meta = apply_edits(lines, edits, DEFAULT_WIDTH)
            if meta["errors"]:  # 防御：注入检测等拒绝（正常测试集已过滤）
                return {"success": False, "attempts": attempts,
                        "tokens": _tokens(out_chars + back_chars),
                        "out_tokens": _tokens(out_chars), "back_tokens": _tokens(back_chars)}
            anchors = build_anchors(new_lines, meta["affected"], DEFAULT_WIDTH)
            diff = _diff_text(lines, new_lines)
            back_chars += len(anchors) + len(diff)
            return {"success": True, "attempts": attempts,
                    "tokens": _tokens(out_chars + back_chars),
                    "out_tokens": _tokens(out_chars), "back_tokens": _tokens(back_chars)}
        # E_STALE_ANCHOR → 重读文件再试
        back_chars += len("E_STALE_ANCHOR: 锚点已失效，文件可能已被修改，请重新 read 拿最新锚点")
        back_chars += len(build_read_output(lines))
    return {"success": False, "attempts": attempts,
            "tokens": _tokens(out_chars + back_chars),
            "out_tokens": _tokens(out_chars), "back_tokens": _tokens(back_chars)}


# ============================================================
# 统计与报告
# ============================================================


def _aggregate(results: list) -> dict:
    n = len(results)
    ok = [r for r in results if r["success"]]
    first_ok = [r for r in results if r["success"] and r["attempts"] == 1]
    return {
        "first_success_rate": len(first_ok) / n,
        "final_success_rate": len(ok) / n,
        "avg_attempts": sum(r["attempts"] for r in results) / n,
        "avg_tokens": sum(r["tokens"] for r in results) / n,
        "avg_out_tokens": sum(r["out_tokens"] for r in results) / n,
        "avg_back_tokens": sum(r["back_tokens"] for r in results) / n,
    }


def run_benchmark(cfg: BenchConfig) -> dict:
    cases = build_all_cases(seed=cfg.seed)
    rows = []
    for ci, case in enumerate(cases):
        old_results = []
        hl_results = []
        for run in range(cfg.runs):
            rng = random.Random(cfg.seed * 100000 + ci * 1000 + run)
            old_results.append(simulate_oldstring(case, rng, cfg))
            hl_results.append(simulate_hashline(case, rng, cfg))
        rows.append({
            "case_id": ci + 1,
            "category": case.category,
            "desc": case.desc,
            "old": _aggregate(old_results),
            "hl": _aggregate(hl_results),
        })
    return {"config": cfg.as_dict(), "case_count": len(cases), "rows": rows}


def _fmt_pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def render_report(data: dict) -> str:
    cfg = data["config"]
    rows = data["rows"]
    cats = []
    for r in rows:
        if r["category"] not in cats:
            cats.append(r["category"])


    # 按类别
    cat_stats = {}
    for c in cats:
        cat_rows = [r for r in rows if r["category"] == c]
        cat_stats[c] = {
            "n": len(cat_rows),
            "old": {k: sum(r["old"][k] for r in cat_rows) / len(cat_rows) for k in ("first_success_rate", "final_success_rate", "avg_attempts", "avg_tokens")},
            "hl": {k: sum(r["hl"][k] for r in cat_rows) / len(cat_rows) for k in ("first_success_rate", "final_success_rate", "avg_attempts", "avg_tokens")},
        }

    L = []
    L.append("# hashline vs oldString 编辑基准报告\n")
    L.append("## 测试集分布\n")
    L.append("| 类别 | 用例数 | 说明 |")
    L.append("|---|---|---|")
    desc_map = {
        "单行小替换": "行内容 <20 字符，行尾追加标记",
        "单行长替换": "行内容 >80 字符，整行替换",
        "多行替换": "连续 2-5 行替换",
        "大段替换": "连续 >5 行替换",
        "含特殊空白": "tab / 连续空格 / 行尾空格行",
        "CRLF 行尾": "行尾 \\r\\n 文件",
        "重复行": "两处相同内容，目标为第一处（oldString 歧义）",
    }
    for c in cats:
        L.append(f"| {c} | {cat_stats[c]['n']} | {desc_map.get(c, '')} |")
    L.append(f"| **合计** | **{data['case_count']}** | 1-4 类从真实代码文件提取，5-7 类合成 |\n")

    L.append("## 噪声配置与 token 口径\n")
    L.append(f"- 噪声概率：oldString `{cfg['noise_old']}`（多余空白/缺失换行/缩进/大小写/字符误抄）；"
             f"anchor `{cfg['noise_anchor']}`（hash 字符/行号误抄）")
    L.append(f"- 重试上限 `{cfg['max_attempts']}` 次；每用例蒙特卡洛 `{cfg['runs']}` 次；seed `{cfg['seed']}`")
    L.append("- token 口径：1 token ≈ 4 字符（OpenAI 经验值，ASCII 代码）；"
             "模型输出=edit 参数 JSON；回传=成功 unified_diff（hashline 另含 anchors 块）/失败错误消息（hashline 含重读 read 输出）\n")

    L.append("## 数据（按类别）\n")
    L.append("| 类别 | 模式 | 首次成功率 | 最终成功率 | 平均尝试 | 平均总 token |")
    L.append("|---|---|---|---|---|---|")
    for c in cats:
        s = cat_stats[c]
        L.append(f"| {c} | oldString | {_fmt_pct(s['old']['first_success_rate'])} | "
                 f"{_fmt_pct(s['old']['final_success_rate'])} | {s['old']['avg_attempts']:.2f} | {s['old']['avg_tokens']:.0f} |")
        L.append(f"| {c} | hashline | {_fmt_pct(s['hl']['first_success_rate'])} | "
                 f"{_fmt_pct(s['hl']['final_success_rate'])} | {s['hl']['avg_attempts']:.2f} | {s['hl']['avg_tokens']:.0f} |")

    L.append("\n## 总体对比\n")
    L.append("| 指标 | oldString | hashline | 差异 |")
    L.append("|---|---|---|---|")
    for label, key in [("首次成功率", "first_success_rate"), ("最终成功率", "final_success_rate"),
                       ("平均尝试次数", "avg_attempts"), ("平均总 token", "avg_tokens")]:
        o = sum(r["old"][key] for r in rows) / len(rows)
        h = sum(r["hl"][key] for r in rows) / len(rows)
        if key == "avg_tokens":
            o_s, h_s = f"{o:.0f}", f"{h:.0f}"
            diff = f"{(h - o) / o * 100:+.1f}%（hashline {'省' if h < o else '多'} {abs(h - o):.0f} token）" if o else "-"
        elif key == "avg_attempts":
            o_s, h_s = f"{o:.2f}", f"{h:.2f}"
            diff = f"{h - o:+.2f}"
        else:
            o_s, h_s = _fmt_pct(o), _fmt_pct(h)
            diff = f"{(h - o) * 100:+.1f} pp"
        L.append(f"| {label} | {o_s} | {h_s} | {diff} |")

    # token 节省（按类别）
    L.append("\n## token 节省（hashline vs oldString，按类别）\n")
    L.append("| 类别 | oldString token | hashline token | 节省幅度 |")
    L.append("|---|---|---|---|")
    for c in cats:
        s = cat_stats[c]
        o, h = s["old"]["avg_tokens"], s["hl"]["avg_tokens"]
        save = (o - h) / o * 100 if o else 0
        L.append(f"| {c} | {o:.0f} | {h:.0f} | {save:+.1f}% |")

    # 结论（数据驱动）
    L.append("\n## 结论\n")
    o_first = sum(r["old"]["first_success_rate"] for r in rows) / len(rows)
    h_first = sum(r["hl"]["first_success_rate"] for r in rows) / len(rows)
    o_final = sum(r["old"]["final_success_rate"] for r in rows) / len(rows)
    h_final = sum(r["hl"]["final_success_rate"] for r in rows) / len(rows)
    o_tok = sum(r["old"]["avg_tokens"] for r in rows) / len(rows)
    h_tok = sum(r["hl"]["avg_tokens"] for r in rows) / len(rows)
    L.append(f"- 成功率：首次 {_fmt_pct(h_first)} vs {_fmt_pct(o_first)}（hashline {'高' if h_first > o_first else '低'} "
             f"{abs(h_first - o_first) * 100:.1f} pp）；最终 {_fmt_pct(h_final)} vs {_fmt_pct(o_final)}")
    L.append(f"- token：hashline 平均 {h_tok:.0f} vs oldString {o_tok:.0f}，"
             f"总体 {'节省' if h_tok < o_tok else '多出'} {abs(h_tok - o_tok):.0f} token"
             f"（{(o_tok - h_tok) / o_tok * 100:+.1f}%）")
    best_save = min(cat_stats.items(), key=lambda kv: (kv[1]["hl"]["avg_tokens"] - kv[1]["old"]["avg_tokens"]) / max(kv[1]["old"]["avg_tokens"], 1))
    worst_save = max(cat_stats.items(), key=lambda kv: (kv[1]["hl"]["avg_tokens"] - kv[1]["old"]["avg_tokens"]) / max(kv[1]["old"]["avg_tokens"], 1))
    L.append(f"- 收益最大：{best_save[0]}（节省 {(1 - best_save[1]['hl']['avg_tokens'] / max(best_save[1]['old']['avg_tokens'], 1)) * 100:.1f}%）")
    L.append(f"- 收益最小/无收益：{worst_save[0]}（{'节省' if worst_save[1]['hl']['avg_tokens'] < worst_save[1]['old']['avg_tokens'] else '多出'} "
             f"{abs(worst_save[1]['hl']['avg_tokens'] - worst_save[1]['old']['avg_tokens']):.0f} token）")
    L.append("\n## 复现命令\n")
    L.append(f"```bash\npython tools/bench/bench_hashline_vs_oldstring.py --seed {cfg['seed']} "
             f"--runs {cfg['runs']} --noise-old {cfg['noise_old']} --noise-anchor {cfg['noise_anchor']}\n```\n")
    return "\n".join(L)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="hashline vs oldString 编辑基准")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--noise-old", type=float, default=0.15)
    parser.add_argument("--noise-anchor", type=float, default=0.05)
    parser.add_argument("--out", default="report_hashline_vs_oldstring.md")
    args = parser.parse_args(argv)

    cfg = BenchConfig(seed=args.seed, runs=args.runs, max_attempts=args.max_attempts,
                      noise_old=args.noise_old, noise_anchor=args.noise_anchor,
                      out=args.out)
    print(f"运行基准：seed={cfg.seed} runs={cfg.runs} max_attempts={cfg.max_attempts} "
          f"noise_old={cfg.noise_old} noise_anchor={cfg.noise_anchor}")
    data = run_benchmark(cfg)
    print(f"测试集：{data['case_count']} 用例 × 2 模式 × {cfg.runs} 次蒙特卡洛")

    report = render_report(data)
    out_dir = Path(__file__).resolve().parent
    out_path = out_dir / cfg.out
    out_path.write_text(report, encoding="utf-8")
    data_path = out_path.with_suffix(".json")
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告已写入: {out_path}")
    print(f"原始数据: {data_path}")
    print()
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())