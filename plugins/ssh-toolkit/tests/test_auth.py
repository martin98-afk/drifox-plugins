import ssh_toolkit_auth as A


class FakeClient:
    def __init__(self):
        self.kwargs = None
        self.closed = False

    def set_missing_host_key_policy(self, p):
        pass

    def connect(self, **kw):
        self.kwargs = kw

    def close(self):
        self.closed = True


def _mock(monkeypatch):
    fc = FakeClient()
    monkeypatch.setattr(A, "paramiko", type("P", (), {"SSHClient": lambda: fc, "AutoAddPolicy": object}))
    return fc


def test_publickey(monkeypatch):
    import os
    fc = _mock(monkeypatch)
    A.connect({"host": "h", "port": 22, "user": "u", "auth_type": "publickey", "key_path": "~/.ssh/id_rsa", "key_passphrase": "kp", "timeout": 10})
    assert fc.kwargs["key_filename"] == os.path.expanduser("~/.ssh/id_rsa")
    assert fc.kwargs["passphrase"] == "kp"


def test_password(monkeypatch):
    fc = _mock(monkeypatch)
    A.connect({"host": "h", "port": 22, "user": "u", "auth_type": "password", "password": "pw", "timeout": 10})
    assert fc.kwargs["password"] == "pw"


def test_unsupported(monkeypatch):
    fc = _mock(monkeypatch)
    try:
        A.connect({"host": "h", "port": 22, "user": "u", "auth_type": "ldap", "timeout": 10})
        assert False, "应抛 ValueError"
    except ValueError:
        pass
