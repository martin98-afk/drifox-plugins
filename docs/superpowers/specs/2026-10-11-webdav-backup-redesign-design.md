# webdav-backup v0.8.0 改版设计文档

> 日期：2026-10-11
> 状态：已获用户批准（彻底移除 4 类目录 + 顶层工具条 + 左右分栏 + .drifox/restore 恢复现场 + 收尾指引对话框）

## 1. 需求

对 `plugins/webdav-backup` 做一次界面与恢复流程改造：

1. **备份范围收窄**：移除「团队 / 项目 / 截图 / 本地备份」4 类选项
2. **布局重排**：左侧展示云端备份列表，右侧展示备份选项（范围勾选）
3. **恢复现场迁移**：被占用文件的落地脚本与暂存文件不再放系统 temp，改到 `.drifox` 下
4. **恢复收尾指引**：需要用户手动执行脚本时，自动打开文件位置 + 弹对话框给出编号步骤

## 2. 需求澄清结论（用户已确认）

| 问题 | 决定 |
|------|------|
| 4 类选项的处理力度 | 彻底移除：UI 选项、`config.py` 白名单一并删除；旧配置残留键忽略不计 |
| 右侧「备份选项」内容 | 只放备份范围勾选 + 额外包含；自动备份/间隔/保留份数/加密密码仍留在设置页 |
| 恢复脚本目录 | 统一 `~/.drifox/restore/`：`restore-<ts>.bat` + `pending-<ts>/` |
| 回滚副本目录 | 一并迁到 `~/.drifox/restore/rollback-<ts>/`，恢复现场集中一处 |
| 顶部按钮位置 | hero 下方独立工具条：立即备份 / 测试连接 / 刷新列表 |
| 收尾指引形式 | 模态对话框（`MessageBoxBase`）：标题 + 3 步编号指引 + 脚本路径 + 「打开所在文件夹」 |
| 分栏宽度比 | 1.15 : 0.85（列表宽、选项窄） |

## 3. 改动清单

### 3.1 `webdavbackup_core/config.py`

- `INCLUDE_FIELDS` 删除 `inc_teams` / `inc_projects` / `inc_screenshots` / `inc_backups`，剩 8 项
- `INCLUDE_LABELS` 删除对应中文名（团队/项目/截图/本地备份）
- `INCLUDE_DEFAULTS` 生成式不再需要 `screenshots` / `backups` 特判，简化为 `plugins` / `workspaces` 默认关
- `load_config()` / `describe_scope()` 逻辑不变（自动跟随白名单收窄）

### 3.2 `webdavbackup_core/engine.py`

新增模块级常量与工具函数：

```python
RESTORE_ROOT_NAME = "restore"          # ~/.drifox/restore

def get_restore_root() -> Path          # 并确保目录存在
def reveal_path(target: Path) -> bool   # explorer /select（Win）/ open -R（mac）/ xdg-open（Linux）
```

`run_restore()` 内：

- `rollback_dir`：`tempfile.gettempdir()/webdav-rollback-<ts>` → `~/.drifox/restore/rollback-<ts>`
- `pending_dir`：`tempfile.gettempdir()/webdav-restore-pending-<ts>` → `~/.drifox/restore/pending-<ts>`
- 返回值新增 `restore_dir`（本次恢复现场根目录）

`_write_finish_bat()`：

- 脚本落 `~/.drifox/restore/restore-<ts>.bat`（原名 `finish_restore-<ts>.bat`）
- robocopy 源改为新的 pending 目录；`rd /s /q` 清理 pending 后追加删除自身所在空目录的说明
- 脚本尾部保留 `pause` + `del "%~f0"`（自删），**不删父目录**（父目录可能还留着 rollback）

### 3.3 `ui/cards.py`

**布局重排**（`_setup_ui`）：

```
hero（图标 + 标题 + 副标题 + 关闭）
工具条卡：立即备份 | 测试连接 | 刷新列表 | 测试结果 … 重启 DriFox（恢复后出现）
摘要行（自动备份/间隔/保留份数/加密/范围/上次结果）
──────────────────────────────────────────────
左右分栏（QHBoxLayout，stretch 1.15 : 0.85）
  左：云端备份卡（标题 + 份数 + 分隔线 + ScrollArea 列表，区域滚动）
  右：备份范围卡（标题 + 保存时间提示 + 8 个单列勾选 + 额外包含输入框）
──────────────────────────────────────────────
状态行（底部固定）
```

- 删除旧的「底部大列表」`root.addWidget(hist, 1)` 结构，改由左栏承载
- 范围勾选由两列 `QGridLayout` 改单列 `QVBoxLayout`
- 左栏列表 `ScrollArea` 撑满可用高度（`stretch=1`），卡片整体高度不再随备份份数增长

**恢复收尾对话框**（新增私有类 `_RestoreGuideDialog(MessageBoxBase)`）：

- 标题「恢复需要手动收尾」
- 摘要：已应用 N 个文件；M 个正被占用
- 编号 3 步：退出 DriFox → 双击脚本 → 重新打开 DriFox
- 脚本绝对路径（可选文本，等宽字体、可选中）
- 回滚副本目录说明（若存在）
- 按钮：「稍后再说」/「打开所在文件夹」（后者调 `engine.reveal_path`）

`_on_restore_done()`：

- 有 pending 时弹对话框，**同时**自动调 `reveal_path(finish_script)` 打开资源管理器定位
- 状态行保留单行摘要（对话框关掉后仍可查）

### 3.4 文档与元数据

- `plugins/webdav-backup/README.md`：范围列表去掉 4 类；「版本管理」段更新恢复现场路径与指引文案
- `plugins/webdav-backup/.drifox-plugin/plugin.json`：`version` `0.7.1` → `0.8.0`
- 仓库 `CHANGELOG.md`：新增 `2.11.2` 段落（webdav-backup v0.8.0）
- `marketplace.json`：由 `tools/generate_marketplace.py` 重新生成（version 同步）

## 4. 不做的事

- 不动 `scheduler.py` / `crypto.py` / `webdav.py` / `host_compat.py`
- 不动设置卡（`config_schema`）字段
- 不主动清理用户 `config.json` 中的历史 `inc_*` 残留键
- 不动 `.github/workflows/`

## 5. 验证计划

1. `python -m py_compile` 三个改动文件
2. `ruff check plugins/webdav-backup/`
3. `python tools/validate_plugins.py`（清单合法性）
4. `python tools/generate_marketplace.py --check`（一致性）
5. 静态核对：`config.py` 白名单 8 项与 `cards.py` 渲染循环一致
6. 运行时（用户侧）：DriFox 热重载插件卡 → 检查左右分栏渲染、范围勾选仅 8 项、恢复触发对话框与 explorer 定位

## 6. 风险

| 风险 | 说明 | 缓解 |
|------|------|------|
| 旧配置残留 `inc_teams` 等键 | 用户 config.json 中仍存在，不再读取 | 无副作用（键不被读取即不生效）；如需彻底清理由用户手动编辑 |
| `.drifox/restore/` 长期堆积 | 每次恢复生成 pending/rollback 目录，不自动清理 | 目录名带时间戳、对话框与 README 明确提示可自行删除 |
| 分栏后左栏过窄 | 备份文件名较长（`drifox-backup-YYYYMMDD-HHMMSS.dvp`） | 列表项文件名 `ellipsis` + ToolTip 显示全名；比例 1.15 保证宽度 |
| 对话框在非主线程弹出 | 恢复结果经 signal queued 回主线程 | `_on_restore_done` 本就在主线程 slot 中执行 |
