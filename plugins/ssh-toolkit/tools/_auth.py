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


def _ensure_openssl_path():
    """让 deps/cryptography 的 _rust.pyd 找到 libcrypto/libssl。

    pip 风格的 cryptography 需要系统 OpenSSL 动态库；conda 默认放在
    ``$CONDA_PREFIX/Library/bin`` 且不在 PATH 里，导致 _rust.pyd 加载失败。
    该函数把含 libcrypto*/libssl* 的目录 prepend 到 PATH。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    cands = []
    cp = os.environ.get("CONDA_PREFIX") or ""
    if cp:
        cands.append(os.path.join(cp, "Library", "bin"))
        cands.append(os.path.join(cp, "bin"))
    cands.append(os.path.abspath(os.path.join(here, "..", "deps", "bin")))
    for d in cands:
        if d and os.path.isdir(d):
            if any(
                f.lower().startswith(("libcrypto", "libssl"))
                and f.lower().endswith((".dll", ".so", ".dylib"))
                for f in os.listdir(d)
            ):
                cur = os.environ.get("PATH", "")
                if d not in cur.split(os.pathsep):
                    os.environ["PATH"] = d + os.pathsep + cur
                return d
    return None


_ensure_openssl_path()
# 优先主环境 paramiko（pip 装到 conda env 后与 cryptography 兼容），缺失时降级插件自包含 deps/
try:
    import paramiko  # noqa: E402
except ImportError:
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
