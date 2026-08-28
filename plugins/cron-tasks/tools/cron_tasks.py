# -*- coding: utf-8 -*-
"""cron_tasks — 定时任务管理工具（cron-tasks 插件 tools 组件）

单个工具覆盖全部管理动作（action 分发）：
  list / get / create / update / delete / toggle / run

数据通路优先级：
1. UI 侧 controller 单例（sys.modules["ui_plugin_cron_tasks.controller"]）
   → 与任务中心卡共享同一 CronScheduler，写操作即时生效 + 信号刷新 UI；
2. UI 未加载时回退 CronStore 磁盘直读直写（调度器 tick 每 30s _reload 自愈）。
   回退路径纯 Python（CronStore/CronJob），不触碰 Qt 对象，线程安全。
"""
from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

from app.tools.result import ToolResult

_ACTIONS = ("list", "get", "create", "update", "delete", "toggle", "run")

_STRING_FIELDS = ("label", "prompt", "agent", "model_key", "workdir", "notify")


# ============================================================
#  数据通路
# ============================================================


def _get_ui_scheduler():
    """取 UI 侧 controller 的 scheduler 单例（与任务中心卡共享）；未加载返回 None"""
    mod = sys.modules.get("ui_plugin_cron_tasks.controller")
    if mod is None:
        return None
    try:
        ctrl = mod.CronTasksController.get_instance()
        ctrl.ensure_started()  # 幂等：保证 _jobs 已从磁盘加载
        return ctrl.scheduler
    except Exception:
        return None


def _load_jobs() -> List[Any]:
    sched = _get_ui_scheduler()
    if sched is not None:
        return sched.get_jobs()
    from crontasks_core.store import CronStore

    return CronStore().load_jobs()


def _mutate(mutator):
    """写操作：优先走 UI scheduler（含校验/重算/信号），否则磁盘直写

    mutator(scheduler_or_none) -> str 错误信息（空=成功）
    """
    sched = _get_ui_scheduler()
    if sched is not None:
        return mutator(sched)
    # 回退：CronStore 直写（调度器 tick _reload 自动同步）
    from crontasks_core.store import CronStore

    store = CronStore()
    jobs = store.load_jobs()
    err = mutator(_StoreAdapter(store, jobs))
    if not err:
        store.save_jobs(jobs)
    return err


class _StoreAdapter:
    """磁盘直写模式下模拟 scheduler 的最小接口（add/update/delete/toggle）"""

    def __init__(self, store, jobs: List[Any]):
        self._store = store
        self._jobs = jobs

    def get_jobs(self):
        return list(self._jobs)

    def new_job_id(self) -> str:
        from crontasks_core.models import now_iso

        return f"job_{now_iso().replace('-', '').replace(':', '').replace('T', '')}"

    def add_job(self, job) -> str:
        err = job.validate()
        if err:
            return err
        if job.type == "at":
            if job.enabled and not job.recompute_next_run():
                return f"单次任务时间已过期: {job.schedule}"
        else:
            job.recompute_next_run()
        self._jobs.append(job)
        return ""

    def update_job(self, job) -> str:
        err = job.validate()
        if err:
            return err
        job.recompute_next_run()
        if job.type == "at" and job.enabled and not job.next_run_at:
            return f"单次任务时间已过期: {job.schedule}"
        for i, existing in enumerate(self._jobs):
            if existing.id == job.id:
                self._jobs[i] = job
                return ""
        return f"任务不存在: {job.id}"

    def delete_job(self, job_id: str) -> bool:
        before = len(self._jobs)
        self._jobs[:] = [j for j in self._jobs if j.id != job_id]
        return len(self._jobs) != before

    def toggle_job(self, job_id: str):
        for job in self._jobs:
            if job.id == job_id:
                if not job.enabled:
                    if not job.recompute_next_run():
                        return None  # 过期不可启用
                else:
                    job.next_run_at = ""
                job.enabled = not job.enabled
                return job.enabled
        return None


def _find_job(job_id: str):
    return next((j for j in _load_jobs() if j.id == job_id), None)


# ============================================================
#  输出格式化
# ============================================================


def _fmt_list_row(j) -> str:
    state = "✅启用" if j.enabled else "⏸禁用"
    nxt = j.next_run_at or "—"
    last = j.last_status or "未运行"
    if j.last_status == "error" and j.last_error:
        last = f"error({j.last_error[:40]})"
    return (
        f"- [{j.id}] {state} {j.display_label()}\n"
        f"    {j.schedule_desc()} · 下次: {nxt} · 上次: {last} · 已运行 {j.run_count} 次"
    )


def _fmt_detail(j) -> str:
    d = j.to_dict()
    lines = [
        f"id: {d['id']}",
        f"名称: {j.display_label()}",
        f"类型: {d['type']} · 调度: {j.schedule_desc()}",
        f"启用: {'是' if d['enabled'] else '否'}",
        f"下次运行: {d['nextRunAt'] or '—'}",
        f"上次运行: {d['lastRunAt'] or '—'}（{d['lastStatus'] or '未运行'}）· 累计 {d['runCount']} 次",
        f"智能体: {d['agent'] or '(跟随默认)'} · 模型: {d['modelKey'] or '(跟随会话)'}",
        f"工作目录: {d['workdir'] or '(当前会话工作目录)'}",
        f"通知: {d['notify'] or '(默认弹窗)'}",
        f"创建时间: {d['createdAt'] or '—'}",
        f"prompt:\n{d['prompt']}",
    ]
    if d["lastError"]:
        lines.append(f"上次错误: {d['lastError']}")
    return "\n".join(lines)


# ============================================================
#  动作实现
# ============================================================


def _act_list(_kw: Dict[str, Any]) -> ToolResult:
    jobs = _load_jobs()
    if not jobs:
        return ToolResult(True, content="当前没有任何定时任务。可用 action=create 新建。")
    rows = "\n".join(_fmt_list_row(j) for j in jobs)
    return ToolResult(True, content=f"共 {len(jobs)} 个定时任务：\n{rows}")


def _act_get(kw: Dict[str, Any]) -> ToolResult:
    job_id = (kw.get("job_id") or "").strip()
    if not job_id:
        return ToolResult(False, error="action=get 需要 job_id 参数（可先用 action=list 查看全部任务 id）")
    job = _find_job(job_id)
    if job is None:
        return ToolResult(False, error=f"任务不存在: {job_id}")
    return ToolResult(True, content=_fmt_detail(job))


def _build_job_from_kw(kw: Dict[str, Any], existing=None):
    """从 kwargs 构建 CronJob（existing 传入时为更新语义：未提供的字段保持原值）"""
    from crontasks_core.models import CronJob

    job = CronJob()
    if existing is not None:
        job = CronJob.from_dict(existing.to_dict())
        job.id = existing.id
    else:
        job.type = str(kw.get("type") or "").lower()
        job.schedule = kw.get("schedule", "")
        if job.type == "every":
            try:
                job.schedule = int(kw.get("schedule"))
            except (TypeError, ValueError):
                return None, "action=create 且 type=every 时 schedule 必须是间隔分钟数（如 \"30\"）"
        if not str(kw.get("prompt") or "").strip():
            return None, "action=create 需要 prompt 参数（到期后驱动 AI 执行的提示词）"
    if kw.get("type") is not None:
        job.type = str(kw.get("type")).lower()
        if job.type == "every":
            try:
                job.schedule = int(kw.get("schedule"))
            except (TypeError, ValueError):
                return None, "type=every 时 schedule 必须是间隔分钟数（如 \"30\"）"
    if kw.get("schedule") is not None and job.type != "every":
        job.schedule = kw.get("schedule")
    for f in _STRING_FIELDS:
        if kw.get(f) is not None:
            setattr(job, f, str(kw.get(f)))
    if kw.get("enabled") is not None:
        job.enabled = bool(kw.get("enabled"))
    return job, ""


def _act_create(kw: Dict[str, Any]) -> ToolResult:
    if not str(kw.get("type") or "").strip():
        return ToolResult(
            False,
            error="action=create 需要 type 参数（at=单次 / every=间隔分钟 / cron=5字段表达式），"
                  "并配合 schedule（如 \"2026-08-28T15:00:00\" / \"30\" / \"30 9 * * 1-5\"）",
        )
    job, err = _build_job_from_kw(kw)
    if err:
        return ToolResult(False, error=err)

    def _do(sched):
        job.id = sched.new_job_id()
        return sched.add_job(job)

    err = _mutate(_do)
    if err:
        return ToolResult(False, error=f"创建失败: {err}")
    return ToolResult(True, content=f"✅ 已创建定时任务「{job.display_label()}」· {job.schedule_desc()}")


def _act_update(kw: Dict[str, Any]) -> ToolResult:
    job_id = (kw.get("job_id") or "").strip()
    if not job_id:
        return ToolResult(False, error="action=update 需要 job_id 参数")
    existing = _find_job(job_id)
    if existing is None:
        return ToolResult(False, error=f"任务不存在: {job_id}")
    job, err = _build_job_from_kw(kw, existing=existing)
    if err:
        return ToolResult(False, error=err)

    err = _mutate(lambda sched: sched.update_job(job))
    if err:
        return ToolResult(False, error=f"更新失败: {err}")
    return ToolResult(True, content=f"✅ 已更新「{job.display_label()}」· {job.schedule_desc()}")


def _act_delete(kw: Dict[str, Any]) -> ToolResult:
    job_id = (kw.get("job_id") or "").strip()
    if not job_id:
        return ToolResult(False, error="action=delete 需要 job_id 参数")
    job = _find_job(job_id)
    label = job.display_label() if job is not None else job_id
    ok = _mutate(lambda sched: "" if sched.delete_job(job_id) else f"任务不存在: {job_id}")
    if ok:
        return ToolResult(False, error=f"删除失败: {ok}")
    return ToolResult(True, content=f"🗑 已删除定时任务「{label}」")


def _act_toggle(kw: Dict[str, Any]) -> ToolResult:
    job_id = (kw.get("job_id") or "").strip()
    if not job_id:
        return ToolResult(False, error="action=toggle 需要 job_id 参数")
    result: Dict[str, Any] = {}

    def _do(sched):
        state = sched.toggle_job(job_id)
        if state is None or state is False:
            # toggle_job 返回 False 可能是不存在 / 过期禁启用 / 禁用成功，需再查
            job = next((j for j in sched.get_jobs() if j.id == job_id), None)
            if job is None:
                return f"任务不存在: {job_id}"
            if not job.enabled:
                return f"「{job.display_label()}」无法启用：时间已过期"
            result["state"] = False
            return ""
        result["state"] = state
        return ""

    err = _mutate(_do)
    if err:
        return ToolResult(False, error=err)
    job = _find_job(job_id)
    label = job.display_label() if job is not None else job_id
    return ToolResult(True, content=f"✅ 已{'启用' if result.get('state') else '禁用'}「{label}」")


def _act_run(kw: Dict[str, Any]) -> ToolResult:
    job_id = (kw.get("job_id") or "").strip()
    if not job_id:
        return ToolResult(False, error="action=run 需要 job_id 参数")
    sched = _get_ui_scheduler()
    if sched is None:
        return ToolResult(False, error="任务中心 UI 未加载，立即执行需要调度器就绪；请先在主界面打开一次定时任务面板")
    job = _find_job(job_id)
    label = job.display_label() if job is not None else job_id
    if not sched.run_now(job_id):
        return ToolResult(False, error=f"「{label}」派发失败（可能已有任务在执行）")
    return ToolResult(True, content=f"▶ 已派发「{label}」立即执行，运行结果将通过通知反馈")


_IMPLS = {
    "list": _act_list,
    "get": _act_get,
    "create": _act_create,
    "update": _act_update,
    "delete": _act_delete,
    "toggle": _act_toggle,
    "run": _act_run,
}


def _impl(tool_ctx, **kwargs):
    action = str(kwargs.get("action") or "").strip().lower()
    if action not in _IMPLS:
        return ToolResult(
            False,
            error=f"未知 action: {action or '(空)'}，可选: {' / '.join(_ACTIONS)}",
        )
    try:
        return _IMPLS[action](kwargs)
    except Exception as e:  # noqa: BLE001
        return ToolResult(False, error=f"cron_tasks 内部异常: {type(e).__name__}: {e}")


_SCHEMA = {
    "type": "function",
    "function": {
        "name": "cron_tasks",
        "description": (
            "管理 cron-tasks 定时任务（到期自动驱动 AI 对话执行 prompt）。"
            "action=list 列出全部 / get 查详情 / create 新建 / update 修改 / delete 删除 / "
            "toggle 启用禁用切换 / run 立即执行。"
            "三种任务类型：type=at 单次（schedule=ISO 本地时间，如 \"2026-08-28T15:00:00\"）；"
            "type=every 间隔（schedule=分钟数字符串，如 \"30\" 每30分钟）；"
            "type=cron 标准5字段表达式（分 时 日 月 周，如 \"30 9 * * 1-5\" 工作日9:30、\"0 */2 * * *\" 每2小时）。"
            "创建/修改后自动计算下次运行时间，任务在 DriFox 任务中心面板可视化展示。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": list(_ACTIONS),
                    "description": "操作类型",
                },
                "job_id": {
                    "type": "string",
                    "description": "任务 id（get/update/delete/toggle/run 必填，用 action=list 获取）",
                },
                "type": {
                    "type": "string",
                    "enum": ["at", "every", "cron"],
                    "description": "任务类型（create 必填；update 可用于改类型）",
                },
                "schedule": {
                    "type": "string",
                    "description": (
                        "调度配置（create 必填）：at=ISO 本地时间 \"2026-08-28T15:00:00\"；"
                        "every=间隔分钟 \"30\"；cron=\"30 9 * * 1-5\"（分 时 日 月 周）"
                    ),
                },
                "prompt": {
                    "type": "string",
                    "description": "到期后驱动 AI 执行的提示词（create 必填；update 可改）",
                },
                "label": {
                    "type": "string",
                    "description": "任务展示名称（可选）",
                },
                "agent": {
                    "type": "string",
                    "description": "执行智能体名（可选，空=跟随主程序默认）",
                },
                "model_key": {
                    "type": "string",
                    "description": "执行模型（主程序 provider 配置名，可选，空=跟随当前会话模型）",
                },
                "workdir": {
                    "type": "string",
                    "description": "执行工作目录（可选，空=当前会话工作目录）",
                },
                "notify": {
                    "type": "string",
                    "description": "完成通知方式：空=默认弹窗 / \"system\"=系统托盘 / \"gateway:平台:chat_id\"",
                },
                "enabled": {
                    "type": "boolean",
                    "description": "是否启用（create 默认 true；update 可改）",
                },
            },
            "required": ["action"],
        },
    },
}


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    registry.register(
        "cron_tasks", _SCHEMA, impl=_impl,
        danger="safe", icon="cron_tasks", cn_name="定时任务管理",
        group="自动化",
        description="创建/查看/修改/删除/启停/立即运行 DriFox 定时任务（单工具全动作）",
        aliases=["cron", "定时任务"],
    )
