# ssh-toolkit/tools/store.py
# -*- coding: utf-8 -*-
"""连接配置读写：~/.drifox/cache/ssh/connections.json（明文，600 权限）"""
import json
import os
from pathlib import Path

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
