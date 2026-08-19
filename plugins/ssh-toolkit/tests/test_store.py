import os
import pytest
import ssh_toolkit_store as S


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    p = tmp_path / "connections.json"
    monkeypatch.setattr(S, "CONNECTIONS_PATH", str(p))
    return p


def test_load_empty(tmp_store):
    d = S.load_connections()
    assert d == {"version": 1, "connections": []}


def test_add_and_get(tmp_store):
    S.add_connection({"name": "h1", "host": "1.1.1.1", "user": "u", "auth_type": "password", "password": "secret"})
    c = S.get_connection("h1")
    assert c["host"] == "1.1.1.1"
    assert c["password"] == "secret"


def test_add_duplicate_raises(tmp_store):
    S.add_connection({"name": "h1", "host": "1.1.1.1", "user": "u", "auth_type": "publickey"})
    with pytest.raises(ValueError):
        S.add_connection({"name": "h1", "host": "2.2.2.2", "user": "u", "auth_type": "publickey"})


def test_remove(tmp_store):
    S.add_connection({"name": "h1", "host": "1.1.1.1", "user": "u", "auth_type": "publickey"})
    assert S.remove_connection("h1") is True
    assert S.get_connection("h1") is None


def test_mask(tmp_store):
    data = {"version": 1, "connections": [{"name": "h1", "password": "p", "key_passphrase": "k"}]}
    m = S.mask_passwords(data)
    assert m["connections"][0]["password"] == "****"
    assert m["connections"][0]["key_passphrase"] == "****"
    assert data["connections"][0]["password"] == "p"  # 原数据不变


def test_chmod_600(tmp_store):
    import sys
    S.add_connection({"name": "h1", "host": "1.1.1.1", "user": "u", "auth_type": "publickey"})
    if sys.platform != "win32":
        mode = os.stat(str(tmp_store)).st_mode & 0o777
        assert mode == 0o600
    else:
        # Windows 不支持 Unix 权限位，仅确认文件已落盘
        assert os.path.exists(str(tmp_store))
