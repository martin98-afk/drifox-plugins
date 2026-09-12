# -*- coding: utf-8 -*-
"""MiniMax 云端识别后端：上传 WAV 到 speech_to_text 接口，返回带标点中文文本。

与 SAPI5（recognizer.py）/ Whisper（whisper_recognizer.py）同级、可切换。链路：
16kHz WAV → multipart/form-data 上传（model=asr-1.0）→ JSON text → 回主线程。

设计约束（对齐 whisper_recognizer.py）：
- 纯标准库 urllib 手写 multipart：宿主为 PyInstaller 打包，未收集 requests/urllib3，
  插件因此零第三方依赖，永不因缺依赖不可用。
- API Key 由调用方（ui/__init__.py）读插件配置后传入，本模块不碰存储。
- 线程模型一致：QThread + run()，信号回主线程；transcribe_wav 纯函数便于单测。
- 短录音（≤60s ≈ ≤1.9MB）一次读入内存构造请求体，无流式必要。

接口：POST https://api.minimaxi.com/v1/speech_to_text
认证：Authorization: Bearer <key>
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from loguru import logger
from PyQt5.QtCore import QThread, pyqtSignal

_API_URL = "https://api.minimaxi.com/v1/speech_to_text"
_MODEL = "asr-1.0"
# 上传总超时（秒）。60 秒音频云端识别通常 1~3 秒返回，超时兜防线程悬挂
_TIMEOUT_SEC = 30.0


def transcribe_wav(api_key: str, wav_path: str) -> str:
    """纯函数：上传一条 WAV → 中文文本。无 Qt 依赖，便于单元测试。

    在 worker 线程内调用。失败抛异常（消息已人话化），上层回退本地引擎。
    """
    key = (api_key or "").strip()
    if not key:
        raise ValueError("MiniMax API Key 为空，请到 设置 → 语音听写配置 填写")

    body = _build_multipart(
        fields={"model": _MODEL, "response_format": "json"},
        file_field="file",
        filename=Path(wav_path).name or "audio.wav",
        file_bytes=Path(wav_path).read_bytes(),
        content_type="audio/wav",
    )
    request = Request(
        _API_URL,
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
        logger.error(f"[voice-input] MiniMax HTTP {e.code}: {detail}")
        raise RuntimeError(f"MiniMax 服务返回 HTTP {e.code}") from e
    except URLError as e:
        logger.error(f"[voice-input] MiniMax 网络错误: {e.reason}")
        raise RuntimeError(f"网络错误：{e.reason}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError("MiniMax 返回了无法解析的内容") from e

    text = str(payload.get("text") or "").strip()
    if not text:
        # 200 但无文本：base_resp 携带平台侧错误信息（如 key 无效/额度不足）
        base = payload.get("base_resp") or {}
        msg = str(base.get("status_msg") or f"状态码 {base.get('status_code', '未知')}")
        raise RuntimeError(f"MiniMax 未返回文本：{msg}")
    logger.info(f"[voice-input] MiniMax 识别完成: {len(text)} 字")
    return text


_boundary = f"----drifoxvoice{uuid.uuid4().hex}"


def _build_multipart(
    fields: dict[str, str],
    file_field: str,
    filename: str,
    file_bytes: bytes,
    content_type: str,
) -> bytes:
    """构造 multipart/form-data 请求体（模块级 _boundary 供 headers 复用）。"""
    lines: list[bytes] = []
    for name, value in fields.items():
        lines.append(f'--{_boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8"))
    lines.append(
        (
            f'--{_boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
            f'filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'
        ).encode("utf-8")
    )
    lines.append(file_bytes)
    lines.append(b"\r\n")
    lines.append(f"--{_boundary}--\r\n".encode("utf-8"))
    return b"".join(lines)


class MiniMaxRecognizeWorker(QThread):
    """MiniMax 云端识别 worker。信号语义与 Whisper worker 对齐：
    - finished_ok(str)   识别成功；
    - failed(str)        识别过程出错（网络/HTTP/key 无效），上层据此回退本地引擎；
    - status(str)        阶段文案，用于浮窗标签实时反馈。
    """

    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, wav_path: str, api_key: str, parent=None) -> None:
        super().__init__(parent)
        self._wav_path = wav_path
        self._api_key = api_key

    def run(self) -> None:
        self.status.emit("云端识别中…")
        try:
            text = transcribe_wav(self._api_key, self._wav_path)
            self.finished_ok.emit(text)
        except Exception as e:  # noqa: BLE001 — 全链路兜底，错误回主线程提示
            logger.error(f"[voice-input] MiniMax 识别失败: {e}")
            self.failed.emit(str(e))
