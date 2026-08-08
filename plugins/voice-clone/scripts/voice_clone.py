#!/usr/bin/env python3
"""
voice_clone.py — MiniMax 语音克隆与克隆音色 TTS 合成

功能:
    1. clone    上传音频样本克隆音色（生成 voice_id），可选试听
    2. tts      用克隆的 voice_id 把文本合成语音
    3. upload   只上传音频文件拿 file_id

用法:
    python voice_clone.py clone --audio sample.wav --voice-id myvoice123 --text "试听文本"
    python voice_clone.py tts --voice-id myvoice123 --text "要合成的文本" --output out.mp3
    python voice_clone.py upload --audio sample.wav

API Key 来源（优先级）:
    1. 环境变量 MINIMAX_API_KEY
    2. ~/.minimax/api_key 文件
    3. --api-key 参数

依赖:
    pip install requests
"""
import argparse
import json
import os
import sys

import requests

API_BASE = "https://api.minimaxi.com/v1"
UPLOAD_URL = f"{API_BASE}/files/upload"
CLONE_URL = f"{API_BASE}/voice_clone"
T2A_URL = f"{API_BASE}/t2a_v2"
CLONE_MODEL = "speech-2.8-hd"  # 支持语气词标签的克隆模型
TTS_MODEL = "speech-2.6-hd"    # 合成模型


def get_api_key(cli_key: str | None = None) -> str:
    """从环境变量/配置文件/CLI 参数获取 API Key，绝不硬编码。"""
    if cli_key:
        return cli_key
    key = os.environ.get("MINIMAX_API_KEY")
    if not key:
        for p in [
            os.path.expanduser("~/.minimax/api_key"),
            os.path.expanduser("~/.minimax/api_key.txt"),
            os.path.expanduser("~/.config/minimax/api_key"),
        ]:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    key = f.read().strip()
                break
    if not key:
        print("❌ 未找到 MiniMax API Key！")
        print("   设置环境变量: set MINIMAX_API_KEY=your_key_here")
        print("   或创建配置文件: echo your_key > %USERPROFILE%\\.minimax\\api_key")
        sys.exit(1)
    return key


def _check_base_resp(data: dict) -> None:
    """检查 base_resp 状态码，非 0 抛异常。"""
    base = data.get("base_resp", {})
    if base.get("status_code") != 0:
        raise RuntimeError(f"API 错误 {base.get('status_code')}: {base.get('status_msg')}")


def upload_audio(audio_path: str, api_key: str, purpose: str = "voice_clone") -> str:
    """上传音频文件，返回 file_id。"""
    if not os.path.exists(audio_path):
        print(f"❌ 文件不存在: {audio_path}")
        sys.exit(1)
    size_mb = os.path.getsize(audio_path) / 1024 / 1024
    if size_mb > 20:
        print(f"❌ 文件 {size_mb:.1f}MB 超过 20MB 上限")
        sys.exit(1)
    headers = {"Authorization": f"Bearer {api_key}"}
    with open(audio_path, "rb") as f:
        files = {"file": (os.path.basename(audio_path), f)}
        data = {"purpose": purpose}
        resp = requests.post(UPLOAD_URL, headers=headers, files=files, data=data, timeout=120)
    data = resp.json()
    _check_base_resp(data)
    file_id = data["file"]["file_id"]
    print(f"✅ 上传成功 file_id={file_id} ({data['file'].get('bytes', 0)} bytes)")
    return file_id


def clone_voice(
    file_id: int,
    voice_id: str,
    api_key: str,
    text: str = "",
    text_validation: str = "",
    accuracy: float = 0.7,
    noise_reduction: bool = False,
) -> dict:
    """克隆音色。file_id 来自 upload。返回响应（含可选试听 demo_audio）。"""
    payload: dict = {
        "file_id": int(file_id),
        "voice_id": voice_id,
    }
    if text:
        payload["text"] = text
        payload["model"] = CLONE_MODEL
    if text_validation:
        payload["text_validation"] = text_validation
        payload["accuracy"] = accuracy
    if noise_reduction:
        payload["need_noise_reduction"] = True
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = requests.post(CLONE_URL, headers=headers, json=payload, timeout=120)
    data = resp.json()
    _check_base_resp(data)
    demo = data.get("demo_audio", "")
    print(f"✅ 音色克隆成功 voice_id={voice_id}")
    if demo:
        print(f"🔊 试听: {demo}")
    return data


def tts_with_voice(voice_id: str, text: str, api_key: str, output: str, speed: float = 1.0) -> None:
    """用克隆音色合成语音到本地文件。"""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": TTS_MODEL,
        "text": text,
        "voice_setting": {"voice_id": voice_id, "speed": speed, "vol": 1.0, "pitch": 0},
        "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
        "output_format": "url",
        "language_boost": "auto",
    }
    resp = requests.post(T2A_URL, headers=headers, json=payload, timeout=120)
    data = resp.json()
    _check_base_resp(data)
    audio_url = data.get("data", {}).get("audio", "")
    if not audio_url:
        raise RuntimeError("响应中无 audio URL")
    audio = requests.get(audio_url, timeout=120)
    audio.raise_for_status()
    with open(output, "wb") as f:
        f.write(audio.content)
    extra = data.get("extra_info", {})
    duration = extra.get("audio_length", 0) / 1000
    print(f"✅ 已生成 {output} ({duration:.1f}s, {len(audio.content)/1024:.0f} KB)")


def main() -> None:
    parser = argparse.ArgumentParser(description="MiniMax 语音克隆工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # clone
    p_clone = sub.add_parser("clone", help="上传音频并克隆音色")
    p_clone.add_argument("--audio", required=True, help="音频样本路径（mp3/m4a/wav，10s~5min）")
    p_clone.add_argument("--voice-id", required=True, help="自定义 voice_id（8-256 字符，字母开头）")
    p_clone.add_argument("--text", default="", help="试听文本（可选，填了会按字符计费）")
    p_clone.add_argument("--text-validation", default="", help="音频预期文本（可选，ASR 校验）")
    p_clone.add_argument("--accuracy", type=float, default=0.7, help="ASR 相似度阈值 0-1")
    p_clone.add_argument("--noise-reduction", action="store_true", help="开启降噪")
    p_clone.add_argument("--api-key", default=None)

    # tts
    p_tts = sub.add_parser("tts", help="用克隆音色合成语音")
    p_tts.add_argument("--voice-id", required=True)
    p_tts.add_argument("--text", required=True, help="要合成的文本")
    p_tts.add_argument("--output", "-o", default="output.mp3", help="输出文件")
    p_tts.add_argument("--speed", type=float, default=1.0, help="语速 0.5-2.0")
    p_tts.add_argument("--api-key", default=None)

    # upload
    p_up = sub.add_parser("upload", help="只上传音频拿 file_id")
    p_up.add_argument("--audio", required=True)
    p_up.add_argument("--api-key", default=None)

    args = parser.parse_args()
    api_key = get_api_key(getattr(args, "api_key", None))

    if args.cmd == "clone":
        file_id = upload_audio(args.audio, api_key, purpose="voice_clone")
        clone_voice(file_id, args.voice_id, api_key,
                    text=args.text, text_validation=args.text_validation,
                    accuracy=args.accuracy, noise_reduction=args.noise_reduction)
    elif args.cmd == "tts":
        tts_with_voice(args.voice_id, args.text, api_key, args.output, args.speed)
    elif args.cmd == "upload":
        upload_audio(args.audio, api_key, purpose="voice_clone")


if __name__ == "__main__":
    main()
