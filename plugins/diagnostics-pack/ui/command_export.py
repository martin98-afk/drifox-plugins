# -*- coding: utf-8 -*-
"""``/diag`` 命令的实现：不开设置页也能一键导出。

命令走 QThread；结果回主线程的 QObject 槽再通知与开目录，
避免在 worker 线程碰 UI。receiver 必须模块级持有，否则信号回来前被 GC。
"""
from __future__ import annotations

from pathlib import Path

from loguru import logger
from PyQt5.QtCore import QObject, QUrl
from PyQt5.QtGui import QDesktopServices

from .config_card import _fmt_size, _notify
from .export_runner import start_export
from .settings_store import load_settings

PLUGIN_NAME = "diagnostics-pack"

_RECEIVERS: list["_DoneReceiver"] = []


class _DoneReceiver(QObject):
    def __init__(self, data_dir: Path, open_after: bool) -> None:
        super().__init__()
        self._data_dir = data_dir
        self._open_after = open_after

    def handle(self, result: dict) -> None:
        try:
            if not result.get("ok"):
                message = str(result.get("error") or "未知错误")
                _notify("诊断包导出失败", message, kind="error")
                return
            name = Path(str(result["path"])).name
            _notify(
                "诊断包已生成",
                f"{name}（{_fmt_size(int(result['size']))}）",
                kind="success",
            )
            if self._open_after:
                out_dir = self._data_dir / "diagnostics"
                out_dir.mkdir(parents=True, exist_ok=True)
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(out_dir)))
        finally:
            if self in _RECEIVERS:
                _RECEIVERS.remove(self)


def run(args: str = "") -> None:
    """``/diag`` 入口：``--open`` 导出后打开目录。"""
    from drifox_diag_pack.host_env import resolve_data_dir

    data_dir = resolve_data_dir("ui")
    open_after = "--open" in (args or "")
    receiver = _DoneReceiver(data_dir, open_after)
    _RECEIVERS.append(receiver)
    try:
        start_export(
            None,
            data_dir=data_dir,
            options=load_settings(data_dir),
            on_done=receiver.handle,
        )
        _notify("诊断包", "正在打包…", kind="info")
    except Exception as exc:  # noqa: BLE001 — 启动失败要能看见
        logger.exception(f"[diagnostics-pack] /diag 启动失败: {exc}")
        _RECEIVERS.remove(receiver)
        _notify("诊断包导出失败", str(exc), kind="error")
