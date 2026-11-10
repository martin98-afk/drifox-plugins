# -*- coding: utf-8 -*-
"""云端语音识别：分片上传 + 说话人分离解析 + 顺序队列 worker。

协议（硅基流动 /v1/audio/transcriptions）::

    POST multipart: file=<wav>, model=<模型名>
    Authorization: Bearer <key>

    普通模型 → {"text": "..."}
    说话人分离模型 → {"text": "1: ...", "segments": [
        {"start": 0.08, "end": 5.16, "text": "...", "speaker": "1"}, ...]}

设计约束：
- 纯标准库 urllib 手写 multipart（宿主是 PyInstaller 打包，插件零第三方依赖）。
- 识别在后台线程串行执行：并发请求会撞免费模型的 TPM/RPM 限流，而队列天然
  保证「先录的片先出结果」，UI 追加顺序与时间轴一致。
- 失败重试 2 次（2s/5s 退避）：限流与网络抖动是常态；401/403 立即失败不重试。
"""

from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from loguru import logger

# 单片（≤60s）识别超时；免费模型限流时表现为挂起不响应
CHUNK_TIMEOUT_SEC = 90.0
# 整段复转（≤25 分钟）超时
FULL_TIMEOUT_SEC = 600.0

_RETRY_DELAYS = (2.0, 5.0)


class AsrError(RuntimeError):
    """识别失败，message 已人话化。"""


# ── 纯逻辑：请求与解析 ─────────────────────────────────────


def transcribe(
    url: str,
    model: str,
    api_key: str,
    wav_path: str,
    timeout: float = CHUNK_TIMEOUT_SEC,
) -> Dict[str, Any]:
    """上传一条 WAV，返回 {"text", "segments", "duration"}。

    segments 元素：{"start": float, "end": float, "text": str, "speaker": str}
    无说话人模型返回 text 且 segments 为 [{"start":0,"end":dur,"text":text,"speaker":""}]。
    """
    key = (api_key or "").strip()
    if not key:
        raise AsrError("未配置硅基流动 API Key，请到 设置 → 会议纪要配置 填写")

    payload = _post_multipart(url, model, key, wav_path, timeout)
    return parse_payload(payload)


def parse_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """把服务端 JSON 归一成统一结构。"""
    if not isinstance(payload, dict):
        raise AsrError("服务返回了无法解析的内容")

    err = payload.get("error")
    if err:
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise AsrError(f"服务返回错误：{msg or err}")
    if payload.get("code") and payload.get("message"):
        raise AsrError(f"服务返回错误：{payload.get('message')}")

    raw_segments = payload.get("segments")
    segments: List[Dict[str, Any]] = []
    if isinstance(raw_segments, list):
        for item in raw_segments:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            segments.append(
                {
                    "start": _to_float(item.get("start")),
                    "end": _to_float(item.get("end")),
                    "text": text,
                    "speaker": str(item.get("speaker") or ""),
                }
            )

    text = str(payload.get("text") or "").strip()
    duration = _to_float(payload.get("duration"))
    if not duration:
        usage = payload.get("usage") or {}
        if isinstance(usage, dict):
            duration = _to_float(usage.get("seconds"))

    if not segments and text:
        segments = [{"start": 0.0, "end": duration, "text": text, "speaker": ""}]

    if not segments:
        raise AsrError("未识别到语音内容（该片可能是静音）")

    return {"text": text or " ".join(s["text"] for s in segments), "segments": segments, "duration": duration}


def _to_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _post_multipart(
    url: str, model: str, key: str, wav_path: str, timeout: float
) -> Dict[str, Any]:
    boundary = f"----drifoxmeeting{uuid.uuid4().hex}"
    data = Path(wav_path).read_bytes()
    head = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n{model}\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"audio.wav\"\r\nContent-Type: audio/wav\r\n\r\n"
    ).encode("utf-8")
    body = head + data + f"\r\n--{boundary}--\r\n".encode("utf-8")

    request = Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as resp:
            raw = resp.read()
    except HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")[:200]
        except Exception:  # noqa: BLE001 — 读响应体失败不影响主错误
            pass
        if e.code in (401, 403):
            raise AsrError(f"API Key 无效或无权限（HTTP {e.code}）") from e
        if e.code == 429:
            raise AsrError("请求被限流（HTTP 429），稍后自动重试") from e
        logger.error(f"[meeting-notes] 识别 HTTP {e.code}: {detail}")
        raise AsrError(f"服务返回 HTTP {e.code}") from e
    except URLError as e:
        reason = str(getattr(e, "reason", e))
        if "timed out" in reason or "timeout" in reason:
            raise AsrError("识别超时（服务限流或网络慢）") from e
        raise AsrError(f"网络错误：{reason}") from e

    try:
        return json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise AsrError("服务返回了无法解析的内容") from e


def should_retry(err: AsrError) -> bool:
    """限流/超时/5xx 值得重试；Key 无效、模型不存在、无语音不重试。"""
    msg = str(err)
    if "API Key 无效" in msg:
        return False
    if "未识别到语音" in msg:
        return False
    return True


def transcribe_with_retry(
    url: str,
    model: str,
    api_key: str,
    wav_path: str,
    timeout: float = CHUNK_TIMEOUT_SEC,
    sleep=time.sleep,
) -> Dict[str, Any]:
    """带退避重试的上传。sleep 可注入，便于单测不真等。"""
    last: Optional[AsrError] = None
    for attempt in range(len(_RETRY_DELAYS) + 1):
        try:
            return transcribe(url, model, api_key, wav_path, timeout)
        except AsrError as e:
            last = e
            if attempt >= len(_RETRY_DELAYS) or not should_retry(e):
                break
            delay = _RETRY_DELAYS[attempt]
            logger.warning(f"[meeting-notes] 识别失败，{delay:.0f}s 后重试: {e}")
            sleep(delay)
    raise last or AsrError("识别失败")


# ── 顺序队列 worker ───────────────────────────────────────


class TranscribeQueue:
    """串行识别队列。submit() 线程安全，结果经 on_result/on_error 回调带外送。

    UI 侧只用它，不需要知道线程细节：

        q = TranscribeQueue(url, model, key)
        q.on_result = lambda task: ...
        q.on_error = lambda task, err: ...
        q.start()
        q.submit(wav_path, offset_sec)
        q.stop()
    """

    def __init__(self, url: str, model: str, api_key: str) -> None:
        self._url = url
        self._model = model
        self._key = api_key
        self._queue: "queue.Queue[Optional[dict]]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stopping = False
        self._busy = False

        # 回调在 worker 线程触发；UI 层负责转主线程
        self.on_result = None  # type: Any
        self.on_error = None  # type: Any
        self.on_idle = None  # type: Any

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stopping = False
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="meeting-notes-asr"
        )
        self._thread.start()

    def submit(
        self, wav_path: str, offset: float, timeout: float = CHUNK_TIMEOUT_SEC, meeting_id: str = ""
    ) -> None:
        """排队一片。meeting_id 随任务回传，防止录音结束后切会议时写错对象。"""
        self._queue.put(
            {"wav": wav_path, "offset": offset, "timeout": timeout, "meeting_id": meeting_id}
        )

    def pending(self) -> int:
        return self._queue.qsize()

    def is_busy(self) -> bool:
        """有任务在排队或正在识别。"""
        return self._busy or not self._queue.empty()

    def stop(self, wait: bool = False) -> None:
        self._stopping = True
        self._queue.put(None)
        if wait and self._thread:
            self._thread.join(timeout=5.0)

    def _run(self) -> None:
        while True:
            task = self._queue.get()
            if task is None or self._stopping:
                break
            try:
                self._busy = True
                result = transcribe_with_retry(
                    self._url,
                    self._model,
                    self._key,
                    task["wav"],
                    timeout=task["timeout"],
                )
                task["result"] = result
                if self.on_result:
                    self.on_result(task)
            except AsrError as e:
                task["error"] = str(e)
                logger.warning(f"[meeting-notes] 分片识别失败 offset={task['offset']:.0f}s: {e}")
                if self.on_error:
                    self.on_error(task, str(e))
            except Exception as e:  # noqa: BLE001 — 线程内异常不能静默
                logger.exception(f"[meeting-notes] 识别线程异常: {e}")
                if self.on_error:
                    self.on_error(task, f"{type(e).__name__}: {e}")
            finally:
                self._busy = False
                if self._queue.empty() and self.on_idle:
                    try:
                        self.on_idle()
                    except Exception:  # noqa: BLE001
                        pass


def to_absolute_segments(result: Dict[str, Any], offset: float) -> List[Dict[str, Any]]:
    """片内时间 → 会议绝对时间。"""
    out = []
    for seg in result.get("segments") or []:
        start = offset + float(seg.get("start") or 0.0)
        out.append(
            {
                "t": start,
                "speaker": str(seg.get("speaker") or ""),
                "text": str(seg.get("text") or "").strip(),
            }
        )
    return [s for s in out if s["text"]]
