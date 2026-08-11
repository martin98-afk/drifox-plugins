#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_downloads.py — 从计数服务拉取各插件下载量，缓存到 downloads_cache.json

由 CI 定时执行（.github/workflows/update-downloads.yml），随后
generate_marketplace.py 会把缓存写入 marketplace.json 的 downloads 字段。

用法:
    python tools/fetch_downloads.py            # 拉取全部插件下载量并更新缓存
    python tools/fetch_downloads.py --check    # 仅检查计数服务可达性，不写缓存

退出码:
    0 — 成功（全部或部分插件拉取成功）
    1 — 计数服务完全不可达（全部失败）
    2 — 参数错误 / marketplace.json 缺失
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from downloads_stats import (
    COUNT_API_BASE,
    _request,
    fetch_downloads,
    load_downloads_cache,
    save_downloads_cache,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
MARKETPLACE_PATH = REPO_ROOT / "marketplace.json"
CACHE_PATH = REPO_ROOT / "downloads_cache.json"

_IS_TTY = sys.stdout.isatty()


def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m" if _IS_TTY else s


def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m" if _IS_TTY else s


def _yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m" if _IS_TTY else s


def _list_plugin_names() -> list[str]:
    """从 marketplace.json 读取全部插件名"""
    if not MARKETPLACE_PATH.exists():
        raise FileNotFoundError(f"marketplace.json 不存在: {MARKETPLACE_PATH}")
    data = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))
    return [p["name"] for p in data.get("plugins", []) if p.get("name")]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="从计数服务拉取插件下载量并缓存到 downloads_cache.json"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="仅检查计数服务可达性，不写缓存",
    )
    args = parser.parse_args(argv if argv is not None else None)

    try:
        names = _list_plugin_names()
    except FileNotFoundError as e:
        print(_red(f"✗ {e}"))
        return 2
    except (json.JSONDecodeError, KeyError) as e:
        print(_red(f"✗ marketplace.json 解析失败: {e}"))
        return 2

    if not names:
        print(_yellow("marketplace.json 中无插件，无需统计。"))
        return 0

    print(f"待统计插件: {len(names)} 个")
    if args.check:
        data = _request("/get/drifox-plugins-probe")
        if data is None:
            print(_red(f"✗ 计数服务不可达: {COUNT_API_BASE}"))
            return 1
        print(_green(f"✓ 计数服务可达: {COUNT_API_BASE}"))
        return 0

    cache = load_downloads_cache(CACHE_PATH)
    previous = cache.get("downloads", {})

    print("拉取下载量...")
    downloads = fetch_downloads(names, previous=previous)
    # 以「全部失败」作为致命错误判定：所有插件值都为 0 且缓存也为空时视为失败
    total = sum(downloads.values())
    if total == 0 and not previous:
        print(_red("✗ 计数服务拉取全部失败（所有插件计数为 0 且无历史缓存）"))
        return 1

    save_downloads_cache(CACHE_PATH, downloads, time.time())
    for name in names:
        print(f"  {name:30s} {downloads.get(name, 0):>8d}")
    print()
    print(_green(f"✓ 已更新 {CACHE_PATH.relative_to(REPO_ROOT)}（{len(names)} 个插件，累计 {total}）"))
    return 0


if __name__ == "__main__":
    from downloads_stats import COUNT_API_BASE

    sys.exit(main())
