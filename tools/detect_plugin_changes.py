#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
detect_plugin_changes.py — 找出需要（重新）发布 tarball 的插件

真源是 `plugins/*/.drifox-plugin/plugin.json`，不是 marketplace.json：新插件
首次推送时后者还没生成对应条目（generate_marketplace 要等 build 产物），
以清单为真源才能让新插件同样走自动发布。

判定逐插件：
  1. 清单里读不到 name / version → 跳过（畸形，交给 validate 报错）
  2. 已有 tarball 字段且已发布版本 == 当前 version → 不需要发布
  3. 其余（版本不一致 / 从未发布过 / tarball 字段缺失）→ 需要发布

`--all` 强制输出全部插件（忽略版本比对）。

输出：逗号分隔的插件名（无变更输出空行），供 workflow 传给 --only。
与 tools/build_plugin_tarballs.py 的 --only 参数格式一致。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = REPO_ROOT / "plugins"
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


def load_published() -> dict:
    """marketplace.json 里的已发布信息：{插件名: tarball 字段}。

    缺失或损坏时返回空字典 —— 此时所有插件都算「从未发布」，会全量重建。
    这是有意的保守选择：宁可多打几个包，也不漏掉该发的插件。
    """
    if not MARKETPLACE_PATH.is_file():
        return {}
    try:
        data = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[detect] marketplace.json 读取失败（按全部未发布处理）: {e}", file=sys.stderr)
        return {}
    out: dict = {}
    for plugin in data.get("plugins") or []:
        if isinstance(plugin, dict) and plugin.get("name"):
            out[str(plugin["name"])] = plugin.get("tarball") or {}
    return out


def iter_manifests():
    """遍历 plugins/ 下的插件清单，产出 (name, version)"""
    if not PLUGINS_DIR.is_dir():
        return
    for plugin_dir in sorted(PLUGINS_DIR.iterdir()):
        if not plugin_dir.is_dir() or plugin_dir.name.startswith("."):
            continue
        mf = plugin_dir / ".drifox-plugin" / "plugin.json"
        if not mf.is_file():
            continue
        try:
            manifest = json.loads(mf.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[detect] {plugin_dir.name} 清单解析失败（跳过）: {e}", file=sys.stderr)
            continue
        name = str(manifest.get("name") or plugin_dir.name)
        version = str(manifest.get("version") or "")
        if not version:
            print(f"[detect] {name} 缺 version（跳过）", file=sys.stderr)
            continue
        yield name, version


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="检测需发布 tarball 的插件")
    ap.add_argument(
        "--all",
        action="store_true",
        help="输出全部插件（强制重打用，忽略版本比对）",
    )
    args = ap.parse_args()

    published = load_published()

    changed: list[str] = []
    new_plugins: list[str] = []
    for name, version in iter_manifests():
        tb = published.get(name)
        if args.all:
            changed.append(name)
            continue
        if tb is None:
            # marketplace 里还没有这个插件 → 首次发布
            new_plugins.append(name)
            changed.append(name)
            continue
        if version not in tarball_versions(tb):
            changed.append(name)

    print(",".join(changed))
    if changed:
        mode = "强制全量" if args.all else "版本不一致/首次发布"
        detail = f"，其中首次发布 {len(new_plugins)} 个" if new_plugins else ""
        print(f"[detect] {len(changed)} 个插件（{mode}{detail}）", file=sys.stderr)
    else:
        print("[detect] 无变更", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
