# -*- coding: utf-8 -*-
"""采集：把诊断需要的事实从数据目录里捞出来，组装成待打包条目。

设计约束：
- 只用标准库，不 import 宿主模块（除宿主版本探测的兜底外），便于单测。
- 单文件有上限、单分区有上限，超限截断并记录原因，避免一个 500MB 日志把包撑爆。
- 文本条目明确标记 ``text=True``，由打包层统一脱敏；二进制原样写入。
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

MAX_LOG_FILES = 30
MAX_LOG_TAIL_BYTES = 1536 * 1024
MAX_LOG_TOTAL_BYTES = 20 * 1024 * 1024
MAX_CONFIG_BYTES = 2 * 1024 * 1024
MAX_PLUGIN_CONFIG_BYTES = 256 * 1024
MAX_PLUGIN_CONFIGS = 60
MAX_CRASH_LOG_BYTES = 4 * 1024 * 1024
MAX_ERROR_SUMMARY_BYTES = 200 * 1024


@dataclass
class Payload:
    """待写入 zip 的条目（文本条目已标注待脱敏）。"""

    arcname: str
    data: bytes | None = None
    source: Path | None = None
    text: bool = False
    stored: bool = False
    truncated: bool = False


def read_tail(path: Path, max_bytes: int) -> tuple[bytes, bool]:
    """读取文件尾部至多 max_bytes，返回 (数据, 是否截断)。"""
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
                return fh.read(), True
            return fh.read(), False
    except OSError as exc:
        return f"[读取失败: {exc}]".encode("utf-8"), False


def detect_app_version() -> str:
    """宿主版本：包元数据 → 未知。不 import 宿主内部模块。"""
    try:
        from importlib.metadata import version

        return version("drifox")
    except Exception:  # noqa: BLE001 — 打包版可能无包元数据
        return "unknown"


def _memory_text() -> str:
    try:
        import psutil  # type: ignore

        vm = psutil.virtual_memory()
        return f"{vm.total / 1024 ** 3:.1f} GB（可用 {vm.available / 1024 ** 3:.1f} GB）"
    except Exception:  # noqa: BLE001 — psutil 可选
        return "不可用"


def _qt_text() -> str:
    try:
        from PyQt5.QtCore import PYQT_VERSION_STR, QT_VERSION_STR

        return f"Qt {QT_VERSION_STR} / PyQt {PYQT_VERSION_STR}"
    except Exception:  # noqa: BLE001 — 无 Qt 环境（纯工具侧测试）
        return "不可用"


def _disk_text(path: Path) -> str:
    try:
        usage = shutil.disk_usage(str(path))
        return f"剩余 {usage.free / 1024 ** 3:.1f} GB / 共 {usage.total / 1024 ** 3:.1f} GB"
    except OSError:
        return "不可用"


def collect_system_info(data_dir: Path) -> str:
    """系统与运行环境快照。"""
    env_lines = []
    for key in sorted(os.environ):
        if key.startswith("DRIFOX_") or key in ("LANG", "LC_ALL", "QT_SCALE_FACTOR", "PYTHONIOENCODING"):
            env_lines.append(f"  {key}={os.environ[key]}")

    lines = [
        f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"平台: {platform.platform()}",
        f"系统: {platform.system()} {platform.release()}",
        f"架构: {platform.machine()}",
        f"Python: {sys.version.split()[0]} ({platform.python_implementation()})",
        f"可执行文件: {sys.executable}",
        f"打包形态: frozen={bool(getattr(sys, 'frozen', False))}, _MEIPASS={hasattr(sys, '_MEIPASS')}",
        f"DriFox 版本: {detect_app_version()}",
        f"Qt: {_qt_text()}",
        f"CPU: {os.cpu_count()} 核",
        f"内存: {_memory_text()}",
        f"数据目录: {data_dir}",
        f"数据目录磁盘: {_disk_text(data_dir)}",
        f"工作目录: {Path.cwd()}",
    ]
    if env_lines:
        lines.append("环境变量（DRIFOX_* 与编码相关）:")
        lines.extend(env_lines)
    return "\n".join(lines) + "\n"


def scan_plugins(data_dir: Path, enabled_names: Iterable[str] | None = None) -> dict[str, Any]:
    """扫描已安装的用户插件清单。

    ``enabled_names`` 由 UI 侧通过 ``plugin.read`` 能力提供；工具侧拿不到，
    此时 ``enabled`` 字段为 None（未知），不猜。
    """
    enabled = set(enabled_names) if enabled_names is not None else None
    items: list[dict[str, Any]] = []
    root = data_dir / "plugins"
    if root.is_dir():
        for manifest_path in sorted(root.glob("*/.drifox-plugin/plugin.json")):
            name = manifest_path.parent.parent.name
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001 — 坏清单本身就是诊断线索
                items.append({"name": name, "error": f"清单读取失败: {exc}"})
                continue
            deps = manifest.get("dependencies") or {}
            items.append(
                {
                    "name": manifest.get("name", name),
                    "version": manifest.get("version", ""),
                    "api_version": manifest.get("api_version", 1),
                    "min_host_version": manifest.get("min_host_version", ""),
                    "components": sorted(
                        key for key, value in (manifest.get("components") or {}).items() if value
                    ),
                    "capabilities": manifest.get("capabilities"),
                    "pip_deps": sorted((deps.get("pip") or {}).get("default") or [])
                    if isinstance(deps, dict)
                    else [],
                    "enabled": (name in enabled) if enabled is not None else None,
                }
            )
    return {
        "root": str(root),
        "count": len(items),
        "enabled_known": enabled is not None,
        "plugins": items,
    }


def collect_configs(data_dir: Path) -> tuple[list[Payload], list[str]]:
    """宿主配置 + 各插件配置，全部标记待脱敏。"""
    payloads: list[Payload] = []
    warnings: list[str] = []

    app_config = data_dir / "app.config"
    if app_config.is_file():
        data, truncated = read_tail(app_config, MAX_CONFIG_BYTES)
        payloads.append(Payload("config/app.config", data=data, text=True, truncated=truncated))
    else:
        warnings.append("未找到 app.config")

    plugin_root = data_dir / "plugin_data"
    if plugin_root.is_dir():
        count = 0
        for config_path in sorted(plugin_root.glob("*/config.json")):
            if count >= MAX_PLUGIN_CONFIGS:
                warnings.append(f"插件配置超过 {MAX_PLUGIN_CONFIGS} 份，其余未打包")
                break
            data, truncated = read_tail(config_path, MAX_PLUGIN_CONFIG_BYTES)
            payloads.append(
                Payload(
                    f"config/plugin_data/{config_path.parent.name}.json",
                    data=data,
                    text=True,
                    truncated=truncated,
                )
            )
            count += 1
    return payloads, warnings


def collect_logs(data_dir: Path) -> tuple[list[Payload], list[str]]:
    """最近日志（按修改时间倒序，受单文件与总量双重限制）。"""
    payloads: list[Payload] = []
    warnings: list[str] = []
    log_dir = data_dir / "logs"
    if not log_dir.is_dir():
        return payloads, ["未找到 logs 目录"]

    files = sorted(
        (path for path in log_dir.glob("*.log") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    total = 0
    for index, path in enumerate(files):
        if index >= MAX_LOG_FILES:
            warnings.append(f"日志文件超过 {MAX_LOG_FILES} 份，其余未打包")
            break
        if total >= MAX_LOG_TOTAL_BYTES:
            warnings.append("日志总量超过上限，其余未打包")
            break
        data, truncated = read_tail(path, MAX_LOG_TAIL_BYTES)
        total += len(data)
        payloads.append(Payload(f"logs/{path.name}", data=data, text=True, truncated=truncated))
    return payloads, warnings


_ERROR_MARKS = ("| ERROR |", "| CRITICAL |", "Traceback (most recent call last)")


def collect_recent_errors(data_dir: Path) -> Payload | None:
    """从最近日志里抽取错误行与堆栈块，单独成一份便于快速定位。"""
    log_dir = data_dir / "logs"
    all_log = log_dir / "all.log"
    if not all_log.is_file():
        return None
    data, truncated = read_tail(all_log, MAX_LOG_TAIL_BYTES)
    lines = data.decode("utf-8", errors="replace").splitlines()

    picked: list[str] = []
    in_traceback = False
    for line in lines:
        if "Traceback (most recent call last)" in line:
            in_traceback = True
            picked.append(line)
            continue
        if in_traceback:
            picked.append(line)
            if line and not line.startswith((" ", "\t")):
                in_traceback = False
            continue
        if any(mark in line for mark in _ERROR_MARKS):
            picked.append(line)

    body = "\n".join(picked)
    encoded = body.encode("utf-8")
    if len(encoded) > MAX_ERROR_SUMMARY_BYTES:
        encoded = encoded[-MAX_ERROR_SUMMARY_BYTES:]
        body = "[...前段已截断...]\n" + encoded.decode("utf-8", errors="replace")
        truncated = True
    header = f"# 最近错误摘要（取 all.log 末尾 {MAX_LOG_TAIL_BYTES // 1024} KB，命中 {len(picked)} 行）\n"
    return Payload(
        "logs/recent-errors.txt",
        data=(header + body + "\n").encode("utf-8"),
        text=True,
        truncated=truncated,
    )


def collect_crash(data_dir: Path, include_dumps: bool) -> tuple[list[Payload], list[str]]:
    """崩溃现场：faulthandler/VEH 的 crash_*.log 与 minidump。"""
    payloads: list[Payload] = []
    warnings: list[str] = []
    crash_dir = data_dir / "logs" / "crash"
    if not crash_dir.is_dir():
        return payloads, ["未找到崩溃目录（本次运行可能没有崩溃记录）"]

    for path in sorted(crash_dir.glob("*.log")):
        data, truncated = read_tail(path, MAX_CRASH_LOG_BYTES)
        payloads.append(Payload(f"crash/{path.name}", data=data, text=True, truncated=truncated))

    dumps = sorted(
        (path for path in list(crash_dir.glob("*.dmp")) + list((crash_dir / "dumps").glob("*.dmp")) if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if dumps and not include_dumps:
        warnings.append(f"发现 {len(dumps)} 个 minidump，按设置未打包")
    elif dumps:
        for path in dumps:
            payloads.append(Payload(f"crash/dumps/{path.name}", source=path, stored=True))
    return payloads, warnings
