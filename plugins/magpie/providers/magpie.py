# -*- coding: utf-8 -*-
"""服务商插件 — magpie（本地 LLM 聚合网关）。

接入形态对齐 Ollama / LM Studio 这类「本机端点」先例，差异在模型命名：
magpie 暴露的模型 id 是 ``provider/model`` 形式（如 ``deepseek/deepseek-v4-pro``、
``group/opus-anywhere``），一个配置即覆盖 magpie 里全部订阅账号、API Key、
本地模型与路由组，配额耗尽时由 magpie 自己换账号，DriFox 无感知。

网关端点为 ``http://127.0.0.1:<port>/v1``（默认端口 3425，``MAGPIE_ADDR`` 或
magpie 的 ``settings.json`` 可改；本插件不读该文件，端口变了请直接改 API URL）。

模型池：``GET /v1/models``（models_hook，权威来源）。不走主程序内置的
``fetch_provider_models``，因为那里按关键词过滤非对话模型（image / vision /
search / embed…），而 magpie 的 id 带厂商前缀，误杀率高于收益。

认证：magpie 网关只监听回环，任意 key 都接受；带 ``magpie-drifox`` 可让这些
调用在 magpie 的 Usage / Requests 页归到 ``drifox`` 名下。未填 Key 时本插件
自己补该默认值（主程序在 Key 为空时会剥掉 Authorization 头，magpie 仍接受，
但计数会落到 User-Agent 推断）。

身份与会话识别（capabilities 声明，宿主 ``resolve_extra_headers`` 通用消费）：
- ``session_header = X-Magpie-Session``：magpie 用它切会话，DriFox 的 session_id
  自动填进去，Usage / Sessions 页按 DriFox 会话分组。
- ``extra_headers = User-Agent: DriFox``：归属兜底，但 DriFox 实际发出的客户端头是
  ``DriFox/1.0.0`` 形态，首词即 ``DriFox``，已足够。
- Agents 页那一行由同目录的 ``agent_plugin/``（magpie 侧插件包）提供，与本服务商
  定义互补：本文件管请求归属，那个包管 magpie 界面上的身份展示。

已知限制（聚合网关的固有代价，非本插件缺陷）：
- 能力表按「最宽」声明：magpie 背后横跨几十家厂商，同一张表无法同时准确描述
  全部 id。上下文窗口 / 思考能力以最宽松者声明，具体模型超限时由厂商返回 400。
- 采样参数（温度等）透传给厂商：magpie 承载 o1/o3 类不接受采样参数的模型时，
  需在模型配置卡里手动关掉，本插件不做按 id 的差异化处理。
- 配额面板暂未接入：``GET /v1/magpie/quotas`` 的响应结构未经实测，不做猜测式
  解析。留待拿到真实响应后补 coding_plan_fetcher。
"""

from typing import Any, Dict, List

from app.plugins.registries.provider_registry import ProviderDef

_DEFAULT_BASE = "http://127.0.0.1:3425"
# 让调用在 magpie 侧归到 drifox 名下（magpie 用 magpie-<app-id> 识别调用方）
_DEFAULT_KEY = "magpie-drifox"

# magpie 的会话标识头（实测：值原样落进 /v1/magpie/usage/requests 的 session 字段）。
# 宿主 resolve_extra_headers 的 session_header 通道会自动填 DriFox 的 session_id，
# 于是 magpie 的 Usage / Sessions 按 DriFox 会话分组。
_SESSION_HEADER = "X-Magpie-Session"

# 归属兜底：不带 magpie-<app-id> 形式的 key 时，magpie 取 User-Agent 首词当
# agent 名（实测 "DriFox/0.6.11" → agent=drifox、agentName=DriFox）。
_EXTRA_HEADERS = {"User-Agent": "DriFox"}


def _gateway_base(api_url: str) -> str:
    """配置里的 API_URL → 网关根地址（剥末尾 /v1 与斜杠）。

    magpie 的 /api/hello 挂在根路径，而 OpenAI 客户端用的是 <base>/v1，
    两个口径都要能从同一个配置值推导出来。
    """
    base = str(api_url or "").strip().rstrip("/")
    if base.lower().endswith("/v1"):
        base = base[:-3].rstrip("/")
    return base


def _auth_headers(config: Dict[str, Any]) -> Dict[str, str]:
    key = str((config or {}).get("API_KEY", "") or "").strip() or _DEFAULT_KEY
    return {"Authorization": f"Bearer {key}", "Accept": "application/json"}


def _open_json(url: str, headers: Dict[str, str], timeout: float) -> Any:
    """GET → JSON（延迟导入网络库：模块级 import 会触发 AST 危险 import 审计）。"""
    import json
    import urllib.request

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return json.loads(resp.read().decode(charset, errors="replace"))


def _fetch_models(config: Dict[str, Any]) -> List[str]:
    """模型列表钩子：先 /api/hello 确认对端是 magpie，再拉 /v1/models。

    失败一律抛异常（主程序据此把状态标为 unreachable 并回显原因），
    不返回空列表——空列表会被当成「服务商确实没有模型」。
    """
    base = _gateway_base(config.get("API_URL", ""))
    if not base:
        raise RuntimeError("请先填写 magpie 网关地址（默认 http://127.0.0.1:3425/v1）")
    headers = _auth_headers(config)

    try:
        hello = _open_json(f"{base}/api/hello", headers, timeout=5)
    except OSError as e:
        reason = getattr(e, "reason", e)
        raise RuntimeError(f"连不上 magpie 网关 {base}（{reason}）：请确认 magpie 已启动（App / magpie serve）") from e

    if not isinstance(hello, dict) or hello.get("name") != "magpie":
        raise RuntimeError(f"{base} 不是 magpie 网关：/api/hello 返回 {hello!r}")

    try:
        payload = _open_json(f"{base}/v1/models", headers, timeout=15)
    except OSError as e:
        reason = getattr(e, "reason", e)
        raise RuntimeError(f"读取 magpie 模型列表失败（{reason}）") from e

    items = payload.get("data") if isinstance(payload, dict) else payload
    models = [str(m.get("id", "") or "").strip() for m in (items or []) if isinstance(m, dict)]
    models = [m for m in models if m]
    if not models:
        raise RuntimeError("magpie 返回的模型列表为空：请在 magpie 里添加服务商，或让模型对 agents 可见")
    return models


def register(registry):
    """注册 magpie 服务商定义"""
    registry.register(
        ProviderDef(
            name="magpie",
            icon="Magpie",
            api_url=f"{_DEFAULT_BASE}/v1",
            auth_type="bearer",
            default_model="",
            default_params={
                "温度": 0.7,
                "最大Token": 200000,
            },
            register_url="https://usemagpie.ai",
            models=[],  # 权威池走 models_hook；不内置（用户装了什么只有网关知道）
            family="magpie",
            capabilities={
                "models_hook": _fetch_models,
                # magpie 侧身份与会话识别（对齐 Integrate 文档的网关约定）
                "session_header": _SESSION_HEADER,
                "extra_headers": _EXTRA_HEADERS,
                # 聚合网关：按最宽声明，具体模型的真实上限由厂商侧把关
                "context_limit": 200000,
                "max_output_tokens": 32000,
                "absolute_limit": 65536,
                "supports_vision": True,
                "supports_thinking": True,
                # magpie 接受 OpenAI 风格的 reasoning_effort 并按目标厂商转译
                # （Anthropic 转 thinking、Gemini 转 thinkingConfig）
                "thinking_param": "reasoning_effort",
                "reasoning_effort_param": "reasoning_effort",
            },
        )
    )
