#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_community.py — 采集所有 fork 本仓库的社区插件「来源」，写入 marketplace.json

设计原则（社区分支约定）：
- **不复制代码**：本仓库只保留 example-plugin 模板，社区插件代码留在各自 fork。
- **只记录来源**：把 fork 中的社区插件条目 append 进 marketplace.json 的 plugins 数组，
  source.url 指向 fork、source.path 指向 plugins/<name>、source.ref 指向 fork 默认分支。
- 用户在 plugin-marketplace 看到来源后，去对应 fork 下载安装。

配合 .github/workflows/sync-community.yml 定时运行，生成 PR 由人工审核合并。

依赖：gh CLI（已注入 GITHUB_TOKEN），以及同目录的 generate_marketplace.py（复用 infer_categories / normalize_author）。
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

# 复用 generate_marketplace 的类别推断与作者归一逻辑，保证 entry 结构与官方一致
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_marketplace import infer_categories, normalize_author  # noqa: E402

MARKETPLACE = Path(__file__).resolve().parent.parent / "marketplace.json"
TEMPLATE_PLUGIN = "example-plugin"  # fork 里的模板插件不计入社区来源


def _gh_api(path: str):
    """调 gh api；失败/解析错返回 None（容错：fork 不可读/限流都跳过）。"""
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def _current_repo() -> str:
    out = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True, text=True,
    )
    return out.stdout.strip()


def list_forks(repo: str) -> list[dict]:
    forks: list[dict] = []
    page = 1
    while True:
        data = _gh_api(f"/repos/{repo}/forks?per_page=100&page={page}")
        if not data:
            break
        forks.extend(data)
        if len(data) < 100:
            break
        page += 1
    return forks


def list_plugin_dirs(fork_full: str) -> list[str]:
    data = _gh_api(f"/repos/{fork_full}/contents/plugins")
    if not isinstance(data, list):
        return []
    return [d["name"] for d in data if d.get("type") == "dir"]


def read_manifest(fork_full: str, name: str) -> dict | None:
    data = _gh_api(f"/repos/{fork_full}/contents/plugins/{name}/.drifox-plugin/plugin.json")
    if not isinstance(data, dict) or "content" not in data:
        return None
    try:
        return json.loads(base64.b64decode(data["content"]).decode("utf-8"))
    except Exception:
        return None


def main() -> int:
    if not MARKETPLACE.exists():
        print("marketplace.json 不存在，请先运行 generate_marketplace.py", file=sys.stderr)
        return 1

    mp = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    plugins = mp.setdefault("plugins", [])
    existing = {p.get("name") for p in plugins}

    repo = _current_repo()
    if not repo:
        print("无法确定当前仓库（gh 未登录？）", file=sys.stderr)
        return 1

    added: list[str] = []
    for f in list_forks(repo):
        fork_full = f.get("full_name", "")
        default_branch = f.get("default_branch") or "main"
        fork_url = f.get("html_url", "")
        if not fork_full or not fork_url:
            continue
        for name in list_plugin_dirs(fork_full):
            if name == TEMPLATE_PLUGIN:
                continue  # 模板插件不算社区来源
            if name in existing:
                continue  # 同名已收录，跳过后续 fork
            manifest = read_manifest(fork_full, name)
            if not manifest or not manifest.get("name"):
                continue
            owner = fork_full.split("/")[0]
            entry = {
                "name": manifest["name"],
                "description": manifest.get("description", ""),
                "version": manifest.get("version", "0.1.0"),
                "author": normalize_author(manifest.get("author")) or owner,
                "license": manifest.get("license", "Unknown"),
                "categories": infer_categories(manifest),
                "source": {
                    "type": "git-subdir",
                    "url": fork_url,
                    "path": f"plugins/{name}",
                    "ref": default_branch,
                    "fork": True,
                },
                "components": manifest.get("components", {}),
            }
            if manifest.get("keywords"):
                entry["keywords"] = manifest["keywords"]
            if manifest.get("icon"):
                entry["icon"] = manifest["icon"]
            if manifest.get("drifox"):
                entry["drifox"] = manifest["drifox"]
            plugins.append(entry)
            existing.add(name)
            added.append(f"{fork_full}/{name}")

    MARKETPLACE.write_text(json.dumps(mp, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"采集社区插件来源 {len(added)} 个：")
    for a in added:
        print(f"  + {a}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
