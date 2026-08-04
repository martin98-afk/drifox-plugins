# -*- coding: utf-8 -*-
"""ip-switcher config 单元测试

模块由 tests/conftest.py 通过 importlib 加载（插件目录名带连字符，
无法用标准包路径导入，与 DriFox 实际插件加载方式一致）。
"""

import json

from ip_switcher_config import (
    ConfigStore,
    discover_opencode_free_provider,
    get_opencode_free_models,
    get_opencode_free_urls,
    reset_config_for_test,
)


def test_default_config(tmp_path):
    store = reset_config_for_test(tmp_path / "cfg.json")
    assert store.get("retry_limit") == 3
    assert store.get("enabled") is True


def test_set_and_persist(tmp_path):
    store = reset_config_for_test(tmp_path / "cfg.json")
    store.set("retry_limit", 5)
    # 重新加载验证持久化
    store2 = ConfigStore(store.path)
    assert store2.get("retry_limit") == 5


def test_whitelist_keys_removed(tmp_path):
    """白名单配置项已从默认配置中移除"""
    store = reset_config_for_test(tmp_path / "cfg.json")
    assert "whitelist_models" not in store.get_all()
    assert "whitelist_base_urls" not in store.get_all()


def test_opencode_free_judge(tmp_path):
    """opencode 免费判定：命中模型名/API 地址返回 True，其他返回 False"""
    store = reset_config_for_test(tmp_path / "cfg.json")
    # 未发现内置 provider 时安全返回 False
    assert store.is_opencode_free_model("deepseek-v4-flash-free") in (True, False)
    assert store.is_opencode_free_model("gpt-4o") is False
    assert store.is_opencode_free_base_url("https://opencode.ai/zen/v1") in (True, False)
    assert store.is_opencode_free_base_url("https://api.deepseek.com") is False


def test_opencode_free_discover(tmp_path):
    """通过 IP_SWITCHER_SYSTEM_CONFIG 注入假系统配置，验证 opencode 免费 provider 发现"""
    import os

    fake_cfg = tmp_path / "app.config"
    fake_cfg.write_text(
        json.dumps(
            {
                "LLM": {
                    "SavedProviders": {
                        "free1": {
                            "name": "opencode免费模型",
                            "API_URL": "https://opencode.ai/zen/v1",
                            "模型列表": ["deepseek-v4-flash-free", "kimi-k3-free"],
                        },
                        "paid1": {
                            "name": "MiniMax",
                            "API_URL": "https://api.minimax.chat/v1",
                            "模型列表": ["MiniMax-M3"],
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    old = os.environ.get("IP_SWITCHER_SYSTEM_CONFIG")
    os.environ["IP_SWITCHER_SYSTEM_CONFIG"] = str(fake_cfg)
    try:
        p = discover_opencode_free_provider()
        assert p is not None
        assert p["name"] == "opencode免费模型"
        assert p["url"] == "https://opencode.ai/zen/v1"
        assert "deepseek-v4-flash-free" in p["models"]
        assert "MiniMax-M3" not in p["models"]
        assert get_opencode_free_models() == ["deepseek-v4-flash-free", "kimi-k3-free"]
        assert get_opencode_free_urls() == ["https://opencode.ai/zen/v1"]
    finally:
        if old is None:
            os.environ.pop("IP_SWITCHER_SYSTEM_CONFIG", None)
        else:
            os.environ["IP_SWITCHER_SYSTEM_CONFIG"] = old


def test_merge_unknown_keys_ignored(tmp_path):
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps({"evil_key": 1, "retry_limit": 7}), encoding="utf-8")
    store = reset_config_for_test(cfg_path)
    assert store.get("retry_limit") == 7
    assert "evil_key" not in store.get_all()
