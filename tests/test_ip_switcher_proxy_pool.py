# -*- coding: utf-8 -*-
"""ip-switcher proxy_pool 单元测试（mock HTTP 层）"""
from unittest.mock import patch

from ip_switcher_proxy_pool import ProxyPoolManager


def _make_manager():
    return ProxyPoolManager(stats_port=18083, proxy_port=18082, data_dir=None)


def test_rotate_returns_current_ip():
    m = _make_manager()
    with patch.object(m, "_request", return_value={"current": "103.216.72.14"}):
        assert m.rotate() == "103.216.72.14"


def test_rotate_failure_returns_none():
    m = _make_manager()
    with patch.object(m, "_request", return_value={"error": "池子为空"}):
        assert m.rotate() is None


def test_set_mode_sticky():
    m = _make_manager()
    with patch.object(m, "_request", return_value={"mode": "sticky"}):
        assert m.set_mode("sticky") is True


def test_get_stats():
    m = _make_manager()
    with patch.object(m, "_request", return_value={"current": "1.2.3.4", "pool_size": 10}):
        stats = m.get_stats()
        assert stats["pool_size"] == 10