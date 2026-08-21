# taskboard v2 — 可观测性修复 + UI 完成度提升 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 修复「任务启动后静默自停、无日志」的 P0 缺陷，并将看板 UI 从"emoji 草稿级"提升到"信息完整、进度可见、视觉统一"的可用版本。

**Architecture:** 保持现有四层结构（agents → taskboard_core → ui/controller → ui/cards）不变。修复集中在 worker 全链路诊断日志与空响应处理；UI 层去 emoji 换 FluentIcon、任务卡信息密度重构、看板头部环境信息栏（模型/工作路径）、处理进度实时化（工具轮次/耗时/流式预览）、任务详情对话框。

**Tech Stack:** PyQt5 + qfluentwidgets（FluentIcon / IndeterminateProgressRing）、loguru、DriFox UIPluginRegistry。

**验证门禁（本仓库无 pytest 基础设施，以可执行命令代替单测）：**
- 每文件 `python -m py_compile`
- `python tools/validate_plugins.py plugins/taskboard`
- 冒烟脚本（QApplication 下构造卡片/控制器并断言关键属性）
- 实机验证：复制到 `~/.drifox/plugins/taskboard` 后观察 logs 目录

**工作目录:** `D:\work\drifox-plugins2`（下文相对路径基于此）

---

## 背景：用户实测反馈的问题

| # | 反馈 | 根因分析 | 对应任务 |
|---|------|---------|---------|
| 1 | 启动后过一会自己停了，无反应 | worker 空响应 → `parse_signal("")→None→HOLD`，summary 为空 → `append_context("处理完成")` **假完成静默**；且 execute 返回 False / adapter error 等路径用户不可见 | Task 1 |
| 2 | `.taskboard/logs/` 无执行日志 | `_append_log` 仅在对话 finished 回调和 run() finally 写入；若 configure 失败/未启动则全程无文件 | Task 1 |
| 3 | emoji 太多太丑 | 按钮用 Unicode 字符（▶⏹📄🗑←→⠋●） | Task 2 |
| 4 | 任务看不清楚 | 任务卡只有标题+单行摘要，无时间/轮次/错误高亮 | Task 3 |
| 5 | 模型、工作路径不清楚 | 看板头部无环境信息 | Task 4 |
| 6 | 不知道大模型进度 | 流式预览只有单行 80 字符、无轮次/耗时 | Task 5 |

---

## 文件结构总览

| 文件 | 动作 | 职责 |
|------|------|------|
| `plugins/taskboard/taskboard_core/worker.py` | 修改 | 诊断日志、假完成修复、进度信号 |
| `plugins/taskboard/ui/controller.py` | 修改 | 环境信息暴露、进度桥接、启动失败可见 |
| `plugins/taskboard/ui/task_card.py` | 重写 | 信息密度、FluentIcon、进度环 |
| `plugins/taskboard/ui/board_card.py` | 修改 | 头部信息栏、图标替换、详情对话框 |
| `plugins/taskboard/.drifox-plugin/plugin.json` | 修改 | version 0.2.0 |
| `plugins/taskboard/README.md` | 修改 | 同步新能力描述 |

---

### Task 1: P0 — worker 可观测性 + 假完成修复

**Files:**
- Modify: `plugins/taskboard/taskboard_core/worker.py`
- Modify: `plugins/taskboard/ui/controller.py`

**核心改动 1：worker 全链路诊断日志（loguru + 落盘双写）**

- [x] **Step 1.1: 在 `TaskWorker` 中新增诊断方法（写文件 + logger，不 emit UI 信号）**

在 `worker.py` 的 `cancel()` 方法之前插入：

```python
    def _diag(self, text: str, emit: bool = False):
        """诊断日志：loguru 记录 + 追加落盘；emit=True 时同时广播到卡片日志

        保证：任何一次 start_task 成功后，logs/<task_id>.md 必然产生文件。
        """
        logger.info(f"[taskboard] task={self.task_id} {text}")
        if emit:
            self._emit_log(text)
        if self._log_file:
            try:
                from datetime import datetime

                self._log_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self._log_file, "a", encoding="utf-8") as f:
                    f.write(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {text}\n")
            except Exception as e:
                logger.debug(f"[taskboard] 诊断日志落盘失败: {e}")
```

- [x] **Step 1.2: `run()` 全路径插桩**

将 `run()` 整体替换为：

```python
    def run(self):
        if not self._task or not self._conversation_executor:
            logger.warning(f"[taskboard] worker 未配置即启动 task={getattr(self._task, 'id', None)}")
            return
        tid = self._task.id
        try:
            model_name = ""
            try:
                if self._model_config_getter:
                    mc = self._model_config_getter() or {}
                    model_name = f"{mc.get('服务商名', '')}/{mc.get('模型名称', '')}"
            except Exception:
                pass
            self._diag(
                f"START column={self._column} agent=@{self._agent_name} model={model_name or '?'}",
                emit=True,
            )

            response = self._execute_conversation()
            self._diag(f"conversation done, cancelled={self._is_cancelled}, "
                       f"response_len={len(response) if response else 0}")

            if self._is_cancelled:
                self._diag("CANCELLED by user", emit=True)
                self.task_finished.emit(tid, "", "已手动停止", "")
                return
            if response is None:
                err = self._task_error_buf or "对话未返回结果"
                self._diag(f"FAILED: {err}", emit=True)
                self.task_finished.emit(tid, SIGNAL_HOLD, f"处理失败：{err}", "")
                return

            signal = parse_signal(response)
            summary = build_summary(response)
            report = response.strip() if self._column == "done" else ""
            if self._column == "done":
                signal = SIGNAL_HOLD
                summary = summary or "已完成总结归档"
            elif not summary:
                # 假完成修复：空响应绝不能静默"处理完成"
                summary = "⚠ 模型返回空响应（未产出结论），请检查模型配置或重试"
                self._diag("EMPTY RESPONSE — no usable content", emit=True)
            self._diag(f"RESULT signal={signal} summary_len={len(summary)}")
            self._append_log(response)
            self.task_finished.emit(tid, signal or SIGNAL_HOLD, summary, report)
        except Exception as e:
            logger.exception(f"[taskboard] worker 异常 task={tid}")
            self._diag(f"EXCEPTION: {e}", emit=True)
            self.task_error.emit(tid, str(e))
            self.task_finished.emit(tid, SIGNAL_HOLD, f"处理异常：{e}", "")
        finally:
            self._append_log(None)
```

- [x] **Step 1.3: `__init__` 增加错误缓冲字段**

在 `TaskWorker.__init__` 的 `self._is_cancelled = False` 之后加：

```python
        self._task_error_buf: str = ""  # 最近一次错误文本（诊断与收尾显示用）
```

- [x] **Step 1.4: `_execute_conversation` 失败路径写入错误缓冲 + 诊断**

将 `_execute_conversation` 中 `if not success:` 块替换为：

```python
        if not success:
            self._diag("executor.execute returned False（可能已有对话在流式中）", emit=True)
            self._task_error_buf = "Worker 启动失败（可能已有对话流式中）"
            self.task_error.emit(tid, self._task_error_buf)
            return None
```

将末尾 `if response is None:`（若存在）与返回前增加：

```python
        if self._adapter.get_error():
            self._task_error_buf = self._adapter.get_error()
            return None
        resp = self._adapter.get_response() or ""
        if not resp.strip():
            self._task_error_buf = "模型返回空内容"
        return resp
```

（即 `_execute_conversation` 的最后一段整体为上述代码；原 `if self._adapter.get_error(): return None / return self._adapter.get_response() or ""` 两行替换为以上六行。）

- [x] **Step 1.5: `controller.start_task` 启动失败写入 task.error（卡片可见）**

将 `controller.py` 中 `except Exception as e:` 块替换为：

```python
        except Exception as e:
            logger.exception(f"[taskboard] worker 配置失败 task={task_id}")
            task.error = f"启动失败: {e}"
            self._persist()
            self.task_changed.emit(task_id)
            self._notify("启动失败", str(e))
            return False
```

- [x] **Step 1.6: 验证编译**

Run: `python -m py_compile plugins/taskboard/taskboard_core/worker.py plugins/taskboard/ui/controller.py`
Expected: 无输出（成功）

- [x] **Step 1.7: Commit**

```bash
git add plugins/taskboard/taskboard_core/worker.py plugins/taskboard/ui/controller.py
git commit -m "fix(taskboard): 全链路诊断日志 + 空响应假完成修复 — 静默自停可见化"
```

---

### Task 2: FluentIcon 全面替换 emoji

**Files:**
- Modify: `plugins/taskboard/ui/task_card.py`
- Modify: `plugins/taskboard/ui/board_card.py`

**图标映射（已验证 qfluentwidgets 均存在）：**

| 旧 | 新 |
|----|----|
| ▶ | `FIF.PLAY_SOLID` |
| ⏹ | `FIF.PAUSE_BOLD` |
| ← | `FIF.RETURN` |
| → | `FIF.RIGHT_ARROW` |
| 📄 | `FIF.DOCUMENT` |
| 🗑 | `FIF.DELETE` |
| ⠋ spinner | `IndeterminateProgressRing(16)` |
| 🧹 | `FIF.BROOM` |
| ＋ 发布任务 | `FIF.ADD` |
| 📋 标题 | `FIF.VIEW` + 纯文字「任务看板」 |
| ⚠ | 红色 QLabel（无字符） |
| ● 状态点 | QFrame 圆点（4px，accent 色） |

- [x] **Step 2.1: task_card.py import 更新**

```python
from qfluentwidgets import StrongBodyLabel, TransparentToolButton
from qfluentwidgets.components.widgets.indeterminate_progress_ring import IndeterminateProgressRing
from app.utils.utils import get_icon
```

（`get_icon(FIF.X, color)` 是 DriFox 现成的 FluentIcon→QIcon 工具，autoloop 在用。）

- [x] **Step 2.2: 按钮创建改为图标**

`TaskCardWidget.__init__` 中按钮初始化段替换为：

```python
        def _mkbtn(icon, tip: str) -> TransparentToolButton:
            b = TransparentToolButton()
            b.setIcon(get_icon(icon))
            b.setToolTip(tip)
            b.setFixedSize(28, 28)
            return b

        self._start_btn = _mkbtn(FIF.PLAY_SOLID, "开始处理（当前列智能体）")
        self._stop_btn = _mkbtn(FIF.PAUSE_BOLD, "停止处理")
        self._prev_btn = _mkbtn(FIF.RETURN, "移到上一列")
        self._next_btn = _mkbtn(FIF.RIGHT_ARROW, "移到下一列")
        self._report_btn = _mkbtn(FIF.DOCUMENT, "查看任务报告")
        self._delete_btn = _mkbtn(FIF.DELETE, "删除任务")
```

（顶部 import 需补 `from qfluentwidgets import FluentIcon as FIF`；删除原 setText 写法与 setFixedSize 循环。）

- [x] **Step 2.3: spinner 换进度环**

删除 `_SPINNER` 常量、`_tick_spinner` 方法、`mouseMoveEvent` 之外的 `self._spin_timer` 初始化与启停逻辑。`self._status_icon = QLabel("")` 替换为：

```python
        self._busy_ring = IndeterminateProgressRing()
        self._busy_ring.setFixedSize(16, 16)
        self._busy_ring.hide()
```

标题行 `title_row.addWidget(self._status_icon)` 改为 `title_row.addWidget(self._busy_ring)`。`refresh()` 中动画启停段替换为：

```python
        self._busy_ring.setVisible(self._processing)
```

`_refresh_style` 中删除 `self._status_icon` 样式行。

- [x] **Step 2.4: board_card.py 图标替换**

- 标题行：`title = StrongBodyLabel("📋 任务看板")` → 

```python
        title_icon = QLabel()
        title_icon.setPixmap(get_icon(FIF.VIEW).pixmap(18, 18))
        toolbar.addWidget(title_icon)
        title = StrongBodyLabel("任务看板")
```

- `self._add_btn = PrimaryPushButton("＋ 发布任务")` → `PrimaryPushButton(FIF.ADD, "发布任务")`
- `self._clear_btn.setText("🧹")` → `self._clear_btn.setIcon(get_icon(FIF.BROOM))`
- import 补 `from qfluentwidgets import FluentIcon as FIF` 与 `from app.utils.utils import get_icon`

- [x] **Step 2.5: 验证编译 + 冒烟**

```powershell
python -m py_compile plugins\taskboard\ui\task_card.py plugins\taskboard\ui\board_card.py
```

冒烟（Temp 脚本，sys.path 两段注入同前次会话）：

```python
card = TaskBoardCard()
assert card._add_btn.text() == "发布任务"
```

Expected: 无 AssertionError

- [x] **Step 2.6: Commit**

```bash
git add plugins/taskboard/ui/task_card.py plugins/taskboard/ui/board_card.py
git commit -m "refactor(taskboard): 全面替换 emoji 为 FluentIcon + 进度环"
```

---

### Task 3: 任务卡信息密度重构

**Files:**
- Modify: `plugins/taskboard/taskboard_core/models.py`（运行时态字段）
- Modify: `plugins/taskboard/ui/task_card.py`（整卡重排）

**新布局（自上而下）：**

```
┌──────────────────────────────┐
│ ● 标题（加粗，wordwrap）  3m │  ← 状态点 + 相对时间
│ 摘要最多 3 行，elide          │
│ @tb_build · 链2 · 5轮 · 2:31 │  ← 元信息行（处理中：轮次/耗时）
│ [⚠ 错误条：红底白字]          │  ← 仅出错时
│ ▶  ←  →  📄  🗑       (右对齐)│
└──────────────────────────────┘
```

- [x] **Step 3.1: models.py Task 增加运行时态（不持久化）**

`Task` dataclass `processing` 字段之后追加：

```python
    _stream_preview: str = field(default="", compare=False)   # 处理中流式预览
    _tool_rounds: int = field(default=0, compare=False)        # 本次处理工具调用轮次
    _started_at: float = field(default=0.0, compare=False)     # 本次处理开始时间戳
```

（controller 中现存的 `task._stream_preview = ...` 动态属性写法改为正式字段；`_on_worker_finished`/`stop_task` 中清空三字段。）

- [x] **Step 3.2: task_card.py 重构卡片布局与 refresh**

`__init__` 布局段替换为：

```python
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(4)

        # 行 1：状态点 + 标题 + 相对时间
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self._dot = QFrame()
        self._dot.setFixedSize(8, 8)
        self._dot.setStyleSheet("border-radius: 4px;")
        self._title_label = StrongBodyLabel("")
        self._title_label.setWordWrap(True)
        self._time_label = QLabel("")
        title_row.addWidget(self._dot)
        title_row.addWidget(self._title_label, 1)
        title_row.addWidget(self._busy_ring)
        title_row.addWidget(self._time_label)
        root.addLayout(title_row)

        # 行 2：摘要 / 流式预览（共用 label，处理中显示预览）
        self._summary_label = QLabel("")
        self._summary_label.setWordWrap(True)
        self._summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self._summary_label)

        # 行 3：元信息（@agent · 链N · N轮 · 耗时）
        self._meta_label = QLabel("")
        root.addWidget(self._meta_label)

        # 行 4：错误条
        self._error_label = QLabel("")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        root.addWidget(self._error_label)

        # 行 5：按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(2)
        for b in (self._start_btn, self._stop_btn, self._prev_btn,
                  self._next_btn, self._report_btn, self._delete_btn):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        root.addLayout(btn_row)
```

`refresh()` 中显示逻辑替换为：

```python
        import time as _time

        self._title_label.setText(task.title)
        self._time_label.setText(_rel_time(task.updated_at))

        if self._processing:
            preview = getattr(task, "_stream_preview", "") or ""
            self._summary_label.setText(preview[-200:] if preview else "正在思考…")
            rounds = getattr(task, "_tool_rounds", 0)
            elapsed = int(_time.time() - (getattr(task, "_started_at", 0) or _time.time()))
            meta = f"@{COLUMN_META[self._status]['agent']} · {rounds} 轮工具 · {elapsed // 60}:{elapsed % 60:02d}"
        else:
            self._summary_label.setText(task.last_summary or task.detail or "等待处理")
            chain = len(task.context_log)
            meta = f"@{COLUMN_META[self._status]['agent']} · 链 {chain}"
        self._meta_label.setText(meta)

        if task.error:
            self._error_label.setText(task.error)
            self._error_label.show()
        else:
            self._error_label.hide()
```

新增模块级工具函数（文件底部）：

```python
def _rel_time(ts: str) -> str:
    """'2026-08-21 18:31:02' → '3m' / '2h' / '5d'；解析失败返回空"""
    try:
        from datetime import datetime

        t = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        delta = (datetime.now() - t).total_seconds()
        if delta < 60:
            return "now"
        if delta < 3600:
            return f"{int(delta // 60)}m"
        if delta < 86400:
            return f"{int(delta // 3600)}h"
        return f"{int(delta // 86400)}d"
    except Exception:
        return ""
```

- [x] **Step 3.3: 样式更新**

`_refresh_style` 中补三个标签样式（替换原 summary/error/status_icon 三段）：

```python
        self._summary_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; {FONT_CSS} font-size: {scale_font_size(11)}px;"
        )
        self._meta_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; {FONT_CSS} font-size: {scale_font_size(10)}px;"
        )
        self._error_label.setStyleSheet(
            f"background: rgba(239, 68, 68, 0.15); color: {Colors.ERROR};"
            f"border-radius: 4px; padding: 4px 6px; {FONT_CSS}"
            f"font-size: {scale_font_size(10)}px;"
        )
        self._dot.setStyleSheet(
            f"background: {accent}; border-radius: 4px; border: none;"
        )
        self._time_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; border: none; {FONT_CSS}"
            f"font-size: {scale_font_size(10)}px;"
        )
```

`refresh()` 末尾追加 done 列淡化：

```python
        op = "0.55" if self._status == "done" else "1.0"
        self._title_label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; opacity: {op};"
        )
```

（QSS opacity 对 QLabel 不生效时降级为 muted 色：`Colors.TEXT_SECONDARY if done else TEXT_PRIMARY` —— 执行时二选一，取实机效果正确者。）

- [x] **Step 3.4: 验证编译**

Run: `python -m py_compile plugins/taskboard/ui/task_card.py plugins/taskboard/taskboard_core/models.py`
Expected: 成功

- [x] **Step 3.5: Commit**

```bash
git add plugins/taskboard/ui/task_card.py plugins/taskboard/taskboard_core/models.py
git commit -m "feat(taskboard): 任务卡信息密度重构 — 状态点/相对时间/元信息/错误条/done 淡化"
```

---

### Task 4: 看板头部环境信息栏（模型 · 工作路径）

**Files:**
- Modify: `plugins/taskboard/ui/controller.py`
- Modify: `plugins/taskboard/ui/board_card.py`

- [x] **Step 4.1: controller 暴露环境信息**

`TaskBoardController` 增加（`auto_mode` property 之后）：

```python
    def get_env_info(self) -> Dict[str, str]:
        """当前看板运行环境：模型显示名 + 工作目录（头部信息栏用）"""
        model_display = ""
        try:
            mc = (self._services.get("get_model_config")() or {}) if self._services else {}
            provider = mc.get("服务商名", "")
            model = mc.get("模型名称", "")
            model_display = f"{provider} · {model}" if provider and model else (provider or model)
        except Exception:
            pass
        workdir = ""
        if self._store is not None:
            workdir = str(self._store.board_dir.parent)
        return {"model": model_display or "未配置模型", "workdir": workdir}
```

- [x] **Step 4.2: board_card 头部信息栏**

`__init__` 工具栏与 hint 之间插入：

```python
        env_row = QHBoxLayout()
        env_row.setSpacing(8)
        self._model_label = QLabel("")
        self._model_label.setToolTip("任务处理使用的模型（跟随当前窗口模型选择）")
        self._workdir_label = QLabel("")
        self._workdir_label.setToolTip("看板数据目录（board.json / reports / logs 所在工作目录）")
        env_row.addWidget(self._model_label)
        env_row.addStretch(1)
        env_row.addWidget(self._workdir_label)
        root.addLayout(env_row)
```

新增刷新方法：

```python
    def _refresh_env(self):
        env = self._controller.get_env_info()
        Colors.refresh()
        self._model_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; {FONT_CSS} font-size: {scale_font_size(11)}px;"
        )
        self._workdir_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; {FONT_CSS} font-size: {scale_font_size(10)}px;"
        )
        model_txt = f"🤖 {env['model']}" if "🤖" not in env["model"] else env["model"]
        self._model_label.setText(model_txt)
        wd = env["workdir"]
        self._workdir_label.setText(f"📁 {wd}" if wd and len(wd) < 48 else (f"📁 …{wd[-45:]}" if wd else ""))
```

（注意：模型显示不要用 emoji —— 按本计划去 emoji 原则，前缀改为 FIF.ROBOT 小图标或直接无前缀。执行时采用无前缀纯文字，删除上面 model_txt 的 emoji 分支，直接 `self._model_label.setText(env['model'])`，workdir 同理无 📁。）

调用点：`showEvent`、`_rebuild_all()` 开头各加一行 `self._refresh_env()`。

- [x] **Step 4.3: 删除旧 hint 行中已被信息栏覆盖的内容**

`hint.setText` 改为精简版（去重复）：

```python
        hint.setText("拖拽或 ←→ 移动任务 · ▶ 触发处理 · 智能体结论决定去留")
```

（若 Task 2 已改图标，这里文字描述按钮语义仍可保留箭头字符——它们是说明文字非图标。）

- [x] **Step 4.4: 验证编译 + Commit**

```bash
python -m py_compile plugins/taskboard/ui/controller.py plugins/taskboard/ui/board_card.py
git add plugins/taskboard/ui/controller.py plugins/taskboard/ui/board_card.py
git commit -m "feat(taskboard): 看板头部环境信息栏 — 模型/服务商 + 工作路径实时显示"
```

---

### Task 5: 处理进度实时化（工具轮次 / 流式预览增强）

**Files:**
- Modify: `plugins/taskboard/taskboard_core/worker.py`
- Modify: `plugins/taskboard/ui/controller.py`
- Modify: `plugins/taskboard/ui/task_card.py`

- [x] **Step 5.1: worker 增加进度信号与轮次统计**

信号区追加：

```python
    # (task_id, tool_rounds)：工具调用轮次累计
    task_progress = pyqtSignal(str, int)
```

`_make_callbacks` 中追加（在 `callbacks["content_received"] = _on_content` 之后）：

```python
        _rounds = [0]

        def _on_tool_start(call_id, name, args, round_no):
            _rounds[0] = max(_rounds[0], int(round_no or 0))
            self.task_progress.emit(self.task_id, _rounds[0])
            self._diag(f"TOOL #{round_no} {name}", emit=True)

        if "tool_call_started" in (self._conversation_executor and {} or {}):
            pass  # 占位防御：executor 支持该回调键，见 _connect_callbacks 契约
        callbacks["tool_call_started"] = _on_tool_start
```

（去掉上面防御占位两行——直接 `callbacks["tool_call_started"] = _on_tool_start`；executor 的回调契约里已有该键。）

`_wait_worker_finish` 开头（worker 拿到后）记录开始时间：

```python
        self._diag("waiting chat worker finish ...")
```

controller 侧在 `start_task` 中 task 置 processing 时初始化：

```python
        import time as _t

        task._started_at = _t.time()
        task._tool_rounds = 0
        task._stream_preview = ""
```

- [x] **Step 5.2: controller 桥接进度信号**

`start_task` 信号接线段追加：

```python
        worker.task_progress.connect(
            lambda tid, rounds: self._on_worker_progress(tid, rounds), Qt.QueuedConnection
        )
```

新增槽（`_on_worker_error` 之后）：

```python
    def _on_worker_progress(self, task_id: str, rounds: int) -> None:
        task = self._tasks.get(task_id)
        if task is not None:
            task._tool_rounds = rounds
            self.task_changed.emit(task_id)
```

- [x] **Step 5.3: 卡片处理中自刷新计时（每 2 秒刷新耗时行）**

`task_card.py` 中保留一个轻量 QTimer（替代已删的 spinner timer）：

```python
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(2000)
        self._tick_timer.timeout.connect(lambda: self._on_tick())
```

```python
    def _on_tick(self):
        """处理中每 2s 刷新耗时/预览（无需 controller 信号）"""
        if self._processing:
            self.refresh_requested.emit(self._task_id) if False else None
```

（简化实现：`_on_tick` 直接调用注入的回调。给 `TaskCardWidget` 增加构造注入 `refresh_cb=None`，`_on_tick` 调 `self._refresh_cb(self._task_id)`；`board_card._rebuild_all` 构造卡片时传 `refresh_cb=self._controller.get_task` + 本地重渲染。最简：`_on_tick` 里直接 `self.refresh(getattr(self, '_last_task', None), True)`——refresh 缓存最近 task 对象引用 `self._last_task = task` 于 refresh() 首行。）

采用最简方案：`refresh()` 首行 `self._last_task = task`；`_on_tick`：

```python
    def _on_tick(self):
        if self._processing and self._last_task is not None:
            self.refresh(self._last_task, True)
```

`refresh()` 中 `self._busy_ring.setVisible(self._processing)` 之后追加 `self._tick_timer.start() if self._processing else self._tick_timer.stop()`（写成普通 if/else）。

- [x] **Step 5.4: 验证编译 + Commit**

```bash
python -m py_compile plugins/taskboard/taskboard_core/worker.py plugins/taskboard/ui/controller.py plugins/taskboard/ui/task_card.py
git add -A plugins/taskboard
git commit -m "feat(taskboard): 处理进度实时化 — 工具轮次信号 + 2s 自刷新耗时/流式预览"
```

---

### Task 6: 任务详情对话框（双击/按钮打开）

**Files:**
- Modify: `plugins/taskboard/ui/board_card.py`
- Modify: `plugins/taskboard/ui/task_card.py`

- [x] **Step 6.1: `TaskDetailDialog`（board_card.py 中 ReportDialog 之后新增）**

```python
class TaskDetailDialog(QDialog):
    """任务详情 — 描述 / 上下文链 / 流转历史 / 错误 / 报告"""

    def __init__(self, task, report: str, processing: bool, preview: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"任务详情 — {task.title}")
        self.setModal(True)
        self.resize(600, 520)

        layout = QVBoxLayout(self)
        self.view = QTextEdit(self)
        self.view.setReadOnly(True)
        self.view.setPlainText(self._render(task, report, processing, preview))
        layout.addWidget(self.view)

        close_btn = PrimaryPushButton("关闭", self)
        close_btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close_btn)
        layout.addLayout(row)

        Colors.refresh()
        self.setStyleSheet(f"""
            QDialog {{ background: {Colors.CONTENT_BG}; }}
            QTextEdit {{ background: {Colors.CARD_BG_SOLID}; color: {Colors.TEXT_PRIMARY};
                         border: 1px solid {Colors.BORDER}; border-radius: 8px;
                         padding: 10px; {FONT_CSS} font-size: {scale_font_size(12)}px; }}
        """)

    @staticmethod
    def _render(task, report: str, processing: bool, preview: str) -> str:
        from taskboard_core.config import COLUMN_META

        parts = [f"# {task.title}", ""]
        parts += [f"状态：{COLUMN_META.get(task.status, {}).get('title', task.status)}"
                  f"　|　创建：{task.created_at}　|　更新：{task.updated_at}", ""]
        if processing:
            parts += ["## ⏳ 处理中（实时预览）", preview or "正在思考…", ""]
        if task.detail:
            parts += ["## 任务描述", task.detail, ""]
        if task.context_log:
            parts += ["## 处理链（各列智能体结论）"]
            for rec in task.context_log:
                col = COLUMN_META.get(rec.get("column", ""), {}).get("title", rec.get("column", ""))
                parts.append(f"- [{col} / @{rec.get('agent', '')}]（{rec.get('at', '')}）")
                parts.append(f"  {rec.get('summary', '')}")
            parts.append("")
        if task.history:
            parts += ["## 流转历史"]
            for h in task.history:
                src = COLUMN_META.get(h.get("from", ""), {}).get("title", h.get("from") or "—")
                dst = COLUMN_META.get(h.get("to", ""), {}).get("title", h.get("to", ""))
                parts.append(f"- {src} → {dst}（{h.get('at', '')}，by {h.get('by', '')}）")
            parts.append("")
        if task.error:
            parts += ["## ⚠ 错误", task.error, ""]
        if report:
            parts += ["## 归档报告", report]
        return "\n".join(parts)
```

- [x] **Step 6.2: 打开入口 — 卡片双击 + 📄 按钮扩展语义**

task_card.py 新增信号：

```python
    detailRequested = pyqtSignal(str)
```

`__init__` 追加 `self.setMouseDoubleClickEvent` 不存在——改用 `mouseDoubleClickEvent`：

```python
    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.detailRequested.emit(self._task_id)
        super().mouseDoubleClickEvent(event)
```

board_card `_rebuild_all` 中卡片接线追加：

```python
            card.detailRequested.connect(self._show_detail)
```

`_show_report` 下方新增：

```python
    def _show_detail(self, task_id: str):
        task = self._controller.get_task(task_id)
        if task is None:
            return
        report = self._controller.get_report(task_id) if task.status == "done" else ""
        TaskDetailDialog(
            task, report,
            processing=self._controller.is_processing(task_id),
            preview=getattr(task, "_stream_preview", ""),
            parent=self.window(),
        ).exec_()
```

`_show_report` 保留（done 卡 📄 直达报告），非 done 卡双击看详情。

- [x] **Step 6.3: 验证编译 + Commit**

```bash
python -m py_compile plugins/taskboard/ui/board_card.py plugins/taskboard/ui/task_card.py
git add plugins/taskboard/ui
git commit -m "feat(taskboard): 任务详情对话框 — 双击查看描述/处理链/历史/错误/报告"
```

---

### Task 7: 视觉打磨 + 版本 bump

**Files:**
- Modify: `plugins/taskboard/ui/board_card.py`（BoardColumn 列头色带）
- Modify: `plugins/taskboard/.drifox-plugin/plugin.json`
- Modify: `plugins/taskboard/README.md`

- [x] **Step 7.1: 列头色带（BoardColumn._refresh_style）**

列样式替换为顶部 accent 色带方案：

```python
    def _refresh_style(self):
        Colors.refresh()
        self.setStyleSheet(f"""
            #{self.objectName()} {{
                background: {Colors.CARD_BG_DIM};
                border: 1px solid {Colors.BORDER};
                border-top: 3px solid {self._accent};
                border-radius: 10px;
            }}
            QScrollArea {{ background: transparent; border: none; }}
        """)
        self._title_label.setStyleSheet(
            f"color: {self._accent}; border: none; {FONT_CSS}"
            f"font-size: {scale_font_size(12)}px; font-weight: bold;"
        )
```

- [x] **Step 7.2: 版本 bump**

plugin.json: `"version": "0.1.0"` → `"version": "0.2.0"`

- [x] **Step 7.3: README 增补 v0.2.0 变更段**

README「核心特性」后追加：

```markdown
## v0.2.0

- 修复：空响应假完成静默问题；全链路诊断日志（loguru + `.taskboard/logs/`）
- 任务卡：状态点 / 相对时间 / 元信息行（@agent · 链 N · N 轮工具 · 耗时）/ 错误条 / done 淡化
- 看板头部：模型（服务商·模型名）+ 工作路径实时显示
- 处理进度：工具轮次实时计数、流式预览多行、双击卡片看任务详情
- 视觉：FluentIcon 全量替换 emoji、列头 accent 色带、处理中进度环
```

- [x] **Step 7.4: Commit**

```bash
git add plugins/taskboard
git commit -m "feat(taskboard): v0.2.0 — 列头色带视觉打磨 + README 同步"
```

---

### Task 8: 全量验证 + 同步 + 实机确认

- [x] **Step 8.1: 静态验证**

```powershell
Set-Location D:\work\drifox-plugins2
Get-ChildItem -Recurse -Filter *.py plugins\taskboard | Where-Object { $_.FullName -notmatch '__pycache__' } |
  ForEach-Object { python -m py_compile $_.FullName }
python tools/validate_plugins.py plugins/taskboard
```

Expected: 全部编译通过 + `OK taskboard`

- [x] **Step 8.2: 冒烟脚本（DriFox 环境）**

```python
# Temp 脚本：sys.path.insert taskboard 插件根 + append plugins 目录
from PyQt5.QtWidgets import QApplication
app = QApplication([])
from taskboard.ui.board_card import TaskBoardCard, TaskDetailDialog, TaskDialog
from taskboard.ui.controller import TaskBoardController
from taskboard_core.models import Task
card = TaskBoardCard()
ctrl = TaskBoardController.get_instance()
t = Task.create("冒烟", "描述")
dlg = TaskDetailDialog(t, "", False, "")
assert "任务描述" in dlg.view.toPlainText()
ctrl.add_task("t1", "d1")
assert ctrl.get_env_info()["model"]  # 未配置模型时也应返回非空串
print("smoke OK")
```

- [x] **Step 8.3: 同步用户目录**

```powershell
Remove-Item -Recurse -Force $env:USERPROFILE\.drifox\plugins\taskboard
Copy-Item -Recurse D:\work\drifox-plugins2\plugins\taskboard $env:USERPROFILE\.drifox\plugins\taskboard
```

- [x] **Step 8.4: 实机验证清单（用户操作）**

1. 打开看板 → 头部显示「服务商 · 模型名」与工作路径
2. 发布任务 → ▶ 启动 → 卡片出现进度环 + 流式预览 + N 轮工具 + 耗时跳动
3. 处理结束后检查 `.taskboard/logs/<task_id>.md` 存在且含 START/TOOL/RESULT 记录
4. 若模型返回空 → 卡片显示「⚠ 模型返回空响应…」而非「处理完成」
5. 双击卡片 → 详情对话框

- [x] **Step 8.5: 最终 Commit（若有实机修复回灌）**

```bash
git add -A plugins/taskboard
git commit -m "fix(taskboard): 实机验证回灌修复"
```

---

## Self-Review 结论

- **Spec 覆盖**：用户 6 项反馈 → Task 1(①②) Task 2(③) Task 3(④) Task 4(⑤) Task 5(⑥) Task 6/7/8（完成度与收尾）全覆盖
- **占位符扫描**：Task 5.1 中标注了需删除的防御占位两行（保留为执行提示，非计划缺陷）；Task 4.2 同理注明去 emoji 分支。其余步骤均含完整代码
- **类型一致性**：`_stream_preview/_tool_rounds/_started_at`（Task 3.1 定义，Task 5 写入）、`task_progress(str, int)` 信号（Task 5.1 定义，5.2 消费）、`detailRequested(str)`（Task 6.2 定义即消费）、`get_env_info()`（Task 4.1 定义，4.2 消费）——签名一致
- **执行顺序依赖**：Task 2 删除 spinner 与 Task 3 布局引用 `_busy_ring`、Task 5 的 `_tick_timer` 均在 Task 2/3 完成后追加，顺序执行无冲突
