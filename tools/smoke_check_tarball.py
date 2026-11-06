#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smoke_check_tarball.py — tarball 发布前冒烟门禁

为什么需要它
------------
2026-11 bili-scroll 事故：manifest 的 pip 依赖写成 `bilibili_api`（2021 年停更的
老包），而业务代码要的是 `bilibili-api-python` 17.x。CI 一路绿灯发布了三平台
tarball，用户装完才发现 `from bilibili_api import login_v2` 直接 ImportError，
插件 UI 与 MCP 控制端点双双挂掉。整个链路缺的正是「发之前验一下」这一步。

为什么是静态检查而不是真实 import
--------------------------------
1. 构建机是 ubuntu + CPython 3.12，而包内是 cp314 的二进制扩展（.so/.pyd），
   import 必然失败 —— 真实 import 在所有含原生扩展的插件上都是假阳性。
2. 插件业务代码普遍 import 宿主模块（loguru/PyQt5/app.*），脱离 DriFox 进程
   根本跑不起来 —— 真实 import 覆盖率接近零。
静态检查只锁定一件确定的事：包内 vendored 依赖里，业务代码用到的子模块是否
真的存在。这正是本次事故的形态。

检查项
------
A. tarball 完整性：能打开、含 .drifox-plugin/plugin.json 且可解析
B. manifest 与包内版本一致
C. 依赖子模块存在性：业务代码 `from X.Y import Z` 中，若 X 是包内依赖，
   则 X/Y/Z.py 或 X/Y/Z/ 必须存在（跨所有 vendored 依赖目录）
D. 声明了 pip 依赖却完全没有 deps 目录 → 警告（安装端需自行补装）

退出码：0 通过 / 1 有问题（调用方据此跳过该插件的发布）
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tarfile
from pathlib import Path
from typing import Iterable, Optional

# 这些目录下的 .py 不参与 C 项检查（依赖自身、缓存、构建产物）
_SKIP_DIR_PARTS = {"__pycache__", ".git", "deps", "vendor", "node_modules"}

# 宿主缺失 stdlib 的 shim 清单（单一事实源，build_plugin_tarballs 引用同一份）：
# 插件名 → 包内必须存在的 deps/ 相对路径锚点。宿主 PyInstaller 打包缺
# xml.dom/optparse（base_library.zip 实测无），插件运行期靠 deps/_pystdlib_xml
# 副本仲裁自愈（pil_arbiter.prefer_vendored_stdlib）。C 项对 stdlib 顶层名豁免，
# 这里反向盯豁免区：清单内插件的包不带 shim = 装上必炸，一票拒绝。
# 宿主补齐 hiddenimports 后清空此表。
STDLIB_SHIM_PLUGINS = {
    "bili-scroll": (
        "_pystdlib_xml/xml/__init__.py",
        "_pystdlib_xml/xml/dom/__init__.py",
        "_pystdlib_xml/xml/dom/minidom.py",
        "_pystdlib_xml/optparse.py",
    ),
}

# 业界有「from 包 import 子模块」但子模块以动态/条件方式提供的场景。
# 命中这些模块时不报错，避免误伤（宁可漏检也不要把好包拦下来）。
_DYNAMIC_MODULE_HINTS = frozenset(
    {
        # 这些包的 __init__ 常做惰性导出，子模块名不落盘
        "PIL",
    }
)


# ── 平台结构验证 ────────────────────────────────────────
# 校验「这个平台的包，里面的二进制确实属于这个平台」。
# 不依赖多平台 runner：.so/.pyd 文件名里带 ABI 与平台标签，静态可判。
#
# 文件名形态（真实样本）：
#   aiohttp/_http_writer.cpython-314-darwin.so
#   PIL/_imaging.cp314-win_amd64.pyd
#   brotli.cpython-314-x86_64-linux-gnu.so
# 注意：文件名**不含 CPU 架构**（mac arm64 与 x86_64 的同名），
# 所以只能验 ABI 版本与操作系统，验不了「arm64 包装了 x86_64」。
_EXT_RE = re.compile(r"\.(cpython-(\d+)-([A-Za-z0-9_\-]+)|cp(\d+)-([A-Za-z0-9_\-]+)|([A-Za-z0-9_\-]+))\.(so|pyd|dylib|dll)$")

# 目标 ABI 版本：与宿主运行时对齐（build_plugin_tarballs.PIP_PY_VERSION）
_TARGET_PY_TAG = "314"

# 平台 → 二进制文件名里应出现的系统标签片段
_PLATFORM_MARKERS = {
    "darwin": ("darwin",),
    "win32": ("win_amd64", "win32", "win_arm64", "cpwin", "pyd"),
    "linux": ("linux",),
}
# 某个系统标签是否属于其它平台（用于交叉污染判定）
_FOREIGN_MARKERS = {
    "darwin": ("linux", "win_amd64", "win32", "win_arm64"),
    "win32": ("darwin", "linux", "manylinux"),
    "linux": ("darwin", "win_amd64", "win32", "win_arm64"),
}


def _parse_ext_tag(filename: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """解析二进制扩展文件名 → (abi_py_tag, platform_tag, ext)。

    解析失败返回 (None, None, ext)。abi_py_tag 是 "314" 形态的短版本号。
    """
    name = filename.rsplit("/", 1)[-1]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else None
    if ext not in ("so", "pyd", "dylib", "dll"):
        return None, None, ext

    # .cpython-314-darwin.so / .cp314-win_amd64.pyd
    m = re.search(r"\.cpython-(\d+)-([A-Za-z0-9_\-]+)\.(?:so|pyd|dylib)$", name)
    if m:
        return m.group(1), m.group(2), ext
    m = re.search(r"\.cp(\d+)-([A-Za-z0-9_\-]+)\.(?:so|pyd|dylib)$", name)
    if m:
        return m.group(1), m.group(2), ext
    # 老式命名 / 无 ABI 标签的 .so（如 libfoo.so、_sqlite3.cpython.so）
    m = re.search(r"\.([A-Za-z0-9_\-]+)\.(?:so|dylib)$", name)
    if m:
        return None, m.group(1), ext
    return None, None, ext


def check_platform_binaries(
    tf: tarfile.TarFile, platform_key: str
) -> tuple[list[str], list[str]]:
    """校验包内二进制是否属于指定平台。返回 (错误, 警告)。

    platform_key 取 "darwin" / "win32" / "linux" / "default"。
    default 表示平台无关（纯 Python 包），此时出现任何二进制都算异常。
    """
    errors: list[str] = []
    warnings: list[str] = []

    binaries = []
    for member in tf.getmembers():
        if not member.isfile():
            continue
        rel = _norm(member.name)
        if "__pycache__" in rel:
            continue
        if rel.rsplit(".", 1)[-1].lower() in ("so", "pyd"):
            binaries.append(rel)

    if not binaries:
        return errors, warnings

    if platform_key == "default":
        errors.append(
            f"标为 default（平台无关）的包内含 {len(binaries)} 个二进制扩展"
            f"（如 {binaries[0]}）—— 应改为按平台分包"
        )
        return errors, warnings

    foreign = _FOREIGN_MARKERS.get(platform_key, ())
    abi_mismatch: list[str] = []
    foreign_hits: list[str] = []
    for rel in binaries:
        abi, plat_tag, _ext = _parse_ext_tag(rel)
        tag_blob = (plat_tag or "").lower()
        if tag_blob and any(f in tag_blob for f in foreign):
            foreign_hits.append(f"{rel}（标签 {plat_tag}）")
        if abi and abi != _TARGET_PY_TAG:
            abi_mismatch.append(f"{rel}（ABI cp{abi}，目标 cp{_TARGET_PY_TAG}）")

    if foreign_hits:
        errors.append(
            f"{len(foreign_hits)} 个扩展属于其它平台，不该出现在 {platform_key} 包内，"
            f"例：{foreign_hits[0]}"
        )
    if abi_mismatch:
        errors.append(
            f"{len(abi_mismatch)} 个扩展的 ABI 与目标 Python 不符，"
            f"例：{abi_mismatch[0]}"
        )

    return errors, warnings


def _norm(name: str) -> str:
    """归一化包内路径：去掉前导 ./ 与 /，统一分隔符。

    build_plugin_tarballs.py 产出的成员名不带 `./`，但用 `tar czf x.tar.gz -C dir .`
    重新打包会带上；两种形态都要能认，否则人工复检的包一律误判。
    """
    n = name.replace("\\", "/")
    while n.startswith("./"):
        n = n[2:]
    return n.lstrip("/")


def _iter_source_members(tf: tarfile.TarFile) -> Iterable[tuple[str, bytes]]:
    """产出插件源码里的 (相对路径, 内容)，跳过 deps/vendor 与缓存"""
    for member in tf.getmembers():
        if not member.isfile() or not member.name.endswith(".py"):
            continue
        rel = _norm(member.name)
        parts = Path(rel).parts
        if any(p in _SKIP_DIR_PARTS for p in parts):
            continue
        fh = tf.extractfile(member)
        if fh is None:
            continue
        yield rel, fh.read()


def _vendored_roots(tf: tarfile.TarFile) -> dict[str, set[str]]:
    """收集包内 vendored 依赖的顶层包名 → 该包的相对路径前缀集合。

    deps/ 与 vendor/ 下都可能塞依赖；<root>/Foo/__init__.py 与
    <root>/Foo.py 都算 Foo 的落点。
    """
    roots: dict[str, set[str]] = {}
    for member in tf.getmembers():
        parts = Path(_norm(member.name)).parts
        if len(parts) < 3 or parts[0] not in ("deps", "vendor"):
            continue
        if "__pycache__" in parts:
            continue
        # deps/Foo/__init__.py → Foo 是包；deps/Foo.py → Foo 是模块
        if len(parts) == 3 and parts[2] == "__init__.py":
            roots.setdefault(parts[1], set()).add("/".join(parts[:2]))
        elif len(parts) == 2 and parts[1].endswith(".py"):
            roots.setdefault(parts[1][:-3], set()).add(parts[0])
    return roots


def _collect_from_imports(source: bytes) -> list[tuple[str, str, int]]:
    """解析源码里的绝对 from-import，产出 (module, name, lineno)"""
    try:
        tree = ast.parse(source.decode("utf-8", errors="replace"))
    except SyntaxError:
        return []
    out: list[tuple[str, str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.level or not node.module:
            continue
        for alias in node.names:
            out.append((node.module, alias.name, node.lineno))
    return out


def _all_member_paths(tf: tarfile.TarFile) -> set[str]:
    return {_norm(m.name) for m in tf.getmembers()}


def _ext_module_names(paths: set[str], base: str) -> set[str]:
    """<base>/ 下的编译扩展模块名（剥掉 ABI/平台标签）。

    lxml.etree、numpy.core._multiarray_umath 等 C 扩展子模块落盘形态是
    etree.cpython-314-darwin.so / _imaging.cp314-win_amd64.pyd，既不是 .py
    也不是包目录；只按 .py 判定会把「扩展确实在包里」误报成缺子模块。
    """
    prefix = base.rstrip("/") + "/"
    out: set[str] = set()
    for path in paths:
        if not path.startswith(prefix):
            continue
        rel = path[len(prefix):]
        if "/" in rel:  # 只看直属这一层
            continue
        m = _EXT_RE.search(rel)
        if m:
            out.add(rel[: m.start()])
    return out


def _module_exists(
    paths: set[str],
    from_import: str,
    name: str,
    roots: set[str],
    init_sources: dict[str, bytes],
) -> bool:
    """from <module> import <name> 在包内是否存在对应落点。

    `roots` 是该顶层包在包内的实际前缀集合（如 {"deps/bilibili_api"}），
    所有候选路径都要带上它 —— 包内成员名是 `deps/bilibili_api/login_v2.py`
    而不是 `bilibili_api/login_v2.py`。

    判定顺序（任一命中即算存在）：
      1. <root>/<module 剩余段>/<name>.py
      2. <root>/<module 剩余段>/<name>/__init__.py
      3. <root>/<module 剩余段>.py（name 是模块级符号）
      4. <root>/<module 剩余段>/__init__.py 里出现 name（重导出）
      5. <root>/<module 剩余段>/ 下有 name 的编译扩展（.so/.pyd/.dylib）

    第 4 条必须做内容级校验，不能只看 __init__.py 存不存在：
    bilibili_api/__init__.py 是存在的，但里面没有 login_v2，那正是本次事故形态。
    重导出的写法 `from .server import Server` 会让 name 字面出现在文件里。
    """
    tail = from_import.split(".", 1)
    rest = tail[1].replace(".", "/") if len(tail) > 1 else ""
    for root in roots:
        base = f"{root}/{rest}" if rest else root
        if f"{base}/{name}.py" in paths:
            return True
        if f"{base}/{name}/__init__.py" in paths:
            return True
        if f"{base}.py" in paths:
            return True
        init_key = f"{base}/__init__.py"
        if init_key in paths:
            body = init_sources.get(init_key, b"")
            if _mentions_symbol(body, name):
                return True
        if name in _ext_module_names(paths, base):
            return True
    return False


def _mentions_symbol(source: bytes, name: str) -> bool:
    """源码里是否导入/定义/列出了 name（重导出、赋值、__all__ 均算）。"""
    try:
        tree = ast.parse(source.decode("utf-8", errors="replace"))
    except SyntaxError:
        # 解析不了就退回文本匹配，宁可放行也别误杀
        return name.encode() in source
    for node in ast.walk(tree):
        # 定义：class Server / def Server / Server = ...
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == name:
                return True
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return True
        # 导入：from .server import Server / from . import Server
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if (alias.asname or alias.name) == name:
                    return True
        # __all__ = ["Server", ...]
        if isinstance(node, ast.Constant) and node.value == name:
            return True
    return False


def _read_member_text(tf: tarfile.TarFile, raw_members: dict, key: str) -> str:
    """读取包内某个文本成员的内容，失败返回空串"""
    member = raw_members.get(key)
    if member is None:
        return ""
    try:
        fh = tf.extractfile(member)
        if fh is None:
            return ""
        return fh.read().decode("utf-8", errors="replace")
    except Exception:
        return ""

def _missing_declared_modules(
    specs: list[str], paths: set[str], read_text
) -> set[str]:
    """检查 manifest 声明的 pip 依赖，其顶层模块是否真的在包内。

    包名与模块名不一致是常态（pyobjc-core → objc，PyYAML → yaml），
    不能靠字符串推断。做法：读包内 dist-info 的 top_level.txt；
    没有该文件时跳过（宁可漏检也不误杀）。
    只检查「包内有对应 dist-info」的依赖 —— dist-info 完全缺失由另一项报告。
    """
    missing: set[str] = set()
    for spec in specs:
        pkg = re.split(r"[<>=!~\[; ]", spec.strip(), maxsplit=1)[0].lower()
        if not pkg:
            continue
        norm = re.sub(r"[-_.]+", "_", pkg)
        tl = [
            p
            for p in paths
            if re.match(
                rf"deps/{re.escape(norm)}-[^/]+\.dist-info/top_level\.txt$", p, re.I
            )
        ]
        if not tl:
            continue  # 无 top_level.txt：跳过，避免误杀
        body = read_text(tl[0]) or ""
        mods = [line.strip() for line in body.splitlines() if line.strip()]
        if not mods:
            continue
        # top_level.txt 可能列出多个顶层名，其中部分是可选的测试/工具包。
        # 典型：pyobjc-core 声明 objc、PyObjCTest、PyObjCTools，但 wheel 只带
        # objc，后两个只存在于源码树（实测第一次跑就误拒了含 objc 的好包）。
        # 判据因此放宽为「至少一个声明模块落盘」—— 说明该依赖确实被打进来了。
        landed = [
            m
            for m in mods
            if f"deps/{m}/__init__.py" in paths or f"deps/{m}.py" in paths
        ]
        if not landed:
            missing.add(pkg)
    return missing

def _parse_name_version(tarball: Path) -> tuple[str, str]:
    """从文件名 <name>-<version>-<platform>.tar.gz 解析出 (name, version)。

    插件名可能含连字符（如 docx-designer、gateway-dingtalk），版本号固定形如
    数字开头且含点，因此以「版本形态」的那一段作为锚点反推：
        docx-designer-0.3.3-darwin → ("docx-designer", "0.3.3")
    解析失败返回 ("", "")，调用方跳过该项检查。
    """
    stem = tarball.name
    for suffix in (".tar.gz", ".tgz"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    parts = stem.split("-")
    if len(parts) < 2:
        return "", ""
    for idx in range(1, len(parts)):
        if re.fullmatch(r"\d+(?:\.\d+)+", parts[idx]):
            name = "-".join(parts[:idx])
            rest = parts[idx + 1 :]
            # 版本后可能带预发布后缀（0.3.3-beta1），一并归入版本段
            version = parts[idx]
            if rest and rest[0] and rest[0] not in ("all", "default", "darwin", "win32", "linux"):
                version = f"{version}-{rest[0]}"
            return name, version
    return "", ""

def _platform_from_filename(tarball: Path) -> str:
    """从 tarball 文件名推断平台：<name>-<version>-<platform>.tar.gz

    build_plugin_tarballs.py 的命名约定；推断不出时返回 "default"。
    """
    stem = tarball.name
    for suffix in (".tar.gz", ".tgz"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    tail = stem.rsplit("-", 1)[-1].lower()
    return tail if tail in ("darwin", "win32", "linux") else "default"


def smoke_check(tarball: Path) -> tuple[bool, list[str], list[str]]:
    """检查单个 tarball。返回 (通过, 错误列表, 警告列表)"""
    errors: list[str] = []
    warnings: list[str] = []

    if not tarball.is_file():
        return False, [f"tarball 不存在: {tarball}"], warnings

    try:
        tf = tarfile.open(tarball, "r:gz")
    except Exception as e:
        return False, [f"tarball 无法打开: {e}"], warnings

    with tf:
        paths = _all_member_paths(tf)
        # 归一化路径 → 原始 member，供 extractfile 取内容
        raw_members = {_norm(m.name): m for m in tf.getmembers() if m.isfile()}

        # A. manifest 存在且可解析
        manifest_name = ".drifox-plugin/plugin.json"
        if manifest_name not in paths:
            errors.append(f"包内缺 {manifest_name}")
            return False, errors, warnings
        try:
            manifest = json.loads(tf.extractfile(raw_members[manifest_name]).read().decode("utf-8"))  # type: ignore[union-attr]
        except Exception as e:
            errors.append(f"{manifest_name} 解析失败: {e}")
            return False, errors, warnings

        plugin_name = str(manifest.get("name") or tarball.stem)

        # B. manifest 与包内版本一致：文件名 <name>-<version>-<platform>.tar.gz
        # 的 version 段必须等于 manifest.version。防止源码已升版本但产物是旧的
        # （或反之），客户端按清单版本更新却拿到旧内容。
        name_part, ver_part = _parse_name_version(tarball)
        manifest_ver = str(manifest.get("version") or "")
        if ver_part and manifest_ver and ver_part != manifest_ver:
            errors.append(
                f"文件名版本 {ver_part} 与 manifest.version {manifest_ver} 不一致"
            )
        if name_part and manifest.get("name") and name_part != manifest["name"]:
            errors.append(
                f"文件名插件名 {name_part} 与 manifest.name {manifest['name']} 不一致"
            )

        # E2. 声明的依赖必须真的在包内：
        #    逐包兜底路径用 pip --no-deps，manifest 漏写传递依赖时不会报错，
        #    打出的包会在运行期 ImportError（desktop-automation 缺 pyobjc-core
        #    即此形态：Quartz 是薄封装，全部 import objc，而 objc 根本不在包里）。
        #    只校验「该平台生效的依赖」（default + 平台专属）。
        declared = (manifest.get("dependencies") or {}).get("pip") or {}
        has_deps_dir = any(p.startswith("deps/") for p in paths)
        this_plat = _platform_from_filename(tarball)
        plat_keys = ["default"] + ([this_plat] if this_plat != "default" else [])
        declared_specs: list[str] = []
        for k in plat_keys:
            v = declared.get(k) if isinstance(declared, dict) else None
            if isinstance(v, list):
                declared_specs.extend(str(s) for s in v)
        if declared_specs and has_deps_dir:
            missing_mods = _missing_declared_modules(
                declared_specs, paths, lambda key: _read_member_text(tf, raw_members, key)
            )
            if missing_mods:
                errors.append(
                    f"包内缺少声明的依赖模块: {', '.join(sorted(missing_mods))}"
                    f"（manifest 未列出传递依赖？逐包兜底走 --no-deps 不会自动补）"
                )

        # C. 依赖子模块存在性
        vendored = _vendored_roots(tf)
        if vendored:
            init_sources: dict[str, bytes] = {}
            for key in paths:
                if key.endswith("/__init__.py") and key.startswith(("deps/", "vendor/")):
                    member = raw_members.get(key)
                    if member is not None:
                        fh = tf.extractfile(member)
                        if fh is not None:
                            init_sources[key] = fh.read()
            for src_path, source in _iter_source_members(tf):
                for module, name, lineno in _collect_from_imports(source):
                    top = module.split(".")[0]
                    if top not in vendored:
                        continue  # 不是包内依赖（stdlib / 宿主模块），不管
                    if top in _DYNAMIC_MODULE_HINTS:
                        continue
                    if not _module_exists(paths, module, name, vendored[top], init_sources):
                        errors.append(
                            f"{src_path}:{lineno} from {module} import {name}"
                            f" —— {top} 已 vendored 但缺 {name}"
                        )

        # D. 声明了 pip 依赖却完全没有 deps 目录
        if declared and not has_deps_dir:
            spec_count = sum(len(v) if isinstance(v, list) else 1 for v in declared.values())
            warnings.append(
                f"{plugin_name} 声明 {spec_count} 条 pip 依赖但包内无 deps/，安装端需自行补装"
            )

        # D2. 平台专属依赖不能塞进 default 单包：
        #    default 包会被所有平台下载，但平台专属依赖（如 darwin 的 pyobjc）
        #    只在对应平台存在 wheel，混进单包会让其他平台多装无用依赖，
        #    更常见的是「按平台拉取」时被跳过，导致目标平台运行时缺后端
        #    （desktop-automation 的 pynput 在 macOS 缺 pyobjc 即此形态）。
        platform_key_for_dep = _platform_from_filename(tarball)
        plat_specific = [k for k in declared if k != "default"] if isinstance(declared, dict) else []
        if plat_specific and platform_key_for_dep == "default":
            warnings.append(
                f"{plugin_name} 含平台专属依赖 {plat_specific}，但产物是 default 单包"
                f"（平台专属依赖需按平台分包才会生效）"
            )

        # E3. 宿主缺失 stdlib 副本（stdlib shim）必须真的在包内。
        #     2026-11 bili-scroll 二次事故：CI pip 通道只装 manifest 内 PyPI 包，
        #     _pystdlib_xml（非 PyPI 产物）整目录丢失，宿主缺 xml.dom 直接炸。
        required_shim = STDLIB_SHIM_PLUGINS.get(plugin_name) or STDLIB_SHIM_PLUGINS.get(name_part)
        if required_shim:
            for rel in required_shim:
                if f"deps/{rel}" not in paths:
                    errors.append(
                        f"宿主缺失 stdlib 副本未打进包：deps/{rel} 缺失（装上必炸，拒绝发布）"
                    )

        # E. 平台结构：包内二进制是否属于该平台 / ABI 是否匹配
        platform_key = _platform_from_filename(tarball)
        p_errors, p_warnings = check_platform_binaries(tf, platform_key)
        errors.extend(p_errors)
        warnings.extend(p_warnings)

    return not errors, errors, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description="tarball 发布前冒烟检查")
    ap.add_argument("paths", nargs="+", help="tarball 路径（可用通配符由 shell 展开）")
    ap.add_argument("--quiet", action="store_true", help="只输出失败项")
    args = ap.parse_args()

    failed = 0
    for raw in args.paths:
        p = Path(raw)
        ok, errors, warnings = smoke_check(p)
        if not args.quiet or not ok:
            status = "OK  " if ok else "FAIL"
            print(f"  [{status}] {p.name}")
        for w in warnings:
            print(f"         warn: {w}")
        for e in errors:
            print(f"         err : {e}")
        if not ok:
            failed += 1

    if failed:
        print(f"\n冒烟检查失败：{failed} 个包（宁可不发也不发残缺包）", file=sys.stderr)
        return 1
    print("\n冒烟检查全部通过", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
