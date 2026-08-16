#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_hooks.py — 校验所有插件 hooks 能否被 DriFox 实际加载并执行

与 validate_plugins.py（静态结构校验）互补：本工具用 DriFox 真实的
HookManager 注册并触发每个 hook，验证:
    1. hooks.json 是合法 JSON，hooks 字典结构正确
    2. python 类型 hook 的模块可被 DriFox 相对导入（.module:func）
    3. 模块函数真实存在且可调用
    4. 触发事件时 hook 真实执行成功（success=True）

用法:
    python tools/validate_hooks.py
    python tools/validate_hooks.py plugins/ponytail
    python tools/validate_hooks.py --drifox D:/work/DriFox

退出码:
    0 — 全部通过（warning 不算失败）
    1 — 至少一个插件校验失败
    2 — 致命错误（无法定位 DriFox / 缺少依赖）
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = REPO_ROOT / "plugins"

# DriFox 仓库定位：环境变量 > --drifox 参数 > 常见路径
DRIFOX_CANDIDATES = [
    os.environ.get("DRIFOX_ROOT", ""),
    "D:/work/DriFox",
    "D:/work/drifox",
    str(Path.home() / "work" / "DriFox"),
]

SUPPORTED_EVENTS = {
    "BuildSystemPrompt",
    "SessionStart",
    "Stop",
    "UserPromptSubmit",
    "PreUserMessage",
    "PostUserMessage",
    "PreAssistantMessage",
    "PostAssistantMessage",
    "PreToolUse",
    "PostToolUse",
}

# 事件 → 最小触发上下文（仅保证 hook 函数能跑通，不含真实业务数据）
_EVENT_CONTEXTS: dict[str, dict] = {
    "BuildSystemPrompt": {"agent_name": "test-agent", "is_subagent_call": False},
    "SessionStart": {"state": "startup"},
    "Stop": {"reason": "completed"},
    "UserPromptSubmit": {"message": "test"},
    "PreUserMessage": {"message": "test"},
    "PostUserMessage": {"message": "test"},
    "PreAssistantMessage": {"message": "test"},
    "PostAssistantMessage": {"message": "test"},
    "PreToolUse": {"tool_name": "Read", "message": "test"},
    "PostToolUse": {"tool_name": "Read", "message": "test"},
}


def _matcher_context(event_name: str, matcher: str | None) -> dict:
    """按规则 matcher 构造能命中的最小上下文。

    工具名 matcher（Edit|Write|MultiEdit 等）需注入匹配的 tool_name，
    否则 matcher 类 hook 永远无法触发验证。
    """
    ctx = dict(_EVENT_CONTEXTS.get(event_name, {"message": "test"}))
    if not matcher or event_name not in ("PreToolUse", "PostToolUse"):
        return ctx
    if matcher.startswith("tool:"):
        ctx["tool_name"] = matcher[5:].split("|")[0]
        return ctx
    # Edit|Write|MultiEdit 等：取第一个工具名
    names = [n.strip() for n in matcher.split("|") if n.strip()]
    if names:
        # Bash 有 command，Edit/Write 有 file_path，兼顾各 matcher
        first = names[0]
        ctx["tool_name"] = first
        if first.lower() in ("bash",):
            ctx["tool_input"] = {"command": "echo test"}
        elif first.lower() in ("edit", "write", "multiedit"):
            ctx["tool_input"] = {"file_path": "test.py"}
        else:
            ctx["tool_input"] = {}
    return ctx

_IS_TTY = sys.stdout.isatty()


def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m" if _IS_TTY else s


def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m" if _IS_TTY else s


def _yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m" if _IS_TTY else s


def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m" if _IS_TTY else s


@dataclass
class HookCheckResult:
    plugin: str
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    executed: int = 0  # 成功执行的 hook 数
    total: int = 0  # 找到的 hook 总数


def resolve_drifox(override: str | None = None) -> Path | None:
    """定位 DriFox 仓库根目录（含 app/core/hook_manager.py）。"""
    for cand in ([override] if override else []) + DRIFOX_CANDIDATES:
        if not cand:
            continue
        p = Path(cand)
        if (p / "app" / "core" / "hook_manager.py").exists():
            return p.resolve()
    return None


def copy_hooks_to_temp(plugin_dir: Path) -> Path:
    """把插件 hooks/ 目录复制到临时目录（避免注册时 id 写回污染源文件）。

    同时复制插件根目录下 hooks 模块可能依赖的兄弟包（core/、utils/ 等），
    保证相对导入的 hook 模块能找到自己的依赖。
    """
    tmp = Path(tempfile.mkdtemp(prefix="hook_validate_"))
    dst = tmp / "hooks"
    shutil.copytree(plugin_dir / "hooks", dst)
    # 复制插件根下的兄弟依赖包（浅层，仅 hooks 模块会 import 的 core/ utils/）
    for dep in ("core", "utils", "matchers"):
        src_dep = plugin_dir / dep
        if src_dep.is_dir():
            shutil.copytree(src_dep, tmp / dep, ignore=shutil.ignore_patterns("__pycache__"))
    return dst


def check_one(plugin_dir: Path, drifox_root: Path) -> HookCheckResult:
    """用真实 HookManager 注册并触发插件所有 hooks。"""
    name = plugin_dir.name
    result = HookCheckResult(plugin=name, ok=True)
    hooks_dir = plugin_dir / "hooks"
    hooks_file = hooks_dir / "hooks.json"

    # 1. JSON 合法 + hooks 字典
    try:
        cfg = json.loads(hooks_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        result.ok = False
        result.errors.append(f"hooks/hooks.json 不是合法 JSON: {e}")
        return result
    raw_hooks = cfg.get("hooks")
    if not isinstance(raw_hooks, dict) or not raw_hooks:
        result.ok = False
        result.errors.append("hooks/hooks.json 缺少 hooks 字典或为空")
        return result

    # 2. 复制到临时目录，避免注册写回源文件
    tmp_hooks = copy_hooks_to_temp(plugin_dir)
    tmp_file = tmp_hooks / "hooks.json"
    try:
        from app.core.hook_manager import HookManager

        hm = HookManager()
        registered = hm.register_hooks_from_json(
            name, str(tmp_hooks), cfg, str(tmp_file)
        )
        if registered <= 0:
            result.ok = False
            result.errors.append("HookManager 注册 0 个 hook")
            return result

        # 3. 逐个事件触发执行
        for event_name, rules in raw_hooks.items():
            if event_name not in SUPPORTED_EVENTS:
                result.warnings.append(f"事件 {event_name} 不在 DriFox SUPPORTED_EVENTS 中")
            seen_rules: set[int] = set()
            for rule_idx, rule in enumerate(rules):
                if rule_idx in seen_rules:
                    continue
                seen_rules.add(rule_idx)
                # 每个规则独立触发：用其 matcher 构造命中上下文
                matcher = rule.get("matcher")
                ctx = _matcher_context(event_name, matcher)
                results = hm.trigger_event(event_name, context=ctx, trigger_async=False)
                matched = [r for r in results if r.success or r.output]
                for r in matched:
                    result.total += 1
                    if r.success:
                        result.executed += 1
                    else:
                        result.ok = False
                        result.errors.append(
                            f"{event_name} 执行失败: {r.output[:200]}"
                        )

        # 4. 注销本插件 hooks，避免类级共享状态串到下一插件
        hm.unregister_skill_hooks(name)
    except Exception as e:
        result.ok = False
        result.errors.append(f"HookManager 加载异常: {type(e).__name__}: {e}")
    finally:
        shutil.rmtree(tmp_hooks.parent, ignore_errors=True)

    return result


def discover_plugins(targets: list[Path] | None = None) -> list[Path]:
    if targets:
        return [t for t in targets if t.is_dir() and (t / "hooks" / "hooks.json").exists()]
    if not PLUGINS_DIR.exists():
        return []
    return sorted(
        d for d in PLUGINS_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".") and (d / "hooks" / "hooks.json").exists()
    )


def print_result(r: HookCheckResult) -> None:
    if r.ok and not r.warnings:
        print(f"  {_green('OK')}   {r.plugin}  ({r.executed}/{r.total} hooks 执行成功)")
        return
    if r.ok:
        print(f"  {_yellow('WARN')} {r.plugin}  ({r.executed}/{r.total} hooks 执行成功)")
    else:
        print(f"  {_red('FAIL')} {r.plugin}")
    for w in r.warnings:
        print(f"        {_yellow('warn')}: {w}")
    for e in r.errors:
        print(f"        {_red('err')}: {e}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="校验所有插件 hooks 能否被 DriFox 实际加载并执行"
    )
    parser.add_argument(
        "targets", nargs="*", type=Path,
        help="指定插件目录（相对或绝对路径），省略则扫描 plugins/* 下所有带 hooks 的插件",
    )
    parser.add_argument(
        "--drifox", type=str, default=None,
        help="DriFox 仓库根目录（默认自动探测 DRIFOX_ROOT / D:/work/DriFox）",
    )
    args = parser.parse_args(argv)

    print(_bold("DriFox hooks validator"))
    print(f"  repo:   {REPO_ROOT}")

    drifox_root = resolve_drifox(args.drifox)
    if drifox_root is None:
        print(f"  {_red('致命')}: 未找到 DriFox 仓库（需含 app/core/hook_manager.py）")
        print("        设置环境变量 DRIFOX_ROOT 或 --drifox 指定路径")
        return 2
    print(f"  drifox: {drifox_root}")

    # 校验 DriFox 依赖可导入
    sys.path.insert(0, str(drifox_root))
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        import PyQt5  # noqa: F401
        import loguru  # noqa: F401
    except ImportError as e:
        print(f"  {_red('致命')}: 缺少 DriFox 运行依赖: {e}")
        return 2
    print()

    plugins = discover_plugins(args.targets or None)
    if not plugins:
        print(_yellow("未发现带 hooks/hooks.json 的插件目录。"))
        return 0

    results = [check_one(p, drifox_root) for p in plugins]

    print(_bold("结果："))
    ok_count = 0
    for r in results:
        print_result(r)
        if r.ok:
            ok_count += 1

    print()
    if ok_count == len(results):
        print(_green(f"✓ 全部 {len(results)} 个插件的 hooks 均可被 DriFox 加载执行"))
        return 0
    print(_red(f"✗ {len(results) - ok_count}/{len(results)} 个插件 hooks 验证失败"))
    return 1


if __name__ == "__main__":
    sys.exit(main())
