# -*- coding: utf-8 -*-
"""
jimeng — 即梦（Dreamina）CLI 透传工具（移植自 openhanako plugins/jimeng-cli）

通过本地安装的 dreamina CLI 调用即梦的图片/视频生成能力：
- submit: 提交生成任务（text2image / image2image / text2video / image2video）
- query:  查询任务状态并下载成品

dreamina CLI 安装：curl -s https://jimeng.jianying.com/cli | bash
查找顺序：DREAMINA_CLI_PATH → PATH → ~/bin、%LOCALAPPDATA%/Programs/dreamina
"""
import json
import os
import re
import subprocess
import sys
from html import escape
from pathlib import Path

from app.tools.result import ToolResult

IMAGE_RATIOS = ["21:9", "16:9", "3:2", "4:3", "1:1", "3:4", "2:3", "9:16"]
VIDEO_RATIOS = ["1:1", "3:4", "16:9", "4:3", "9:16", "21:9"]
RESULT_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm"}
PENDING = {"querying", "pending", "running", "processing", "submitted"}
SUCCESS = {"success", "succeeded", "done", "completed"}
FAILED = {"fail", "failed", "error"}
INSTALL_CMD = "curl -s https://jimeng.jianying.com/cli | bash"


def _resolve_dreamina() -> str | None:
    """定位 dreamina 可执行文件：env 显式路径 → PATH → 常见安装目录。"""
    exe = "dreamina.exe" if sys.platform == "win32" else "dreamina"

    explicit = os.environ.get("DREAMINA_CLI_PATH", "").strip()
    if explicit:
        cand = Path(explicit)
        if cand.is_dir() and (cand / exe).exists():
            return str(cand / exe)
        if cand.exists():
            return str(cand)

    from shutil import which

    found = which(exe)
    if found:
        return found

    candidates = []
    install_dir = os.environ.get("DREAMINA_INSTALL_DIR", "").strip()
    if install_dir:
        candidates.append(Path(install_dir))
    if sys.platform == "win32":
        home = Path.home()
        candidates.append(home / "bin")
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            candidates.append(Path(local) / "Programs" / "dreamina")
    else:
        home = Path.home()
        candidates += [home / ".local" / "bin", home / "bin", Path("/usr/local/bin")]
        if sys.platform == "darwin":
            candidates.append(Path("/opt/homebrew/bin"))
    for d in candidates:
        cand = d / exe
        if cand.exists():
            return str(cand)
    return None


def _run(cmd: list, cwd: str, timeout: int = 180):
    """静默执行 dreamina 命令，返回合并输出（无窗口、UTF-8 解码兜底）。"""
    startupinfo, creationflags = None, 0
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
    except subprocess.TimeoutExpired:
        return None, f"dreamina 执行超时（>{timeout}s）"
    except FileNotFoundError:
        return None, f"未找到可执行文件：{cmd[0]}"

    raw = proc.stdout or b""
    if proc.stderr:
        if raw and not raw.endswith(b"\n"):
            raw += b"\n"
        raw += proc.stderr
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    return (proc.returncode, text), None


def _first_json(text: str):
    """CLI 可能在 JSON 前打印提示文字；提取首个 JSON 对象。"""
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        pass
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(raw[start : end + 1])
    except ValueError:
        return None


def _parse_task(stdout: str) -> dict:
    text = stdout or ""
    obj = _first_json(text)
    keys_get = lambda *ks: next(
        (str(obj[k]).strip() for k in ks if isinstance(obj, dict) and isinstance(obj.get(k), str) and obj[k].strip()),
        "",
    )
    submit_id = keys_get("submit_id", "submitId", "id")
    if not submit_id:
        m = re.search(r"submit_id\s*[:=]\s*([^\s]+)", text, re.I)
        submit_id = m.group(1) if m else ""
    raw_status = keys_get("gen_status", "genStatus", "status", "task_status")
    if not raw_status:
        m = re.search(r"(?:gen_status|task_status)\s*[:=]\s*([^\s]+)", text, re.I)
        raw_status = m.group(1) if m else ""
    status_l = raw_status.lower()
    if status_l in SUCCESS:
        status = "success"
    elif status_l in FAILED:
        status = "failed"
    elif status_l in PENDING:
        status = "querying"
    else:
        status = status_l
    fail_reason = keys_get("fail_reason", "failReason", "error_msg", "error", "message") or None
    return {"submit_id": submit_id, "status": status, "fail_reason": fail_reason}


def _output_dir(tool_ctx) -> Path:
    app_data = tool_ctx.get("env", {}).get("app_data_dir")
    base = Path(app_data) if app_data else Path.home() / ".drifox"
    out = base / "plugins" / "openhanako-adapter" / "generated"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _submit_impl(tool_ctx, **kwargs):
    mode = str(kwargs.get("mode") or "text2image")
    prompt = str(kwargs.get("prompt") or "").strip()
    if not prompt:
        return ToolResult(False, error="prompt 不能为空")
    if mode not in ("text2image", "image2image", "text2video", "image2video"):
        return ToolResult(False, error=f"未知 mode：{mode}")

    images = kwargs.get("images") or []
    if isinstance(images, str):
        images = [images]
    images = [str(i).strip() for i in images if str(i).strip()]

    cmd_path = _resolve_dreamina()
    if not cmd_path:
        return ToolResult(
            False,
            error=(
                f"未检测到 dreamina CLI。请先执行：{INSTALL_CMD}。"
                "已安装则设置 DREAMINA_CLI_PATH 指向可执行文件，"
                "或 DREAMINA_INSTALL_DIR 指向安装目录。"
            ),
        )

    args = [mode]
    if mode in ("image2image", "image2video"):
        if not images:
            return ToolResult(False, error=f"{mode} 需要至少一张参考图（images）")
        for img in images:
            args += ["--images", img]
    elif images:
        args += ["--images", images[0]]
    args += ["--prompt", prompt]

    model = str(kwargs.get("model") or "").strip()
    if model:
        args += ["--model_version", re.sub(r"^jimeng-image-", "", model, flags=re.I)]

    ratio = str(kwargs.get("ratio") or "").strip()
    if ratio and mode in ("text2image", "image2image"):
        if ratio not in IMAGE_RATIOS:
            return ToolResult(False, error=f"图片 ratio 须为 {'/'.join(IMAGE_RATIOS)}")
        args += ["--ratio", ratio]
    if ratio and mode == "text2video":
        if ratio not in VIDEO_RATIOS:
            return ToolResult(False, error=f"视频 ratio 须为 {'/'.join(VIDEO_RATIOS)}")
        args += ["--ratio", ratio]

    resolution = str(kwargs.get("resolution") or "").strip()
    if resolution:
        if mode.endswith("image"):
            args += ["--resolution_type", resolution]  # 1k/2k/4k
        else:
            args += ["--video_resolution", resolution]

    duration = kwargs.get("duration")
    if duration is not None and mode.endswith("video"):
        args += ["--duration", str(int(duration))]

    args += ["--poll", "0"]  # 提交即返回，轮询交给 query

    out_dir = _output_dir(tool_ctx)
    result, err = _run([cmd_path, *args], str(out_dir))
    if err:
        return ToolResult(False, error=err)
    code, text = result
    parsed = _parse_task(text)
    if not parsed["submit_id"]:
        return ToolResult(
            False,
            error=f"dreamina 提交失败（退出码 {code}）：{text[:500] or '(无输出)'}",
        )
    status = parsed["status"] or "querying"
    return ToolResult(
        True,
        content=(
            f"任务已提交：submit_id={parsed['submit_id']} 状态={status}\n"
            f"下一步：用 jimeng query 查询状态并下载成品到 {out_dir}"
        ),
        data={"submit_id": parsed["submit_id"], "status": status},
    )


def _query_impl(tool_ctx, **kwargs):
    submit_id = str(kwargs.get("submit_id") or "").strip()
    if not submit_id:
        return ToolResult(False, error="submit_id 不能为空")

    cmd_path = _resolve_dreamina()
    if not cmd_path:
        return ToolResult(False, error=f"未检测到 dreamina CLI。安装：{INSTALL_CMD}")

    out_dir = _output_dir(tool_ctx)
    before = {p.name for p in out_dir.iterdir() if p.suffix.lower() in RESULT_EXTS}
    result, err = _run(
        [
            cmd_path,
            "query_result",
            "--submit_id",
            submit_id,
            "--download_dir",
            str(out_dir),
        ],
        str(out_dir),
        timeout=300,
    )
    if err:
        return ToolResult(False, error=err)
    _, text = result
    parsed = _parse_task(text)

    if parsed["status"] == "failed":
        return ToolResult(
            False,
            error=f"生成失败：{parsed['fail_reason'] or text[:300] or '(无原因)'}",
        )
    if parsed["status"] != "success":
        return ToolResult(
            True,
            content=f"任务仍在进行中（{parsed['status'] or 'querying'}），稍后再查。submit_id={submit_id}",
            data={"status": "querying"},
        )

    after = {p.name for p in out_dir.iterdir() if p.suffix.lower() in RESULT_EXTS}
    files = sorted(after - before)
    if not files:
        # CLI 可能已在 JSON 里给出文件路径
        obj = _first_json(text)
        if isinstance(obj, dict):
            files = [
                str(v)
                for v in (obj.get("files") or obj.get("results") or [])
                if isinstance(v, str)
            ]
    if not files:
        return ToolResult(False, error=f"任务成功但未发现成品文件：{text[:300]}")

    paths = [str(out_dir / f) if not Path(f).is_absolute() else f for f in files]
    return ToolResult(
        True,
        content="生成完成，成品：\n" + "\n".join(paths),
        data={"files": paths},
    )


_SCHEMA = {
    "type": "function",
    "function": {
        "name": "jimeng",
        "description": (
            "即梦（Dreamina）生图/生视频工具（移植自 openhanako jimeng-cli）。"
            "action=submit：提交生成任务（文生图/图生图/文生视频/图生视频）；"
            "action=query：轮询任务状态并下载成品。需本地安装 dreamina CLI。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["submit", "query"],
                    "description": "submit=提交生成任务；query=查询状态并下载",
                },
                "mode": {
                    "type": "string",
                    "enum": ["text2image", "image2image", "text2video", "image2video"],
                    "description": "生成模式，默认 text2image",
                },
                "prompt": {
                    "type": "string",
                    "description": "生成提示词（submit 必填）",
                },
                "images": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "参考图路径列表（image2image/image2video 必填，可多张）",
                },
                "ratio": {
                    "type": "string",
                    "description": "宽高比。图：21:9/16:9/3:2/4:3/1:1/3:4/2:3/9:16；视频：1:1/3:4/16:9/4:3/9:16/21:9",
                },
                "resolution": {
                    "type": "string",
                    "description": "分辨率。图：1k/2k/4k；视频按 CLI 支持值",
                },
                "duration": {
                    "type": "integer",
                    "description": "视频时长秒数（仅视频模式）",
                },
                "model": {
                    "type": "string",
                    "description": "模型版本，如 3.0 / 2.1（可选，用 CLI 默认模型）",
                },
                "submit_id": {
                    "type": "string",
                    "description": "query 必填：submit 返回的任务 ID",
                },
            },
            "required": ["action"],
        },
    },
}


def _preview(args: dict) -> str:
    action = (args or {}).get("action", "")
    prompt = (args or {}).get("prompt", "")
    sid = (args or {}).get("submit_id", "")
    if action == "query":
        return f"即梦查询 {sid}"[:60]
    return f"即梦{(args or {}).get('mode', '')}: {escape(str(prompt)[:36])}"


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    from app.tools.registry import make_summarize_from_preview

    def _dispatch(tool_ctx, **kw):
        if kw.get("action") == "submit":
            return _submit_impl(tool_ctx, **kw)
        if kw.get("action") == "query":
            return _query_impl(tool_ctx, **kw)
        return ToolResult(False, error=f"未知 action：{kw.get('action')}")

    registry.register(
        "jimeng",
        _SCHEMA,
        impl=_dispatch,
        danger="dangerous",
        icon="jimeng",
        cn_name="即梦生成",
        group="openhanako",
        description="即梦 CLI 生图/生视频（submit/query）",
        aliases=["即梦", "dreamina"],
        render_mode="",
        preview=_preview,
        summarize=make_summarize_from_preview(_preview),
    )
