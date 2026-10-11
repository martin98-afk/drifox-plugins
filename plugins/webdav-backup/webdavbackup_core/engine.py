# -*- coding: utf-8 -*-
"""备份/恢复引擎（纯同步函数，供后台线程或工具线程调用，禁止在 Qt 主线程直接跑）

备份：收集 app_data → zip（排除日志/缓存/大文件）→ 可选 AES 加密 → 上传 → 清理旧版本 → 写 state
恢复：下载 → 解密校验 → staging 解包（zip-slip 防护）→ 本地回滚副本 → 覆盖应用

恢复现场统一放 <app_data>/restore/（不落系统 temp）：
- restore-<ts>.bat       被占用文件的完成脚本（双击应用暂存文件）
- pending-<ts>/          被占用而无法直接覆盖的文件，保持数据目录相对结构
- rollback-<ts>/         本次覆盖前的旧文件副本，确认无误后可自行删除
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
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

# 恢复现场目录名（相对数据目录根）
RESTORE_ROOT_NAME = "restore"

# 进程内互斥：调度器与手动/工具触发同时备份时只放一个进去
_BACKUP_LOCK = threading.Lock()


def _now_str() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def get_restore_root() -> Path:
    """恢复现场根目录 <app_data>/restore/（不存在则建）"""
    root = cfg_mod.get_app_data_root() / RESTORE_ROOT_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def reveal_path(target: Path) -> bool:
    """在系统文件管理器中定位文件（Win：资源管理器选中；macOS：Finder 显示；Linux：打开父目录）

    尽力而为，失败返回 False，不影响调用方流程。
    """
    try:
        target = Path(target)
        if os.name == "nt":
            if target.exists():
                subprocess.Popen(["explorer", "/select,", str(target)])
            elif target.parent.exists():
                subprocess.Popen(["explorer", str(target.parent)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(target)])
        elif target.parent.exists():
            subprocess.Popen(["xdg-open", str(target.parent)])
        else:
            return False
        return True
    except Exception:
        return False


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
        # 恢复现场目录（回滚副本 / 暂存文件）是恢复过程产物，任何情况下都不入包
        if parts[0] == RESTORE_ROOT_NAME:
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


def _make_client(cfg: Dict[str, Any]) -> WebDAVClient:
    return WebDAVClient(cfg["server_url"], cfg["username"], cfg["password"])


def _checkpoint_sqlite(app_data: Path) -> List[str]:
    """备份前对数据目录顶层 *.db 做 WAL checkpoint（合并 -wal 进主库）

    尽力而为：库被主程序持有写锁时失败，仅记 note，不阻断备份。
    """
    import sqlite3

    notes: List[str] = []
    for db in app_data.glob("*.db"):
        try:
            conn = sqlite3.connect(str(db), timeout=1)
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                conn.close()
        except Exception as e:
            notes.append(f"{db.name}: WAL checkpoint 失败({e})")
    return notes


def _sqlite_snapshots(app_data: Path, files: List[Path], tmp_dir: Path) -> tuple:
    """对数据目录顶层的 *.db 用 SQLite backup API 生成一致性快照，替换入包来源

    返回 (payload_files, notes)：payload_files 与 files 一一对应；快照成功的条目指向
    tmp_dir 下的快照文件（含 -wal 中已提交数据，绕开文件锁），失败条目保留原路径。
    """
    import sqlite3

    notes: List[str] = []
    replaced: Dict[int, Path] = {}
    for idx, p in enumerate(files):
        if p.parent != app_data or p.suffix.lower() != ".db":
            continue
        snap = tmp_dir / f"{p.name}.snapshot"
        try:
            src = sqlite3.connect(f"file:{p.resolve().as_posix()}?mode=ro", uri=True, timeout=1)
            try:
                dst = sqlite3.connect(str(snap))
                try:
                    src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()
            replaced[idx] = snap
            notes.append(f"{p.name}: 已以 SQLite 快照入包")
        except Exception as e:
            notes.append(f"{p.name}: SQLite 快照失败，回退直读({e})")
    if not replaced:
        return files, notes
    payload_files = list(files)
    for idx, snap in replaced.items():
        payload_files[idx] = snap
    return payload_files, notes


def _remote_dir(cfg: Dict[str, Any]) -> str:
    return (cfg.get("remote_dir") or "drifox-backup").strip("/")


def _backup_filename(encrypted: bool) -> str:
    return f"drifox-backup-{_now_str()}.{'dvp' if encrypted else 'zip'}"


def _update_state(**kv: Any) -> None:
    state = cfg_mod.load_state()
    state.update(kv)
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    cfg_mod.save_state(state)


def _describe_webdav_error(e: WebDAVError) -> str:
    """把 WebDAV 错误映射成可直接照做的中文提示。

    401 才是凭证问题；403 涵盖配额/限流/只读目录等多种情况，
    按服务器返回的 DAV 专有异常名区分（坚果云把机器可读原因放在
    <s:exception> 里），不能一律归因到密码。
    """
    if e.status == 401:
        return "认证失败(401)：用户名或密码不正确。坚果云请确认使用的是「应用密码」而非登录密码"
    if e.dav_exception == "TrafficRateExhausted":
        return (
            "上传流量超额(403 TrafficRateExhausted)：坚果云本计算周期的上传流量已用完。"
            "可降低备份频率/保留份数（减小包体积），或等下一个周期额度重置后重试"
        )
    if e.dav_exception == "OverQuota":
        return "存储空间不足(403 OverQuota)：网盘剩余空间不够，请清理云端旧备份或扩容后重试"
    if e.status == 403:
        extra = f"（{e.dav_exception}）" if e.dav_exception else ""
        return f"服务器拒绝(403){extra}：可能是配额/流量限制或目录只读。服务器返回：{e.detail[:300] or '无详情'}"
    if e.status == 507:
        return "存储空间不足(507)：网盘剩余空间不够，请清理云端旧备份或扩容后重试"
    return str(e)


def run_test() -> Dict[str, Any]:
    """测试连接（不写 state）"""
    c = cfg_mod.load_config()
    if not cfg_mod.is_configured(c):
        return {"ok": False, "message": "尚未配置：请在 设置 → 插件 → WebDAV备份 填写服务器地址、账号与密码"}
    try:
        info = _make_client(c).test()
        return {"ok": True, "message": f"连接成功：{info.get('host', '')}"}
    except WebDAVError as e:
        return {"ok": False, "message": _describe_webdav_error(e)}
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
        return {"ok": False, "message": _describe_webdav_error(e), "items": []}


def run_backup() -> Dict[str, Any]:
    """完整备份流程；线程安全（进程内互斥）"""
    c = cfg_mod.load_config()
    if not cfg_mod.is_configured(c):
        return {"ok": False, "message": "尚未配置：请在 设置 → 插件 → WebDAV备份 完成配置"}
    if not _BACKUP_LOCK.acquire(blocking=False):
        return {"ok": False, "message": "已有备份任务进行中，请稍后再试"}
    t0 = time.monotonic()
    skipped: List[str] = []
    notes: List[str] = []
    tmp_dir: Path | None = None
    try:
        app_data = cfg_mod.get_app_data_root()
        notes += _checkpoint_sqlite(app_data)
        files, skipped = _collect_files(app_data, c.get("include_dirs", set()), c.get("include_extra", []))
        if not files:
            return {"ok": False, "message": f"未收集到可备份文件（数据目录: {app_data}）", "skipped": skipped}

        arcnames = [f.relative_to(app_data).as_posix() for f in files]
        tmp_dir = Path(tempfile.mkdtemp(prefix="webdav-backup-"))
        payload_files, snap_notes = _sqlite_snapshots(app_data, files, tmp_dir)
        notes += snap_notes
        entries = list(zip(arcnames, payload_files))
        pwd = (c.get("encryption_password") or "").strip()
        encrypted = bool(pwd)
        payload = crypto.make_zip(entries, skipped)
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
            last_backup_warning="; ".join(skipped),
        )
        msg = f"备份完成：{fname}（{size / 1048576:.1f} MB，{len(files)} 个文件，{dur:.1f}s）"
        if pruned:
            msg += f"，清理旧版 {len(pruned)} 份"
        if notes:
            msg += "；" + "；".join(notes)
        if skipped:
            msg += f"；警告：{len(skipped)} 个文件未入包（" + "；".join(skipped[:3]) + "）"
        return {"ok": True, "message": msg, "file": fname, "size": size, "count": len(files), "skipped": skipped}
    except crypto.CryptoUnavailableError as e:
        _update_state(last_backup_status="error", last_error=str(e), last_backup_warning="")
        return {"ok": False, "message": str(e), "skipped": skipped}
    except WebDAVError as e:
        msg = _describe_webdav_error(e)
        _update_state(last_backup_status="error", last_error=msg, last_backup_warning="")
        return {"ok": False, "message": msg, "skipped": skipped}
    except Exception as e:  # 顶层屏障
        msg = f"备份失败: {e}"
        _update_state(last_backup_status="error", last_error=msg, last_backup_warning="")
        return {"ok": False, "message": msg, "skipped": skipped}
    finally:
        if tmp_dir is not None:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        _BACKUP_LOCK.release()


def _write_finish_bat(pending_dir: Path, app_data: Path) -> Path:
    """生成一键完成脚本：robocopy 把暂存文件移入数据目录，完成后自删

    落在 <app_data>/restore/ 下（与 pending / rollback 同处，方便用户查找）。
    """
    bat = get_restore_root() / f"restore-{_now_str()}.bat"
    content = (
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        "echo Applying remaining DriFox restore files...\r\n"
        "echo.\r\n"
        f'robocopy "{pending_dir}" "{app_data.resolve()}" /E /MOVE /NFL /NDL /NJH /NJS\r\n'
        "if errorlevel 8 (\r\n"
        "  echo.\r\n"
        "  echo RESTORE FAILED - please check the paths above.\r\n"
        "  pause\r\n"
        "  exit /b 1\r\n"
        ")\r\n"
        f'rd /s /q "{pending_dir}" 2>nul\r\n'
        "echo.\r\n"
        "echo Done. You can start DriFox now.\r\n"
        "pause\r\n"
        'del "%~f0"\r\n'
    )
    bat.write_text(content, encoding="utf-8")
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


def run_restore(backup_name: str, encryption_password: str = "") -> Dict[str, Any]:
    """恢复指定备份包到本地（覆盖前留回滚副本），完成后需重启 DriFox"""
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
            # 回滚副本放数据目录下的 restore/ 现场（不自动清理，路径在结果中给出，确认无误后自行删除）
            restore_root = get_restore_root()
            rollback_dir = restore_root / f"rollback-{_now_str()}"
            rollback_dir.mkdir(parents=True, exist_ok=True)
            applied, moved_count, pending = _apply(app_data, data, staging, rollback_dir, skipped)

            finish_bat = None
            if pending:
                # 被占用的文件暂存（保持 zip 内相对结构），生成关闭 DriFox 后的一键完成脚本
                pending_dir = restore_root / f"pending-{_now_str()}"
                for rel, _dst in pending:
                    dest = pending_dir / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(staging / rel, dest)
                finish_bat = _write_finish_bat(pending_dir, app_data)

        _update_state(last_restore_at=datetime.now().isoformat(timespec="seconds"), last_restore_file=name)
        if pending:
            msg = (
                f"恢复部分完成：{name}，已应用 {applied} 个文件，"
                f"{len(pending)} 个正被占用需手动收尾（详见弹窗指引）"
            )
        else:
            msg = f"恢复完成：{name}（应用 {applied} 个文件）。请重启 DriFox 生效。"
        if skipped:
            msg += f" 跳过 {len(skipped)} 项。"
        return {
            "ok": True,
            "message": msg,
            "applied": applied,
            "pending": [rel for rel, _ in pending],
            "finish_script": str(finish_bat) if finish_bat else None,
            "restore_dir": str(restore_root),
            "skipped": skipped,
            "rollback_dir": str(rollback_dir) if moved_count else None,
        }
    except crypto.DecryptionError as e:
        return {"ok": False, "message": str(e)}
    except WebDAVError as e:
        return {"ok": False, "message": _describe_webdav_error(e)}
    except Exception as e:  # 顶层屏障
        return {"ok": False, "message": f"恢复失败: {e}"}
    finally:
        _BACKUP_LOCK.release()


def _apply(app_data: Path, data: bytes, staging: Path, rollback_dir: Path, skipped: List[str]) -> tuple:
    """解包到 staging → 数据目录相对路径覆盖应用

    可覆盖的直接覆盖（旧文件备份进 rollback_dir）；占用类失败（OSError）
    记入 pending（(rel, 目标绝对路径) 列表），由调用方暂存生成完成脚本。
    返回 (applied 成功数, moved_count, pending)。"""
    applied_names = crypto.extract_zip(data, staging, skipped)
    if not applied_names:
        raise ValueError("备份包内没有可应用的文件")

    applied = 0
    moved: List[tuple] = []
    pending: List[tuple] = []
    try:
        for rel in applied_names:
            src = staging / rel
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
        return applied, len(moved), pending
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
