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
import shutil
import subprocess
import sys
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = REPO_ROOT / "plugins"
DEFAULT_OUT = REPO_ROOT / "dist"
DEFAULT_DEPS_BACKUP = Path(r"D:/work/_drifox_plugins_backup/20261105/deps")

def _infer_repo_url() -> str:
    """推导 release 下载基址。fork CI 里自动指向 fork 仓库，用户分支发布的
    tarball URL 天然落在 fork 自己的 Release；本地/官方仓库回退官方地址。

    优先级：GITHUB_REPOSITORY 环境变量 > git origin remote > 官方仓库。
    """
    import os
    import re
    import subprocess

    official = "https://github.com/martin98-afk/drifox-plugins"
    repo = (os.environ.get("GITHUB_REPOSITORY") or "").strip()
    server = (os.environ.get("GITHUB_SERVER_URL") or "https://github.com").rstrip("/")
    if repo and re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        return f"{server}/{repo}"
    try:
        url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"], cwd=REPO_ROOT, text=True
        ).strip()
        m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", url)
        if m:
            return f"https://github.com/{m.group(1)}/{m.group(2)}"
    except subprocess.SubprocessError:
        pass
    return official


REPO_URL = _infer_repo_url()
RELEASE_TAG_PREFIX = "plugin-"  # release tag 约定：plugin-<name>-v<version>

PLATFORMS = ("win32", "darwin", "linux")
# 包内不需要的东西（开发产物/缓存）
EXCLUDE_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}

# ── pip 跨平台拉取（CI 无本地 deps 时的依赖来源）──
# 目标 Python 与 ABI：与宿主运行时对齐（3.14 / cp314）；abi3/none 覆盖
# 稳定 ABI 包与纯 Python 包
PIP_PY_VERSION = "3.14"
PIP_ABIS = ("cp314", "abi3", "none")
# 包内平台名 → pip --platform 候选（逐个尝试，首个能拉全的生效）。
# darwin 优先 universal2（一份包盖 Intel/ARM，避免同名 .so 冲突），回退 arm64
#        （Apple Silicon 为主；Intel mac 因二进制同名无法与 arm64 共存一包）。
# linux 从新到旧：现代 wheel 普遍标 manylinux_2_28/2_27（如 Pillow 13），
#        老包才用 manylinux2014(=2_17)。
PIP_PLATFORM_TAGS = {
    "win32": ["win_amd64"],
    "darwin": ["macosx_11_0_universal2", "macosx_11_0_arm64"],
    "linux": [
        "manylinux_2_28_x86_64",
        "manylinux_2_27_x86_64",
        "manylinux2014_x86_64",
        "manylinux_2_17_x86_64",
    ],
}


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


def _pip_download(
    specs: List[str],
    wheel_dir: Path,
    plat_tags: List[str],
    index_url: str,
    pip_python: str,
    *,
    only_binary: bool = True,
    no_deps: bool = False,
) -> subprocess.CompletedProcess:
    """跑一次 pip download；plat_tags 为空表示不限平台（sdist 兜底用）"""
    cmd = [
        pip_python,
        "-m",
        "pip",
        "download",
        "--dest",
        str(wheel_dir),
        "--only-binary=:all:" if only_binary else "--no-binary=:all:",
    ]
    if no_deps:
        cmd.append("--no-deps")
    if only_binary:
        # wheel 拉取必须始终指定目标 Python/ABI：不指定会按**本机**解释器
        # 版本解析（CI 上 python 3.12 → 拉到 cp312 wheel，宿主 3.14 装不了）
        cmd += ["--python-version", PIP_PY_VERSION, "--implementation", "cp"]
        for abi in PIP_ABIS:
            cmd += ["--abi", abi]
        for tag in plat_tags:
            cmd += ["--platform", tag]
    if index_url:
        cmd += ["--index-url", index_url]
    cmd += specs
    return subprocess.run(cmd, capture_output=True, text=True, timeout=900)



def _extract_wheels(wheel_dir: Path, target: Path) -> int:
    """把目录里的 wheel 全部解压到 target，返回解压个数"""
    count = 0
    for whl in sorted(wheel_dir.glob("*.whl")):
        try:
            with zipfile.ZipFile(whl) as zf:
                zf.extractall(target)
            count += 1
        except Exception as e:
            print(f"  [warn] wheel 解压失败 {whl.name}: {e}")
    return count


def fetch_deps_via_pip(
    manifest: dict,
    platforms: List[str],
    work_root: Path,
    index_url: str = "",
    pip_python: str = "",
) -> Dict[str, Path]:
    """按 manifest 的 dependencies.pip 用 pip download 拉各平台 wheel 并解压

    CI 环境（无本地 vendored deps、无备份）依赖此通道产出完整包。
    每个平台单独拉取，避免跨平台同名 .so 覆盖；平台标签逐级回退
    （darwin: universal2 → arm64）。

    Returns:
        ({平台名或 "all": deps 目录}, {平台名: [缺失 spec]})；
        无依赖声明/全部拉取失败时 deps 字典为空。
    """
    pip_decl = (manifest.get("dependencies") or {}).get("pip") or {}
    missing_by_plat: Dict[str, List[str]] = {}
    if not isinstance(pip_decl, dict):
        return {}, missing_by_plat
    default_specs = [str(s) for s in (pip_decl.get("default") or []) if s]
    plat_specs: Dict[str, List[str]] = {
        p: [str(s) for s in (pip_decl.get(p) or []) if s] for p in PLATFORMS
    }
    if not default_specs and not any(plat_specs.values()):
        return {}, missing_by_plat

    python_cmd = pip_python or sys.executable
    result: Dict[str, Path] = {}
    # 逐平台拉取（default + 该平台专属）：绝不能产「无平台」包——那会落到
    # CI 机器自己的平台/Python 版本（实测 linux cp312 的 .so 发给了 Windows 用户）
    for plat in platforms:
        specs = default_specs + plat_specs.get(plat, [])
        if not specs:
            continue

        dest = work_root / plat
        shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True, exist_ok=True)
        tags = PIP_PLATFORM_TAGS.get(plat) or [""]
        # 1) 整批拉取（保留 pip 的依赖解析），tag 逐级回退
        ok = False
        for tag in tags:
            wheel_dir = work_root / f"{plat}_wheels"
            shutil.rmtree(wheel_dir, ignore_errors=True)
            wheel_dir.mkdir(parents=True, exist_ok=True)
            proc = _pip_download(
                specs, wheel_dir, [tag] if tag else [], index_url, python_cmd
            )
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or "").strip().splitlines()
                print(f"  [info] 整批拉取失败 {plat}@{tag or 'any'}: {err[-1] if err else ''}")
                continue
            if _extract_wheels(wheel_dir, dest) == 0:
                continue
            ok = True
            break

        # 2) 整批失败 → 逐包兜底（wheel 多 tag → 纯 Python sdist）
        #    原因：部分包只有 sdist（qrcode-terminal），或某 tag 下无 wheel
        #    （PyYAML 无 universal2）。逐包 --no-deps：manifest 已列全传递依赖。
        if not ok:
            missing: List[str] = []
            for spec in specs:
                if not _fetch_single(spec, dest, tags, index_url, python_cmd):
                    missing.append(spec)
            if missing:
                missing_by_plat[plat] = missing
                print(f"  [warn] {plat} 缺失依赖（包内不含）: {', '.join(missing)}")
            ok = any(dest.iterdir())

        if ok:
            result[plat] = dest
        else:
            missing_by_plat.setdefault(plat, []).append("(整平台拉取失败)")
            print(f"  [warn] {plat} 平台依赖拉取失败，该平台不出包")

    # 纯 Python 去重：全平台均无二进制扩展 → 三份内容等价，合并为一个
    # "default" 包（客户端 _preferred_sources 优先按平台键取，回退 default）
    if len(result) == len(platforms) and len(platforms) > 1:
        if not any(_has_binary_ext(d) for d in result.values()):
            keep = result[platforms[0]]
            for p in platforms[1:]:
                shutil.rmtree(result.get(p, Path()), ignore_errors=True)
            print("  [pip] 全平台纯 Python → 合并为 default 单包")
            return {"default": keep}, missing_by_plat

    return result, missing_by_plat


def _has_binary_ext(root: Path) -> bool:
    """目录内是否存在平台相关的二进制扩展（有 → 不能跨平台复用）"""
    try:
        for p in root.rglob("*"):
            if p.is_file() and p.suffix.lower() in (".so", ".pyd", ".dll", ".dylib"):
                return True
    except OSError:
        return True
    return False


def _extract_sdist(arc: Path, target: Path) -> bool:
    """解压纯 Python sdist 并提取包目录；含 C 扩展源码则放弃（跨平台不可用）"""
    try:
        with tarfile.open(arc) as tf:
            names = tf.getnames()
            if any(n.endswith((".c", ".cc", ".cpp", ".pyx", ".h")) for n in names):
                print(f"  [info] sdist 含需编译源码，跳过: {arc.name}")
                return False
            tmp = target.parent / f"_sdist_{arc.name[: -len('.tar.gz')]}"
            shutil.rmtree(tmp, ignore_errors=True)
            tf.extractall(tmp, filter="data")
    except Exception as e:
        print(f"  [warn] sdist 解压失败 {arc.name}: {e}")
        return False

    roots = [x for x in tmp.iterdir() if x.is_dir()]
    if not roots:
        return False
    got = False
    for cand in roots[0].iterdir():
        if cand.is_dir() and (cand / "__init__.py").exists():
            shutil.copytree(cand, target / cand.name, dirs_exist_ok=True)
            got = True
        elif cand.is_file() and cand.suffix == ".py" and cand.name not in ("setup.py", "conftest.py"):
            shutil.copy2(cand, target / cand.name)
            got = True
    return got


def _fetch_single(spec: str, dest: Path, tags: List[str], index_url: str, pip_python: str) -> bool:
    """单包兜底：wheel（多 tag 尝试）→ 纯 Python sdist"""
    for tag in tags or [""]:
        wd = dest.parent / "_single_wheels"
        shutil.rmtree(wd, ignore_errors=True)
        wd.mkdir(parents=True, exist_ok=True)
        proc = _pip_download([spec], wd, [tag] if tag else [], index_url, pip_python, no_deps=True)
        if proc.returncode == 0 and _extract_wheels(wd, dest) > 0:
            return True
    sd = dest.parent / "_single_sdist"
    shutil.rmtree(sd, ignore_errors=True)
    sd.mkdir(parents=True, exist_ok=True)
    proc = _pip_download([spec], sd, [], index_url, pip_python, only_binary=False, no_deps=True)
    if proc.returncode == 0:
        for arc in list(sd.glob("*.tar.gz")) + list(sd.glob("*.tgz")):
            if _extract_sdist(arc, dest):
                return True
    return False


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


def _run_smoke_checks(
    name: str, entry: Dict[str, dict], out_dir: Path
) -> Tuple[Dict[str, dict], List[str]]:
    """对已构建的包做发布前冒烟检查，返回 (通过的 entry, 失败说明列表)。

    失败的包从 entry 里剔除：宁可不发，也不能把装不上的包推到市场
    （2026-11 bili-scroll 事故：包名写错导致三平台 tarball 全是坏包）。
    """
    if not entry:
        return entry, []
    try:
        from smoke_check_tarball import smoke_check
    except Exception as e:  # noqa: BLE001 - 工具缺失不应阻断构建
        print(f"  [warn] {name} 冒烟模块导入失败（跳过检查）: {e}")
        return entry, []

    kept: Dict[str, dict] = {}
    failures: List[str] = []
    for plat, meta in entry.items():
        fname = str(meta.get("url") or "").rsplit("/", 1)[-1]
        tar_path = out_dir / fname
        ok, errors, warnings = smoke_check(tar_path)
        for w in warnings:
            print(f"  [smoke warn] {name} {plat}: {w}")
        if ok:
            kept[plat] = meta
        else:
            for e in errors:
                print(f"  [smoke err] {name} {plat}: {e}")
            failures.append(f"{name}/{plat} 冒烟未通过（{errors[0] if errors else '未知'}）")
    return kept, failures


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
    ap.add_argument(
        "--deps-source",
        default="auto",
        choices=["auto", "local", "pip"],
        help="deps 来源：auto=本地>备份>pip，local=仅本地/备份，pip=强制 pip 拉取（CI 用）",
    )
    ap.add_argument("--index-url", default="", help="pip 索引源（CI/国内镜像，留空用 pip 默认）")
    ap.add_argument("--pip-python", default="", help="带 pip 的 Python 解释器（默认 sys.executable）")
    ap.add_argument("--pip-work", default="", help="pip 拉取临时目录（默认 <out>/.deps）")
    ap.add_argument(
        "--strict-deps",
        action="store_true",
        help="严格模式：任一插件缺依赖/无包即整体失败（CI 用，宁可不发也不发残缺包）",
    )
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
    strict_failures: List[str] = []

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

        # pip 通道：CI 无本地 deps 时的依赖来源；--deps-source pip 强制走
        use_pip = bool(declared) and (
            args.deps_source == "pip" or (args.deps_source == "auto" and deps_dir is None)
        )
        if use_pip:
            pip_root = Path(args.pip_work) if args.pip_work else out_dir / ".deps"
            pip_deps, pip_missing = fetch_deps_via_pip(
                manifest,
                platforms,
                pip_root / name,
                index_url=args.index_url,
                pip_python=args.pip_python,
            )
            if args.strict_deps and pip_missing:
                detail = "; ".join(
                    f"{plat}: {', '.join(specs)}" for plat, specs in sorted(pip_missing.items())
                )
                strict_failures.append(f"{name} 缺依赖（{detail}）")
            if pip_deps:
                for plat, d in sorted(pip_deps.items()):
                    suffix = "default" if plat == "default" else plat
                    fname = f"{name}-{version}-{suffix}.tar.gz"
                    sha, size = build_tarball(plugin_dir, d, out_dir / fname, keep_platforms=None)
                    entry[suffix] = {
                        "url": release_url(name, version, fname),
                        "sha256": sha,
                        "size": size,
                    }
                    built += 1
                    total_bytes += size
                    print(f"  {fname:56s} {size/1048576:7.2f} MB")
                print(f"  [pip] {name} 依赖由 pip 跳平台拉取（{', '.join(sorted(pip_deps))}）")
                entry, smoke_fail = _run_smoke_checks(name, entry, out_dir)
                strict_failures.extend(smoke_fail)
                if entry:
                    index[name] = {"version": version, "tarball": entry}
                else:
                    print(f"  [strict] {name} 全部包未通过冒烟检查，跳过发布")
                continue
            print(f"  [warn] {name} pip 拉取失败，回退本地/备份/源码包")
            if args.strict_deps:
                strict_failures.append(f"{name} pip 依赖全部拉取失败")

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
            if args.strict_deps:
                strict_failures.append(f"{name} 声明依赖但无任何 deps 来源")
        elif deps_dir is not None:
            print(f"  [{deps_src}] {name} deps={deps_dir}")
        entry, smoke_fail = _run_smoke_checks(name, entry, out_dir)
        strict_failures.extend(smoke_fail)
        if entry:
            index[name] = {"version": version, "tarball": entry}
        else:
            print(f"  [strict] {name} 全部包未通过冒烟检查，跳过发布")

    index_path = out_dir / "tarball_index.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repo": REPO_URL,
        "plugins": index,
    }
    index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n构建完成：{built} 个包，共 {total_bytes/1048576:.1f} MB")
    print(f"索引：{index_path}")
    if strict_failures:
        print("\n[strict] 构建失败（宁可不发也不发残缺包）：")
        for item in strict_failures:
            print(f"  - {item}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
