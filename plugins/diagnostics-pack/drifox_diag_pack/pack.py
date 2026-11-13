# -*- coding: utf-8 -*-
"""打包：把采集条目脱敏后写入 zip，带体积预算与保留份数。

预算按「未压缩字节」计算，写入前就判，避免先落盘再删。
"""
from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path
from typing import Any, Iterable

from .collect import (
    Payload,
    collect_configs,
    collect_crash,
    collect_logs,
    collect_recent_errors,
    collect_system_info,
    scan_plugins,
)
from .mask import mask_bytes

DEFAULT_MAX_MB = 50
DEFAULT_KEEP_RUNS = 5
MIN_MAX_MB = 5
MAX_MAX_MB = 1000
PACK_PREFIX = "drifox-diagnostics"

_PRIVACY_NOTE = """DriFox 诊断包
生成时间: {generated_at}
生成方式: diagnostics-pack v{plugin_version}

包含内容
- metadata.json     本包清单: 选项 / 条目 / 体积 / 脱敏计数 / 截断与跳过原因
- system-info.txt   系统 / Python / Qt / 宿主机版本 / 数据目录
- plugins.json      已安装用户插件清单（启用状态由 UI 侧提供，未知写 null）
- config/           宿主与插件配置（密钥字段已脱敏）
- logs/             最近日志（默认每份最多 1.5 MB 尾部）+ recent-errors.txt
- crash/            崩溃堆栈与 minidump（可选）

隐私提醒
- 含本机绝对路径、用户名、插件名，日志里可能有会话片段。
- 配置与日志按常见密钥形态脱敏，不排除自定义字段漏网。
- minidump 可能含崩溃瞬间的内存片段。公开上传前务必检查内容。

怎么用
- 自查：先看 logs/recent-errors.txt，再看 crash/ 下最新堆栈。
- 回传：整个 zip 发给开发者；不需要 minidump 时可关闭后重导。
"""


def _normalize_mb(value: Any, default: int = DEFAULT_MAX_MB) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(MIN_MAX_MB, min(MAX_MAX_MB, number))


def _unique_path(out_dir: Path, stamp: str) -> Path:
    path = out_dir / f"{PACK_PREFIX}-{stamp}.zip"
    index = 2
    while path.exists():
        path = out_dir / f"{PACK_PREFIX}-{stamp}-{index}.zip"
        index += 1
    return path


def _prune(out_dir: Path, keep_runs: int) -> list[str]:
    """只清理本插件自己产出的包，按修改时间留最新 keep_runs 份。"""
    packs = sorted(
        out_dir.glob(f"{PACK_PREFIX}-*.zip"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    removed = []
    for path in packs[max(1, keep_runs):]:
        try:
            path.unlink()
            removed.append(path.name)
        except OSError:
            pass
    return removed


def build_pack(
    data_dir: Path | str,
    out_dir: Path | str | None = None,
    *,
    include_crash_dumps: bool = True,
    max_mb: int = DEFAULT_MAX_MB,
    keep_runs: int = DEFAULT_KEEP_RUNS,
    plugin_version: str = "",
    host_version: str = "",
    enabled_plugins: Iterable[str] | None = None,
    note: str = "",
    now: float | None = None,
) -> dict[str, Any]:
    """生成诊断 zip，返回结果摘要（含 path / size / entries / masked_hits 等）。"""
    started = time.monotonic()
    data_dir = Path(data_dir).expanduser().resolve()
    out_dir = (Path(out_dir).expanduser() if out_dir else data_dir / "diagnostics").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    zip_path = _unique_path(out_dir, stamp)
    budget = _normalize_mb(max_mb) * 1024 * 1024

    warnings: list[str] = []
    payloads: list[Payload] = []

    system_text = collect_system_info(data_dir)
    payloads.append(Payload("system-info.txt", data=system_text.encode("utf-8"), text=True))

    plugin_info = scan_plugins(data_dir, enabled_plugins)
    payloads.append(
        Payload(
            "plugins.json",
            data=json.dumps(plugin_info, ensure_ascii=False, indent=2).encode("utf-8"),
            text=True,
        )
    )

    config_payloads, config_warnings = collect_configs(data_dir)
    payloads.extend(config_payloads)
    warnings.extend(config_warnings)

    log_payloads, log_warnings = collect_logs(data_dir)
    payloads.extend(log_payloads)
    warnings.extend(log_warnings)

    error_payload = collect_recent_errors(data_dir)
    if error_payload is not None:
        payloads.append(error_payload)

    crash_payloads, crash_warnings = collect_crash(data_dir, include_crash_dumps)
    payloads.extend(crash_payloads)
    warnings.extend(crash_warnings)

    readme = _PRIVACY_NOTE.format(
        generated_at=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
        plugin_version=plugin_version or "unknown",
    )
    if note.strip():
        readme += f"\n用户备注\n{note.strip()}\n"

    entries: list[dict[str, Any]] = []
    skipped: list[str] = []
    masked_hits = 0
    used = 0

    try:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr("README.txt", readme)

            for payload in payloads:
                if payload.data is not None:
                    size = len(payload.data)
                elif payload.source is not None:
                    try:
                        size = payload.source.stat().st_size
                    except OSError as exc:
                        skipped.append(f"{payload.arcname}: 读取失败 {exc}")
                        continue
                else:
                    continue

                if used + size > budget:
                    skipped.append(
                        f"{payload.arcname}: 超出体积预算（{size / 1024 / 1024:.1f} MB，"
                        f"预算剩余 {(budget - used) / 1024 / 1024:.1f} MB）"
                    )
                    continue

                if payload.data is not None:
                    blob = payload.data
                    if payload.text:
                        blob, hits = mask_bytes(blob)
                        masked_hits += hits
                    archive.writestr(payload.arcname, blob)
                else:
                    assert payload.source is not None
                    compress = zipfile.ZIP_STORED if payload.stored else zipfile.ZIP_DEFLATED
                    archive.write(payload.source, payload.arcname, compress_type=compress)

                used += size
                entries.append(
                    {
                        "path": payload.arcname,
                        "bytes": size,
                        "truncated": bool(payload.truncated),
                        "stored": bool(payload.stored),
                    }
                )

            metadata = {
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
                "plugin": {"name": "diagnostics-pack", "version": plugin_version},
                "host_version": host_version or "unknown",
                "options": {
                    "include_crash_dumps": bool(include_crash_dumps),
                    "max_mb": _normalize_mb(max_mb),
                    "keep_runs": max(1, int(keep_runs)),
                    "note": note.strip(),
                },
                "budget_bytes": budget,
                "used_bytes": used,
                "entries": entries,
                "masked_hits": masked_hits,
                "skipped": skipped,
                "warnings": warnings,
            }
            archive.writestr(
                "metadata.json",
                json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"),
            )
    except Exception:
        try:
            zip_path.unlink()
        except OSError:
            pass
        raise

    removed = _prune(out_dir, keep_runs)
    return {
        "ok": True,
        "path": str(zip_path),
        "size": zip_path.stat().st_size,
        "uncompressed": used,
        "entries": len(entries),
        "masked_hits": masked_hits,
        "skipped": skipped,
        "warnings": warnings,
        "pruned": removed,
        "duration_ms": int((time.monotonic() - started) * 1000),
    }
