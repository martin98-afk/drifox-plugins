# jsonl-storage

JSONL 存储引擎 — 会话以 jsonl 格式持久化（per-session 文件 + 辅助索引文件），行为对齐 system 的 sqlite 引擎，可作为并存可选引擎注册。

## 引擎 ID

`id = "jsonl"`

## 数据目录布局

默认根目录：`~/.drifox/data/sessions/`（可通过构造函数 `db_dir` 覆盖）

```
<base_dir>/
  ├─ sessions/{session_id}.jsonl      每会话一个文件，单行 JSON（最新快照）
  ├─ file_ops/{session_id}.jsonl      该会话的文件操作记录（append 流）
  ├─ input_history.jsonl              用户输入历史（append 流，倒序读取）
  ├─ subagent_tasks.jsonl             子代理任务（append 流）
  ├─ projects.json                    项目列表（轻量 JSON 索引）
  └─ archived/<project>/              archive_sessions_by_project 的归档目录
```

## 写入策略

- **session 文件**：每次 `save()` 全量覆盖为单行 JSON（与 sqlite 的 row 语义一致）
- **辅助流**（file_ops / input_history / subagent_tasks）：append-only
- **原子写**：先写 `.tmp` 再 `os.replace`，避免读到半行

## 接口对齐

实现与 `system/storages/sqlite.py` 100% 同名同签名，可热切换：

| 类别 | 方法 |
|------|------|
| SessionRepository 主接口 | `save / get / get_all / get_by_project / get_projects / delete` |
| SessionStore 消费方 | `save_session / get_session / get_sessions / get_sessions_lightweight / get_sessions_by_team_run_id / delete_session / get_session_count / update_session_project / archive_sessions_by_project / clear_old_subagent_tasks / force_cleanup_project` |
| 文件操作 | `record_file_operation / get_file_operations_by_call_id / get_all_file_operations / clear_session_file_operations / remove_file_operation` |
| 可选能力 | `update_session_title / get_session_counts / get_input_history / add_input_history` |

## 使用方式

1. 启用插件后，`registry` 中会出现 id 为 `"jsonl"` 的存储引擎实例
2. 在 DriFox 设置/配置中选择 `"jsonl"` 作为存储引擎（与 `"sqlite"` 并存可选）
3. 不影响 system 默认 sqlite 引擎的运行

## 测试

```bash
py tests/smoke_test.py
```

烟雾测试覆盖：save/get/update_title/list/by_project/session_counts/input_history/file_ops/archive/delete。

## 版本

- 0.2.0 — 加图标（JSON-Line.svg）；register 末尾自激活；__init__ 立即初始化目录
- 0.1.0 — 初始实现