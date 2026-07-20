#!/usr/bin/env python3
"""
generate_tts.py — 为 guizang-ppt-skill 演讲稿逐页生成 MiniMax TTS 语音 MP3

用法:
    set MINIMAX_API_KEY=your_key_here
    python generate_tts.py --input 演讲稿.md --output-dir audio
    python generate_tts.py --input 演讲稿.md --output-dir audio --voice female-shaonv
    python generate_tts.py --input 演讲稿.md --output-dir audio --dry-run
    python generate_tts.py --input 演讲稿.md --output-dir audio --page P05

依赖:
    pip install requests

API Key 来源（优先级）:
    1. 环境变量 MINIMAX_API_KEY
    2. ~/.minimax/api_key 文件
"""

import os, sys, re, time, json, argparse
import requests

# ── 默认配置 ──────────────────────────────────────────────────────
API_URL = "https://api.minimax.chat/v1/t2a_v2"    # MiniMax TTS 中文端点
MODEL = "speech-2.6-hd"                             # TTS 模型
VOICE_ID = "male-qn-qingse"                         # 默认音色（男声清晰）
SPEED = 1.0                                          # 语速 0.5~2.0
VOL = 1.0                                            # 音量 0~10
PITCH = 0                                            # 音调 -12~12
SAMPLE_RATE = 32000
BITRATE = 128000
AUDIO_FORMAT = "mp3"
CHANNEL = 1


def get_api_key() -> str:
    """从环境变量获取 API Key，绝不硬编码"""
    key = os.environ.get("MINIMAX_API_KEY")
    if not key:
        for p in [
            os.path.expanduser("~/.minimax/api_key"),
            os.path.expanduser("~/.minimax/api_key.txt"),
            os.path.expanduser("~/.config/minimax/api_key"),
        ]:
            if os.path.exists(p):
                with open(p, "r") as f:
                    key = f.read().strip()
                break
    if not key:
        print("❌ 未找到 MiniMax API Key！")
        print("   请设置环境变量: set MINIMAX_API_KEY=your_key_here")
        print("   或创建配置文件: echo your_key > %USERPROFILE%\\.minimax\\api_key")
        sys.exit(1)
    return key


def extract_slide_texts(md_path: str) -> list[dict]:
    """解析演讲稿.md，返回每页 {page, title, text} 列表"""
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = re.split(r'\n(?=## P\d+)', content)
    slides = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        page_match = re.match(r'## (P\d+)', block)
        if not page_match:
            continue
        page = page_match.group(1)
        title_line = block.split('\n')[0]
        title = re.sub(r'^## P\d+\s*[·\-]\s*', '', title_line).strip()

        speech_match = re.search(r'\*\*演讲词\*\*.*?(?=\n## |\Z)', block, re.DOTALL)
        if not speech_match:
            slides.append({"page": page, "title": title, "text": ""})
            continue

        raw = speech_match.group(0)
        raw = re.sub(r'\*\*演讲词\*\*.*?\n', '', raw, count=1)
        lines = [re.sub(r'^>\s?', '', l).strip() for l in raw.split('\n') if re.sub(r'^>\s?', '', l).strip()]
        text = re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()
        slides.append({"page": page, "title": title, "text": text})

    return slides


def text_to_speech(text: str, output_path: str, api_key: str, voice_id: str) -> bool:
    """调用 MiniMax TTS API 生成语音文件"""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "text": text,
        "voice_setting": {"voice_id": voice_id, "speed": SPEED, "vol": VOL, "pitch": PITCH},
        "audio_setting": {"sample_rate": SAMPLE_RATE, "bitrate": BITRATE, "format": AUDIO_FORMAT, "channel": CHANNEL},
        "output_format": "url",
        "language_boost": "auto",
    }
    try:
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=60)
        data = resp.json()
        if data.get("base_resp", {}).get("status_code") != 0:
            print(f"     ❌ API 错误: {data['base_resp']['status_msg']}")
            return False
        audio_url = data.get("data", {}).get("audio", "")
        if not audio_url:
            print(f"     ❌ 无音频 URL")
            return False
        audio_resp = requests.get(audio_url, timeout=60)
        if audio_resp.status_code != 200:
            print(f"     ❌ 下载失败: HTTP {audio_resp.status_code}")
            return False
        with open(output_path, "wb") as f:
            f.write(audio_resp.content)
        extra = data.get("extra_info", {})
        duration = extra.get("audio_length", 0) / 1000
        print(f"     ✅ {duration:.1f}s | {extra.get('usage_characters', 0)} 字 | {len(audio_resp.content)/1024:.0f} KB")
        return True
    except requests.exceptions.Timeout:
        print(f"     ❌ 请求超时")
        return False
    except Exception as e:
        print(f"     ❌ 异常: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="为演讲稿生成 MiniMax TTS 语音 MP3")
    parser.add_argument("--input", "-i", default="演讲稿.md", help="演讲稿.md 路径")
    parser.add_argument("--output-dir", "-o", default="audio", help="输出目录")
    parser.add_argument("--voice", default=VOICE_ID, help=f"音色 ID (默认: {VOICE_ID})")
    parser.add_argument("--dry-run", action="store_true", help="只打印文本，不调 API")
    parser.add_argument("--page", help="只生成指定页，如 P01")
    args = parser.parse_args()

    api_key = get_api_key()
    os.makedirs(args.output_dir, exist_ok=True)
    slides = extract_slide_texts(args.input)
    print(f"📖 共提取 {len(slides)} 页演讲稿\n")

    if args.page:
        slides = [s for s in slides if s["page"] == args.page]
        if not slides: print(f"❌ 未找到 {args.page}"); return

    total_chars = sum(len(s["text"]) for s in slides)
    print(f"📝 总字数: {total_chars}")
    print(f"🎤 音色: {args.voice}")
    print()

    success = fail = 0
    for i, slide in enumerate(slides):
        page, title, text = slide["page"], slide["title"], slide["text"]
        if not text:
            print(f"  [{i+1:2d}/{len(slides)}] {page} · {title}  — ⏭️ 无演讲词")
            continue
        print(f"[{i+1:2d}/{len(slides)}] {page} · {title}")
        print(f"     文本: {text[:80].replace(chr(10),' ')}...")

        if args.dry_run:
            print(f"     字数: {len(text)}\n"); continue

        output_file = os.path.join(args.output_dir, f"{page.lower()}.mp3")
        if os.path.exists(output_file) and os.path.getsize(output_file) > 1000:
            print(f"     已存在, 跳过\n"); success += 1; continue

        print(f"     生成中...", end=" "); sys.stdout.flush()
        if text_to_speech(text, output_file, api_key, args.voice):
            success += 1
        else:
            fail += 1
        time.sleep(0.5)
        print()

    print("=" * 50)
    print(f"📊 完成: {success} 成功 / {fail} 失败 / {len(slides)} 总计")


if __name__ == "__main__":
    main()
