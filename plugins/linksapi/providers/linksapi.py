"""LinksAPI 服务商 — 国内直连的 OpenAI 兼容中转网关。

模型列表为「GPT低价特供」分组 /v1/models 实测结果（2026-11-18）；
不同分组可见模型不同，用户可在设置中手动增删模型名。
"""
from app.plugins.registries.provider_registry import ProviderDef


def register(registry):
    registry.register(
        ProviderDef(
            name="LinksAPI",
            icon="linksapi",
            api_url="https://linksapi.cn/v1",
            auth_type="bearer",
            default_model="gpt-6.1-sol",
            default_params={"温度": 0.7, "最大Token": 16384},
            register_url="https://linksapi.cn/keys",
            models=[
                "gpt-5.4",
                "gpt-5.5",
                "gpt-5.6-luna",
                "gpt-5.6-sol",
                "gpt-5.6-terra",
                "gpt-6-astra",
                "gpt-6-sol",
                "gpt-6.1-sol",
                "gpt-6.1-terra",
            ],
            family="linksapi",
            capabilities={
                # 低价中转分组无官方能力表，取保守值：
                # context 256K（官方 272K 断崖前留余量）、暂不支持视觉与思考参数
                "token_ratio": 1.00,
                "context_limit": 262144,
                "max_output_tokens": 16384,
                "supports_vision": False,
                "supports_thinking": False,
            },
        )
    )
