# -*- coding: utf-8 -*-
"""会议数据模型与本地持久化（一场会议一个文件夹）。

布局::

    <app_data>/plugin_data/meeting-notes/
    ├── 产品评审会/
    │   ├── meeting.json     转写 + 纪要 + 说话人命名
    │   └── audio.wav        会议录音（16kHz/16bit/单声道）
    └── 11月11日 10:30 会议/
        ├── meeting.json
        └── audio.wav

为什么按会议文件夹存：用户能直接在文件管理器里按名字找会议、拷走、备份；
以前的 meetings/<id>.json + audio/<id>.wav 只能靠 id 认领，对人是不可读的。

目录名 = 会议名（非法字符净化）。重名时加 ` (2)` 序号；会议改名时目录跟着改。
会议 id 仍是内部主键（存在 meeting.json 里），目录名可变。

旧结构（meetings/*.json + audio/*.wav）在首次访问时自动迁移，迁移失败不阻塞。
"""

from __future__ import annotations

import json
import os
import shutil
import struct
import time
import uuid
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

PLUGIN_NAME = "meeting-notes"

# Windows 文件名非法字符（含控制符），及结尾不允许的空格/点
_ILLEGAL_FILENAME_CHARS = '\\/:*?"<>|'
_MAX_FOLDER_LEN = 60

_MEETING_FILE = "meeting.json"
_AUDIO_FILE = "audio.wav"

_migrated = False
# 目录扫描缓存：click→load、列表刷新会在同一操作里多次需要 id→目录映射，
# 每次都全盘解析一遍 meeting.json 代价太高。2 秒 TTL 足够。
_index_cache: Dict[str, Any] = {"ts": 0.0, "data": {}}
_INDEX_TTL = 2.0


# ── 目录 ────────────────────────────────────────────────────


def data_root() -> Path:
    """插件数据根目录（宿主未提供时回退 ~/.drifox/plugin_data/meeting-notes）。"""
    global _migrated
    base: Optional[Path] = None
    try:
        from app.utils.utils import get_app_data_dir

        base = Path(get_app_data_dir())
    except Exception:  # noqa: BLE001 — 脱离宿主（单测/脚本）时走回退
        base = Path(os.path.expanduser("~")) / ".drifox"
    root = base / "plugin_data" / PLUGIN_NAME
    root.mkdir(parents=True, exist_ok=True)
    if not _migrated:
        _migrated = True
        try:
            _migrate_legacy(root)
        except Exception as e:  # noqa: BLE001 — 迁移失败不阻塞主流程
            logger.warning(f"[meeting-notes] 旧数据迁移失败（不影响新会议）: {e}")
    return root


def safe_filename(name: str, max_len: int = _MAX_FOLDER_LEN) -> str:
    """会议名 → 可用作文件夹名的串（冒号等非法字符换下划线）。"""
    text = "".join(
        "_" if c in _ILLEGAL_FILENAME_CHARS or ord(c) < 32 else c for c in (name or "")
    )
    text = text.strip().strip(".").rstrip(" .")
    text = text[:max_len].rstrip(" .")
    return text or "未命名会议"


def _folder_owner(folder: Path) -> str:
    """目录属于哪场会议（读 meeting.json 的 id）；不是会议目录返回空串。"""
    try:
        data = json.loads((folder / _MEETING_FILE).read_text(encoding="utf-8"))
        return str(data.get("id") or "")
    except Exception:  # noqa: BLE001 — 缺文件/坏文件都当他人的
        return ""


def _index(force: bool = False) -> Dict[str, Path]:
    """会议 id → 会议目录（带 2 秒缓存）。"""
    now = time.time()
    if not force and (now - _index_cache["ts"]) < _INDEX_TTL:
        return _index_cache["data"]

    out: Dict[str, Path] = {}
    root = data_root()
    try:
        entries = list(root.iterdir())
    except OSError as e:
        logger.warning(f"[meeting-notes] 扫描会议目录失败: {e}")
        return out
    for d in entries:
        if not d.is_dir() or d.name.startswith("."):
            continue
        owner = _folder_owner(d)
        if owner:
            out[owner] = d
    _index_cache["ts"] = now
    _index_cache["data"] = out
    return out


def _claim_folder(root: Path, desired: str, meeting_id: str) -> Path:
    """给会议占一个以会议名命名的目录（重名加序号）。"""
    candidate = desired
    index = 2
    while True:
        path = root / candidate
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            return path
        if _folder_owner(path) == meeting_id:
            return path
        candidate = f"{desired} ({index})"
        index += 1


def _rename_folder(current: Path, desired: str, meeting_id: str) -> Path:
    """会议改名后把目录跟着改；目标被别的会议占了就加序号。"""
    if current.name == desired:
        return current
    root = current.parent
    target = root / desired
    if target.exists() and _folder_owner(target) != meeting_id:
        index = 2
        while (root / f"{desired} ({index})").exists():
            index += 1
        target = root / f"{desired} ({index})"
    try:
        current.rename(target)
        return target
    except OSError as e:  # noqa: BLE001 — 改名失败（文件被占用）沿用旧目录
        logger.warning(f"[meeting-notes] 会议目录改名失败 {current.name} → {desired}: {e}")
        return current


def _migrate_legacy(root: Path) -> None:
    """旧结构（meetings/<id>.json + audio/<id>.wav）→ 会议文件夹。"""
    legacy_dir = root / "meetings"
    legacy_audio = root / "audio"
    if not legacy_dir.exists():
        return
    moved = 0
    for json_path in list(legacy_dir.glob("*.json")):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            m = Meeting.from_dict(data)
            if not m.id:
                continue
            folder = _claim_folder(root, safe_filename(m.display_title()), m.id)
            old_audio = legacy_audio / f"{m.id}.wav"
            if old_audio.exists():
                try:
                    shutil.move(str(old_audio), str(folder / _AUDIO_FILE))
                except OSError as e:  # noqa: BLE001 — 音频丢了不影响文字
                    logger.warning(f"[meeting-notes] 迁移录音失败 {old_audio}: {e}")
            m.folder = folder.name
            (folder / _MEETING_FILE).write_text(
                json.dumps(m.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8"
            )
            json_path.unlink()
            moved += 1
        except Exception as e:  # noqa: BLE001 — 单个坏文件跳过
            logger.warning(f"[meeting-notes] 迁移会议失败 {json_path.name}: {e}")
    for d in (legacy_dir, legacy_audio):
        try:
            if d.exists() and not any(d.iterdir()):
                d.rmdir()
        except OSError:
            pass
    if moved:
        logger.info(f"[meeting-notes] 已把 {moved} 场旧会议迁移为独立文件夹")
    _index_cache["ts"] = 0.0


# ── 数据模型 ────────────────────────────────────────────────


@dataclass
class Segment:
    """一条转写片段。t = 相对会议开始的秒数。"""

    t: float
    speaker: str
    text: str

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Segment":
        return Segment(
            t=float(d.get("t") or 0.0),
            speaker=str(d.get("speaker") or ""),
            text=str(d.get("text") or ""),
        )


@dataclass
class Meeting:
    id: str
    title: str
    created_at: float
    duration_sec: float = 0.0
    status: str = "recording"  # draft | recording | done
    model: str = ""
    segments: List[Segment] = field(default_factory=list)
    speaker_names: Dict[str, str] = field(default_factory=dict)
    summary_md: str = ""
    summary_at: float = 0.0
    # 会议目录名（= 会议名，重名带序号）；空表示还没落盘
    folder: str = ""
    # 已做精转的音频时长（秒）：增量精转从这里往后接
    refined_until: float = 0.0

    @property
    def refined(self) -> bool:
        return bool(self.duration_sec) and self.refined_until >= (self.duration_sec - 2)

    def display_title(self) -> str:
        return self.title or time.strftime("%m-%d %H:%M", time.localtime(self.created_at))

    def speaker_label(self, spk: str) -> str:
        if not spk:
            return ""
        return self.speaker_names.get(spk) or f"说话人 {spk}"

    def transcript_lines(self) -> List[str]:
        out: List[str] = []
        for seg in self.segments:
            text = (seg.text or "").strip()
            if not text:
                continue
            label = self.speaker_label(seg.speaker) or "发言"
            out.append(f"[{_fmt_clock(seg.t)}] {label}: {text}")
        return out

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["segments"] = [asdict(s) for s in self.segments]
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Meeting":
        return Meeting(
            id=str(d.get("id") or ""),
            title=str(d.get("title") or ""),
            created_at=float(d.get("created_at") or 0.0),
            duration_sec=float(d.get("duration_sec") or 0.0),
            status=str(d.get("status") or "done"),
            model=str(d.get("model") or ""),
            segments=[Segment.from_dict(x) for x in (d.get("segments") or [])],
            speaker_names={str(k): str(v) for k, v in (d.get("speaker_names") or {}).items()},
            summary_md=str(d.get("summary_md") or ""),
            summary_at=float(d.get("summary_at") or 0.0),
            folder=str(d.get("folder") or ""),
            refined_until=float(d.get("refined_until") or 0.0),
        )


def _fmt_clock(seconds: float) -> str:
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


# ── 读写 ────────────────────────────────────────────────────


def new_meeting(model: str) -> Meeting:
    now = time.time()
    mid = time.strftime("%Y%m%d-%H%M%S", time.localtime(now)) + "-" + uuid.uuid4().hex[:4]
    return Meeting(
        id=mid,
        title=time.strftime("%m月%d日 %H:%M 会议", time.localtime(now)),
        created_at=now,
        model=model,
    )


def save(m: Meeting) -> None:
    """写入会议文件夹。首次落盘分配目录；会议改名时目录跟着改。"""
    root = data_root()
    desired = safe_filename(m.display_title())
    folder: Optional[Path] = None
    if m.folder:
        candidate = root / m.folder
        if candidate.is_dir() and _folder_owner(candidate) == m.id:
            folder = _rename_folder(candidate, desired, m.id)
    if folder is None:
        folder = _claim_folder(root, desired, m.id)

    m.folder = folder.name
    target = folder / _MEETING_FILE
    # 唯一临时名：录音线程与精转线程可能同时落盘，共用 .tmp 会互相截断
    tmp = folder / f".{_MEETING_FILE}.{uuid.uuid4().hex[:8]}.tmp"
    tmp.write_text(json.dumps(m.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, target)
    _index_cache["ts"] = 0.0  # 目录可能改名了，下次重新扫描


def load(mid: str) -> Optional[Meeting]:
    folder = _index().get(mid)
    if folder is None:
        return None
    try:
        data = json.loads((folder / _MEETING_FILE).read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 — 单个坏文件不影响列表
        logger.warning(f"[meeting-notes] 会议文件损坏 {folder.name}: {e}")
        return None
    m = Meeting.from_dict(data)
    m.folder = folder.name
    return m


def list_meetings() -> List[Meeting]:
    """按创建时间倒序。"""
    items: List[Meeting] = []
    for folder in _index().values():
        try:
            data = json.loads((folder / _MEETING_FILE).read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[meeting-notes] 跳过损坏会议 {folder.name}: {e}")
            continue
        m = Meeting.from_dict(data)
        if m.id:
            m.folder = folder.name
            items.append(m)
    items.sort(key=lambda x: x.created_at, reverse=True)
    return items


def delete(mid: str) -> None:
    folder = _index().get(mid)
    if folder is None:
        return
    try:
        shutil.rmtree(folder)
    except OSError as e:  # noqa: BLE001
        logger.warning(f"[meeting-notes] 删除会议目录失败 {folder}: {e}")
    _index_cache["ts"] = 0.0


def meeting_folder(m: Meeting) -> Path:
    """会议的目录（未落盘的会议返回根目录，避免调用方拿到空路径）。"""
    if m.folder:
        return data_root() / m.folder
    return data_root()


def audio_path_for(m: Meeting) -> Path:
    return meeting_folder(m) / _AUDIO_FILE


def export_markdown(m: Meeting) -> str:
    lines = [f"# {m.display_title()}", ""]
    meta = [
        f"时间：{time.strftime('%Y-%m-%d %H:%M', time.localtime(m.created_at))}",
        f"时长：{_fmt_clock(m.duration_sec)}",
    ]
    if m.model:
        meta.append(f"识别模型：{m.model}")
    lines.append(" · ".join(meta))
    lines.append("")
    if m.summary_md.strip():
        lines.append(m.summary_md.strip())
        lines.append("")
    lines.append("## 完整转写")
    lines.append("")
    lines.extend(m.transcript_lines())
    lines.append("")
    return "\n".join(lines)


# ── 录音拼接 ────────────────────────────────────────────────


class WavJoiner:
    """把分片 WAV 依次追加到一个主 WAV。片间参数不一致的片被跳过（记日志）。

    第一片的参数即主文件参数。所有操作都是「打开-追加-关闭」，进程崩溃最多丢
    最后一片，不会毁掉已录部分。append=True 用于「继续录一场已有录音的会议」。

    ⚠ 不用 wave.open(path, "ab")：CPython 的 wave 只接受 r/w 模式（3.14 起明确
    报错），追加必须自己维护 RIFF 头里的两个长度字段。
    """

    def __init__(self, target: Path, append: bool = False) -> None:
        self.target = target
        self._params: Optional[tuple] = None
        if append and target.exists() and target.stat().st_size > 44:
            try:
                with wave.open(str(target), "rb") as wf:
                    self._params = (
                        wf.getnchannels(),
                        wf.getsampwidth(),
                        wf.getframerate(),
                    )
            except Exception as e:  # noqa: BLE001 — 旧文件坏了就当新文件写
                logger.warning(f"[meeting-notes] 读取已有录音参数失败，按新文件处理: {e}")
                self._params = None

    @property
    def params(self) -> Optional[tuple]:
        return self._params

    def append(self, chunk_path: Path) -> float:
        """追加一片，返回该片时长（秒）。失败返回 0.0。"""
        if not chunk_path.exists():
            return 0.0
        try:
            with wave.open(str(chunk_path), "rb") as src:
                params = (
                    src.getnchannels(),
                    src.getsampwidth(),
                    src.getframerate(),
                )
                frames = src.readframes(src.getnframes())
                duration = src.getnframes() / float(src.getframerate() or 1)
        except Exception as e:  # noqa: BLE001 — 坏片不阻断整场录音
            logger.warning(f"[meeting-notes] 读取音频片失败 {chunk_path.name}: {e}")
            return 0.0

        if not frames:
            return 0.0

        try:
            if self._params is None:
                self._params = params
                self._write_new(frames, params)
            elif params != self._params:
                # 采样参数变了（设备降级）。整片丢弃：混采样率拼接会得到变速音频，
                # 对精转是灾难性的，宁可少这一片。
                logger.warning(
                    f"[meeting-notes] 音频片参数与主文件不一致，已跳过 "
                    f"{chunk_path.name}: {params} != {self._params}"
                )
                return 0.0
            else:
                self._append_frames(frames)
        except Exception as e:  # noqa: BLE001 — 磁盘错误等，保住已录部分
            logger.error(f"[meeting-notes] 追加音频失败（保留已录部分）: {e}")
            return 0.0
        return duration

    def _write_new(self, frames: bytes, params: tuple) -> None:
        """首片：写标准 44 字节头 + 帧数据。"""
        nch, width, rate = params
        block_align = nch * width
        data_len = len(frames)
        header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF",
            36 + data_len,
            b"WAVE",
            b"fmt ",
            16,
            1,
            nch,
            rate,
            rate * block_align,
            block_align,
            width * 8,
            b"data",
            data_len,
        )
        self.target.write_bytes(header + frames)

    def _append_frames(self, frames: bytes) -> None:
        """就地追加：改 RIFF/data 两个长度字段，帧数据写到文件尾。"""
        with open(self.target, "r+b") as f:
            data_pos, data_size = _locate_data_chunk(f)
            f.seek(data_pos + data_size)
            f.write(frames)
            new_size = data_size + len(frames)
            f.seek(4)
            f.write(struct.pack("<I", 36 + new_size))
            f.seek(data_pos - 4)
            f.write(struct.pack("<I", new_size))

    def duration_sec(self) -> float:
        if not self.target.exists() or self._params is None:
            return 0.0
        try:
            with open(self.target, "r+b") as f:
                _data_pos, data_size = _locate_data_chunk(f)
            nch, width, rate = self._params
            return data_size / float((nch * width) or 1) / float(rate or 16000)
        except Exception:  # noqa: BLE001 — 录音中文件可能正被写
            return 0.0


def _locate_data_chunk(f) -> tuple:
    """解析 RIFF，返回 (帧数据起始偏移, 数据字节数)。"""
    f.seek(0)
    head = f.read(12)
    if len(head) < 12 or head[:4] != b"RIFF" or head[8:12] != b"WAVE":
        raise ValueError("不是合法的 WAV 文件")
    while True:
        chunk = f.read(8)
        if len(chunk) < 8:
            raise ValueError("WAV 缺少 data 块")
        cid, size = struct.unpack("<4sI", chunk)
        if cid == b"data":
            return f.tell(), size
        f.seek(size + (size & 1), 1)


def extract_wav_range(src: Path, out: Path, start_sec: float, end_sec: float) -> Optional[Path]:
    """从主录音里剪出 [start_sec, end_sec) 一段。用于增量精转。"""
    if not src.exists():
        return None
    with wave.open(str(src), "rb") as f:
        params = (f.getnchannels(), f.getsampwidth(), f.getframerate())
        rate = params[2] or 16000
        start = max(0, int(start_sec * rate))
        end = int(end_sec * rate)
        if end <= start:
            return None
        f.setpos(min(start, f.getnframes()))
        frames = f.readframes(end - start)
    if not frames:
        return None
    with wave.open(str(out), "wb") as dst:
        dst.setnchannels(params[0])
        dst.setsampwidth(params[1])
        dst.setframerate(params[2])
        dst.writeframes(frames)
    return out


def cleanup_temp(paths: List[Path]) -> None:
    for p in paths:
        try:
            if p.exists():
                p.unlink()
        except OSError:
            pass


def remove_audio(m: Meeting) -> None:
    p = audio_path_for(m)
    try:
        if p.exists():
            p.unlink()
    except OSError as e:  # noqa: BLE001
        logger.warning(f"[meeting-notes] 删除录音失败 {p}: {e}")
