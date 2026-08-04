# -*- coding: utf-8 -*-
"""ip-switcher state 单元测试

模块由 tests/conftest.py 通过 importlib 加载（插件目录名带连字符，
无法用标准包路径导入，与 DriFox 实际插件加载方式一致）。
"""

from ip_switcher_state import reset_state_for_test


def test_record_switch_updates_history_and_stats():
    st = reset_state_for_test()
    st.record_switch("ratelimit", "1.1.1.1", "2.2.2.2")
    st.record_switch("manual", "2.2.2.2", "3.3.3.3", success=False)
    assert st.current_ip() == "3.3.3.3"
    assert len(st.history()) == 2
    stats = st.stats()
    assert stats["total_switches"] == 2
    assert stats["rate_limit_hits"] == 1
    assert stats["fail_count"] == 1


def test_set_pool_state():
    st = reset_state_for_test()
    st.set_pool_state("ok")
    assert st.pool_state() == "ok"