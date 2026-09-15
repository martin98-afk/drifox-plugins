# -*- coding: utf-8 -*-
"""插件取模型配置的密钥通道回归测试（prompt-enhancer / git-panel）

背景（2026-09-15）：插件直读 `~/.drifox/app.config` 取 API_KEY，而 SecretMode
非 none 时磁盘该字段是密文（password 模式 `enc:v2:…`）或空串（keyring 模式密钥
已入系统凭证库）。插件把密文当 Bearer token 发出 → 401
`log in fail: Please carry the API secret key`。

修复：改走宿主 `ctx["services"]["get_provider_config"]`（主程序读内存态已解锁
明文），旧版主程序回退遍历 `main_widget._valid_configs`（同为内存态）。

本测试用 importlib 按 DriFox 实际插件加载方式加载模块（目录名带连字符）。
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_PE_UI = _ROOT / "plugins" / "prompt-enhancer" / "ui" / "__init__.py"
_GP_LLM = _ROOT / "plugins" / "git-panel" / "ui" / "llm_config.py"

_DISK_CIPHER = "enc:v2:CIPHERTEXT-NOT-A-USABLE-KEY"
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
    return {
        "app.plugins": plugins,
        "app.plugins.managers": managers,
        "app.plugins.managers.plugin_config_store": store,
        "app.plugins.registries": registries,
        "app.plugins.registries.ui_plugin_registry": ui_reg,
    }


def _host_valid_configs():
    """主程序内存态 _valid_configs（API_KEY 已是解密后的明文）"""
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


def _make_host():
    import types

    host = types.SimpleNamespace()
    host._valid_configs = _host_valid_configs()
    host._display_to_config_id = {"MiniMax": "cid1"}
    host._current_provider_name = "cid1"
    host._current_model_name = "MiniMax-M3"
    return host


@pytest.fixture()
def pe(tmp_path, monkeypatch):
    """prompt-enhancer：加载模块，并让「磁盘 app.config」指向一份密文配置"""
    mod = _load("_pe_key_probe", _PE_UI, _stubs())
    fake_cfg = tmp_path / "app.config"
    fake_cfg.write_text(
        json.dumps(
            {
                "LLM": {
                    "SavedProviders": {
                        "cid1": {
                            "provider_name": "MiniMax",
                            "API_URL": "https://api.example.com/v1",
                            "API_KEY": _DISK_CIPHER,
                            "模型名称": "MiniMax-M3",
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    mod._SYSTEM_CONFIG_CACHE.update({"path": None, "mtime": 0.0, "data": None})
    mod._DEFAULT_SYSTEM_CONFIG_PATHS = (str(fake_cfg),)
    return mod


@pytest.fixture()
def gp(tmp_path):
    """git-panel：同上"""
    mod = _load("_gp_key_probe", _GP_LLM, {})
    fake_cfg = tmp_path / "app.config"
    fake_cfg.write_text(
        json.dumps(
            {
                "LLM": {
                    "SavedProviders": {
                        "cid1": {
                            "provider_name": "MiniMax",
                            "API_URL": "https://api.example.com/v1",
                            "API_KEY": _DISK_CIPHER,
                            "模型名称": "MiniMax-M3",
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    mod._SYSTEM_CONFIG_CACHE.update({"path": None, "mtime": 0.0, "data": None})
    mod._DEFAULT_SYSTEM_CONFIG_PATHS = (str(fake_cfg),)
    return mod


# ── prompt-enhancer ──


def test_pe_prefers_host_service_plaintext(pe):
    """宿主服务可用时取到明文 key（不经磁盘）"""
    services = {
        "get_provider_config": lambda provider="", model="": {
            "API_KEY": _MEM_PLAIN,
            "API_URL": "https://api.example.com/v1",
            "模型名称": model or "MiniMax-M3",
        }
    }
    cfg = pe._get_llm_config(_make_host(), "MiniMax", "MiniMax-M2.7", services)
    assert cfg is not None
    assert cfg["API_KEY"] == _MEM_PLAIN
    assert cfg["模型名称"] == "MiniMax-M2.7"
    assert not cfg["API_KEY"].startswith("enc:v2:")


def test_pe_fallback_uses_memory_not_disk(pe):
    """无 services（旧版主程序）→ 回退内存态，绝不返回磁盘密文"""
    cfg = pe._get_llm_config(_make_host(), "MiniMax", "MiniMax-M2.7")
    assert cfg is not None
    assert cfg["API_KEY"] == _MEM_PLAIN
    assert _DISK_CIPHER not in json.dumps(cfg, ensure_ascii=False)


def test_pe_unknown_provider_not_silently_switched(pe):
    """显式指名的服务商不存在 → 返回 None，不串到别的服务商"""
    assert pe._get_llm_config(_make_host(), "不存在的服务商") is None


def test_pe_empty_key_provider_is_valid(pe):
    """免鉴权服务商（空 key）也是有效配置，不能因 key 为空被拒"""
    services = {
        "get_provider_config": lambda provider="", model="": {
            "API_KEY": "",
            "API_URL": "https://opencode.ai/zen/v1",
            "模型名称": "deepseek-v4-flash-free",
        }
    }
    cfg = pe._get_llm_config(_make_host(), "OpenCode Zen", "deepseek-v4-flash-free", services)
    assert cfg is not None
    assert cfg["API_KEY"] == ""


# ── git-panel ──


def test_gp_prefers_host_service_plaintext(gp):
    services = {
        "get_provider_config": lambda provider="", model="": {
            "API_KEY": _MEM_PLAIN,
            "API_URL": "https://api.example.com/v1",
            "模型名称": model or "MiniMax-M3",
        }
    }
    cfg = gp.get_llm_config(_make_host(), "MiniMax", "MiniMax-M2.7", services)
    assert cfg is not None
    assert cfg["API_KEY"] == _MEM_PLAIN
    assert not cfg["API_KEY"].startswith("enc:v2:")


def test_gp_fallback_uses_memory_not_disk(gp):
    cfg = gp.get_llm_config(_make_host(), "MiniMax", "MiniMax-M2.7")
    assert cfg is not None
    assert cfg["API_KEY"] == _MEM_PLAIN
    assert _DISK_CIPHER not in json.dumps(cfg, ensure_ascii=False)


def test_gp_unknown_provider_not_silently_switched(gp):
    assert gp.get_llm_config(_make_host(), "不存在的服务商") is None


def test_gp_empty_key_provider_is_valid(gp):
    services = {
        "get_provider_config": lambda provider="", model="": {
            "API_KEY": "",
            "API_URL": "https://opencode.ai/zen/v1",
            "模型名称": "deepseek-v4-flash-free",
        }
    }
    cfg = gp.get_llm_config(_make_host(), "OpenCode Zen", "deepseek-v4-flash-free", services)
    assert cfg is not None
    assert cfg["API_KEY"] == ""
