# -*- coding: utf-8 -*-
"""SAPI5 zh-CN 听写识别：win32com 调 Windows 自带离线引擎，QThread 后台执行。

流程：zh-CN token 定位识别器 → SpFileStream 喂 WAV → dictation 语法收音
→ Recognition 事件收集分句 → EndStream 事件收尾 → 拼接文本回主线程。
COM 单元线程模型：worker 线程内 CoInitialize + 消息泵（PumpWaitingMessages），
否则连接点事件永不派发。
"""

from __future__ import annotations

import threading
import time

from loguru import logger
from PyQt5.QtCore import QThread, pyqtSignal

_RECOGNIZER_CATEGORY = r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Recognizers"
_LANG_ZH_PREFIX = "804"

# 识别总超时（秒）。60 秒音频 SAPI5 一般数秒识别完，超时兜底防线程悬挂
_RECOGNIZE_TIMEOUT_SEC = 30.0
_PUMP_INTERVAL_SEC = 0.05

# SpFileStream.Open 的 FileMode：SSFMOpenForRead
_SSFM_OPEN_FOR_READ = 0
# Dictation 状态：SGDSActive
_SGDS_ACTIVE = 1


def find_zh_recognizer_id() -> str | None:
    """检测系统是否装有中文识别引擎，返回 token id（无则 None）。轻量，可在主线程调。"""
    import win32com.client

    cat = win32com.client.Dispatch("SAPI.SpObjectTokenCategory")
    cat.SetId(_RECOGNIZER_CATEGORY, False)
    tokens = cat.EnumerateTokens()
    if tokens is None:
        return None
    for i in range(tokens.Count):
        token = tokens.Item(i)
        try:
            lang = token.GetAttribute("Language")
        except Exception:  # noqa: BLE001 — 个别 token 无 Language 属性，跳过
            continue
        if lang.split(";")[0].strip() == _LANG_ZH_PREFIX:
            return token.Id
    return None


class RecognizeWorker(QThread):
    """识别一条 WAV → 文本。finished_ok / failed 信号回主线程。"""

    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, wav_path: str, token_id: str, parent=None) -> None:
        super().__init__(parent)
        self._wav_path = wav_path
        self._token_id = token_id

    def run(self) -> None:
        import pythoncom

        pythoncom.CoInitialize()
        try:
            text = self._recognize()
            self.finished_ok.emit(text)
        except Exception as e:  # noqa: BLE001 — 全链路兜底，错误回主线程提示
            logger.error(f"[voice-input] 识别失败: {e}")
            self.failed.emit(str(e))
        finally:
            pythoncom.CoUninitialize()

    def _recognize(self) -> str:
        import pythoncom
        import win32com.client

        # 定位 zh-CN 识别器 token
        recognizer = win32com.client.Dispatch("SAPI.SpInprocRecognizer")
        token = win32com.client.Dispatch("SAPI.SpObjectToken")
        token.SetId(self._token_id, "", False)
        recognizer.Recognizer = token

        # WAV 文件作音频输入
        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        stream.Open(self._wav_path, _SSFM_OPEN_FOR_READ, False)
        recognizer.AudioInputStream = stream

        results: list[str] = []
        done = threading.Event()

        class _RecoEvents:
            """_ISpeechRecoContextEvents 事件接收器（win32com 按方法名匹配）。"""

            def OnRecognition(
                self, StreamNumber, StreamPosition, RecognitionType, Result
            ):  # noqa: N802,N803
                try:
                    # 事件参数是裸 PyIDispatch，必须先包装；且 gen_py 静态包装缺
                    # PhraseInfo 属性时降级动态迟到绑定（两种均验证可用）
                    try:
                        result = win32com.client.Dispatch(Result)
                    except Exception:  # noqa: BLE001
                        result = win32com.client.dynamic.Dispatch(Result)
                    text = result.PhraseInfo.GetText()
                except Exception:  # noqa: BLE001 — 单句取文本失败不影响整体
                    return
                if text:
                    results.append(text)
                    logger.debug(f"[voice-input] 分句: {text}")

            def OnEndStream(
                self, StreamNumber=0, StreamPosition=0, StreamReleased=False
            ):  # noqa: N802,N803
                done.set()

            # SAPI 5.4 类型库事件派发带 3 个参数（含 StreamReleased），默认值兼容旧签名

        context = recognizer.CreateRecoContext()
        # sink 必须保活到识别结束，否则事件断链
        sink = win32com.client.WithEvents(context, _RecoEvents)

        grammar = context.CreateGrammar()
        # SAPI 5.4 类型库把听写暴露为方法（DictationLoad/DictationSetState），
        # 无高层 ISpeechDictation 属性（gen_py 包装已核实）
        grammar.DictationLoad()
        grammar.DictationSetState(_SGDS_ACTIVE)

        # STA 事件派发依赖消息泵：循环 PumpWaitingMessages 直到 EndStream 或超时
        deadline = time.monotonic() + _RECOGNIZE_TIMEOUT_SEC
        try:
            while not done.wait(_PUMP_INTERVAL_SEC):
                pythoncom.PumpWaitingMessages()
                if time.monotonic() > deadline:
                    logger.warning("[voice-input] 识别超时，返回已收集文本")
                    break
        finally:
            try:
                grammar.DictationSetState(0)
                stream.Close()
            except Exception:  # noqa: BLE001 — 收尾清理失败不影响结果
                pass
        del sink

        text = "".join(results).strip()
        logger.info(f"[voice-input] 识别完成: {len(text)} 字")
        return text
