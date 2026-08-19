import ssh_toolkit_pool as P


class FakeClient:
    closed = False

    def close(self):
        self.closed = True


def test_put_get_handle():
    c = FakeClient()
    h = P.put_connection("h1", c)
    assert h.startswith("h1:")
    assert P.get_client(h) is c


def test_get_by_name():
    c = FakeClient()
    P.put_connection("h2", c)
    assert P.get_client("h2") is c


def test_remove():
    c = FakeClient()
    h = P.put_connection("h3", c)
    assert P.remove_connection_handle(h) is True
    assert P.get_client(h) is None


def test_close_all():
    c = FakeClient()
    P.put_connection("h4", c)
    P.close_all()
    assert c.closed is True
