# -*- coding: utf-8 -*-
"""voice-reply 无声诊断（一次性，用完删除）。

在 DriFox 里打开 Python 终端 / 或用项目 uv 环境直接跑：
    uv run python tools/diag_voice_reply.py

会做 4 件事，把结果打印出来贴回给我：
1. 读插件配置，确认 engine/api_url/api_model/api_voice/api_key 实际值（Key 只显示前 8 位）
2. 用真实配置打一次 TTS API，打印 HTTP 状态 + 返回字节数 + wav 头摘要
3. 把音频写到 %TEMP%/voice_reply_diag.wav，用 winsound 与 winmm mci 各播一次并打印结果
4. 用系统默认播放器再播一遍（能响 = 音频数据没问题，是我们播放后端的问题）

⚠️ 需要本机已配置好 API Key（设置 → 语音播报配置 → 在线引擎）。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PLUGIN_NAME = "voice-reply"
TEST_TEXT = "语音播报诊断测试，这是一段用于验证音频播放的中文文本。"


def read_config() -> dict:
    try:
        from app.plugins.managers.plugin_config_store import PluginConfigStore

        s = PluginConfigStore()
        keys = ["engine", "api_url", "api_model", "api_voice", "api_key"]
        return {k: s.get(PLUGIN_NAME, k) for k in keys}
    except Exception as e:  # noqa: BLE001
        print(f"[配置] 读取失败: {type(e).__name__}: {e}")
        return {}


def call_tts(cfg) -> bytes | None:
    import urllib.request
    from urllib.error import HTTPError

    body = json.dumps(
        {
            "model": cfg.get("api_model"),
            "input": TEST_TEXT,
            "voice": cfg.get("api_voice"),
            "response_format": "wav",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        cfg.get("api_url"),
        data=body,
        headers={
            "Authorization": f'Bearer {cfg.get("api_key") or ""}',
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=50) as r:
            print(f"[API] HTTP {r.status} Content-Type={r.headers.get('Content-Type')}")
            return r.read()
    except HTTPError as e:
        print(f"[API] HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:400]}")
    except Exception as e:  # noqa: BLE001
        print(f"[API] 请求失败: {type(e).__name__}: {e}")
    return None


def main() -> int:
    cfg = read_config()
    print("=== 1. 插件配置 ===")
    for k, v in cfg.items():
        if k == "api_key" and v:
            print(f"  {k} = {str(v)[:8]}...(长度 {len(str(v))})")
        else:
            print(f"  {k} = {v}")

    data = call_tts(cfg)
    print("\n=== 2. API 返回 ===")
    if not data:
        print("  无音频数据，诊断中止")
        return 1
    print(f"  {len(data)} 字节，前 4 字节 = {data[:4]!r}")

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "voice-reply" / "ui"))
    try:
        from audio_player import describe_wav  # type: ignore

        print(f"  wav 摘要: {describe_wav(data)}")
    except Exception as e:  # noqa: BLE001
        print(f"  wav 摘要不可用: {e}")

    path = os.path.join(tempfile.gettempdir(), "voice_reply_diag.wav")
    with open(path, "wb") as f:
        f.write(data)
    print(f"\n=== 3. 播放测试（音频已存 {path}）===")

    import time

    t0 = time.time()
    try:
        import winsound

        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_SYNC)
        print(f"  winsound: 调用返回 dt={time.time() - t0:.2f}s（失败也不报错，仅供参考）")
    except Exception as e:  # noqa: BLE001
        print(f"  winsound: ERR {type(e).__name__}: {e}")

    try:
        from audio_player import play_wav  # type: ignore

        t0 = time.time()
        play_wav(path, {})
        print(f"  winmm mci: 成功 dt={time.time() - t0:.2f}s")
    except Exception as e:  # noqa: BLE001
        print(f"  winmm mci: 失败 {type(e).__name__}: {e}")

    print("\n=== 4. 系统播放器对照 ===")
    print("  正在用系统默认播放器播放同一文件…（能听到 = 音频数据没问题）")
    try:
        os.startfile(path)  # 诊断脚本：用系统默认程序打开验证音频
    except Exception as e:  # noqa: BLE001
        print(f"  打开失败: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
