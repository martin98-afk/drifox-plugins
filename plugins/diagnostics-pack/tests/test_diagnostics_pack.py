# -*- coding: utf-8 -*-
"""diagnostics-pack 核心回归：脱敏、包内容、预算跳过、保留份数。

只测纯标准库核心（drifox_diag_pack），不启动宿主。
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from drifox_diag_pack import build_pack  # noqa: E402
from drifox_diag_pack.mask import mask_text  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sample_data_dir(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    _write(data / "app.config", '{\n  "LLM": {"api_key": "sk-verysecret1234567890", "max_tokens": 4096}\n}\n')
    _write(data / "plugin_data" / "foo" / "config.json", '{"password": "hunter2secret", "enabled": true}\n')
    _write(
        data / "plugins" / "foo" / ".drifox-plugin" / "plugin.json",
        json.dumps({"name": "foo", "version": "1.2.3", "components": {"tools": True}}),
    )
    _write(
        data / "logs" / "all.log",
        "2026-11-13 12:00:00 | INFO | 启动\n"
        "2026-11-13 12:00:01 | ERROR | 请求失败 key=sk-abcdefghijklmnop\n"
        "Traceback (most recent call last):\n"
        '  File "x.py", line 1, in <module>\n'
        "ValueError: boom\n",
    )
    _write(data / "logs" / "crash" / "crash_20261113_120000.log", "access violation\n")
    dump = data / "logs" / "crash" / "dumps" / "crash_1.dmp"
    dump.parent.mkdir(parents=True, exist_ok=True)
    dump.write_bytes(b"MDMP" + b"\x00" * 64)
    return data


def _read_zip(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_mask_keeps_normal_params() -> None:
    text = 'api_key: "sk-abcdefghijklmnop"\nAuthorization: Bearer abcdefghijklmnop\nmax_tokens: 4096'
    masked, hits = mask_text(text)
    assert hits >= 3
    assert "sk-abcdefghijklmnop" not in masked
    assert "abcdefghijklmnop" not in masked
    assert "max_tokens: 4096" in masked


def test_build_pack_contents_and_masking(tmp_path: Path) -> None:
    data = _sample_data_dir(tmp_path)
    result = build_pack(data, include_crash_dumps=True, max_mb=10, enabled_plugins=["foo"])

    assert result["ok"] is True
    assert Path(result["path"]).is_file()
    entries = _read_zip(Path(result["path"]))

    assert "README.txt" in entries
    assert "system-info.txt" in entries
    assert "plugins.json" in entries
    assert "config/app.config" in entries
    assert "config/plugin_data/foo.json" in entries
    assert "logs/all.log" in entries
    assert "logs/recent-errors.txt" in entries
    assert "crash/crash_20261113_120000.log" in entries
    assert "crash/dumps/crash_1.dmp" in entries

    config_text = entries["config/app.config"].decode("utf-8")
    assert "sk-verysecret1234567890" not in config_text
    assert "max_tokens" in config_text
    assert "hunter2secret" not in entries["config/plugin_data/foo.json"].decode("utf-8")
    assert "sk-abcdefghijklmnop" not in entries["logs/all.log"].decode("utf-8")

    plugins = json.loads(entries["plugins.json"].decode("utf-8"))
    assert plugins["enabled_known"] is True
    assert plugins["plugins"][0]["enabled"] is True

    errors = entries["logs/recent-errors.txt"].decode("utf-8")
    assert "ValueError: boom" in errors
    assert result["masked_hits"] >= 3


def test_crash_dumps_can_be_excluded(tmp_path: Path) -> None:
    data = _sample_data_dir(tmp_path)
    result = build_pack(data, include_crash_dumps=False, max_mb=10)
    entries = _read_zip(Path(result["path"]))

    assert not any(name.startswith("crash/dumps/") for name in entries)
    assert any("未打包" in warning for warning in result["warnings"])


def test_budget_skips_oversize_logs(tmp_path: Path) -> None:
    data = tmp_path / "data"
    for index in range(6):
        _write(data / "logs" / f"big{index}.log", "x" * (1600 * 1024))
    result = build_pack(data, max_mb=5, include_crash_dumps=False)

    assert result["skipped"], "预算不足时必须有跳过记录"
    assert result["uncompressed"] <= 5 * 1024 * 1024
    entries = _read_zip(Path(result["path"]))
    metadata = json.loads(entries["metadata.json"].decode("utf-8"))
    assert metadata["skipped"]


def test_prune_keeps_latest(tmp_path: Path) -> None:
    data = _sample_data_dir(tmp_path)
    for _ in range(3):
        build_pack(data, max_mb=10, keep_runs=2)
    packs = sorted((data / "diagnostics").glob("drifox-diagnostics-*.zip"))
    assert len(packs) == 2
