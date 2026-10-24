"""ssh_exec 有界读取：远端灌数据不得撑爆内存、不得无限阻塞。

覆盖 _read_streams 的两条硬约束：
1. 单路输出达到 MAX_OUTPUT_BYTES 后停止累积并标记 truncated。
2. stdout 灌满时 stderr 仍在被消费（否则远端写 stderr 阻塞，通道锁死）。
"""
import sys
import types

import pytest


@pytest.fixture
def exec_mod(monkeypatch):
    """stub 掉宿主 app.tools.result，独立于主程序测试 tools/exec_tool.py。"""
    app = types.ModuleType("app")
    tools = types.ModuleType("app.tools")
    result = types.ModuleType("app.tools.result")

    class ToolResult:
        def __init__(self, success, content=None, error=None):
            self.success = success
            self.content = content
            self.error = error

        def __str__(self):
            return str(self.content) if self.success else f"[Error] {self.error}"

    result.ToolResult = ToolResult
    monkeypatch.setitem(sys.modules, "app", app)
    monkeypatch.setitem(sys.modules, "app.tools", tools)
    monkeypatch.setitem(sys.modules, "app.tools.result", result)
    sys.modules.pop("exec_tool", None)
    import exec_tool

    return exec_tool


class FakeChannel:
    """可控通道：按队列喂 stdout/stderr，exit 状态可指定。"""

    def __init__(self, out_chunks=(), err_chunks=(), exit_after=True):
        self._out = list(out_chunks)
        self._err = list(err_chunks)
        self._exit_after = exit_after
        self.closed = False

    def recv_ready(self):
        return bool(self._out)

    def recv_stderr_ready(self):
        return bool(self._err)

    def recv(self, n):
        return self._out.pop(0) if self._out else b""

    def recv_stderr(self, n):
        return self._err.pop(0) if self._err else b""

    def exit_status_ready(self):
        return self._exit_after and not self._out and not self._err

    def recv_exit_status(self):
        return 0

    def close(self):
        self.closed = True


def _deadline(seconds=5.0):
    import time

    return time.monotonic() + seconds


def test_read_streams_collects_both(exec_mod):
    ch = FakeChannel([b"out1", b"out2"], [b"err1"])
    out, err, cut = exec_mod._read_streams(ch, 1024, _deadline())
    assert out == b"out1out2"
    assert err == b"err1"
    assert cut is False


def test_read_streams_caps_output(exec_mod):
    big = [b"x" * 4096] * 200
    ch = FakeChannel(big, [], exit_after=False)
    out, err, cut = exec_mod._read_streams(ch, 8192, _deadline(2.0))
    assert len(out) <= 8192 + 32768
    assert cut is True


def test_read_streams_drains_stderr_while_stdout_flooded(exec_mod):
    """stdout 满额后 stderr 仍被消费，否则远端写 stderr 会锁死通道。"""
    out_chunks = [b"x" * 4096] * 10
    err_chunks = [b"e" * 64] * 5
    ch = FakeChannel(out_chunks, err_chunks, exit_after=False)
    out, err, _ = exec_mod._read_streams(ch, 4096, _deadline(2.0))
    assert len(out) <= 4096 + 32768
    assert b"e" * 64 in err


def test_read_streams_respects_deadline(exec_mod):
    """远端一直不给数据也不退出：到点必须返回，不能永久阻塞。"""

    class NeverEnding(FakeChannel):
        def exit_status_ready(self):
            return False

    ch = NeverEnding([], [])
    out, err, cut = exec_mod._read_streams(ch, 1024, _deadline(0.2))
    assert out == b"" and cut is True


def test_exit_status_times_out(exec_mod):
    class Never(FakeChannel):
        def exit_status_ready(self):
            return False

    assert exec_mod._exit_status(Never(), _deadline(0.1)) == -1


def test_exec_impl_truncates_and_marks(exec_mod, monkeypatch):
    big = [b"y" * 4096] * 200
    chan = FakeChannel(big, [], exit_after=True)

    class FakeStdout:
        channel = chan

    class FakeClient:
        def exec_command(self, command, timeout=None):
            return None, FakeStdout(), None

    monkeypatch.setattr(exec_mod.pool, "ensure_client", lambda ref: (FakeClient(), None))
    result = exec_mod._exec_impl(None, handle="h", command="cat /dev/urandom", timeout=2)
    assert result.success is True
    assert "输出已截断" in result.content
    assert len(result.content) < exec_mod.MAX_OUTPUT_BYTES * 3
