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


def ensure_client(ref):
    """解析活跃连接；无活跃连接但 ref 命中已保存配置时自动建连入池。

    返回 (client, error_msg)：成功时 error_msg 为 None，失败时 client 为 None。
    """
    client = get_client(ref)
    if client is not None:
        return client, None
    # 懒连接：ref 作为已保存连接名时，按配置自动建立连接
    try:
        from _store import get_connection
        from _auth import connect
    except ImportError as e:
        name = getattr(e, "name", "") or "paramiko/cryptography"
        return None, (
            f"自动连接失败：依赖 {name} 加载失败（{e}）。"
            "请在 DriFox 所在 Python 环境执行：pip install --upgrade paramiko cryptography"
        )
    except Exception:
        return None, f"未找到活跃连接：{ref}（先 ssh_connect）"
    conn = get_connection(ref)
    if conn is None:
        return None, f"未找到活跃连接：{ref}（先 ssh_connect）"
    try:
        client = connect(conn)
    except Exception as e:
        return None, f"自动连接失败：{e}"
    put_connection(ref, client)
    return client, None


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
