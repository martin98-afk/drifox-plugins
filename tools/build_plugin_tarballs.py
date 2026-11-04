#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_plugin_tarballs.py — 为市场插件构建按平台分发的 tarball

背景：
  插件 vendored deps 已从 git 出库（仓库只留源码），安装端改为「单插件 tarball」
  分发。每个包 = 插件源码 + 当前平台 deps，客户端下载后解压即用，离线可用。

产物：
  dist/<name>-<version>-<platform>.tar.gz      单平台包（含该平台 deps）
  dist/<name>-<version>-all.tar.gz             无平台差异的插件（纯源码或无平台 deps）
  dist/tarball_index.json                      包索引（url/sha256/size），供
                                               marketplace.json 的 tarball 字段合并

平台语义：
  - 插件 deps 含 win32/darwin/linux 子目录 → 按平台分包，包内只保留该平台子目录
  - deps 无平台子目录（依赖两平台通用）→ 打 all 包
  - 无 deps → 打 all 包（纯源码）

用法：
  python tools/build_plugin_tarballs.py                     # 全部插件，输出到 dist/
  python tools/build_plugin_tarballs.py --only bili-scroll  # 单个插件（灰度/调试）
  python tools/build_plugin_tarballs.py --deps-backup D:/path/to/deps   # 指定 deps 来源

deps 来源（按优先级）：
  1. plugins/<name>/deps/（本地开发时已同步的目录）
  2. --deps-backup 目录下的 <name>/deps/（出库前的备份）
  两处都没有而 manifest 声明了 pip 依赖时，该包仍可构建（纯源码），
  但会打印 warning：客户端安装后需自行补依赖。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = REPO_ROOT / "plugins"
DEFAULT_OUT = REPO_ROOT / "dist"
DEFAULT_DEPS_BACKUP = Path(r"D:/work/_drifox_plugins_backup/20261105/deps")

REPO_URL = "https://github.com/martin98-afk/drifox-plugins"
RELEASE_TAG_PREFIX = "plugin-"  # release tag 约定：plugin-<name>-v<version>

PLATFORMS = ("win32", "darwin", "linux")
# 包内不需要的东西（开发产物/缓存）
EXCLUDE_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}


def read_manifest(plugin_dir: Path) -> Optional[dict]:
    mf = plugin_dir / ".drifox-plugin" / "plugin.json"
    if not mf.is_file():
        return None
    try:
        return json.loads(mf.read_text(encoding="utf-8"))
    except Exception:
        return None


def resolve_deps_dir(plugin_dir: Path, backup_root: Optional[Path]) -> Tuple[Optional[Path], str]:
    """定位该插件的 deps 目录：本地优先，其次备份。返回 (路径, 来源说明)"""
    local = plugin_dir / "deps"
    if local.is_dir():
        return local, "local"
    if backup_root is not None:
        cand = backup_root / plugin_dir.name / "deps"
        if cand.is_dir():
            return cand, "backup"
    return None, ""


def has_platform_dirs(deps_dir: Optional[Path]) -> bool:
    return bool(deps_dir and any((deps_dir / p).is_dir() for p in PLATFORMS))


def iter_files(root: Path, skip_deps_platforms: Optional[set] = None):
    """遍历目录下要入包的文件，产出 (绝对路径, 包内相对路径)

    skip_deps_platforms：要保留的平台名集合；非集合内的平台子目录跳过。
    注意 root 可能是插件根（首段为 deps/...）或 deps 根（首段直接是平台名），
    两种形态都按「首段命中平台名」处理，不依赖 deps/ 前缀。
    """
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        parts = p.relative_to(root).parts
        if any(part in EXCLUDE_NAMES for part in parts):
            continue
        if p.suffix in EXCLUDE_SUFFIXES:
            continue
        # deps 平台过滤：首段是平台名且不在保留集合 → 跳过
        if skip_deps_platforms and parts[0] in PLATFORMS and parts[0] not in skip_deps_platforms:
            continue
        yield p, "/".join(parts)


def build_tarball(
    plugin_dir: Path,
    deps_dir: Optional[Path],
    out_path: Path,
    keep_platforms: Optional[set],
) -> Tuple[str, int]:
    """打包插件源码 + deps，返回 (sha256, size)"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256()
    with tarfile.open(out_path, "w:gz", compresslevel=6) as tf:
        # 1) 插件源码（不含 deps，deps 单独按平台过滤加入）
        for abs_path, rel in iter_files(plugin_dir, skip_deps_platforms=set(PLATFORMS)):
            if rel.split("/", 1)[0] == "deps":
                continue
            info = tf.gettarinfo(str(abs_path), arcname=rel)
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            with open(abs_path, "rb") as fh:
                tf.addfile(info, fh)
        # 2) deps（按平台过滤）
        if deps_dir is not None and deps_dir.is_dir():
            for abs_path, rel in iter_files(deps_dir, skip_deps_platforms=keep_platforms):
                arcname = f"deps/{rel}"
                info = tf.gettarinfo(str(abs_path), arcname=arcname)
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mtime = 0
                with open(abs_path, "rb") as fh:
                    tf.addfile(info, fh)
    size = out_path.stat().st_size
    with open(out_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest(), size


def release_url(name: str, version: str, filename: str) -> str:
    tag = f"{RELEASE_TAG_PREFIX}{name}-v{version}"
    return f"{REPO_URL}/releases/download/{tag}/{filename}"


def main() -> int:
    ap = argparse.ArgumentParser(description="构建市场插件 tarball（按平台）")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="输出目录（默认 dist/）")
    ap.add_argument("--deps-backup", default=str(DEFAULT_DEPS_BACKUP), help="deps 备份根目录")
    ap.add_argument("--only", default="", help="只构建指定插件（逗号分隔）")
    ap.add_argument("--platforms", default=",".join(PLATFORMS), help="要构建的平台（逗号分隔）")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    backup_root = Path(args.deps_backup) if args.deps_backup else None
    if backup_root is not None and not backup_root.is_dir():
        print(f"[warn] deps 备份目录不存在: {backup_root}（将只打源码包）")
        backup_root = None
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    platforms = [s.strip() for s in args.platforms.split(",") if s.strip()]

    index: Dict[str, dict] = {}
    built = 0
    total_bytes = 0

    for plugin_dir in sorted(PLUGINS_DIR.iterdir()):
        if not plugin_dir.is_dir() or plugin_dir.name.startswith("."):
            continue
        if only and plugin_dir.name not in only:
            continue
        manifest = read_manifest(plugin_dir)
        if manifest is None:
            continue
        name = manifest.get("name") or plugin_dir.name
        version = str(manifest.get("version") or "0.0.0")
        deps_dir, deps_src = resolve_deps_dir(plugin_dir, backup_root)
        declared = (manifest.get("dependencies") or {}).get("pip") or {}

        entry: Dict[str, object] = {}
        if deps_dir is not None and has_platform_dirs(deps_dir):
            # 按平台分包：包内只保留目标平台子目录
            present = {p for p in PLATFORMS if (deps_dir / p).is_dir()}
            wanted = [p for p in platforms if p in present]
            for plat in wanted:
                fname = f"{name}-{version}-{plat}.tar.gz"
                sha, size = build_tarball(plugin_dir, deps_dir, out_dir / fname, keep_platforms={plat})
                entry[plat] = {
                    "url": release_url(name, version, fname),
                    "sha256": sha,
                    "size": size,
                }
                built += 1
                total_bytes += size
                print(f"  {fname:56s} {size/1048576:7.2f} MB")
        else:
            fname = f"{name}-{version}-all.tar.gz"
            sha, size = build_tarball(plugin_dir, deps_dir, out_dir / fname, keep_platforms=None)
            entry["default"] = {
                "url": release_url(name, version, fname),
                "sha256": sha,
                "size": size,
            }
            built += 1
            total_bytes += size
            print(f"  {fname:56s} {size/1048576:7.2f} MB")

        if declared and deps_dir is None:
            print(f"  [warn] {name} 声明了 pip 依赖但无 vendored deps：包内不含依赖，安装端需自行补装")
        elif deps_dir is not None:
            print(f"  [{deps_src}] {name} deps={deps_dir}")
        index[name] = {"version": version, "tarball": entry}

    index_path = out_dir / "tarball_index.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repo": REPO_URL,
        "plugins": index,
    }
    index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n构建完成：{built} 个包，共 {total_bytes/1048576:.1f} MB")
    print(f"索引：{index_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
