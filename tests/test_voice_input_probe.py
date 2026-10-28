# -*- coding: utf-8 -*-
"""voice-input 云端识别连通性探测的单测（不发真实网络请求）。

覆盖 probe_asr 的判定口径：
- HTTP 200 + 识别文本为空 → 判可用（测试音频是音调，无文本属正常）
- JSON 里带错误字段（MiniMax base_resp / OpenAI 风格 error）→ 判失败
- 401/403 → 人话提示「API Key 无效」
- Key 为空 → ValueError
"""

import importlib.util
import io
from pathlib import Path
from urllib.error import HTTPError

import pytest

_PLUGIN_UI = Path(__file__).resolve().parent.parent / "plugins" / "voice-input" / "ui"


@pytest.fixture(scope="module")
def cr():
    spec = importlib.util.spec_from_file_location(
        "voice_input_cloud_recognizer", _PLUGIN_UI / "cloud_recognizer.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def wav(tmp_path):
    path = tmp_path / "probe.wav"
    path.write_bytes(b"RIFF" + b"\x00" * 60)
    return str(path)


class _FakeResp:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_ok_even_when_text_empty(cr, wav, monkeypatch):
    monkeypatch.setattr(cr, "urlopen", lambda *a, **k: _FakeResp(b'{"text": ""}'))
    assert "可用" in cr.probe_asr("https://x/y", "m", "sk-1", wav)


def test_minimax_error_field(cr, wav, monkeypatch):
    body = b'{"base_resp": {"status_code": 1004, "status_msg": "invalid api key"}}'
    monkeypatch.setattr(cr, "urlopen", lambda *a, **k: _FakeResp(body))
    with pytest.raises(RuntimeError) as exc:
        cr.probe_asr("https://x/y", "m", "sk-1", wav)
    assert "invalid api key" in str(exc.value)


def test_openai_style_error_field(cr, wav, monkeypatch):
    body = b'{"error": {"message": "model not found"}}'
    monkeypatch.setattr(cr, "urlopen", lambda *a, **k: _FakeResp(body))
    with pytest.raises(RuntimeError) as exc:
        cr.probe_asr("https://x/y", "m", "sk-1", wav)
    assert "model not found" in str(exc.value)


def test_unauthorized(cr, wav, monkeypatch):
    def boom(*_a, **_k):
        raise HTTPError("https://x/y", 401, "Unauthorized", None, io.BytesIO(b"{}"))

    monkeypatch.setattr(cr, "urlopen", boom)
    with pytest.raises(RuntimeError) as exc:
        cr.probe_asr("https://x/y", "m", "sk-1", wav)
    assert "API Key 无效" in str(exc.value)


def test_empty_key(cr, wav):
    with pytest.raises(ValueError):
        cr.probe_asr("https://x/y", "m", "   ", wav)


def test_probe_wav_is_playable(cr):
    path = cr.make_probe_wav()
    try:
        raw = Path(path).read_bytes()
        assert raw[:4] == b"RIFF"
        assert len(raw) > 1000  # 1 秒 16k/16bit ≈ 32KB
    finally:
        Path(path).unlink(missing_ok=True)
