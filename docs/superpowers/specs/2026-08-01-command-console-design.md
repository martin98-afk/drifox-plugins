# command-console 插件设计文档

> 状态：已批准（用户确认 2026-08-01）
> 类型：DriFox 官方插件（ui 组件）
> 目标：在 DriFox 内提供**完全 cmd 体验**的内置命令终端

---

## 1. 背景与目标

### 问题
DriFox 生态目前没有通用用户终端。主程序 `app/tools/terminal_tools.py` 的 `execute_bash`
是给 AI 用的工具（subprocess 捕获输出），不是用户可交互的终端窗口。用户需要像打开 cmd 一样
直接在 DriFox 里敲命令。

### 目标
- 提供 `/command-console` 命令，`container="full"` 全屏覆盖对话区
- **完全 cmd 体验**：单一终端视图，提示符后直接输入、光标跟随、行内编辑、↑↓ 历史、
  Tab 补全、Ctrl+C 中断、交互式程序（python/vim/node REPL）完整可用
- **不是**「输出区 + 底部独立输入框」的分离式布局

### 非目标（本期不做）
- AI 命令捕获/双向联动（用户明确暂缓）
- 多标签终端、分屏
- 远程 SSH 会话

---

## 2. 核心洞察：ConPTY = 真实终端

Windows 10+ 内置 **ConPTY（Pseudo Console）API**（`kernel32.dll`：
`CreatePseudoConsole` / `ResizePseudoConsole` / `ClosePseudoConsole`）。

关键性质：**它是真实终端**。cmd.exe 跑在 ConPTY 里时，shell 自己完成——
回显、行编辑（←→ 移动光标）、方向键历史、Tab 补全、Ctrl+C 中断。
因此我们的 UI **不需要自己实现这些交互**，只需：

1. **键盘原样转发**：用户按键 → ConPTY stdin
2. **渲染输出**：ConPTY stdout（VT 转义序列）→ 终端模拟器解析 → 视图

### 为什么不用 pywinpty
- pywinpty 含 C 扩展，无法通过 `_vendor/` 机制 vendoring（vendor-demo 先例限制：
  「仅限纯 Python 包；含 C 扩展的包需主程序构建期声明」）
- DriFox 主程序 `pyproject.toml` 未声明 pywinpty，且主程序要求 Python ≥3.14，
  pywinpty 很可能没有 3.14 预编译 wheel
- **方案**：用 Python 标准库 `ctypes` 直接调用 ConPTY API（纯标准库，零第三方依赖）

---

## 3. 架构

### 目录结构

```
plugins/command-console/
├── .drifox-plugin/plugin.json     # manifest（components.ui = true）
├── __init__.py                    # 标记 Python 包
├── README.md                      # 插件说明 + 安装/使用
└── ui/
    ├── __init__.py                # register_ui(registry) → 注册浮动卡片
    ├── cards.py                   # CommandConsoleCard：终端视图 + 状态栏 + 生命周期
    ├── terminal_widget.py         # ★ TerminalWidget：pyte 渲染 + 键盘全捕获转发
    ├── shell.py                   # ShellSession 抽象（双后端自动选择）
    ├── conpty.py                  # ★ ctypes 直调 Windows ConPTY API
    └── _vendor/
        └── pyte/                  # vendored 纯 Python 终端模拟器（含 py.typed）
```

### 组件职责

| 模块 | 职责 | 依赖 |
|------|------|------|
| `register_ui` | 清理 sys.modules 缓存（热重载）→ 加载 `_vendor/` → 注册浮动卡片 | 无 |
| `CommandConsoleCard` | 卡片容器：TerminalWidget + 状态栏；卡片打开/关闭时启停 shell | TerminalWidget |
| `TerminalWidget` | 终端视图：pyte 屏幕 → QPlainTextEdit；键盘事件全捕获 → shell.write() | pyte, ShellSession |
| `ShellSession` | 会话抽象：`start(cwd)/write(data)/resize(cols,rows)/stop()` + `output_ready/exited` 信号 | — |
| `ConPTYSession`（shell.py 内） | Windows + ConPTY 可用时：ctypes 管道 + 子进程 | conpty.py |
| `PipeSession`（shell.py 内） | 兜底：QProcess 直连 stdin/stdout（非 Windows 或 ConPTY 失败） | PyQt5 |
| `conpty.py` | ctypes 绑定：CreatePseudoConsole/ResizePseudoConsole/ClosePseudoConsole + CreatePipe | ctypes |

### manifest

```json
{
    "name": "command-console",
    "description": "DriFox 内置命令终端 — 完全 cmd 体验的真实 shell 窗口（ConPTY）",
    "version": "0.1.0",
    "author": { "name": "DriFox Contributors" },
    "license": "GPL-3.0-or-later",
    "type": "user",
    "components": { "ui": true }
}
```

> 浮动卡片注册时自动注册 `/command-console` FUNCTION 命令（UIPluginRegistry 行为），
> 无需单独 commands/ 目录。

---

## 4. 详细设计

### 4.1 conpty.py — ctypes ConPTY 绑定

```python
# 核心 API（kernel32.dll）
CreatePseudoConsole(SIZE size, HANDLE hInput, HANDLE hOutput,
                    DWORD dwFlags, HPCON* phPC) -> HRESULT
ResizePseudoConsole(HPCON hPC, COORD size) -> HRESULT
ClosePseudoConsole(HPCON hPC) -> void
CreatePipe(PHANDLE hReadPipe, PHANDLE hWritePipe,
           LPSECURITY_ATTRIBUTES lpPipeAttributes, DWORD nSize) -> BOOL
```

实现要点：
- `SIZE`/`COORD` 为 `{SHORT X; SHORT Y}` 结构体，ctypes 用 `c_short` 打包
- 建立两条管道：`in_pipe`（ConPTY 输入，我们的写端 → ConPTY 读端）、
  `out_pipe`（ConPTY 输出，ConPTY 写端 → 我们读端）
- 子进程 `subprocess.Popen([shell, "/K", "chcp 65001>nul"], stdin=in_read, stdout=out_write,
  stderr=out_write, cwd=..., creationflags=CREATE_UNICODE_ENVIRONMENT | DETACHED_PROCESS)`
- 注意句柄继承：子进程须能继承 ConPTY 管道句柄（STARTUPINFO 不必须，Popen 传句柄即可）
- 读取线程：`out_pipe` 读字节 → 插件内实现简化版 `_smart_decode`（思路复用主程序
  `terminal_tools._smart_decode`：UTF-8 优先、GBK 回退、errors='replace'；**不 import
  主程序内部模块**，遵守隔离原则）→ `output_ready.emit(text)`
- `resize(cols, rows)` → `ResizePseudoConsole`
- `stop()` → 写 `exit\r\n` → 等退出 → `ClosePseudoConsole` → 关闭句柄

### 4.2 shell.py — 双后端

```python
class ShellSession(QObject):
    output_ready = pyqtSignal(str)   # 解码后的增量输出
    exited = pyqtSignal(int)         # shell 退出码

    def start(self, cwd): ...
    def write(self, data): ...       # 原样写 stdin（含 \r\n 控制序列）
    def resize(self, cols, rows): ...
    def stop(self): ...

def create_session(parent) -> ShellSession:
    """ConPTY 可用 → ConPTYSession；否则 PipeSession"""
    if sys.platform == "win32" and _conpty_available():
        return ConPTYSession(parent)
    return PipeSession(parent)
```

- `_conpty_available()`：`ctypes.windll.kernel32.CreatePseudoConsole` 存在性探测
- 启动时工作目录：卡片 context_provider 提供的项目根目录（与 AI `BackgroundTaskManager`
  对齐）；无则 `Path.cwd()`
- 编码：Windows 首行 `chcp 65001>nul`（复用主程序 `_prepare_windows_encoding` 经验），
  读取端 `_smart_decode` 式容错（UTF-8 优先，GBK 回退）

### 4.3 terminal_widget.py — 终端视图（核心）

**渲染**：
- 维护 `pyte.Screen(cols, rows)` + `pyte.Stream(screen)`
- ConPTY 输出字节 → `stream.feed(text)` → pyte 更新屏幕 cell 矩阵
- 渲染策略：**全量重绘**（v0.1 简化，每次 feed 后把屏幕转成文本重绘 QPlainTextEdit；
  性能优化留待 v0.2：diff 增量更新）——cmd 场景输出量可控，全量重绘可接受
- 光标：从 `screen.cursor` 映射到 QTextCursor 位置（闪烁跟随，QTimer 控制闪烁）
- ANSI 颜色：pyte 的 `screen.colors` 映射到 QPlainTextEdit 富文本（简化版：仅前景色）

**键盘**：
- `keyPressEvent` **全捕获**（除复制粘贴外不本地消费）→ 映射为字节序列 → `shell.write()`
- 映射表（Windows cmd 语义）：
  - 普通字符/回车/退格/方向键 → 原样 + 控制序列（`\r` 而非 `\n`）
  - `Ctrl+C` → `\x03`（中断，**不**用于复制）
  - `Ctrl+V` / `Ctrl+Shift+V` → UI 层粘贴：读剪贴板文本 → `shell.write()`（不依赖
    conhost 行为，统一由插件处理，跨平台一致）
  - `Ctrl+Shift+C` → 复制选中文本到剪贴板
  - `Ctrl+L` → `\x0c`（清屏）
- 焦点：终端获得焦点时 `setFocusPolicy(StrongFocus)`，避免误输到主界面

**尺寸**：
- `resizeEvent` → 计算 cols/rows（fontMetrics 字符宽高）→ `shell.resize(cols, rows)`
- 等宽字体：`Consolas`（Windows）/ `Menlo`（macOS）/ `monospace`（Linux）

### 4.4 cards.py — 卡片容器

- `CommandConsoleCard(QWidget)`：
  - `TerminalWidget` 为主体（expand）
  - 底部薄状态栏：项目根目录、后端类型（ConPTY/管道）、编码
- 生命周期：
  - 首次显示（`showEvent`）→ `create_session()` → `shell.start(cwd)`
  - 关闭（`closed` 信号）→ `shell.write("exit\r\n")` → 超时 2s 强杀 → 清理句柄
  - 热重载：register_ui 清理 `ui_plugin_command_console.*` 缓存（先例同 context-usage-stats）
- 与主界面隔离：不导入 `app.core`/`app.widgets` 内部模块（除必要的 registry API）

### 4.5 _vendor/pyte

- 来源：`pip download pyte` 或直接复制已安装的 pyte（纯 Python）
- 版本：最新稳定（≥0.8.2，需支持 Python 3.14）
- **许可证检查**：pyte 为 LGPL-3.0 —— 需确认与插件 GPL-3.0 兼容（LGPL 与 GPL 兼容 ✅，
  动态链接场景合规；vendoring 场景需保留许可证声明文件）
- register_ui 中 `sys.path.insert(0, vendor_dir)` + 清理同名缓存（vendor-demo 先例完整照搬）

---

## 5. 错误处理

| 场景 | 处理 |
|------|------|
| 非 Windows 平台 | 自动选 PipeSession（QProcess），功能可用但交互式程序受限 |
| ConPTY API 不存在（Win7/8） | `_conpty_available()` 返回 False → PipeSession |
| ConPTY 创建失败（句柄/权限） | try/except → 降级 PipeSession + logger.warning |
| shell 崩溃/退出 | `exited` 信号 → 状态栏提示「shell 已退出」（重启按钮留待 v0.2） |
| 编码乱码 | `_smart_decode` 容错（UTF-8→GBK 回退，errors='replace'） |
| 输出过大 | 全量重绘前限制 pyte 滚动缓冲行数（如 10000 行），超出丢弃最旧 |
| 卡片关闭时 shell 忙 | 先 `exit\r\n`，2s 超时 `taskkill /T /F` 强杀子进程树 |

---

## 6. 测试方案

### 单元测试（`plugins/command-console/tests/`）
- `test_conpty.py`：ctypes 结构体打包正确性（SIZE/COORD 偏移）、句柄创建/关闭
  （Windows only，无 ConPTY 时 skip）
- `test_shell.py`：`create_session` 后端选择逻辑（mock 平台/API 可用性）
- `test_terminal_widget.py`：pyte feed 后屏幕文本正确性（mock ShellSession）
  - 已知输入序列（如 `echo hello\r\n` + 提示符）→ 断言屏幕含 `hello`
- `test_cards.py`：生命周期（showEvent 启动 shell / closed 停止）

### 集成验证（手动清单）
- [ ] `/command-console` 打开全屏终端
- [ ] `dir` / `echo` / `cd` 正常
- [ ] `python` 进入 REPL，`1+1` 回车出结果，`Ctrl+C` 退出
- [ ] ↑↓ 历史切换、Tab 补全
- [ ] 中文命令输出无乱码（chcp 65001）
- [ ] 卡片关闭后 shell 进程退出（任务管理器确认无残留 cmd.exe）
- [ ] 非 Windows（Linux/macOS）降级管道模式可用

---

## 7. 发布清单

1. `python tools/validate_plugins.py` 通过
2. `python tools/generate_marketplace.py` 更新 marketplace.json
3. `plugins/README.md` 索引表追加 `command-console`
4. README 注明：Windows 10+ 完整 ConPTY 体验；非 Windows 降级
5. **附带文档补丁**（可选）：`docs/plugin-development.md` 增加「ui 插件引入第三方
   纯 Python 包（`_vendor/`）」说明段（本插件立下先例）

---

## 8. 待确认事项（TODO）

- [ ] pyte 版本锁定（需确认 3.14 兼容性与 LGPL 许可证文件放置）
- [ ] 全量重绘 vs 增量 diff 渲染：v0.1 全量，若性能不足 v0.2 升级
- [ ] 状态栏是否需要「重启 shell」按钮（v0.1 先不做，崩溃时状态栏提示即可）
- [ ] 主程序 `ContainerType` 对 `container="full"` 的映射已确认（ui_plugin_registry.py：
  full → TOP 覆盖层），无需额外改动
