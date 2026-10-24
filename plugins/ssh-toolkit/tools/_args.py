# ssh-toolkit/tools/_args.py
# -*- coding: utf-8 -*-
"""工具入参归一化。

模型调用工具时会把 integer 参数传成 None（显式 null）或字符串，
``kwargs.get("port", 22)`` 的默认值只在 key 缺失时生效，key 存在而值为 None
时 ``int(None)`` 抛 ``TypeError: int() argument must be a string, a
bytes-like object or a real number, not 'NoneType'``，整次调用失败。
配置读取侧（_auth.connect）同病：手改 connections.json 写入 null、或旧版本
遗留缺字段时，``int(conn.get("port", 22))`` 同样炸。该侧不能 import 本模块
（_auth 是加密后端仲裁的入口，import 链要尽量短），用本地等价实现。
"""


def to_int(value, default):
    """归一化为 int：None / 空串 / 不可解析值一律回落 default。"""
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
