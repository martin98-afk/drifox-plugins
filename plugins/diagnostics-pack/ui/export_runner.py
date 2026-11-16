# -*- coding: utf-8 -*-
"""后台导出：QThread 跑采集+打包，主线程只更新 UI。

为什么不直接在按钮槽里跑：日志尾部+配置脱敏+压缩在机械盘上可能几秒，
主线程阻塞会让设置页假死。worker 必须存模块级集合，否则出作用域被 GC，
线程会以「QThread: Destroyed while thread is still running」崩掉。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

from loguru import logger
from PyQt5.QtCore import QThread, pyqtSignal

PLUGIN_NAME = "diagnostics-pack"
_PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

_ACTIVE: set["ExportWorker"] = set()


def plugin_version() -> str:
    try:
        manifest = json.loads(
            (_PLUGIN_DIR / ".drifox-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        return str(manifest.get("version", ""))
    except Exception:  # noqa: BLE001 — 版本只用于包内元数据
        return ""


def enabled_plugin_names() -> list[str] | None:
    """宿主已启用插件名；能力不可用时返回 None（包内标未知，不猜）。"""
    try:
        from app.plugins.sdk import caps_for

        read = caps_for("plugin.read", plugin=PLUGIN_NAME, surface="ui")
        if read is None:
            return None
        api = read()
        return [info.name for info in api["enabled"]()]
    except Exception as exc:  # noqa: BLE001 — 旧宿主或无窗口上下文
        logger.debug(f"[diagnostics-pack] plugin.read 不可用: {exc}")
        return None


class ExportWorker(QThread):
    done = pyqtSignal(dict)

    def __init__(
        self,
        data_dir: Path,
        options: dict[str, Any],
        enabled_plugins: Iterable[str] | None = None,
        note: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._data_dir = Path(data_dir)
        self._options = dict(options or {})
        self._enabled = list(enabled_plugins) if enabled_plugins is not None else None
        self._note = note

    def run(self) -> None:  # noqa: D102 — QThread 入口
        try:
            from drifox_diag_pack import build_pack
            from drifox_diag_pack.collect import detect_app_version

            result = build_pack(
                self._data_dir,
                include_crash_dumps=bool(self._options.get("include_crash_dumps", True)),
                max_mb=int(self._options.get("max_mb", 50)),
                keep_runs=int(self._options.get("keep_runs", 5)),
                plugin_version=plugin_version(),
                host_version=detect_app_version(),
                enabled_plugins=self._enabled,
                note=self._note,
            )
        except Exception as exc:  # noqa: BLE001 — 失败结果回主线程展示
            logger.exception(f"[diagnostics-pack] 导出失败: {exc}")
            result = {"ok": False, "error": str(exc)}
        self.done.emit(result)


def start_export(
    parent,
    *,
    data_dir: Path,
    options: dict[str, Any],
    on_done: Callable[[dict], None],
    note: str = "",
) -> ExportWorker:
    worker = ExportWorker(data_dir, options, enabled_plugin_names(), note=note, parent=parent)
    worker.done.connect(on_done)
    worker.finished.connect(lambda: _ACTIVE.discard(worker))
    _ACTIVE.add(worker)
    worker.start()
    return worker
