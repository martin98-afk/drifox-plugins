# ssh-toolkit/tools/auth.py
# -*- coding: utf-8 -*-
"""按 auth_type 建立 paramiko SSH 连接。"""
import os
import sys

# 注入 tools/ 目录到 sys.path（PluginToolLoader 用 importlib 加载时未自动注入，
# 同目录的 _store/_pool/_auth 相互 import 会报 No module named）。
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

# 注入插件自包含的 deps/ 目录（paramiko 不在主程序环境，依赖本插件自带）
_PLUGIN_DEPS = os.path.abspath(os.path.join(_TOOLS_DIR, "..", "deps"))
if _PLUGIN_DEPS not in sys.path:
    sys.path.insert(0, _PLUGIN_DEPS)

import paramiko  # noqa: E402

SUPPORTED = {"publickey", "password", "keyboard-interactive", "agent"}


def _client():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    return c


def connect(conn):
    auth_type = conn.get("auth_type", "publickey")
    if auth_type not in SUPPORTED:
        raise ValueError(f"不支持的 auth_type: {auth_type}，可选 {sorted(SUPPORTED)}")
    client = _client()
    host = conn["host"]
    port = int(conn.get("port", 22))
    user = conn.get("user")
    timeout = int(conn.get("timeout", 10))
    base = dict(hostname=host, port=port, username=user, timeout=timeout)
    if auth_type == "publickey":
        base.update(key_filename=os.path.expanduser(conn.get("key_path", "~/.ssh/id_rsa")),
                    passphrase=conn.get("key_passphrase") or None)
    elif auth_type == "password":
        base.update(password=conn.get("password"))
    elif auth_type == "agent":
        base.update(allow_agent=True, look_for_keys=False)
    elif auth_type == "keyboard-interactive":
        def _handler(title, instructions, prompts):
            return [conn.get("password", "")] * len(prompts)
        base.update(auth_interactive_callback=_handler)
    client.connect(**base)
    return client
