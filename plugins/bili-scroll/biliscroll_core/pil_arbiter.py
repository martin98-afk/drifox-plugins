# -*- coding: utf-8 -*-
"""PIL 仲裁：打包版宿主 FrozenImporter 会虚拟出残缺 PIL（_internal 无 _imaging.pyd），
且 meta_path 优先于 deps/ 的 sys.path 注入 ⇒ 必须用钩子把 PIL 指到插件 deps 版。

放 biliscroll_core/ 而非 tools/ 顶层：PluginToolLoader 对 tools/ 非下划线文件
过 ASTGuard，回滚路径的 sys.modules.update(saved)（动态键）会被整文件拒载；
ssh-toolkit 同款仲裁同理藏在 _auth.py（_ 前缀不被扫）。调用方：biliscroll_core/
bili_impl.py 在 import vendor mcp_server 之前调仲裁。
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import sys
from pathlib import Path

from loguru import logger

_PIL_SELFTEST_OK = False


def vendored_pil_dir() -> Path | None:
    here = Path(__file__).resolve().parent.parent
    plat = "win32" if os.name == "nt" else sys.platform
    for sub in (plat, ""):
        d = here / "deps" / sub / "PIL"
        if (d / "__init__.py").is_file():
            return d
    return None

class _VendoredPilFinder:
    """meta_path 钩子：PIL* 一律指向插件 deps 目录，其余放行。"""

    def __init__(self, pkg_dir: str):
        hook = importlib.machinery.FileFinder.path_hook(
            (importlib.machinery.ExtensionFileLoader, importlib.machinery.EXTENSION_SUFFIXES),
            (importlib.machinery.SourceFileLoader, importlib.machinery.SOURCE_SUFFIXES),
            (importlib.machinery.SourcelessFileLoader, importlib.machinery.BYTECODE_SUFFIXES),
        )
        self._finder = hook(pkg_dir)

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "PIL" or fullname.startswith("PIL."):
            return self._finder.find_spec(fullname, target)
        return None

def _pil_modules():
    return [k for k in sys.modules if k == "PIL" or k.startswith("PIL.")]

def _pil_selftest():
    from PIL import _imaging  # noqa: F401  残缺副本正是缺这个

def prefer_vendored_pil():
    """宿主 PIL 缺 _imaging 时换成 deps 版（幂等，失败回滚宿主原状）。"""
    global _PIL_SELFTEST_OK
    if _PIL_SELFTEST_OK:
        return
    pkg_dir = vendored_pil_dir()
    if not pkg_dir:
        return
    try:
        _pil_selftest()
        _PIL_SELFTEST_OK = True  # 宿主副本完好，不动
        return
    except Exception:
        pass
    saved = {k: sys.modules[k] for k in _pil_modules()}
    finder = _VendoredPilFinder(str(pkg_dir.parent))
    for k in saved:
        del sys.modules[k]
    sys.meta_path.insert(0, finder)
    try:
        importlib.import_module("PIL")
        mod = sys.modules.get("PIL")
        new_file = os.path.normcase(os.path.abspath(str(getattr(mod, "__file__", "") or "")))
        if not new_file.startswith(os.path.normcase(str(pkg_dir.parent))):
            raise RuntimeError(f"vendored PIL 未生效：{new_file}")
        _pil_selftest()
        _PIL_SELFTEST_OK = True  # 钩子常驻：后续 PIL.* 子模块 import 仍需绕开 FrozenImporter
        logger.info("[bili-scroll] 已仲裁 PIL → 插件 deps 版（宿主副本缺 _imaging）")
    except Exception as e:  # noqa: BLE001 - 任何失败都回滚到宿主现状
        logger.warning(f"[bili-scroll] vendored PIL 仲裁失败，回滚宿主原状: {e}")
        try:
            sys.meta_path.remove(finder)
        except ValueError:
            pass
        for k in _pil_modules():
            sys.modules.pop(k, None)
        sys.modules.update(saved)

# ── stdlib 副本仲裁：宿主打包只收集主程序用到的标准库子集（已知缺 xml.dom、
# optparse），且 PyiFrozenLoader 挂 meta_path 优先于 sys.path ⇒ 光往 sys.path 塞
# 副本无效，必须 del 残缺 sys.modules 条目 + meta_path 钩子 + 重新 import（PIL 同款）。
# 副本统一放 deps/_pystdlib_xml/（目录名避开 stdlib 顶层名，否则 deps_loader 按
# 防劫持检查拒注入整个 deps）。纪律：这里只放宿主打包缺失的标准库副本。

_STDLIB_SHIM_PROBES = ("xml.dom", "optparse")
_STDLIB_SHIM_OK = False

class _VendoredStdlibFinder:
    """meta_path 钩子：shim 目录里有的顶层名一律接管，其余放行。"""

    def __init__(self, root: Path):
        self._names: set[str] = set()
        for entry in root.iterdir():
            if entry.is_dir() and (entry / "__init__.py").is_file():
                self._names.add(entry.name)
            elif entry.is_file() and entry.suffix == ".py":
                self._names.add(entry.stem)
        hook = importlib.machinery.FileFinder.path_hook(
            (importlib.machinery.ExtensionFileLoader, importlib.machinery.EXTENSION_SUFFIXES),
            (importlib.machinery.SourceFileLoader, importlib.machinery.SOURCE_SUFFIXES),
            (importlib.machinery.SourcelessFileLoader, importlib.machinery.BYTECODE_SUFFIXES),
        )
        self._finder = hook(str(root))

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in self._names:
            return self._finder.find_spec(fullname, target)
        return None

def prefer_vendored_stdlib(shim_root: Path):
    """探测 PROBES 名单，import 失败的顶层名 del 残缺条目 + meta_path 钩子接管副本。"""
    global _STDLIB_SHIM_OK
    if _STDLIB_SHIM_OK:
        return
    root = Path(shim_root)
    if not root.is_dir():
        return
    missing = []
    for probe in _STDLIB_SHIM_PROBES:
        try:
            importlib.import_module(probe)
        except Exception:
            missing.append(probe.split(".")[0])
    if not missing:
        return
    saved = {}
    for k in list(sys.modules):
        if k.split(".")[0] in missing:
            saved[k] = sys.modules[k]
            del sys.modules[k]
    finder = _VendoredStdlibFinder(root)
    sys.meta_path.insert(0, finder)
    try:
        for name in missing:
            importlib.import_module(name)
        _STDLIB_SHIM_OK = True  # 钩子常驻：后续同根子模块 import 仍需绕开打包加载器
        logger.info(f"[bili-scroll] 已仲裁 stdlib 副本 → {root.name}（宿主打包缺 {missing}）")
    except Exception as e:  # noqa: BLE001 - 任何失败都回滚到宿主现状
        logger.warning(f"[bili-scroll] stdlib 副本仲裁失败，回滚宿主原状: {e}")
        try:
            sys.meta_path.remove(finder)
        except ValueError:
            pass
        for k in list(sys.modules):
            if k.split(".")[0] in missing:
                sys.modules.pop(k, None)
        sys.modules.update(saved)
