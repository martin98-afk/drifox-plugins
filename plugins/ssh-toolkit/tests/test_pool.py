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


def test_name_with_colon_resolves():
    """连接名含冒号（user@host:port）时，按名查池与按名断连必须命中。"""
    c = FakeClient()
    P.put_connection("root@10.0.0.5:22022", c)
    assert P.get_client("root@10.0.0.5:22022") is c
    assert P.close_by_name("root@10.0.0.5:22022") == 1
    assert c.closed is True


def test_empty_name_gets_placeholder():
    c = FakeClient()
    h = P.put_connection(None, c)
    assert not h.startswith("None:")
    assert P.get_client("conn") is c
