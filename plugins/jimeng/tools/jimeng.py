# -*- coding: utf-8 -*-
"""jimeng — 即梦（Dreamina）官方 CLI 封装工具

通过本地 dreamina CLI 调用即梦的图片/视频生成能力。8 个生成命令 + 8 个管理命令
全部收敛到单工具，用 ``action`` 分派，参数语义与官方 v1.4.21 的 ``-h`` 逐项对齐。

CLI 安装：
  macOS/Linux   curl -s https://jimeng.jianying.com/cli | bash
  Windows       官方安装脚本是 bash（仅 MINGW/MSYS/CYGWIN 走 windows 分支），
                原生 PowerShell 跑不了；直接下载 exe 到 %USERPROFILE%\\bin 即可。

查找顺序：DREAMINA_CLI_PATH → PATH → DREAMINA_INSTALL_DIR → 常见安装目录。

异步语义（官方 SKILL.md 明令）：``submit_id`` + ``gen_status=querying`` 只代表
提交成功，``success`` 才算完成，``fail`` 要念 ``fail_reason``。本工具提交后不阻塞，
轮询交给 ``action=query``。
"""

import json
import os
import re
import subprocess
import sys
from html import escape
from pathlib import Path

from app.tools.result import ToolResult

# ── 常量 ──────────────────────────────────────────────────────────

INSTALL_CMD_UNIX = "curl -s https://jimeng.jianying.com/cli | bash"
INSTALL_WIN_URL = (
    "https://lf3-static.bytednsdoc.com/obj/eden-cn/psj_hupthlyk/ljhwZthlaukjlkulzlp"
    "/dreamina_cli_beta/dreamina_cli_windows_amd64.exe"
)

IMAGE_RATIOS = ("21:9", "16:9", "3:2", "4:3", "1:1", "3:4", "2:3", "9:16")
VIDEO_RATIOS = ("1:1", "3:4", "16:9", "4:3", "9:16", "21:9")
IMAGE_RESOLUTIONS = ("1k", "1.5k", "2k", "4k")
UPSCALE_RESOLUTIONS = ("2k", "4k", "8k")
VIDEO_RESOLUTIONS = ("480p", "720p", "1080p", "4k")

GEN_ACTIONS = (
    "text2image",
    "image2image",
    "upscale",
    "text2video",
    "image2video",
    "frames2video",
    "multiframe2video",
    "multimodal2video",
)
ALL_ACTIONS = GEN_ACTIONS + (
    "query",
    "list_tasks",
    "credit",
    "session",
    "login",
    "checklogin",
    "logout",
    "version",
)

# 扩展名 → (kind, mime)；kind 决定成果栏用哪种控件渲染
_KIND_BY_EXT = {
    ".png": ("image", "image/png"),
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
    ".webp": ("image", "image/webp"),
    ".gif": ("image", "image/gif"),
    ".bmp": ("image", "image/bmp"),
    ".mp4": ("video", "video/mp4"),
    ".mov": ("video", "video/quicktime"),
    ".webm": ("video", "video/webm"),
    ".html": ("html", "text/html"),
    ".htm": ("html", "text/html"),
    ".md": ("text", "text/markdown"),
    ".txt": ("text", "text/plain"),
    ".json": ("text", "application/json"),
}
_RESULT_EXTS = frozenset(_KIND_BY_EXT)

_LOGIN_HINT = "未检测到有效登录态"
_COMPLIANCE_HINT = "AigcComplianceConfirmationRequired"


# ── CLI 定位与执行 ────────────────────────────────────────────────


def _exe_name() -> str:
    return "dreamina.exe" if sys.platform == "win32" else "dreamina"


def _resolve_dreamina() -> "str | None":
    """定位 dreamina 可执行文件：env 显式路径 → PATH → 常见安装目录。"""
    exe = _exe_name()

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
    home = Path.home()
    if sys.platform == "win32":
        candidates.append(home / "bin")
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            candidates.append(Path(local) / "Programs" / "dreamina")
            candidates.append(Path(local) / "dreamina")
    else:
        candidates += [home / ".local" / "bin", home / "bin", Path("/usr/local/bin")]
        if sys.platform == "darwin":
            candidates.append(Path("/opt/homebrew/bin"))
    for d in candidates:
        cand = d / exe
        if cand.exists():
            return str(cand)
    return None


def _install_hint() -> str:
    """按平台给出安装指引（官方脚本在 PowerShell 下不可用）。"""
    if sys.platform == "win32":
        return (
            "未检测到 dreamina CLI。Windows 原生安装（官方脚本是 bash，PowerShell 跑不了）：\n"
            f'  curl.exe -L "{INSTALL_WIN_URL}" -o "$env:USERPROFILE\\bin\\dreamina.exe"\n'
            '  然后把 "$env:USERPROFILE\\bin" 加入用户 PATH\n'
            "已装则在环境变量 DREAMINA_CLI_PATH 指向可执行文件，"
            "或 DREAMINA_INSTALL_DIR 指向安装目录。"
        )
    return (
        f"未检测到 dreamina CLI。请先执行：{INSTALL_CMD_UNIX}。"
        "已安装则设置 DREAMINA_CLI_PATH 指向可执行文件，"
        "或 DREAMINA_INSTALL_DIR 指向安装目录。"
    )


def _decode(raw: bytes) -> str:
    """UTF-8 优先，失败退 GBK（Windows 中文控制台输出）。"""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return raw.decode("gbk")
        except UnicodeDecodeError:
            return raw.decode("utf-8", errors="replace")


def _run(cmd, cwd, timeout: int = 180):
    """静默执行 dreamina 命令，返回 ((退出码, 合并输出), 错误信息)。"""
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
    except OSError as e:
        return None, f"dreamina 启动失败：{e}"

    raw = proc.stdout or b""
    if proc.stderr:
        if raw and not raw.endswith(b"\n"):
            raw += b"\n"
        raw += proc.stderr
    return (proc.returncode, _decode(raw)), None


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


def _cli_failure(text: str) -> "str | None":
    """把 CLI 的已知失败信号翻成人能看懂的引导语；无信号返回 None。"""
    if _LOGIN_HINT in text:
        return (
            "未登录即梦账号。请先调用 jimeng action=login 获取授权链接，"
            "完成授权后再调用 action=checklogin。"
        )
    if _COMPLIANCE_HINT in text:
        return (
            "该模型首次使用需先在即梦网页端完成一次生成（官方合规确认），"
            f"完成后重试。原始提示：{text.strip()[:300]}"
        )
    return None


# ── 路径 ──────────────────────────────────────────────────────────


def _plugin_dir(tool_ctx) -> Path:
    app_data = (tool_ctx or {}).get("env", {}).get("app_data_dir")
    # app_data_dir 可能是相对路径（MCP 宿主进程 cwd 不定），必须 resolve，
    # 否则默认下载目录漂移到宿主 cwd 下，用户找不到成品。
    base = Path(app_data).resolve() if app_data else Path.home() / ".drifox"
    out = base / "plugins" / "jimeng"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _output_dir(tool_ctx) -> Path:
    out = _plugin_dir(tool_ctx) / "generated"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _pending_path(tool_ctx) -> Path:
    return _plugin_dir(tool_ctx) / "pending_login.json"


def _workdir(tool_ctx) -> str:
    """子进程 cwd：工作目录优先，回退插件目录（保证相对路径可解析）。"""
    wd = (tool_ctx or {}).get("workdir")
    if wd and Path(wd).is_dir():
        return str(wd)
    return str(_plugin_dir(tool_ctx))


def _kind_of(path: Path):
    return _KIND_BY_EXT.get(path.suffix.lower(), ("file", "application/octet-stream"))


def _artifact_for(path: Path, caption: str = "", meta=None) -> dict:
    """把一个落盘文件包成成果条目（字段形状见成果栏设计文档）。"""
    kind, mime = _kind_of(path)
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    return {
        "path": str(path),
        "kind": kind,
        "mime": mime,
        "name": path.name,
        "size": size,
        "caption": caption or path.name,
        "meta": dict(meta or {}),
    }


def _result_with_artifacts(**kwargs) -> ToolResult:
    """构造带成果条目的 ToolResult，兼容尚未升级的主程序。

    ``ToolResult.artifacts`` 是新增字段：宿主未升级时构造参数不存在，直接传会
    TypeError。降级策略是丢掉该字段——content 里已写了文件路径，功能退化为
    「告诉用户文件在哪」，不会失败。
    """
    artifacts = kwargs.pop("artifacts", None)
    if artifacts:
        try:
            return ToolResult(artifacts=artifacts, **kwargs)
        except TypeError:
            pass
    return ToolResult(**kwargs)


def _scan_results(directory: Path) -> "list[Path]":
    """递归收集目录下成果文件（CLI 可能忽略 download_dir 写进 cwd 下嵌套默认目录）。"""
    try:
        return [
            p for p in directory.rglob("*")
            if p.is_file() and p.suffix.lower() in _RESULT_EXTS
        ]
    except OSError:
        return []


# ── 参数校验 ──────────────────────────────────────────────────────


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _check_ratio(value: str, video: bool):
    if not value:
        return None
    allowed = VIDEO_RATIOS if video else IMAGE_RATIOS
    if value not in allowed:
        return f"ratio 须为 {'/'.join(allowed)}，收到 {value!r}"
    return None


def _check_resolution(value: str, allowed, label: str):
    if not value:
        return None
    if value not in allowed:
        return f"{label} 须为 {'/'.join(allowed)}，收到 {value!r}"
    return None


# ── 生成命令参数构建 ──────────────────────────────────────────────

def _append_session_poll(args, kw):
    sid = kw.get("session_id")
    if sid is not None and str(sid).strip() != "":
        args += ["--session", str(int(sid))]
    poll = kw.get("poll")
    if poll is not None and str(poll).strip() != "":
        args += ["--poll", str(int(poll))]


def _append_dimensions(args, kw):
    width, height = kw.get("width"), kw.get("height")
    if width is None and height is None:
        return None
    if width is None or height is None:
        return "width 与 height 必须成对提供"
    try:
        args += ["--width", str(int(width)), "--height", str(int(height))]
    except (TypeError, ValueError):
        return "width/height 须为正整数"
    return None


def _build_text2image(args, kw):
    res = str(kw.get("resolution") or "").strip()
    err = _check_resolution(res, IMAGE_RESOLUTIONS, "resolution（图）")
    if err:
        return err
    if not res:
        return "text2image 需要 resolution（1k/1.5k/2k/4k，按模型不同）"
    args += ["--resolution_type", res]
    err = _check_ratio(str(kw.get("ratio") or "").strip(), video=False)
    if err:
        return err
    return None


def _build_image2image(args, kw):
    return _build_text2image(args, kw)


def _build_upscale(args, kw):
    res = str(kw.get("resolution") or "").strip()
    err = _check_resolution(res, UPSCALE_RESOLUTIONS, "resolution（放大）")
    if err:
        return err
    if not res:
        return "upscale 需要 resolution（2k/4k/8k）"
    args += ["--resolution_type", res]
    return None


def _build_video_common(args, kw):
    res = str(kw.get("resolution") or "").strip()
    err = _check_resolution(res, VIDEO_RESOLUTIONS, "resolution（视频）")
    if err:
        return err
    if not res:
        return "视频命令需要 resolution（480p/720p/1080p/4k，按模型不同）"
    args += ["--video_resolution", res]
    err = _check_ratio(str(kw.get("ratio") or "").strip(), video=True)
    if err:
        return err
    return None


def _build_text2video(args, kw):
    return _build_video_common(args, kw)


def _build_image2video(args, kw):
    return _build_video_common(args, kw)


def _build_frames2video(args, kw):
    return _build_video_common(args, kw)


def _build_multiframe2video(args, kw):
    res = str(kw.get("resolution") or "").strip()
    err = _check_resolution(res, VIDEO_RESOLUTIONS, "resolution（多帧视频）")
    if err:
        return err
    if not res:
        return "multiframe2video 需要 resolution（720p/1080p）"
    args += ["--video_resolution", res]
    return None


def _build_multimodal2video(args, kw):
    return _build_video_common(args, kw)


# 每个生成 action：CLI 子命令 + prompt 是否必填 + 是否需要多图 + 是否需要单图 +
# 是否需要首尾帧 + 是否支持 model/ratio/duration/generate_num/尺寸
_GEN_SPECS = {
    "text2image": {
        "cmd": "text2image",
        "prompt": "required",
        "build": _build_text2image,
        "model": True, "ratio": True, "duration": False,
        "generate_num": True, "dims": True,
    },
    "image2image": {
        "cmd": "image2image",
        "prompt": "required",
        "images": (1, 10, "--images"),
        "build": _build_image2image,
        "model": True, "ratio": True, "duration": False,
        "generate_num": True, "dims": True,
    },
    "upscale": {
        "cmd": "image_upscale",
        "prompt": "none",
        "single_image": "--image",
        "build": _build_upscale,
        "model": False, "ratio": False, "duration": False,
        "generate_num": False, "dims": False,
    },
    "text2video": {
        "cmd": "text2video",
        "prompt": "required",
        "build": _build_text2video,
        "model": True, "ratio": True, "duration": True,
        "generate_num": False, "dims": False,
    },
    "image2video": {
        "cmd": "image2video",
        "prompt": "required",
        "single_image": "--image",
        "build": _build_image2video,
        "model": True, "ratio": True, "duration": True,
        "generate_num": False, "dims": False,
    },
    "frames2video": {
        "cmd": "frames2video",
        "prompt": "optional",
        "first_last": True,
        "build": _build_frames2video,
        "model": True, "ratio": True, "duration": True,
        "generate_num": False, "dims": False,
    },
    "multiframe2video": {
        "cmd": "multiframe2video",
        "prompt": "optional",
        "images": (2, 20, "--images"),
        "transitions": True,
        "build": _build_multiframe2video,
        "model": False, "ratio": False, "duration": False,
        "generate_num": False, "dims": False,
    },
    "multimodal2video": {
        "cmd": "multimodal2video",
        "prompt": "optional",
        "multimodal": True,
        "build": _build_multimodal2video,
        "model": True, "ratio": True, "duration": True,
        "generate_num": False, "dims": False,
    },
}


def _build_gen_args(action: str, kw) -> "tuple[list, str | None]":
    """按 action 组装 CLI 参数。返回 (args, 错误信息)。"""
    spec = _GEN_SPECS[action]
    args = [spec["cmd"]]
    prompt = str(kw.get("prompt") or "").strip()

    if spec["prompt"] == "required" and not prompt:
        return [], f"{action} 需要 prompt"
    if prompt:
        args += ["--prompt", prompt]

    # 多图（image2image / multiframe2video）
    if "images" in spec:
        lo, hi, flag = spec["images"]
        images = _as_list(kw.get("images"))
        if not images and action == "image2image":
            return [], "image2image 需要 images（1-10 张本地图片路径）"
        if images and not (lo <= len(images) <= hi):
            return [], f"{action} 的 images 需 {lo}-{hi} 张，收到 {len(images)} 张"
        for img in images:
            args += [flag, img]

    # 单图（image2video / upscale）
    if "single_image" in spec:
        image = str(kw.get("image") or "").strip()
        if not image:
            return [], f"{action} 需要 image（本地图片路径）"
        args += [spec["single_image"], image]

    # 首尾帧
    if spec.get("first_last"):
        first, last = str(kw.get("first") or "").strip(), str(kw.get("last") or "").strip()
        if not first or not last:
            return [], "frames2video 需要 first 与 last（首帧/尾帧图片路径）"
        args += ["--first", first, "--last", last]

    # 多模态（图/视频/音频混参）
    if spec.get("multimodal"):
        images = _as_list(kw.get("images"))
        videos = _as_list(kw.get("videos"))
        audios = _as_list(kw.get("audios"))
        for img in images:
            args += ["--image", img]
        for vid in videos:
            args += ["--video", vid]
        for aud in audios:
            args += ["--audio", aud]
        if not (images or videos or audios):
            return [], "multimodal2video 需要至少一个 images / videos / audios"

    # 多帧过渡提示词
    if spec.get("transitions"):
        images = _as_list(kw.get("images"))
        prompts = _as_list(kw.get("transition_prompts"))
        durations = _as_list(kw.get("transition_durations"))
        if len(images) > 2 and not prompts:
            return [], (
                f"multiframe2video 传了 {len(images)} 张图，需要 {len(images) - 1} 个 "
                "transition_prompts 描述相邻帧如何过渡"
            )
        if prompts and len(prompts) != len(images) - 1:
            return [], f"transition_prompts 需 {len(images) - 1} 个，收到 {len(prompts)} 个"
        for p in prompts:
            args += ["--transition-prompt", p]
        for d in durations:
            args += ["--transition-duration", d]

    # 模型 / 宽高比 / 时长 / 张数
    if spec.get("model"):
        model = str(kw.get("model") or "").strip()
        if model:
            args += ["--model_version", model]
    if spec.get("ratio"):
        ratio = str(kw.get("ratio") or "").strip()
        if ratio:
            args += ["--ratio", ratio]
    if spec.get("duration"):
        duration = kw.get("duration")
        if duration is not None and str(duration).strip() != "":
            try:
                args += ["--duration", str(int(duration))]
            except (TypeError, ValueError):
                return [], "duration 须为整数秒"
    if spec.get("generate_num"):
        num = kw.get("generate_num")
        if num is not None and str(num).strip() != "":
            try:
                num_i = int(num)
            except (TypeError, ValueError):
                return [], "generate_num 须为整数"
            if not (1 <= num_i <= 10):
                return [], "generate_num 需在 1-10 之间"
            args += ["--generate_num", str(num_i)]
    if spec.get("dims"):
        err = _append_dimensions(args, kw)
        if err:
            return [], err

    # 分辨率 + 宽高比取值校验（图/视频各自的合法值）
    err = spec["build"](args, kw)
    if err:
        return [], err

    _append_session_poll(args, kw)
    return args, None


# ── 各 action 实现 ────────────────────────────────────────────────


def _require_cli():
    path = _resolve_dreamina()
    if not path:
        return None, ToolResult(False, error=_install_hint())
    return path, None


def _gen_impl(tool_ctx, action: str, kw) -> ToolResult:
    cmd_path, err_result = _require_cli()
    if err_result:
        return err_result

    args, err = _build_gen_args(action, kw)
    if err:
        return ToolResult(False, error=err)

    workdir = _workdir(tool_ctx)
    result, run_err = _run([cmd_path, *args], workdir, timeout=180)
    if run_err:
        return ToolResult(False, error=run_err)
    code, text = result

    hint = _cli_failure(text)
    if hint:
        return ToolResult(False, error=hint)

    obj = _first_json(text)
    submit_id = ""
    status = ""
    if isinstance(obj, dict):
        for key in ("submit_id", "submitId", "id"):
            val = obj.get(key)
            if isinstance(val, str) and val.strip():
                submit_id = val.strip()
                break
        for key in ("gen_status", "genStatus", "status"):
            val = obj.get(key)
            if isinstance(val, str) and val.strip():
                status = val.strip().lower()
                break
    if not submit_id:
        m = re.search(r"submit_id\s*[:=]\s*([^\s,}]+)", text, re.I)
        submit_id = m.group(1) if m else ""

    if not submit_id:
        return ToolResult(
            False,
            error=f"dreamina {action} 提交失败（退出码 {code}）：{text.strip()[:600] or '(无输出)'}",
        )

    lines = [
        f"任务已提交：submit_id={submit_id}",
        f"状态：{status or 'querying'}（querying 仅表示提交成功，success 才算完成）",
        "",
        "下一步：调用 jimeng action=query 并传 submit_id 查询并下载成品。",
    ]
    if status and status not in ("querying", "pending", "running", "submitted", ""):
        lines.insert(2, f"注意：提交即返回状态 {status}，请以 query 结果为准。")
    return ToolResult(
        True,
        content="\n".join(lines),
        data={"submit_id": submit_id, "status": status or "querying", "action": action},
    )


def _query_impl(tool_ctx, kw) -> ToolResult:
    submit_id = str(kw.get("submit_id") or "").strip()
    if not submit_id:
        return ToolResult(False, error="query 需要 submit_id")

    cmd_path, err_result = _require_cli()
    if err_result:
        return err_result

    out_dir = Path(str(kw.get("download_dir") or "").strip() or _output_dir(tool_ctx))
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return ToolResult(False, error=f"下载目录不可用：{out_dir}（{e}）")

    # 目录差异法：并发任务会互相串（已知限制），JSON 路径优先于差异
    before = {p.name for p in _scan_results(out_dir)}
    result, run_err = _run(
        [cmd_path, "query_result", "--submit_id", submit_id, "--download_dir", str(out_dir)],
        str(out_dir),
        timeout=300,
    )
    if run_err:
        return ToolResult(False, error=run_err)
    code, text = result

    hint = _cli_failure(text)
    if hint:
        return ToolResult(False, error=hint)

    obj = _first_json(text) if isinstance(_first_json(text), dict) else {}
    status_raw = ""
    fail_reason = ""
    for key in ("gen_status", "genStatus", "status"):
        val = obj.get(key) if isinstance(obj, dict) else None
        if isinstance(val, str) and val.strip():
            status_raw = val.strip().lower()
            break
    for key in ("fail_reason", "failReason", "error_msg"):
        val = obj.get(key) if isinstance(obj, dict) else None
        if isinstance(val, str) and val.strip():
            fail_reason = val.strip()
            break
    if not status_raw:
        m = re.search(r"gen_status\s*[:=]\s*([^\s,}]+)", text, re.I)
        status_raw = m.group(1).strip().lower() if m else ""

    success_set = {"success", "succeeded", "done", "completed"}
    fail_set = {"fail", "failed", "error"}
    pending_set = {"querying", "pending", "running", "processing", "submitted"}

    if status_raw in fail_set:
        return ToolResult(
            False,
            error=f"生成失败：{fail_reason or text.strip()[:400] or '(无原因)'}",
            data={"submit_id": submit_id, "status": "failed"},
        )
    if status_raw in pending_set or not status_raw:
        return ToolResult(
            True,
            content=(
                f"任务进行中（{status_raw or 'querying'}），稍后再查。submit_id={submit_id}\n"
                f"下载目录：{out_dir}"
            ),
            data={"submit_id": submit_id, "status": status_raw or "querying"},
        )

    if status_raw not in success_set:
        return ToolResult(
            False,
            error=f"未知任务状态 {status_raw!r}，原始输出：{text.strip()[:400]}",
            data={"submit_id": submit_id, "status": status_raw},
        )

    # 成功：优先 JSON 里的路径，其次目录差异（含嵌套子目录）
    files = []
    for key in ("files", "results", "paths", "download_paths"):
        val = obj.get(key) if isinstance(obj, dict) else None
        if isinstance(val, list):
            files += [str(v) for v in val if isinstance(v, str) and v.strip()]
    # CLI 实际回传 result_json.images[]/videos[].path（v1.4.21 实测）
    rj = obj.get("result_json") if isinstance(obj, dict) else None
    if isinstance(rj, dict):
        for group in ("images", "videos", "audios"):
            val = rj.get(group)
            if isinstance(val, list):
                files += [
                    str(v.get("path")).strip()
                    for v in val
                    if isinstance(v, dict) and str(v.get("path") or "").strip()
                ]
    paths = []
    for f in files:
        p = Path(f)
        if not p.is_absolute():
            # CLI 可能回显自身默认相对路径（如 .drifox\plugins\...），
            # 按原样拼不存在时按文件名兜底
            cand = out_dir / p
            p = cand if cand.exists() else out_dir / p.name
        if p.exists():
            paths.append(p)
    if not paths:
        paths = sorted(
            (p for p in _scan_results(out_dir) if p.name not in before),
            key=lambda p: p.name,
        )

    if not paths:
        return ToolResult(
            False,
            error=(
                f"任务成功但未发现成品文件。原始输出：{text.strip()[:400]}\n"
                f"如 CLI 已下载到别处，请检查 {out_dir}"
            ),
            data={"submit_id": submit_id, "status": "success"},
        )

    caption = str(kw.get("prompt") or "").strip()
    artifacts = [_artifact_for(p, caption, {"submit_id": submit_id}) for p in paths]
    return _result_with_artifacts(
        success=True,
        content="生成完成，成品已保存：\n" + "\n".join(str(p) for p in paths),
        artifacts=artifacts,
        data={"submit_id": submit_id, "status": "success", "files": [str(p) for p in paths]},
    )


def _list_tasks_impl(tool_ctx, kw) -> ToolResult:
    cmd_path, err_result = _require_cli()
    if err_result:
        return err_result
    args = ["list_task"]
    for key, flag in (
        ("gen_status", "--gen_status"),
        ("gen_task_type", "--gen_task_type"),
        ("submit_id", "--submit_id"),
        ("limit", "--limit"),
        ("offset", "--offset"),
    ):
        val = kw.get(key)
        if val is not None and str(val).strip() != "":
            args += [flag, str(val).strip()]

    result, run_err = _run([cmd_path, *args], _workdir(tool_ctx), timeout=60)
    if run_err:
        return ToolResult(False, error=run_err)
    code, text = result
    hint = _cli_failure(text)
    if hint:
        return ToolResult(False, error=hint)
    if code != 0 and not text.strip():
        return ToolResult(False, error=f"list_task 失败（退出码 {code}）")
    obj = _first_json(text)
    return ToolResult(
        True,
        content=text.strip() or "(无任务)",
        data={"tasks": obj} if isinstance(obj, (list, dict)) else {},
    )


def _credit_impl(tool_ctx) -> ToolResult:
    cmd_path, err_result = _require_cli()
    if err_result:
        return err_result
    result, run_err = _run([cmd_path, "user_credit"], _workdir(tool_ctx), timeout=60)
    if run_err:
        return ToolResult(False, error=run_err)
    code, text = result
    hint = _cli_failure(text)
    if hint:
        return ToolResult(False, error=hint)
    obj = _first_json(text)
    return ToolResult(
        True,
        content=text.strip() or "(无输出)",
        data={"credit": obj} if isinstance(obj, (dict, list)) else {},
    )


def _session_impl(tool_ctx, kw) -> ToolResult:
    sub = str(kw.get("session_action") or "").strip().lower()
    if sub not in ("create", "list", "search", "rename", "delete"):
        return ToolResult(
            False, error="session 需要 session_action：create / list / search / rename / delete"
        )
    cmd_path, err_result = _require_cli()
    if err_result:
        return err_result

    name = str(kw.get("session_name") or "").strip()
    sid = kw.get("session_id")
    args = ["session"]
    if sub == "create":
        args += ["create"]
        if name:
            args += [name]
    elif sub == "list":
        args += ["list"]
        limit = kw.get("limit")
        if limit is not None and str(limit).strip() != "":
            args += ["-n", str(int(limit))]
    elif sub == "search":
        if not name:
            return ToolResult(False, error="session search 需要 session_name")
        args += ["search", name]
    elif sub == "rename":
        if sid is None or str(sid).strip() == "" or not name:
            return ToolResult(False, error="session rename 需要 session_id 与 session_name")
        args += ["rename", str(int(sid)), name]
    else:  # delete
        if sid is None or str(sid).strip() == "":
            return ToolResult(False, error="session delete 需要 session_id")
        args += ["rm", str(int(sid))]

    result, run_err = _run([cmd_path, *args], _workdir(tool_ctx), timeout=60)
    if run_err:
        return ToolResult(False, error=run_err)
    code, text = result
    hint = _cli_failure(text)
    if hint:
        return ToolResult(False, error=hint)
    if code != 0:
        return ToolResult(False, error=f"session {sub} 失败（退出码 {code}）：{text.strip()[:400]}")
    return ToolResult(True, content=text.strip() or f"session {sub} 完成")


def _login_impl(tool_ctx) -> ToolResult:
    """headless 两段式第一段：拿授权材料并退出，不阻塞等人工。"""
    cmd_path, err_result = _require_cli()
    if err_result:
        return err_result

    result, run_err = _run([cmd_path, "login", "--headless"], _workdir(tool_ctx), timeout=90)
    if run_err:
        return ToolResult(False, error=run_err)
    code, text = result

    uri = ""
    m = re.search(r"verification_uri[\"'\s:：]*([^\s\"',}]+)", text, re.I)
    if m:
        uri = m.group(1)
    if not uri:
        m = re.search(r"https?://[^\s\"',}]+", text)
        uri = m.group(0) if m else ""
    user_code = ""
    m = re.search(r"user_code[\"'\s:：]*([A-Za-z0-9-]+)", text, re.I)
    if m:
        user_code = m.group(1)
    device_code = ""
    m = re.search(r"device_code[\"'\s:：]*([A-Za-z0-9._-]+)", text, re.I)
    if m:
        device_code = m.group(1)

    if not device_code:
        obj = _first_json(text)
        if isinstance(obj, dict):
            device_code = str(obj.get("device_code") or "").strip()
            uri = uri or str(obj.get("verification_uri") or "").strip()
            user_code = user_code or str(obj.get("user_code") or "").strip()

    if not device_code:
        return ToolResult(
            False,
            error=(
                "未能从 CLI 输出解析出 device_code。请手动执行 "
                "`dreamina login --headless` 并按提示授权。原始输出：\n"
                + (text.strip()[:600] or "(无输出)")
            ),
        )

    try:
        _pending_path(tool_ctx).write_text(
            json.dumps({"device_code": device_code}, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass

    lines = [
        "请在浏览器打开下面的地址完成即梦授权：",
        "",
        f"  授权链接：{uri or '(见原始输出)'}",
        f"  验证码  ：{user_code or '(见原始输出)'}",
        "",
        "授权完成后调用 jimeng action=checklogin（device_code 已本地暂存，无需重新提供）。",
    ]
    if not uri or not user_code:
        lines += ["", "原始输出：", text.strip()[:800]]
    return ToolResult(True, content="\n".join(lines), data={"device_code": device_code})


def _checklogin_impl(tool_ctx, kw) -> ToolResult:
    cmd_path, err_result = _require_cli()
    if err_result:
        return err_result

    device_code = str(kw.get("device_code") or "").strip()
    if not device_code:
        try:
            data = json.loads(_pending_path(tool_ctx).read_text(encoding="utf-8"))
            device_code = str(data.get("device_code") or "").strip()
        except (OSError, ValueError):
            device_code = ""
    if not device_code:
        return ToolResult(False, error="没有待完成的登录。请先调用 jimeng action=login")

    poll = kw.get("poll")
    poll_s = str(int(poll)) if poll is not None and str(poll).strip() != "" else "30"
    result, run_err = _run(
        [cmd_path, "login", "checklogin", f"--device_code={device_code}", f"--poll={poll_s}"],
        _workdir(tool_ctx),
        timeout=max(60, int(poll_s) + 30),
    )
    if run_err:
        return ToolResult(False, error=run_err)
    code, text = result

    body = text.strip()
    lower = body.lower()

    # 未授权时 CLI 轮询到期输出「等待登录超时，请重试」并以非 0 退出。
    # 这不是失败而是「用户还没点授权」，保留 pending 让用户授权后再查。
    timeout_hint = ("超时" in body) or ("timeout" in lower) or ("timed out" in lower)
    still_pending = ("authorization_pending" in lower) or ("等待" in body)
    if timeout_hint or still_pending:
        return ToolResult(
            True,
            content=(
                "授权还没完成。请先在浏览器打开 login 返回的链接完成即梦授权，"
                "然后再次调用 jimeng action=checklogin。\n"
                f"CLI 输出：{body[:300]}"
            ),
            data={"status": "pending"},
        )

    # CLI 实测：OAuth 成功但账号无 dreamina_cli 权限（非会员）时同样以非 0 退出，
    # 输出含 user_id/total_credit 即登录已成功，不能笼统报错。
    logged_in = (
        ("user_id" in lower)
        or ("total_credit" in lower)
        or ("登录成功" in body)
    ) and _LOGIN_HINT not in body
    if code == 0 or logged_in:
        try:
            _pending_path(tool_ctx).unlink()
        except OSError:
            pass
        no_perm = ("dreamina_cli" in lower) and (
            ("权限" in body) or ("permission" in lower) or ("会员" in body)
        )
        if no_perm:
            return ToolResult(
                True,
                content=(
                    "OAuth 登录成功，但当前账号没有 dreamina_cli 使用权限（仅限会员），"
                    "开通会员或换会员账号后即可生成。\n"
                    f"CLI 输出：{body[:300]}"
                ),
                data={"status": "success", "permission": "limited"},
            )
        return ToolResult(
            True,
            content="即梦登录成功，可以开始生成。\n" + (f"CLI 输出：{body[:200]}" if body else ""),
            data={"status": "success"},
        )

    return ToolResult(
        False,
        error=f"登录检查失败（退出码 {code}）：{body[:500] or '(无输出)'}",
    )


def _logout_impl(tool_ctx) -> ToolResult:
    cmd_path, err_result = _require_cli()
    if err_result:
        return err_result
    result, run_err = _run([cmd_path, "logout"], _workdir(tool_ctx), timeout=60)
    if run_err:
        return ToolResult(False, error=run_err)
    code, text = result
    if code != 0:
        return ToolResult(False, error=f"logout 失败（退出码 {code}）：{text.strip()[:400]}")
    return ToolResult(True, content=text.strip() or "已清除本地即梦登录态。")


def _version_impl(tool_ctx) -> ToolResult:
    cmd_path, err_result = _require_cli()
    if err_result:
        return err_result
    result, run_err = _run([cmd_path, "version"], _workdir(tool_ctx), timeout=30)
    if run_err:
        return ToolResult(False, error=run_err)
    _, text = result
    return ToolResult(
        True,
        content=f"dreamina CLI: {text.strip() or '(无输出)'}\n可执行文件：{cmd_path}",
    )


# ── 注册 ──────────────────────────────────────────────────────────

_SCHEMA = {
    "type": "function",
    "function": {
        "name": "jimeng",
        "description": (
            "即梦（Dreamina）生图/生视频，封装官方 dreamina CLI。消耗账号额度。\n"
            "生成（提交即返回 submit_id，异步）："
            "text2image / image2image / upscale / text2video / image2video / "
            "frames2video / multiframe2video / multimodal2video。\n"
            "任务：query（按 submit_id 查状态并下载成品）/ list_tasks。\n"
            "账号：credit / session（create,list,search,rename,delete）。\n"
            "登录：login（返回授权链接与验证码，不阻塞）/ checklogin / logout。\n"
            "元信息：version。\n"
            "必填速查：图类要 prompt+resolution（upscale 只需 image+resolution）；"
            "视频类要 resolution（480p/720p/1080p/4k，按模型不同）；"
            "image2image 要 images(1-10)；image2video 要 image；"
            "frames2video 要 first+last；multiframe2video 要 images(2-20)，"
            "3 张以上需 transition_prompts(N-1 个)；multimodal2video 要 images/videos/audios 之一。\n"
            "生成完成后用 action=query 取回成品，文件会落盘并展示在消息卡片成果栏。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": list(ALL_ACTIONS),
                    "description": "要执行的动作",
                },
                "prompt": {
                    "type": "string",
                    "description": "提示词。多数生成命令必填；frames2video/multiframe2video 选填；upscale 不用",
                },
                "images": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "本地图片路径列表。image2image(1-10)、multiframe2video(2-20)、multimodal2video",
                },
                "image": {
                    "type": "string",
                    "description": "单张本地图片路径。image2video（首帧）、upscale",
                },
                "first": {"type": "string", "description": "frames2video 首帧图片路径"},
                "last": {"type": "string", "description": "frames2video 尾帧图片路径"},
                "videos": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "multimodal2video 参考视频路径列表",
                },
                "audios": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "multimodal2video 参考音频路径列表",
                },
                "transition_prompts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "multiframe2video 过渡描述，N 张图需 N-1 个",
                },
                "transition_durations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "multiframe2video 每段过渡秒数（1-8），可省（默认 3）",
                },
                "model": {
                    "type": "string",
                    "description": (
                        "模型版本。图：3.0/3.1/4.0/4.1/4.5/4.6/4.7/5.0/5.0Pro；"
                        "视频：seedance2.0/seedance2.0fast/seedance2.0_vip/"
                        "seedance2.0fast_vip/seedance2.0mini/seedance2.5（部分命令还支持 "
                        "seedance1.0fast/seedance1.5pro）。留空用 CLI 默认"
                    ),
                },
                "ratio": {
                    "type": "string",
                    "description": (
                        "宽高比。图：21:9/16:9/3:2/4:3/1:1/3:4/2:3/9:16；"
                        "视频：1:1/3:4/16:9/4:3/9:16/21:9。seedance2.5 的图生视频不接受 ratio"
                    ),
                },
                "resolution": {
                    "type": "string",
                    "description": (
                        "分辨率，必填。图：1k/1.5k/2k/4k（按模型不同）；"
                        "upscale：2k/4k/8k；视频：480p/720p/1080p/4k（按模型不同）"
                    ),
                },
                "duration": {
                    "type": "integer",
                    "description": "视频时长秒数。seedance2.5 支持 4-30，其余 4-15（1.5pro 5-12）",
                },
                "generate_num": {
                    "type": "integer",
                    "description": "出图张数 1-10（仅 text2image / image2image）",
                },
                "width": {
                    "type": "integer",
                    "description": "自定义宽度（仅图类），须与 height 成对，与 ratio 互斥",
                },
                "height": {
                    "type": "integer",
                    "description": "自定义高度（仅图类），须与 width 成对，与 ratio 互斥",
                },
                "session_id": {
                    "type": "integer",
                    "description": "即梦会话 id。生成命令用它归档任务；session rename/delete 用它指定目标",
                },
                "session_action": {
                    "type": "string",
                    "enum": ["create", "list", "search", "rename", "delete"],
                    "description": "session 动作",
                },
                "session_name": {
                    "type": "string",
                    "description": "会话名（create/rename 的新名、search 的查询词），1-50 字",
                },
                "submit_id": {
                    "type": "string",
                    "description": "任务 id。query 必填；list_tasks 用作过滤条件",
                },
                "download_dir": {
                    "type": "string",
                    "description": "成品下载目录（仅 query），留空用插件默认目录",
                },
                "gen_status": {
                    "type": "string",
                    "description": "list_tasks 过滤：按任务状态（如 success / fail / querying）",
                },
                "gen_task_type": {
                    "type": "string",
                    "description": "list_tasks 过滤：按任务类型",
                },
                "limit": {
                    "type": "integer",
                    "description": "数量上限。list_tasks 默认 20；session list 默认 30（上限 100）",
                },
                "offset": {"type": "integer", "description": "list_tasks 分页偏移"},
                "device_code": {
                    "type": "string",
                    "description": "checklogin 用。通常不用传，login 已在本地暂存",
                },
                "poll": {
                    "type": "integer",
                    "description": (
                        "提交后等待秒数（0=不等待，立即返回 submit_id）。默认不等待；"
                        "checklogin 时表示轮询等待秒数，默认 30"
                    ),
                },
            },
            "required": ["action"],
        },
    },
}


_ACTION_LABELS = {
    "text2image": "文生图",
    "image2image": "图生图",
    "upscale": "图片放大",
    "text2video": "文生视频",
    "image2video": "图生视频",
    "frames2video": "首尾帧生视频",
    "multiframe2video": "多帧生视频",
    "multimodal2video": "多模态生视频",
    "query": "查询任务",
    "list_tasks": "任务列表",
    "credit": "查额度",
    "session": "会话管理",
    "login": "登录",
    "checklogin": "登录检查",
    "logout": "退出登录",
    "version": "版本",
}


def _preview(args: dict) -> str:
    args = args or {}
    action = str(args.get("action") or "")
    label = _ACTION_LABELS.get(action, action or "即梦")
    prompt = str(args.get("prompt") or "").strip()
    if action == "query":
        return f"即梦查询 {str(args.get('submit_id') or '')[:16]}"
    if action in ("credit", "version", "logout", "login", "checklogin", "list_tasks"):
        return f"即梦{label}"
    if action == "session":
        return f"即梦会话 {args.get('session_action') or ''}".strip()
    if prompt:
        return f"即梦{label}: {escape(prompt[:36])}"
    return f"即梦{label}"


def _dispatch(tool_ctx, **kw):
    action = str(kw.get("action") or "").strip()
    if action not in ALL_ACTIONS:
        return ToolResult(False, error=f"未知 action：{action!r}")
    if action in GEN_ACTIONS:
        return _gen_impl(tool_ctx, action, kw)
    if action == "query":
        return _query_impl(tool_ctx, kw)
    if action == "list_tasks":
        return _list_tasks_impl(tool_ctx, kw)
    if action == "credit":
        return _credit_impl(tool_ctx)
    if action == "session":
        return _session_impl(tool_ctx, kw)
    if action == "login":
        return _login_impl(tool_ctx)
    if action == "checklogin":
        return _checklogin_impl(tool_ctx, kw)
    if action == "logout":
        return _logout_impl(tool_ctx)
    return _version_impl(tool_ctx)


def register(registry):
    """工具插件化注册入口（PluginToolLoader 调用）"""
    from app.tools.registry import make_summarize_from_preview

    registry.register(
        "jimeng",
        _SCHEMA,
        impl=_dispatch,
        danger="dangerous",
        icon="jimeng",
        cn_name="即梦生成",
        group="jimeng",
        description="即梦（Dreamina）生图/生视频：官方 CLI 全命令封装，消耗额度",
        aliases=["即梦", "dreamina", "jimeng"],
        render_mode="",
        preview=_preview,
        summarize=make_summarize_from_preview(_preview),
    )
