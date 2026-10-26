#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验迁移产物的结构一致性，并给出证明层级的判定。

用法:
    python scripts/check_migration.py <plugin-dir> [--repo <drifox-plugins2 根>]

退出码:
    0 — 结构一致（structure_status=artifact_consistent）
    1 — 结构有问题
    2 — 目标不是迁移产物 / 参数错误

这个脚本只证明结构，不证明运行，更不证明语义。存在未处理 MIGRATION_TODO 时，
它会把 runtime_status 判为 blocked —— 这是预期行为，不是脚本缺陷。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

TODO_MARK = "MIGRATION_TODO"
MANIFEST_KEYS = ("name", "description", "version", "components")
REQUIRED_FILES = (".drifox-plugin/plugin.json", "README.md", "__init__.py")


def find_todos(root: Path) -> list[tuple[str, int, str]]:
    hits: list[tuple[str, int, str]] = []
    skip_dirs = {"__pycache__", ".git", "node_modules"}
    for path in root.rglob("*"):
        if not path.is_file() or any(p in skip_dirs for p in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if TODO_MARK in line:
                hits.append((str(path.relative_to(root)), i, line.strip()[:120]))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description="校验 dsh→DriFox 迁移产物")
    ap.add_argument("plugin_dir")
    ap.add_argument("--repo", default=None, help="仓库根，用于定位 validate_plugins.py")
    args = ap.parse_args()

    plugin = Path(args.plugin_dir).resolve()
    if not plugin.is_dir():
        print(f"error: 不是目录 {plugin}", file=sys.stderr)
        return 2

    failures: list[str] = []
    warnings: list[str] = []

    for rel in REQUIRED_FILES:
        if not (plugin / rel).exists():
            failures.append(f"缺少必需文件：{rel}")

    report = plugin / "migration-report.md"
    if not report.exists():
        warnings.append("无 migration-report.md —— 这不是 dsh-plugin-migrator 的产物（若手工迁移可忽略）")

    manifest_path = plugin / ".drifox-plugin" / "plugin.json"
    if manifest_path.exists():
        import json
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            failures.append(f"plugin.json 非法 JSON: {e}")
            manifest = {}
        for key in MANIFEST_KEYS:
            if key not in manifest:
                failures.append(f"plugin.json 缺少 {key}")
        name = manifest.get("name")
        if name and name != plugin.name:
            failures.append(f"plugin.json 的 name={name!r} 与目录名 {plugin.name!r} 不一致")
        if name and not re.match(r"^[a-z][a-z0-9-]{1,63}$", name):
            failures.append(f"name 不符合 kebab-case: {name!r}")
        desc = manifest.get("description") or ""
        if not (1 <= len(desc) <= 200):
            failures.append(f"description 长度须 1-200，当前 {len(desc)}")
        comps = manifest.get("components") or {}
        for flag in ("commands", "agents", "skills", "tools", "hooks", "ui", "mcp", "lsp", "themes"):
            target = {
                "commands": "commands", "agents": "agents", "skills": "skills",
                "tools": "tools", "hooks": "hooks", "ui": "ui", "themes": "themes",
            }.get(flag)
            if comps.get(flag):
                if target and not (plugin / target).is_dir():
                    failures.append(f"components.{flag}=true 但 {target}/ 不存在")
                if flag == "mcp" and not (plugin / ".mcp.json").exists():
                    failures.append("components.mcp=true 但 .mcp.json 不存在")
                if flag == "lsp" and not (plugin / ".lsp.json").exists():
                    failures.append("components.lsp=true 但 .lsp.json 不存在")

    # 运行仓库的 validate_plugins.py（若可定位）
    validator = None
    candidates = []
    if args.repo:
        candidates.append(Path(args.repo) / "tools" / "validate_plugins.py")
    p = plugin
    for _ in range(6):
        if (p / "tools" / "validate_plugins.py").exists():
            candidates.append(p / "tools" / "validate_plugins.py")
            break
        p = p.parent
    for c in candidates:
        if c.exists():
            validator = c
            break

    validate_status = "not-run"
    if validator:
        proc = subprocess.run(
            [sys.executable, str(validator), str(plugin)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        out = proc.stdout or ""
        # validate_plugins.py 会额外跑全仓 marketplace 一致性检查，那个 FAIL
        # 属于仓库规则（新增插件须跑 generate_marketplace.py），不是本产物结构问题。
        # 因此只看以本插件名结尾的那一行 OK/FAIL。
        own = re.search(rf"^\s*(OK|FAIL)\s+{re.escape(plugin.name)}\s*$", out, re.M)
        own_ok = own.group(1) == "OK" if own else None
        if own_ok is True:
            validate_status = "pass"
        elif own_ok is False:
            validate_status = "fail"
            failures.append(f"validate_plugins.py 判定 {plugin.name} FAIL")
            for line in out.splitlines():
                s = line.strip()
                if s.startswith(("err:", "warn:","error:")) or s.startswith("-"):
                    failures.append(f"  {s[:160]}")
        else:
            validate_status = "unknown"
            warnings.append(f"未能从 validate_plugins.py 输出中定位 {plugin.name} 的判定行")
        for line in out.splitlines():
            s = line.strip()
            if s.startswith("warn:"):
                warnings.append(f"  {s[:160]}")
            if s.startswith("err:") and "marketplace.json" in s:
                warnings.append(f"外部项（不计入本产物结构）：{s[:160]}")
    else:
        warnings.append("未定位 validate_plugins.py —— 用 --repo 指定仓库根")

    todos = find_todos(plugin)
    structure_ok = not failures
    runtime = "blocked" if todos else ("pass" if structure_ok else "blocked")

    print(f"结构检查：{'通过' if structure_ok else '失败'}（validate_plugins.py: {validate_status}）")
    print(f"structure_status = {'artifact_consistent' if structure_ok else 'inconsistent'}")
    print(f"runtime_status   = {runtime}   # 未处理 TODO 数：{len(todos)}")
    print("human_status     = unverified  # 必须由人工比对源插件语义后填写")
    if todos:
        print(f"\n未处理 {TODO_MARK}（{len(todos)}）：")
        for f, ln, txt in todos[:40]:
            print(f"  {f}:{ln} {txt}")
        if len(todos) > 40:
            print(f"  ... 其余 {len(todos) - 40} 条见 migration-report.md")
    if warnings:
        print("\n警告：")
        for w in warnings:
            print(f"  {w}")
    if failures:
        print("\n失败项：")
        for f in failures:
            print(f"  {f}")
    return 0 if structure_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
