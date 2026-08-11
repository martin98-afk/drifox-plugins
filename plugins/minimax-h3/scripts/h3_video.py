#!/usr/bin/env python3
"""
h3_video.py — MiniMax H3 全模态音视频生成

功能:
    create    提交视频生成任务（文生视频/首帧/尾帧/首尾帧/多模态参考），返回 task_id
    query     查询任务状态与结果
    download  查询到成功后把视频下载到本地

用法:
    python h3_video.py create --prompt "一只猫在沙滩上奔跑" --resolution 768P --duration 8 --ratio 16:9
    python h3_video.py create --prompt "..." --first-frame first.png --last-frame last.png
    python h3_video.py create --prompt "..." --ref-image a.jpg --ref-video b.mp4 --ref-audio c.mp3
    python h3_video.py create --prompt "..." --wait --output out.mp4 --timeout 900
    python h3_video.py query <task_id>
    python h3_video.py download <task_id> --output out.mp4

输入模式（自动推导）:
    仅 text                          → t2va 文生视频
    text + 1 图（--first-frame）      → i2va 首帧生视频
    text + 1 图（--last-frame）       → 尾帧生视频
    text + 2 图（首+尾）              → fl2va 首尾帧生视频
    text + --ref-*                    → ref2va 多模态参考生视频

约束:
    - 请求体总大小 ≤ 64MB（本地文件自动 Base64，大文件请用公网 URL）
    - duration 整数 4~15
    - 图生视频（first/last frame）与多模态参考（ref-*）互斥
    - 参考图 ≤9、参考视频 ≤3、参考音频 ≤3

API Key 来源（优先级）:
    1. 环境变量 MINIMAX_API_KEY
    2. ~/.minimax/api_key 文件
    3. --api-key 参数

依赖:
    pip install requests
"""
import argparse
import base64
import mimetypes
import os
import sys
import time

import requests

API_BASE = "https://api.minimaxi.com"  # 海外: https://api.minimax.io
CREATE_URL = "/v2/video_generation"
QUERY_URL = "/v2/query/video_generation/{task_id}"
POLL_INTERVAL = 5  # 秒
DEFAULT_TIMEOUT = 600  # 秒


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


def _to_data_url(path: str) -> str:
    """本地文件 → Data URL（Base64）。返回 None 表示文件不存在。"""
    if not os.path.exists(path):
        print(f"❌ 文件不存在: {path}")
        sys.exit(1)
    mime, _ = mimetypes.guess_type(path)
    mime = mime or "application/octet-stream"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _media_url(value: str) -> str:
    """媒体输入统一转 URL：本地路径 → Data URL；http(s) 直传。"""
    if value.startswith(("http://", "https://", "data:")):
        return value
    return _to_data_url(value)


def _check_base_resp(data: dict) -> None:
    """检查 base_resp 状态码，非 0 抛异常（兼容 v1 风格响应）。"""
    base = data.get("base_resp", {})
    if base.get("status_code") != 0:
        raise RuntimeError(f"API 错误 {base.get('status_code')}: {base.get('status_msg')}")


def build_content(args) -> list:
    """根据参数推导输入模式，构造 content 数组。"""
    # 互斥校验：图生视频（首/尾帧）与多模态参考不能混用
    has_frames = bool(args.first_frame or args.last_frame)
    has_refs = bool(args.ref_image or args.ref_video or args.ref_audio)
    if has_frames and has_refs:
        print("❌ 图生视频（--first-frame/--last-frame）与多模态参考（--ref-*）互斥，不能同时使用")
        sys.exit(1)

    frames = []
    if args.first_frame:
        frames.append({"type": "image_url", "image_url": {"url": _media_url(args.first_frame)}, "role": "first_frame"})
    if args.last_frame:
        frames.append({"type": "image_url", "image_url": {"url": _media_url(args.last_frame)}, "role": "last_frame"})

    refs = []
    for img in args.ref_image or []:
        refs.append({"type": "image_url", "image_url": {"url": _media_url(img)}, "role": "reference_image"})
    for vid in args.ref_video or []:
        refs.append({"type": "video_url", "video_url": {"url": _media_url(vid)}, "role": "reference_video"})
    for aud in args.ref_audio or []:
        refs.append({"type": "audio_url", "audio_url": {"url": _media_url(aud)}, "role": "reference_audio"})

    content: list = [{"type": "text", "text": args.prompt}]
    content.extend(frames)
    content.extend(refs)
    return content


def create_task(args, api_key: str) -> str:
    """提交生成任务，返回 task_id。"""
    content = build_content(args)
    # 多模态参考：按 API 约束校验数量
    ref_images = [c for c in content if c.get("role") == "reference_image"]
    ref_videos = [c for c in content if c.get("role") == "reference_video"]
    ref_audios = [c for c in content if c.get("role") == "reference_audio"]
    if len(ref_images) > 9:
        print(f"❌ 参考图片最多 9 张，当前 {len(ref_images)} 张")
        sys.exit(1)
    if len(ref_videos) > 3:
        print(f"❌ 参考视频最多 3 段，当前 {len(ref_videos)} 段")
        sys.exit(1)
    if len(ref_audios) > 3:
        print(f"❌ 参考音频最多 3 段，当前 {len(ref_audios)} 段")
        sys.exit(1)

    payload: dict = {
        "model": "MiniMax-H3",
        "content": content,
        "resolution": args.resolution,
        "duration": args.duration,
    }
    if args.ratio:
        payload["ratio"] = args.ratio
    if args.watermark:
        payload["aigc_watermark"] = True

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = requests.post(args.api_base + CREATE_URL, headers=headers, json=payload, timeout=120)
    if resp.status_code != 200:
        print(f"❌ 创建任务失败 HTTP {resp.status_code}: {resp.text[:500]}")
        sys.exit(1)
    data = resp.json()
    task_id = data.get("task_id")
    if not task_id:
        print(f"❌ 响应中无 task_id: {data}")
        sys.exit(1)
    print(f"✅ 任务已提交 task_id={task_id}")
    print(f"   模式: {'多模态参考' if refs_mode(content) else '图文'} | 分辨率: {args.resolution} | 时长: {args.duration}s"
          + (f" | 比例: {args.ratio}" if args.ratio else ""))
    return task_id


def refs_mode(content: list) -> bool:
    """判断是否为多模态参考模式。"""
    return any(c.get("role", "").startswith("reference_") for c in content)


def query_task(task_id: str, api_key: str, api_base: str) -> dict:
    """查询任务状态，返回 task 对象。"""
    headers = {"Authorization": f"Bearer {api_key}"}
    url = api_base + QUERY_URL.format(task_id=task_id)
    resp = requests.get(url, headers=headers, timeout=60)
    if resp.status_code != 200:
        print(f"❌ 查询失败 HTTP {resp.status_code}: {resp.text[:500]}")
        sys.exit(1)
    data = resp.json()
    _check_base_resp(data)
    task = data.get("task")
    if not task:
        print(f"❌ 响应中无 task: {data}")
        sys.exit(1)
    return task


def print_task(task: dict) -> None:
    """打印任务信息。"""
    status = task.get("status", "?")
    print(f"状态: {status}")
    print(f"模型: {task.get('model', '?')} | 分辨率: {task.get('resolution', '?')} | 时长: {task.get('duration', '?')}s | 比例: {task.get('ratio', '?')}")
    if status == "succeeded":
        content = task.get("content", {})
        url = content.get("url", "")
        if url:
            print(f"视频: {url}")
    elif status == "failed":
        content = task.get("content", {})
        print(f"失败原因: {content.get('error', '未知错误')}")


def wait_and_download(task_id: str, api_key: str, api_base: str, output: str, timeout: int) -> None:
    """轮询直到成功/失败/超时；成功且有 output 则下载。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = query_task(task_id, api_key, api_base)
        status = task.get("status")
        print(f"[{time.strftime('%H:%M:%S')}] 状态: {status}")
        if status == "succeeded":
            url = task.get("content", {}).get("url", "")
            if not url:
                print("❌ 任务成功但无视频 URL")
                sys.exit(1)
            if output:
                download_url(url, output)
            else:
                print(f"视频: {url}")
            return
        if status in ("failed", "cancelled"):
            print(f"❌ 任务{status}: {task.get('content', {}).get('error', '未知')}")
            sys.exit(1)
        time.sleep(POLL_INTERVAL)
    print(f"❌ 轮询超时（{timeout}s），任务仍在进行。可用 query 继续查询: {task_id}")
    sys.exit(1)


def download_url(url: str, output: str) -> None:
    """下载视频到本地文件。"""
    print(f"⏳ 下载中: {url}")
    resp = requests.get(url, timeout=300)
    resp.raise_for_status()
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    with open(output, "wb") as f:
        f.write(resp.content)
    print(f"✅ 已保存 {output} ({len(resp.content)/1024/1024:.1f} MB)")


def main() -> None:
    parser = argparse.ArgumentParser(description="MiniMax H3 全模态音视频生成工具")
    parser.add_argument("--api-base", default=API_BASE, help=f"API 基础地址（默认 {API_BASE}，海外用 https://api.minimax.io）")
    parser.add_argument("--api-key", default=None, help="API Key（默认读环境变量 MINIMAX_API_KEY 或 ~/.minimax/api_key）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # create
    p_create = sub.add_parser("create", help="提交视频生成任务")
    p_create.add_argument("--prompt", required=True, help="提示词（必填，建议先用 h3-prompt-writing 技能重写）")
    p_create.add_argument("--first-frame", default=None, help="首帧图（本地路径或 URL）")
    p_create.add_argument("--last-frame", default=None, help="尾帧图（本地路径或 URL）")
    p_create.add_argument("--ref-image", action="append", default=[], help="参考图片（可多次，≤9 张）")
    p_create.add_argument("--ref-video", action="append", default=[], help="参考视频（可多次，≤3 段）")
    p_create.add_argument("--ref-audio", action="append", default=[], help="参考音频（可多次，≤3 段）")
    p_create.add_argument("--resolution", choices=["768P", "2K"], default="768P", help="分辨率（默认 768P）")
    p_create.add_argument("--duration", type=int, default=8, help="时长 4-15 秒（默认 8）")
    p_create.add_argument("--ratio", default=None, help="宽高比：21:9/16:9/4:3/1:1/3:4/9:16（文生视频必填；图生视频恒 adaptive）")
    p_create.add_argument("--watermark", action="store_true", help="添加 AIGC 水印")
    p_create.add_argument("--wait", action="store_true", help="提交后阻塞轮询直到完成")
    p_create.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"轮询超时秒数（默认 {DEFAULT_TIMEOUT}）")
    p_create.add_argument("--output", "-o", default=None, help="配合 --wait：完成后保存到该文件")

    # query
    p_query = sub.add_parser("query", help="查询任务状态")
    p_query.add_argument("task_id", help="任务 ID")

    # download
    p_dl = sub.add_parser("download", help="下载任务视频")
    p_dl.add_argument("task_id", help="任务 ID")
    p_dl.add_argument("--output", "-o", default="output.mp4", help="输出文件（默认 output.mp4）")

    args = parser.parse_args()
    api_key = get_api_key(getattr(args, "api_key", None))

    if args.cmd == "create":
        # 文生视频必须指定 ratio（非 adaptive）
        if not args.first_frame and not args.last_frame and not args.ref_image and not args.ref_video and not args.ref_audio:
            if not args.ratio:
                print("❌ 文生视频必须指定 --ratio（如 --ratio 16:9）")
                sys.exit(1)
        if not 4 <= args.duration <= 15:
            print("❌ --duration 必须在 4~15 之间")
            sys.exit(1)
        task_id = create_task(args, api_key)
        if args.wait:
            wait_and_download(task_id, api_key, args.api_base, args.output, args.timeout)
    elif args.cmd == "query":
        print_task(query_task(args.task_id, api_key, args.api_base))
    elif args.cmd == "download":
        task = query_task(args.task_id, api_key, args.api_base)
        if task.get("status") != "succeeded":
            print(f"任务状态: {task.get('status')}，尚未成功，无法下载")
            sys.exit(1)
        url = task.get("content", {}).get("url", "")
        if not url:
            print("❌ 任务无视频 URL")
            sys.exit(1)
        download_url(url, args.output)


if __name__ == "__main__":
    main()
