# -*- coding: utf-8 -*-
"""插件取模型配置的密钥通道回归测试（prompt-enhancer / git-panel）

背景（2026-09-15）：插件直读 `~/.drifox/app.config` 取 API_KEY，而 SecretMode
非 none 时磁盘该字段是密文（password 模式 `enc:v2:…`）或空串（keyring 模式密钥
已入系统凭证库）。插件把密文当 Bearer token 发出 → 401
`log in fail: Please carry the API secret key`。

演进（能力池收敛）：取配置唯一通道是宿主能力池——
`pool["model.config_for"]`（按名解析指定服务商/模型，query 为
「服务商:模型」或单值）/ `pool["model.config"]`（无参 = 当前会话
模型）；pool_for 解析到活跃窗口。ctx["services"]["get_provider_config"]
窗口上下文注入与磁盘扫描均已删除。

本测试 mock 能力池 / 宿主服务验证该通道（不落任何磁盘配置文件）；
用 importlib 按 DriFox 实际插件加载方式加载模块（目录名带连字符）。
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_PE_UI = _ROOT / "plugins" / "prompt-enhancer" / "ui" / "__init__.py"
_GP_LLM = _ROOT / "plugins" / "git-panel" / "ui" / "llm_config.py"

_MEM_PLAIN = "test-plain-key-from-memory"


def _load(name: str, path: Path, stubs: dict):
    """从文件路径加载插件模块；stubs 用于顶掉仅在主程序进程可用的依赖"""
    saved = {k: sys.modules.get(k) for k in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return module


class _Store:
    """PluginConfigStore 替身：读取一律返回 None（走插件内置默认）"""

    def get(self, *args, **kwargs):
        return None

    def set_values(self, *args, **kwargs):
        pass


class _UIReg:
    @staticmethod
    def get_instance():
        return _UIReg()

    def register_input_button(self, *a, **k):
        pass

    def register_settings_card(self, *a, **k):
        pass


def _stubs():
    import types

    plugins = types.ModuleType("app.plugins")
    managers = types.ModuleType("app.plugins.managers")
    store = types.ModuleType("app.plugins.managers.plugin_config_store")
    store.PluginConfigStore = _Store
    registries = types.ModuleType("app.plugins.registries")
    ui_reg = types.ModuleType("app.plugins.registries.ui_plugin_registry")
    ui_reg.UIPluginRegistry = _UIReg
    sdk = types.ModuleType("app.plugins.sdk")
    sdk.caps_for = lambda *a, **k: None
    sdk.pool_for = lambda plugin="", surface="": None
    return {
        "app.plugins": plugins,
        "app.plugins.managers": managers,
        "app.plugins.managers.plugin_config_store": store,
        "app.plugins.registries": registries,
        "app.plugins.registries.ui_plugin_registry": ui_reg,
        "app.plugins.sdk": sdk,
    }


def _install_sdk(monkeypatch, pool):
    """让插件内的 `from app.plugins.sdk import pool_for` 拿到 mock 能力池"""
    sdk = types.ModuleType("app.plugins.sdk")
    sdk.caps_for = lambda *a, **k: None
    sdk.pool_for = lambda plugin="", surface="": pool
    monkeypatch.setitem(sys.modules, "app.plugins.sdk", sdk)


class _FakePool:
    """能力池替身：下标访问 model.config_for / model.config 取注入的解析器

    与源码一致：插件经 pool["model.config_for"](query) 按名解析、
    pool["model.config"]() 取当前会话；能力被拒 = 下标访问抛异常。
    """

    def __init__(self, resolve=None, cap_error: Exception = None):
        self._resolve = resolve
        self._cap_error = cap_error

    def __contains__(self, cap_id):
        return self._cap_error is None and cap_id in (
            "model.config",
            "model.config_for",
        )

    def __getitem__(self, cap_id):
        if self._cap_error is not None:
            raise self._cap_error
        if cap_id not in ("model.config", "model.config_for"):
            raise KeyError(cap_id)
        return self._resolve


def _make_pool_resolve(valid: dict, current_id: str = "cid1"):
    """mock 宿主能力语义：model.config_for(query) 按名匹配指定服务商/模型；
    model.config() 无参 = 当前会话模型。未命中返回 {}（源码判空 → None）"""

    def _match(provider: str):
        if provider in valid:
            return valid[provider]
        for info in valid.values():
            if isinstance(info, dict) and provider in (
                info.get("display_name"),
                info.get("provider_name"),
                info.get("name"),
            ):
                return info
        return None

    def resolve(*args):
        if not args:
            cfg, model = valid.get(current_id), ""
        else:
            query = str(args[0] or "")
            provider, _, model = query.partition(":")
            cfg = _match(provider or model)
        if not isinstance(cfg, dict) or not cfg:
            return {}
        out = dict(cfg)
        if model:
            out["模型名称"] = model
        return out

    return resolve


def _host_valid_configs():
    """宿主内存态配置（API_KEY 已是解密后的明文）"""
    return {
        "cid1": {
            "provider_name": "MiniMax",
            "display_name": "MiniMax",
            "API_URL": "https://api.example.com/v1",
            "API_KEY": _MEM_PLAIN,
            "模型名称": "MiniMax-M3",
            "模型列表": ["MiniMax-M3", "MiniMax-M2.7"],
        }
    }


@pytest.fixture()
def pe():
    """prompt-enhancer：加载模块（能力池默认不可用，用例内按需 _install_sdk）"""
    pytest.importorskip("PyQt5.QtCore")  # prompt-enhancer ui/__init__ 顶层依赖 Qt
    return _load("_pe_key_probe", _PE_UI, _stubs())


@pytest.fixture()
def gp():
    """git-panel：加载 llm_config 模块"""
    return _load("_gp_key_probe", _GP_LLM, {})


# ── prompt-enhancer ──


def test_pe_prefers_host_service_plaintext(pe, monkeypatch):
    """override 指名服务商 → 能力池 model.config_for 取内存态明文（不经磁盘）"""
    _install_sdk(monkeypatch, _FakePool(_make_pool_resolve(_host_valid_configs())))
    cfg = pe._get_llm_config("MiniMax", "MiniMax-M2.7")
    assert cfg is not None
    assert cfg["API_KEY"] == _MEM_PLAIN
    assert cfg["模型名称"] == "MiniMax-M2.7"


def test_pe_fallback_pool_plaintext(pe, monkeypatch):
    """override 缺省 → 能力池 model.config 无参取当前会话模型，同样内存态明文"""
    _install_sdk(monkeypatch, _FakePool(_make_pool_resolve(_host_valid_configs())))
    cfg = pe._get_llm_config()
    assert cfg is not None
    assert cfg["API_KEY"] == _MEM_PLAIN
    assert cfg["模型名称"] == "MiniMax-M3"


def test_pe_pool_unavailable_returns_none(pe, monkeypatch):
    """无 services 且能力池不可用（无窗口/旧宿主）→ None，不崩不降级到磁盘"""
    _install_sdk(monkeypatch, None)  # pool_for 返回 None
    assert pe._get_llm_config("MiniMax", "MiniMax-M2.7") is None
    assert pe._get_llm_config() is None


def test_pe_pool_denied_returns_none(pe, monkeypatch):
    """能力被拒（legacy 抛异常）→ None（能力不可用时下拉空/调用方提示配置）"""
    _install_sdk(
        monkeypatch, _FakePool(cap_error=RuntimeError("capability denied"))
    )
    assert pe._get_llm_config("MiniMax") is None


def test_pe_unknown_provider_not_silently_switched(pe, monkeypatch):
    """显式指名的服务商不存在 → 返回 None，不串到别的服务商"""
    _install_sdk(monkeypatch, _FakePool(_make_pool_resolve(_host_valid_configs())))
    assert pe._get_llm_config("不存在的服务商") is None


def test_pe_empty_key_provider_is_valid(pe, monkeypatch):
    """免鉴权服务商（空 key）也是有效配置，不能因 key 为空被拒"""
    _install_sdk(
        monkeypatch,
        _FakePool(
            _make_pool_resolve(
                {
                    "zen": {
                        "provider_name": "OpenCode Zen",
                        "display_name": "OpenCode Zen",
                        "API_URL": "https://opencode.ai/zen/v1",
                        "API_KEY": "",
                        "模型名称": "deepseek-v4-flash-free",
                    }
                }
            )
        ),
    )
    cfg = pe._get_llm_config("OpenCode Zen", "deepseek-v4-flash-free")
    assert cfg is not None
    assert cfg["API_KEY"] == ""


# ── git-panel ──


def test_gp_prefers_host_service_plaintext(gp, monkeypatch):
    """override 指名服务商 → 能力池 model.config_for 取内存态明文"""
    _install_sdk(monkeypatch, _FakePool(_make_pool_resolve(_host_valid_configs())))
    cfg = gp.get_llm_config("MiniMax", "MiniMax-M2.7")
    assert cfg is not None
    assert cfg["API_KEY"] == _MEM_PLAIN
    assert cfg["模型名称"] == "MiniMax-M2.7"


def test_gp_fallback_pool_plaintext(gp, monkeypatch):
    """override 缺省 → 能力池 model.config 无参取当前会话模型，内存态明文"""
    _install_sdk(monkeypatch, _FakePool(_make_pool_resolve(_host_valid_configs())))
    cfg = gp.get_llm_config()
    assert cfg is not None
    assert cfg["API_KEY"] == _MEM_PLAIN
    assert cfg["模型名称"] == "MiniMax-M3"


def test_gp_pool_unavailable_returns_none(gp, monkeypatch):
    _install_sdk(monkeypatch, None)
    assert gp.get_llm_config("MiniMax", "MiniMax-M2.7") is None
    assert gp.get_llm_config() is None


def test_gp_unknown_provider_not_silently_switched(gp, monkeypatch):
    _install_sdk(monkeypatch, _FakePool(_make_pool_resolve(_host_valid_configs())))
    assert gp.get_llm_config("不存在的服务商") is None


def test_gp_empty_key_provider_is_valid(gp, monkeypatch):
    """免鉴权服务商（空 key）也是有效配置，不能因 key 为空被拒"""
    _install_sdk(
        monkeypatch,
        _FakePool(
            _make_pool_resolve(
                {
                    "zen": {
                        "provider_name": "OpenCode Zen",
                        "display_name": "OpenCode Zen",
                        "API_URL": "https://opencode.ai/zen/v1",
                        "API_KEY": "",
                        "模型名称": "deepseek-v4-flash-free",
                    }
                }
            )
        ),
    )
    cfg = gp.get_llm_config("OpenCode Zen", "deepseek-v4-flash-free")
    assert cfg is not None
    assert cfg["API_KEY"] == ""


def test_gp_resolve_model_legacy_combined_value(gp):
    """resolve_model：两键分开存为主；model 键存旧格式合并值时拆分；均空 → None"""
    assert gp.resolve_model("MiniMax", "MiniMax-M2.7") == ("MiniMax", "MiniMax-M2.7")
    assert gp.resolve_model("", "MiniMax:MiniMax-M2.7") == ("MiniMax", "MiniMax-M2.7")
    assert gp.resolve_model("", "MiniMax") == ("", "MiniMax")
    assert gp.resolve_model("", "") is None
