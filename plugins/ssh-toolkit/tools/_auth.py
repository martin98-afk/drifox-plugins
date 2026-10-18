# ssh-toolkit/tools/auth.py
# -*- coding: utf-8 -*-
"""按 auth_type 建立 paramiko SSH 连接。

主机密钥策略（conn["host_key_policy"]，默认 tofu）：
- tofu：首次连接记录指纹并写入插件自有 known_hosts，之后不一致即由 paramiko
  抛 BadHostKeyException 硬拒（原 AutoAddPolicy 等于完全关掉主机身份校验，
  DNS 劫持/ARP 欺骗即可中间人截获全部命令与凭据）。
- strict：未知主机直接拒绝，只认已登记条目。
- off：退回 AutoAddPolicy，仅为兼容旧行为保留，需用户显式声明。

加密后端仲裁（_prefer_vendored_crypto）：cx_Freeze 打包版的 FrozenImporter
挂在 sys.meta_path，优先于 sys.path —— 宿主内嵌的 cryptography 会截胡 import，
paramiko 因此被绑到宿主副本上（实测该副本 AES-CTR 不可用，报
cipher AES in CTR mode is not supported）。此处在 import paramiko 前把
cryptography* 的 import 强制指到插件 deps 目录，自检通过才保留，失败回滚。
"""
import base64
import hashlib
import importlib
import importlib.machinery
import os
import sys
import threading

# 注入 tools/ 目录到 sys.path（PluginToolLoader 用 importlib 加载时未自动注入，
# 同目录的 _store/_pool/_auth 相互 import 会报 No module named）。
# deps/ 与 deps/<platform>/ 注入已由宿主统一接管（app/plugins/deps_loader.py）。
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)


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
    # openssl dll 在平台专属 deps/win32/bin（deps 按平台分目录后）
    for plat in ("win32", ""):
        cands.append(os.path.abspath(os.path.join(here, "..", "deps", plat, "bin")))
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

# ── 加密后端仲裁：paramiko 必须绑插件 deps 的 cryptography ──────────────────

_CRYPTO_SELFTEST_OK = False


def _vendored_crypto_dir():
    """插件 deps 里 cryptography 包目录（平台目录优先，与 deps_loader 同口径）"""
    here = os.path.dirname(os.path.abspath(__file__))
    plat = "win32" if sys.platform == "win32" else sys.platform
    for sub in (plat, ""):
        d = os.path.normpath(os.path.join(here, "..", "deps", sub, "cryptography"))
        if os.path.exists(os.path.join(d, "__init__.py")):
            return d
    return None


class _VendoredCryptoFinder:
    """meta_path 钩子：cryptography* 一律指向插件 deps 目录，其余放行。"""

    _hook = None

    def __init__(self, pkg_dir):
        hook = importlib.machinery.FileFinder.path_hook(
            (importlib.machinery.ExtensionFileLoader, importlib.machinery.EXTENSION_SUFFIXES),
            (importlib.machinery.SourceFileLoader, importlib.machinery.SOURCE_SUFFIXES),
            (importlib.machinery.SourcelessFileLoader, importlib.machinery.BYTECODE_SUFFIXES),
        )
        self._finder = hook(pkg_dir)

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "cryptography" or fullname.startswith("cryptography."):
            return self._finder.find_spec(fullname, target)
        return None


def _crypto_modules():
    return [k for k in sys.modules if k == "cryptography" or k.startswith("cryptography.")]


def _selftest_aes_ctr():
    """AES-CTR 可用性自检：正是打包版副本缺失的能力，失败即回滚依据。"""
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    enc = Cipher(algorithms.AES(b"0" * 16), modes.CTR(b"1" * 16), backend=default_backend()).encryptor()
    enc.update(b"drifox-ssh-toolkit")


def _prefer_vendored_crypto():
    """把 cryptography 换成插件 deps 版（幂等，失败回滚宿主原状）。

    回滚语义：自检不过 → 摘钩子 + 恢复原 sys.modules 条目。恢复用模块对象
    回填而非重新 import，避免触发 FrozenImporter 又拿回坏副本。
    """
    global _CRYPTO_SELFTEST_OK
    if _CRYPTO_SELFTEST_OK:
        return
    pkg_dir = _vendored_crypto_dir()
    if not pkg_dir:
        return
    current = sys.modules.get("cryptography")
    cur_file = os.path.normcase(os.path.abspath(str(getattr(current, "__file__", "") or "")))
    if cur_file.startswith(os.path.normcase(pkg_dir)):
        _CRYPTO_SELFTEST_OK = True  # 已是 vendored 版
        return
    saved = {k: sys.modules[k] for k in _crypto_modules()}
    finder = _VendoredCryptoFinder(os.path.dirname(pkg_dir))
    for k in saved:
        del sys.modules[k]
    sys.meta_path.insert(0, finder)
    try:
        importlib.import_module("cryptography")
        mod = sys.modules.get("cryptography")
        new_file = os.path.normcase(os.path.abspath(str(getattr(mod, "__file__", "") or "")))
        if not new_file.startswith(os.path.normcase(pkg_dir)):
            raise RuntimeError(f"vendored cryptography 未生效：{new_file}")
        _selftest_aes_ctr()
        _CRYPTO_SELFTEST_OK = True  # 钩子常驻：后续子模块 import 仍需绕开 FrozenImporter
    except Exception:  # noqa: BLE001 - 任何失败都回滚到宿主现状（可用性优先）
        try:
            sys.meta_path.remove(finder)
        except ValueError:
            pass
        for k in _crypto_modules():
            sys.modules.pop(k, None)
        sys.modules.update(saved)


_prefer_vendored_crypto()
# paramiko：优先主环境，缺失时由宿主注入的插件 deps/ 提供（无需自理 sys.path）
import paramiko  # noqa: E402

SUPPORTED = {"publickey", "password", "keyboard-interactive", "agent"}

HOST_KEY_POLICIES = ("tofu", "strict", "off")
DEFAULT_HOST_KEY_POLICY = "tofu"
_HOST_KEY_ATTR = "_drifox_new_host_keys"
_REMEMBER_LOCK = threading.Lock()


def known_hosts_path():
    """插件自有 known_hosts（与 connections.json 同目录）"""
    try:
        from _store import CACHE_DIR  # noqa: WPS433 - 同目录模块，避免路径口径分叉
    except Exception:  # noqa: BLE001
        CACHE_DIR = os.path.join(os.path.expanduser("~"), ".drifox", "cache", "ssh")
    return os.path.join(CACHE_DIR, "known_hosts")


def fingerprint(key):
    """OpenSSH 风格 SHA256 指纹（AI/用户可肉眼比对）"""
    digest = hashlib.sha256(key.asbytes()).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def _remember_host(hostname, key, path):
    """把新主机密钥追加进 known_hosts（读改写 + 锁，容忍并发/文件损坏）"""
    with _REMEMBER_LOCK:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        hosts = paramiko.HostKeys()
        if os.path.exists(path):
            try:
                hosts.load(path)
            except Exception:  # noqa: BLE001 - 文件损坏时重建，不阻断连接
                hosts = paramiko.HostKeys()
        hosts.add(hostname, key.get_name(), key)
        hosts.save(path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


class _TofuPolicy(paramiko.MissingHostKeyPolicy):
    """未知主机：记录指纹 + 落盘后放行；已知主机不匹配由 paramiko 直接抛异常"""

    def __init__(self, path, record):
        self._path = path
        self._record = record

    def missing_host_key(self, client, hostname, key):
        fp = fingerprint(key)
        # 落盘失败不阻断连接（用户仍可从返回内容读到指纹并自行核对）
        try:
            _remember_host(hostname, key, self._path)
        except Exception:  # noqa: BLE001
            pass
        self._record.append({"host": hostname, "fingerprint": fp})


class _StrictPolicy(paramiko.MissingHostKeyPolicy):
    """strict：未知主机一律拒绝，错误里带上指纹供用户离线核对"""

    def missing_host_key(self, client, hostname, key):
        raise paramiko.SSHException(
            f"未知主机 {hostname}（指纹 {fingerprint(key)}）。strict 模式下拒绝连接；"
            f"确认可信后可将该指纹登记到 {known_hosts_path()}，或改用 host_key_policy=tofu"
        )


def _client(policy_name, record):
    c = paramiko.SSHClient()
    path = known_hosts_path()
    try:
        c.load_system_host_keys()  # 用户已在系统 known_hosts 登记过的主机直接可信
    except Exception:  # noqa: BLE001
        pass
    if os.path.exists(path):
        try:
            c.load_host_keys(path)
        except Exception:  # noqa: BLE001
            pass
    if policy_name == "off":
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    elif policy_name == "strict":
        c.set_missing_host_key_policy(_StrictPolicy())
    else:
        c.set_missing_host_key_policy(_TofuPolicy(path, record))
    return c


def connect(conn):
    auth_type = conn.get("auth_type", "publickey")
    if auth_type not in SUPPORTED:
        raise ValueError(f"不支持的 auth_type: {auth_type}，可选 {sorted(SUPPORTED)}")
    policy_name = str(conn.get("host_key_policy") or DEFAULT_HOST_KEY_POLICY).strip().lower()
    if policy_name not in HOST_KEY_POLICIES:
        raise ValueError(f"不支持的 host_key_policy: {policy_name}，可选 {list(HOST_KEY_POLICIES)}")
    record = []
    client = _client(policy_name, record)
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
    # 首次连接的主机密钥记录挂在 client 上，供调用方回显指纹
    try:
        setattr(client, _HOST_KEY_ATTR, record)
        setattr(client, "_drifox_host_key_policy", policy_name)
    except Exception:  # noqa: BLE001
        pass
    return client
