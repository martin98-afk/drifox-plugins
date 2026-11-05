#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
detect_plugin_changes.py — 找出需要（重新）发布 tarball 的插件

判定：插件在 marketplace.json 里已有 tarball 字段（tarball 通道已启用），
但 tarball URL 里的版本与清单当前 version 不一致 → 需要重新构建发布。

设计取舍：
  - 只跟进「已启用 tarball 通道」的插件。新插件首次发布仍需手动跑
    build + publish（首次需人工验证包能装、功能正常）。
  - 不升版本号不会触发发布：semver 语义（patch/minor/major）是人的决定，
    CI 不替人猜。

输出：逗号分隔的插件名（无变更输出空行），供 workflow 传给 --only。
与 tools/build_plugin_tarballs.py 的 --only 参数格式一致。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MARKETPLACE_PATH = REPO_ROOT / "marketplace.json"

# release 资产 URL：.../releases/download/plugin-<name>-v<version>/<file>
_URL_VER_RE = re.compile(r"/releases/download/plugin-[^/]+?-v(\d+\.\d+\.\d+)/")


def tarball_versions(tb: dict) -> set:
    """从 tarball 字段各平台条目解析已发布版本集合"""
    versions: set = set()
    if not isinstance(tb, dict):
        return versions
    for key, meta in tb.items():
        if key == "mirrors" or not isinstance(meta, dict):
            continue
        url = str(meta.get("url") or "")
        m = _URL_VER_RE.search(url)
        if m:
            versions.add(m.group(1))
    return versions


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="检测需发布 tarball 的插件")
    ap.add_argument(
        "--all",
        action="store_true",
        help="输出全部已启用 tarball 的插件（强制重打用，忽略版本比对）",
    )
    args = ap.parse_args()

    if not MARKETPLACE_PATH.is_file():
        print("")
        return 0
    try:
        data = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"marketplace.json 读取失败: {e}", file=sys.stderr)
        return 2

    changed: list[str] = []
    for plugin in data.get("plugins") or []:
        if not isinstance(plugin, dict):
            continue
        name = str(plugin.get("name") or "")
        version = str(plugin.get("version") or "")
        tb = plugin.get("tarball")
        if not name or not version or not tb:
            continue  # 未启用 tarball 通道：不走自动发布
        if args.all or version not in tarball_versions(tb):
            changed.append(name)

    print(",".join(changed))
    if changed:
        mode = "强制全量" if args.all else "版本不一致"
        print(f"[detect] {len(changed)} 个插件（{mode}）", file=sys.stderr)
    else:
        print("[detect] 无版本变更", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
