# -*- coding: utf-8 -*-
"""ip-switcher config 单元测试

模块由 tests/conftest.py 通过 importlib 加载（插件目录名带连字符，
无法用标准包路径导入，与 DriFox 实际插件加载方式一致）。
"""

import json

from ip_switcher_config import ConfigStore, reset_config_for_test


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


def test_whitelist_model(tmp_path):
    store = reset_config_for_test(tmp_path / "cfg.json")
    store.set("whitelist_models", ["free-gpt4o", "gemini-flash-free"])
    assert store.is_whitelisted_model("free-gpt4o")
    assert not store.is_whitelisted_model("gpt-4o")


def test_whitelist_base_url_trailing_slash(tmp_path):
    store = reset_config_for_test(tmp_path / "cfg.json")
    store.set("whitelist_base_urls", ["https://free-api.example.com"])
    assert store.is_whitelisted_base_url("https://free-api.example.com/")
    assert not store.is_whitelisted_base_url("https://other.example.com")


def test_merge_unknown_keys_ignored(tmp_path):
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps({"evil_key": 1, "retry_limit": 7}), encoding="utf-8")
    store = reset_config_for_test(cfg_path)
    assert store.get("retry_limit") == 7
    assert "evil_key" not in store.get_all()