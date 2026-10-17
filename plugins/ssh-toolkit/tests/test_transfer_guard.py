"""ssh_upload / ssh_download 的本地路径边界：拒绝时不得建立 SFTP 连接。"""
import os
import sys
import types

import pytest


@pytest.fixture
def transfer_mod(monkeypatch):
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
    sys.modules.pop("transfer", None)
    import transfer

    return transfer


class RecordingClient:
    def __init__(self):
        self.sftp_opened = 0
        self.commands = []

    def exec_command(self, cmd):
        self.commands.append(cmd)

        class _F:
            def read(self):
                return b"/home/u\n"

        return None, _F(), None

    def open_sftp(self):
        self.sftp_opened += 1
        raise AssertionError("路径被拒时不应建立 SFTP 连接")


def _wire(monkeypatch, mod):
    client = RecordingClient()
    monkeypatch.setattr(mod.pool, "ensure_client", lambda ref: (client, None))
    return client


def test_upload_rejects_ssh_key(transfer_mod, monkeypatch, tmp_path):
    client = _wire(monkeypatch, transfer_mod)
    key = os.path.join(os.path.expanduser("~"), ".ssh", "id_rsa")
    r = transfer_mod._upload_impl({"workdir": str(tmp_path)}, handle="h", local_path=key, remote_path="/tmp/x")
    assert r.success is False
    assert "受保护目录" in r.error or "凭据类文件" in r.error
    assert client.sftp_opened == 0


def test_upload_rejects_outside_workdir(transfer_mod, monkeypatch, tmp_path):
    client = _wire(monkeypatch, transfer_mod)
    outside = str(tmp_path.parent / "outside.txt")
    r = transfer_mod._upload_impl(
        {"workdir": str(tmp_path)}, handle="h", local_path=outside, remote_path="/tmp/x"
    )
    assert r.success is False
    assert "超出允许范围" in r.error
    assert client.sftp_opened == 0


def test_upload_allows_allow_paths(transfer_mod, monkeypatch, tmp_path):
    client = _wire(monkeypatch, transfer_mod)
    extra = tmp_path.parent / "extra_zone"
    extra.mkdir(exist_ok=True)
    target = extra / "ok.txt"
    target.write_text("x", encoding="utf-8")
    r = transfer_mod._upload_impl(
        {"workdir": str(tmp_path)},
        handle="h",
        local_path=str(target),
        remote_path="/tmp/x",
        allow_paths=[str(extra)],
    )
    # 越过边界检查后才会走到 open_sftp（此处故意抛错以证明放行）
    assert r.success is False
    assert "上传失败" in r.error
    assert client.sftp_opened == 1


def test_download_rejects_startup_dir(transfer_mod, monkeypatch, tmp_path):
    client = _wire(monkeypatch, transfer_mod)
    import transfer

    saved = transfer.guard._BLOCK_TARGET_DIRS
    fake = tmp_path / "startup"
    fake.mkdir()
    try:
        transfer.guard._BLOCK_TARGET_DIRS = (str(fake),)
        r = transfer_mod._download_impl(
            {"workdir": str(tmp_path)}, handle="h", remote_path="/etc/x", local_path=str(fake / "evil.exe")
        )
        assert r.success is False
        assert "自启动" in r.error
        assert client.sftp_opened == 0
    finally:
        transfer.guard._BLOCK_TARGET_DIRS = saved


def test_download_rejects_env(transfer_mod, monkeypatch, tmp_path):
    client = _wire(monkeypatch, transfer_mod)
    r = transfer_mod._download_impl(
        {"workdir": str(tmp_path)}, handle="h", remote_path="/etc/x", local_path=str(tmp_path / ".env")
    )
    assert r.success is False
    assert client.sftp_opened == 0
