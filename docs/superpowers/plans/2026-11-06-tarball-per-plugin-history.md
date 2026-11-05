# dist 按插件分组 + Releases 历史同步 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** dist/ 构建产物按插件分子目录存放，并提供从 GitHub Releases 拉取全部历史包的同步脚本。

**Architecture:** 纯本地构建布局变更（dist/<name>/<file>.tar.gz），索引 tarball_index.json 位置结构不变，CI 与 generate_marketplace.py 零改动；新增 tools/sync_release_history.py 复用 publish 的鉴权与 API 封装拉取历史包到 dist/<name>/。

**Tech Stack:** Python 3 stdlib（urllib/argparse/hashlib/pathlib），GitHub REST API。

**Spec:** `docs/superpowers/specs/2026-11-06-tarball-per-plugin-history-design.md`

**执行环境说明：** 本仓库惯例直接在 main 工作（无 worktree 流程）；所有脚本为 stdlib，系统 python 可跑；Windows bash 工具不支持 head/grep，验证命令一律用 python -X utf8 -c。

**重要前提（做每个 task 前都知道）：**
- 本地跑 build 会把 dist/tarball_index.json 重写为「只含本次构建插件」——这与 CI 行为一致，generate_marketplace 有旧清单回退保护，属预期，不是事故。
- 权威产物在 GitHub Releases 且不可变，本地 dist 任何文件都可由 sync 重新拉回，删除安全。
- CI 触发：push 到 main 且 paths 含 tools/** 会跑 release-plugins.yml，detect 无版本变更时只打印「无插件版本变更」后跳过，无副作用。

---

### Task 1: build_plugin_tarballs.py 产物路径分组

**Files:**
- Modify: `tools/build_plugin_tarballs.py:11-12`（头注释路径示例）
- Modify: `tools/build_plugin_tarballs.py:353`（_run_smoke_checks 内 tar_path）
- Modify: `tools/build_plugin_tarballs.py:492`（pip 通道 build_tarball 调用）
- Modify: `tools/build_plugin_tarballs.py:519`（平台分包 build_tarball 调用）
- Modify: `tools/build_plugin_tarballs.py:529`（all 包 build_tarball 调用）

- [ ] **Step 1: 记录改动前基线（不跑 build，避免覆盖现有完整索引）**

Run:
```
python -X utf8 -c "import json,hashlib; p='dist/anthropic-1.0.0-all.tar.gz'; h=hashlib.sha256(open(p,'rb').read()).hexdigest(); idx=json.load(open('dist/tarball_index.json',encoding='utf-8'))['plugins']['anthropic']; print('file_sha256:',h); print('index:',json.dumps(idx))"
```
Expected: 打印 file_sha256 与 index 条目（url/sha256/size），把这两个值记下来（后续比对）。anthropic 源码近期无变动（git log 仅 desktop-automation），sha 应具备确定性可比性。

- [ ] **Step 2: 修改头注释路径示例（11-12 行）**

原文：
```python
#   dist/<name>-<version>-<platform>.tar.gz      单平台包（含该平台 deps）
#   dist/<name>-<version>-all.tar.gz             无平台差异的插件（纯源码或无平台 deps）
```
改为：
```python
#   dist/<name>/<name>-<version>-<platform>.tar.gz   单平台包（含该平台 deps）
#   dist/<name>/<name>-<version>-all.tar.gz          无平台差异的插件（纯源码或无平台 deps）
```

- [ ] **Step 3: 修改 _run_smoke_checks 内文件定位（约 353 行）**

原文：
```python
    for plat, meta in entry.items():
        fname = str(meta.get("url") or "").rsplit("/", 1)[-1]
        tar_path = out_dir / fname
```
改为：
```python
    for plat, meta in entry.items():
        fname = str(meta.get("url") or "").rsplit("/", 1)[-1]
        tar_path = out_dir / name / fname
```

- [ ] **Step 4: 修改三处 build_tarball 调用的输出路径**

pip 通道（约 492 行）原文：
```python
                    fname = f"{name}-{version}-{suffix}.tar.gz"
                    sha, size = build_tarball(plugin_dir, d, out_dir / fname, keep_platforms=None)
```
改为：
```python
                    fname = f"{name}-{version}-{suffix}.tar.gz"
                    sha, size = build_tarball(plugin_dir, d, out_dir / name / fname, keep_platforms=None)
```

平台分包（约 519 行）原文：
```python
                fname = f"{name}-{version}-{plat}.tar.gz"
                sha, size = build_tarball(plugin_dir, deps_dir, out_dir / fname, keep_platforms={plat})
```
改为：
```python
                fname = f"{name}-{version}-{plat}.tar.gz"
                sha, size = build_tarball(plugin_dir, deps_dir, out_dir / name / fname, keep_platforms={plat})
```

all 包（约 529 行）原文：
```python
            fname = f"{name}-{version}-all.tar.gz"
            sha, size = build_tarball(plugin_dir, deps_dir, out_dir / fname, keep_platforms=None)
```
改为：
```python
            fname = f"{name}-{version}-all.tar.gz"
            sha, size = build_tarball(plugin_dir, deps_dir, out_dir / name / fname, keep_platforms=None)
```

- [ ] **Step 5: 构建单插件验证（选无依赖小插件 anthropic，秒级完成）**

Run:
```
python tools/build_plugin_tarballs.py --only anthropic
```
Expected: 输出包含 `dist\anthropic\anthropic-1.0.0-all.tar.gz` 路径与 `索引：...dist\tarball_index.json`，无 smoke 错误。

- [ ] **Step 6: 验证产物落子目录 + sha 与基线一致**

Run:
```
python -X utf8 -c "import json,hashlib,os; p='dist/anthropic/anthropic-1.0.0-all.tar.gz'; print('exists:',os.path.isfile(p)); print('flat_gone:',not os.path.isfile('dist/anthropic-1.0.0-all.tar.gz')); print('sha256:',hashlib.sha256(open(p,'rb').read()).hexdigest()); idx=json.load(open('dist/tarball_index.json',encoding='utf-8'))['plugins']; print('index_keys:',list(idx)); print('entry:',json.dumps(idx['anthropic']))"
```
Expected:
- exists: True；flat_gone: True（子目录有新文件，旧平铺文件仍在 dist 根属预期，Task 4 清理）
- sha256 与 Step 1 的基线一致（gzip mtime=0 确定性构建；不一致先 `git log --oneline -3 -- plugins/anthropic` 确认源码无变动，再排查构建）
- index_keys: ['anthropic']（索引只含本次构建插件，预期）；entry 的 url 与基线相同

- [ ] **Step 7: 语法检查**

Run: `python -X utf8 -c "import ast; ast.parse(open('tools/build_plugin_tarballs.py',encoding='utf-8').read()); print('syntax OK')"`
Expected: syntax OK

- [ ] **Step 8: Commit**

```bash
git add tools/build_plugin_tarballs.py
git commit -m "build(tarball): 产物按插件分子目录 dist/<name>/，索引结构不变"
```

---

### Task 2: publish_plugin_tarballs.py 路径适配 + api 空头兼容

**Files:**
- Modify: `tools/publish_plugin_tarballs.py:4-6`（头注释）
- Modify: `tools/publish_plugin_tarballs.py:27-30`（api headers）
- Modify: `tools/publish_plugin_tarballs.py:177`（fpath 拼接）

- [ ] **Step 1: 修改头注释（第 4-6 行）**

原文：
```python
publish_plugin_tarballs.py — 把 dist/ 里的插件包发布到 GitHub Releases

前置：先跑 tools/build_plugin_tarballs.py 生成 dist/ 与 tarball_index.json。
```
改为：
```python
publish_plugin_tarballs.py — 把 dist/ 里的插件包发布到 GitHub Releases

前置：先跑 tools/build_plugin_tarballs.py 生成 dist/<name>/ 与 tarball_index.json。
```

- [ ] **Step 2: api() 空 token 时不带 Authorization 头（27-30 行）**

背景：sync 脚本匿名拉公开 release 时 token 为空串，GitHub 对空 Authorization 头返回 401。
publish 自身无行为变化（main 里空 token 已提前拦截）。

原文：
```python
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "DriFox-plugin-publisher",
    }
```
改为：
```python
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "DriFox-plugin-publisher",
    }
    if token:
        headers["Authorization"] = f"token {token}"
```

- [ ] **Step 3: 修改 fpath 拼接（约 177 行）**

原文：
```python
        for plat, meta in assets.items():
            url = str(meta.get("url") or "")
            fname = url.rsplit("/", 1)[-1]
            fpath = DIST_DIR / fname
```
改为：
```python
        for plat, meta in assets.items():
            url = str(meta.get("url") or "")
            fname = url.rsplit("/", 1)[-1]
            fpath = DIST_DIR / name / fname
```

- [ ] **Step 4: dry-run 验证（此时索引只含 anthropic）**

Run:
```
python tools/publish_plugin_tarballs.py --dry-run
```
Expected: 打印 `仓库: martin98-afk/drifox-plugins`、`anthropic v1.0.0 → tag plugin-anthropic-v1.0.0（1 个包）`，文件行显示 `dist\anthropic\anthropic-1.0.0-all.tar.gz  0.00 MB` 级别的子目录路径，无 `[skip] 缺文件`。

- [ ] **Step 5: 语法检查**

Run: `python -X utf8 -c "import ast; ast.parse(open('tools/publish_plugin_tarballs.py',encoding='utf-8').read()); print('syntax OK')"`
Expected: syntax OK

- [ ] **Step 6: Commit**

```bash
git add tools/publish_plugin_tarballs.py
git commit -m "publish(tarball): 按 dist/<name>/ 子目录定位包，api 空 token 不带认证头"
```

---

### Task 3: 新增 sync_release_history.py

**Files:**
- Create: `tools/sync_release_history.py`

- [ ] **Step 1: 写入完整脚本**

```python
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
```

- [ ] **Step 2: dry-run 小范围验证（单插件）**

Run:
```
python tools/sync_release_history.py --only anthropic --dry-run
```
Expected: 打印 `仓库: martin98-afk/drifox-plugins`、`plugin-anthropic-v1.0.0（1 个包）`、`[skip] 已存在: dist\anthropic\anthropic-1.0.0-all.tar.gz`（Task 1 已构建该文件）、`计划：1 个包（已存在 1）`。

- [ ] **Step 3: dry-run 全量看清单规模**

Run:
```
python tools/sync_release_history.py --dry-run | python -X utf8 -c "import sys; d=sys.stdin.read(); lines=d.splitlines(); print('总行数:',len(lines)); print(chr(10).join(lines[-3:]))"
```
Expected: 末尾打印 `计划：N 个包（已存在 M）`，N 为全部已发布 asset 总数（约 200+），无 API 报错。

- [ ] **Step 4: 实跑单插件下载验证**

Run:
```
python tools/sync_release_history.py --only anthropic
```
Expected: `同步完成：新增 0，跳过 1，失败 0`（文件已在，验证幂等跳过路径）。

- [ ] **Step 5: 换一个本地没有的插件实跑，验证下载 + digest 校验路径**

Run:
```
python tools/sync_release_history.py --only desktop-automation
```
Expected: 下载 plugin-desktop-automation-v1.0.0 至 v1.0.4 的所有 asset 到 `dist/desktop-automation/`，逐个 `[done]`，`失败 0`。再重跑同命令，Expected 全部 `[skip] 已存在`（幂等验证）。

- [ ] **Step 6: 语法检查**

Run: `python -X utf8 -c "import ast; ast.parse(open('tools/sync_release_history.py',encoding='utf-8').read()); print('syntax OK')"`
Expected: syntax OK

- [ ] **Step 7: Commit**

```bash
git add tools/sync_release_history.py
git commit -m "feat(tools): sync_release_history 拉取 Releases 全量历史包到 dist/<name>/"
```

---

### Task 4: generate 回退验证 + 清理旧平铺文件 + 全量归档（操作步骤，无代码改动）

**Files:** 无代码文件改动；操作对象 dist/

- [ ] **Step 1: generate_marketplace 无 diff 验证（确认回退保护工作）**

Run:
```
python tools/generate_marketplace.py
git status --porcelain marketplace.json
```
Expected: generate 正常退出；marketplace.json 无 diff（anthropic 同版本走 KEEP/等值覆盖，其余插件全走旧清单回退）。若出现 diff，停止并核对 diff 内容是否仅为 anthropic 的等值字段。

- [ ] **Step 2: 全量归档（可选，量大，先征询用户）**

确认项：全量下载约 200+ 插件全部历史包（体积数百 MB、耗时数十分钟）。用户同意后：
```
python tools/sync_release_history.py
```
Expected: `失败 0`（个别失败看失败清单，重跑补齐）。

- [ ] **Step 3: 清理旧平铺文件（破坏性操作，展示清单后经用户确认再删）**

Run:
```
python -X utf8 -c "import os,glob; fs=[f for f in glob.glob('dist/*.tar.gz')]; print(len(fs),'个'); print(chr(10).join(fs[:5]),'...')"
```
用户确认后执行：
```
python -X utf8 -c "import glob,os; [os.remove(f) for f in glob.glob('dist/*.tar.gz')]; print('cleaned')"
```
Expected: dist 根只剩 tarball_index.json 与各插件子目录。

- [ ] **Step 4: 终态核验**

Run:
```
python -X utf8 -c "import os; d='dist'; subs=[x for x in os.listdir(d) if os.path.isdir(os.path.join(d,x))]; roots=[x for x in os.listdir(d) if os.path.isfile(os.path.join(d,x))]; print('子目录数:',len(subs)); print('根文件:',roots)"
```
Expected: 根文件仅 `['tarball_index.json']`。

---

## Self-Review 结论

- **Spec 覆盖**：spec「改动清单」1-3 全部落到 Task 1-3；验证方案 5 条分别落 Task 1 Step 5-6、Task 2 Step 4、Task 3 Step 2-5、Task 4 Step 1、release-plugins.yml 观察归入 push 后动作（Task 4 之后由用户决定何时 push）。无缺口。
- **占位符**：无 TBD/TODO；所有代码步骤含完整代码与精确行号。
- **类型一致性**：sync 引用的 `DIST_DIR/api/parse_remote` 与 publish 内定义签名一致（parse_remote()->Tuple[str,str,str]，api(method,url,token)->(status,payload)）；`TAG_RE` 命名与用法一致。
