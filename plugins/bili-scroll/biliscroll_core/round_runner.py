# -*- coding: utf-8 -*-
"""值班轮驱动：组装章程 + 设置 + 工具集，经引擎会话跑一轮。

工具执行说明：turn(tools=...) 只决定模型「看得见」哪些工具；B站能力经
MCP 工具（mcp__bili__*）调用，ToolExecutor 路由到宿主 MCP 桥（stdio 壳
→ HTTP → biliscroll_core/bili_impl.py 宿主进程内执行）。
"""
from __future__ import annotations

import datetime as _dt
import threading
from typing import Any, Dict, List

from loguru import logger

from .diagnostics import _schemas_with_timeout
from .paths import PLUGIN_ROOT
from .store import DutyStore

PLUGIN_NAME = "bili-scroll"
SKILL_PATH = PLUGIN_ROOT / "skills" / "bili-scroll-duty" / "SKILL.md"
ROUND_TIMEOUT_SECONDS = 20 * 60

# 值班轮可见的 B站工具名（MCP 形态：mcp__bili__<上游工具名>；写类需配置开启）
MCP_PREFIX = "mcp__bili__"
BASE_TOOLS = [
    MCP_PREFIX + n
    for n in (
        "bili_recommend", "bili_search", "bili_subtitle", "bili_video_info",
        "bili_comments", "bili_danmaku", "bili_cover", "bili_frames",
        "bili_user_info", "bili_seen_append",
    )
]
COMMENT_TOOLS = [MCP_PREFIX + "bili_reply"]            # auto_comment 开才给
REPLY_TOOLS = [MCP_PREFIX + "bili_received_replies"]   # reply_comments 开才给

def load_settings() -> Dict[str, Any]:
    from app.plugins.managers.plugin_config_store import PluginConfigStore

    values = PluginConfigStore().get_all(PLUGIN_NAME)
    # 数字字段归一化（config store 对 number 存 str）
    for key in ("daily_quota", "comment_quota"):
        try:
            values[key] = int(float(values.get(key) or 0))
        except (TypeError, ValueError):
            values[key] = 0
    for key in ("peak_noon", "peak_night", "auto_comment", "reply_comments"):
        values[key] = str(values.get(key)).lower() in ("1", "true", "yes", "on")
    values["report_mode"] = values.get("report_mode") or "full"
    return values


def _collect_tool_schemas(settings: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从宿主工具池取值班轮可见的 MCP 工具 schema（mcp__bili__ 前缀，tool.read）。"""
    allowed = set(BASE_TOOLS)
    if settings.get("auto_comment"):
        allowed |= set(COMMENT_TOOLS)
    if settings.get("reply_comments"):
        allowed |= set(REPLY_TOOLS)

    by_name: Dict[str, Dict[str, Any]] = {}
    try:
        # MCP 工具不进 ToolRegistry；mcp.call 能力直接给 MCPClientManager（_TOOL surface）
        mgr = _mcp_manager()
        by_server = _schemas_with_timeout(mgr) if mgr else {}
        for schema in by_server.get("bili", []):
            fn = (schema or {}).get("function") or {}
            if fn.get("name"):
                by_name[fn["name"]] = schema
    except Exception as e:
        logger.warning(f"[bili-scroll] 取 MCP 工具 schema 失败: {e}")

    out: List[Dict[str, Any]] = []
    missing: List[str] = []
    for name in sorted(allowed):
        schema = by_name.get(name)
        if schema is None:
            missing.append(name)
            continue
        out.append(schema)
    if missing:
        logger.warning(
            f"[bili-scroll] 值班轮缺 MCP 工具 schema：{', '.join(missing)}（MCP 未连接或控制端点未就绪）"
        )
    return out


def _opening_user_message(store: DutyStore, settings: Dict[str, Any]) -> str:
    """开场指令：设置快照 + 今日状态。章程在 system，这里只给本轮事实。"""
    picked = store.count_picked_today()
    quota = int(settings.get("daily_quota") or 0)
    keywords = (settings.get("keywords") or "").strip()
    lines = [
        f"今天是 {_dt.date.today().isoformat()}，开始这一轮值班。",
        f"- 关键词：{'已设置，逐行用 bili_search 搜（近 7 天优先）' if keywords else '未设置，用 bili_recommend 刷首页推荐流，随机挑，别固定取前 N'}",
        f"- 今天已挑 {picked} 条，配额 {quota} 条" + ("（已满，本轮只补归档与判重）" if quota and picked >= quota else ""),
        f"- 日报档位：{settings.get('report_mode')}（完整 full / 薄版 thin / 不写 none，判重表任何档位都要写）",
        f"- 日报：由系统把你最终回复整体写入 {store.report_path()}（每段以 ### BV号 开头）",
        f"- 判重：看过的每条视频都要 bili_seen_append 记一行（status 必填，「跳过」在 note 写一句理由）",
        f"- 归档：系统按判重记录自动生成（{store.digest_path()}），无需手动写",
    ]
    seen_rows = store.seen_recent(limit=200)
    if seen_rows:
        lines.append("- 最近判重记录（日期 BV号 状态，旧→新），出现过的一律跳过或只快速复核：")
        lines.extend(f"  {r['date']} {r['bvid']} {r['status']}" for r in reversed(seen_rows))
    if settings.get("auto_comment"):
        uid = (settings.get("my_uid") or "").strip()
        per_round = min(int(settings.get("comment_quota") or 1), 20)
        delivery = settings.get("delivery") or "comment"
        delivery_desc = {"comment": "只发公开评论", "dm_only": "只发私信（bili_send_message，一条公开评论都不发）",
                         "both": "公开评论照发，另加一条私信"}.get(delivery, "只发公开评论")
        lines += [
            f"- 自动评论：开着。投递方式：{delivery_desc}。每轮最多 {per_round} 条，@ UID {uid or '（未填，发不了 @，只写报告）'}",
            "- bili_reply 返回 blocked_by 时按提示改写一次，再被拦就不发并记入报告；"
            "私信上限 500 字符（code 21007 被拒就精简一次重发，一轮只发一条）",
        ]
    else:
        lines.append("- 自动评论：关着。本轮只看不发，bili_reply 不可用也不许尝试")
    if settings.get("reply_comments"):
        mine = store.my_recent_comments(days=7)
        if mine:
            lines.append("- 回复评论：开着。最近 7 天自己发过的评论（rpid | BV号 | 标题），只回直接回复到那条下面的，每条 ≤100 字：")
            lines.extend(f"  {r['rpid']} | {r['bvid']} | {r['title']}" for r in mine)
        else:
            lines.append("- 回复评论：开着，但最近 7 天没有自己发过的评论，本轮忽略")
    persona = (settings.get("persona") or "").strip()
    if persona:
        lines.append(f"- 使用者人设补充：{persona}")
    lines.append("转写：v1 未启用本地转写；没字幕的视频先按「演示类看画面」判断一次，看过仍说不清才跳过，"
                 "并在报告末尾写「因无字幕跳过 N 条」。")
    lines.append("保底：报告至少一行（「不写日报」档除外）、判重表至少一行，先把这两样落下再干别的。")
    return "\n".join(lines)


def _mcp_manager():
    """MCPClientManager 单例（mcp.call 能力投影返回完整实例，含 enable/disable_ephemeral）。"""
    try:
        from app.plugins.capabilities.resolve import pool_for

        pool = pool_for(plugin=PLUGIN_NAME, surface="tool") or {}
        mgr = pool.get("mcp.call")
        if callable(mgr):
            mgr = mgr()
        return mgr
    except Exception:
        return None


def _ensure_bili_mcp(max_tries: int = 3) -> bool:
    """值班前确保 bili MCP 可用；缺失时经 enable_ephemeral 临时拉起（不写 config）。

    插件 market 更新/重载后 MCP 注册表有一段空窗（"未注册 MCP server"），
    一次失败就放弃会让每次更新后的首跑必撞——按 2s/4s 退避重试穿透窗口。

    Returns:
        True = 本次值班临时拉起的，调用方结束须 disable_ephemeral("bili") 清理；
        False = 已常驻连接，或重试后仍失败（后续 _collect_tool_schemas 如实报空）。
    """
    import time as _time

    mgr = _mcp_manager()
    if mgr is None:
        return False
    transient = ("未找到", "未注册", "正在连接", "稍后", "稍等")
    for attempt in range(1, max_tries + 1):
        try:
            if mgr.get_tool_schemas_by_server().get("bili"):
                return False  # 已连接，无需临时态
            ok, payload = mgr.enable_ephemeral("bili")
            if ok:
                logger.info(f"[bili-scroll] bili MCP 临时开启成功（{len(payload)} 个工具，值班结束自动关闭）")
                return True
            logger.warning(f"[bili-scroll] bili MCP 临时开启失败（第 {attempt}/{max_tries} 次）：{payload}")
            if attempt < max_tries and any(k in str(payload) for k in transient):
                _time.sleep(2.0 * attempt)
                continue
        except Exception as e:
            logger.warning(f"[bili-scroll] bili MCP 临时开启异常：{type(e).__name__}: {e}")
        return False
    return False


def run_duty_round() -> Dict[str, Any]:
    """同步跑一轮（调用方负责放线程）。返回 {status, text, error, report_path}。

    模块级互斥：工具入口（bili_duty_run）与 UI 按钮（卡片）共用本函数，
    同一时刻只允许一轮；拿不到锁返回 status=busy。
    """

    if not _ROUND_LOCK.acquire(blocking=False):
        return {"status": "busy", "error": "已有一轮值班在跑", "text": ""}
    try:
        return _run_duty_round_locked()
    finally:
        _ROUND_LOCK.release()


_ROUND_LOCK = threading.Lock()


def _resolve_model_override(spec: str) -> Dict[str, Any]:
    """设置里的「值班模型」→ 宿主模型配置（含明文 key）。空串返回 {}（跟随当前对话模型）。

    spec 格式与 meeting-notes 对齐：``服务商:模型名``，也接受配置 ID / 服务商名
    （五级解析由宿主 model.config_for 负责）。解析失败抛 ValueError，由调用方
    转成人话错误显示，不静默回退到别的模型。
    """
    spec = (spec or "").strip()
    if not spec:
        return {}
    from app.plugins.capabilities.resolve import pool_for

    pool = pool_for(plugin=PLUGIN_NAME, surface="ui") or {}
    resolve = pool.get("model.config_for")
    if not callable(resolve):
        raise ValueError("宿主未提供 model.config_for，无法使用指定模型（可留空跟随当前对话模型）")
    cfg = resolve(spec) or {}
    if not isinstance(cfg, dict) or not cfg:
        raise ValueError(f"找不到模型配置：{spec}（检查服务商与模型名）")
    return {str(k): v for k, v in cfg.items()}


def _credential_ready() -> bool:
    """本地扫码凭证是否可用：没有就别开轮，否则整轮 B站工具全报未登录。"""
    try:
        from .diagnostics import _check_credential
        from .paths import plugin_data_root

        return str(_check_credential(plugin_data_root())).startswith("已存在（登录过）")
    except Exception as e:  # noqa: BLE001 — 预检失败不阻断，让轮内错误如实上报
        logger.warning(f"[bili-scroll] 凭证预检失败：{e}")
        return True


def _run_duty_round_locked() -> Dict[str, Any]:
    from app.plugins.capabilities.resolve import pool_for

    settings = load_settings()
    store = DutyStore()

    if not _credential_ready():
        return {
            "status": "need_login",
            "error": "B站未登录：先在对话里喊「扫码登录B站」完成扫码，再跑一轮",
            "text": "",
        }

    try:
        model_override = _resolve_model_override(str(settings.get("duty_model") or ""))
    except ValueError as e:
        return {"status": "error", "error": str(e), "text": ""}

    ephemeral = _ensure_bili_mcp()
    try:
        return _duty_round_with_tools(settings, store, model_override)
    finally:
        if ephemeral:
            try:
                mgr = _mcp_manager()
                if mgr is not None:
                    mgr.disable_ephemeral("bili")
                    logger.info("[bili-scroll] bili MCP 临时连接已关闭")
            except Exception as e:
                logger.warning(f"[bili-scroll] bili MCP 临时连接关闭失败：{type(e).__name__}: {e}")


def _duty_round_with_tools(settings: Dict[str, Any], store: DutyStore,
                           model_override: Dict[str, Any]) -> Dict[str, Any]:
    tools = _collect_tool_schemas(settings)
    if not tools:
        return {
            "status": "error",
            "error": "B站工具还没就绪（MCP 未连接）：等几秒再点一次，或重载插件后重试",
            "text": "",
        }

    pool_ui = pool_for(plugin=PLUGIN_NAME, surface="ui") or {}
    create_session = pool_ui.get("engine.session")
    if not callable(create_session):
        return {"status": "error", "error": "engine.session 能力不可用（未声明或无窗口）", "text": ""}

    charter = SKILL_PATH.read_text(encoding="utf-8") if SKILL_PATH.is_file() else ""
    if not charter:
        return {"status": "error", "error": f"值班章程缺失：{SKILL_PATH}", "text": ""}

    model_desc = str(settings.get("duty_model") or "").strip() or "跟随当前对话模型"
    logger.info(f"[bili-scroll] 值班轮开始（模型：{model_desc}，工具 {len(tools)} 个）")
    try:
        session = create_session(PLUGIN_NAME, model_config_override=model_override)
    except Exception as e:  # noqa: BLE001 — 常见于无活跃窗口或模型配置不可用
        logger.error(f"[bili-scroll] 创建值班会话失败：{type(e).__name__}: {e}")
        return {"status": "error", "error": f"创建值班会话失败：{type(e).__name__}: {e}", "text": ""}

    result = session.turn(
        system=charter,
        user=_opening_user_message(store, settings),
        tools=tools,
        timeout=ROUND_TIMEOUT_SECONDS,
    )
    err = getattr(result, "error", None)
    status = "error" if err else ("cancelled" if getattr(result, "cancelled", False)
                                  else ("timeout" if getattr(result, "timed_out", False) else "success"))
    text = str(getattr(result, "text", "") or "")
    if status == "success":
        # 落盘收口到代码（0.5.3）：不再依赖 LLM 调本地写盘工具（tools 组件开关
        # 曾导致全部 Unknown tool 而虚报成功）。success 才写，残缺轮不污染日报。
        if str(settings.get("report_mode") or "full") != "none":
            if text.strip():
                store.report_append(text)
            else:
                store.report_append(f"### 本轮无输出\n\n- 模型未产出文本（{model_desc}）")
        archive = store.digest_sync_today()
        logger.info(f"[bili-scroll] 值班轮完成（输出 {len(text)} 字，日报 {store.report_path()}，归档 {archive or '空'}）")
    else:
        logger.warning(f"[bili-scroll] 值班轮未完成（{status}）：{err or '无错误信息'}")
    return {
        "status": status,
        "error": str(err or ""),
        "text": text,
        "report_path": str(store.report_path()),
        "model": model_desc,
    }
