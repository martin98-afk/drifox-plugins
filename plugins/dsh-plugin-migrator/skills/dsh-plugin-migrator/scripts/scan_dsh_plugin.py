#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描一个 dsh 插件包，产出能力清单 JSON。

用法:
    python scripts/scan_dsh_plugin.py --source <pkg-dir> [--out <file>]

退出码:
    0 — 扫描成功（可能含 warnings）
    2 — 源不是 dsh 插件 / 缺关键材料（硬停止）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("需要 PyYAML：pip install pyyaml", file=sys.stderr)
    raise SystemExit(2)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# harness 宿主固有服务：这些包不属于可迁移范围
HOST_SERVICES = {
    "dsh-base", "dsh-llm", "dsh-session", "dsh-agent", "dsh-workspace",
    "dsh-attachment", "dsh-attachment-local", "dsh-authorization", "dsh-otel",
    "dsh-hmr", "dsh-client-hmr", "dsh-config-editor", "dsh-settings",
    "dsh-session-persistence-jsonl", "dsh-session-log-deepseek",
    "dsh-session-query-sqlite", "dsh-credentials-local", "dsh-typert-registry",
    "dsh-typert-loader", "dsh-api-gateway", "dsh-api-remote-access",
    "dsh-api-remotes", "dsh-api-session-controller", "dsh-api-workspace-controller",
    "dsh-jobs-local", "dsh-llm-retry", "dsh-llm-pi-ai", "dsh-compaction",
    "dsh-plugin-manager", "dsh-plugin-market", "dsh-host-plugin-inventory",
    "dsh-plugin-package-inventory-deepseek", "dsh-anonymous-user-id",
    "dsh-brand", "dsh-atomic-write", "dsh-app-boot", "dsh-cli", "dsh",
    "dsh-time-context", "dsh-persona", "dsh-agent-instructions",
    "dsh-agent-default-model", "dsh-session-title",
    "dsh-deepseek-account-platform", "dsh-deepseek-llm-api-extensions",
    "dsh-client-connection", "dsh-client-locale", "dsh-client-modules",
    "dsh-client-runtime", "dsh-client-schema-form", "dsh-skill",
    "dsh-skill-filesystem", "dsh-tool-skill", "dsh-skill-badge",
    "dsh-commands", "dsh-tools", "dsh-native-command", "dsh-headless",
    "dsh-web", "dsh-web-app", "dsh-web-frontend", "dsh-cordis-client-runner",
    "dsh-web-deepseek-api", "dsh-web-search-deepseek", "dsh-web-fetch-http",
    "dsh-user-questions", "dsh-user-approval", "dsh-permission-presets",
    "dsh-repeat-tool-reminder", "dsh-compaction-tool-result-pruner",
    "dsh-agent-tool-presentation", "dsh-agent-loop", "dsh-scope",
}

JS_PREFIX = "__JS_EXPR__ "

# 一个离散 dsh 插件不会声明这么多 patch 行；超过即视为 harness 组合层
AGGREGATE_ROW_THRESHOLD = 20


class _PatchLoader(yaml.SafeLoader):
    """容忍 cordis patch 里的 `!!js` 自定义标签。"""


def _unknown_tag(loader: yaml.Loader, tag_suffix: str, node: yaml.Node) -> Any:
    """未知标签（`!!js <expr>`）原样保留为带前缀的字符串，不做求值。"""
    if isinstance(node, yaml.ScalarNode):
        return JS_PREFIX + str(loader.construct_scalar(node))
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


_PatchLoader.add_multi_constructor("", _unknown_tag)


def load_patch_yaml(text: str) -> Any:
    return yaml.load(text, Loader=_PatchLoader)


def is_js_expr(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(JS_PREFIX)


def read_js_expr(value: str) -> str:
    return value[len(JS_PREFIX):].strip()


def load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"warn: {path} 解析失败: {e}", file=sys.stderr)
        return None


def parse_frontmatter(content: str) -> dict | None:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            try:
                data = load_patch_yaml("\n".join(lines[1:i]))
            except yaml.YAMLError as e:
                print(f"warn: frontmatter YAML 解析失败: {e}", file=sys.stderr)
                return None
            return data if isinstance(data, dict) else None
    return None


def pkg_short_name(full: str) -> str:
    """`@deepseek-ai/dsh-tool-subagent/model-selection-settings` -> `dsh-tool-subagent`。

    cordis 的 `name` 允许 `@scope/pkg/subpath`，表示包内具名导出。
    取 `pkg` 而不是最后一段，否则子导出会被误判成独立包。
    """
    parts = (full or "").split("/")
    if full.startswith("@"):
        return parts[1] if len(parts) > 1 else full
    return parts[0]


def pkg_subpath(full: str) -> str:
    """`@deepseek-ai/dsh-tool-subagent/model-selection-settings` -> `model-selection-settings`"""
    parts = (full or "").split("/")
    if full.startswith("@"):
        return "/".join(parts[2:]) if len(parts) > 2 else ""
    return "/".join(parts[1:]) if len(parts) > 1 else ""


def walk_patch_rows(node: Any, depth: int = 0) -> list[dict]:
    """递归展开 patch / group 行，返回扁平行列表。"""
    rows: list[dict] = []
    if not isinstance(node, list):
        return rows
    for entry in node:
        if not isinstance(entry, dict):
            continue
        for row in entry.get("insert", []) or []:
            if not isinstance(row, dict):
                continue
            item = {
                "id": row.get("id"),
                "name": row.get("name"),
                "subpath": pkg_subpath(row.get("name")),
                "depth": depth,
                "group": bool(row.get("group")),
                "disabled": row.get("disabled"),
                "config": row.get("config") if not row.get("group") else None,
            }
            rows.append(item)
            if row.get("group"):
                rows.extend(walk_patch_rows(row.get("config"), depth + 1))
            rows.extend(walk_patch_rows(row.get("config") if row.get("group") else None, depth + 1))
    return rows


def dedup_rows(rows: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for r in rows:
        key = (r.get("id"), r.get("name"), r.get("depth"))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _scan_one_root(root: Path, base: Path) -> list[dict]:
    """扫一个 skill 根的深度 1（与 dsh-skill-filesystem 一致）。"""
    found: list[dict] = []
    for child in sorted(root.iterdir()):
        if child.name.startswith(".") or child.name in {"node_modules", "lib", "types", "locale"}:
            continue
        if child.is_dir():
            skill_md = child / "SKILL.md"
            if skill_md.exists():
                fm = parse_frontmatter(skill_md.read_text(encoding="utf-8")) or {}
                found.append({
                    "kind": "bundle",
                    "name": child.name,
                    "path": str(child.relative_to(base)),
                    "frontmatter": fm,
                    "resources": sorted(
                        d.name for d in child.iterdir()
                        if d.is_dir() and d.name in {"references", "scripts", "assets", "examples"}
                    ),
                })
        elif child.suffix == ".md" and child.name not in {"README.md", "README.zh.md", "CHANGELOG.md"}:
            fm = parse_frontmatter(child.read_text(encoding="utf-8")) or {}
            found.append({
                "kind": "flat",
                "name": child.stem,
                "path": str(child.relative_to(base)),
                "frontmatter": fm,
                "resources": [],
            })
    return found


def scan_skill_bundles(root: Path) -> list[dict]:
    """发现包内的 skill bundle 与平铺 .md。

    包根与 `<pkg>/skills/` 都是合法 skill 根：dsh-skill-filesystem 允许
    `bundledSkillDir` 随包提供 skill，多数包就放在 `skills/` 下。
    深度固定为 1，与 dsh 的发现语义一致。
    """
    found = _scan_one_root(root, root)
    seen = {f["path"] for f in found}
    for sub in ("skills",):
        sub_root = root / sub
        if sub_root.is_dir():
            for item in _scan_one_root(sub_root, root):
                if item["path"] not in seen:
                    seen.add(item["path"])
                    found.append(item)
    return found


def guess_ui_hint(name: str, row: dict) -> dict:
    """推测一个 Client UI 包该注册哪类 DriFox 扩展点、挂哪个方位。

    判据全部来自包名与 patch 行 id 的语义，强度很低：
    host 侧的 `dsh-client-ui-*` 包 `apply()` 大多是空函数（实测 32 个里 31 个
    没有任何 register 调用），浏览器那一半通过 package.json 的 dsh.client
    声明单独分发，host 包里根本没有 UI 结构可提取。
    所以这里只决定「注册哪个扩展点」和「挂哪个方位」，widget 一律留空。
    """
    hay = f"{name} {row.get('id') or ''}".lower()
    if "sidebar" in hay or "right" in hay:
        container = "right"
    elif any(k in hay for k in ("setting", "config", "preference", "inventory", "model")):
        container = "right"
    elif any(k in hay for k in ("conversation", "chat", "trajectory", "message")):
        container = "bottom"
    elif any(k in hay for k in ("plan", "goal", "approval", "input-trigger")):
        container = "bottom"
    else:
        container = "right"

    if any(k in hay for k in ("setting", "config", "preference", "inventory")):
        kind = "settings_card"
    elif any(k in hay for k in ("render", "attachment", "reference", "trajectory", "deliverable", "documentpreview")):
        kind = "content_renderer"
    elif any(k in hay for k in ("message", "feedback", "tool", "approval", "user-questions")):
        kind = "message_factory"
    else:
        kind = "floating_card"

    return {"extension": kind, "container": container, "confidence": "low"}


def guess_stub_target(name: str, row: dict) -> str:
    """推测一个 stub 行该落到哪个 DriFox 通道。

    只是推测，不是事实：源包若没有可读材料（README/locale/src），
    判定会退化。下游必须把这个值连同 TODO 一起交给人复核。
    """
    haystack = f"{name} {row.get('id') or ''}".lower()
    if "mcp" in haystack:
        return "mcp"
    if any(k in haystack for k in ("audit", "session-log", "telemetry", "observ", "stat", "track", "record", "injector", "watch")):
        return "hooks"
    if any(k in haystack for k in ("theme", "brand", "style")):
        return "themes"
    if "lsp" in haystack:
        return "lsp"
    if any(k in haystack for k in ("ui-", "panel", "render", "widget", "sidebar")):
        return "ui"
    return "tools"


def classify_row(row: dict) -> dict:
    """给出单个 patch 行的建议处置。"""
    name = pkg_short_name(row.get("name") or "")
    note = ""
    target = "none"
    if name in HOST_SERVICES:
        verdict = "skip"
        note = "dsh 宿主固有服务"
    elif name.startswith("dsh-client-ui-") or name.startswith("dsh-client-") or "-ui-" in name:
        verdict = "stub"
        target = "ui"
        note = "Client UI（见 §3.7）：仅扩展点类型与容器方位可推测，widget 实现须人工重写"
    elif name.startswith("dsh-command-"):
        verdict = "stub"
        target = "commands"
        note = "TS handler 命令；仅 locale 的 title/description 可搬"
    elif name.startswith("dsh-tool-"):
        verdict = "stub"
        target = "tools"
        note = "TS 工具；parameters schema 可搬，execute 不可搬"
    elif name == "dsh-agent-preset":
        verdict = "port"
        target = "agents"
        note = "preset 声明可落成 agents/<id>.md 骨架"
    elif name == "dsh-mcp-client" or "mcp" in name:
        verdict = "stub"
        target = "mcp"
        note = "MCP 客户端/服务端；只写 .mcp.json 骨架（enabled=false，凭据待填）"
    elif name.startswith("dsh-"):
        verdict = "stub"
        target = guess_stub_target(name, row)
        note = f"dsh 运行时服务包，按语义推测落 {target}"
    else:
        verdict = "stub"
        target = guess_stub_target(name, row)
        note = f"第三方包（目标推测为 {target}），需读 README/locale 确认"

    disabled = row.get("disabled")
    if disabled is True:
        verdict = "skip"
        target = "none"
        note = "patch 行默认 disabled（可选能力）" + (f"；{note}" if note else "")
    elif is_js_expr(disabled):
        note += f"；disabled 为不可静态求值的 JS 表达式: {read_js_expr(disabled)}"

    out = {"verdict": verdict, "target": target, "note": note}
    if target == "ui":
        out["ui_hint"] = guess_ui_hint(name, row)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="扫描 dsh 插件包并产出能力清单")
    ap.add_argument("--source", required=True, help="dsh 插件包目录")
    ap.add_argument("--out", default=None, help="输出 JSON 路径，默认打印到 stdout")
    args = ap.parse_args()

    src = Path(args.source).expanduser().resolve()
    if not src.is_dir():
        print(f"error: 源目录不存在: {src}", file=sys.stderr)
        return 2

    pkg_json = src / "package.json"
    if not pkg_json.exists():
        print("error: 无 package.json —— 不是 dsh 插件（硬停止）", file=sys.stderr)
        return 2
    pkg = load_json(pkg_json)
    if pkg is None:
        return 2

    dsh_decl = pkg.get("dsh")
    if dsh_decl is None:
        print("error: package.json 无 dsh 声明段 —— 不是可直接迁移的 dsh 插件（硬停止）", file=sys.stderr)
        return 2

    warnings: list[str] = []

    # dsh 声明形态
    if isinstance(dsh_decl, str):
        print(f"error: dsh 段是 CLI bin 入口（{dsh_decl}）—— 不是插件（skip）", file=sys.stderr)
        return 2
    decl_kind = "client" if isinstance(dsh_decl, dict) and "client" in dsh_decl else "bundle"
    patch_files: list[str] = []
    if decl_kind == "bundle":
        raw = (dsh_decl.get("bundle") or {}).get("patch")
        patch_files = [raw] if isinstance(raw, str) else list(raw or [])

    # patch 行
    rows: list[dict] = []
    for rel in patch_files:
        p = src / rel
        if not p.exists():
            print(f"error: dsh.bundle.patch 指向的文件不存在: {rel}（硬停止）", file=sys.stderr)
            return 2
        try:
            data = load_patch_yaml(p.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            print(f"error: patch YAML 解析失败 {rel}: {e}", file=sys.stderr)
            return 2
        rows.extend(walk_patch_rows(data))
    rows = dedup_rows(rows)

    for r in rows:
        r.update(classify_row(r))

    # preset 内的 plugins 清单单独抽出来（语义重要但不可映射）
    presets: list[dict] = []
    for r in rows:
        if pkg_short_name(r.get("name") or "") == "dsh-agent-preset":
            cfg = r.get("config") or {}
            sub = cfg.get("plugins") if isinstance(cfg, dict) else None
            presets.append({
                "preset_id": cfg.get("id") if isinstance(cfg, dict) else r.get("id"),
                "order": cfg.get("order") if isinstance(cfg, dict) else None,
                "plugins": [
                    {"id": s.get("id"), "name": s.get("name")}
                    for s in (sub or []) if isinstance(s, dict)
                ],
            })

    skills = scan_skill_bundles(src)

    # 第三方 dsh 插件通常带 dshWorkshop 元数据块与 engines.dsh 版本约束；
    # 两者都是语义来源（能力契约、兼容范围），缺了会让迁移丧失判定依据。
    workshop = pkg.get("dshWorkshop") if isinstance(pkg.get("dshWorkshop"), dict) else None
    engines = pkg.get("engines") if isinstance(pkg.get("engines"), dict) else None
    dsh_range = (engines or {}).get("dsh")
    if workshop is None:
        warnings.append("无 dshWorkshop 元数据块 —— 缺能力契约与兼容性声明，判定依据变弱")
    if not dsh_range:
        warnings.append("engines.dsh 未声明 —— 无法判断源包面向哪个 harness 版本")

    # locale 里的可读显示名
    locale_meta: dict[str, str] = {}
    for loc in sorted((src / "locale").glob("zh.json")) if (src / "locale").is_dir() else []:
        data = load_json(loc)
        if isinstance(data, dict) and isinstance(data.get("meta"), dict):
            locale_meta = data["meta"]
            break

    readable_materials = {
        "has_readme": any((src / f).exists() for f in ("README.md", "README.zh.md")),
        "has_locale": bool(locale_meta),
        "has_src_dir": (src / "src").is_dir(),
        "has_types": (src / "types").is_dir() or (src / "lib" / "types").is_dir(),
    }
    if not readable_materials["has_readme"] and not readable_materials["has_locale"]:
        warnings.append("源包无 README 也无 locale —— 语义只能靠编译产物推断，产出将大量降级为 stub")

    # 聚合 bundle 拒识：一个「离散插件」不会声明几十个 patch 行，
    # 那是 harness 的组合层（dsh-web-app / dsh-base 这类），迁它会产出一堆垃圾。
    # 同理，stub 占比过高说明材料不足以支撑自动迁移。
    total_rows = len(rows)
    stub_rows = sum(1 for r in rows if r["verdict"] == "stub")
    agg = {
        "is_aggregate_bundle": total_rows >= AGGREGATE_ROW_THRESHOLD,
        "row_count": total_rows,
        "stub_count": stub_rows,
        "stub_ratio": round(stub_rows / total_rows, 3) if total_rows else 0.0,
    }
    if agg["is_aggregate_bundle"]:
        warnings.append(
            f"该包声明了 {total_rows} 个 patch 行（stub 占比 {agg['stub_ratio']}）——"
            "它看起来是 harness 组合层而非离散插件。整体迁移会产出大量无语义 stub；"
            "应从清单里挑单个能力单元作为迁移目标，而不是整包搬。"
        )

    inventory: dict[str, Any] = {
        "source_dir": str(src),
        "package": {
            "name": pkg.get("name"),
            "version": pkg.get("version"),
            "description": pkg.get("description"),
            "license": pkg.get("license"),
            "repository": (pkg.get("repository") or {}).get("url") if isinstance(pkg.get("repository"), dict) else None,
        },
        "dsh_declaration": {"kind": decl_kind, "raw": dsh_decl},
        "engines_dsh": dsh_range,
        "dsh_workshop": {
            "schema": (workshop or {}).get("schema"),
            "type": (workshop or {}).get("type"),
            "permissions": (workshop or {}).get("permissions") or [],
            "dsh_versions": ((workshop or {}).get("compatibility") or {}).get("dshVersions") or [],
            "capability": (workshop or {}).get("capability") or {},
            "lifecycle": (workshop or {}).get("lifecycle") or {},
        },
        "aggregate_bundle": agg,
        "patch_files": patch_files,
        "patch_rows": rows,
        "agent_presets": presets,
        "skill_bundles": skills,
        "locale_meta": locale_meta,
        "readable_materials": readable_materials,
        "warnings": warnings,
        "verdict_summary": {
            v: sum(1 for r in rows if r["verdict"] == v) for v in ("port", "stub", "skip")
        },
    }
    inventory["verdict_summary"]["skill_bundles"] = len(skills)

    text = json.dumps(inventory, ensure_ascii=False, indent=2)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"已写入 {out}")
        s = inventory["verdict_summary"]
        print(f"patch 行: port={s['port']} stub={s['stub']} skip={s['skip']}；skill bundle={s['skill_bundles']}")
        for w in warnings:
            print(f"warn: {w}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
