# -*- coding: utf-8 -*-
"""Whisper（faster-whisper）离线识别后端：中文听写准确率远高于 SAPI5。

与 SAPI5 后端（recognizer.py）同级、可切换。链路：
MCI 录制的 16kHz/16bit/mono WAV → faster-whisper CPU(int8) → 固定 zh + VAD 裁剪
→ 中文文本（带标点）。Whisper 内部即按 16kHz 处理，录音格式无需改动。

设计约束（重要）：
- faster-whisper 是重依赖（ctranslate2 / av / tokenizers 等编译轮子），宿主环境
  不一定预装。因此**所有重 import 都延迟到 worker 线程内执行**；顶层只做轻量探测，
  探测失败由上层（ui/__init__.py）自动回退 SAPI5，插件永不因缺依赖而不可用。
- 依赖来源支持两处（按优先级）：
  1) 插件自带 deps/ 目录（tools/install_whisper.py 生成，desktop-automation 同款
     sys.path 注入模式，编译轮子与宿主 Python 版本匹配）；
  2) 宿主环境已 pip install faster-whisper。
- 模型首次使用自动从 HuggingFace 下载并缓存；默认 small（约 460MB，准确率/速度
  均衡），可用环境变量覆盖，见 README。

线程模型与 recognizer.py 一致：QThread + run()，信号回主线程。
"""

from __future__ import annotations

import importlib.util
import os
import sys

from loguru import logger
from PyQt5.QtCore import QThread, pyqtSignal

# ── 模型配置 ──────────────────────────────────────────────────────────────
# 默认模型档位：tiny/base/small/medium。small 在中文长句上字准确率约 90%+，
# CPU int8 实时率良好；medium 更准但下载约 1.5GB、CPU 明显变慢。
_DRIFOX_MODEL_ENV = "DRIFOX_VOICE_MODEL"  # 覆盖默认档位
_DRIFOX_DIR_ENV = "DRIFOX_VOICE_WHISPER_DIR"  # 覆盖模型缓存目录
_DEFAULT_MODEL = "small"

# HF 仓库：faster-whisper 官方 ctranslate2 权重（CPU 友好，无需 torch）
_HF_ORG = "Systran"
_MODEL_REPOS = {
    "tiny": f"{_HF_ORG}/faster-whisper-tiny",
    "base": f"{_HF_ORG}/faster-whisper-base",
    "small": f"{_HF_ORG}/faster-whisper-small",
    "medium": f"{_HF_ORG}/faster-whisper-medium",
}
# 仅供「首次下载」提示文案使用（各档位约略体积，MB）
_MODEL_HINT_MB = {"tiny": 75, "base": 145, "small": 460, "medium": 1500}

# CPU 推理：int8 量化，识别速度/内存更优
_DEVICE = "cpu"
_COMPUTE_TYPE = "int8"

# 固定中文，避免短句被误判为其它语言导致整句乱码
_LANGUAGE = "zh"
# 提示词引导简体中文与标点输出（对 whisper 输出格式有实际影响）
_INITIAL_PROMPT = "以下是普通话听写内容，请使用简体中文并加上正确的标点符号。"
# VAD 裁剪：去掉头尾静音与长停顿，提升准确率与速度
_VAD_MIN_SILENCE_MS = 300


def model_size() -> str:
    """当前生效的模型档位（环境变量可覆盖）。"""
    size = os.environ.get(_DRIFOX_MODEL_ENV, "").strip().lower()
    if size in _MODEL_REPOS:
        return size
    return _DEFAULT_MODEL


def model_repo() -> str:
    return _MODEL_REPOS[model_size()]


def model_dir() -> str:
    """模型缓存根目录（默认 ~/.cache/drifox-voice-input）。"""
    env = os.environ.get(_DRIFOX_DIR_ENV, "").strip()
    if env:
        return env
    return os.path.join(os.path.expanduser("~"), ".cache", "drifox-voice-input")


def model_hint_mb() -> int:
    return _MODEL_HINT_MB.get(model_size(), _MODEL_HINT_MB[_DEFAULT_MODEL])


def is_model_present() -> bool:
    """模型文件是否已下载到本地（递归找 ctranslate2 权重 model.bin）。"""
    root = model_dir()
    if not os.path.isdir(root):
        return False
    # 下载布局为 cache_dir/models--org--name/snapshots/<rev>/，递归找权重即可，
    # 对 faster-whisper 不同版本的目录实现免疫
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".locks")]
        if "model.bin" in filenames:
            return True
    return False


def _ensure_plugin_deps() -> None:
    """把插件自带 deps/ 目录前置进 sys.path（若存在）。幂等，仅路径操作。"""
    deps = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "deps")
    )
    if os.path.isdir(deps) and deps not in sys.path:
        sys.path.insert(0, deps)


_ensure_plugin_deps()


def faster_whisper_available() -> bool:
    """轻量探测 faster_whisper 是否可导入（不做重 import，避免卡 UI 线程）。"""
    # find_spec 只加载父包不执行 __init__；真正 import 在 worker 内再验证
    return importlib.util.find_spec("faster_whisper") is not None


def transcribe_wav(wav_path: str, on_status=None) -> str:
    """纯函数：Whisper 识别一条 WAV → 中文文本。无 Qt 依赖，便于单元测试。

    在 worker 线程内调用。首次使用会自动下载模型（阻塞数分钟级），
    通过 on_status(text) 回调上报阶段文案（如「下载模型中…」）。
    """
    if on_status:
        on_status("加载语音模型…")

    # 延迟 import：失败抛 ImportError，上层据此回退 SAPI5
    from faster_whisper import WhisperModel  # noqa: PLC0415

    size = model_size()
    repo = model_repo()
    root = model_dir()
    if not is_model_present():
        if on_status:
            on_status(f"首次使用：正在下载语音模型（约 {model_hint_mb()}MB）…")
        logger.info(f"[voice-input] 首次使用，下载 Whisper 模型 {repo}")

    model = WhisperModel(
        repo,
        device=_DEVICE,
        compute_type=_COMPUTE_TYPE,
        download_root=root,
    )

    if on_status:
        on_status("识别中…")
    segments, _info = model.transcribe(
        wav_path,
        language=_LANGUAGE,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": _VAD_MIN_SILENCE_MS},
        initial_prompt=_INITIAL_PROMPT,
        # 整段一次识别：关掉对前文的条件依赖，避免长音频出现重复/幻觉
        condition_on_previous_text=False,
    )
    text = "".join(seg.text for seg in segments).strip()
    logger.info(f"[voice-input] Whisper 识别完成: {len(text)} 字")
    return text


class WhisperRecognizeWorker(QThread):
    """Whisper 识别 worker。信号语义：
    - finished_ok(str)   识别成功；
    - unavailable(str)   依赖/模型不可用 → 上层应自动回退 SAPI5；
    - failed(str)        识别过程真实出错；
    - status(str)        阶段文案，用于浮窗标签实时反馈。
    """

    finished_ok = pyqtSignal(str)
    unavailable = pyqtSignal(str)
    failed = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, wav_path: str, parent=None) -> None:
        super().__init__(parent)
        self._wav_path = wav_path

    def run(self) -> None:
        try:
            # 顶层探测通过不代表真 import 成功（动态库加载等），这里再兜一层
            import faster_whisper  # noqa: PLC0415,F401

            del faster_whisper
        except Exception as e:  # noqa: BLE001 — 依赖缺失信息回主线程提示
            logger.warning(f"[voice-input] faster-whisper 不可用: {e}")
            self.unavailable.emit(_install_hint(e))
            return

        try:
            text = transcribe_wav(self._wav_path, on_status=self._emit_status)
            self.finished_ok.emit(text)
        except Exception as e:  # noqa: BLE001 — 模型下载/解码等全链路兜底
            logger.error(f"[voice-input] Whisper 识别失败: {e}")
            self.failed.emit(str(e))

    def _emit_status(self, text: str) -> None:
        self.status.emit(text)


def _install_hint(err: Exception) -> str:
    """不可用原因的简短人话（详情见 README「安装 faster-whisper」）。"""
    return (
        f"未安装 faster-whisper（{err}）。"
        "安装后自动启用高精度识别；当前已回退系统识别。"
    )
