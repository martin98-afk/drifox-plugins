# -*- coding: utf-8 -*-
"""图库存储 — JSON 持久化、图片落盘、CRUD。

数据结构与 DSH 版保持一致（stickers.json / preferences.json），
便于两边对照，也方便用户手工编辑。
"""
from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 单图 8MB 上限

STICKERS_FILE = "stickers.json"
PREFS_FILE = "preferences.json"
CONFIG_FILE = "config.json"
STICKERS_DIR = "stickers"


# ═══════════════ 路径 ═══════════════

def default_data_dir() -> Path:
    """DriFox 插件数据根。

    skills/tools 是独立子进程，拿不到宿主 caps_for，按平台约定推断：
    macOS ~/Library/Application Support/Drifox/.drifox/plugin_data/biaoqingbao
    Windows %APPDATA%/Drifox/.drifox/plugin_data/biaoqingbao
    Linux ~/.config/Drifox/.drifox/plugin_data/biaoqingbao
    环境变量 BIAOQINGBAO_DATA_DIR 可覆盖。
    """
    override = os.environ.get("BIAOQINGBAO_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    override = os.environ.get("DRIFOX_APP_DATA", "").strip()
    if override:
        return Path(override).expanduser().resolve() / "plugin_data" / "biaoqingbao"
    import sys

    if sys.platform == "darwin":
        base = Path("~/Library/Application Support/Drifox/.drifox").expanduser()
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", "~")) / "Drifox" / ".drifox"
    else:
        base = Path("~/.config/Drifox/.drifox").expanduser()
    return base / "plugin_data" / "biaoqingbao"


def resolve_data_dir(tool_ctx: dict | None = None) -> Path:
    """优先用宿主注入的 app_data_dir，退回平台约定。"""
    app_data = (tool_ctx or {}).get("env", {}).get("app_data_dir")
    if app_data:
        out = Path(app_data).resolve() / "plugin_data" / "biaoqingbao"
    else:
        out = default_data_dir()
    out.mkdir(parents=True, exist_ok=True)
    (out / STICKERS_DIR).mkdir(parents=True, exist_ok=True)
    return out


# ═══════════════ JSON 读写 ═══════════════

def _read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def _write_json(path: Path, data: Any) -> None:
    """原子写：先写临时文件再替换，避免半截文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_stickers(data_dir: Path) -> list[dict]:
    raw = _read_json(data_dir / STICKERS_FILE, [])
    return raw if isinstance(raw, list) else []


def save_stickers(data_dir: Path, stickers: list[dict]) -> None:
    _write_json(data_dir / STICKERS_FILE, stickers)


def load_prefs(data_dir: Path) -> dict:
    raw = _read_json(data_dir / PREFS_FILE, None)
    if not isinstance(raw, dict):
        return {"version": 1, "users": {"default": {"mappings": []}}}
    users = raw.setdefault("users", {})
    default = users.setdefault("default", {"mappings": []})
    if not isinstance(default.get("mappings"), list):
        default["mappings"] = []
    return raw


def save_prefs(data_dir: Path, prefs: dict) -> None:
    _write_json(data_dir / PREFS_FILE, prefs)


def load_config(data_dir: Path) -> dict:
    raw = _read_json(data_dir / CONFIG_FILE, {})
    return raw if isinstance(raw, dict) else {}


def save_config(data_dir: Path, cfg: dict) -> None:
    _write_json(data_dir / CONFIG_FILE, cfg)


# ═══════════════ 图片路径 ═══════════════

def sticker_abs_path(data_dir: Path, sticker: dict) -> Path | None:
    """把 sticker.file（相对数据目录）解析成绝对路径，文件不存在返回 None。"""
    rel = (sticker or {}).get("file") or ""
    if not rel:
        return None
    p = Path(rel)
    if not p.is_absolute():
        p = data_dir / rel
    p = p.expanduser().resolve()
    return p if p.is_file() else None


def new_id() -> str:
    return "stk_" + uuid.uuid4().hex[:12]


# ═══════════════ 导入 ═══════════════

def import_image(
    data_dir: Path,
    src: Path,
    *,
    description: str = "",
    tags: dict | None = None,
    extra: dict | None = None,
) -> dict:
    """把一张本地图片复制进图库并登记，返回新 sticker 记录。

    extra 会合并进记录（如 source 标记，用于批量导入去重）。
    """
    src = Path(src).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"图片不存在: {src}")
    if src.suffix.lower() not in IMAGE_EXTS:
        raise ValueError(f"不支持的图片格式: {src.suffix}")
    size = src.stat().st_size
    if size > MAX_IMAGE_BYTES:
        raise ValueError(f"图片超过 {MAX_IMAGE_BYTES // 1024 // 1024}MB 上限: {src.name}")

    sid = new_id()
    dest_name = f"{sid}{src.suffix.lower()}"
    dest = data_dir / STICKERS_DIR / dest_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)

    sticker = {
        "id": sid,
        "file": f"{STICKERS_DIR}/{dest_name}",
        "description": description or src.stem,
        "tags": {
            "emotion": list((tags or {}).get("emotion") or []),
            "scene": list((tags or {}).get("scene") or []),
            "keywords": list((tags or {}).get("keywords") or []),
        },
        "mediaType": _mime_of(src.suffix),
        "size": size,
        "created_at": time.time(),
    }
    if extra:
        sticker.update(extra)
    stickers = load_stickers(data_dir)
    stickers.append(sticker)
    save_stickers(data_dir, stickers)
    return sticker


def import_starter_pack(data_dir: Path, pack_dir: Path) -> dict:
    """批量导入内置图库（按 manifest 的分类与关键词打标）。

    已导入过的（按 source 标记）跳过，可重复执行。
    """
    import json

    manifest_path = pack_dir / "manifest.json"
    categories: dict = {}
    if manifest_path.is_file():
        try:
            categories = (json.loads(manifest_path.read_text(encoding="utf-8-sig"))
                          .get("categories") or {})
        except (OSError, ValueError):
            categories = {}

    existing_sources = {s.get("source") for s in load_stickers(data_dir) if s.get("source")}
    added = skipped = 0
    memes_root = pack_dir / "memes"
    if not memes_root.is_dir():
        return {"added": 0, "skipped": 0, "error": f"图库目录不存在: {memes_root}"}

    for tag_dir in sorted(p for p in memes_root.iterdir() if p.is_dir()):
        tag = tag_dir.name
        meta = categories.get(tag) or {}
        keywords = [k for k in str(meta.get("keywords") or "").split() if k][:30]
        images = sorted(
            p for p in tag_dir.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS
        )
        for idx, img in enumerate(images, 1):
            source = f"starter:{tag}/{img.name}"
            if source in existing_sources:
                skipped += 1
                continue
            # 描述保持短（会显示在聊天里），语义靠 keywords 承担
            desc = f"{tag} {idx}"
            try:
                import_image(
                    data_dir, img,
                    description=desc,
                    tags={"emotion": [tag], "keywords": keywords},
                    extra={"source": source, "license": "CC-BY-SA-4.0"},
                )
                added += 1
            except (FileNotFoundError, ValueError):
                skipped += 1
    return {"added": added, "skipped": skipped}


STARTER_MARKER = ".starter_imported"


def ensure_starter_imported(data_dir: Path, pack_dir: Path) -> dict:
    """首次使用时自动导入内置图库，只做一次。

    用标记文件控制：
    - 图库非空 → 打标记，不导入（尊重用户已有图库）
    - 已导入过 → 直接跳过（用户清空图库后不会被重新填充）
    - 首次且为空 → 导入 39 张并打标记
    """
    marker = data_dir / STARTER_MARKER
    if marker.is_file():
        return {"imported": False, "reason": "already"}
    if load_stickers(data_dir):
        marker.write_text("skip: library not empty", encoding="utf-8")
        return {"imported": False, "reason": "not_empty"}
    if not (pack_dir / "memes").is_dir():
        return {"imported": False, "reason": "no_starter_pack"}
    result = import_starter_pack(data_dir, pack_dir)
    marker.write_text(
        f"imported: added={result.get('added', 0)}", encoding="utf-8"
    )
    return {"imported": True, **result}


def delete_sticker(data_dir: Path, sticker_id: str) -> bool:
    """删除图库条目并移除图片文件。"""
    stickers = load_stickers(data_dir)
    keep, removed = [], None
    for s in stickers:
        if s.get("id") == sticker_id:
            removed = s
        else:
            keep.append(s)
    if not removed:
        return False
    save_stickers(data_dir, keep)
    p = sticker_abs_path(data_dir, removed)
    if p:
        try:
            p.unlink()
        except OSError:
            pass
    return True


def _mime_of(suffix: str) -> str:
    return {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
    }.get(suffix.lower(), "application/octet-stream")


def update_sticker(
    data_dir: Path,
    sticker_id: str,
    *,
    description: str | None = None,
    tags: dict | None = None,
) -> dict | None:
    """更新描述/标签，返回更新后的记录（找不到返回 None）。"""
    stickers = load_stickers(data_dir)
    hit = None
    for s in stickers:
        if s.get("id") == sticker_id:
            if description is not None:
                s["description"] = description
            if tags is not None:
                cur = s.get("tags") or {}
                s["tags"] = {
                    "emotion": list(tags.get("emotion", cur.get("emotion") or [])),
                    "scene": list(tags.get("scene", cur.get("scene") or [])),
                    "keywords": list(tags.get("keywords", cur.get("keywords") or [])),
                }
            hit = s
            break
    if hit is not None:
        save_stickers(data_dir, stickers)
    return hit


# ═══════════════ 偏好记录 ═══════════════

def record_feedback(
    data_dir: Path,
    *,
    emotion: str,
    sticker_id: str,
    positive: bool,
    agent_id: str = "default",
) -> dict:
    """记录喜欢/不喜欢到该助手的偏好映射里。"""
    prefs = load_prefs(data_dir)
    users = prefs.setdefault("users", {})
    entry = users.setdefault(agent_id or "default", {"mappings": []})
    mappings = entry.setdefault("mappings", [])

    target = None
    for m in mappings:
        if (m.get("context") or {}).get("emotion") == emotion:
            target = m
            break
    if target is None:
        target = {"context": {"emotion": emotion}, "preferred_ids": [], "vetoed_ids": [], "dislike_counts": {}}
        mappings.append(target)

    if positive:
        if sticker_id not in target["preferred_ids"]:
            target["preferred_ids"].append(sticker_id)
        if sticker_id in target["vetoed_ids"]:
            target["vetoed_ids"].remove(sticker_id)
    else:
        if sticker_id not in target["vetoed_ids"]:
            target["vetoed_ids"].append(sticker_id)
        if sticker_id in target["preferred_ids"]:
            target["preferred_ids"].remove(sticker_id)
        dc = target.setdefault("dislike_counts", {})
        dc[sticker_id] = int(dc.get(sticker_id, 0)) + 1

    save_prefs(data_dir, prefs)
    return target
