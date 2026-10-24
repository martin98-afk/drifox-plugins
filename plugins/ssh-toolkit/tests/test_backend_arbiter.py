"""加密后端仲裁：paramiko 必须绑插件 deps 的 cryptography，AES-CTR 必须可用。

背景：cx_Freeze 打包版宿主的 FrozenImporter 优先于 sys.path，内嵌 cryptography
会截胡 import，paramiko 被绑到宿主副本上，实测该副本 AES-CTR 不可用（报
cipher AES in CTR mode is not supported）。_auth._prefer_vendored_crypto 负责
把 cryptography 指回插件 deps 版并自检，失败回滚。
"""
import os
import sys

import ssh_toolkit_auth as A


def test_arbiter_marked_done_after_lazy_init():
    """懒加载（#23）语义：首次 _ensure_paramiko() 后仲裁标记就位。

    旧断言「import 后 _CRYPTO_SELFTEST_OK 为 True」与懒化目标直接冲突
    （模块级仲裁+cryptography 全量导入正是被移除的 1.4s 启动开销）。
    注意合跑时其他用例可能已先触发懒初始化，故不断言「此前为 False」；
    import 不触发仲裁的验证在探针（独立进程）覆盖。
    """
    A._ensure_paramiko()
    assert A._CRYPTO_SELFTEST_OK is True, "_ensure_paramiko 后仲裁应已完成"


def test_cryptography_bound_to_vendored_copy():
    """sys.modules 里的 cryptography 必须来自插件 deps 目录。"""
    import cryptography

    file_norm = os.path.normcase(os.path.abspath(str(getattr(cryptography, "__file__", "") or "")))
    dir_norm = os.path.normcase(os.path.abspath(A._vendored_crypto_dir() or ""))
    assert dir_norm, "vendored cryptography 目录不存在（deps 不完整？）"
    assert file_norm.startswith(dir_norm), f"cryptography 绑定到了宿主副本: {file_norm}"


def _snap():
    return {k: sys.modules[k] for k in A._crypto_modules()}


def test_arbiter_idempotent():
    """重复调用是 no-op，不再触碰 sys.modules。"""
    before = _snap()
    A._prefer_vendored_crypto()
    assert _snap() == before


def test_vendored_dir_exists():
    assert os.path.exists(os.path.join(A._vendored_crypto_dir(), "__init__.py"))


def test_missing_vendored_dir_is_noop(monkeypatch):
    """deps 缺失时仲裁应静默跳过，不抛异常、不破坏现有模块。"""
    monkeypatch.setattr(A, "_vendored_crypto_dir", lambda: None)
    before = _snap()
    A._CRYPTO_SELFTEST_OK = False
    try:
        A._prefer_vendored_crypto()  # 不应抛
        assert _snap() == before
    finally:
        A._CRYPTO_SELFTEST_OK = True


def test_selftest_failure_rolls_back(monkeypatch, tmp_path):
    """自检失败必须回滚：钩子摘除、sys.modules 恢复原状、异常不外泄。

    对应用户实测场景：宿主内嵌 cryptography 的 AES-CTR 不可用时，宁可退回
    宿主现状（保持可导入），也不能让插件加载半途炸掉。
    构造：monkeypatch _vendored_crypto_dir 指向一个空 cryptography 假包，
    selftest 注入失败 → 仲裁必须走完回滚且不抛。
    """
    fake_pkg = tmp_path / "cryptography"
    fake_pkg.mkdir()
    (fake_pkg / "__init__.py").write_text("", encoding="utf-8")

    def boom():
        raise RuntimeError("cipher AES in CTR mode is not supported")

    saved = _snap()
    monkeypatch.setattr(A, "_vendored_crypto_dir", lambda: str(fake_pkg))
    monkeypatch.setattr(A, "_selftest_aes_ctr", boom)
    A._CRYPTO_SELFTEST_OK = False
    try:
        A._prefer_vendored_crypto()  # 不应抛
        assert A._CRYPTO_SELFTEST_OK is False
        assert _snap() == saved
        # 旧模块对象仍可直接 import 使用
        import cryptography  # noqa: F401
    finally:
        A._CRYPTO_SELFTEST_OK = True


def test_vendored_not_effective_rolls_back(monkeypatch, tmp_path):
    """钩子接管失败（import 到的不是 deps 版）同样回滚。"""
    fake_pkg = tmp_path / "cryptography"
    fake_pkg.mkdir()
    (fake_pkg / "__init__.py").write_text("", encoding="utf-8")

    saved = _snap()
    monkeypatch.setattr(A, "_vendored_crypto_dir", lambda: str(fake_pkg))
    A._CRYPTO_SELFTEST_OK = False
    try:
        # 真实 selftest 会执行：deps 版 AES-CTR 本身可用 → new_file 检查先失败
        # （钩子 finder 在 tmp_path 找不到 cryptography，落到原 vendored？不，
        #  FileFinder 只找自己的目录，找不到 → import 落回 sys.path 的 vendored，
        #  __file__ 不在 fake_pkg 下 → 未生效 → 回滚）
        A._prefer_vendored_crypto()  # 不应抛
        assert A._CRYPTO_SELFTEST_OK is False
        assert _snap() == saved
    finally:
        A._CRYPTO_SELFTEST_OK = True


def test_paramiko_engine_aes_ctr_usable():
    """端到端：报错场景本身的回归测试——AES-CTR 引擎必须可构造。"""
    import paramiko

    t = paramiko.Transport.__new__(paramiko.Transport)
    engine = t._get_engine("aes128-ctr", b"0" * 16, b"1" * 16)
    assert engine is not None
    t2 = paramiko.Transport.__new__(paramiko.Transport)
    engine256 = t2._get_engine("aes256-ctr", b"0" * 32, b"1" * 16)
    assert engine256 is not None
