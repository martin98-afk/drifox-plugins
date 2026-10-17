# -*- coding: utf-8 -*-
"""
服务商插件 — Moonshot (Kimi)

数据 + 余额查询 fetcher 全部由本插件声明（万物为插件）。
余额：GET /v1/users/me/balance（Bearer token，返回 available_balance 字段）。

模型清单与能力依据 Moonshot 开放平台官方文档（2026-10 核实）：
    - kimi-k3          1M 上下文，原生视觉，始终思考，reasoning_effort 三档
                      （low/high/max，默认 max）。temperature/top_p/n/penalty
                      固定不可改，传入其他值报错。
    - kimi-k2.7-code   256K 上下文，始终思考，Preserved Thinking 恒开，
                      不支持 reasoning_effort 与 tool_choice=required。
    - kimi-k2.6        256K 上下文，思考可开关（thinking:enabled/disabled），
                      非思考态 temperature 固定 0.6。
    kimi-k2.5 与 moonshot-v1 全系已于 2026-08-31 下线，kimi-k2 系 2026-05-25
    下线，故 models 不录入。

family 自建 moonshot-open：主程序 system-providers/zhipu.py 等已把默认 URL
指向各家 Coding/Token Plan 网关，能力表描述的是订阅网关而非按量主站。
Kimi 主站（api.moonshot.cn）为按量计费，上下文与思考参数约束均不同，
故不复用现有 family，独立声明避免能力表错配。
"""

from typing import Any, Dict, Optional

from app.plugins.registries.provider_registry import ProviderDef


def _fetch_moonshot_balance(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """从 Moonshot 获取账户可用余额（Bearer token，无需额外配置）。

    响应形态：{"code":123,"data":{"available_balance":49.58,...},"status":true}
    available_balance 已含代金券（voucher_balance）与现金（cash_balance）之和，
    直接取该字段即可，不必自行相加。
    """
    import requests

    api_key = (config.get("API_KEY", "") or "").strip()
    if not api_key:
        return None
    try:
        resp = requests.get(
            "https://api.moonshot.cn/v1/users/me/balance",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
    except Exception:
        return {"hide": True}
    if resp.status_code != 200:
        return {"hide": True, "tooltip": f"余额查询失败 (HTTP {resp.status_code})"}
    try:
        data = resp.json() or {}
    except Exception:
        return {"hide": True, "tooltip": "余额查询异常: 响应不是 JSON"}
    # 接口用 status=false 表示业务失败（如 key 无效），此时无 data 可用
    if data.get("status") is False:
        return {"hide": True, "tooltip": "余额查询失败: 账户状态异常"}
    inner = data.get("data") or {}
    balance = inner.get("available_balance")
    if balance is None:
        return {"hide": True}
    try:
        return {"balance": round(float(balance), 2), "currency": "¥"}
    except (TypeError, ValueError):
        return {"hide": True}


# K3 旗舰能力：1M 上下文 + 视觉 + reasoning_effort 三档
_MOONSHOT_CAPABILITIES = {
    "token_ratio": 1.00,
    "context_limit": 1000000,
    "max_output_tokens": 32768,
    "absolute_limit": 65536,
    "supports_vision": True,
    "supports_thinking": True,
    "thinking_param": "reasoning_effort",
    "reasoning_effort_param": "reasoning_effort",
}

# per-model 能力：K2.x 系上下文 256K，且 K2.x 用 thinking 开关而非 reasoning_effort
_MOONSHOT_MODEL_CAPABILITIES = {
    "kimi-k3": {
        "context_limit": 1000000,
        "max_output_tokens": 32768,
        "supports_vision": True,
        "supports_thinking": True,
        "thinking_param": "reasoning_effort",
        "reasoning_effort_values": ["low", "high", "max"],
    },
    "kimi-k2.7-code": {
        "context_limit": 262144,
        "max_output_tokens": 32768,
        "supports_vision": False,
        "supports_thinking": True,
        "thinking_param": "thinking",
    },
    "kimi-k2.7-code-highspeed": {
        "context_limit": 262144,
        "max_output_tokens": 32768,
        "supports_vision": False,
        "supports_thinking": True,
        "thinking_param": "thinking",
    },
    "kimi-k2.6": {
        "context_limit": 262144,
        "max_output_tokens": 32768,
        "supports_vision": True,
        "supports_thinking": True,
        "thinking_param": "thinking",
    },
}


def register(registry):
    """注册 Moonshot (Kimi) 服务商定义"""
    registry.register(
        ProviderDef(
            name="Moonshot (Kimi)",
            icon="moonshot",
            api_url="https://api.moonshot.cn/v1",
            preset_urls=[
                "https://api.moonshot.cn/v1",
                "https://api.moonshot.ai/v1",
            ],
            auth_type="bearer",
            default_model="kimi-k3",
            default_params={
                "温度": 1.0,
                "最大Token": 1000000,
                "思考模式": True,
                "思考等级": "max",
            },
            register_url="https://platform.moonshot.cn/console/api-keys",
            models=[
                "kimi-k3",
                "kimi-k2.7-code",
                "kimi-k2.7-code-highspeed",
                "kimi-k2.6",
            ],
            models_dev_id="moonshot",
            family="moonshot-open",
            capabilities=_MOONSHOT_CAPABILITIES,
            model_capabilities=_MOONSHOT_MODEL_CAPABILITIES,
            balance_fetcher=_fetch_moonshot_balance,
        )
    )
