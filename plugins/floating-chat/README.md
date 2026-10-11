# floating-chat

> 随时呼出的对话悬浮窗：不打开 DriFox 主窗也能快速问大模型。输入即问、流式作答、一键跳转完整会话。

## 用途

主程序的输入框在主窗里，想随口问一句就得先切回 DriFox、找会话、找输入框。本插件把这条路径压到一次按键：

- 全局热键呼出一个小窗，输完回车就发
- **独立会话**，不污染主窗正在进行的对话
- 回答以纯文本流式吐出（等宽字体、保留换行缩进）
- 需要看完整内容时，一键拉起主窗加载该会话

## 使用

### 1. 绑定热键（首次需要）

本插件**不自建全局热键**，走 DriFox 既有的快捷键管理：

1. 打开 DriFox → 设置 → 快捷键管理
2. 找到命令 `/floating-chat`（描述「打开悬浮对话窗」）
3. 给它分配 `Alt+Space`（或任意你顺手的组合）

分配后落 `user-custom/shortcuts.json`，重启仍生效。
命令同时可在主窗输入 `/floating-chat` 回车触发。

> ⚠️ `Alt+Space` 在 Windows 上是系统窗口菜单键。若实测与系统菜单打架，换成 `Ctrl+Alt+Space` 或 `Alt+Q`。

### 2. 交互

| 操作 | 效果 |
|------|------|
| 热键 / 命令 `/floating-chat` / 左侧插件栏点击 | 打开或关闭悬浮窗 |
| `Enter` | 发送 |
| `Shift+Enter` | 换行 |
| `Esc`（光标在输入框） | 隐藏窗口（会话保留） |
| 发送中再点发送钮（■） | 停止当前流 |
| 标题栏「📌」 | 钉住：窗口常驻最前，不再沉底 |
| 「新会话」 | 清空当前会话重新开始 |
| 「打开完整会话」 | 拉起主窗并加载该会话 |

窗口位置与尺寸自动记忆，下次打开落在原处（首次居中偏上）。

## 行为口径

| 项 | 行为 |
|----|------|
| 会话归属 | 插件独立会话，与主窗对话隔离 |
| 历史 | 每轮结束后写入主窗历史，标题「快速对话 · <首问前 20 字>」，历史面板可翻到 |
| 模型 | 跟随主窗当前选中的服务商 + 模型，状态行显示，无需单独配置 |
| 工具权限 | 与主窗一致（INTERACTIVE）。工具需确认时窗内出现「允许 / 拒绝」审批条 |
| 回答渲染 | 纯文本等宽，不渲染 Markdown |
| 图片附件 | 不支持（定位是快问快答） |

## 结构

```
floating-chat/
├── .drifox-plugin/
│   └── plugin.json           # manifest（启用 ui + commands）
├── __init__.py               # 插件包标记
├── commands/
│   └── floating-chat.md      # FUNCTION 命令（命令名 = 文件名，供快捷键管理器分配）
├── icon.svg / icon_dark.svg  # 插件管理列表图标
├── README.md                 # 本文件
└── ui/
    ├── __init__.py           # register_ui：register_window + 上下文 provider + 命令 handler
    ├── chat_page.py          # ChatPage：状态行 / 回答区 / 输入区 / 审批条 / 钉住 / 几何记忆
    └── engine_bridge.py      # ChatController：IsolatedChatContext 封装 + 跨线程信号桥
```

## 实现要点

**引擎**：复用主程序 `app/gateway/local_service/isolated_context.py` 的 `IsolatedChatContext`
（独立 SessionManager + ToolExecutor + 经 `create_engine_for_slot` 构造的 ChatEngine），
不自建引擎栈。因为这层走 `create_engine_for_slot`，主窗若被插件替换过引擎，悬浮窗自动跟随。

**权限**：主窗 `ChatEngine` 本身硬编码 `PermissionStrategy.INTERACTIVE` +
`_check_tool_permission`（无 backend 时兜底读全局 Settings 工具开关），直接复用即等于「与主窗一致」。

**线程**：`ChatEngine.send_message` 内部有 `QEventLoop().exec()` 阻塞等待预处理 worker，
必须放后台 `QThread`；worker 回调在 worker 线程触发，一律只 `emit` Qt 信号，
UI 更新全在主线程槽里做。

**历史**：写宿主窗口的 `history_manager.save_session`，**不走** `APIHistoryManager`
——后者写独立 SQLite 且只留 100 条，主窗历史面板翻不到。

## 已知限制

| 项 | 说明 |
|----|------|
| 热键生效范围 | 走命令快捷键通道，主窗完全隐藏/仅剩托盘时可能不触发，实测后决定是否补全局钩子 |
| `_load_session_from_record` | 主窗私有 API，加载失败自动降级为提示去历史面板找，不崩 |
| 主窗全关 | 无法取到模型配置，提示先打开主窗 |
| 多轮历史 | 窗内只保留当前会话，历史请在主窗查看 |

## 依赖

仅依赖主程序内置能力（PyQt5 + loguru），零第三方新依赖。

## License

MIT（与 DriFox 项目一致）。
