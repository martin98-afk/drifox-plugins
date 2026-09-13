# dsh-presets

DeepSeek Harness 三种 `agent preset`（`standard` / `code` / `cordis`）的 **DriFox 适配插件**。源自对真实 DSH 会话 JSONL 的逆向整理（`session-72ced1af-*` / `session-ebc0fc2e-*` / `session-2f28127a-*`），将三种 preset 的差异化 system prompt 翻译为 DriFox 的三个 Agent，并配套一个状态化路由 Hook。

> **定位**：DSH 模式适配器 —— 让用户在 DriFox 中**直接获得** DSH standard/code/cordis 三种模式的工作流能力，附 `/dsh-mode` 切换与 `/dsh-status` 查询。

---

## 组件覆盖

- `agents` × 3（standard / code / cordis）
- `hooks` × 1（BuildSystemPrompt 注入 + UserPromptSubmit 切换）
- `skills` × 1（dsh-preset-router：关键词自动匹配 preset）
- `commands` × 2（`/dsh-mode` / `/dsh-status`）

---

## 三种 Preset 速查

| preset | DriFox Agent | system prompt 体量 | 核心定位 | 步骤预算 | 温度 |
|--------|-------------|-------------------|---------|---------|------|
| `standard` | `dsh-standard` | ~6.5k chars | 通用编码；模糊任务默认起点 | 25 | 0.4 |
| `code` | `dsh-code` | ~6.5k chars | 纯写代码专注模式；产出更收敛 | 35 | 0.3 |
| `cordis` | `dsh-cordis` | ~18k chars | Cordis 插件框架开发专用 | 30 | 0.5 |

> **关键差异**：cordis 比 standard 多出**整整一节 Dynamic Cordis Plugins**（含 cordis_inspect_list / cordis_define / cordis_run / cordis_stop / cordis_undefine 等七个工具的完整工作流、HOST vs AGENT PRESET 平面划分、五种身份概念 pluginId/packageId/pluginRunId/currentPackageId/nextPackageId、以及高频错误规避：ctx.get & inject、纯 JavaScript、不序列化 live data、副作用可逆）。

---

## 安装

### 从市场安装（推荐）

在 DriFox 插件市场搜索 **dsh-presets** → 安装。

### 手动安装

将整个 `dsh-presets/` 目录复制到：

```bash
# Windows
xcopy plugins\dsh-presets %USERPROFILE%\.drifox\plugins\dsh-presets /E /I /Y

# Linux / macOS
cp -r dsh-presets ~/.drifox/plugins/
```

启动 DriFox，插件会被自动发现并加载。

---

## 使用方式

### 1. 显式切换

在会话中输入：

```
/dsh-mode standard    # 切到通用编码
/dsh-mode code        # 切到纯写代码
/dsh-mode cordis      # 切到 Cordis 框架开发
```

切换会写入 `~/.drifox/memory/dsh-presets-state.json`，下一次 BuildSystemPrompt 时 Hook 按新 preset 注入对应声明。

### 2. 查询状态

```
/dsh-status
```

输出当前 preset + 切换时间 + 上一 preset + 三选项总览。

### 3. 自动匹配（关键词驱动）

不需要显式调用 `/dsh-mode`。会话中**直接 @ 提及**对应 Agent 即可：

- `@dsh-standard` —— 触发 standard 工作流
- `@dsh-code` —— 触发 code 工作流
- `@dsh-cordis` —— 触发 cordis 工作流

或者由 `dsh-preset-router` skill 在消息内容里识别强信号（`cordis` / `cordis_define` / `@pluginId` / `cordis.yml` / `HOST composition` 等）自动选择 cordis preset。

### 4. 在 cordis 模式下加载专用 skill

切换到 cordis preset 后，AI 会**自动加载** `editing-cordis-compositions` skill 来读取 Cordis composition 编辑规范。

---

## Hook 行为细节

### BuildSystemPrompt（声明注入）

```
PRESET_DECLARATIONS = {
    "standard": "本会话运行在 DSH standard preset（dsh-standard）—— 通用编码 agent ...",
    "code":     "本会话运行在 DSH code preset（dsh-code）—— 纯写代码专注模式 ...",
    "cordis":   "本会话运行在 DSH cordis preset（dsh-cordis）—— Cordis 插件框架开发专用 ...",
}
```

返回的字符串被追加到系统提示尾部，供 LLM 知道当前会话是哪个 preset。

### UserPromptSubmit（切换指令）

- 匹配正则：`/^\/?\s*dsh[-_]mode\s+(standard|code|cordis)\s*\.?$/i`
- 命中 → 更新 `~/.drifox/memory/dsh-presets-state.json` 中对应 session 的 preset 字段
- 返回 `<DSH-PRESETS-INSTRUCTION>...</DSH-PRESETS-INSTRUCTION>` 自包含消息（前端会作为 user 消息注入）
- 不命中 / 消息过短 → 返回空串，不污染消息流

### 状态文件 schema

```json
{
  "<session_id 或 'default'>": {
    "preset": "cordis",
    "updated_at": "2026-08-30T15:00:00+00:00",
    "prev_preset": "standard"
  }
}
```

---

## 文件结构

```
dsh-presets/
├── .drifox-plugin/
│   └── plugin.json              # manifest（agents + hooks + skills + commands）
├── __init__.py                   # 插件包标识
├── README.md                     # 本文件
├── agents/
│   ├── standard.md              # dsh-standard agent
│   ├── code.md                  # dsh-code agent
│   └── cordis.md                # dsh-cordis agent（含完整 cordis 工作流）
├── hooks/
│   ├── hooks.json               # BuildSystemPrompt + UserPromptSubmit 注册
│   └── dsh_presets_hook.py      # 状态化路由实现
├── skills/
│   └── dsh-preset-router/
│       └── SKILL.md             # 关键词 → preset 自动匹配
└── commands/
    ├── dsh-mode.md              # /dsh-mode <preset> 切换
    └── dsh-status.md            # /dsh-status 状态查询
```

---

## 调试

独立测试 hook：

```bash
# BuildSystemPrompt：读 ctx.dsh_preset，注入对应声明
echo '{"dsh_preset":"cordis","session_id":"test"}' \
    | python hooks/dsh_presets_hook.py --event=BuildSystemPrompt

# UserPromptSubmit：解析 /dsh-mode 切换
echo '{"session_id":"test","message":"/dsh-mode cordis"}' \
    | python hooks/dsh_presets_hook.py --event=UserPromptSubmit

# 状态文件位置
cat ~/.drifox/memory/dsh-presets-state.json
```

---

## 数据来源

本插件基于以下三份 DSH 真实会话记录逆向整理（`session.jsonl`，事件流式）：

| 文件 | preset | system prompt 大小 | 关键特征 |
|------|--------|-------------------|---------|
| `session-72ced1af-*` | standard | 6472 chars | 标准 coding agent，基础工具集 |
| `session-ebc0fc2e-*` | standard（从 code 切换） | 6472 chars | 与 standard 同 prompt；验证 preset 可运行时切换 |
| `session-2f28127a-*` | cordis | 18037 chars | 完整 Dynamic Cordis Plugins 工作流 |

`code` preset 的 system prompt 与 `standard` 高度相似（6472 chars 同体量），但定位为**纯编码专注模式**：更长 step 预算、更低温度、更紧验证回路、禁止中途切计划模式。

---

## 许可

MIT
