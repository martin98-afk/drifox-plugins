# -*- coding: utf-8 -*-
"""备份/恢复引擎（纯同步函数，供后台线程或工具线程调用，禁止在 Qt 主线程直接跑）

备份：收集 app_data → zip（排除日志/缓存/大文件）→ 可选 AES 加密 → 上传 → 清理旧版本 → 写 state
恢复：下载 → 解密校验 → staging 解包（zip-slip 防护）→ 本地回滚副本 → 覆盖应用
"""
from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from . import config as cfg_mod
from . import crypto
from .webdav import WebDAVClient, WebDAVError

# 路径任意一段命中即整树排除
EXCLUDE_DIR_NAMES = {
    "logs", "log", "cache", "Cache", "GPUCache", "Crashpad", "Code Cache",
    "__pycache__", ".tmp", "tmp", "Temp", "webcache", "Crash Reports",
}
EXCLUDE_SUFFIXES = {".lock", ".tmp", ".pyc", ".pyo", ".log"}
MAX_FILE_SIZE = 200 * 1024 * 1024  # 坚果云免费版单文件上限附近，超过直接跳过
MAX_EXTERNAL_FILES = 20000         # 外部路径收集总文件数上限，防误填大目录

# 进程内互斥：调度器与手动/工具触发同时备份时只放一个进去
_BACKUP_LOCK = threading.Lock()


def _now_str() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _collect_files(app_data: Path, include_dirs: set, include_extra: list) -> tuple:
    """白名单收集：选中目录 + 额外路径 + 顶层散文件；排除规则优先生效

    返回 (files, skipped)。
    """
    files: List[Path] = []
    skipped: List[str] = []
    self_dir = (app_data / "plugin_data" / cfg_mod.PLUGIN_NAME).resolve()
    extra = {e.strip("/") for e in include_extra if e.strip()}

    def in_extra(rel_posix: str) -> bool:
        return any(rel_posix == e or rel_posix.startswith(e + "/") for e in extra)

    for p in sorted(app_data.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(app_data)
        parts = rel.parts
        rel_posix = rel.as_posix()
        if parts[0] in EXCLUDE_DIR_NAMES or (set(parts) & EXCLUDE_DIR_NAMES):
            continue
        # 白名单：顶层散文件始终收集；目录内容须命中白名单目录或额外路径
        if len(parts) > 1 and parts[0] not in include_dirs and not in_extra(rel_posix):
            continue
        try:
            if self_dir == p.resolve() or self_dir in p.resolve().parents:
                continue
        except OSError:
            continue
        if p.suffix.lower() in EXCLUDE_SUFFIXES:
            continue
        try:
            size = p.stat().st_size
        except OSError as e:
            skipped.append(f"{p.name}: {e}")
            continue
        if size > MAX_FILE_SIZE:
            skipped.append(f"{p.name}: 超过 200MB 已跳过")
            continue
        files.append(p)
    return files, skipped


def _collect_external(paths: List[str]) -> tuple:
    """收集数据目录之外的自定义备份路径。

    返回 (externals, skipped)；externals = [(key, root_path, files)]，
    key 为 zip 内 _external/<key>/ 前缀序号。沿用排除集/大小限制，
    单文件上限 200MB，总文件数超限截断并记录。
    """
    externals: List[tuple] = []
    skipped: List[str] = []
    total = 0
    for i, raw in enumerate(paths):
        raw = (raw or "").strip().strip('"')
        if not raw:
            continue
        try:
            p = Path(os.path.expandvars(raw)).expanduser()
            rp = p.resolve()
        except OSError:
            skipped.append(f"{raw}: 路径无法解析")
            continue
        if not rp.exists():
            skipped.append(f"{raw}: 路径不存在，已跳过")
            continue

        if rp.is_file():
            try:
                if rp.stat().st_size > MAX_FILE_SIZE:
                    skipped.append(f"{raw}: 超过 200MB 已跳过")
                    continue
                externals.append((str(i), rp.parent, [rp]))
                total += 1
            except OSError as e:
                skipped.append(f"{raw}: {e}")
            continue

        files: List[Path] = []
        for f in sorted(rp.rglob("*")):
            if not f.is_file():
                continue
            parts = set(f.relative_to(rp).parts)
            if parts & EXCLUDE_DIR_NAMES:
                continue
            if f.suffix.lower() in EXCLUDE_SUFFIXES:
                continue
            try:
                if f.stat().st_size > MAX_FILE_SIZE:
                    skipped.append(f"{raw}/{f.name}: 超过 200MB 已跳过")
                    continue
            except OSError as e:
                skipped.append(f"{f.name}: {e}")
                continue
            files.append(f)
        if not files:
            skipped.append(f"{raw}: 目录为空或全部被排除")
            continue
        if total + len(files) > MAX_EXTERNAL_FILES:
            skipped.append(f"{raw}: 文件数超出上限（累计 {MAX_EXTERNAL_FILES}），已整路径跳过")
            continue
        total += len(files)
        externals.append((str(i), rp, files))
    return externals, skipped


def _make_client(cfg: Dict[str, Any]) -> WebDAVClient:
    return WebDAVClient(cfg["server_url"], cfg["username"], cfg["password"])


def _remote_dir(cfg: Dict[str, Any]) -> str:
    return (cfg.get("remote_dir") or "drifox-backup").strip("/")


def _backup_filename(encrypted: bool) -> str:
    return f"drifox-backup-{_now_str()}.{'dvp' if encrypted else 'zip'}"


def _update_state(**kv: Any) -> None:
    state = cfg_mod.load_state()
    state.update(kv)
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    cfg_mod.save_state(state)


def run_test() -> Dict[str, Any]:
    """测试连接（不写 state）"""
    c = cfg_mod.load_config()
    if not cfg_mod.is_configured(c):
        return {"ok": False, "message": "尚未配置：请在 设置 → 插件 → WebDAV备份 填写服务器地址、账号与密码"}
    try:
        info = _make_client(c).test()
        return {"ok": True, "message": f"连接成功：{info.get('host', '')}"}
    except WebDAVError as e:
        msg = str(e)
        if e.status in (401, 403):
            msg = "认证失败(401/403)：坚果云请确认使用「应用密码」而非登录密码"
        return {"ok": False, "message": msg}
    except Exception as e:  # 顶层屏障：结果必须可序列化回 UI
        return {"ok": False, "message": f"未知错误: {e}"}


def run_list() -> Dict[str, Any]:
    """列出远端备份包（新→旧）"""
    c = cfg_mod.load_config()
    if not cfg_mod.is_configured(c):
        return {"ok": False, "message": "尚未配置 WebDAV", "items": []}
    try:
        client = _make_client(c)
        entries = client.list_dir(_remote_dir(c))
        items = [
            {
                "name": e["name"],
                "size": e["size"],
                "modified": e["modified"].astimezone().isoformat(timespec="seconds") if e["modified"] else "",
            }
            for e in entries
            if not e["is_dir"]
            and (e["name"].startswith("drifox-backup-"))
            and (e["name"].endswith(".zip") or e["name"].endswith(".dvp"))
        ]
        items.sort(key=lambda x: x["name"], reverse=True)
        return {"ok": True, "items": items, "message": ""}
    except WebDAVError as e:
        return {"ok": False, "message": str(e), "items": []}


def run_backup() -> Dict[str, Any]:
    """完整备份流程；线程安全（进程内互斥）"""
    c = cfg_mod.load_config()
    if not cfg_mod.is_configured(c):
        return {"ok": False, "message": "尚未配置：请在 设置 → 插件 → WebDAV备份 完成配置"}
    if not _BACKUP_LOCK.acquire(blocking=False):
        return {"ok": False, "message": "已有备份任务进行中，请稍后再试"}
    t0 = time.monotonic()
    skipped: List[str] = []
    try:
        app_data = cfg_mod.get_app_data_root()
        files, skipped = _collect_files(app_data, c.get("include_dirs", set()), c.get("include_extra", []))
        externals, ext_skipped = _collect_external(c.get("include_paths", []))
        skipped = skipped + ext_skipped
        if not files and not externals:
            return {"ok": False, "message": f"未收集到可备份文件（数据目录: {app_data}）", "skipped": skipped}

        # 打包条目：数据目录相对路径 + 外部路径（_external/<key>/…）+ 映射清单
        entries = [(f.relative_to(app_data).as_posix(), f) for f in files]
        manifest = {"externals": [{"key": key, "path": str(root_path)} for key, root_path, _ in externals]}
        for key, root_path, efiles in externals:
            for f in efiles:
                entries.append((f"_external/{key}/{f.relative_to(root_path).as_posix()}", f))
        manifest_json = json.dumps(manifest, ensure_ascii=False) if externals else ""

        pwd = (c.get("encryption_password") or "").strip()
        encrypted = bool(pwd)
        payload = crypto.make_zip(entries, skipped, manifest_json)
        if encrypted:
            payload = crypto.encrypt_bytes(payload, pwd)
        fname = _backup_filename(encrypted)

        client = _make_client(c)
        rdir = _remote_dir(c)
        client.mkdirs(rdir)
        client.put(f"{rdir}/{fname}", payload)

        pruned = _prune_old(client, c, keep=cfg_mod.load_config().get("keep_versions", 10))
        size = len(payload)
        dur = time.monotonic() - t0
        _update_state(
            last_backup_at=datetime.now().isoformat(timespec="seconds"),
            last_backup_status="success",
            last_backup_file=fname,
            last_backup_size=size,
            last_error="",
        )
        msg = f"备份完成：{fname}（{size / 1048576:.1f} MB，{len(files) + sum(len(e[2]) for e in externals)} 个文件，{dur:.1f}s）"
        if externals:
            paths_desc = "、".join(str(e[1]) for e in externals[:3]) + ("…" if len(externals) > 3 else "")
            msg += f"；含外部路径 {len(externals)} 个：{paths_desc}"
        if pruned:
            msg += f"，清理旧版 {len(pruned)} 份"
        return {
            "ok": True,
            "message": msg,
            "file": fname,
            "size": size,
            "count": len(files),
            "externals": [str(e[1]) for e in externals],
            "skipped": skipped,
        }
    except crypto.CryptoUnavailableError as e:
        _update_state(last_backup_status="error", last_error=str(e))
        return {"ok": False, "message": str(e), "skipped": skipped}
    except WebDAVError as e:
        msg = str(e)
        if e.status in (401, 403):
            msg = "认证失败(401/403)：坚果云请确认使用「应用密码」而非登录密码"
        _update_state(last_backup_status="error", last_error=msg)
        return {"ok": False, "message": msg, "skipped": skipped}
    except Exception as e:  # 顶层屏障
        msg = f"备份失败: {e}"
        _update_state(last_backup_status="error", last_error=msg)
        return {"ok": False, "message": msg, "skipped": skipped}
    finally:
        _BACKUP_LOCK.release()


def _write_finish_bat(pending_dir: Path, app_data: Path, externals_map: Dict[str, Path]) -> Path:
    """生成一键完成脚本：按目标分组 robocopy（/MOVE），完成后自删。

    pending_dir 内保持 zip 内相对结构；app_data 组排除 _external，
    外部路径组按 key 逐组拷回原绝对路径。"""
    bat = Path(tempfile.gettempdir()) / f"finish_restore-{_now_str()}.bat"
    rc = 'robocopy "{src}" "{dst}" /E /MOVE /NFL /NDL /NJH /NJS'
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        "echo Applying remaining DriFox restore files...",
        rc.format(src=pending_dir, dst=app_data.resolve()) + ' /XD _external',
    ]
    for key, target in externals_map.items():
        sub = pending_dir / "_external" / key
        if sub.exists():
            lines.append(rc.format(src=sub, dst=target))
    lines += [
        "if errorlevel 8 (",
        "  echo RESTORE FAILED - please check the paths above.",
        "  pause",
        "  exit /b 1",
        ")",
        f'rd /s /q "{pending_dir}" 2>nul',
        "echo Done. You can start DriFox now.",
        "pause",
        'del "%~f0"',
    ]
    bat.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return bat


def _prune_old(client: WebDAVClient, cfg: Dict[str, Any], keep: int) -> List[str]:
    """按文件名（时间戳序）保留最新 keep 份，删多余；删除失败不中断"""
    rdir = _remote_dir(cfg)
    try:
        entries = client.list_dir(rdir)
    except WebDAVError:
        return []
    names = sorted(
        [
            e["name"]
            for e in entries
            if not e["is_dir"] and e["name"].startswith("drifox-backup-") and (e["name"].endswith(".zip") or e["name"].endswith(".dvp"))
        ],
        reverse=True,
    )
    removed: List[str] = []
    for old in names[max(0, keep):]:
        try:
            client.delete(f"{rdir}/{old}")
            removed.append(old)
        except Exception:  # 清理是尽力而为：任何失败不拖累备份结果
            continue
    return removed


def _download_backup(c: Dict[str, Any], name: str, encryption_password: str) -> tuple:
    """下载并解密备份包，返回 (data, error_dict)；成功时 error_dict 为 None"""
    client = _make_client(c)
    blob = client.get(f"{_remote_dir(c)}/{name}")
    pwd = (encryption_password or "").strip() or (c.get("encryption_password") or "").strip()
    if crypto.is_encrypted(blob):
        if not pwd:
            return None, {"ok": False, "message": "该备份包已加密，请先在设置中填写备份加密密码（或由工具传入）"}
        return crypto.decrypt_bytes(blob, pwd), None
    return blob, None


def run_inspect(backup_name: str, encryption_password: str = "") -> Dict[str, Any]:
    """查看备份包内容清单（数据目录文件数 + 外部路径构成），不落盘"""
    name = (backup_name or "").strip().strip("/")
    if not name or "/" in name or name.startswith("."):
        return {"ok": False, "message": f"非法备份名: {backup_name!r}"}
    c = cfg_mod.load_config()
    if not cfg_mod.is_configured(c):
        return {"ok": False, "message": "尚未配置 WebDAV"}
    try:
        data, err = _download_backup(c, name, encryption_password)
        if err:
            return err
        lines = [f"{name} 内容："]
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
            data_files = [n for n in names if not n.startswith("_external/")]
            lines.append(f"- DriFox 数据目录：{len(data_files)} 个文件")
            try:
                raw = zf.read("_external/manifest.json")
                externals = json.loads(raw).get("externals", [])
                for e in externals:
                    prefix = f"_external/{e['key']}/"
                    n = len([x for x in names if x.startswith(prefix)])
                    lines.append(f"- 外部路径 {e['path']}：{n} 个文件")
            except KeyError:
                lines.append("- 外部路径：无")
        return {"ok": True, "message": "\n".join(lines)}
    except crypto.DecryptionError as e:
        return {"ok": False, "message": str(e)}
    except WebDAVError as e:
        return {"ok": False, "message": str(e)}
    except Exception as e:
        return {"ok": False, "message": f"查看失败: {e}"}


def run_restore(backup_name: str, encryption_password: str = "") -> Dict[str, Any]:
    """恢复指定备份包（数据目录 + 外部路径写回原位；覆盖前留回滚副本）"""
    name = (backup_name or "").strip().strip("/")
    if not name or "/" in name or name.startswith("."):
        return {"ok": False, "message": f"非法备份名: {backup_name!r}"}
    c = cfg_mod.load_config()
    if not cfg_mod.is_configured(c):
        return {"ok": False, "message": "尚未配置 WebDAV"}
    if not _BACKUP_LOCK.acquire(blocking=False):
        return {"ok": False, "message": "有备份任务进行中，请稍后再试"}
    try:
        data, err = _download_backup(c, name, encryption_password)
        if err:
            return err

        app_data = cfg_mod.get_app_data_root()
        app_data.mkdir(parents=True, exist_ok=True)
        skipped: List[str] = []

        with tempfile.TemporaryDirectory(prefix="webdav-backup-") as td:
            staging = Path(td) / "payload"
            staging.mkdir()
            # 回滚副本放系统临时目录固定前缀下，不自动清理（路径在结果中给出，确认无误后自行删除）
            rollback_dir = Path(tempfile.gettempdir()) / f"webdav-rollback-{_now_str()}"
            rollback_dir.mkdir(parents=True, exist_ok=True)
            applied, moved_count, pending, externals_map = _apply(
                app_data, data, staging, rollback_dir, skipped
            )

            finish_bat = None
            if pending:
                # 被占用的文件暂存（保持 zip 内相对结构），生成关闭 DriFox 后的一键完成脚本
                pending_dir = Path(tempfile.gettempdir()) / f"webdav-restore-pending-{_now_str()}"
                for rel, _dst in pending:
                    dest = pending_dir / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(staging / rel, dest)
                finish_bat = _write_finish_bat(pending_dir, app_data, externals_map)

        _update_state(last_restore_at=datetime.now().isoformat(timespec="seconds"), last_restore_file=name)
        ext_note = f"；外部路径 {len(externals_map)} 个已写回原位" if externals_map else ""
        if pending:
            msg = (
                f"恢复部分完成：{name}\n"
                f"已应用 {applied - len(pending)} 个文件{ext_note}；另有 {len(pending)} 个正被占用，已暂存待应用。\n"
                f"请完全退出 DriFox 后，双击运行：{finish_bat}\n完成后再启动 DriFox。"
            )
        else:
            msg = f"恢复完成：{name}（应用 {applied} 个文件{ext_note}）。请重启 DriFox 生效。"
        if skipped:
            msg += f" 跳过 {len(skipped)} 项。"
        return {
            "ok": True,
            "message": msg,
            "applied": applied - len(pending),
            "pending": [rel for rel, _ in pending],
            "finish_script": str(finish_bat) if finish_bat else None,
            "skipped": skipped,
            "rollback_dir": str(rollback_dir) if moved_count else None,
        }
    except crypto.DecryptionError as e:
        return {"ok": False, "message": str(e)}
    except WebDAVError as e:
        return {"ok": False, "message": str(e)}
    except Exception as e:  # 顶层屏障
        return {"ok": False, "message": f"恢复失败: {e}"}
    finally:
        _BACKUP_LOCK.release()


def _apply(app_data: Path, data: bytes, staging: Path, rollback_dir: Path, skipped: List[str]) -> tuple:
    """解包到 staging → 按 manifest 分发：数据目录相对路径 + _external/<key>/ 外部路径

    可覆盖的直接覆盖（旧文件备份进 rollback_dir）；占用类失败（OSError）
    记入 pending（(rel, 目标绝对路径) 列表），由调用方暂存生成完成脚本。
    返回 (applied 成功数, moved_count, pending, externals_map)。"""
    applied_names = crypto.extract_zip(data, staging, skipped)
    if not applied_names:
        raise ValueError("备份包内没有可应用的文件")

    externals_map: Dict[str, Path] = {}
    manifest_rel = "_external/manifest.json"
    if manifest_rel in applied_names:
        try:
            raw = json.loads((staging / manifest_rel).read_text(encoding="utf-8"))
            for e in raw.get("externals", []):
                externals_map[str(e["key"])] = Path(e["path"])
        except Exception:
            skipped.append("_external/manifest.json: 清单解析失败，外部路径部分按无映射跳过")

    ext_prefix = "_external/"
    applied = 0
    moved: List[tuple] = []
    pending: List[tuple] = []
    try:
        for rel in applied_names:
            if rel == manifest_rel:
                continue
            src = staging / rel
            if rel.startswith(ext_prefix):
                rest = rel[len(ext_prefix):]
                key, _, sub = rest.partition("/")
                target_root = externals_map.get(key)
                if target_root is None or not sub:
                    skipped.append(f"{rel}: 无映射清单，跳过")
                    continue
                dst = target_root / sub
            else:
                dst = app_data / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                try:
                    rb = rollback_dir / rel
                    rb.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(dst, rb)
                    moved.append((dst, rb))
                except OSError:
                    moved.append((dst, None))
            try:
                shutil.copy2(src, dst)
                applied += 1
            except OSError:
                # PermissionError(WinError 32/5) 与 WinError 1224(用户映射区域，
                # SQLite mmap 打开的文件) 均为占用类失败 → 暂存待应用
                pending.append((rel, dst))
        return applied, len(moved), pending, externals_map
    except Exception:
        # 尽力回滚已覆盖文件
        for dst, rb in reversed(moved):
            if rb is None:
                continue
            try:
                shutil.copy2(rb, dst)
            except OSError:
                pass
        raise
