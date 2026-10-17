"""ssh_forward：绑定地址白名单、真实端口回报、未实现类型拒绝。"""
import socket
import sys
import types

import pytest


@pytest.fixture
def fwd_mod(monkeypatch):
    """stub 宿主 app.tools.result，独立测试 tools/forward.py。"""
    app = types.ModuleType("app")
    tools = types.ModuleType("app.tools")
    result = types.ModuleType("app.tools.result")

    class ToolResult:
        def __init__(self, success, content=None, error=None):
            self.success = success
            self.content = content
            self.error = error

    result.ToolResult = ToolResult
    monkeypatch.setitem(sys.modules, "app", app)
    monkeypatch.setitem(sys.modules, "app.tools", tools)
    monkeypatch.setitem(sys.modules, "app.tools.result", result)
    sys.modules.pop("forward", None)
    import forward

    return forward


class _Transport:
    def __init__(self):
        self.opened = 0

    def open_channel(self, kind, dst, src):
        self.opened += 1
        raise RuntimeError("测试不发真实流量")


class FakeClient:
    def __init__(self):
        self._t = _Transport()

    def get_transport(self):
        return self._t


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_public_bind_rejected_by_default(fwd_mod, monkeypatch):
    monkeypatch.setattr(fwd_mod.pool, "ensure_client", lambda ref: (FakeClient(), None))
    r = fwd_mod._forward_impl(None, handle="h", bind_addr="0.0.0.0", bind_port=12345, remote_port=80)
    assert r.success is False
    assert "回环" in r.error


def test_remote_type_rejected(fwd_mod, monkeypatch):
    monkeypatch.setattr(fwd_mod.pool, "ensure_client", lambda ref: (FakeClient(), None))
    r = fwd_mod._forward_impl(None, handle="h", type="remote", bind_port=12345, remote_port=80)
    assert r.success is False
    assert "仅实现 local" in r.error


def test_reports_real_port_when_zero(fwd_mod, monkeypatch):
    monkeypatch.setattr(fwd_mod.pool, "ensure_client", lambda ref: (FakeClient(), None))
    r = fwd_mod._forward_impl(None, handle="h", bind_port=0, remote_port=80)
    assert r.success is True, r.error
    assert ":0 " not in r.content and ":0→" not in r.content
    # 回报的端口应真的可连（监听已就绪）
    fid = r.content.split("转发 ")[1].split(":")[0]
    real = int(r.content.split("127.0.0.1:")[1].split(" ")[0])
    assert real > 0
    s = socket.create_connection(("127.0.0.1", real), timeout=2)
    s.close()
    # 清理监听
    for key in list(fwd_mod.FORWARDS):
        if key.startswith(f"fw:{fid}"):
            fwd_mod.FORWARDS[key]["stop"].set()


def test_bind_failure_reported(fwd_mod, monkeypatch):
    monkeypatch.setattr(fwd_mod.pool, "ensure_client", lambda ref: (FakeClient(), None))
    port = _free_port()
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", port))
    blocker.listen(1)
    try:
        r = fwd_mod._forward_impl(None, handle="h", bind_port=port, remote_port=80)
        assert r.success is False
        assert "转发启动失败" in r.error
    finally:
        blocker.close()
