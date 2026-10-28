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


def test_upsert_creates_with_metadata(tmp_store):
    name, created = S.upsert_connection({"host": "1.1.1.1", "user": "root", "port": 22})
    assert created is True
    assert name == "root@1.1.1.1"  # 未命名时按 user@host 生成
    c = S.get_connection(name)
    assert c["connect_count"] == 1
    assert c["last_connected"]


def test_upsert_default_name_keeps_port(tmp_store):
    name, _ = S.upsert_connection({"host": "1.1.1.1", "user": "root", "port": 22022})
    assert name == "root@1.1.1.1:22022"


def test_upsert_existing_bumps_count_and_keeps_password(tmp_store):
    S.upsert_connection({"host": "1.1.1.1", "user": "root", "password": "secret"})
    # 二次连接只传 host/user（没带密码）：不能把已存密码洗成空
    name, created = S.upsert_connection({"host": "1.1.1.1", "user": "root"})
    assert created is False
    c = S.get_connection("root@1.1.1.1")
    assert c["password"] == "secret"
    assert c["connect_count"] == 2


def test_upsert_requires_host_and_user(tmp_store):
    with pytest.raises(ValueError):
        S.upsert_connection({"host": "1.1.1.1"})
