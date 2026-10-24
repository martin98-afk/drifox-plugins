# -*- coding: utf-8 -*-
"""vision-proxy 工具离线单测。

覆盖三块纯逻辑（不联网、不依赖 Qt）：
1. 图片编码：本地文件 → data URI；URL 透传；缺失/非图片/超限的错误路径
2. user content 组装：text 块 + 每张图一个 image_url 块
3. impl 参数校验与编排：paths 空/超限、能力缺失的降级错误

模块顶层 import app.plugins.sdk / plugin_config_store，宿主环境缺失时整体跳过。
"""

import base64
import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

_TOOL_PATH = (
    Path(__file__).resolve().parent.parent
    / "plugins"
    / "vision-proxy"
    / "tools"
    / "vision_describe.py"
)


def _stub_modules():
    """顶掉仅在主程序进程可用的依赖（app.plugins.*）。"""
    saved = {k: sys.modules.get(k) for k in list(sys.modules) if k.startswith("app.plugins")}
    app = sys.modules.get("app")
    if app is None:
        app = types.ModuleType("app")
        sys.modules["app"] = app

    plugins = types.ModuleType("app.plugins")
    managers = types.ModuleType("app.plugins.managers")
    store_mod = types.ModuleType("app.plugins.managers.plugin_config_store")

    class _Store:
        """配置替身：按 key 返回注入值，未注入返回 None（走插件内置默认）"""

        values = {}

        def get(self, plugin, key):
            return self.values.get(key)

    store_mod.PluginConfigStore = _Store

    sdk = types.ModuleType("app.plugins.sdk")

    class _ToolResult:
        def __init__(self, success, content=None, error=None):
            self.success = success
            self.content = content
            self.error = error

    sdk.ToolResult = _ToolResult
    sdk.pool_for = lambda **kwargs: None
    sdk.make_summarize_from_preview = lambda fn: fn

    plugins.sdk = sdk
    plugins.managers = managers
    managers.plugin_config_store = store_mod
    sys.modules["app.plugins"] = plugins
    sys.modules["app.plugins.sdk"] = sdk
    sys.modules["app.plugins.managers"] = managers
    sys.modules["app.plugins.managers.plugin_config_store"] = store_mod
    return saved, _Store


@pytest.fixture(scope="module")
def vd():
    saved, store = _stub_modules()
    try:
        spec = importlib.util.spec_from_file_location("vision_describe_probe", _TOOL_PATH)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules["vision_describe_probe"] = module
        spec.loader.exec_module(module)
    except Exception as e:  # noqa: BLE001 — 宿主缺 loguru 等则跳过
        pytest.skip(f"vision_describe 导入失败（宿主环境缺依赖？）: {e}")
    module._STORE = store
    return module


# ── 1. 图片编码 ──


def _png(tmp_path, name="a.png", size=64):
    """最小合法 PNG（1x1 透明）+ 补齐到指定字节数。"""
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    p = tmp_path / name
    p.write_bytes(png + b"\x00" * max(0, size - len(png)))
    return p


def test_local_png_to_data_uri(vd, tmp_path):
    p = _png(tmp_path)
    url, err = vd._encode_image(str(p))
    assert err == ""
    assert url.startswith("data:image/png;base64,")


def test_jpeg_mime(vd, tmp_path):
    p = tmp_path / "a.jpg"
    p.write_bytes(b"\xff\xd8\xff" + b"\x00" * 32)
    url, err = vd._encode_image(str(p))
    assert err == ""
    assert url.startswith("data:image/jpeg;base64,")


def test_remote_url_passthrough(vd):
    url, err = vd._encode_image("https://example.com/x.png")
    assert err == ""
    assert url == "https://example.com/x.png"


def test_data_uri_passthrough(vd):
    raw = "data:image/png;base64,AAAA"
    url, err = vd._encode_image(raw)
    assert err == ""
    assert url == raw


def test_missing_file(vd):
    url, err = vd._encode_image("D:/nope/not-exist.png")
    assert url == ""
    assert "文件不存在" in err


def test_unsupported_ext(vd, tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes(b"hello")
    url, err = vd._encode_image(str(p))
    assert url == ""
    assert "不是受支持的图片格式" in err


def test_oversize_rejected(vd, tmp_path, monkeypatch):
    p = _png(tmp_path)
    monkeypatch.setattr(vd, "_MAX_BYTES", 8)
    url, err = vd._encode_image(str(p))
    assert url == ""
    assert "图片过大" in err


def test_empty_path(vd):
    url, err = vd._encode_image("")
    assert url == ""
    assert err == "空路径"


# ── 2. user content 组装 ──


def test_content_blocks(vd):
    blocks = vd._build_user_content("读出报错", ["u1", "u2"])
    assert blocks[0] == {"type": "text", "text": "读出报错"}
    assert blocks[1] == {"type": "image_url", "image_url": {"url": "u1"}}
    assert blocks[2] == {"type": "image_url", "image_url": {"url": "u2"}}


def test_content_default_question(vd):
    blocks = vd._build_user_content("", ["u1"])
    assert blocks[0]["text"] == vd._DEFAULT_QUESTION


# ── 3. impl 参数校验 ──


def test_impl_empty_paths(vd):
    r = vd._impl({}, paths=[])
    assert r.success is False
    assert "paths 不能为空" in r.error


def test_impl_single_string_path(vd, tmp_path):
    """paths 传单字符串也要能走（AI 常这么调）；此处卡在能力缺失而非参数解析。"""
    p = _png(tmp_path)
    vd._STORE.values = {"vision_model": "gpt-4o"}
    try:
        r = vd._impl({}, paths=str(p))
    finally:
        vd._STORE.values = {}
    assert r.success is False
    assert "model.config" in r.error


def test_impl_too_many_images(vd, tmp_path):
    vd._STORE.values = {"max_images": 2}
    try:
        paths = [str(_png(tmp_path, f"a{i}.png")) for i in range(3)]
        r = vd._impl({}, paths=paths)
    finally:
        vd._STORE.values = {}
    assert r.success is False
    assert "一次最多 2 张" in r.error


def test_impl_bad_image_reports_error(vd, tmp_path):
    r = vd._impl({}, paths=[str(tmp_path / "not-here.png")])
    assert r.success is False
    assert "文件不存在" in r.error


def test_impl_no_vision_config(vd, tmp_path):
    """未配置视觉模型 → 明确报错，不静默串到当前（非视觉）模型。"""
    vd._STORE.values = {}
    r = vd._impl({}, paths=[str(_png(tmp_path))])
    assert r.success is False
    assert "未配置视觉模型" in r.error


def test_impl_capability_missing(vd, tmp_path, monkeypatch):
    """配了视觉模型但宿主无能力 → 明确报错，不静默失败。"""
    vd._STORE.values = {"vision_model": "gpt-4o"}
    monkeypatch.setattr(vd, "_host_pool", lambda: None)
    try:
        r = vd._impl({}, paths=[str(_png(tmp_path))])
    finally:
        vd._STORE.values = {}
    assert r.success is False
    assert "model.config" in r.error


# ── 4. 成功路径（引擎替身）──


class _FakeResult:
    text = "图里是一段 Python 报错 Traceback。"
    error = None
    cancelled = False
    timed_out = False


class _FakeSession:
    def __init__(self):
        self.messages = None
        self.cleaned = False

    def turn(self, messages, tools, timeout):
        self.messages = messages
        return _FakeResult()

    def cleanup(self):
        self.cleaned = True


def test_impl_success(vd, tmp_path, monkeypatch):
    vd._STORE.values = {"vision_model": "gpt-4o", "timeout_sec": 60}
    session = _FakeSession()

    class _Pool(dict):
        def legacy(self, key, cap_id):
            return lambda provider="", model="": {"模型名称": model or "gpt-4o"}

    monkeypatch.setattr(vd, "_host_pool", lambda: _Pool({"model.config": 1, "engine.session": 1}))
    monkeypatch.setattr(vd, "_create_session", lambda override: (session, ""))
    try:
        r = vd._impl({}, paths=[str(_png(tmp_path))], question="读出报错")
    finally:
        vd._STORE.values = {}
    assert r.success is True
    assert "Traceback" in r.content
    assert "gpt-4o" in r.content
    # 图片块确实进了 user content
    user = session.messages[-1]
    assert user["role"] == "user"
    assert any(b.get("type") == "image_url" for b in user["content"])
    assert session.cleaned is True
