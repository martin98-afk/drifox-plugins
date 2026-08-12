# -*- coding: utf-8 -*-
"""context-stats 插件测试

模拟 DriFox 运行时加载方式：
- 把 plugins/context-stats/ui 加入 sys.path
- 以 ui_plugin_context_stats 包名从文件加载（与 UIPluginRegistry.load_plugin 一致）
- 测试 data.py 聚合 / 缓存 / render.py echarts option 生成
"""

import importlib.util
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

_UI_DIR = Path(__file__).resolve().parent.parent / "plugins" / "context-stats" / "ui"


def _load_plugin_package():
    """以 ui_plugin_context_stats 包名加载插件 ui 包（与运行时一致）"""
    module_name = "ui_plugin_context_stats"
    if module_name in sys.modules:
        return sys.modules[module_name]
    if str(_UI_DIR) not in sys.path:
        sys.path.insert(0, str(_UI_DIR))
    spec = importlib.util.spec_from_file_location(module_name, _UI_DIR / "__init__.py")
    assert spec is not None and spec.loader is not None, "无法加载插件包"
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    class _FakeRegistry:
        """记录 register_welcome_tab 调用（触发子模块延迟导入）"""

        def __init__(self):
            self.tabs = {}

        def register_welcome_tab(
            self, plugin_name, mode_key, label, render_func, priority=0, metadata=None
        ):
            self.tabs[mode_key] = (label, render_func)

    module.register_ui(_FakeRegistry())
    return module


@pytest.fixture(scope="module")
def plugin():
    return _load_plugin_package()


@pytest.fixture()
def mock_db(tmp_path, monkeypatch):
    """创建带数据的 SQLite 测试库，替换插件 data 模块的 _find_db"""
    plugin = _load_plugin_package()
    data_mod = sys.modules["ui_plugin_context_stats.data"]

    db_path = tmp_path / "sessions.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE sessions ("
        "id INTEGER PRIMARY KEY, project TEXT, created_at TEXT, "
        "message_count INTEGER, context_usage INTEGER, messages TEXT, compaction_state TEXT)"
    )

    today = datetime.now()
    # 3 天前：有 context_usage 的会话
    for i in range(1, 4):
        day = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        conn.execute(
            "INSERT INTO sessions (project, created_at, message_count, context_usage, messages, compaction_state) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("test-proj", f"{day} 10:00:00", 5, 1000, '[{"role":"user"}]', None),
        )
    # 5 天前：context_usage 缺失 → 走 messages 估算
    day5 = (today - timedelta(days=5)).strftime("%Y-%m-%d")
    conn.execute(
        "INSERT INTO sessions (project, created_at, message_count, context_usage, messages, compaction_state) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("test-proj", f"{day5} 12:00:00", 8, 0, "中文内容" * 100, None),
    )
    # 20 天前：超出 14 天窗口，不应计入
    day20 = (today - timedelta(days=20)).strftime("%Y-%m-%d")
    conn.execute(
        "INSERT INTO sessions (project, created_at, message_count, context_usage, messages, compaction_state) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("test-proj", f"{day20} 09:00:00", 99, 99999, "", None),
    )
    # 归档项目：不应计入
    conn.execute(
        "INSERT INTO sessions (project, created_at, message_count, context_usage, messages, compaction_state) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("__archived__/old", f"{day5} 08:00:00", 50, 50000, "", None),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(data_mod, "_find_db", lambda: db_path)
    monkeypatch.setattr(data_mod, "_cache", {})  # 清缓存
    return db_path


# ── data.py ───────────────────────────────────────────────


def test_fetch_stats_aggregation(mock_db):
    """聚合正确性：14 天窗口、context_usage 直读、fallback 估算、归档排除"""
    plugin = _load_plugin_package()
    data_mod = sys.modules["ui_plugin_context_stats.data"]

    stats = data_mod.get_stats()
    assert stats["error"] is None

    # 近 14 天序列固定 14 项
    assert len(stats["daily_tokens"]) == 14
    assert len(stats["daily_messages"]) == 14

    # 3 天前（context_usage=1000）+ 5 天前（估算 >0）
    assert stats["total_tokens"] > 1000
    # 消息量：5+5+5+8 = 23（归档排除）
    assert stats["total_messages"] == 23

    # 20 天前不计入
    labels = [l for l, _ in stats["daily_tokens"]]
    assert all(
        l not in (datetime.now() - timedelta(days=20)).strftime("%m-%d") for l in labels
    )


def test_fetch_stats_cache_hit(mock_db):
    """缓存命中：db mtime 不变时二次读取不重查"""
    plugin = _load_plugin_package()
    data_mod = sys.modules["ui_plugin_context_stats.data"]

    stats1 = data_mod.get_stats()
    stats2 = data_mod.get_stats()
    assert stats1 is stats2  # 同一缓存对象

    # 修改 db（模拟新会话）→ 缓存失效
    conn = sqlite3.connect(str(mock_db))
    day = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    conn.execute(
        "INSERT INTO sessions (project, created_at, message_count, context_usage, messages, compaction_state) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("proj2", f"{day} 11:00:00", 3, 500, "", None),
    )
    conn.commit()
    conn.close()
    stats3 = data_mod.get_stats()
    assert stats3 is not stats1
    assert stats3["total_messages"] == 26


def test_fetch_stats_no_db(tmp_path, monkeypatch):
    """无数据库 → 返回 error"""
    plugin = _load_plugin_package()
    data_mod = sys.modules["ui_plugin_context_stats.data"]

    monkeypatch.setattr(data_mod, "_find_db", lambda: None)
    monkeypatch.setattr(data_mod, "_cache", {})
    stats = data_mod.get_stats()
    assert stats["error"] is not None
    assert stats["daily_tokens"] == []


# ── render.py ─────────────────────────────────────────────


def test_render_welcome_tab_html(mock_db):
    """输出 markdown 片段：单个合并 echarts 代码块（双面板），JSON 可解析"""
    plugin = _load_plugin_package()
    render_mod = sys.modules["ui_plugin_context_stats.render"]

    html = render_mod.render_welcome_tab({"is_dark": True})
    assert "```echarts" in html
    assert html.count("```echarts") == 1  # 合并单图（token + 消息双面板）

    # 提取 echarts JSON 并验证可解析
    import re

    blocks = re.findall(r"```echarts\n(.*?)\n```", html, re.DOTALL)
    assert len(blocks) == 1
    opt = json.loads(blocks[0])
    assert opt["backgroundColor"] == "transparent"
    # 双面板：2 个 grid / 2 条 x 轴 / 2 条 y 轴 / 2 个 series
    assert len(opt["grid"]) == 2
    assert len(opt["xAxis"]) == 2
    assert len(opt["yAxis"]) == 2
    assert len(opt["series"]) == 2
    assert len(opt["xAxis"][0]["data"]) == 14
    # 双轴联动
    assert opt["axisPointer"]["link"] == [{"xAxisIndex": "all"}]
    # 面板标题
    assert len(opt["title"]) == 2


def test_render_dark_light_palette(mock_db):
    """明暗色板切换：accent 色不同"""
    plugin = _load_plugin_package()
    render_mod = sys.modules["ui_plugin_context_stats.render"]

    html_dark = render_mod.render_welcome_tab({"is_dark": True})
    html_light = render_mod.render_welcome_tab({"is_dark": False})

    assert "#62a0ea" in html_dark
    assert "#2878dc" in html_light


def test_render_no_data(tmp_path, monkeypatch):
    """空库 → 提示文案，无 echarts 代码块"""
    plugin = _load_plugin_package()
    render_mod = sys.modules["ui_plugin_context_stats.render"]
    data_mod = sys.modules["ui_plugin_context_stats.data"]

    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE sessions ("
        "id INTEGER PRIMARY KEY, project TEXT, created_at TEXT, "
        "message_count INTEGER, context_usage INTEGER, messages TEXT, compaction_state TEXT)"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(data_mod, "_find_db", lambda: db_path)
    monkeypatch.setattr(data_mod, "_cache", {})
    html = render_mod.render_welcome_tab({"is_dark": True})
    assert "暂无会话数据" in html
    assert "```echarts" not in html
