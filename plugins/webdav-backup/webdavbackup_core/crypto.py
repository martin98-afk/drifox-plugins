# -*- coding: utf-8 -*-
"""备份包加密与 zip 打包

容器格式（加密时）：MAGIC "DFBK" + version(1B) + salt(16B) + nonce(12B) + AES-256-GCM 密文
密钥：PBKDF2-HMAC-SHA256(密码, salt, 480000 轮) 派生 32 字节
不加密时为标准 zip（ZIP_DEFLATED），任意解压工具可打开。
"""
from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path
from typing import Iterable, List

MAGIC = b"DFBK"
VERSION = 1
_SALT_LEN = 16
_NONCE_LEN = 12
_PBKDF2_ROUNDS = 480_000


class CryptoUnavailableError(RuntimeError):
    """cryptography 库不可用（DriFox 环境异常缺失）"""


class DecryptionError(ValueError):
    """密码错误或文件损坏（GCM 认证失败）"""


def _aesgcm(password: str, salt: bytes):
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as e:  # pragma: no cover
        raise CryptoUnavailableError(
            "加密功能依赖 cryptography 库（DriFox 自带），当前环境缺失：请勿设置加密密码，或重新安装 DriFox"
        ) from e
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=_PBKDF2_ROUNDS)
    key = kdf.derive(password.encode("utf-8"))
    return AESGCM(key)


def is_encrypted(blob: bytes) -> bool:
    return blob[:4] == MAGIC


def encrypt_bytes(data: bytes, password: str) -> bytes:
    if not password:
        raise ValueError("加密密码为空")
    from os import urandom

    salt, nonce = urandom(_SALT_LEN), urandom(_NONCE_LEN)
    ct = _aesgcm(password, salt).encrypt(nonce, data, None)
    return MAGIC + bytes([VERSION]) + salt + nonce + ct


def decrypt_bytes(blob: bytes, password: str) -> bytes:
    if not is_encrypted(blob):
        raise DecryptionError("该备份包未加密")
    if len(blob) < 4 + 1 + _SALT_LEN + _NONCE_LEN + 16:
        raise DecryptionError("备份包已损坏")
    ver = blob[4]
    if ver != VERSION:
        raise DecryptionError(f"不支持的备份包版本: {ver}")
    off = 5
    salt = blob[off:off + _SALT_LEN]
    off += _SALT_LEN
    nonce = blob[off:off + _NONCE_LEN]
    off += _NONCE_LEN
    ct = blob[off:]
    try:
        return _aesgcm(password, salt).decrypt(nonce, ct, None)
    except Exception as e:
        raise DecryptionError("解密失败：密码错误或文件已损坏") from e


# ============================================================
# zip 打包 / 解包
# ============================================================


def make_zip(app_data_dir: Path, files: Iterable[Path], skipped: List[str]) -> bytes:
    """把收集到的文件按相对路径打进 zip，返回字节流"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for f in files:
            try:
                zf.write(f, arcname=f.relative_to(app_data_dir).as_posix())
            except OSError as e:
                skipped.append(f"{f.name}: {e}")
    return buf.getvalue()


def extract_zip(data: bytes, dest: Path, skipped: List[str]) -> List[str]:
    """解压 zip 到 dest，带 zip-slip 防护；返回解出的相对路径列表"""
    root = os.path.realpath(dest)
    applied: List[str] = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            # 统一正斜杠并拒绝绝对路径 / 盘符 / 上跳
            norm = name.replace("\\", "/").lstrip("/")
            if not norm or ":" in norm.split("/", 1)[0] or norm.startswith("..") or "/../" in norm:
                skipped.append(f"{name}: 不安全路径，已跳过")
                continue
            target = os.path.realpath(os.path.join(dest, norm))
            if target != root and not target.startswith(root + os.sep):
                skipped.append(f"{name}: 越界路径，已跳过")
                continue
            zf.extract(info, dest)
            applied.append(norm)
    return applied
