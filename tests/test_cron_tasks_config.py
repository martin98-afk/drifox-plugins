# -*- coding: utf-8 -*-
"""cron-tasks 可配置轮数/超时测试

背景：定时任务两次「中途中断却记成功」根因是硬编码 15 轮上限，
任务做不完被主程序按正常完成返回。本次把 max_rounds / timeout_seconds
做成任务级可配置（0=默认）。

覆盖：
1. CronJob 序列化往返保留两字段
2. scheduler._dispatch 把任务配置应用到 model_override 与 executor
3. tools/cron_tasks 的 _build_job_from_kw 解析整数参数
"""

import importlib.util
import sys
import tempfile
from pathlib import Path

import pytest

_PLUGIN_DIR = Path(__file__).resolve().parent.parent / "plugins" / "cron-tasks"
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from crontasks_core.models import CronJob  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    """全局唯一 QCoreApplication（session 级保活，防 QObject 被连带回收）"""
    from PyQt5.QtCore import QCoreApplication

    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


# ============================================================
#  1. 模型序列化
# ============================================================


def test_job_serialization_roundtrip_keeps_limits():
    """max_rounds/timeout_seconds 经 to_dict/from_dict 往返保留"""
    job = CronJob(
        id="job_x",
        type="cron",
        schedule="0 10 1 * *",
        label="月度新闻",
        prompt="搜索上月新闻",
        max_rounds=120,
        timeout_seconds=300,
    )
    restored = CronJob.from_dict(job.to_dict())
    assert restored.max_rounds == 120
    assert restored.timeout_seconds == 300


def test_job_serialization_defaults_zero():
    """未配置时两字段默认 0（调度层再兜底默认值）"""
    job = CronJob(id="job_y", type="at", schedule="2099-01-01T10:00:00", prompt="p")
    d = job.to_dict()
    assert d["maxRounds"] == 0
    assert d["timeoutSeconds"] == 0
    restored = CronJob.from_dict(d)
    assert restored.max_rounds == 0
    assert restored.timeout_seconds == 0


def test_job_from_dict_tolerates_bad_int():
    """脏数据（非整数）不抛异常，回落 0"""
    job = CronJob.from_dict({"maxRounds": "abc", "timeoutSeconds": None})
    assert job.max_rounds == 0
    assert job.timeout_seconds == 0


# ============================================================
#  2. scheduler._dispatch 应用
# ============================================================


class _FakeSignal:
    """可 connect/disconnect 的假信号"""

    def connect(self, *a, **k):
        pass

    def disconnect(self, *a, **k):
        pass


class FakeExecutor:
    """记录 configure 调用的假 executor"""

    def __init__(self):
        self.configured = None
        self.started = False
        self.finished_with_result = _FakeSignal()

    def configure(self, **kwargs):
        self.configured = kwargs

    def start(self):
        self.started = True

    # 调度器 stop/收尾路径需要的最小接口
    def isRunning(self):
        return False


def _fake_services():
    return {
        "create_engine_session": lambda *a, **k: None,
        "get_agent_prompt": lambda name: "",
        "get_tools_schema": lambda name: [],
        "get_workdir": lambda: "D:/work",
        "set_workdir": lambda wd: None,
    }


def _make_scheduler(monkeypatch, qapp):
    from crontasks_core.scheduler import CronScheduler, DEFAULT_MAX_ROUNDS
    from crontasks_core.store import CronStore

    tmp = Path(tempfile.mkdtemp())
    store = CronStore(base_dir=tmp / "cron")
    sched = CronScheduler(store=store)
    sched.set_services(_fake_services())
    monkeypatch.setattr(sched, "_resolve_services", lambda: _fake_services())
    monkeypatch.setattr(sched, "_resolve_model_override", lambda job: None)
    fake = FakeExecutor()
    monkeypatch.setattr("crontasks_core.scheduler.CronExecutor", lambda *a, **k: fake)
    return sched, fake, DEFAULT_MAX_ROUNDS


def test_dispatch_applies_job_limits(monkeypatch, qapp):
    """任务配置的轮数/超时被应用到 executor.configure"""
    sched, fake, _default = _make_scheduler(monkeypatch, qapp)
    job = CronJob(
        id="job_z", type="cron", schedule="30 9 * * 1-5",
        label="t", prompt="do something",
        max_rounds=120, timeout_seconds=300,
    )
    sched._dispatch(job)
    assert fake.configured is not None
    override = fake.configured["model_config_override"]
    assert override["最大循环轮数"] == 120
    assert fake.configured["timeout_seconds"] == 300
    assert fake.started is True


def test_dispatch_defaults_to_60_rounds(monkeypatch, qapp):
    """未配置轮数 → 默认 60；未配置超时 → 0（executor 侧回落 20min）"""
    sched, fake, default = _make_scheduler(monkeypatch, qapp)
    job = CronJob(
        id="job_w", type="cron", schedule="30 9 * * 1-5",
        label="t", prompt="do something",
    )
    sched._dispatch(job)
    assert fake.configured is not None
    assert fake.configured["model_config_override"]["最大循环轮数"] == default
    assert fake.configured["timeout_seconds"] == 0


# ============================================================
#  3. tools 参数解析
# ============================================================

# tools/cron_tasks.py 顶层 import 主程序 app.tools.result，测试环境无 app → 注入 stub


def _ensure_app_stub():
    import types

    if "app" in sys.modules:
        return
    pkg = types.ModuleType("app")
    pkg.__path__ = []
    tools_pkg = types.ModuleType("app.tools")
    tools_pkg.__path__ = []
    result_mod = types.ModuleType("app.tools.result")

    class ToolResult:
        def __init__(self, ok=True, content="", error=""):
            self.ok = ok
            self.content = content
            self.error = error

    result_mod.ToolResult = ToolResult
    sys.modules["app"] = pkg
    sys.modules["app.tools"] = tools_pkg
    sys.modules["app.tools.result"] = result_mod


def _load_tools_module():
    _ensure_app_stub()
    name = "cron_tasks_tool_under_test"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, _PLUGIN_DIR / "tools" / "cron_tasks.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_build_job_from_kw_parses_limits():
    """create 参数 max_rounds/timeout_seconds 被解析为 int 落入 job"""
    mod = _load_tools_module()
    job, err = mod._build_job_from_kw(
        {
            "type": "cron",
            "schedule": "0 10 1 * *",
            "prompt": "p",
            "max_rounds": "80",
            "timeout_seconds": "600",
        }
    )
    assert err == ""
    assert job.max_rounds == 80
    assert job.timeout_seconds == 600


def test_build_job_from_kw_rejects_bad_int():
    """非法整数 → 返回错误信息，不静默吞掉"""
    mod = _load_tools_module()
    _job, err = mod._build_job_from_kw(
        {
            "type": "cron",
            "schedule": "0 10 1 * *",
            "prompt": "p",
            "max_rounds": "abc",
        }
    )
    assert err != ""
    assert "整数" in err
