# ssh-toolkit/tools/pool.py
# -*- coding: utf-8 -*-
"""进程内 SSH 连接池，按 handle 复用 paramiko client。"""
import atexit
from uuid import uuid4

POOL: dict = {}


def put_connection(name, client):
    handle = f"{name}:{uuid4().hex[:8]}"
    POOL[handle] = client
    return handle


def get_client(ref):
    if ref in POOL:
        return POOL[ref]
    for handle, client in POOL.items():
        if handle.split(":", 1)[0] == ref:
            return client
    return None


def remove_connection_handle(handle):
    if handle in POOL:
        POOL.pop(handle, None)
        return True
    return False


def close_all():
    for client in POOL.values():
        try:
            client.close()
        except Exception:
            pass
    POOL.clear()


atexit.register(close_all)
