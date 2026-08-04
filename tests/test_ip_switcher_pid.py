# -*- coding: utf-8 -*-
"""ip-switcher proxy_pool PID 文件管理单元测试

覆盖：PID 文件写入/读取/删除、_kill_pid 防误杀校验、stop 兜底清理。
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from ip_switcher_proxy_pool import ProxyPoolManager


def _make_manager(tmp_path: Path) -> ProxyPoolManager:
    m = ProxyPoolManager(stats_port=18093, proxy_port=18092, data_dir=tmp_path)
    return m


def test_write_and_read_pid_file(tmp_path):
    m = _make_manager(tmp_path)
    m._write_pid_file(12345)
    assert m._read_pid_file() == 12345
    m._delete_pid_file()
    assert m._read_pid_file() is None


def test_kill_pid_rejects_non_proxypool(tmp_path):
    """防误杀：命令行不含 proxypool 的进程不被终止"""
    m = _make_manager(tmp_path)
    fake_proc = MagicMock()
    fake_proc.cmdline.return_value = ["python", "some_other.py"]
    with patch("psutil.Process", return_value=fake_proc):
        assert m._kill_pid(9999) is False
    fake_proc.terminate.assert_not_called()


def test_kill_pid_terminates_proxypool(tmp_path):
    m = _make_manager(tmp_path)
    fake_proc = MagicMock()
    fake_proc.cmdline.return_value = ["python", "main.py", "serve", "--port", "8082"]
    with patch("psutil.Process", return_value=fake_proc):
        assert m._kill_pid(12345) is True
    fake_proc.terminate.assert_called_once()


def test_stop_uses_pid_file_fallback(tmp_path):
    """复用分支（_proc=None）时 stop 仍通过 PID 文件清理旧进程"""
    m = _make_manager(tmp_path)
    m._proc = None  # 模拟热重载后新实例不持有子进程
    m._write_pid_file(99999)  # 残留 PID
    with patch.object(m, "_kill_pid", return_value=True) as mock_kill:
        m.stop()
    mock_kill.assert_called_once_with(99999)
    assert m._read_pid_file() is None  # PID 文件已清理