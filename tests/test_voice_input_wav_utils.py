# -*- coding: utf-8 -*-
"""wav_utils 离线单测：WAV 头解析 / 时长 / 电平统计。

重点覆盖两种真实生产者：
- Windows winmm：标准 44 字节头，data 紧跟 fmt
- macOS AVAudioRecorder：fmt 前插 JUNK + FLLR 填充块，data 偏移实测 4096 字节

不联网、不依赖 PyQt5：wav_utils 只 import os，loguru 在函数内延迟导入。
"""

import importlib.util
import os
import struct
from pathlib import Path

import pytest

_PLUGIN_UI = os.environ.get(
    "DRIFOX_TEST_PLUGIN_UI",
    str(Path(__file__).resolve().parent.parent / "plugins" / "voice-input" / "ui"),
)


@pytest.fixture(scope="module")
def wu():
    spec = importlib.util.spec_from_file_location(
        "voice_input_wav_utils", Path(_PLUGIN_UI) / "wav_utils.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _chunk(chunk_id: bytes, body: bytes) -> bytes:
    """构造一个 RIFF 子块（含奇数长度填充字节）。"""
    pad = b"\x00" if len(body) % 2 else b""
    return chunk_id + struct.pack("<I", len(body)) + body + pad


def _fmt_chunk(rate: int = 16000, channels: int = 1, bits: int = 16) -> bytes:
    byte_rate = rate * channels * bits // 8
    return _chunk(
        b"fmt ",
        struct.pack(
            "<HHIIHH", 1, channels, rate, byte_rate, channels * bits // 8, bits
        ),
    )


def _wav(
    *,
    cover: bytes = b"",
    frames: bytes = b"\x00" * 32,
    rate: int = 16000,
    channels: int = 1,
    bits: int = 16,
    data_declared: int | None = None,
) -> bytes:
    """组装完整 WAV 字节流；cover 为 fmt 前的填充块（模拟 AVAudioRecorder）。"""
    body = cover + _fmt_chunk(rate, channels, bits)
    size = len(frames) if data_declared is None else data_declared
    body += b"data" + struct.pack("<I", size) + frames
    return b"RIFF" + struct.pack("<I", len(body) + 4) + b"WAVE" + body


def _write(tmp_path: Path, name: str, blob: bytes) -> str:
    p = tmp_path / name
    p.write_bytes(blob)
    return str(p)


def test_parse_standard_winmm_layout(wu):
    """winmm 风格：data 紧跟 fmt，偏移 44。"""
    rate, ch, bits, off = wu.parse_wav_header(_wav())
    assert (rate, ch, bits) == (16000, 1, 16)
    assert off == 44


def test_parse_avfoundation_padding_blocks(wu):
    """AVAudioRecorder 风格：JUNK(28) + FLLR(4008) 前置，data 偏移 4096。"""
    cover = _chunk(b"JUNK", b"\x00" * 28) + _chunk(b"FLLR", b"\x00" * 4008)
    blob = _wav(cover=cover)
    # 前置块共 8+28 + 8+4008 = 4052 字节，加 RIFF 头 12 → fmt 在 4064
    assert blob[4064:4068] == b"fmt "
    rate, ch, bits, off = wu.parse_wav_header(blob)
    assert (rate, ch, bits) == (16000, 1, 16)
    assert off == 4096


def test_parse_rejects_bad_magic(wu):
    assert wu.parse_wav_header(b"XXXX" + b"\x00" * 60) == (0, 0, 0, 0)
    assert wu.parse_wav_header(b"RIFF") == (0, 0, 0, 0)
    assert wu.parse_wav_header(b"") == (0, 0, 0, 0)


def test_parse_truncated_header_does_not_hang(wu):
    """块声明长度越界时截断到实际，不越界读、不死循环。"""
    blob = b"RIFF" + struct.pack("<I", 1000) + b"WAVE" + b"fLLR" + struct.pack("<I", 4096)
    assert wu.parse_wav_header(blob) == (0, 0, 0, 0)


def test_duration_uses_actual_file_size(wu, tmp_path):
    """时长按文件实际大小算（不看 data 声明值），且能跨前置填充块。"""
    cover = _chunk(b"JUNK", b"\x00" * 28) + _chunk(b"FLLR", b"\x00" * 4008)
    frames = b"\x00" * 32000  # 16000Hz * 2B * 1ch = 1 秒
    p = _write(tmp_path, "af.wav", _wav(cover=cover, frames=frames))
    assert wu.wav_duration(p) == pytest.approx(1.0, abs=0.01)


def test_duration_invalid_returns_minus_one(wu, tmp_path):
    assert wu.wav_duration(str(tmp_path / "missing.wav")) == -1.0
    p = _write(tmp_path, "bad.wav", b"not a wav at all" + b"\x00" * 60)
    assert wu.wav_duration(p) == -1.0


def test_level_silence(wu, tmp_path):
    """全零采样 → rms=peak=0（macOS 未授权时的典型表现）。"""
    p = _write(tmp_path, "silence.wav", _wav(frames=b"\x00" * 4000))
    rms, peak = wu.wav_level(p)
    assert rms == 0.0
    assert peak == 0.0


def test_level_detects_signal(wu, tmp_path):
    """有信号时 peak 反映最大振幅。"""
    samples = struct.pack("<h", 16384) * 100 + struct.pack("<h", -8192) * 100
    p = _write(tmp_path, "signal.wav", _wav(frames=samples))
    rms, peak = wu.wav_level(p)
    assert peak == pytest.approx(16384 / 32768.0, abs=0.001)
    assert 0.0 < rms < peak


def test_level_across_padding_blocks(wu, tmp_path):
    """前置填充块不影响电平统计（data 偏移须正确解析）。"""
    cover = _chunk(b"JUNK", b"\x00" * 28) + _chunk(b"FLLR", b"\x00" * 4008)
    samples = struct.pack("<h", 32767) * 50
    p = _write(tmp_path, "af_signal.wav", _wav(cover=cover, frames=samples))
    rms, peak = wu.wav_level(p)
    assert peak == pytest.approx(32767 / 32768.0, abs=0.001)


def test_level_non_16bit_returns_minus_one(wu, tmp_path):
    p = _write(tmp_path, "float.wav", _wav(bits=32))
    assert wu.wav_level(p) == (-1.0, -1.0)
