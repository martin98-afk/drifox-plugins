# -*- coding: utf-8 -*-
"""voice_presets 离线单测：服务商预设完整性 + 端点归属匹配。

不依赖 PyQt5（voice_presets.py 是纯数据 + 标准库）。
覆盖设置卡「服务商 → Key 跳转链接」的判定口径：
- 每个预置服务商都必须有可点击的 http(s) 密钥页
- 端点全等 / 同域名不同路径 / 未知域名 / 空串 四种匹配结果
"""

import importlib.util
from pathlib import Path

import pytest

_PLUGIN_UI = Path(__file__).resolve().parent.parent / "plugins" / "voice-reply" / "ui"


@pytest.fixture(scope="module")
def vp():
    spec = importlib.util.spec_from_file_location(
        "voice_reply_voice_presets", _PLUGIN_UI / "voice_presets.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_preset_has_key_page(vp):
    """每个服务商都要有能打开的密钥页，否则设置卡会静默收起「获取 Key」。"""
    assert vp.ENDPOINT_PRESETS
    for preset in vp.ENDPOINT_PRESETS:
        assert preset.url.startswith("https://"), preset
        assert preset.key_url.startswith("https://"), preset
        assert preset.key_label, preset


def test_preset_labels_unique(vp):
    """服务商下拉按 label 识别人，label 重复会让用户分不清。"""
    labels = [preset.label for preset in vp.ENDPOINT_PRESETS]
    assert len(labels) == len(set(labels))


def test_find_endpoint_exact(vp):
    preset = vp.find_endpoint("https://api.siliconflow.cn/v1/audio/speech")
    assert preset is not None and "siliconflow" in preset.key_url


def test_find_endpoint_trailing_slash(vp):
    preset = vp.find_endpoint("https://api.openai.com/v1/audio/speech/")
    assert preset is not None and preset.key_url == "https://platform.openai.com/api-keys"


def test_find_endpoint_same_host_other_path(vp):
    """手改路径（多写/少写 /v1）仍认回同一平台，Key 链接不丢。"""
    preset = vp.find_endpoint("https://open.bigmodel.cn/api/paas/v4")
    assert preset is not None and "bigmodel" in preset.key_url


def test_find_endpoint_unknown_host(vp):
    """自部署端点（如 openai-edge-tts）不猜平台，链接收起。"""
    assert vp.find_endpoint("http://127.0.0.1:5050/v1/audio/speech") is None
    assert vp.find_endpoint("https://tts.example.com/v1/audio/speech") is None


def test_find_endpoint_empty(vp):
    assert vp.find_endpoint("") is None
    assert vp.find_endpoint("   ") is None
