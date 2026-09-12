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
        # 无文本：各平台错误字段不同，逐个翻
        base = payload.get("base_resp") or {}
        msg = (
            base.get("status_msg")
            or payload.get("message")
            or f"状态码 {base.get('status_code', '未知')}"
        )
        raise RuntimeError(f"服务未返回文本：{msg}")
    logger.info(f"[voice-input] 云端识别完成: {len(text)} 字")
    return text


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
