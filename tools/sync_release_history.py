#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_release_history.py — 把 GitHub Releases 上已发布的插件包拉回本地 dist/<name>/ 归档

背景：历史版本的权威存储是 GitHub Releases（每插件 × 每版本一个 release，
tag 形如 plugin-<name>-v<version>，产物不可变）。CI 构建的产物不回流本地，
本脚本把全部历史包拉回本地，形成 dist/<name>/ 完整归档。

幂等：同名文件已存在即跳过（产物不可变 ⇒ 同名必同内容）。

用法：
    python tools/sync_release_history.py --dry-run          # 只列清单不下载
    python tools/sync_release_history.py --only see-now     # 只同步指定插件
    python tools/sync_release_history.py                    # 全量同步

鉴权：复用 publish_plugin_tarballs.parse_remote()（origin remote 里的 token 或
      GITHUB_TOKEN 环境变量）。无 token 时匿名访问公开 release（60 次/小时限流）。
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from publish_plugin_tarballs import DIST_DIR, api, parse_remote  # noqa: E402

TAG_RE = re.compile(r"^plugin-(?P<name>.+)-v(?P<ver>[0-9][0-9A-Za-z.+\-]*)$")


def list_releases(owner: str, repo: str, token: str) -> list:
    """分页拉全部 release（每页 100，返回空页即止）"""
    out = []
    page = 1
    while True:
        status, data = api(
            "GET",
            f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=100&page={page}",
            token,
        )
        if status != 200 or not data:
            break
        out.extend(data)
        if len(data) < 100:
            break
        page += 1
    return out


def download(url: str, dest: Path, token: str) -> str:
    """下载 asset 到 dest（.part 暂存防半包），返回本地 sha256"""
    headers = {"User-Agent": "DriFox-plugin-sync"}
    if token:
        headers["Authorization"] = f"token {token}"
    req = urllib.request.Request(url, headers=headers)
    sha = hashlib.sha256()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(req, timeout=300) as resp, open(tmp, "wb") as fh:
        for chunk in iter(lambda: resp.read(1024 * 1024), b""):
            fh.write(chunk)
            sha.update(chunk)
    tmp.rename(dest)
    return sha.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="拉取 GitHub Releases 历史包到 dist/<name>/")
    ap.add_argument("--only", default="", help="只同步指定插件（逗号分隔）")
    ap.add_argument("--dry-run", action="store_true", help="只列清单，不下载")
    args = ap.parse_args()
    only = {s.strip() for s in args.only.split(",") if s.strip()}

    owner, repo, token = parse_remote()
    print(f"仓库: {owner}/{repo} | token: {'有' if token else '无（匿名，限流 60 次/小时）'}")

    releases = list_releases(owner, repo, token)
    planned = done = skipped = failed = 0
    failures = []
    for rel in releases:
        tag = str(rel.get("tag_name") or "")
        m = TAG_RE.match(tag)
        if not m:
            continue
        name = m.group("name")
        if only and name not in only:
            continue
        assets = rel.get("assets") or []
        if not assets:
            print(f"  [skip] {tag}: 无 asset")
            continue
        print(f"\n{tag}（{len(assets)} 个包）")
        for asset in assets:
            fname = str(asset.get("name") or "")
            dest = DIST_DIR / name / fname
            planned += 1
            if dest.is_file():
                skipped += 1
                print(f"    [skip] 已存在: {dest}")
                continue
            if args.dry_run:
                print(f"    [plan] {fname}  {asset.get('size', 0)/1048576:.2f} MB")
                continue
            url = str(asset.get("browser_download_url") or "")
            if not url:
                failed += 1
                failures.append(f"{tag}/{fname}: 缺 browser_download_url")
                continue
            digest = str(asset.get("digest") or "")
            try:
                local_sha = download(url, dest, token)
            except Exception as e:  # noqa: BLE001 - 单包失败不中断整体
                failed += 1
                failures.append(f"{tag}/{fname}: {e}")
                continue
            if digest.startswith("sha256:") and local_sha != digest.split(":", 1)[1]:
                dest.unlink(missing_ok=True)
                failed += 1
                failures.append(f"{tag}/{fname}: sha256 不符（已删除坏包）")
                continue
            done += 1
            print(f"    [done] {fname}  {dest.stat().st_size/1048576:.2f} MB")
    if args.dry_run:
        print(f"\n计划：{planned} 个包（已存在 {skipped}）")
    else:
        print(f"\n同步完成：新增 {done}，跳过 {skipped}，失败 {failed}")
    if failures:
        print("\n失败清单：")
        for item in failures:
            print(f"  - {item}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
