# -*- coding: utf-8 -*-
"""tarball 分发链路的回归测试

覆盖 2026-11 事故链上的三个确定行为：
1. 构建可复现 —— 同一份源码两次构建 sha256 必须一致
   （清单记录 sha，客户端据此校验；gzip 头带构建时间会让 sha 每次都不同）
2. 冒烟门禁能拦坏包 —— bili-scroll 事故形态（包内 deps 缺子模块）
3. 冒烟门禁 fail-closed —— 门禁模块不可用时必须拒绝发布，不能静默放行

工具模块在 tools/ 下，非包结构，走 importlib 按路径加载。
"""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import sys
import tarfile
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"

def _load_tool(name: str):
    """从 tools/ 按文件路径加载模块"""
    mod_name = f"_tool_{name}"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    path = TOOLS_DIR / f"{name}.py"
    if not path.exists():
        pytest.skip(f"工具不存在: {path}")
    # smoke_check_tarball 内部按裸名 import 兄弟模块时依赖 tools/ 在 sys.path
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module

def _make_plugin(tmp_path: Path, name: str = "demo") -> Path:
    """构造一个最小可构建的插件目录"""
    plugin = tmp_path / "plugins" / name
    (plugin / ".drifox-plugin").mkdir(parents=True)
    (plugin / ".drifox-plugin" / "plugin.json").write_text(
        '{"name": "%s", "version": "1.0.0"}' % name, encoding="utf-8"
    )
    (plugin / "__init__.py").write_text("", encoding="utf-8")
    (plugin / "main.py").write_text("VALUE = 1\n", encoding="utf-8")
    return plugin

class TestBuildReproducible:
    """构建产物必须可复现，否则清单记录的 sha256 无法校验已发布的 asset"""

    def test_same_source_same_sha(self, tmp_path):
        builder = _load_tool("build_plugin_tarballs")
        plugin = _make_plugin(tmp_path)

        out1 = tmp_path / "a.tar.gz"
        out2 = tmp_path / "b.tar.gz"
        sha1, size1 = builder.build_tarball(plugin, None, out1, None)
        # 间隔超过 1 秒，确保「把当前时间写进 gzip 头」的实现会暴露
        time.sleep(1.2)
        sha2, size2 = builder.build_tarball(plugin, None, out2, None)

        assert sha1 == sha2, "同一份源码两次构建 sha256 不同：gzip 头可能在写构建时间"
        assert size1 == size2

    def test_gzip_header_mtime_is_zero(self, tmp_path):
        """直接查 gzip 头：mtime 必须归零，而不是依赖文件系统时间恰好相同"""
        builder = _load_tool("build_plugin_tarballs")
        plugin = _make_plugin(tmp_path)
        out = tmp_path / "c.tar.gz"
        builder.build_tarball(plugin, None, out, None)

        with open(out, "rb") as fh:
            header = fh.read(10)
        # gzip 头：magic(2) method(1) flags(1) mtime(4) ...
        assert header[:2] == b"\x1f\x8b"
        mtime_bytes = header[4:8]
        assert mtime_bytes == b"\x00\x00\x00\x00", (
            f"gzip 头 mtime 未归零（{mtime_bytes.hex()}），构建产物不可复现"
        )

    def test_member_metadata_normalized(self, tmp_path):
        """tar 成员的 uid/gid/uname/mtime 也必须归零，避免构建机差异进产物"""
        builder = _load_tool("build_plugin_tarballs")
        plugin = _make_plugin(tmp_path)
        out = tmp_path / "d.tar.gz"
        builder.build_tarball(plugin, None, out, None)

        with tarfile.open(out, "r:gz") as tf:
            members = tf.getmembers()
        assert members, "包内无成员"
        for m in members:
            assert m.uid == 0 and m.gid == 0
            assert m.uname == "" and m.gname == ""
            assert m.mtime == 0

class TestSmokeCheckRejectsBrokenPackage:
    """冒烟门禁必须拦住 bili-scroll 事故形态的坏包"""

    def _build_broken_tarball(self, tmp_path: Path) -> Path:
        """构造坏包：业务代码 from bilibili_api import login_v2，
        但 deps/bilibili_api/__init__.py 里没有 login_v2（事故原形态）"""
        tar_path = tmp_path / "broken-1.0.0-all.tar.gz"
        files = {
            ".drifox-plugin/plugin.json": '{"name": "broken", "version": "1.0.0"}',
            "main.py": "from bilibili_api import login_v2\n\nprint(login_v2)\n",
            "deps/bilibili_api/__init__.py": "# 空壳，没有 login_v2\n",
        }
        with tarfile.open(tar_path, "w:gz") as tf:
            for name, content in files.items():
                data = content.encode("utf-8")
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mtime = 0
                tf.addfile(info, io.BytesIO(data))
        return tar_path

    def test_rejects_missing_submodule(self, tmp_path):
        smoke = _load_tool("smoke_check_tarball")
        tarball = self._build_broken_tarball(tmp_path)
        ok, errors, _warnings = smoke.smoke_check(tarball)
        assert not ok, "缺子模块的坏包必须被门禁拒绝"
        assert errors, "拒绝时必须给出可读原因"

    def test_accepts_good_package(self, tmp_path):
        """正向对照：同一形态但子模块存在时必须通过，避免门禁变成「一律拒绝」"""
        smoke = _load_tool("smoke_check_tarball")
        tar_path = tmp_path / "good-1.0.0-all.tar.gz"
        files = {
            ".drifox-plugin/plugin.json": '{"name": "good", "version": "1.0.0"}',
            "main.py": "from bilibili_api import login_v2\n\nprint(login_v2)\n",
            "deps/bilibili_api/__init__.py": "",
            "deps/bilibili_api/login_v2.py": "def login():\n    return 1\n",
        }
        with tarfile.open(tar_path, "w:gz") as tf:
            for name, content in files.items():
                data = content.encode("utf-8")
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mtime = 0
                tf.addfile(info, io.BytesIO(data))

        ok, errors, _warnings = smoke.smoke_check(tar_path)
        assert ok, f"好包被误杀: {errors}"

    def test_rejects_manifest_version_mismatch(self, tmp_path):
        """包内 manifest 版本与文件名不符必须拒绝（防止发错包）"""
        smoke = _load_tool("smoke_check_tarball")
        tar_path = tmp_path / "demo-2.0.0-all.tar.gz"
        files = {
            ".drifox-plugin/plugin.json": '{"name": "demo", "version": "1.0.0"}',
            "main.py": "X = 1\n",
        }
        with tarfile.open(tar_path, "w:gz") as tf:
            for name, content in files.items():
                data = content.encode("utf-8")
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mtime = 0
                tf.addfile(info, io.BytesIO(data))
        ok, errors, _warnings = smoke.smoke_check(tar_path)
        assert not ok, "manifest 版本与文件名不一致必须拒绝"

class TestSmokeGateFailClosed:
    """门禁不可用时必须拒绝发布，不能静默放行"""

    def test_missing_smoke_module_blocks_release(self, tmp_path, monkeypatch):
        builder = _load_tool("build_plugin_tarballs")
        # 模拟门禁模块不可用：让 import smoke_check_tarball 抛错
        monkeypatch.setattr(sys, "modules", {**sys.modules})
        sys.modules["smoke_check_tarball"] = None  # 触发 ImportError

        entry = {"default": {"url": "https://example.com/x.tar.gz", "sha256": "0" * 64}}
        kept, failures = builder._run_smoke_checks("demo", entry, tmp_path)

        assert kept == {}, "门禁不可用时不能放行任何包"
        assert failures, "门禁不可用必须记录失败原因"
        assert any("门禁" in f for f in failures)
