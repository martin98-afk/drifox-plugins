# -*- coding: utf-8 -*-
"""browser 数据目录解析与旧数据迁移单测。

plugins/ 没有 __init__.py，不能按包导入，走 importlib 按路径加载
（与 tests/test_browser_design_mode.py 同款）。
"""

import importlib.util
from pathlib import Path

_PATHS = (
    Path(__file__).resolve().parent.parent
    / "plugins"
    / "browser"
    / "ui"
    / "paths.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("browser_paths", _PATHS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fresh(tmp_path):
    """加载模块并把旧目录 / app_data 根指到 tmp，清掉路径缓存"""
    m = _load()
    legacy = tmp_path / "legacy"
    app_data = tmp_path / "app_data"
    m.LEGACY_DATA_DIR = legacy
    m._app_data_root = lambda: app_data
    m._cached_dir = None
    return m, legacy, app_data


def test_data_dir_under_plugin_data(tmp_path):
    m, _legacy, app_data = _fresh(tmp_path)
    d = m.data_dir()
    assert d == app_data / "plugin_data" / "browser"
    assert d.is_dir()


def test_helpers_share_same_root(tmp_path):
    m, _legacy, app_data = _fresh(tmp_path)
    root = app_data / "plugin_data" / "browser"
    assert m.profile_dir() == root / "profile"
    assert m.cache_dir() == root / "cache"
    assert m.picks_dir() == root / "picks"
    assert m.screenshots_dir() == root / "screenshots"
    assert m.db_path() == root / "browser.db"
    assert m.redirect_config_path() == root / "browser-redirect.json"


def test_migrates_legacy_files_and_dirs(tmp_path):
    m, legacy, _app_data = _fresh(tmp_path)
    legacy.mkdir(parents=True)
    (legacy / "browser.db").write_bytes(b"db")
    (legacy / "browser-redirect.json").write_text("{}", encoding="utf-8")
    (legacy / "picks").mkdir()
    (legacy / "picks" / "a.png").write_bytes(b"png")
    (legacy / "profile").mkdir()
    (legacy / "profile" / "Cookies").write_bytes(b"c")

    d = m.data_dir()

    assert (d / "browser.db").read_bytes() == b"db"
    assert (d / "browser-redirect.json").exists()
    assert (d / "picks" / "a.png").exists()
    assert (d / "profile" / "Cookies").exists()
    assert (d / ".migrated-from-plugin-dir").exists()
    # 复制不删：旧目录留着当回滚
    assert legacy.exists()


def test_migration_runs_once(tmp_path):
    m, legacy, _app_data = _fresh(tmp_path)
    legacy.mkdir(parents=True)
    (legacy / "browser.db").write_bytes(b"old")
    m.data_dir()

    (legacy / "browser.db").write_bytes(b"changed")
    m._cached_dir = None
    d = m.data_dir()

    assert (d / "browser.db").read_bytes() == b"old"


def test_existing_target_not_overwritten(tmp_path):
    m, legacy, app_data = _fresh(tmp_path)
    legacy.mkdir(parents=True)
    (legacy / "browser.db").write_bytes(b"legacy")
    target = app_data / "plugin_data" / "browser"
    target.mkdir(parents=True)
    (target / "browser.db").write_bytes(b"current")

    d = m.data_dir()

    assert (d / "browser.db").read_bytes() == b"current"


def test_no_legacy_dir_is_noop(tmp_path):
    m, legacy, _app_data = _fresh(tmp_path)
    assert not legacy.exists()
    d = m.data_dir()
    assert d.is_dir()
    assert not (d / ".migrated-from-plugin-dir").exists()
