# -*- coding: utf-8 -*-
"""voice-reply 在线 TTS 预设数据：服务商端点 + 模型 → 音色包。

独立成模块的理由：`ui/__init__.py` 的设置卡与运行时都要读这份数据，
且它必须是纯数据（无 Qt、无 IO），便于单测与后续补充。

数据口径（2026-10-18 核对硅基流动官方文档）：
- 预置音色 8 个：alex / benjamin / charles / david / anna / bella / claire / diana。
  CosyVoice2-0.5B 与 fish-speech-1.5 **音色名完全一致**，voice 值统一为
  `<model>:<voice>`，切换模型时只需替换冒号前缀。
- MOSS-TTSD-v0.5 是对话合成模型（input 需 [S1]/[S2] 标记，voice 走参考音频
  uri），单段播报用不上，列出来只为允许用户手填，不提供音色包。
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple
from urllib.parse import urlsplit


class EndpointPreset(NamedTuple):
    """一个在线 TTS 服务商：端点 + 平台名 + 密钥获取页。

    key_url 是各平台控制台的 API Key 管理页（2026-10 逐个验证可访问）。
    """

    url: str
    label: str
    key_url: str
    key_label: str


# ── 服务商端点预设（OpenAI 兼容 /audio/speech） ──
ENDPOINT_PRESETS: List[EndpointPreset] = [
    EndpointPreset(
        "https://api.siliconflow.cn/v1/audio/speech",
        "硅基流动 SiliconFlow（默认）",
        "https://cloud.siliconflow.cn/account/ak",
        "去硅基流动创建 Key",
    ),
    EndpointPreset(
        "https://api.openai.com/v1/audio/speech",
        "OpenAI 官方",
        "https://platform.openai.com/api-keys",
        "去 OpenAI 创建 Key",
    ),
    EndpointPreset(
        "https://open.bigmodel.cn/api/paas/v4/audio/speech",
        "智谱 BigModel",
        "https://bigmodel.cn/usercenter/proj-mgmt/apikeys",
        "去智谱创建 Key",
    ),
    EndpointPreset(
        "https://api.minimaxi.com/v1/audio/speech",
        "MiniMax",
        "https://platform.minimaxi.com/user-center/basic-information/interface-key",
        "去 MiniMax 创建 Key",
    ),
    EndpointPreset(
        "https://api.moonshot.cn/v1/audio/speech",
        "月之暗面 Kimi",
        "https://platform.moonshot.cn/console/api-keys",
        "去 Kimi 创建 Key",
    ),
]


def find_endpoint(url: str) -> EndpointPreset | None:
    """按端点查预设：先全等，再同域名兜底（用户手改路径仍认回平台）。

    同域名兜底的意义：自部署兼容服务的地址通常与官方同域不同路径的场景少，
    但用户手滑多写/少写 `/v1` 时仍能给出正确的 Key 链接；域名不同则不猜。
    """
    target = (url or "").strip().rstrip("/")
    if not target:
        return None
    for preset in ENDPOINT_PRESETS:
        if preset.url.rstrip("/") == target:
            return preset
    try:
        host = urlsplit(target).netloc.lower()
    except ValueError:
        return None
    if not host:
        return None
    for preset in ENDPOINT_PRESETS:
        if urlsplit(preset.url).netloc.lower() == host:
            return preset
    return None


class VoicePreset(NamedTuple):
    """一个音色选项：value 为 API 的 voice 参数值，label 为人话描述。"""

    value: str
    label: str


class ModelPreset(NamedTuple):
    """一个模型选项：含模型名、人话描述、以及该模型可用的音色包。

    voices 为空表示该模型不提供预置音色（用户自行手填 voice 值）。
    """

    model: str
    label: str
    voices: List[VoicePreset]

    def voice_value(self, name: str) -> str:
        """音色短名 → API voice 值（`<model>:<name>`）。"""
        return f"{self.model}:{name}"


# 预置音色名 → 人话（两模型共用同一套命名）
_VOICE_LABELS: Dict[str, str] = {
    "alex": "沉稳男声 alex",
    "benjamin": "低沉男声 benjamin",
    "charles": "磁性男声 charles",
    "david": "欢快男声 david",
    "anna": "沉稳女声 anna",
    "bella": "激情女声 bella",
    "claire": "温柔女声 claire",
    "diana": "欢快女声 diana",
}

# 8 个预置音色的短名顺序（男声在前，与官方文档一致）
_VOICE_NAMES: List[str] = [
    "alex",
    "benjamin",
    "charles",
    "david",
    "anna",
    "bella",
    "claire",
    "diana",
]


def _voice_pack() -> List[VoicePreset]:
    """构造 8 音色包（label 与 value 分离，value 只存短名）。"""
    return [VoicePreset(name, _VOICE_LABELS[name]) for name in _VOICE_NAMES]


# ── 模型预设 ──
MODEL_PRESETS: List[ModelPreset] = [
    ModelPreset(
        "FunAudioLLM/CosyVoice2-0.5B",
        "CosyVoice2-0.5B（中英日韩 + 方言）",
        _voice_pack(),
    ),
    ModelPreset(
        "fishaudio/fish-speech-1.5",
        "Fish-Speech 1.5（多语言，可克隆）",
        _voice_pack(),
    ),
    ModelPreset(
        "fnlp/MOSS-TTSD-v0.5",
        "MOSS-TTSD-v0.5（对话合成，需手填音色）",
        [],
    ),
]

# 默认端点（与历史 default 一致，老用户配置不受影响）
DEFAULT_API_URL = "https://api.siliconflow.cn/v1/audio/speech"
# 默认模型（与历史 default 一致，老用户配置不受影响）
DEFAULT_MODEL = "FunAudioLLM/CosyVoice2-0.5B"
DEFAULT_VOICE_NAME = "alex"


def find_model(model: str) -> ModelPreset | None:
    """按模型名查预设；未收录返回 None（用户在用手填值）。"""
    for preset in MODEL_PRESETS:
        if preset.model == model:
            return preset
    return None


def split_voice(voice: str) -> tuple:
    """把 voice 值拆成 (model, voice_name)。

    兼容三种输入：
    - "FunAudioLLM/CosyVoice2-0.5B:alex" → (model, "alex")
    - "alex"                              → ("", "alex")
    - ""                                  → ("", "")
    无冒号时 model 为空串，由调用方补当前所选模型。
    """
    if not voice:
        return "", ""
    if ":" in voice:
        model, name = voice.split(":", 1)
        return model.strip(), name.strip()
    return "", voice.strip()


def default_voice_value(model: str = DEFAULT_MODEL) -> str:
    """给定模型的默认 voice 值。"""
    return f"{model}:{DEFAULT_VOICE_NAME}"
