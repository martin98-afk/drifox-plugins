# floating-chat 悬浮对话插件设计文档

> 日期：2026-10-12
> 状态：待用户评审（视觉稿 v2 已在浏览器确认：纯文本回答区 + 钉住开关）

## 1. 需求

一个可随时呼出的对话悬浮窗，不打开 DriFox 主窗也能快速给大模型发消息：

1. **全局热键呼出**：`alt+space`（由用户在快捷键管理器分配给插件命令）
2. **独立会话**：与主窗当前对话隔离，不污染正在进行的会话
3. **窗内闭环**：输入框 + 纯文本流式回答区，多轮保留
4. **可跳转完整会话**：悬浮窗内能一键打开主窗并加载该会话

## 2. 需求澄清结论（用户已确认）

| 问题 | 决定 |
|------|------|
| 呼出方式 | 全局热键（命令快捷键通道），非托盘菜单、非输入区按钮 |
| 会话归属 | 插件独立会话，与主窗隔离；落主窗历史，可在历史面板翻到 |
| 窗内展示 | 输入 + 流式回答；不做完整历史列表、不做通知式角标 |
| 工具权限 | 与主窗一致（INTERACTIVE），工具需确认时窗内弹审批条 |
| 回答渲染 | **纯文本**：等宽字体 + `pre-wrap` 保留换行缩进，不渲染 Markdown、不引 WebView |
| 窗口位置 | 记住上次关闭时的位置与尺寸（首次居中偏上） |
| 钉住开关 | 标题栏加「📌 钉住」，开 = `WindowStaysOnTopHint` |
| 热键实现 | **不自建全局钩子**：注册 `/floating-chat` 命令，由用户用既有快捷键管理系统绑定 `alt+space` |
| 打开完整会话 | 支持：窗内按钮 → 拉起主窗 → 加载该 session_id |

## 3. 载体选型

**独立弹窗 `register_window`**，不用浮动卡片。

理由：需求核心是「不打开主窗也能用」，浮动卡片寄生在主窗容器内，主窗隐藏时无从依附。
`UIPluginRegistry.register_window` 提供：无边框壳 + 精简标题栏（拖动/最小化/关闭/主题全托管）、
左侧插件栏条目、右键「弹出」、自动注册 `/<window_id>` 命令。

## 4. 目录结构

```
plugins/floating-chat/
├── .drifox-plugin/
│   └── plugin.json             # manifest：仅 components.ui = true
├── icon.svg / icon_dark.svg    # 插件管理列表图标
├── README.md
└── ui/
    ├── __init__.py             # register_ui：register_window + 命令注册
    ├── chat_page.py            # 内容页 QWidget（三约定接口 + 全部 UI）
    └── engine_bridge.py        # 对话引擎桥：IsolatedChatContext 封装 + Qt 信号桥
```

## 5. 对话引擎方案

### 5.1 复用 `IsolatedChatContext`（不自建引擎栈）

主程序已有 `app/gateway/local_service/isolated_context.py`，为 API 调用封装了完整隔离环境：

```python
IsolatedChatContext(
    context_id=str(uuid.uuid4()),
    main_widget=宿主窗口,
    target_session=目标会话,
    model_config=宿主窗口._get_current_model_config(),
).create_chat_engine(worker_callbacks=..., api_mode=...)
```

它内部组装：独立 `SessionManager`（不碰主窗会话）+ `ToolExecutor`（共享主窗 builtin tools）
+ `AgentManager` 单例 + `create_engine_for_slot("ui", ChatEngine, ...)`。

**关键收益**：走 `create_engine_for_slot` 意味着主窗若被插件替换过引擎，悬浮窗自动跟随，
无需插件自己适配引擎注册表。

### 5.2 权限策略：INTERACTIVE = 与主窗一致

`ChatEngine.__init__` 硬编码 `PermissionStrategy.INTERACTIVE` + `interactive_check_callback=self._check_tool_permission`，
且该回调在 `self._backend is None` 时兜底读全局 `Settings` 的工具开关与策略。

**因此直接复用 ChatEngine 就是「与主窗一致」**，不需要任何额外配置。
工具开关关闭 → 按 `resolve_tool_off_policy` 返回 ask/deny；ask 走审批回调。

### 5.3 流式回调 → Qt 信号桥

`IsolatedChatContext.create_chat_engine(worker_callbacks=...)` 接受回调字典，
`ChatEngine._emit` 在 api_mode 下优先走回调（`engine.py:330`）。

⚠️ **回调在 worker 线程触发，禁止直接操作 QWidget**。插件侧定义 `QObject` 信号桥：

```python
class _StreamBridge(QObject):
    chunk = pyqtSignal(str)          # content_received
    error = pyqtSignal(str)          # error
    finished = pyqtSignal()          # stream_finished
    permission = pyqtSignal(str, str, dict)  # permission_approval_requested
```

回调只 `emit`，内容页槽函数在主线程更新 UI。

### 5.4 阻塞调用的线程约束

`ChatEngine.send_message` 内部 `QEventLoop().exec()` 阻塞等待 `_PreSendWorker`，
**必须在后台 QThread 调用**，否则冻住 UI。方案：

- 一个 `QThread` + 常驻 worker，串行消费发送队列
- 同一时刻只允许一个流在跑（`engine._conversation_executor.is_streaming` 已自锁）
- 停止：worker 调 `engine._conversation_executor.cancel_worker()`

### 5.5 会话持久化：写主窗历史

流结束后把消息写回主窗 `history_manager`，让「打开完整会话」与历史面板可翻到：

```python
host.history_manager.save_session(
    messages=session.messages, title="快速对话 · <首问前 20 字>", session_id=session_id,
)
```

⚠️ 规避 `APIHistoryManager`（`session_handler.py`）：它走独立 SQLite + 只留 100 条，
主窗历史面板看不到。这里直接写宿主窗口的 `history_manager`。

## 6. UI 设计（视觉稿 v2）

### 6.1 布局（自上而下三段）

```
┌ PluginWindow 壳（主程序提供）─────────────┐
│ 📌标题栏：图标 + 「快速对话」+ 钉住 + ⟳ ✕ │  ← 钉住由插件注入，其余主程序
├───────────────────────────────────────────┤
│ 状态行：[模型名 chip] 独立会话 · N 轮  新会话│
│ ┌ 回答区（QTextEdit readOnly, 等宽）────┐ │
│ │ 你                                     │ │
│ │ python 里怎么把 list 去重…             │ │
│ │                                        │ │
│ │ 助手                                   │ │
│ │ 用 dict.fromkeys() …                   │ │
│ └────────────────────────────────────────┘ │
│ [工具审批条]（仅 INTERACTIVE 触发时出现）   │
│ ┌ 输入框（自增高，max 88px）────── 发送 ┐ │
│ Enter 发送 · Shift+Enter 换行 · Esc 隐藏    │
└───────────────────────────────────────────┘
```

默认几何 420×340，最小 340×260。

### 6.2 主题

全程从 ctx 取色 + 深浅 fallback，不硬编码：

```python
def _ctx_colors(ctx) -> dict:
    colors = (ctx or {}).get("colors", {}) or {}
    dark = bool((ctx or {}).get("is_dark", True))
    return {
        "text_primary":   colors.get("text_primary")   or ("rgba(255,255,255,0.9)" if dark else "rgba(0,0,0,0.85)"),
        "text_secondary": colors.get("text_secondary") or ("rgba(255,255,255,0.55)" if dark else "rgba(0,0,0,0.45)"),
        "border":         colors.get("border")         or ("rgba(255,255,255,0.12)" if dark else "rgba(0,0,0,0.12)"),
        "accent":         colors.get("accent")         or ("#f59e0b" if dark else "#b8791a"),
    }
```

`register_window(context_provider=...)` 每次调用现取 `app.utils.design_tokens.Colors`（先 `Colors.refresh()`）。

### 6.3 状态机（回答区）

| 状态 | 表现 |
|------|------|
| 空闲 | 灰字占位「问点什么…」 |
| 请求中 | 「◌ 思考中…」+ 已耗时 |
| 流式 | 逐字追加，尾部琥珀光标，自动滚底，发送钮变 ■ 停止 |
| 失败 | 红字错误 + 「重试」按钮，**输入内容不吞** |

### 6.4 钉住开关

标题栏由主程序 `CustomTitleBar(minimal=True)` 提供，插件在 `show_card()` 里
往 `self.window().titleBar.layout()` 的关闭按钮左侧 `insertWidget` 一个小 `QToolButton`。

```python
pinned  →  window.setWindowFlags(window.windowFlags() | Qt.WindowStaysOnTopHint)
unpinned→  window.setWindowFlags(window.windowFlags() & ~Qt.WindowStaysOnTopHint)
```

改 flags 会隐藏窗口，改完必须 `window.show()`。

### 6.5 位置记忆

几何写入插件数据目录（不用 `config_schema`，那是给用户看的设置项）：

```
<app_data>/plugin_data/floating-chat/geometry.json  → {"x": .., "y": .., "w": .., "h": .., "pinned": true}
```

closeEvent 落盘；下次打开还原，越界（屏幕外）则回退居中偏上。

## 7. 「打开完整会话」流程

```
点「打开完整会话」
  → 确保会话已 save_session 落 history_manager
  → 取宿主 MainWidget（window_registry.alive_window_instances()[0]，无则提示）
  → win.show() / raise_() / activateWindow()   # 主窗可见
  → record = win.history_manager.get_session_by_session_id(session_id)
  → win._load_session_from_record(record)      # 主程序既有加载路径
```

⚠️ `_load_session_from_record` 是主窗私有 API，用 `getattr` + 失败降级（只拉起主窗 + InfoBar 提示去历史面板找），
不允许硬崩。

## 8. 热键与命令

- `register_window(register_command=True)` 自动注册 `/floating-chat` 命令
- 用户在**快捷键管理器**里给该命令分配 `alt+space`，落 `user-custom/shortcuts.json`（主程序既有机制）
- 插件**不**自建 `RegisterHotKey` / `keyboard` 钩子——避免与托盘 toggle-window 的全局热键抢消息队列

> 已知风险：`alt+space` 是 Windows 系统窗口菜单键。走命令快捷键（QShortcut）通道时
> 主窗需有焦点才触发——若不满足「主窗完全隐藏也能呼出」，后续再补全局钩子降级方案。

## 9. 边界与不做

| 项 | 决定 |
|----|------|
| Markdown 渲染 | 不做（纯文本等宽） |
| 图片/附件 | 不做（悬浮窗定位是快问快答） |
| 历史多会话切换 | 不做（单会话 + 「新会话」重置） |
| 独立模型选择 | 不做（跟随主窗当前服务商+模型） |
| 全局热键自建 | 不做（走既有快捷键管理） |
| 会话落独立 SQLite | 不做（写主窗 history_manager，保证可翻到） |

## 10. 验证清单

```
1. 命令 /floating-chat 能打开窗                    → 左侧插件栏 + 命令面板
2. 主窗隐藏时仍可用（前提：快捷键走全局通道）        → 实测 alt+space
3. 发消息 → 流式出现 → 完成                        → 纯文本正确、换行缩进保留
4. 与主窗会话隔离：主窗发消息不串到悬浮窗            → 两侧各发一条核对
5. 钉住开/关：切到其他应用验证是否沉底              → WindowStaysOnTopHint
6. 位置记忆：拖动+关窗+重开落原处                   → geometry.json
7. 深浅主题切换后文字/边框/按钮均可见               → theme_manager 刷新
8. 工具审批：触发一个需确认的工具 → 窗内审批条可用   → INTERACTIVE 链路
9. 「打开完整会话」：主窗加载出该会话                → _load_session_from_record
10. 历史面板能翻到该会话                            → save_session 落库
11. 热重载：改 py 后窗与命令均正常                  → sys.modules 前缀清理
12. 应用退出无残留线程/窗口                         → aboutToQuit
```

## 11. 风险登记

| 风险 | 缓解 |
|------|------|
| `_load_session_from_record` 私有 API 变更 | getattr + 失败降级提示 |
| `IsolatedChatContext` 需 `main_widget`，主窗全关时拿不到 | 降级：创建时不发消息，提示先开主窗 |
| `send_message` 阻塞 → 必须后台线程 | QThread worker 串行队列，UI 线程零阻塞 |
| worker 回调跨线程 | QObject 信号桥，槽函数在主线程 |
| `alt+space` 系统键抢占 | 见 §8 降级方案 |
| 改 window flags 会隐藏窗口 | 改完立即 `show()` |
