# -*- coding: utf-8 -*-
"""Cron 调度器 — QTimer 每分钟检查到期任务并派发执行（参考 openhanako cron-scheduler）

设计要点：
- 调度逻辑不涉及 LLM，只有执行回调才驱动对话（确定性代码层）
- 串行执行：同一时刻仅一个任务在跑（tool_executor 为主程序共享单例，
  并行会互相干扰工作目录/会话状态；到期任务依次排队）
- 任务执行完自动重算 next_run_at（at 类型跑完即禁用）
- services 懒解析：每次 tick 前尝试从活跃窗口拉最新（多窗口/主窗口变化自适应），
  拉不到时退回 controller 缓存
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger
from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from .executor import CronExecutor
from .models import CronJob
from .store import CronStore

TICK_INTERVAL_MS = 30_000  # 30 秒检查一次（分钟粒度任务的最低唤醒成本）


class CronScheduler(QObject):
    """定时任务调度器（主线程 QTimer 驱动）"""

    jobs_changed = pyqtSignal()  # 任务列表/状态变化（UI 刷新）
    job_started = pyqtSignal(str)  # job_id
    # (job_id, label, status, summary) — summary 供通知展示
    job_finished = pyqtSignal(str, str, str, str)
    notify_requested = pyqtSignal(str, str)  # (title, message) → controller 转发

    def __init__(self, store: Optional[CronStore] = None, parent=None):
        super().__init__(parent)
        self._store = store or CronStore()
        self._jobs: List[CronJob] = []
        self._executor: Optional[CronExecutor] = None
        self._services: Dict[str, Any] = {}  # controller 注入的缓存
        self._main_widget: Any = None  # 活跃窗口 main_widget（模型列表/覆盖用）
        self._prev_workdir: str = ""  # 执行前的工作目录（结束后还原）
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)
        self._done_keys: set = set()  # 已收尾的结果去重（job_id, duration_ms, status）

    # ================================================================
    #  生命周期
    # ================================================================

    def start(self):
        """启动调度（幂等）：加载任务 → 复位残留状态 → 补算 next_run → 启动 tick"""
        if self._timer.isActive():
            return
        self._reload()
        # 存量任务补算 next_run_at（禁用/单次已过期除外）；复位上次异常退出
        # 遗留的 lastStatus=running（无 executor 在跑却显示运行中的假状态）
        changed = False
        now = datetime.now()
        for job in self._jobs:
            if job.last_status == "running":
                job.last_status = ""
                changed = True
            if job.enabled and not job.next_run_at:
                if not job.recompute_next_run(now):
                    if job.type == "at":
                        job.enabled = False  # 过期单次任务自动禁用
                        changed = True
                        continue
                changed = True
        if changed:
            self._store.save_jobs(self._jobs)
        self._timer.start()
        self.jobs_changed.emit()
        logger.info(f"[cron-tasks] scheduler started: {len(self._jobs)} 个任务")

    def _detach_executor(self, ex):
        """断开 executor 信号（防孤儿写盘）

        热重载/手动停止后 executor 可能仍在卡着的 turn 里存活很久
        （极端场景卡满 20 分钟超时才醒）。旧调度器对象未被 Python GC 回收时，
        queued 信号仍会送达旧 _on_executor_done —— 用过期的内存 _jobs 整体
        回写 jobs.json，会覆盖磁盘上的新任务/新状态（实测事故）。
        此处无条件 disconnect，孤儿 emit 落空，不再有任何写盘副作用。
        """
        if ex is None:
            return
        try:
            ex.finished_with_result.disconnect(self._on_executor_done)
        except (TypeError, RuntimeError):
            pass

    def stop(self):
        """停止调度并取消运行中的任务（插件卸载/热重载/应用退出）

        先 disconnect（孤儿防写盘），再 cancel + 有限等待；
        等待期内正常返回的同步手动收尾落盘，卡死不返回的放弃收尾
        （热重载属开发场景，新代调度器 start() 时 _reload 自愈磁盘状态）。
        """
        self._timer.stop()
        ex = self._executor
        if ex is not None and ex.isRunning():
            self._detach_executor(ex)
            try:
                ex.cancel()
                ex.wait(8000)
            except Exception:
                pass
            if not ex.isRunning():
                res = getattr(ex, "_last_result", None)
                if isinstance(res, dict):
                    try:
                        self._on_executor_done(res)
                    except Exception as e:
                        logger.warning(f"[cron-tasks] stop 收尾失败: {e}")
        elif ex is not None:
            self._detach_executor(ex)
        self._executor = None
        logger.info("[cron-tasks] scheduler stopped")

    def cancel_job(self, job_id: str) -> bool:
        """手动停止指定任务（UI 停止按钮）。立即断开信号 + 置 None 释放串行锁

        executor 内部轮询模型保证 cancel 后 ~3.2s 内线程退出；
        此处先 disconnect（防止 executor 后续 emit 触发二次收尾/孤儿写盘），
        再置 None 让 is_running_job() 立即返回 False（新任务可派发），
        运行记录由本方法的同步路径直接落盘。
        """
        ex = self._executor
        if ex is not None and ex.isRunning() and ex._job and ex._job.id == job_id:
            self._detach_executor(ex)
            ex.cancel()
            if ex.wait(4000):
                # 正常返回：同步消费结果落盘（信号已断开）
                res = getattr(ex, "_last_result", None)
                if isinstance(res, dict):
                    try:
                        self._on_executor_done(res)
                    except Exception as e:
                        logger.warning(f"[cron-tasks] cancel_job 收尾失败: {e}")
            else:
                # turn 未响应（卡死）：放弃等待，但 UI/历史必须有反馈
                logger.warning("[cron-tasks] cancel_job: turn 未响应取消，放弃等待")
                try:
                    ex.finished.connect(ex.deleteLater)
                except (RuntimeError, TypeError):
                    pass
                res = {
                    "job_id": ex._job.id,
                    "status": "cancelled",
                    "error": "已手动停止",
                    "response_text": "",
                    "head": "",
                    "duration_ms": 4000,
                    "tool_calls": 0,
                }
                try:
                    self._on_executor_done(res)
                except Exception as e:
                    logger.warning(f"[cron-tasks] cancel_job 放弃路径收尾失败: {e}")
            self._executor = None  # 立即释放串行锁
            return True
        return False

    def is_running_job(self) -> bool:
        ex = self._executor
        return bool(ex and ex.isRunning())

    # ================================================================
    #  services 注入（controller 转发，含 UIPluginRegistry 活跃窗口解析）
    # ================================================================

    def set_services(self, services: Dict[str, Any]):
        if services:
            self._services = services

    def _resolve_services(self) -> Dict[str, Any]:
        """尝试从活跃窗口拉最新 services，失败退回缓存"""
        try:
            from app.plugins.registries.ui_plugin_registry import UIPluginRegistry

            reg = UIPluginRegistry.get_instance()
            provider = reg._resolve_active_window_provider() or reg._context_provider
            if provider is not None:
                ctx = provider() or {}
                services = ctx.get("services")
                if isinstance(services, dict) and services.get("create_engine_session"):
                    self._services = services
                    mw = ctx.get("main_widget")
                    if mw is not None:
                        self._main_widget = mw
        except Exception:
            pass
        return self._services

    # ================================================================
    #  任务 CRUD（UI 调用，主线程）
    # ================================================================

    def get_jobs(self) -> List[CronJob]:
        return list(self._jobs)

    def add_job(self, job: CronJob) -> str:
        """新增任务（保存 + 重算 next_run）。返回错误信息（空=成功）"""
        err = job.validate()
        if err:
            return err
        if job.type == "at":
            # 单次任务未过期才可启用
            if job.enabled and not job.recompute_next_run():
                return f"单次任务时间已过期: {job.schedule}"
        else:
            job.recompute_next_run()
        self._jobs.append(job)
        self._store.save_jobs(self._jobs)
        self.jobs_changed.emit()
        return ""

    def update_job(self, job: CronJob) -> str:
        """更新任务（按 id 匹配替换）"""
        err = job.validate()
        if err:
            return err
        job.recompute_next_run()
        if job.type == "at" and job.enabled and not job.next_run_at:
            return f"单次任务时间已过期: {job.schedule}"
        for i, existing in enumerate(self._jobs):
            if existing.id == job.id:
                self._jobs[i] = job
                break
        else:
            return f"任务不存在: {job.id}"
        self._store.save_jobs(self._jobs)
        self.jobs_changed.emit()
        return ""

    def delete_job(self, job_id: str) -> bool:
        before = len(self._jobs)
        self._jobs = [j for j in self._jobs if j.id != job_id]
        if len(self._jobs) == before:
            return False
        self._store.save_jobs(self._jobs)
        self.jobs_changed.emit()
        return True

    def toggle_job(self, job_id: str) -> bool:
        """启用/禁用切换。返回最终 enabled 状态（任务不存在返回 False）"""
        for job in self._jobs:
            if job.id == job_id:
                if not job.enabled:
                    if not job.recompute_next_run():
                        self.notify_requested.emit("定时任务", f"「{job.display_label()}」无法启用：时间已过期")
                        return False
                else:
                    job.next_run_at = ""
                job.enabled = not job.enabled
                self._store.save_jobs(self._jobs)
                self.jobs_changed.emit()
                return job.enabled
        return False

    def new_job_id(self) -> str:
        return f"job_{datetime.now().strftime('%Y%m%d%H%M%S')}_{id(self) % 10000:04d}"

    # ================================================================
    #  调度主循环
    # ================================================================

    def _tick(self):
        if self.is_running_job():
            return  # 串行：当前任务跑完后的完成回调会补算 next 并继续
        self._reload()
        now = datetime.now()
        due = None
        for job in self._jobs:
            if not job.enabled:
                continue
            nxt = job.next_run_dt()
            if nxt is None:
                # 缺失/失效的 next 补算（用户手改 jobs.json 的自愈路径）
                if not job.recompute_next_run(now):
                    continue
                self._store.save_jobs(self._jobs)
                continue
            if nxt <= now and (due is None or nxt < due[1]):
                due = (job, nxt)
        if due is not None:
            self._dispatch(due[0])

    def _reload(self):
        """从磁盘重载（允许用户/外部工具直接编辑 jobs.json）"""
        self._jobs = self._store.load_jobs()

    # ================================================================
    #  执行派发
    # ================================================================

    def run_now(self, job_id: str) -> bool:
        """立即运行（UI「▶ 立即运行」按钮）。返回是否成功派发"""
        if self.is_running_job():
            self.notify_requested.emit("定时任务", "已有任务在执行，请稍候")
            return False
        self._reload()
        job = next((j for j in self._jobs if j.id == job_id), None)
        if job is None:
            return False
        self._dispatch(job)
        return True

    def _dispatch(self, job: CronJob):
        services = self._resolve_services()
        if not services or not callable(services.get("create_engine_session")):
            logger.warning("[cron-tasks] 无可用 services，任务推迟到下一轮 tick")
            self.notify_requested.emit("定时任务", "对话服务未就绪，任务将在稍后自动重试")
            # 推迟：保持 next_run_at 不变，30 秒后重试
            job.next_run_at = datetime.now().replace(second=0, microsecond=0).isoformat(
                timespec="seconds"
            )
            self._store.save_jobs(self._jobs)
            return

        # 组装执行上下文：agent prompt + agent 视角工具集 + workdir + 模型覆盖
        agent_name = self._resolve_agent_name(job, services)
        system_prompt = ""
        tools: List[Dict] = []
        try:
            get_prompt = services.get("get_agent_prompt")
            if callable(get_prompt):
                system_prompt = get_prompt(agent_name) or ""
            get_tools = services.get("get_tools_schema")
            if callable(get_tools):
                tools = get_tools(agent_name) or []
        except Exception as e:
            logger.warning(f"[cron-tasks] 组装执行上下文失败: {e}")

        # 无人值守场景剔除 question：该工具会阻塞等用户回答，没人应答 → 卡满执行超时
        tools = [t for t in tools if t.get("function", {}).get("name") != "question"]

        # 模型覆盖：任务指定模型 → 从主程序 _valid_configs 取完整配置传 override
        model_override = self._resolve_model_override(job)

        # workdir 切换（执行完还原）
        self._prev_workdir = ""
        workdir = (job.workdir or "").strip()
        get_workdir = services.get("get_workdir")
        set_workdir = services.get("set_workdir")
        if workdir and callable(set_workdir):
            if callable(get_workdir):
                self._prev_workdir = get_workdir() or ""
            set_workdir(workdir)

        # 标记运行状态
        job.last_status = "running"
        job.last_run_at = datetime.now().isoformat(timespec="seconds")
        self._store.save_jobs(self._jobs)

        self._executor = CronExecutor()
        self._executor.configure(
            job=job,
            services=services,
            system_prompt=system_prompt,
            tools=tools,
            model_config_override=model_override,
        )
        self._executor.finished_with_result.connect(self._on_executor_done)
        self._executor.start()
        self.job_started.emit(job.id)
        logger.info(f"[cron-tasks] 执行任务: {job.display_label()} ({job.id})")

    def _resolve_agent_name(self, job: CronJob, services: Dict[str, Any]) -> str:
        """解析任务执行所用智能体名：任务指定 > 主程序默认"""
        if job.agent:
            return job.agent
        try:
            from app.config.settings import Settings

            return Settings.get_instance().llm_primary_agent.value or "build"
        except Exception:
            return "build"

    def _resolve_model_override(self, job: CronJob) -> Optional[Dict[str, Any]]:
        """任务指定模型 → 返回完整模型配置 dict（作为 model_config_override）；
        未指定/配置缺失 → None（跟随当前会话模型）。

        model_key 复合键格式："<config_id>||<model_name>"（每服务商可选其模型列表任意模型）；
        兼容旧格式：纯 config_id（用该配置当前模型）。
        模型列表来源：main_widget._valid_configs（provider 名 → 配置 dict），
        同 prompt-enhancer 先例（用户已确认接受私有状态复用）。
        """
        if not job.model_key or self._main_widget is None:
            return None
        valid = getattr(self._main_widget, "_valid_configs", None)
        if not isinstance(valid, dict):
            return None
        config_id, _, model_name = str(job.model_key).partition("||")
        cfg = valid.get(config_id)
        if not isinstance(cfg, dict) or not cfg:
            return None
        override = dict(cfg)
        if model_name:
            override["模型名称"] = model_name
        return override

    def _on_executor_done(self, result: dict):
        """执行完成（主线程 Queued 回调 / stop / cancel_job 手动收尾）：
        重读磁盘按 id 合并更新（防过期内存整表覆盖）+ 写历史 + 通知 + 还原 workdir"""
        from datetime import datetime as _dt

        job_id = str(result.get("job_id") or "")
        status = str(result.get("status") or "error")
        # 去重键以 job_id+status+timestamp（毫秒）保证唯一；
        # 避免 duration_ms 重复导致“同一次完成被吞”的关键 bug
        import time as _t2

        done_key = (job_id, status, int(_t2.time() * 1000))
        if done_key in self._done_keys:
            return  # 同毫秒内重复（极高概率不可能），走冗余防护
        self._done_keys.add(done_key)
        # 去重表上限（防内存泄漏：调度器长期运行期间累积）
        if len(self._done_keys) > 256:
            self._done_keys = set(list(self._done_keys)[-64:])
        error = str(result.get("error") or "")
        response_text = str(result.get("response_text") or "")
        head = str(result.get("head") or "")
        tool_calls = int(result.get("tool_calls") or 0)
        duration_ms = int(result.get("duration_ms") or 0)

        # 防覆盖：重读磁盘最新列表（内存 _jobs 可能过期 —— 运行期间用户删/建任务，
        # 或历史孤儿实例写过盘）。按 id 定位目标，不存在则仅写运行历史。
        disk_jobs = self._store.load_jobs()
        job = next((j for j in disk_jobs if j.id == job_id), None)
        label = job_id
        if job is not None:
            label = job.display_label()
            job.last_status = status
            job.last_error = error
            job.run_count += 1
            if status in ("success", "error", "timeout"):
                # 重算下次运行；at 类型跑完禁用
                if not job.recompute_next_run() and job.type == "at":
                    job.enabled = False
                    job.next_run_at = ""
            elif status == "cancelled":
                job.next_run_at = ""
            self._jobs = disk_jobs  # 内存同步为磁盘最新 + 本次更新
            self._store.save_jobs(self._jobs)
        self._store.append_run(
            job_id,
            {
                "ts": _dt.now().isoformat(timespec="seconds"),
                "label": label,
                "status": status,
                "durationMs": duration_ms,
                "toolCalls": tool_calls,
                "agent": job.agent if job else "",
                "model": job.model_key if job else "",
                "error": error,
                "responseHead": head,
                "responseText": response_text,
            },
        )

        # 还原工作目录
        if self._prev_workdir:
            try:
                set_workdir = (self._services or {}).get("set_workdir")
                if callable(set_workdir):
                    set_workdir(self._prev_workdir)
            except Exception:
                pass
            self._prev_workdir = ""

        # 清理 executor（延迟 deleteLater 避免 QThread Destroyed-while-running）
        ex = self._executor
        self._executor = None
        if ex is not None:
            try:
                ex.finished.connect(ex.deleteLater)
            except (RuntimeError, TypeError):
                pass

        # 通知 + UI 刷新（同步触发 jobs_changed + 直接调用 controller 刷新
        # ——避免信号同线程 queued 卡住时 UI 永远不更新）
        icon = {"success": "✅", "error": "❌", "timeout": "⏱", "cancelled": "🛑"}.get(status, "•")
        summary = head if status == "success" and head else (error or status)
        self.notify_requested.emit("定时任务", f"{icon}「{label}」{summary[:120]}")
        self.job_finished.emit(job_id, label, status, summary)
        self.jobs_changed.emit()

    def load_runs(self, job_id: str, limit: int = 20) -> List[dict]:
        return self._store.load_runs(job_id, limit)

    def is_job_running(self, job_id: str) -> bool:
        ex = self._executor
        return bool(ex and ex.isRunning() and ex._job and ex._job.id == job_id)
