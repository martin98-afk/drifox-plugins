# -*- coding: utf-8 -*-
"""voice-input Whisper 后端离线单测（不联网、不下载模型）。

覆盖：模型档位解析 / 体积提示 / 缓存目录 / 模型存在性探测 / 可用性探测。
whisper_recognizer 模块顶层依赖 PyQt5 + loguru，宿主测试环境缺依赖时整体跳过
（逻辑在真实 DriFox 环境由宿主 Python 验证）。
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

_PLUGIN_UI = os.environ.get(
    "DRIFOX_TEST_PLUGIN_UI",
    str(Path(__file__).resolve().parent.parent / "plugins" / "voice-input" / "ui"),
)

if _PLUGIN_UI not in sys.path:
    sys.path.insert(0, _PLUGIN_UI)


@pytest.fixture(scope="module")
def wr():
    try:
        import whisper_recognizer as wr  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001 — 宿主缺 PyQt5/loguru 等则跳过
        pytest.skip(f"whisper_recognizer 导入失败（宿主环境缺依赖？）: {e}")
    return wr


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ("", "small"),
        (None, "small"),
        ("tiny", "tiny"),
        ("MEDIUM", "medium"),
        ("big", "small"),  # 非法档位回退默认
        (" base ", "base"),  # 允许空白
    ],
)
def test_model_size_parse(wr, monkeypatch, env, expected):
    if env is None:
        monkeypatch.delenv("DRIFOX_VOICE_MODEL", raising=False)
    else:
        monkeypatch.setenv("DRIFOX_VOICE_MODEL", env)
    assert wr.model_size() == expected


def test_model_hint_mb(wr, monkeypatch):
    monkeypatch.setenv("DRIFOX_VOICE_MODEL", "tiny")
    assert wr.model_hint_mb() == 75
    monkeypatch.setenv("DRIFOX_VOICE_MODEL", "small")
    assert wr.model_hint_mb() == 460
    monkeypatch.setenv("DRIFOX_VOICE_MODEL", "nonsense")
    assert wr.model_hint_mb() == 460  # 回退默认 small


def test_model_dir_default(wr, monkeypatch):
    monkeypatch.delenv("DRIFOX_VOICE_WHISPER_DIR", raising=False)
    assert wr.model_dir() == os.path.join(
        os.path.expanduser("~"), ".cache", "drifox-voice-input"
    )


def test_model_dir_env_override(wr, monkeypatch, tmp_path):
    monkeypatch.setenv("DRIFOX_VOICE_WHISPER_DIR", str(tmp_path / "custom"))
    assert wr.model_dir() == str(tmp_path / "custom")


def test_model_present(wr, monkeypatch, tmp_path):
    monkeypatch.setenv("DRIFOX_VOICE_WHISPER_DIR", str(tmp_path / "cache"))
    # 空目录 / 不存在 → False
    assert wr.is_model_present() is False
    # 只缺权重文件 → False
    snap = (
        tmp_path
        / "cache"
        / "models--Systran--faster-whisper-tiny"
        / "snapshots"
        / "abc123"
    )
    snap.mkdir(parents=True)
    (snap / "config.json").write_text("{}", encoding="utf-8")
    assert wr.is_model_present() is False
    # 权重到位 → True
    (snap / "model.bin").write_bytes(b"fake")
    assert wr.is_model_present() is True


def test_available_probe(wr):
    # find_spec 不执行重 import；装了 faster-whisper 才为 True，否则 False，
    # 两种结果都是合法布尔 —— 这里只校验类型与幂等
    assert wr.faster_whisper_available() in (True, False)
    assert wr.faster_whisper_available() == wr.faster_whisper_available()


def test_worker_class_exists(wr):
    assert wr.WhisperRecognizeWorker is not None
    assert callable(wr.transcribe_wav)
