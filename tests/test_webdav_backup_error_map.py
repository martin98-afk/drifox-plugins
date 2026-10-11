# -*- coding: utf-8 -*-
"""webdav-backup 错误映射回归测试

背景（2026-10-11 线上 bug）：坚果云上传流量超额返回 HTTP 403 +
<s:exception>TrafficRateExhausted</s:exception>，而 engine 把 401 与 403
一律映射为「认证失败…请确认使用应用密码」，把配额问题误报成密码问题，
误导排查方向（实际凭证完全正常）。

本测试锁定：401 才归因认证；403 按 DAV 专有异常名区分配额/流量/未知原因。
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "webdav-backup"


def _load(name: str, rel: str):
    """从文件路径加载独立插件模块（无相对导入时用）

    插件目录名带连字符无法常规 import，故走 importlib。
    webdavbackup_core 包内模块（含相对导入）改用 _import_pkg。
    """
    full = f"webdav_backup_test_{name}"
    if full in sys.modules:
        return sys.modules[full]
    if str(_PLUGIN) not in sys.path:
        sys.path.insert(0, str(_PLUGIN))
    spec = importlib.util.spec_from_file_location(full, _PLUGIN / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def webdav_mod():
    return _load("webdav", "webdavbackup_core/webdav.py")


@pytest.fixture(scope="module")
def engine_mod():
    """engine 内部用相对导入（from . import config），须按包正常导入"""
    if str(_PLUGIN) not in sys.path:
        sys.path.insert(0, str(_PLUGIN))
    import webdavbackup_core.engine as engine

    return engine


# ============================================================
#  异常名抽取
# ============================================================


def test_extract_dav_exception(webdav_mod):
    """坚果云把机器可读原因放在 <s:exception>，须能抽出"""
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<d:error xmlns:d="DAV:" xmlns:s="http://ns.jianguoyun.com">'
        "<s:exception>TrafficRateExhausted</s:exception>"
        "<s:message>The upstream traffic rate is ...</s:message></d:error>"
    )
    assert webdav_mod._extract_dav_exception(body) == "TrafficRateExhausted"


def test_extract_dav_exception_absent(webdav_mod):
    """无 exception 标签时返回空串，不抛错"""
    assert webdav_mod._extract_dav_exception("<d:error/>") == ""
    assert webdav_mod._extract_dav_exception("") == ""


# ============================================================
#  错误映射
# ============================================================


def test_401_maps_to_auth(engine_mod, webdav_mod):
    e = webdav_mod.WebDAVError("HTTP 401", status=401)
    msg = engine_mod._describe_webdav_error(e)
    assert "认证失败(401)" in msg
    assert "应用密码" in msg


def test_403_traffic_rate_not_auth(engine_mod, webdav_mod):
    """核心回归：403 + TrafficRateExhausted 必须归因流量，且不得再提密码"""
    e = webdav_mod.WebDAVError(
        "HTTP 403 PUT",
        status=403,
        detail="<s:exception>TrafficRateExhausted</s:exception>",
        dav_exception="TrafficRateExhausted",
    )
    msg = engine_mod._describe_webdav_error(e)
    assert "上传流量超额" in msg
    assert "密码" not in msg, "回归：403 流量超额曾被误报为密码问题"


def test_403_over_quota(engine_mod, webdav_mod):
    e = webdav_mod.WebDAVError("HTTP 403", status=403, dav_exception="OverQuota")
    assert "存储空间不足" in engine_mod._describe_webdav_error(e)


def test_403_unknown_keeps_server_detail(engine_mod, webdav_mod):
    """未知 403 原因：带出服务器原文，不臆断为认证问题"""
    e = webdav_mod.WebDAVError("HTTP 403", status=403, detail="<s:message>自定义拒绝</s:message>")
    msg = engine_mod._describe_webdav_error(e)
    assert "自定义拒绝" in msg
    assert "应用密码" not in msg


def test_507_quota(engine_mod, webdav_mod):
    e = webdav_mod.WebDAVError("HTTP 507", status=507)
    assert "存储空间不足" in engine_mod._describe_webdav_error(e)


def test_no_status_passthrough(engine_mod, webdav_mod):
    """无状态码（网络类错误）原样透传，不被错误归类"""
    e = webdav_mod.WebDAVError("网络错误 PROPFIND /dav/: timed out")
    assert "timed out" in engine_mod._describe_webdav_error(e)


def test_webdav_error_defaults(webdav_mod):
    """新增字段有默认值，旧调用点不破"""
    e = webdav_mod.WebDAVError("boom")
    assert e.status == 0
    assert e.detail == ""
    assert e.dav_exception == ""
