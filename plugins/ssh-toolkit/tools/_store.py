# ssh-toolkit/tools/store.py
# -*- coding: utf-8 -*-
"""连接配置读写：~/.drifox/cache/ssh/connections.json（明文，600 权限）"""
import json
import os

CACHE_DIR = os.path.join(os.path.expanduser("~"), ".drifox", "cache", "ssh")
CONNECTIONS_PATH = os.path.join(CACHE_DIR, "connections.json")
_MASK = "****"
_EMPTY = {"version": 1, "connections": []}


def _ensure_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def load_connections():
    if not os.path.exists(CONNECTIONS_PATH):
        return {"version": 1, "connections": []}
    with open(CONNECTIONS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_connections(data):
    _ensure_dir()
    with open(CONNECTIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.chmod(CONNECTIONS_PATH, 0o600)


def get_connection(name):
    for c in load_connections()["connections"]:
        if c.get("name") == name:
            return c
    return None


def add_connection(conn):
    if not conn.get("name"):
        raise ValueError("connection 必须含 name")
    data = load_connections()
    for c in data["connections"]:
        if c.get("name") == conn["name"]:
            raise ValueError(f"连接名已存在: {conn['name']}")
    data["connections"].append(conn)
    save_connections(data)


def default_name(conn):
    """未指定连接名时的默认命名：user@host（非 22 端口带端口号）。"""
    user = str(conn.get("user") or "").strip() or "user"
    host = str(conn.get("host") or "").strip() or "host"
    try:
        port = int(conn.get("port") or 22)
    except (TypeError, ValueError):
        port = 22
    return f"{user}@{host}" if port == 22 else f"{user}@{host}:{port}"


# 空值不覆盖已存字段：运行时直连往往只传 host/user，不能把已存的密码洗成空
_SKIP_EMPTY = (None, "")


def upsert_connection(conn):
    """连接成功后自动落库，返回 (落库用的连接名, 是否新建)。

    - 同名连接：合并本次传入的非空字段，累加 connect_count，刷新 last_connected
    - 新连接：新增一条，connect_count=1
    没有 name 时按 user@host（非 22 端口带端口）生成，保证同目标重复连接不产生多条。
    """
    import datetime

    if not conn.get("host") or not conn.get("user"):
        raise ValueError("connection 必须含 host 与 user")
    name = str(conn.get("name") or "").strip() or default_name(conn)
    data = load_connections()
    now = datetime.datetime.now().isoformat(timespec="seconds")

    for c in data["connections"]:
        if c.get("name") != name:
            continue
        for key, value in conn.items():
            if value in _SKIP_EMPTY:
                continue
            c[key] = value
        c["name"] = name
        c["last_connected"] = now
        c["connect_count"] = int(c.get("connect_count") or 0) + 1
        save_connections(data)
        return name, False

    record = {k: v for k, v in conn.items() if v not in _SKIP_EMPTY}
    record["name"] = name
    record["last_connected"] = now
    record["connect_count"] = 1
    data["connections"].append(record)
    save_connections(data)
    return name, True


def remove_connection(name):
    data = load_connections()
    before = len(data["connections"])
    data["connections"] = [c for c in data["connections"] if c.get("name") != name]
    if len(data["connections"]) == before:
        return False
    save_connections(data)
    return True


def mask_passwords(data):
    import copy
    d = copy.deepcopy(data)
    for c in d.get("connections", []):
        if c.get("password"):
            c["password"] = _MASK
        if c.get("key_passphrase"):
            c["key_passphrase"] = _MASK
    return d
