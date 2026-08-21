# -*- coding: utf-8 -*-
"""JSONL 存储引擎 — 会话以 jsonl 格式持久化。

布局（base_dir 下）：
  ├─ sessions/{session_id}.jsonl        每行一条 session 快照（最新一条为当前状态）
  ├─ file_ops/{session_id}.jsonl        每行一次文件操作（按 session_id 关联）
  ├─ input_history.jsonl                每行一次用户输入
  ├─ subagent_tasks.jsonl               每行一次子代理任务
  └─ projects.json                      项目列表（轻量元数据，jsonl 不适合小 list）

设计目标：
  - 与 system/storages/sqlite.py 暴露的方法签名 100% 对齐，可热切换
  - 并存可选引擎（id="jsonl"），不替换默认 sqlite
  - 文件级原子写入：先写 .tmp 再 rename，避免读到半行
  - save() 全量覆盖（与 sqlite 行为一致：每次写入完整 session dict）
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


# 内部存储事件类型（file_ops/input_history/subagent_tasks 通用）
_TS_KEYS = ("updated_at", "created_at", "timestamp", "ts")


def _now_iso() -> str:
    """统一时间戳格式（与 sqlite 行为兼容，保留 ISO 字符串）"""
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # 兼容 "...Z" 与 "...+00:00"
        s2 = s.replace("Z", "+00:00") if s.endswith("Z") else s
        return datetime.fromisoformat(s2).replace(tzinfo=None)
    except Exception:
        return None


def _session_mtime(rec: dict) -> datetime:
    """按 updated_at / created_at / fallback now 取最新时间戳"""
    for k in ("updated_at", "created_at"):
        v = _parse_iso(rec.get(k))
        if v:
            return v
    return datetime.utcnow()


class JsonlStorageEngine:
    """JSONL 存储引擎 — 会话/文件操作/输入历史/子任务全部以 jsonl 持久化"""

    id = "jsonl"

    def __init__(self, db_dir: Optional[str] = None):
        """
        Args:
            db_dir: 数据根目录。None 时先读 plugin.json config_schema 里
                    "db_dir" 字段；都没有则默认 ~/.drifox/data/sessions/
        """
        # 读取插件自身配置（系统配置卡片写入的值）
        cfg_db_dir, cfg_on_corrupt = self._load_plugin_config()
        self._on_corrupt = cfg_on_corrupt

        if db_dir:
            self._base = Path(db_dir)
        elif cfg_db_dir:
            self._base = Path(cfg_db_dir)
        else:
            self._base = Path.home() / ".drifox" / "data" / "sessions"
        self._sessions_dir = self._base / "sessions"
        self._file_ops_dir = self._base / "file_ops"
        self._input_history_path = self._base / "input_history.jsonl"
        self._subagent_tasks_path = self._base / "subagent_tasks.jsonl"
        self._projects_path = self._base / "projects.json"

        # 状态标记：先设 False 再调 _ensure_init（_ensure_init 第一行
        # `if self._initialized:` 需要这个属性存在）。初始化目录必须立即
        # 执行：history_manager._init_storage 会读 engine.is_initialized，
        # False 即回退 JSON 走不到本引擎（input_history 走通是因为
        # main_widget 直接调 session_store.add_input_history，不经
        # is_initialized 检查）。失败兜底：捕获后保持 _initialized=False。
        self._initialized = False

        # 文件锁：保证同一进程内并发写入不撕裂
        self._lock = threading.RLock()

        # 初始化目录必须立即执行：history_manager._init_storage 会读
        # engine.is_initialized，False 即回退 JSON 走不到本引擎
        # （input_history 走通是因为 main_widget 直接调 session_store.add_input_history，
        # 不经 is_initialized 检查）。失败兜底：捕获后保持 _initialized=False
        try:
            self._ensure_init()
        except Exception:
            self._initialized = False

    # ---------- 内部辅助 ----------

    @staticmethod
    def _load_plugin_config() -> tuple:
        """从 PluginConfigStore 读取本插件配置（db_dir, on_corrupt）。

        PluginConfigStore 可能在导入期尚未初始化（依赖 DriFox 主程序启动），
        任何异常都静默降级，返回 ("", "skip")。
        """
        try:
            from app.plugins.managers.plugin_config_store import PluginConfigStore
            store = PluginConfigStore()
            db_dir = str(store.get("jsonl-storage", "db_dir") or "").strip()
            on_corrupt = str(store.get("jsonl-storage", "on_corrupt") or "skip").strip()
            if on_corrupt not in ("skip", "empty"):
                on_corrupt = "skip"
            return db_dir, on_corrupt
        except Exception:
            return "", "skip"

    def _ensure_init(self) -> None:
        if self._initialized:
            return
        for d in (self._base, self._sessions_dir, self._file_ops_dir):
            d.mkdir(parents=True, exist_ok=True)
        self._initialized = True

    @property
    def _db_path(self) -> str:
        """兼容 sqlite 引擎的 _db_path 属性（消费方 getattr 检查）"""
        return str(self._base)

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def store(self):
        """返回自身以满足 sqlite 引擎同名属性（消费方 hasattr 探测）"""
        return self

    # ---------- 通用 IO ----------

    @staticmethod
    def _atomic_write_jsonl(path: Path, lines: List[str]) -> None:
        """原子写 jsonl：先写临时文件再 rename，避免读到半行"""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(lines))
                if lines:
                    f.write("\n")
            os.replace(tmp, path)
        except Exception:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except Exception:
                    pass
            raise

    def _read_jsonl(self, path: Path) -> List[dict]:
        """读取 jsonl 文件。

        损坏行处理由 self._on_corrupt 决定：
          - "skip"（默认）：跳过损坏行
          - "empty"：遇到损坏行立即返回 []（视整文件为空）
        """
        if not path.exists():
            return []
        out: List[dict] = []
        try:
            with open(path, "r", encoding="utf-8", newline="\n") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        if getattr(self, "_on_corrupt", "skip") == "empty":
                            return []
                        # skip：继续读下一行
                        continue
        except OSError:
            return []
        return out

    @staticmethod
    def _append_jsonl(path: Path, record: dict) -> None:
        """追加一条 jsonl 行（追加流：input_history / subagent_tasks / file_ops）"""
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")

    def _session_path(self, session_id: str) -> Path:
        return self._sessions_dir / f"{session_id}.jsonl"

    def _file_ops_path(self, session_id: str) -> Path:
        return self._file_ops_dir / f"{session_id}.jsonl"

    # ---------- projects 索引（轻量 JSON） ----------

    def _load_projects(self) -> List[dict]:
        if not self._projects_path.exists():
            return []
        try:
            with open(self._projects_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except (OSError, json.JSONDecodeError):
            pass
        return []

    def _save_projects(self, projects: List[dict]) -> None:
        self._atomic_write_jsonl(
            self._projects_path, [json.dumps(p, ensure_ascii=False) for p in projects]
        )

    def _upsert_project(self, project: str, when: str) -> None:
        if not project:
            return
        projects = self._load_projects()
        found = False
        for p in projects:
            if p.get("name") == project:
                p["last_session_at"] = when
                p["session_count"] = p.get("session_count", 0) + 1
                found = True
                break
        if not found:
            projects.append(
                {"name": project, "last_session_at": when, "session_count": 1}
            )
        self._save_projects(projects)

    # ====================================================================
    # 主接口（与 SessionRepository 同名）
    # ====================================================================

    def save(self, session: dict) -> bool:
        """保存一个会话快照（全量覆盖）。session 必须含 session_id。"""
        self._ensure_init()
        sid = session.get("session_id") or session.get("id")
        if not sid:
            return False
        with self._lock:
            # 更新时间戳
            now = _now_iso()
            session.setdefault("created_at", now)
            session["updated_at"] = now
            path = self._session_path(sid)
            # 全量覆盖：单行 jsonl（最新状态）
            self._atomic_write_jsonl(
                path, [json.dumps(session, ensure_ascii=False)]
            )
            # 更新项目索引
            project = session.get("project")
            if project:
                self._upsert_project(project, now)
            return True

    def get(self, session_id: str) -> Optional[dict]:
        self._ensure_init()
        path = self._session_path(session_id)
        records = self._read_jsonl(path)
        return records[-1] if records else None

    def get_all(self, limit: int = 100, offset: int = 0) -> List[dict]:
        self._ensure_init()
        all_sessions = self._list_all_sessions()
        return all_sessions[offset : offset + limit]

    def get_by_project(self, project: str, limit: int = 100) -> List[dict]:
        self._ensure_init()
        if not project:
            return []
        all_sessions = self._list_all_sessions()
        matched = [s for s in all_sessions if s.get("project") == project]
        return matched[:limit]

    def get_projects(self) -> List[dict]:
        self._ensure_init()
        return self._load_projects()

    def delete(self, session_id: str) -> bool:
        self._ensure_init()
        path = self._session_path(session_id)
        if not path.exists():
            return False
        try:
            with self._lock:
                path.unlink()
            return True
        except OSError:
            return False

    # ====================================================================
    # 消费方方法（与 SessionStore 同名，行为对齐）
    # ====================================================================

    def save_session(self, session: dict) -> bool:
        return self.save(session)

    def get_session(self, session_id: str) -> Optional[dict]:
        return self.get(session_id)

    def get_sessions(self, limit: int = 100, offset: int = 0) -> List[dict]:
        return self.get_all(limit=limit, offset=offset)

    def get_sessions_lightweight(
        self, limit: int = 100, offset: int = 0
    ) -> List[dict]:
        """轻量列表：裁剪 messages 字段，减少返回体积"""
        all_sessions = self.get_all(limit=limit, offset=offset)
        light: List[dict] = []
        for s in all_sessions:
            slim = {k: v for k, v in s.items() if k != "messages"}
            # 保留消息数（消费方常用）
            msgs = s.get("messages") or []
            if isinstance(msgs, list):
                slim["message_count"] = len(msgs)
            light.append(slim)
        return light

    def get_sessions_by_team_run_id(self, run_id: str) -> List[dict]:
        if not run_id:
            return []
        return [
            s for s in self._list_all_sessions()
            if s.get("team_run_id") == run_id
        ]

    def delete_session(self, session_id: str) -> bool:
        return self.delete(session_id)

    def get_session_count(self) -> int:
        self._ensure_init()
        try:
            return sum(1 for _ in self._sessions_dir.glob("*.jsonl"))
        except OSError:
            return 0

    def update_session_project(self, session_id: str, project: str) -> bool:
        self._ensure_init()
        session = self.get(session_id)
        if not session:
            return False
        session["project"] = project
        session["updated_at"] = _now_iso()
        return self.save(session)

    def archive_sessions_by_project(self, project: str) -> int:
        """归档某项目下的所有会话（移到 archived/ 子目录，软删除语义对齐 sqlite）"""
        self._ensure_init()
        if not project:
            return 0
        archived_dir = self._base / "archived" / project
        archived_dir.mkdir(parents=True, exist_ok=True)
        moved = 0
        for s in self._list_all_sessions():
            if s.get("project") != project:
                continue
            sid = s.get("session_id") or s.get("id")
            if not sid:
                continue
            src = self._session_path(sid)
            if src.exists():
                dst = archived_dir / src.name
                try:
                    with self._lock:
                        shutil.move(str(src), str(dst))
                    moved += 1
                except OSError:
                    pass
        return moved

    def clear_old_subagent_tasks(self, days: int = 7) -> int:
        """清理 N 天前的子代理任务记录"""
        self._ensure_init()
        if not self._subagent_tasks_path.exists():
            return 0
        cutoff = datetime.utcnow() - timedelta(days=days)
        kept: List[str] = []
        removed = 0
        for rec in self._read_jsonl(self._subagent_tasks_path):
            ts = _parse_iso(rec.get("created_at") or rec.get("timestamp"))
            if ts and ts.replace(tzinfo=None) < cutoff:
                removed += 1
                continue
            kept.append(json.dumps(rec, ensure_ascii=False))
        if removed:
            self._atomic_write_jsonl(self._subagent_tasks_path, kept)
        return removed

    def force_cleanup_project(self, project_name: str) -> bool:
        """强制清理某项目：归档其会话并清理关联文件操作记录"""
        archived = self.archive_sessions_by_project(project_name)
        # 清理 file_ops 下该项目的记录（无法直接按 project 过滤，需要扫描 sessions）
        if archived:
            self._remove_file_ops_for_project(project_name)
        return archived > 0

    def _remove_file_ops_for_project(self, project: str) -> None:
        """删除某项目下所有会话的文件操作记录"""
        for s in self._list_all_sessions():
            if s.get("project") != project:
                continue
            sid = s.get("session_id") or s.get("id")
            if sid:
                p = self._file_ops_path(sid)
                if p.exists():
                    try:
                        p.unlink()
                    except OSError:
                        pass

    # ---------- 文件操作记录 ----------

    def record_file_operation(
        self,
        session_id: str,
        call_id: str,
        tool_name: str,
        file_path: str,
        backup_path: str,
    ) -> bool:
        self._ensure_init()
        if not session_id or not call_id:
            return False
        record = {
            "session_id": session_id,
            "call_id": call_id,
            "tool_name": tool_name,
            "file_path": file_path,
            "backup_path": backup_path,
            "created_at": _now_iso(),
        }
        with self._lock:
            self._append_jsonl(self._file_ops_path(session_id), record)
        return True

    def get_file_operations_by_call_id(
        self, session_id: str, call_id: str
    ) -> List[dict]:
        self._ensure_init()
        return [
            r for r in self._read_jsonl(self._file_ops_path(session_id))
            if r.get("call_id") == call_id
        ]

    def get_all_file_operations(self, session_id: str) -> List[dict]:
        self._ensure_init()
        return self._read_jsonl(self._file_ops_path(session_id))

    def clear_session_file_operations(self, session_id: str) -> None:
        self._ensure_init()
        p = self._file_ops_path(session_id)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass

    def remove_file_operation(self, session_id: str, call_id: str) -> int:
        self._ensure_init()
        p = self._file_ops_path(session_id)
        records = self._read_jsonl(p)
        kept = [r for r in records if r.get("call_id") != call_id]
        removed = len(records) - len(kept)
        if removed:
            self._atomic_write_jsonl(
                p, [json.dumps(r, ensure_ascii=False) for r in kept]
            )
        return removed

    # ====================================================================
    # 可选能力（标题 / 计数 / 输入历史）
    # ====================================================================

    def update_session_title(self, session_id: str, title: str) -> bool:
        self._ensure_init()
        session = self.get(session_id)
        if not session:
            return False
        session["title"] = title
        session["updated_at"] = _now_iso()
        return self.save(session)

    def get_session_counts(self) -> Dict[str, int]:
        """返回会话计数信息（与 sqlite 行为对齐：total/today/week）"""
        self._ensure_init()
        all_sessions = self._list_all_sessions()
        total = len(all_sessions)
        now = datetime.utcnow()
        today = sum(
            1 for s in all_sessions
            if _session_mtime(s).date() == now.date()
        )
        week_start = now - timedelta(days=7)
        week = sum(
            1 for s in all_sessions
            if _session_mtime(s) >= week_start
        )
        return {"total": total, "today": today, "week": week}

    def get_input_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        self._ensure_init()
        records = self._read_jsonl(self._input_history_path)
        # 倒序取最新 N 条
        records.reverse()
        return records[:limit]

    def add_input_history(
        self, content: str, attachments: Optional[list] = None
    ) -> bool:
        self._ensure_init()
        record = {
            "content": content,
            "attachments": attachments or [],
            "created_at": _now_iso(),
        }
        with self._lock:
            self._append_jsonl(self._input_history_path, record)
        return True

    # ====================================================================
    # 内部：扫描所有 session
    # ====================================================================

    def _list_all_sessions(self) -> List[dict]:
        """扫描 sessions 目录，按 updated_at 倒序返回所有最新会话快照"""
        self._ensure_init()
        out: List[dict] = []
        for path in self._sessions_dir.glob("*.jsonl"):
            records = self._read_jsonl(path)
            if records:
                out.append(records[-1])
        out.sort(key=_session_mtime, reverse=True)
        return out


def register(registry):
    """注册入口 — 与 tools/providers 插件约定一致（source 由 loader 强制注入）

    自激活逻辑（v0.1.0+）：
      主程序目前没有任何代码根据 plugin config_schema.enabled 自动调用
      StorageRegistry.set_active（搜遍 app/plugins 未发现），默认永远是 sqlite。
      本插件在注册完毕后主动检测 enabled 字段，若为 true 则 set_active("jsonl")
      立即激活自己；这样 settings 卡片开关就是真实生效的入口。
      任何异常（PluginConfigStore 未初始化/Proxy 转发不可用等）静默降级。
    """
    engine = JsonlStorageEngine()
    registry.register(engine)
    _try_self_activate(registry)


def _try_self_activate(registry) -> None:
    """如果 plugin.json config_schema.enabled == true，主动 set_active("jsonl")"""
    try:
        from app.plugins.managers.plugin_config_store import PluginConfigStore
        if not PluginConfigStore().get("jsonl-storage", "enabled"):
            return
    except Exception:
        # PluginConfigStore 未初始化 / 不可用 → 静默跳过
        return
    try:
        # _RegistryProxy 通过 __getattr__ 转发到真正的 StorageRegistry
        # → registry.set_active(...) 等价于底层 registry.set_active(...)
        ok = registry.set_active("jsonl")
        if not ok:
            # 极少见：register 时尚未在池中（并发）或 id 不匹配
            try:
                from loguru import logger
                logger.debug("[jsonl-storage] set_active('jsonl') returned False — pool not ready")
            except Exception:
                pass
    except Exception:
        # 不阻塞插件加载：失败也只是不接管，让 sqlite 继续
        pass