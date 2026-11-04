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

def _log_pil_origin() -> None:
    """记录当前实际生效的 PIL 来源与版本（只读，绝不抛异常）。

    为什么需要：宿主 deps_loader 把每个插件的 deps 目录 insert(0) 到 sys.path，
    带 PIL 的插件谁后加载谁占位，先进 sys.modules 的那份赢。本机实测：
    docx-designer(Pillow 13.0.0) 会赢过本插件的 12.2.0。SDK 是按自带版本写
    和测的，跨版本跑可能摸到已移除 API，而报错现场离根因极远（曾为了一个
    UnidentifiedImageError 查到多插件临时文件冲突）。这里只留一行现场快照，
    不改任何行为。
    """
    try:
        mod = sys.modules.get("PIL")
        if mod is None:
            return
        actual_file = str(getattr(mod, "__file__", "") or "")
        actual_ver = str(getattr(mod, "__version__", "") or "?")
        own_dir = vendored_pil_dir()
        own_ver = "?"
        if own_dir is not None:
            try:
                vi = own_dir / "_version.py"
                if vi.is_file():
                    for line in vi.read_text(encoding="utf-8").splitlines():
                        if line.startswith("__version__"):
                            own_ver = line.split("=", 1)[1].strip().strip("\"'")
                            break
            except Exception:
                pass
        from_own = bool(
            own_dir is not None
            and os.path.normcase(os.path.abspath(actual_file)).startswith(
                os.path.normcase(str(own_dir))
            )
        )
        level = logger.info
        detail = f"本插件自带 {own_ver}"
        if not from_own:
            detail = f"非本插件自带，本插件自带 {own_ver}"
        if own_ver not in ("?", actual_ver):
            level = logger.warning
        level(
            f"[bili-scroll] PIL 实际生效：Pillow {actual_ver} @ {actual_file or '?'}"
            f" | {detail}"
        )
    except Exception:  # noqa: BLE001 - 诊断日志绝不影响仲裁
        pass

def _pil_selftest():
    """自检必须真解码一张图，不能只验 import。

    踩过的坑：PyInstaller 打包版的 PIL 能 `from PIL import _imaging` 成功
    （扩展在位、Image 能 import），但**格式插件没注册**，Image.open() 一律
    抛 `UnidentifiedImageError: cannot identify image file`。只看 import
    会判定「宿主副本完好」，跳过仲裁，结果所有吃图的能力（发动态带图、
    视频封面上传）在真机上全废，且报错位置离根因很远。
    """
    from PIL import Image

    Image.init()  # 触发插件注册（返回值不可靠，不判它）
    if "PNG" not in Image.OPEN:
        raise RuntimeError(f"PIL 未注册 PNG 解码器（已注册: {sorted(Image.OPEN)[:8]}）")
    # 1x1 RGB 真 PNG（IHDR/IDAT/IEND 齐全、CRC 正确），走完整解码链路。
    # 别手编字节：早先写的样本 CRC 错，PIL 报 "broken data stream"，
    # 仲裁据此判定宿主 PIL 坏掉并误回滚。
    sample = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108020000"
        "00907753de0000000c49444154789c63f8cfc0000003010100c9fe92ef"
        "0000000049454e44ae426082"
    )
    import io

    with Image.open(io.BytesIO(sample)) as im:
        im.load()
        if im.size != (1, 1):
            raise RuntimeError(f"PIL 解码结果异常: {im.size}")

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
        _log_pil_origin()
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
        logger.info("[bili-scroll] 已仲裁 PIL → 插件 deps 版（宿主副本不可用）")
        _log_pil_origin()
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
