# -*- coding: utf-8 -*-
"""云端语音识别统一 worker：硅基流动（OpenAI 兼容）+ MiniMax 专有接口。

两类服务协议同构：multipart 上传 WAV（file + model 字段）→ Bearer 认证
→ JSON {"text": ...}。差异仅在 URL / 模型名 / Key，由调用方按引擎组装。

设计约束：
- 纯标准库 urllib 手写 multipart：宿主为 PyInstaller 打包，未收集
  requests/urllib3，插件因此零第三方依赖，永不因缺依赖不可用。
- API Key / URL / 模型名由调用方（ui/__init__.py）读插件配置后传入，
  本模块不碰存储、不含引擎知识。
- 线程模型：QThread + run()，信号回主线程；transcribe_wav 纯函数便于单测。
- 短录音（≤60s ≈ ≤1.9MB）一次读入内存构造请求体，无流式必要。
- 超时 30s：免费通道限流时常表现为「挂起不响应」，超时后由上层走备用引擎。
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from loguru import logger
from PyQt5.QtCore import QThread, pyqtSignal

# 上传总超时（秒）。60 秒音频云端识别通常 1~3 秒返回，超时兜防线程悬挂
_TIMEOUT_SEC = 30.0

_boundary = f"----drifoxvoice{uuid.uuid4().hex}"


def transcribe_wav(url: str, model: str, api_key: str, wav_path: str) -> str:
    """纯函数：上传一条 WAV → 文本。无 Qt 依赖，便于单元测试。

    在 worker 线程内调用。失败抛异常（消息已人话化），上层据此走备用引擎。
    """
    key = (api_key or "").strip()
    if not key:
        raise ValueError("API Key 为空，请到 设置 → 语音听写配置 填写")

    body = _build_multipart(
        fields={"model": model},
        file_bytes=Path(wav_path).read_bytes(),
    )
    request = Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={_boundary}",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=_TIMEOUT_SEC) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")[:200]
        except Exception:  # noqa: BLE001 — 读响应体失败不影响主错误
            pass
        logger.error(f"[voice-input] 云端识别 HTTP {e.code}: {detail}")
        raise RuntimeError(f"服务返回 HTTP {e.code}") from e
    except URLError as e:
        reason = str(getattr(e, "reason", e))
        if "timed out" in reason:
            raise RuntimeError("服务响应超时（可能限流）") from e
        logger.error(f"[voice-input] 云端识别网络错误: {reason}")
        raise RuntimeError(f"网络错误：{reason}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError("服务返回了无法解析的内容") from e

    text = str(payload.get("text") or "").strip()
    if not text:
        # 无文本：各平台错误字段不同，逐个翻。
        # MiniMax 风格 base_resp / OpenAI 兼容风格 error / 通用 message
        base = payload.get("base_resp") or {}
        err = payload.get("error")
        if isinstance(err, dict):
            err_msg = str(err.get("message") or err.get("code") or "")
        else:
            err_msg = str(err or "")
        msg = (
            base.get("status_msg")
            or err_msg
            or payload.get("message")
            or ""
        )
        logger.warning(f"[voice-input] 未识别到文本，原始响应: {str(payload)[:300]}")
        if msg:
            raise RuntimeError(f"服务未返回文本：{msg}")
        # 无任何错误字段：服务端正常处理但识别结果为空（录音太短/静音/过载丢音频）
        usage = payload.get("usage") or {}
        seconds = usage.get("seconds") if isinstance(usage, dict) else None
        tail = f"（{seconds} 秒音频）" if seconds else ""
        raise RuntimeError(f"未识别到语音{tail}，请对准麦克风说话后稍停再停止")
    logger.info(f"[voice-input] 云端识别完成: {len(text)} 字")
    return text


def make_probe_wav() -> str:
    """生成 1 秒 440Hz 正弦 WAV（16kHz / 单声道 / 16bit），供连通性测试使用。

    用音调而不是静音：部分平台对纯静音直接判「无效音频」返回 4xx，
    会把「配置正确」误报成失败。调用方负责删除返回的临时文件。
    """
    import math
    import os
    import struct
    import tempfile
    import wave

    rate = 16000
    frames = bytearray()
    for i in range(rate):
        frames += struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate)))
    fd, path = tempfile.mkstemp(suffix=".wav", prefix="drifox_asr_probe_")
    os.close(fd)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(bytes(frames))
    return path


def probe_asr(url: str, model: str, api_key: str, wav_path: str) -> str:
    """连通性探测：只校验服务可达与凭据有效，不要求识别出文字。

    与 transcribe_wav 的差异：识别文本为空**不算失败**（测试音频是音调，
    服务端识别为空属正常）。返回一句人话结论；不可用时抛 RuntimeError。
    """
    key = (api_key or "").strip()
    if not key:
        raise ValueError("API Key 为空")

    body = _build_multipart(
        fields={"model": model},
        file_bytes=Path(wav_path).read_bytes(),
    )
    request = Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={_boundary}",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=_TIMEOUT_SEC) as resp:
            raw = resp.read()
    except HTTPError as e:
        if e.code in (401, 403):
            raise RuntimeError("API Key 无效或无权限（HTTP %s）" % e.code) from e
        if e.code == 404:
            raise RuntimeError(f"端点或模型不存在（HTTP 404，模型 {model}）") from e
        if e.code == 429:
            raise RuntimeError("请求被限流（HTTP 429），稍后重试") from e
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")[:150]
        except Exception:  # noqa: BLE001 — 读响应体失败不影响主错误
            pass
        logger.warning(f"[voice-input] 探测 HTTP {e.code}: {detail}")
        raise RuntimeError(f"服务返回 HTTP {e.code}") from e
    except URLError as e:
        reason = str(getattr(e, "reason", e))
        raise RuntimeError(f"网络错误：{reason}") from e

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise RuntimeError("服务返回了无法解析的内容") from e

    base = payload.get("base_resp") or {}
    if isinstance(base, dict) and base.get("status_code") not in (None, 0):
        raise RuntimeError(f"服务返回错误：{base.get('status_msg') or base.get('status_code')}")
    err = payload.get("error")
    if err:
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise RuntimeError(f"服务返回错误：{msg or err}")
    return "可用（HTTP 200）"


def _build_multipart(fields: dict[str, str], file_bytes: bytes) -> bytes:
    """构造 multipart/form-data 请求体（音频固定文件名 audio.wav）。"""
    lines: list[bytes] = []
    for name, value in fields.items():
        lines.append(
            f'--{_boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode(
                "utf-8"
            )
        )
    lines.append(
        (
            f'--{_boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="audio.wav"\r\nContent-Type: audio/wav\r\n\r\n'
        ).encode("utf-8")
    )
    lines.append(file_bytes)
    lines.append(b"\r\n")
    lines.append(f"--{_boundary}--\r\n".encode("utf-8"))
    return b"".join(lines)


class CloudRecognizeWorker(QThread):
    """云端识别 worker。信号语义：
    - finished_ok(str)   识别成功；
    - failed(str)        识别过程出错（网络/超时/HTTP/key 无效），上层据此走备用引擎；
    - status(str)        阶段文案，用于浮窗标签实时反馈。
    """

    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, wav_path: str, url: str, model: str, api_key: str, parent=None) -> None:
        super().__init__(parent)
        self._wav_path = wav_path
        self._url = url
        self._model = model
        self._api_key = api_key

    def run(self) -> None:
        self.status.emit("云端识别中…")
        try:
            text = transcribe_wav(self._url, self._model, self._api_key, self._wav_path)
            self.finished_ok.emit(text)
        except Exception as e:  # noqa: BLE001 — 全链路兜底，错误回主线程提示
            logger.error(f"[voice-input] 云端识别失败: {e}")
            self.failed.emit(str(e))
