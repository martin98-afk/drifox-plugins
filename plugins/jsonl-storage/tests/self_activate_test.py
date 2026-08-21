# -*- coding: utf-8 -*-
"""验证 register() 末尾的自激活逻辑（mock PluginConfigStore + StorageRegistry proxy）"""
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, '.')


def main():
    # mock 整个 PluginConfigStore
    fake_store = MagicMock()
    fake_store.get.return_value = True  # enabled=True

    # mock StorageRegistry（通过 _RegistryProxy.__getattr__ 转发）
    fake_registry = MagicMock()
    fake_registry.set_active.return_value = True
    fake_registry.register.return_value = None

    # 场景 1：enabled=true → 应调用 set_active("jsonl")
    with patch.dict(sys.modules, {
        "app.plugins.managers.plugin_config_store": MagicMock(PluginConfigStore=MagicMock(return_value=fake_store)),
        "loguru": MagicMock(),
    }):
        from storages.jsonl_storage import register
        register(fake_registry)
        assert fake_registry.register.called, "engine 应被注册"
        assert fake_registry.set_active.called, "set_active 应被调用"
        assert fake_registry.set_active.call_args.args[0] == "jsonl", f"应激活 jsonl，实际 {fake_registry.set_active.call_args}"
        print("[ok] enabled=true → set_active('jsonl') 触发")

    # 场景 2：enabled=false → 不应调用 set_active
    fake_registry2 = MagicMock()
    fake_store2 = MagicMock()
    fake_store2.get.return_value = False
    with patch.dict(sys.modules, {
        "app.plugins.managers.plugin_config_store": MagicMock(PluginConfigStore=MagicMock(return_value=fake_store2)),
        "loguru": MagicMock(),
    }):
        from storages.jsonl_storage import register
        register(fake_registry2)
        assert fake_registry2.register.called
        assert not fake_registry2.set_active.called, "enabled=false 不应激活"
        print("[ok] enabled=false → set_active 不触发")

    # 场景 3：PluginConfigStore 导入失败 → 静默降级，不 panic
    fake_registry3 = MagicMock()
    with patch.dict(sys.modules, {"app.plugins.managers.plugin_config_store": None}):
        from storages.jsonl_storage import register
        try:
            register(fake_registry3)
            assert fake_registry3.register.called, "即使配置不可用，引擎仍应注册"
            print("[ok] 配置不可用时静默降级，不影响 register")
        except Exception as e:
            raise AssertionError(f"register 不应抛异常: {e}")

    # 场景 4：set_active 返回 False（极少见：pool not ready）→ 不 panic
    fake_registry4 = MagicMock()
    fake_registry4.set_active.return_value = False
    fake_store4 = MagicMock()
    fake_store4.get.return_value = True
    with patch.dict(sys.modules, {
        "app.plugins.managers.plugin_config_store": MagicMock(PluginConfigStore=MagicMock(return_value=fake_store4)),
        "loguru": MagicMock(),
    }):
        from storages.jsonl_storage import register
        register(fake_registry4)  # 不应抛异常
        print("[ok] set_active 返回 False 不抛异常")

    print("SELF-ACTIVATE TESTS PASS")


if __name__ == "__main__":
    main()