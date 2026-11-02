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


def test_drifox_workspaces_exempt_from_block_dirs(tmp_path):
    """~/.drifox 整棵在黑名单，但 workspaces 子树豁免（用户项目工作区）。"""
    fake_home = tmp_path / "home"
    drifox = fake_home / ".drifox"
    workspaces = drifox / "workspaces" / "proj"
    workspaces.mkdir(parents=True)
    conn = drifox / "connections.json"
    conn.write_text("{}", encoding="utf-8")
    ok_file = workspaces / "data.txt"
    ok_file.write_text("d", encoding="utf-8")

    orig_dirs = G._BLOCK_DIRS
    orig_exempt = G._EXEMPT_SUBTREES
    try:
        G._BLOCK_DIRS = (str(drifox),)
        G._EXEMPT_SUBTREES = (str(drifox / "workspaces"),)
        # 豁免子树内：放行
        assert G.check_local_read(str(ok_file), {"workdir": str(workspaces)})[0] is True
        assert G.check_local_write(str(ok_file), {"workdir": str(workspaces)})[0] is True
        # 豁免子树外（.drifox 根下凭据落盘）：仍拒
        ok, reason = G.check_local_read(str(conn), {"workdir": str(workspaces)})
        assert ok is False and "受保护目录" in reason
        # 豁免子树内凭据文件名黑名单仍生效
        ok, reason = G.check_local_read(str(workspaces / ".env"), {"workdir": str(workspaces)})
        assert ok is False and "凭据类文件" in reason
    finally:
        G._BLOCK_DIRS = orig_dirs
        G._EXEMPT_SUBTREES = orig_exempt

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
