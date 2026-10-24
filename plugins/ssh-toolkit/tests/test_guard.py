import os

import pytest

import ssh_toolkit_guard as G


@pytest.fixture
def workdir(tmp_path):
    return str(tmp_path)


def test_inside_workdir_allowed(workdir):
    p = os.path.join(workdir, "a.txt")
    assert G.check_local_read(p, {"workdir": workdir})[0] is True
    assert G.check_local_write(p, {"workdir": workdir})[0] is True


def test_outside_workdir_rejected(workdir):
    ok, reason = G.check_local_read(os.path.join(workdir, "..", "x.txt"), {"workdir": workdir})
    assert ok is False and "超出允许范围" in reason


def test_allow_paths_extends_root(workdir, tmp_path_factory):
    extra = tmp_path_factory.mktemp("extra")
    p = str(extra / "b.txt")
    assert G.check_local_write(p, {"workdir": workdir})[0] is False
    assert G.check_local_write(p, {"workdir": workdir}, [str(extra)])[0] is True


def test_ssh_dir_blocked_even_if_inside_workdir(tmp_path):
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir()
    key = ssh_dir / "id_rsa"
    key.write_text("k", encoding="utf-8")
    # allow_paths 显式放行也不行：凭据目录是硬黑名单
    ok, reason = G.check_local_read(str(key), {"workdir": str(tmp_path)}, [str(tmp_path)])
    assert ok is False
    assert "受保护目录" in reason or "凭据类文件" in reason


def test_env_file_blocked(workdir):
    env = os.path.join(workdir, ".env")
    ok, reason = G.check_local_read(env, {"workdir": workdir})
    assert ok is False and "凭据类文件" in reason


def test_sessions_db_blocked(workdir):
    ok, reason = G.check_local_read(os.path.join(workdir, "sessions.db"), {"workdir": workdir})
    assert ok is False


def test_startup_dir_blocked_for_write(tmp_path):
    fake_appdata = tmp_path / "appdata" / "roaming"
    startup = fake_appdata / "microsoft" / "windows" / "start menu" / "programs" / "startup"
    startup.mkdir(parents=True)
    target = startup / "evil.exe"
    import ssh_toolkit_guard as GG

    orig = GG._BLOCK_TARGET_DIRS
    try:
        GG._BLOCK_TARGET_DIRS = (str(startup),)
        ok, reason = GG.check_local_write(str(target), {"workdir": str(tmp_path)})
        assert ok is False and "自启动" in reason
    finally:
        GG._BLOCK_TARGET_DIRS = orig


def test_no_workdir_falls_back_to_home():
    home_file = os.path.join(os.path.expanduser("~"), "note.txt")
    assert G.check_local_write(home_file, {})[0] is True


def test_bind_addr_default_loopback_only():
    assert G.check_bind_addr("127.0.0.1")[0] is True
    assert G.check_bind_addr("")[0] is True
    ok, reason = G.check_bind_addr("0.0.0.0")
    assert ok is False and "回环" in reason
    assert G.check_bind_addr("0.0.0.0", allow_public=True)[0] is True


def test_symlink_escape_blocked(tmp_path):
    """符号链接指向受保护目录时 realpath 解析后仍被拒。"""
    secrets = tmp_path / ".ssh"
    secrets.mkdir()
    key = secrets / "id_ed25519"
    key.write_text("k", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    link = work / "innocent.txt"
    try:
        os.symlink(str(key), str(link))
    except (OSError, NotImplementedError):
        pytest.skip("当前环境不支持创建符号链接")
    ok, _ = G.check_local_read(str(link), {"workdir": str(work)})
    assert ok is False
