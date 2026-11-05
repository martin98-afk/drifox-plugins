#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
publish_plugin_tarballs.py — 把 dist/ 里的插件包发布到 GitHub Releases

前置：先跑 tools/build_plugin_tarballs.py 生成 dist/ 与 tarball_index.json。

发布模型（每插件一个 release，独立版本节奏）：
    tag:  plugin-<name>-v<version>
    asset: <name>-<version>-<platform>.tar.gz
客户端按 marketplace.json 的 tarball 字段直链下载该 asset（sha256 已记录，可校验）。

用法：
    python tools/publish_plugin_tarballs.py --dry-run          # 只打印计划
    python tools/publish_plugin_tarballs.py --only see-now     # 发布单个插件
    python tools/publish_plugin_tarballs.py                    # 全部发布（已存在同名 asset 跳过）

鉴权：从 `git remote get-url origin` 解析 https://user:token@github.com/... 里的 token；
      没有 token（ssh remote）时读环境变量 GITHUB_TOKEN。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = REPO_ROOT / "dist"
INDEX_PATH = DIST_DIR / "tarball_index.json"
API_ROOT = "https://api.github.com"


def parse_remote() -> Tuple[str, str, str]:
    """解析 origin remote → (owner, repo, token)"""
    try:
        url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"], cwd=REPO_ROOT, text=True
        ).strip()
    except subprocess.SubprocessError as e:
        raise SystemExit(f"无法读取 origin remote: {e}")
    m = re.search(r"https://(?:([^:/@]+):)?([^@]+)@github\.com/([^/]+)/([^/]+?)(?:\.git)?$", url)
    if m:
        _user, token, owner, repo = m.groups()
        return owner, repo, token or ""
    m2 = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", url)
    if m2:
        import os

        return m2.group(1), m2.group(2), os.environ.get("GITHUB_TOKEN", "")
    raise SystemExit(f"无法解析 GitHub 仓库: {url}")


def api(method: str, url: str, token: str, data: Optional[dict] = None, raw: Optional[bytes] = None):
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "DriFox-plugin-publisher",
    }
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif raw is not None:
        body = raw
        headers["Content-Type"] = "application/octet-stream"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = resp.read()
        return resp.status, (json.loads(payload) if payload else {})


def ensure_release(owner: str, repo: str, tag: str, name: str, version: str, token: str) -> dict:
    """创建 release；已存在则复用（409）"""
    url = f"{API_ROOT}/repos/{owner}/{repo}/releases"
    payload = {
        "tag_name": tag,
        "name": f"{name} v{version}",
        "body": f"插件 {name} v{version} 分发包（按平台，含依赖）。由 tools/publish_plugin_tarballs.py 发布。",
        "draft": False,
        "prerelease": False,
    }
    try:
        status, data = api("POST", url, token, data=payload)
        if status in (200, 201):
            return data
    except urllib.error.HTTPError as e:
        if e.code == 422:  # release 已存在
            _, data = api("GET", f"{url}/tags/{tag}", token)
            return data
        raise
    raise RuntimeError(f"创建 release 失败: {tag}")


def upload_asset(upload_url: str, file_path: Path, token: str) -> None:
    base = upload_url.split("{", 1)[0]
    url = f"{base}?name={urllib.parse.quote(file_path.name)}"
    api("POST", url, token, raw=file_path.read_bytes())


def main() -> int:
    ap = argparse.ArgumentParser(description="发布插件 tarball 到 GitHub Releases")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不请求 API")
    ap.add_argument("--only", default="", help="只发布指定插件（逗号分隔）")
    ap.add_argument(
        "--replace",
        action="store_true",
        help="同名 asset 已存在时先删除再上传（同版本重打包用）",
    )
    args = ap.parse_args()

    if not INDEX_PATH.is_file():
        print(f"缺少构建索引：{INDEX_PATH}\n先运行 tools/build_plugin_tarballs.py")
        return 2
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8")).get("plugins") or {}
    only = {s.strip() for s in args.only.split(",") if s.strip()}

    owner, repo, token = parse_remote()
    print(f"仓库: {owner}/{repo} | token: {'有' if token else '缺失'}")
    if not args.dry_run and not token:
        print("缺少 token：ssh remote 需设置 GITHUB_TOKEN 环境变量")
        return 2

    planned = 0
    for name, entry in sorted(index.items()):
        if only and name not in only:
            continue
        version = entry.get("version") or "0.0.0"
        tag = f"plugin-{name}-v{version}"
        assets = entry.get("tarball") or {}
        files = []
        for plat, meta in assets.items():
            url = str(meta.get("url") or "")
            fname = url.rsplit("/", 1)[-1]
            fpath = DIST_DIR / fname
            if not fpath.is_file():
                print(f"  [skip] 缺文件: {fpath}")
                continue
            files.append(fpath)
        if not files:
            continue
        print(f"\n{name} v{version} → tag {tag}（{len(files)} 个包）")
        for f in files:
            print(f"    {f.name}  {f.stat().st_size/1048576:.2f} MB")
        planned += len(files)
        if args.dry_run:
            continue
        rel = ensure_release(owner, repo, tag, name, version, token)
        upload_url = rel.get("upload_url") or ""
        if not upload_url:
            print(f"  [skip] 未取得 upload_url（release 可能已存在但无权限）")
            continue
        existing = {a.get("name"): a for a in (rel.get("assets") or [])}
        for f in files:
            old = existing.get(f.name)
            if old is not None:
                if not args.replace:
                    print(f"    [跳过] 已存在: {f.name}")
                    continue
                try:
                    api("DELETE", str(old.get("url") or ""), token)
                    print(f"    [删除] 旧 asset: {f.name}")
                except urllib.error.HTTPError as e:
                    print(f"    [warn] 删除旧 asset 失败 {f.name}: {e}")
                    continue
            upload_asset(upload_url, f, token)
            print(f"    [上传] {f.name}")

    print(f"\n完成：{planned} 个包{'(dry-run)' if args.dry_run else '已处理'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
