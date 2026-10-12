# -*- coding: utf-8 -*-
"""voice-reply 在线 TTS worker：OpenAI 兼容 /audio/speech 接口合成 + 本地播放。

设计约束（对齐 voice-input/cloud_recognizer.py）：
- 纯标准库 urllib：宿主为 PyInstaller 打包，未收集 requests/urllib3，零第三方依赖。
- API Key / URL / 模型 / 音色由调用方（ui/__init__.py）读插件配置后传入，
  本模块不碰存储。
- 线程模型：QThread + run()，信号回主线程；synthesize_wav 纯函数便于单测。
- 音频固定请求 wav（RIFF），Windows winsound / macOS afplay 均可零依赖播放；
  响应非 RIFF 头时按 JSON 错误解析并人话化。
- 播放超时：50 秒兜底（文本上限 500 字，正常合成 + 播放远小于此）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from loguru import logger
from PyQt5.QtCore import QThread, pyqtSignal

# 合成请求总超时（秒）。500 字合成通常 2~5 秒返回，超时兜防线程悬挂
_TIMEOUT_SEC = 50.0


def synthesize_wav(url: str, model: str, voice: str, api_key: str, text: str) -> bytes:
    """纯函数：调 OpenAI 兼容 /audio/speech → wav 字节。无 Qt 依赖，便于单测。

    在 worker 线程内调用。失败抛异常（消息已人话化），上层回主线程提示。
    """
    key = (api_key or "").strip()
    if not key:
        raise ValueError("API Key 为空，请到 设置 → 语音播报配置 填写")

    body = json.dumps(
        {"model": model, "input": text, "voice": voice, "response_format": "wav"}
    ).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=_TIMEOUT_SEC) as resp:
            data = resp.read()
    except HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")[:300]
        except Exception:  # noqa: BLE001 — 读响应体失败不影响主错误
            pass
        msg = _extract_error_message(detail)
        logger.error(f"[voice-reply] TTS HTTP {e.code}: {detail[:200]}")
        if msg:
            raise RuntimeError(f"服务返回 HTTP {e.code}：{msg}") from e
        raise RuntimeError(f"服务返回 HTTP {e.code}") from e
    except URLError as e:
        reason = str(getattr(e, "reason", e))
        if "timed out" in reason:
            raise RuntimeError("服务响应超时（可能限流或网络不通）") from e
        logger.error(f"[voice-reply] TTS 网络错误: {reason}")
        raise RuntimeError(f"网络错误：{reason}") from e

    # 非 RIFF 头：多半是 JSON 错误响应（key 无效 / 模型名错 / 余额不足）
    if data[:4] != b"RIFF":
        msg = _extract_error_message(data.decode("utf-8", "ignore"))
        logger.warning(f"[voice-reply] TTS 未返回音频: {str(data[:300])}")
        raise RuntimeError(msg or "服务未返回音频（检查 URL / 模型 / 音色配置）")
    logger.info(f"[voice-reply] TTS 合成完成: {len(data)} bytes wav")
    return data


def _extract_error_message(raw: str) -> str:
    """从 JSON 错误响应提取人话消息（OpenAI 兼容 error.message / 通用 message）。"""
    if not raw.strip():
        return ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    err = payload.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err.get("code") or "")
    if err:
        return str(err)
    return str(payload.get("message") or "")


def play_wav(path: str, proc_slot: dict) -> None:
    """阻塞播放一个 wav 文件（在 worker 线程内调用）。

    proc_slot["proc"]：macOS afplay 子进程句柄，供主线程 stop() 终止；
    Windows 走 winsound 全局播放，stop 侧用 PlaySound(None, SND_PURGE) 停止。
    """
    if sys.platform == "darwin":
        proc = subprocess.Popen(["afplay", path])
        proc_slot["proc"] = proc
        proc.wait()
        return
    # Windows：SND_SYNC 在 worker 线程内阻塞播完；主线程 PURGE 可打断
    import winsound

    proc_slot["winsound"] = True
    winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_SYNC)


class ApiTtsWorker(QThread):
    """在线合成 + 播放 worker。信号语义：

    - finished_ok()  播放自然结束（被打断不发射）；
    - failed(str)    合成或播放出错（网络/超时/HTTP/key 无效）；
    - status(str)    阶段文案，主线程可提示。
    """

    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(
        self, url: str, model: str, voice: str, api_key: str, text: str, parent=None
    ) -> None:
        super().__init__(parent)
        self._url = url
        self._model = model
        self._voice = voice
        self._api_key = api_key
        self._text = text
        self._stop_requested = False
        self._proc_slot: dict = {}

    def stop(self) -> None:
        """主线程调用：打断合成（标志位）+ 打断播放（PURGE / 终止子进程）。"""
        self._stop_requested = True
        slot = self._proc_slot
        if slot.get("proc") is not None:
            try:
                slot["proc"].terminate()
            except Exception:  # noqa: BLE001 — 进程已退出等场景忽略
                pass
        if slot.get("winsound") and sys.platform == "win32":
            try:
                import winsound

                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception as e:  # noqa: BLE001 — 停止失败不影响主流程
                logger.warning(f"[voice-reply] 打断播放失败: {e}")

    @property
    def stop_requested(self) -> bool:
        return self._stop_requested

    def run(self) -> None:
        self.status.emit("正在合成语音…")
        try:
            data = synthesize_wav(
                self._url, self._model, self._voice, self._api_key, self._text
            )
        except Exception as e:  # noqa: BLE001 — 全链路兜底，错误回主线程提示
            logger.error(f"[voice-reply] 在线合成失败: {e}")
            if not self._stop_requested:
                self.failed.emit(str(e))
            return
        if self._stop_requested:
            return

        # wav 落临时文件再播（winsound/afplay 都吃文件路径）
        self.status.emit("播放中…")
        fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="voice_reply_")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            play_wav(wav_path, self._proc_slot)
        except Exception as e:  # noqa: BLE001 — 播放器缺失/设备占用等
            logger.error(f"[voice-reply] 播放失败: {e}")
            if not self._stop_requested:
                self.failed.emit(f"播放失败：{e}")
            return
        finally:
            try:
                os.remove(wav_path)
            except OSError:  # %TEMP% 系统兜底清理
                pass
        if not self._stop_requested:
            self.finished_ok.emit()
