import types

import pytest

from test_tool_args import _load, stub_app_result  # noqa: F401


class FakeChannel:
    def __init__(self):
        self.closed = False

    def recv_ready(self):
        return False

    def recv_stderr_ready(self):
        return False

    def recv(self, n):
        return b""

    def recv_stderr(self, n):
        return b""

    def exit_status_ready(self):
        return True

    def recv_exit_status(self):
        return 0

    def close(self):
        self.closed = True


class FakeClient:
    def exec_command(self, command, timeout=None):
        return None, types.SimpleNamespace(channel=FakeChannel()), None


@pytest.fixture
def exec_mod(monkeypatch, stub_app_result):  # noqa: F811
    mod = _load(monkeypatch, "exec", "exec_tool.py")
    monkeypatch.setattr(mod.pool, "ensure_client", lambda ref: (FakeClient(), None))
    return mod


@pytest.fixture
def conn_mgmt_mod(monkeypatch, stub_app_result):  # noqa: F811
    return _load(monkeypatch, "conn_mgmt", "conn_mgmt.py")


@pytest.fixture
def forward_mod(monkeypatch, stub_app_result):  # noqa: F811
    return _load(monkeypatch, "forward", "forward.py")


def test_exec_none_timeout(exec_mod):
    """LLM 显式传 timeout=None 时不得炸 int(None)，按默认 30s 执行。"""
    r = exec_mod._exec_impl(None, handle="h", command="echo hi", timeout=None)
    assert r.success is True, r.error
    assert "exit=0" in r.content


def test_exec_missing_timeout(exec_mod):
    r = exec_mod._exec_impl(None, handle="h", command="echo hi")
    assert r.success is True, r.error


def test_exec_string_timeout(exec_mod):
    """模型有时把 integer 参数序列化成字符串。"""
    r = exec_mod._exec_impl(None, handle="h", command="echo hi", timeout="45")
    assert r.success is True, r.error


def test_connect_autosaves_normalized_args(exec_mod, monkeypatch):
    """连接成功即落库：port/timeout 传 None 时归一成默认值再写盘。"""
    saved = {}
    monkeypatch.setattr(exec_mod.store, "get_connection", lambda name: None)
    monkeypatch.setattr(
        exec_mod.store, "upsert_connection", lambda conn: (saved.update(conn) or ("n1", True))
    )
    monkeypatch.setattr(exec_mod.auth, "connect", lambda conn: object())
    monkeypatch.setattr(exec_mod.pool, "put_connection", lambda name, client: f"{name}:h")
    r = exec_mod._connect_impl(None, name="n1", host="h", user="u", port=None, timeout=None)
    assert r.success is True, r.error
    assert saved["port"] == 22
    assert saved["timeout"] == 10
    assert "已记录连接" in r.content


def test_connect_autosaves_string_port(exec_mod, monkeypatch):
    """模型有时把 integer 参数序列化成字符串，落库前必须归一。"""
    saved = {}
    monkeypatch.setattr(exec_mod.store, "get_connection", lambda name: None)
    monkeypatch.setattr(
        exec_mod.store, "upsert_connection", lambda conn: (saved.update(conn) or ("n2", True))
    )
    monkeypatch.setattr(exec_mod.auth, "connect", lambda conn: object())
    monkeypatch.setattr(exec_mod.pool, "put_connection", lambda name, client: f"{name}:h")
    r = exec_mod._connect_impl(None, name="n2", host="h", user="u", port="22022", timeout="30")
    assert r.success is True, r.error
    assert saved["port"] == 22022
    assert saved["timeout"] == 30


def test_connect_still_works_when_save_fails(exec_mod, monkeypatch):
    """落库失败不能连坐连接本身：仍返回成功，只提示未保存。"""
    monkeypatch.setattr(exec_mod.store, "get_connection", lambda name: None)

    def boom(conn):
        raise OSError("disk full")

    monkeypatch.setattr(exec_mod.store, "upsert_connection", boom)
    monkeypatch.setattr(exec_mod.auth, "connect", lambda conn: object())
    monkeypatch.setattr(exec_mod.pool, "put_connection", lambda name, client: "h:h")
    r = exec_mod._connect_impl(None, host="h", user="u")
    assert r.success is True, r.error
    assert "连接配置未保存" in r.content


def test_forward_none_ports(forward_mod, monkeypatch):
    """bind_port/remote_port 为 None 时必须给出可读错误，而不是 TypeError。"""
    monkeypatch.setattr(forward_mod.guard, "check_bind_addr", lambda a, p: (True, ""))
    monkeypatch.setattr(forward_mod.pool, "ensure_client", lambda ref: (None, "no conn"))
    r = forward_mod._forward_impl(
        None, handle="h", bind_port=None, remote_port=None, remote_addr="127.0.0.1"
    )
    assert r.success is False
    assert "NoneType" not in (r.error or "")


def test_forward_zero_bind_port_still_allowed(forward_mod, monkeypatch):
    """bind_port=0 是合法语义（内核分配端口），不得被参数归一化误杀。

    回归点：早期修法用 ``if not bind_port`` 一并拒掉 0，破坏了
    test_reports_real_port_when_zero 约定的"回报真实端口"行为。
    """
    monkeypatch.setattr(forward_mod.guard, "check_bind_addr", lambda a, p: (True, ""))
    monkeypatch.setattr(forward_mod.pool, "ensure_client", lambda ref: (None, "占位"))
    r = forward_mod._forward_impl(None, handle="h", bind_port=0, remote_port=22)
    # 走到 ensure_client 说明端口校验放行；此处 pool 返回 None 故报未找到连接
    assert r.success is False
    assert "NoneType" not in (r.error or "")
    assert "remote_port" not in (r.error or "")


def test_auth_connect_none_port_timeout(monkeypatch, stub_app_result):  # noqa: F811
    """手写配置 / 旧版本写入 null 时，连接参数不得炸 int(None)。"""
    auth = _load(monkeypatch, "auth", "_auth.py")
    captured = {}

    class RecordingClient:
        def set_missing_host_key_policy(self, p):
            pass

        def load_system_host_keys(self):
            pass

        def load_host_keys(self, path):
            pass

        def connect(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(auth, "paramiko", type("P", (), {"SSHClient": lambda: RecordingClient()}))
    auth.connect(
        {"host": "h", "port": None, "user": "u", "auth_type": "password", "password": "pw", "timeout": None}
    )
    assert captured["port"] == 22
    assert captured["timeout"] == 10
