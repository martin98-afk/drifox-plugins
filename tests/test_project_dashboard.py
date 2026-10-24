# -*- coding: utf-8 -*-
"""project-dashboard 离线单测：跨插件模块名撞车 + QThread 生命周期。

不依赖主程序 / 真实 git 仓库，PyQt5 缺失时 Qt 相关用例自动跳过。

覆盖两个已踩过的线上 bug：
1. ui/__init__.py 曾用顶层裸名 ``from collector import ...``，而宿主
   UIPluginRegistry 把每个插件的 ui 目录塞进 sys.path（后加载者排前），
   与 token-usage 的 ui/collector.py 撞车 → render_func 抛 TypeError，
   被宿主 _render_welcome_body 的 except 吞掉 → 回退渲染会话列表。
2. QThread 曾在 still running 时被析构 → qFatal，缓存永不写入。
"""

import ast
import importlib
import importlib.util
import inspect
import json
import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_PLUGIN = _ROOT / "plugins" / "project-dashboard"
_UI = _PLUGIN / "ui"
_TOKEN_USAGE_UI = _ROOT / "plugins" / "token-usage" / "ui"


def _make_fake_registry(project_root: str):
    """伪造宿主 UIPluginRegistry（提供 window_id → project_root 上下文）"""
    mod = types.ModuleType("app.plugins.registries.ui_plugin_registry")

    class FakeRegistry:
        _inst = None

        def __init__(self):
            self.tabs = {}
            self._context_providers = {"win_1": lambda: {"project_root": project_root}}
            self._context_provider = None
            self._window_main_widgets = {}

        @classmethod
        def get_instance(cls):
            if cls._inst is None:
                cls._inst = FakeRegistry()
            return cls._inst

        def _resolve_active_window_provider(self):
            return self._context_providers["win_1"]

        def register_welcome_tab(self, **kw):
            self.tabs[kw["mode_key"]] = kw

    mod.UIPluginRegistry = FakeRegistry
    for pkg in ("app", "app.plugins", "app.plugins.registries"):
        sys.modules.setdefault(pkg, types.ModuleType(pkg))
    sys.modules["app.plugins.registries.ui_plugin_registry"] = mod
    return FakeRegistry.get_instance()


@pytest.fixture(scope="module")
def pdpkg(tmp_path_factory):
    """把 ui/ 按宿主方式加载成包：ui_plugin_project_dashboard.ui.*

    宿主用 spec_from_file_location("ui_plugin_<name>", ui/__init__.py)，
    submodule_search_locations 自动带上 ui 目录 → 相对导入可用。断言包已生效。
    """
    sys.modules.pop("ui_plugin_project_dashboard", None)
    spec = importlib.util.spec_from_file_location("ui_plugin_project_dashboard", _UI / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ui_plugin_project_dashboard"] = mod
    spec.loader.exec_module(mod)
    assert mod.__package__ == "ui_plugin_project_dashboard"
    return mod


# ── 回归 1：子模块必须用相对导入，禁止塞 sys.path 的顶层裸名 ──


def _own_modules() -> tuple:
    """本插件 ui/ 下的子模块名（这些必须相对导入，不能走 sys.path 顶层名）"""
    return ("dashboard", "collector")


def _walk_imports(path: Path):
    """产出该文件所有 import 语句：(node, module_name, level, is_from_import)"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                yield node, node.module or alias.name, node.level
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield node, alias.name, 0


def test_ui_init_uses_relative_imports_only(pdpkg):
    """ui/__init__.py 引用的本插件子模块必须是相对导入（level > 0）

    顶层裸名（`from dashboard import` / `from collector import`）听命于
    sys.path 顺序，会撞上其他插件的同名文件。历史 bug：与 token-usage 的
    ui/collector.py 撞车 → build_cache_key 签名不符 → render_func 抛
    TypeError → 宿主 _render_welcome_body 的 except 吞掉 → 回退渲染会话列表。
    """
    own = _own_modules()
    bad = [(mod, node.lineno) for node, mod, level in _walk_imports(_UI / "__init__.py") if mod.split(".")[0] in own and level == 0]
    assert not bad, f"ui/__init__.py 存在顶层裸名导入（会被跨插件同名模块遮蔽）: {bad}"
    # 至少确有一个相对导入存在（防止整段被删导致测试空转）
    rel = [mod for _n, mod, level in _walk_imports(_UI / "__init__.py") if mod.split(".")[0] in own and level > 0]
    assert rel, "未找到相对导入，测试手段本身失效"


def test_collector_uses_relative_imports_only(collector_mod):
    """collector.py 同理：内部 `dashboard` 引用必须是相对导入"""
    own = _own_modules()
    path = Path(collector_mod.__file__)
    bad = [(mod, node.lineno) for node, mod, level in _walk_imports(path) if mod.split(".")[0] in own and level == 0]
    assert not bad, f"collector.py 存在顶层裸名导入: {bad}"


def test_register_ui_does_not_touch_sys_path(pdpkg):
    """register_ui 不得把 ui 目录塞进 sys.path

    宿主干这件事（逐插件 insert(0)），插件自己再干一遍只会遮蔽/被遮蔽。
    """
    tree = ast.parse((_UI / "__init__.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "register_ui")
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        # sys.path.insert(...) / sys.path.append(...)
        attr = node.func
        if isinstance(attr, ast.Attribute) and attr.attr in ("insert", "append"):
            target = attr.value
            if isinstance(target, ast.Attribute) and target.attr == "path":
                pytest.fail("register_ui 不得操作 sys.path（插入顺序由宿主决定，不可控）")


def test_collector_and_dashboard_resolve_to_this_plugin(pdpkg):
    """本插件内部解析到的 collector / dashboard 必须指向自己的 ui 目录"""
    col = importlib.import_module("ui_plugin_project_dashboard.collector")
    dash = importlib.import_module("ui_plugin_project_dashboard.dashboard")
    assert Path(col.__file__).resolve() == (_UI / "collector.py").resolve()
    assert Path(dash.__file__).resolve() == (_UI / "dashboard.py").resolve()


def test_render_survives_module_name_collision(pdpkg, tmp_path):
    """与 token-usage 同时加载时，render_func 不得因模块撞车抛异常

    复刻宿主加载顺序：先 project-dashboard、后 token-usage（后者的 ui 目录
    抢占 sys.path[0]）。修好前这一步会抛 TypeError，宿主 except 吞掉后
    回退渲染会话列表 —— 用户看到的是「切了 tab 却显示会话内容」。
    """
    pytest.importorskip("PyQt5.QtWidgets")
    saved = list(sys.path)
    saved_mods = {k: v for k, v in sys.modules.items() if k.startswith("ui_plugin_")}
    try:
        for d in (_UI, _TOKEN_USAGE_UI):
            p = str(d)
            if p not in sys.path:
                sys.path.insert(0, p)
        # 宿主顺序：project-dashboard 先装载，token-usage 后（撞车来源）
        for name, ui_dir in (("project-dashboard", _UI), ("token-usage", _TOKEN_USAGE_UI)):
            safe = name.replace("-", "_")
            for k in [k for k in sys.modules if k.startswith(f"ui_plugin_{safe}")]:
                del sys.modules[k]
            spec = importlib.util.spec_from_file_location(f"ui_plugin_{safe}", ui_dir / "__init__.py")
            mod = importlib.util.module_from_spec(spec)
            sys.modules[f"ui_plugin_{safe}"] = mod
            spec.loader.exec_module(mod)

        col = importlib.import_module("ui_plugin_project_dashboard.collector")
        # ★ 关键断言：修好前这里会指向 token-usage 的 collector
        assert Path(col.__file__).resolve() == (_UI / "collector.py").resolve()
        sig = inspect.signature(col.build_cache_key)
        assert "project_root" in sig.parameters, f"build_cache_key 签名不符: {sig}"

        reg = _make_fake_registry(str(_ROOT))
        pd_mod = sys.modules["ui_plugin_project_dashboard"]
        pd_mod.register_ui(reg)
        render = reg.tabs["project-dashboard"]["render_func"]
        out = render({"is_dark": True})  # 不得抛异常
        assert isinstance(out, str) and out
    finally:
        sys.path[:] = saved
        for k in [k for k in sys.modules if k.startswith("ui_plugin_")]:
            if k not in saved_mods:
                del sys.modules[k]


# ── 回归 2：QThread 生命周期 ──


@pytest.fixture(scope="module")
def collector_mod(pdpkg):
    return importlib.import_module("ui_plugin_project_dashboard.collector")


def test_worker_run_quits_thread_before_emit(collector_mod):
    """worker.run 必须在 emit 之前让所在线程退出事件循环

    原实现靠 ``worker.finished -> thread.quit`` 的 queued 连接：而 _on_done
    首行就把 self._thread 置 None → QThread 失去最后引用即刻析构，此时
    exec() 仍在跑 → ``qFatal: QThread: Destroyed while thread is still running``
    → 后续缓存写入代码根本到不了。
    """
    tree = ast.parse(Path(collector_mod.__file__).read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "_CollectWorker")
    fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "run")

    quit_lines, emit_lines = [], []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        attr = node.func
        if isinstance(attr, ast.Attribute):
            if attr.attr == "quit":
                quit_lines.append(node.lineno)
            elif attr.attr == "emit" and isinstance(attr.value, ast.Attribute) and attr.value.attr == "finished":
                emit_lines.append(node.lineno)
    assert quit_lines, "run() 内必须显式 quit() 所在线程"
    assert emit_lines, "run() 内必须 emit finished"
    assert min(quit_lines) < min(emit_lines), "必须先 quit 再 emit：否则 _on_done 会在线程仍在运行时析构它"


def test_finalize_collect_writes_cache_without_signal(collector_mod, monkeypatch):
    """_finalize_collect 就地写缓存，不依赖任何跨线程信号投递"""
    c = collector_mod._Collector()
    fake_data = {"repo_name": "repo", "daily_commits": [("2026-01-01", 3)]}
    collector_mod._finalize_collect(fake_data, c)
    assert c._cache is fake_data
    assert c._cache_ts > 0


def test_worker_run_finalizes_even_when_signal_never_delivered(collector_mod, monkeypatch):
    """同步直调 worker.run()（等价「信号投进死线程」极端场景）也必须完成收尾"""
    pytest.importorskip("PyQt5.QtCore")
    from PySide6.QtCore import QThread

    monkeypatch.setattr(
        collector_mod,
        "_finalize_collect",
        lambda data, collector: setattr(collector, "_cache", data),
    )
    monkeypatch.setattr(QThread, "currentThread", classmethod(lambda cls: types.SimpleNamespace(quit=lambda: None)))

    collector = collector_mod._Collector()
    collector._thread = object()  # 伪运行中：is_running() 挡住新采集
    worker = collector_mod._CollectWorker("/nonexistent-repo", True, collector)
    worker.run()
    # root 非 git 仓库 → dashboard 返回 error 结果，但收尾必须发生
    assert collector._cache is not None
    assert collector._thread is None, "worker 收尾必须清 _thread，否则后续 start() 全被拦截"
    assert collector._cache.get("error"), f"非 git 路径应返回 error: {collector._cache}"


def test_notify_refresh_survives_missing_host(collector_mod):
    """宿主不可用（无 app.* 模块）时 notify_refresh 不得抛异常"""
    collector_mod.notify_refresh()


# ── echarts option 生成（纯 stdlib，无 Qt / 无 git）──


@pytest.fixture(scope="module")
def dashboard_mod(pdpkg):
    return importlib.import_module("ui_plugin_project_dashboard.dashboard")


def test_build_options_returns_single_grid_option(dashboard_mod):
    data = {
        "daily_commits": [("2026-01-01", 2), ("2026-01-02", 5)],
        "contributors": [("alice", 7), ("bob", 3)],
        "languages": [("Python", 10, 500)],
        "file_types": [(".py", 10), (".md", 4)],
    }
    opts = dashboard_mod.build_options(data, True)
    assert len(opts) == 1
    opt = opts[0]
    assert len(opt["grid"]) == 4
    assert len(opt["series"]) == 4
    json.dumps(opt, ensure_ascii=False)  # 必须可序列化为 echarts JSON


def test_build_options_empty_data_returns_empty(dashboard_mod):
    assert dashboard_mod.build_options({}, False) == []


def test_scan_files_skips_noise_dirs(dashboard_mod, tmp_path):
    (tmp_path / "keep.py").write_text("a\nb\n", encoding="utf-8")
    noise = tmp_path / "node_modules"
    noise.mkdir()
    (noise / "junk.js").write_text("x\n", encoding="utf-8")
    ext_counter, lang_files, lang_lines = dashboard_mod._scan_files(str(tmp_path))
    assert ext_counter[".py"] == 1
    assert ".js" not in ext_counter, "噪音目录必须被跳过"
    assert lang_lines.get("Python") == 2
