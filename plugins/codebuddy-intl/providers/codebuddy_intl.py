# -*- coding: utf-8 -*-
"""服务商插件 — 腾讯 CodeBuddy 国际版（www.codebuddy.ai 动态路由）。

动态路由：模型列表只暴露 craft 路由槽位（default-model / fast-model /
balanced-model / primary-model），网关按账号档位与任务动态分配实际模型
（gpt-6-luna / claude 系），用户不接触具体模型 ID，也不踩 11102 门控。

伪装 CodeBuddy VSCode 插件（craft 形态）接入国际版网关：身份标识
（X-Domain / X-Product / X-Agent-Intent / X-IDE-* 系 / User-Agent）经
capabilities["extra_headers"] 注入每个 LLM 请求，主程序
（chat_worker._provider_extra_headers）通用消费，无需感知具体服务商。

多账号模型：一条服务商配置 = 一个号（对齐国内版 CodeBuddy / OpenAI Codex 先例）。
    API Key 字段存该号的 refresh_token（长效不变 → config_id 稳定、原生加密链）。
    Authorization 头为可调用值：chat_worker 每次请求传入 llm_config，按
    refresh_token 从本地缓存取 access_token（临期自动刷新）——各配置各号。
租户身份头：access_token JWT 内提取 X-Tenant-Id / X-Enterprise-Id /
    X-User-Id，可调用值注入（取不到省略，不影响鉴权）。

凭据缓存：<app_data>/codebuddy_intl/cache/<hash>.json，与国内版
codebuddy/cache 分流，防 token 串号。

风险提示：非官方客户端协议实现，存在违反服务条款与封号风险，自行评估。
"""

import hashlib
import json
import os
import threading
import time
from pathlib import Path

from app.plugins.registries.provider_registry import ProviderDef
from app.utils.utils import get_app_data_dir

_ENDPOINT = "https://www.codebuddy.ai"
_CACHE_DIR = get_app_data_dir() / "codebuddy_intl" / "cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_REFRESH_SKEW_SEC = 6 * 3600  # 剩 6h 视为临期（access_token 实测 72h 级）
_REFRESH_INTERVAL_SEC = 6 * 3600  # 守护轮间隔（access_token 72h 级，6h 一轮足够）

_CACHE_LOCK = threading.Lock()
_CACHE: dict = {}  # refresh_token -> {"access_token","refresh_token","expires_at","identity"}


def _load_auth_module():
    """按路径加载同目录认证模块（providers 目录非包，loader 按文件加载）。"""
    import importlib.util

    auth_path = Path(__file__).with_name("_buddy_intl_auth.py")
    spec = importlib.util.spec_from_file_location("codebuddy_intl_auth", auth_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载认证模块: {auth_path}")
    ba = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ba)
    return ba


def _cache_path(refresh_token: str) -> Path:
    digest = hashlib.sha1(refresh_token.encode("utf-8")).hexdigest()[:12]
    return _CACHE_DIR / f"{digest}.json"


def _cache_get(refresh_token: str) -> dict:
    with _CACHE_LOCK:
        if refresh_token in _CACHE:
            return _CACHE[refresh_token]
    try:
        entry = json.loads(_cache_path(refresh_token).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        entry = {}
    entry.setdefault("refresh_token", refresh_token)
    with _CACHE_LOCK:
        _CACHE[refresh_token] = entry
    return entry


def _cache_put(refresh_token: str, access_token: str, identity: dict) -> None:
    entry = {
        "refresh_token": refresh_token,
        "access_token": access_token,
        "expires_at": time.time() + 72 * 3600,  # 服务端未回过期时间，按实测级记
        "identity": identity,
    }
    with _CACHE_LOCK:
        _CACHE[refresh_token] = entry
    _cache_path(refresh_token).write_text(json.dumps(entry), encoding="utf-8")


def _exchange_access_token(refresh_token: str) -> str:
    """按 refresh_token 取可用 access_token：缓存命中（未临期）直接返回，否则刷新。"""
    entry = _cache_get(refresh_token)
    if entry.get("access_token") and entry.get("expires_at", 0) > time.time() + _REFRESH_SKEW_SEC:
        return entry["access_token"]
    ba = _load_auth_module()
    new = ba.refresh(refresh_token)
    if not new.get("access_token"):
        raise RuntimeError("刷新未返回 access_token")
    identity = ba.identity_headers(new["access_token"])
    _cache_put(refresh_token, new["access_token"], identity)
    return new["access_token"]


def _cached_entry(refresh_token: str) -> dict:
    """取缓存 entry，必要时触发刷新（供身份头等可调用值复用）。"""
    entry = _cache_get(refresh_token)
    if not (entry.get("access_token") and entry.get("expires_at", 0) > time.time() + _REFRESH_SKEW_SEC):
        _exchange_access_token(refresh_token)
        entry = _cache_get(refresh_token)
    return entry


def _auth_header(llm_config: dict) -> str:
    """动态 Authorization 头：按当前配置的 API_KEY（refresh_token）换取。"""
    refresh_token = str((llm_config or {}).get("API_KEY", "") or "").strip()
    if not refresh_token:
        return ""
    try:
        return f"Bearer {_exchange_access_token(refresh_token)}"
    except Exception:
        return ""  # 换取失败回退空头（SDK 用 API_KEY 鉴权，报错由请求层透出）


def _make_identity_header(key: str):
    """生成单个租户身份头的可调用值：从缓存 entry.identity 取，缺失返回空。"""

    def _get(llm_config: dict) -> str:
        refresh_token = str((llm_config or {}).get("API_KEY", "") or "").strip()
        if not refresh_token:
            return ""
        try:
            return str(_cached_entry(refresh_token).get("identity", {}).get(key, "") or "")
        except Exception:
            return ""

    _get.__name__ = f"_identity_header_{key.lower().replace('-', '_')}"
    return _get


# 伪装身份头（来源：opencode/pi 扩展实测 2026-09/10；craft 形态）。
# Authorization 与租户三头为可调用值：chat_worker 每次请求传入 llm_config。
_EXTRA_HEADERS = {
    "X-Domain": "www.codebuddy.ai",
    "X-Product": "SaaS",
    "X-Product-Code": "codebuddy",
    "X-Agent-Intent": "craft",
    "X-IDE-Type": "VSCode",
    "X-IDE-Name": "VSCode",
    "X-IDE-Version": "1.119.0",
    "X-Product-Version": "4.9.29177644",
    "X-Env-ID": "production",
    "User-Agent": "VSCode/1.119.0 CodeBuddy/4.9.29177644",
    "Authorization": _auth_header,
    "X-Tenant-Id": _make_identity_header("X-Tenant-Id"),
    "X-Enterprise-Id": _make_identity_header("X-Enterprise-Id"),
    "X-User-Id": _make_identity_header("X-User-Id"),
}

# 路由槽位（动态路由：用户只选槽位，网关动态分配实际模型）。
# 2026-10-14 真机校准：槽位真源 = /v3/config data.agents[craft].models；
# auto-chat 直传报 11102（agent 内部兜底别名），不暴露。
_MODELS = ["default-model", "fast-model", "balanced-model", "primary-model"]

# per-model 能力声明（2026-10-13 /v3/config 槽位详情真机校准 + reasoning_effort
# 真机验证：四槽位透传 low/xhigh 均 200，reasoning_tokens 拉开差距；default-model
# 详情无 reasoning 字段但透传同样生效，故思考声明与详情字段解耦）。
# 限额/多模态随 models_hook 动态回写（_sync_slot_capabilities），静态值为兜底。
_THINKING_IE = "reasoning_effort"
_ROUTE_EFFORTS = ["low", "medium", "high", "xhigh"]
_MODEL_CAPABILITIES = {
    "default-model": {
        "context_limit": 176000,
        "max_output_tokens": 24000,
        "absolute_limit": 24000,
        "supports_thinking": True,
        "thinking_param": _THINKING_IE,
        "reasoning_effort_values": _ROUTE_EFFORTS,
        "supports_vision": True,
        "note": "Auto 路由槽位（isDefault）：不带 effort 思考关，透传 effort 思考开",
    },
    "fast-model": {
        "context_limit": 200000,
        "max_output_tokens": 32000,
        "absolute_limit": 32000,
        "supports_thinking": True,
        "thinking_param": _THINKING_IE,
        "reasoning_effort_values": _ROUTE_EFFORTS,
        "supports_vision": True,
        "note": "Fast 路由槽位（credits x0.34）：响应快，适合简单任务",
    },
    "balanced-model": {
        "context_limit": 256000,
        "max_output_tokens": 32000,
        "absolute_limit": 32000,
        "supports_thinking": True,
        "thinking_param": _THINKING_IE,
        "reasoning_effort_values": _ROUTE_EFFORTS,
        "supports_vision": True,
        "note": "Balanced 路由槽位（credits x0.59）：速度与质量兼顾",
    },
    "primary-model": {
        "context_limit": 272000,
        "max_output_tokens": 72000,
        "absolute_limit": 72000,
        "supports_thinking": True,
        "thinking_param": _THINKING_IE,
        "reasoning_effort_values": _ROUTE_EFFORTS,
        "supports_vision": True,
        "note": "Primary 路由槽位（credits x3.31）：高质量输出，复杂任务",
    },
}

# data.models 全表里不可作为对话模型暴露的内部别名（2026-10-14 真机校准）：
# auto-chat 是 agent 内部兜底别名，直传报 11102；enhance-1.0 为 prompt 增强专用。
# 其余小模型（nes-* / completion-1.0 / codewise-jump / 图像类）靠 out<16000 剔除。
_HIDDEN_MODEL_IDS = {"auto-chat", "enhance-1.0"}
# 对话级模型输出下限：低于此值为补全/嵌入/图像类小模型（真机表见上）
_DIALOGUE_MIN_OUTPUT_TOKENS = 16000


def _is_dialogue_model(mid: str, m: dict) -> bool:
    """判断全表条目是否为可暴露的对话级模型（真实模型 ID 用）。

    槽位别名（`*-model` 后缀）不走这条判据：它们由 agents[craft].models 单独
    提供，此处排除以防与槽位列表重复。
    """
    if mid.endswith("-model") or mid in _HIDDEN_MODEL_IDS:
        return False
    try:
        out = int(m.get("maxOutputTokens") or 0)
    except (TypeError, ValueError):
        out = 0
    return out >= _DIALOGUE_MIN_OUTPUT_TOKENS


def _auto_login():
    """自动登录钩子（编辑卡后台线程调用）：弹浏览器授权，回填长效 refresh_token。"""
    ba = _load_auth_module()
    result = ba.login(timeout_sec=280)
    access_token = result["access_token"]
    refresh_token = result.get("refresh_token", "")
    account = result.get("account") or {}
    nickname = account.get("nickname") or account.get("name") or "CodeBuddy"

    api_key = refresh_token or access_token
    if refresh_token:
        # 预热：保存后立即可聊天 + 落租户身份
        identity = ba.identity_headers(access_token)
        _cache_put(refresh_token, access_token, identity)

    info = f"登录成功（{nickname}）：API Key 为长效续期令牌，聊天自动换取访问令牌"
    return {"api_key": api_key, "info": info + "，API Key 已回填请保存"}


def _sync_slot_capabilities(exposed: list, details: dict) -> None:
    """把 /v3/config 限额与多模态回写 ProviderDef.model_capabilities（就地）。

    models_hook 被「获取模型列表」/自动刷新调用时同步服务端最新值，只写本次
    暴露给用户的条目（exposed）——非工具调用类与未列入 craft 的模型不回写：
    context_limit←maxInputTokens、max_output_tokens/absolute_limit←maxOutputTokens、
    supports_vision←supportsImages。思考三键以静态真机校准为准：槽位
    reasoning_effort 透传均 200 且生效，详情是否带 reasoning 字段不作关闭依据。
    """
    try:
        from app.plugins.registries.provider_registry import ProviderRegistry

        pdef = ProviderRegistry.get_instance().get("CodeBuddy International")
    except Exception:
        return
    if pdef is None:
        return
    caps = pdef.model_capabilities
    for mid in exposed:
        m = details.get(mid)
        if not isinstance(m, dict):
            continue
        entry = caps.get(mid)
        if not isinstance(entry, dict):
            entry = {}
            caps[mid] = entry
        try:
            ctx = int(m.get("maxInputTokens") or 0)
            out = int(m.get("maxOutputTokens") or 0)
        except (TypeError, ValueError):
            continue
        if ctx > 0:
            entry["context_limit"] = ctx
        if out > 0:
            entry["max_output_tokens"] = out
            entry["absolute_limit"] = out
        if "supportsImages" in m:
            entry["supports_vision"] = bool(m.get("supportsImages"))


def _fetch_models(config):
    """模型列表获取钩子（签名对齐 balance_fetcher）：craft 路由槽位 + 真实模型 ID。

    2026-10-14 真机校准：两个来源合并——
    1. 路由槽位：data.agents[name=craft].models（default/fast/balanced/primary-model），
       网关按账号档位自动分配实际模型；
    2. 真实模型 ID：data.models 全表中的对话级模型（gpt-6-luna / claude 系），
       用户精确指定，档位不足时报 11102 自行剔除。

    槽位不会出现在全表筛选结果里（其 id 带 `*-model` 后缀且属路由别名），两类
    天然不重复。全表筛选剔除非工具调用类（补全/嵌入/图像小模型，out<16000）与
    内部专用别名（auto-chat 报 11102、enhance-1.0 为 prompt 增强专用）。
    """
    refresh_token = str((config or {}).get("API_KEY", "") or "").strip()
    if not refresh_token:
        raise RuntimeError("尚未登录：请先点击「自动登录」")
    ba = _load_auth_module()
    token = _exchange_access_token(refresh_token)
    cfg = ba.fetch_config(token)
    details = {
        str(m.get("id") or "").strip(): m
        for m in (cfg.get("models") or [])
        if isinstance(m, dict) and str(m.get("id") or "").strip()
    }
    slots: list = []
    for a in cfg.get("agents") or []:
        if isinstance(a, dict) and a.get("name") == "craft":
            slots = [str(s).strip() for s in (a.get("models") or []) if str(s or "").strip()]
            break
    # 真实模型 ID：全表筛对话级（剔除非工具调用类与内部专用别名）
    real_ids = [
        mid
        for mid, m in details.items()
        if m.get("supportsToolCall") is not False and _is_dialogue_model(mid, m)
    ]
    picked = [s for s in slots if s in details] + real_ids
    if not picked:
        return list(_MODELS)
    _sync_slot_capabilities(picked, details)
    return picked


def _fetch_balance(config):
    """积分查询（对齐国内版同款通道，2026-10-13 国际版真机验证同构）：
    按本配置的号返回可用积分合计（Bonus Pack + Free Plan 等套餐包剩余之和）。
    """
    refresh_token = str((config or {}).get("API_KEY", "") or "").strip()
    if not refresh_token:
        return None
    try:
        token = _exchange_access_token(refresh_token)
    except Exception:
        return {"hide": True, "tooltip": "登录凭据失效，请重新自动登录"}
    try:
        left = sum(float(r.get("CycleCapacityRemainPrecise") or 0) for r in _load_auth_module().user_resources(token))
    except Exception:
        return {"hide": True, "tooltip": "积分查询失败"}
    return {"balance": round(left, 1), "currency": ""}


# ── 守护线程：临期刷新 + 每日自动签到（移植国内版，幂等安全）──────────
# 与解释器拆解竞态的防护对齐国内版先例：
# - 退出信标：aboutToQuit 置位，线程在分段睡眠间隙退出，不再 exec auth 模块
# - 预热：启动时先加载一次 auth 模块（sys.modules 缓存），退出期 exec 命中
#   缓存 import，避免「拆解中首次 import email/urllib」的 Windows 退出竞态
# - 测试/CI（DRIFOX_NO_CODEBUDDY_REFRESH=1）不启动
_STOP_EVENT = threading.Event()
_THREAD_STARTED = False


def _maintain_account(ba, entry: dict) -> str:
    """维护单号：临期刷新 access_token + 每日自动签到（幂等）。返回动作摘要。

    签到判定：active 且今日未签才领取（活动关闭/已签均跳过，天然安全——
    daily-checkin 端点仅在活动开启时被触达）。刷新后 refresh_token 可能
    轮换：缓存落新值、旧文件删除，配置里的旧 rt 仅作冷启动兜底。
    """
    rt = str(entry.get("refresh_token", "") or "").strip()
    if not rt:
        return "skip:no-rt"
    at = str(entry.get("access_token", "") or "")
    action = "idle"
    if entry.get("expires_at", 0) <= time.time() + 24 * 3600:
        new = ba.refresh(rt)
        if new.get("access_token"):
            at = new["access_token"]
            new_rt = new.get("refresh_token") or rt
            _cache_put(new_rt, at, ba.identity_headers(at))
            if _cache_path(rt) != _cache_path(new_rt):
                _cache_path(rt).unlink(missing_ok=True)
            rt = new_rt
            action = "refreshed"
    if not at:
        return action or "skip:no-at"
    status = ba.checkin_status(at)
    if (
        isinstance(status, dict)
        and status.get("active")
        and not (status.get("today_checked_in") or status.get("todayCheckedIn"))
    ):
        ba.checkin_claim(at)
        return "checked-in" if action == "idle" else "refreshed+checked-in"
    return action


def _refresh_loop():
    """守护循环：遍历缓存内全部号维护；一轮 6h，分段睡眠支持秒级退出。"""
    try:
        _load_auth_module()  # 预热：退出期不再首次加载 auth 模块
    except Exception:
        pass
    while not _STOP_EVENT.is_set():
        try:
            ba = _load_auth_module()
            for path in sorted(_CACHE_DIR.glob("*.json")):
                try:
                    entry = json.loads(path.read_text(encoding="utf-8"))
                    _maintain_account(ba, entry)
                except Exception:
                    continue  # 单号失败不影响其余号
        except Exception:
            pass  # 守护线程不允许退出
        for _ in range(_REFRESH_INTERVAL_SEC):
            if _STOP_EVENT.is_set():
                return
            time.sleep(1)


def _bootstrap():
    """注册时启动守护线程（热重载重复启动无害：daemon 且幂等写）。"""
    global _THREAD_STARTED
    if _THREAD_STARTED:
        return
    if os.environ.get("DRIFOX_NO_CODEBUDDY_REFRESH") == "1":
        return
    _THREAD_STARTED = True
    _STOP_EVENT.clear()
    threading.Thread(target=_refresh_loop, daemon=True).start()
    try:
        from PyQt5.QtCore import QCoreApplication

        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(_STOP_EVENT.set)
    except Exception:
        pass


def register(registry):
    _bootstrap()
    registry.register(
        ProviderDef(
            name="CodeBuddy International",
            icon="codebuddy",
            api_url="https://www.codebuddy.ai/v2",
            auth_type="bearer",
            default_model="default-model",
            default_params={"温度": 0.7, "最大Token": 176000},
            register_url="https://www.codebuddy.ai/",
            models=_MODELS,
            model_capabilities=_MODEL_CAPABILITIES,
            balance_fetcher=_fetch_balance,
            # 独立 family：与国内版 codebuddy 族隔离。family_capabilities 按
            # family 聚合（后注册覆盖同名字段），两套 extra_headers 共族会互相
            # 覆盖（伪装域错串）；主程序对 codebuddy 族无行为特判，独立无副作用
            family="codebuddy_intl",
            capabilities={
                "extra_headers": _EXTRA_HEADERS,
                "login_hook": _auto_login,
                "models_hook": _fetch_models,
                # ── 族级能力（2026-10-13 真机校准）─────────────────────
                # 思考：reasoning_effort 四槽位真机验证被网关接受（low/xhigh
                # 均 200，reasoning_tokens 拉开差距）；思考内容不透传 delta。
                "supports_thinking": True,
                "thinking_param": "reasoning_effort",
                "reasoning_effort_values": ["low", "medium", "high", "xhigh"],
                # 上下文/输出：族级保守兜底（per-model 已按槽位校准并动态回写）
                "context_limit": 176000,
                "max_output_tokens": 24000,
                "absolute_limit": 72000,
                "supports_vision": True,
            },
        )
    )
