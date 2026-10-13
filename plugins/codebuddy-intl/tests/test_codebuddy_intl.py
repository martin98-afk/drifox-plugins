# -*- coding: utf-8 -*-
"""codebuddy-intl 插件测试：声明、认证模块、模型目录解析（全部不触网）。

运行：uv run pytest ~/.drifox/plugins/codebuddy-intl/tests -v
"""

import base64
import importlib.util
import json
import sys
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
    """加载 provider 模块：缓存目录指到 tmp，auth 模块复用 fixture 实例。"""
    monkeypatch.setattr("app.utils.utils.get_app_data_dir", lambda: tmp_path)
    mod = _load_module("codebuddy_intl_test_provider", _PROVIDER_FILE)
    return mod


def test_fetch_models_real_ids_only(monkeypatch, tmp_path, auth):
    """仅真实模型 ID：滤槽位别名（*-model/auto-chat）、补全类、supportsToolCall=False

    2026-10-13 真机校准：craft 目录只是路由槽位，真实 ID（gpt-6-luna 等）
    可直传（真机 200）；claude 系账号门控仍列出。"""
    mod = _install_provider(monkeypatch, tmp_path)
    monkeypatch.setattr(mod, "_load_auth_module", lambda: auth)
    monkeypatch.setattr(mod, "_exchange_access_token", lambda rt: "at")
    monkeypatch.setattr(
        auth,
        "fetch_config",
        lambda at: {
            # 对齐真机响应结构的关键样本
            "models": [
                {"id": "default-model", "supportsToolCall": True, "maxOutputTokens": 24000},
                {"id": "primary-model", "supportsToolCall": True, "maxOutputTokens": 72000},
                {"id": "auto-chat", "supportsToolCall": True, "maxOutputTokens": 32000},
                {"id": "gpt-6-luna", "supportsToolCall": True, "maxOutputTokens": 128000},
                {"id": "claude-opus-4.8", "supportsToolCall": True, "maxOutputTokens": 131072},
                {"id": "claude-haiku-4.5", "supportsToolCall": True, "maxOutputTokens": 24000},
                # IDE 补全/嵌入类：输出上限过小或显式不支持工具 → 排除
                {"id": "completion-1.0", "maxOutputTokens": 256},
                {"id": "nes-1.2", "supportsToolCall": True, "maxOutputTokens": 8192},
                {"id": "enhance-1.0", "supportsToolCall": True},
                {"id": "gpt-image-2.5-sunburst", "supportsToolCall": False},
            ],
            "agents": [{"name": "craft", "models": ["default-model", "primary-model"]}],
        },
    )
    assert mod._fetch_models({"API_KEY": "rt"}) == [
        "gpt-6-luna",
        "claude-opus-4.8",
        "claude-haiku-4.5",
    ]


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
    assert provider.default_model == "gpt-6-luna"
    assert "auto" not in provider.models


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
    # 族级保守值：真实模型集最低（haiku 176K/24K），luna/opus 走 models.dev 覆盖
    assert caps["context_limit"] == 176000
    assert caps["max_output_tokens"] == 24000
    assert caps["absolute_limit"] == 131072
    assert caps["supports_vision"] is True


def test_per_model_capabilities_pipeline(fresh_provider_registry, monkeypatch, tmp_path):
    """per-model 声明贯通主程序解析链：get_model_capabilities 命中插件权威值

    2026-10-13 真机校准：claude 带点 ID 在 models.dev 不命中（官方带杠），
    luna 网关 1M 与官方 API 1.05M 各自成立 → 插件 per-model 层压过一切。
    """
    from app.core.modelmeta.model_capabilities import (
        get_caps_max_output_tokens,
        get_model_capabilities,
    )

    mod = _install_provider(monkeypatch, tmp_path)
    mod.register(fresh_provider_registry)

    opus = get_model_capabilities("claude-opus-4.8", "CodeBuddy International")
    assert opus["context_limit"] == 400000
    assert opus["max_output_tokens"] == 131072
    assert opus["thinking_param"] == "reasoning_effort"
    haiku = get_model_capabilities("claude-haiku-4.5", "CodeBuddy International")
    assert haiku["context_limit"] == 176000
    assert haiku["reasoning_effort_values"] == ["low", "medium", "high"]
    luna = get_model_capabilities("gpt-6-luna", "CodeBuddy International")
    assert luna["context_limit"] == 1000000
    assert "canDisableThinking" not in luna or luna.get("supports_thinking") is True

    # 输出上限链贯通（chat_worker._cap_max_output_tokens 的 L0 层）
    llm_config = {"模型名称": "claude-opus-4.8", "provider_name": "CodeBuddy International"}
    assert get_caps_max_output_tokens("claude-opus-4.8", llm_config) == 131072


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
