# -*- coding: utf-8 -*-
"""团队数据访问层 — TeamManager / 窗口实例 / 模板 / 上下文快照

延迟 import app.*（避免顶层循环依赖与热重载竞态）。
所有函数均带 try/except 兜底，保证 UI 在任何异常下不崩溃。
"""

from typing import Any, Dict, List, Optional

from loguru import logger


# ── 主窗口定位 ───────────────────────────────────────────


def _main_window():
    """获取第一个存活的主窗口实例（团队操作以它为准）"""
    try:
        from app.core.window_registry import alive_window_instances

        wins = alive_window_instances()
        for win in wins:
            if win is not None and not getattr(win, "_is_destroyed", False):
                return win
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[pixel-team-studio] 定位主窗口失败: {e}")
    return None


def _find_window(window_id: str):
    """按 window_id 查找存活窗口实例"""
    try:
        from app.core.window_registry import alive_window_instances

        for win in alive_window_instances():
            if win is not None and getattr(win, "_window_id", "") == window_id:
                return win
    except Exception:  # noqa: BLE001
        pass
    return None


def _team_manager():
    from app.core.team_manager import TeamManager

    return TeamManager.get_instance()


# ── 团队列表 ─────────────────────────────────────────────


def get_teams() -> List[Dict[str, Any]]:
    """获取全部团队（按 run_id 分组）+ 未分组团队

    返回：[{run_id, label, members: [member dict], is_active}]
    """
    try:
        tm = _team_manager()
        teams = []
        active_run = tm.get_team_run_id()
        for rid in tm.get_team_run_ids():
            members = tm.get_members(run_id=rid)
            label = tm.get_team_label_by_run(rid) or rid[:8]
            teams.append(
                {
                    "run_id": rid,
                    "label": label,
                    "members": members,
                    "is_active": rid == active_run,
                }
            )
        # 未归属成员（无 run_id）
        ungrouped = tm.get_members(run_id="")
        if ungrouped:
            teams.append({"run_id": "", "label": "未分组", "members": ungrouped, "is_active": False})
        return teams
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[pixel-team-studio] get_teams 失败: {e}")
        return []


def get_active_run_id() -> str:
    """当前激活团队 run_id"""
    try:
        return _team_manager().get_team_run_id()
    except Exception:  # noqa: BLE001
        return ""


# ── 成员状态与上下文 ─────────────────────────────────────


def get_member_state(member: Dict[str, Any]) -> str:
    """成员工作状态：优先窗口实时 AI 状态（streaming/thinking/question/error），
    否则回退团队 busy/idle"""
    wid = member.get("window_id", "")
    win = _find_window(wid)
    if win is not None:
        ai = getattr(win, "_ai_state", "") or ""
        if ai in ("streaming", "thinking", "question", "error"):
            return ai
    try:
        return _team_manager().get_member_busy_status(wid)
    except Exception:  # noqa: BLE001
        return "idle"


def get_member_context(member: Dict[str, Any]) -> Dict[str, float]:
    """成员上下文负荷快照：{used, budget, percent}

    与主程序上下文圆环同源（backend.get_context_usage_snapshot），
    快照内部有 30s 工具 schema 缓存，5s 轮询开销可控。
    """
    wid = member.get("window_id", "")
    win = _find_window(wid)
    if win is None:
        return {"used": 0, "budget": 0, "percent": 0}
    try:
        session = win.session_manager.get_current_session()
        cfg = win._get_current_model_config()
        snap = win.backend.get_context_usage_snapshot(session, cfg)
        return {
            "used": snap.get("used_tokens", 0) or 0,
            "budget": snap.get("budget_tokens", 0) or 0,
            "percent": snap.get("percent", 0) or 0,
        }
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[pixel-team-studio] 上下文快照失败({wid}): {e}")
        return {"used": 0, "budget": 0, "percent": 0}


def get_member_task_count(member: Dict[str, Any]) -> int:
    """成员未完成任务数（pending/running 邮件）"""
    wid = member.get("window_id", "")
    try:
        return len(_team_manager().get_pending_tasks(wid)) + len(
            _team_manager().get_running_tasks(wid)
        )
    except Exception:  # noqa: BLE001
        return 0


# ── 智能体库 ─────────────────────────────────────────────


def list_agents() -> List[Dict[str, str]]:
    """所有可组建团队的 @智能体角色：[{name, description, mode}]"""
    try:
        from app.core.agent import AgentManager

        am = AgentManager.get_instance()
        agents = []
        for a in am.list_agents(include_hidden=False):
            if getattr(a, "mode", "subagent") in ("subagent", "all"):
                agents.append(
                    {
                        "name": a.name,
                        "description": getattr(a, "description", "") or "",
                        "mode": getattr(a, "mode", ""),
                    }
                )
        # 稳定排序：leader/plan/build 优先，其余按名
        priority = {"leader": 0, "plan": 1, "build": 2, "review": 3, "code-reviewer": 4, "explore": 5}
        agents.sort(key=lambda x: (priority.get(x["name"], 9), x["name"]))
        return agents
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[pixel-team-studio] list_agents 失败: {e}")
        return []


# ── 团队模板 ─────────────────────────────────────────────


def list_templates() -> List[Dict[str, Any]]:
    """可用团队模板：[{name, description, agent_count, agent_names, source}]"""
    try:
        from app.core.team.template_manager import TemplateManager

        return TemplateManager.get_instance().list_templates()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[pixel-team-studio] list_templates 失败: {e}")
        return []


# ── 团队操作 ─────────────────────────────────────────────


def create_team_from_template(template_name: str) -> int:
    """从模板一键创建团队：新 run_id + 为每个角色新建成员窗口

    复用主窗口 _spawn_team_members（与 /team --load 同链路，无确认弹窗）。
    返回成功创建窗口数；失败返回 -1。
    """
    try:
        from app.core.team.template_manager import TemplateManager

        template = TemplateManager.get_instance().load(template_name)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[pixel-team-studio] 模板加载失败: {e}")
        return -1

    win = _main_window()
    if win is None:
        return -1

    try:
        tm = _team_manager()
        new_run_id = tm.start_team_run(force=True)
        tm.set_template(
            {
                "name": template.template_name,
                "description": template.description,
                "agents": [
                    {"agent_name": a.agent_name, "description": a.description}
                    for a in template.agents
                ],
            }
        )
        count = win._spawn_team_members(
            [a.agent_name for a in template.agents],
            run_id=new_run_id,
            team_label=template.template_name,
            team_name="default",
        )
        return count
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[pixel-team-studio] 创建团队失败: {e}")
        return -1


def add_member(agent_name: str, run_id: str, team_label: str) -> bool:
    """拖拽添加成员：为角色新建成员窗口并加入指定团队"""
    win = _main_window()
    if win is None:
        return False
    try:
        count = win._spawn_team_members(
            [agent_name],
            run_id=run_id or "",
            team_label=team_label or "",
            team_name="default",
        )
        return count > 0
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[pixel-team-studio] 添加成员失败({agent_name}): {e}")
        return False


def remove_member(window_id: str) -> bool:
    """拖拽移除成员：离开团队（窗口保留，恢复独立模式）"""
    win = _find_window(window_id)
    if win is not None:
        try:
            win._handle_team_leave()
            return True
        except Exception as e:  # noqa: BLE001
            logger.exception(f"[pixel-team-studio] 移除成员失败({window_id}): {e}")
            return False
    try:
        _team_manager().leave_team(window_id)
        return True
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[pixel-team-studio] 清理失效成员失败({window_id}): {e}")
        return False
