"""主机密钥策略（TOFU/strict/off）。"""
import pytest

import ssh_toolkit_auth as A


class FakeKey:
    """真实 paramiko PKey 替身（HostKeys.add 只接受 PKey 实例）。"""

    @staticmethod
    def make():
        import paramiko

        return paramiko.ECDSAKey.generate()

    def __init__(self, name="ssh-ed25519", raw=b"0123456789abcdef"):
        self._key = self.make()
        self._raw = raw

    def get_name(self):
        return self._key.get_name()

    def get_base64(self):
        return self._key.get_base64()

    def asbytes(self):
        return self._raw


@pytest.fixture
def known_hosts(tmp_path, monkeypatch):
    path = str(tmp_path / "known_hosts")
    monkeypatch.setattr(A, "known_hosts_path", lambda: path)
    return path


class RecordingClient:
    """替身：记录 policy 对象与 connect 参数，不碰网络。"""

    def __init__(self):
        self.policy = None
        self.kwargs = None
        self.system_keys_loaded = False
        self.host_keys_loaded = None
        self.closed = False

    def set_missing_host_key_policy(self, policy):
        self.policy = policy

    def load_system_host_keys(self):
        self.system_keys_loaded = True

    def load_host_keys(self, path):
        self.host_keys_loaded = path

    def connect(self, **kw):
        self.kwargs = kw

    def close(self):
        self.closed = True


@pytest.fixture
def fake_paramiko(monkeypatch):
    client = RecordingClient()
    monkeypatch.setattr(
        A,
        "paramiko",
        type(
            "P",
            (),
            {
                "SSHClient": lambda: client,
                "AutoAddPolicy": type("AutoAddPolicy", (), {}),
                "HostKeys": __import__("paramiko").HostKeys,
                "MissingHostKeyPolicy": __import__("paramiko").MissingHostKeyPolicy,
                "SSHException": __import__("paramiko").SSHException,
            },
        ),
    )
    return client


def _conn(**extra):
    base = {"host": "h", "port": 22, "user": "u", "auth_type": "password", "password": "pw", "timeout": 10}
    base.update(extra)
    return base


def test_default_policy_is_tofu_not_autoadd(fake_paramiko, known_hosts):
    A.connect(_conn())
    assert isinstance(fake_paramiko.policy, A._TofuPolicy)
    assert not isinstance(fake_paramiko.policy, A.paramiko.AutoAddPolicy)


def test_system_known_hosts_loaded(fake_paramiko, known_hosts):
    A.connect(_conn())
    assert fake_paramiko.system_keys_loaded is True


def test_plugin_known_hosts_loaded_when_exists(fake_paramiko, known_hosts):
    with open(known_hosts, "w", encoding="utf-8") as f:
        f.write("")
    A.connect(_conn())
    assert fake_paramiko.host_keys_loaded == known_hosts


def test_tofu_records_new_host_fingerprint(fake_paramiko, known_hosts):
    client = A.connect(_conn())
    policy = fake_paramiko.policy
    key = FakeKey()
    policy.missing_host_key(fake_paramiko, "example.com", key)
    record = getattr(client, "_drifox_new_host_keys")
    assert record and record[0]["host"] == "example.com"
    assert record[0]["fingerprint"].startswith("SHA256:")
    # 已落盘：再次读取 known_hosts 应含该主机
    import paramiko

    hosts = paramiko.HostKeys(known_hosts)
    assert hosts.lookup("example.com") is not None


def test_tofu_fingerprint_matches_sha256(fake_paramiko, known_hosts):
    import base64
    import hashlib

    key = FakeKey(raw=b"abcdefghij")
    expect = "SHA256:" + base64.b64encode(hashlib.sha256(b"abcdefghij").digest()).decode().rstrip("=")
    assert A.fingerprint(key) == expect


def test_strict_policy_rejects_unknown_host(fake_paramiko, known_hosts):
    import paramiko

    A.connect(_conn(host_key_policy="strict"))
    assert isinstance(fake_paramiko.policy, A._StrictPolicy)
    with pytest.raises(paramiko.SSHException, match="未知主机"):
        fake_paramiko.policy.missing_host_key(fake_paramiko, "example.com", FakeKey())


def test_policy_off_uses_autoadd(fake_paramiko, known_hosts):
    A.connect(_conn(host_key_policy="off"))
    assert isinstance(fake_paramiko.policy, A.paramiko.AutoAddPolicy)


def test_invalid_policy_raises(fake_paramiko, known_hosts):
    with pytest.raises(ValueError, match="host_key_policy"):
        A.connect(_conn(host_key_policy="whatever"))


def test_policy_attached_to_client(fake_paramiko, known_hosts):
    client = A.connect(_conn(host_key_policy="strict"))
    assert getattr(client, "_drifox_host_key_policy") == "strict"
