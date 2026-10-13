# -*- coding: utf-8 -*-
"""codebuddy-intl 插件测试：声明、认证模块、模型目录解析（全部不触网）。

运行：uv run pytest ~/.drifox/plugins/codebuddy-intl/tests -v
"""

import base64
import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_PROVIDER_FILE = _PLUGIN_ROOT / "providers" / "codebuddy_intl.py"
_AUTH_FILE = _PLUGIN_ROOT / "providers" / "_buddy_intl_auth.py"

pytestmark = pytest.mark.skipif(not _PROVIDER_FILE.exists(), reason="codebuddy-intl 插件不存在")


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def auth():
    return _load_module("codebuddy_intl_test_auth", _AUTH_FILE)


@pytest.fixture()
def fresh_provider_registry(monkeypatch):
    from app.plugins.registries.provider_registry import ProviderRegistry

    reg = ProviderRegistry()
    monkeypatch.setattr(ProviderRegistry, "get_instance", staticmethod(lambda: reg))
    return reg


def _make_jwt(claims: dict) -> str:
    """构造无签名三段式 JWT（header.payload.signature），仅供解析测试。"""
    b64 = lambda obj: (
        base64.urlsafe_b64encode(  # noqa: E731
            json.dumps(obj).encode()
        )
        .decode()
        .rstrip("=")
    )
    return f"{b64({'alg': 'none'})}.{b64(claims)}.sig"


# ── 认证模块：请求头 ────────────────────────────────────


def test_build_headers_carry_disguise(auth):
    """伪装身份九件套 + 鉴权头"""
    headers = auth.build_headers(access_token="at", refresh_token="rt")
    assert headers["X-Domain"] == "www.codebuddy.ai"
    assert headers["X-Product"] == "SaaS"
    assert headers["X-Product-Code"] == "codebuddy"
    assert headers["X-Agent-Intent"] == "craft"
    assert headers["X-Env-ID"] == "production"
    assert headers["User-Agent"].startswith("VSCode/")
    assert "CodeBuddy/" in headers["User-Agent"]
    assert headers["Authorization"] == "Bearer at"
    assert headers["X-Refresh-Token"] == "rt"


def test_anonymous_headers_strip_auth_and_add_no_marks(auth):
    """登录链匿名头：带 X-No-*，剥离鉴权"""
    headers = auth.build_anonymous_headers()
    assert headers["X-No-Authorization"] == "true"
    assert headers["X-No-User-Id"] == "true"
    assert "Authorization" not in headers
    assert "X-Refresh-Token" not in headers


# ── 认证模块：JWT / 身份头 ──────────────────────────────


def test_parse_jwt_claims_roundtrip(auth):
    token = _make_jwt({"tenant_id": "t1", "enterpriseId": "e1", "user_id": "u1"})
    claims = auth.parse_jwt_claims(token)
    assert claims["tenant_id"] == "t1"
    assert claims["enterpriseId"] == "e1"


def test_parse_jwt_claims_garbage_safe(auth):
    """非法 token 返回空表不抛"""
    assert auth.parse_jwt_claims("not-a-jwt") == {}
    assert auth.parse_jwt_claims("") == {}


def test_identity_headers_multi_key_compat(auth):
    """租户三元组多候选键名兼容；取不到的键省略"""
    token = _make_jwt({"tenantId": "t1", "user_id": "u1"})
    ident = auth.identity_headers(token)
    assert ident == {"X-Tenant-Id": "t1", "X-User-Id": "u1"}


def test_identity_headers_missing_ok(auth):
    token = _make_jwt({"exp": 123})
    assert auth.identity_headers(token) == {}


# ── 认证模块：刷新协议 ──────────────────────────────────


def test_refresh_sends_dual_head_and_parses_camel(auth, monkeypatch):
    """刷新：refresh_token 双头（Bearer + X-Refresh-Token）；响应驼峰字段兼容"""
    captured = {}

    def fake_request(method, path, body=None, access_token="", refresh_token="", timeout=30.0):
        captured.update(method=method, path=path, access_token=access_token, refresh_token=refresh_token)
        return {"code": 0, "data": {"accessToken": "new-at"}}

    monkeypatch.setattr(auth, "_request", fake_request)
    result = auth.refresh("rt-old")
    assert captured["method"] == "POST"
    assert captured["path"] == auth.TOKEN_REFRESH_PATH
    # 双头保留：Bearer 与 X-Refresh-Token 同值
    assert captured["access_token"] == "rt-old"
    assert captured["refresh_token"] == "rt-old"
    # 服务端不回 refreshToken 时沿用旧值；accessToken 驼峰可读
    assert result == {"access_token": "new-at", "refresh_token": "rt-old"}


def test_refresh_raises_on_business_error(auth, monkeypatch):
    monkeypatch.setattr(auth, "_request", lambda *a, **k: {"code": 401, "message": "expired"})
    with pytest.raises(RuntimeError, match="刷新失败"):
        auth.refresh("rt")


# ── 模型目录解析 ────────────────────────────────────────


def _install_provider(monkeypatch, tmp_path):
    """加载 provider 模块：缓存目录指到 tmp，auth 模块复用 fixture 实例。

    默认禁守护线程（DRIFOX_NO_CODEBUDDY_REFRESH=1）：测试不起真线程，
    _THREAD_STARTED 单例不被污染（bootstrap 开关用例因此始终有效）。
    """
    monkeypatch.setattr("app.utils.utils.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setenv("DRIFOX_NO_CODEBUDDY_REFRESH", "1")
    mod = _load_module("codebuddy_intl_test_provider", _PROVIDER_FILE)
    return mod


def test_fetch_models_route_slots_only(monkeypatch, tmp_path, auth):
    """动态路由：仅返回 craft 路由槽位；排除 auto-chat（11102）与非槽位条目

    2026-10-13 真机校准：槽位真源 = agents[craft].models，网关按账号动态
    分配实际模型，用户不接触模型 ID；结构变化时兜底取详情表 `*-model` 后缀。
    """
    mod = _install_provider(monkeypatch, tmp_path)
    monkeypatch.setattr(mod, "_load_auth_module", lambda: auth)
    monkeypatch.setattr(mod, "_exchange_access_token", lambda rt: "at")
    monkeypatch.setattr(
        auth,
        "fetch_config",
        lambda at: {
            # 对齐真机响应结构的关键样本
            "models": [
                {"id": "default-model", "supportsToolCall": True, "maxInputTokens": 176000, "maxOutputTokens": 24000, "supportsImages": True},
                {"id": "fast-model", "supportsToolCall": True, "maxInputTokens": 200000, "maxOutputTokens": 32000, "supportsImages": True},
                {"id": "balanced-model", "supportsToolCall": True, "maxInputTokens": 256000, "maxOutputTokens": 32000, "supportsImages": True},
                {"id": "primary-model", "supportsToolCall": True, "maxInputTokens": 272000, "maxOutputTokens": 72000, "supportsImages": True},
                {"id": "auto-chat", "supportsToolCall": True, "maxInputTokens": 168000, "maxOutputTokens": 32000, "supportsImages": False},
                {"id": "gpt-6-luna", "supportsToolCall": True, "maxOutputTokens": 128000},
                {"id": "claude-opus-4.8", "supportsToolCall": True, "maxOutputTokens": 131072},
                {"id": "completion-1.0", "maxOutputTokens": 256},
                {"id": "nes-1.2", "supportsToolCall": True, "maxOutputTokens": 8192},
            ],
            "agents": [
                {"name": "craft", "models": ["default-model", "fast-model", "balanced-model", "primary-model"]},
                {"name": "agent", "models": ["default-model", "auto-chat"]},
            ],
        },
    )
    assert mod._fetch_models({"API_KEY": "rt"}) == [
        "default-model",
        "fast-model",
        "balanced-model",
        "primary-model",
    ]


def test_fetch_models_slots_fallback_from_details(monkeypatch, tmp_path, auth):
    """服务端结构变化（agents 无 craft）→ 兜底取详情表 `*-model` 后缀条目"""
    mod = _install_provider(monkeypatch, tmp_path)
    monkeypatch.setattr(mod, "_load_auth_module", lambda: auth)
    monkeypatch.setattr(mod, "_exchange_access_token", lambda rt: "at")
    monkeypatch.setattr(
        auth,
        "fetch_config",
        lambda at: {
            "models": [
                {"id": "default-model", "supportsToolCall": True, "maxOutputTokens": 24000},
                {"id": "new-slot-model", "supportsToolCall": True, "maxOutputTokens": 32000},
                {"id": "gpt-6-luna", "supportsToolCall": True, "maxOutputTokens": 128000},
            ],
            "agents": [],
        },
    )
    assert mod._fetch_models({"API_KEY": "rt"}) == ["default-model", "new-slot-model"]


def test_fetch_models_fallback_without_config(monkeypatch, tmp_path, auth):
    """空目录 / 全被过滤 → 真机校准兜底清单"""
    mod = _install_provider(monkeypatch, tmp_path)
    monkeypatch.setattr(mod, "_load_auth_module", lambda: auth)
    monkeypatch.setattr(mod, "_exchange_access_token", lambda rt: "at")
    monkeypatch.setattr(auth, "fetch_config", lambda at: {"models": [], "agents": []})
    assert mod._fetch_models({"API_KEY": "rt"}) == mod._MODELS


def test_fetch_models_requires_login(monkeypatch, tmp_path):
    """未登录（空 API_KEY）直接报错，不触网"""
    mod = _install_provider(monkeypatch, tmp_path)
    with pytest.raises(RuntimeError, match="尚未登录"):
        mod._fetch_models({"API_KEY": ""})


# ── 插件声明侧 ──────────────────────────────────────────


def test_declares_international_provider(fresh_provider_registry, monkeypatch, tmp_path):
    """按 ProviderDef 注册 CodeBuddy International，family 独立（与国内版隔离）"""
    mod = _install_provider(monkeypatch, tmp_path)
    mod.register(fresh_provider_registry)
    provider = fresh_provider_registry.get("CodeBuddy International")
    assert provider is not None
    assert provider.family == "codebuddy_intl"
    assert provider.api_url == "https://www.codebuddy.ai/v2"
    assert provider.auth_type == "bearer"
    # 动态路由：默认与列表均为路由槽位，不暴露具体模型 ID
    assert provider.default_model == "default-model"
    assert provider.models == ["default-model", "fast-model", "balanced-model", "primary-model"]


def test_slot_capabilities_declare_thinking_and_vision(fresh_provider_registry, monkeypatch, tmp_path):
    """四槽位 per-model 能力：思考开关+强度、多模态、限额（主程序据此渲染

    思考配置项并自动补「思考模式」/「思考等级」（_merge_model_caps_into_config）。"""
    mod = _install_provider(monkeypatch, tmp_path)
    mod.register(fresh_provider_registry)
    caps = fresh_provider_registry.get("CodeBuddy International").model_capabilities
    assert set(caps) == {"default-model", "fast-model", "balanced-model", "primary-model"}
    limits = {
        "default-model": (176000, 24000),
        "fast-model": (200000, 32000),
        "balanced-model": (256000, 32000),
        "primary-model": (272000, 72000),
    }
    for mid, (ctx, out) in limits.items():
        entry = caps[mid]
        assert entry["context_limit"] == ctx
        assert entry["max_output_tokens"] == out
        assert entry["supports_thinking"] is True
        assert entry["thinking_param"] == "reasoning_effort"
        assert entry["reasoning_effort_values"] == ["low", "medium", "high", "xhigh"]
        assert entry["supports_vision"] is True


def test_fetch_models_syncs_slot_capabilities(monkeypatch, tmp_path, auth, fresh_provider_registry):
    """拉取成功后把槽位限额/多模态回写 ProviderDef.model_capabilities（思考键不动）"""
    mod = _install_provider(monkeypatch, tmp_path)
    monkeypatch.setattr(mod, "_load_auth_module", lambda: auth)
    monkeypatch.setattr(mod, "_exchange_access_token", lambda rt: "at")
    monkeypatch.setattr(
        auth,
        "fetch_config",
        lambda at: {
            "models": [
                # 服务端调额：primary 降到 128K/32K；auto-chat 不回写（非槽位）
                {"id": "primary-model", "supportsToolCall": True, "maxInputTokens": 128000, "maxOutputTokens": 32000, "supportsImages": False},
                {"id": "auto-chat", "supportsToolCall": True, "maxInputTokens": 999000, "maxOutputTokens": 99000, "supportsImages": True},
                # 缺限额字段的槽位：保留静态兜底值
                {"id": "fast-model", "supportsToolCall": True},
            ],
            "agents": [{"name": "craft", "models": ["primary-model", "fast-model"]}],
        },
    )
    reg = fresh_provider_registry
    mod.register(reg)
    pdef = reg.get("CodeBuddy International")
    mod._fetch_models({"API_KEY": "rt"})
    primary = pdef.model_capabilities["primary-model"]
    assert primary["context_limit"] == 128000
    assert primary["max_output_tokens"] == 32000
    assert primary["supports_vision"] is False
    # 思考三键以静态真机校准为准，不被详情字段冲掉
    assert primary["supports_thinking"] is True
    assert primary["reasoning_effort_values"] == ["low", "medium", "high", "xhigh"]
    # auto-chat 非路由槽位，不回写
    assert "auto-chat" not in pdef.model_capabilities
    # 缺限额字段：保留静态值
    assert pdef.model_capabilities["fast-model"]["context_limit"] == 200000


def test_capabilities_carry_intl_disguise_headers(fresh_provider_registry, monkeypatch, tmp_path):
    """capabilities 声明国际版伪装头 + 四个可调用头"""
    mod = _install_provider(monkeypatch, tmp_path)
    mod.register(fresh_provider_registry)
    caps = fresh_provider_registry.family_capabilities("codebuddy_intl")
    extra = caps.get("extra_headers")
    assert extra["X-Domain"] == "www.codebuddy.ai"
    assert extra["X-Agent-Intent"] == "craft"
    assert extra["User-Agent"] == "VSCode/1.119.0 CodeBuddy/4.9.29177644"
    for key in ("Authorization", "X-Tenant-Id", "X-Enterprise-Id", "X-User-Id"):
        assert callable(extra[key])


def test_family_declaration_via_registry(fresh_provider_registry, monkeypatch, tmp_path):
    """provider_name → family 声明优先链路（主程序 detect 的主路径）"""
    from app.utils.provider_ui_meta import get_family

    mod = _install_provider(monkeypatch, tmp_path)
    mod.register(fresh_provider_registry)
    assert get_family("CodeBuddy International") == "codebuddy_intl"


def test_capabilities_declare_thinking_and_context(fresh_provider_registry, monkeypatch, tmp_path):
    """族级能力声明：思考挡位（reasoning_effort，真机验证）+ 保守上下文/输出"""
    mod = _install_provider(monkeypatch, tmp_path)
    mod.register(fresh_provider_registry)
    caps = fresh_provider_registry.family_capabilities("codebuddy_intl")
    assert caps["supports_thinking"] is True
    assert caps["thinking_param"] == "reasoning_effort"
    assert caps["reasoning_effort_values"] == ["low", "medium", "high", "xhigh"]
    # 族级保守值：槽位最低（default-model 176K/24K），动态路由下作兑底
    assert caps["context_limit"] == 176000
    assert caps["max_output_tokens"] == 24000
    assert caps["absolute_limit"] == 72000
    assert caps["supports_vision"] is True


def test_per_model_capabilities_pipeline(fresh_provider_registry, monkeypatch, tmp_path):
    """per-model 声明贯通主程序解析链：get_model_capabilities 命中插件权威值

    动态路由槽位是私有命名，models.dev 不命中 → 插件 per-model 层压过一切。
    """
    from app.core.modelmeta.model_capabilities import (
        get_caps_max_output_tokens,
        get_model_capabilities,
    )

    mod = _install_provider(monkeypatch, tmp_path)
    mod.register(fresh_provider_registry)

    primary = get_model_capabilities("primary-model", "CodeBuddy International")
    assert primary["context_limit"] == 272000
    assert primary["max_output_tokens"] == 72000
    assert primary["thinking_param"] == "reasoning_effort"
    assert primary["supports_vision"] is True
    balanced = get_model_capabilities("balanced-model", "CodeBuddy International")
    assert balanced["context_limit"] == 256000
    assert balanced["reasoning_effort_values"] == ["low", "medium", "high", "xhigh"]

    # 输出上限链贯通（chat_worker._cap_max_output_tokens 的 L0 层）
    llm_config = {"模型名称": "primary-model", "provider_name": "CodeBuddy International"}
    assert get_caps_max_output_tokens("primary-model", llm_config) == 72000


# ── 积分查询（balance_fetcher）──────────────────────────


def test_fetch_balance_sums_remaining_credits(monkeypatch, tmp_path, auth):
    """积分 = 各套餐包 CycleCapacityRemainPrecise 之和（真机结构）"""
    mod = _install_provider(monkeypatch, tmp_path)
    monkeypatch.setattr(mod, "_load_auth_module", lambda: auth)
    monkeypatch.setattr(mod, "_exchange_access_token", lambda rt: "at")
    monkeypatch.setattr(
        auth,
        "user_resources",
        lambda at: [
            {"PackageName": "Bonus Pack", "CycleCapacityRemainPrecise": "245.7"},
            {"PackageName": "Free Plan Subscription", "CycleCapacityRemainPrecise": "100"},
        ],
    )
    assert mod._fetch_balance({"API_KEY": "rt"}) == {"balance": 345.7, "currency": ""}


def test_fetch_balance_none_without_key(monkeypatch, tmp_path):
    """无 API_KEY → None（不请求）"""
    mod = _install_provider(monkeypatch, tmp_path)
    assert mod._fetch_balance({"API_KEY": ""}) is None


def test_fetch_balance_hide_on_auth_failure(monkeypatch, tmp_path, auth):
    """凭据失效 → hide + tooltip（对齐国内版同款语义）"""
    mod = _install_provider(monkeypatch, tmp_path)

    def boom(rt):
        raise RuntimeError("refresh failed")

    monkeypatch.setattr(mod, "_exchange_access_token", boom)
    result = mod._fetch_balance({"API_KEY": "rt"})
    assert result == {"hide": True, "tooltip": "登录凭据失效，请重新自动登录"}


def test_fetch_balance_hide_on_api_error(monkeypatch, tmp_path, auth):
    """查询接口业务码异常 → hide + tooltip"""
    mod = _install_provider(monkeypatch, tmp_path)
    monkeypatch.setattr(mod, "_load_auth_module", lambda: auth)
    monkeypatch.setattr(mod, "_exchange_access_token", lambda rt: "at")

    def bad_resources(at):
        raise RuntimeError("get-user-resource 响应异常")

    monkeypatch.setattr(auth, "user_resources", bad_resources)
    assert mod._fetch_balance({"API_KEY": "rt"}) == {"hide": True, "tooltip": "积分查询失败"}


def test_auth_module_has_user_resources_endpoint(auth):
    """认证模块暴露 user_resources（billing 通道与国内版同构）"""
    assert auth.USER_RESOURCE_PATH == "/v2/billing/meter/get-user-resource"
    assert callable(auth.user_resources)


# ── 签到（checkin）──────────────────────────────────────


def test_checkin_status_passes_payload(auth, monkeypatch):
    """签到状态：POST checkin-activity-status，返回 data 段（真机蛇形字段）"""
    captured = {}

    def fake_request(method, path, body=None, access_token="", refresh_token="", timeout=30.0):
        captured.update(method=method, path=path, access_token=access_token)
        return {"code": 0, "data": {"active": True, "today_checked_in": False, "daily_credit": 100}}

    monkeypatch.setattr(auth, "_request", fake_request)
    status = auth.checkin_status("at")
    assert captured["method"] == "POST"
    assert captured["path"] == auth.CHECKIN_ACTIVITY_STATUS_PATH
    assert status["active"] is True
    assert status["today_checked_in"] is False


def test_checkin_claim_idempotent_codes(auth, monkeypatch):
    """领取：业务码 10001/1001 → already_claimed；0 → credit"""
    for code in (10001, 1001):
        monkeypatch.setattr(auth, "_request", lambda *a, **k: {"code": code})
        assert auth.checkin_claim("at")["already_claimed"] is True
    monkeypatch.setattr(auth, "_request", lambda *a, **k: {"code": 0, "data": {"credit": 100}})
    result = auth.checkin_claim("at")
    assert result["already_claimed"] is False
    assert result["credit"] == 100
    monkeypatch.setattr(auth, "_request", lambda *a, **k: {"code": 500, "message": "bad"})
    with pytest.raises(RuntimeError, match="签到失败"):
        auth.checkin_claim("at")


# ── 守护线程维护逻辑 ────────────────────────────────────


class _FakeAuth:
    """_maintain_account 的 auth 桩：记录调用，可编程返回"""

    def __init__(self, refresh_result=None, status=None, claim_error=None):
        self.refresh_result = refresh_result
        self.status = status or {}
        self.claim_error = claim_error
        self.claimed = 0
        self.refreshed_with = []

    def refresh(self, rt):
        self.refreshed_with.append(rt)
        if isinstance(self.refresh_result, Exception):
            raise self.refresh_result
        return self.refresh_result or {}

    def identity_headers(self, at):
        return {"X-User-Id": "u1"}

    def checkin_status(self, at):
        return self.status

    def checkin_claim(self, at):
        self.claimed += 1
        if self.claim_error:
            raise self.claim_error
        return {"already_claimed": False, "credit": 100}


def test_maintain_account_refresh_then_checkin(monkeypatch, tmp_path):
    """临期 + 活动开启未签 → 刷新 + 领取；refresh_token 轮换落新删旧"""
    mod = _install_provider(monkeypatch, tmp_path)
    ba = _FakeAuth(
        refresh_result={"access_token": "new-at", "refresh_token": "new-rt"},
        status={"active": True, "today_checked_in": False},
    )
    old_path = mod._cache_path("rt-old")
    old_path.parent.mkdir(parents=True, exist_ok=True)
    old_path.write_text(
        json.dumps({"refresh_token": "rt-old", "access_token": "old-at", "expires_at": 0}), encoding="utf-8"
    )
    action = mod._maintain_account(ba, {"refresh_token": "rt-old", "access_token": "old-at", "expires_at": 0})
    assert action == "refreshed+checked-in"
    assert ba.claimed == 1
    # 新缓存落盘、旧文件已删
    assert mod._cache_path("new-rt").exists()
    assert not old_path.exists()


def test_maintain_account_skips_when_not_active(monkeypatch, tmp_path):
    """活动关闭（active=false，当前账号实况）→ 不领取、不刷新（未临期）"""
    mod = _install_provider(monkeypatch, tmp_path)
    ba = _FakeAuth(status={"active": False, "today_checked_in": False})
    entry = {"refresh_token": "rt", "access_token": "at", "expires_at": time.time() + 72 * 3600}
    assert mod._maintain_account(ba, entry) == "idle"
    assert ba.claimed == 0
    assert ba.refreshed_with == []


def test_maintain_account_already_checked_in(monkeypatch, tmp_path):
    """活动开启但今日已签 → 跳过领取（幂等）"""
    mod = _install_provider(monkeypatch, tmp_path)
    ba = _FakeAuth(status={"active": True, "today_checked_in": True})
    entry = {"refresh_token": "rt", "access_token": "at", "expires_at": time.time() + 72 * 3600}
    assert mod._maintain_account(ba, entry) == "idle"
    assert ba.claimed == 0


def test_maintain_account_claim_failure_isolated(monkeypatch, tmp_path):
    """领取抛错 → 异常上抛由循环层隔离（单号失败不影响其余号）"""
    mod = _install_provider(monkeypatch, tmp_path)
    ba = _FakeAuth(status={"active": True, "today_checked_in": False}, claim_error=RuntimeError("x"))
    entry = {"refresh_token": "rt", "access_token": "at", "expires_at": time.time() + 72 * 3600}
    with pytest.raises(RuntimeError):
        mod._maintain_account(ba, entry)


def test_bootstrap_guard_and_loop_isolation(monkeypatch, tmp_path):
    """_bootstrap：测试开关不起线程；循环层单号失败隔离"""
    mod = _install_provider(monkeypatch, tmp_path)
    monkeypatch.setenv("DRIFOX_NO_CODEBUDDY_REFRESH", "1")
    started_before = mod._THREAD_STARTED
    mod._bootstrap()
    assert mod._THREAD_STARTED == started_before  # 开关生效，未启动

    # 循环体语义：sorted glob + 逐文件 try/except，坏文件不影响好号
    ba = _FakeAuth(status={"active": False})
    monkeypatch.setattr(mod, "_load_auth_module", lambda: ba)
    good = {"refresh_token": "rt-good", "access_token": "at", "expires_at": time.time() + 72 * 3600}
    (mod._CACHE_DIR / "bad.json").write_text("not-json", encoding="utf-8")
    (mod._CACHE_DIR / "good.json").write_text(json.dumps(good), encoding="utf-8")
    results = []
    for path in sorted(mod._CACHE_DIR.glob("*.json")):
        try:
            results.append(mod._maintain_account(ba, json.loads(path.read_text(encoding="utf-8"))))
        except Exception:
            results.append("error")
    assert "error" in results  # 坏文件被隔离
    assert "idle" in results  # 好号仍被维护


# ── token 缓存轮转 ──────────────────────────────────────


def test_cache_roundtrip_and_refresh(monkeypatch, tmp_path, auth):
    """缓存未临期命中；临期刷新回写并换 access_token"""
    mod = _install_provider(monkeypatch, tmp_path)
    monkeypatch.setattr(mod, "_load_auth_module", lambda: auth)
    calls = []

    def fake_refresh(rt):
        calls.append(rt)
        return {"access_token": f"at-{len(calls)}", "refresh_token": rt}

    monkeypatch.setattr(auth, "refresh", fake_refresh)
    first = mod._exchange_access_token("rt-1")
    assert first == "at-1"
    # 缓存命中：不再刷新
    assert mod._exchange_access_token("rt-1") == "at-1"
    assert len(calls) == 1
    # 强制临期 → 再刷
    mod._cache_get("rt-1")["expires_at"] = 0
    assert mod._exchange_access_token("rt-1") == "at-2"
    assert len(calls) == 2
    # 落盘可见（分流目录 codebuddy_intl/cache）
    files = list((tmp_path / "codebuddy_intl" / "cache").glob("*.json"))
    assert len(files) == 1


def test_identity_header_callable_reads_cache(monkeypatch, tmp_path, auth):
    """租户身份可调用值：从缓存 entry.identity 取；缺失返回空"""
    mod = _install_provider(monkeypatch, tmp_path)
    monkeypatch.setattr(mod, "_load_auth_module", lambda: auth)
    token = _make_jwt({"tenant_id": "t9"})
    monkeypatch.setattr(auth, "refresh", lambda rt: {"access_token": token, "refresh_token": rt})
    getter = mod._EXTRA_HEADERS["X-Tenant-Id"]
    assert getter({"API_KEY": "rt-id"}) == "t9"
    assert mod._EXTRA_HEADERS["X-User-Id"]({"API_KEY": "rt-id"}) == ""
