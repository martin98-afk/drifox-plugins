# session-tree

会话树 — DriFox 左侧停靠面板，按时间分组展示**当前项目**的会话列表，交互风格对齐 Codex 桌面版左侧面板。

## 功能

- **时间分组**：今天 / 昨天 / 近7天 / 近30天 / 更早（按会话最后对话时间）
- **点击切换**：点击会话项加载该会话（自动保存当前会话、停止流式）
- **新建会话**：面板顶部 `+` 按钮
- **右键菜单**：
  - ✏️ 重命名 — 修改会话标题（同步 DB / 当前会话对象 / Tab 标题）
  - 📦 归档会话 — 移入归档区（可恢复）
  - 🗑 永久删除 — 二次确认后从内存 + SQLite 彻底删除
- **当前会话高亮**：accent 背景 + 左侧强调条，切换后自动滚动可见
- **自动刷新**：3s 轮询（仅面板可见时），流式对话中标题/时间/列表实时同步
- **主题跟随**：颜色 / 字体随主程序 context 变化（深浅色自适应）

## 使用

- 安装后默认停靠在左侧（`container="left"`），宽度可拖拽调整
- 命令 `/session-tree` 切换显示/隐藏
- 每个会话项两行：标题 + 最后消息预览，右侧显示相对时间

## 数据源

- 会话列表：`main_widget.history_manager.get_history_list(project=<当前项目>)`（轻量，不含 messages）
- 切换：`main_widget._switch_to_session_by_id(session_id)`
- 新建：`main_widget._create_new_session()`

## 设计约束

- 不导入 `app.core` / `app.widgets` 内部模块，仅通过 `ctx["main_widget"]` 公开属性访问
- 多 Tab 隔离：每次刷新动态解析当前活跃窗口的 `main_widget`
- 归档/重命名优先走数据层 + `_notify_history_data_changed()` 同步主程序 UI
