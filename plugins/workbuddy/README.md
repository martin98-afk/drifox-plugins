# workbuddy 插件

把"专家全能模式"体验注入到 DriFox：安装即开启具备完整 agentic 能力的助手——自动加载工作流、强制以成果呈现收尾、按用户语言回复。

## 功能

- **BuildSystemPrompt 钩子**：在会话构建 system prompt 时注入 `prompts/expert-prompt.md`，让助手进入"专家全能模式"——具备规划、工具调用、子代理、强制成果呈现、最终回答规范等完整行为。
- **`present_files` 工具**：把任务产出的文件以结构化清单呈现给用户（路径、类型、大小、行数），是专家模式末尾的强制收尾步骤。

## 目录结构

```
workbuddy/
├── .drifox-plugin/
│   └── plugin.json
├── hooks/
│   ├── hooks.json                  # BuildSystemPrompt 事件映射
│   └── workbuddy_hook.py           # 提示词注入实现
├── prompts/
│   └── expert-prompt.md            # 专家模式系统提示词（hook 注入）
├── tools/
│   ├── wb_present.py               # present_files 工具实现
│   ├── icons/
│   │   └── present.svg             # 深色主题图标
│   └── icons_light/
│       └── present.svg             # 浅色主题图标
├── icon.svg
├── icon_dark.svg
└── README.md
```

## 安装

```bash
# 从 marketplace 安装（推荐）
drifox plugin install workbuddy

# 或手动复制开发目录
xcopy plugins\workbuddy %USERPROFILE%\.drifox\plugins\workbuddy /E /I /Y
```

## 使用

安装后，新建会话即自动进入专家全能模式，无需额外命令。

会话期间，助手会：

1. **遵循 agent loop**：分析→思考→选工具→执行→观察→迭代→呈现。
2. **以 `present_files` 收尾**：每完成产生文件的子任务，把成果路径批量提交给 `present_files` 工具呈现给用户。
3. **按用户语言回复**：用户用中文提问则中文回答；英文则英文回答。
4. **使用任务管理**：复杂任务会用 TaskCreate / TaskUpdate 追踪进度，必要时派生子代理并行。

## 配置

无需配置。钩子自动：

- 定位 `prompts/expert-prompt.md`（相对 hooks/ 目录）
- 把模板里的 `<PROJECT_ROOT>` 替换为当前项目根目录，写入路径变为 `<project_root>/.drifox/workbuddy-artifacts/`
- 静态文本注入，不拼接会话状态（保证 system prompt 缓存稳定）

## 开发与调试

单独调试钩子：

```bash
echo '{"extra_context":{"project_root":"D:/work/test"}}' \
  | python plugins/workbuddy/hooks/workbuddy_hook.py --event=BuildSystemPrompt
```

校验整个插件：

```bash
python tools/validate_plugins.py plugins/workbuddy
```

## 设计要点

- **静态优先**：提示词内容只做 `<PROJECT_ROOT>` 一项替换，其余保持静态，匹配 DriFox `BuildSystemPrompt` 钩子的缓存友好建议。
- **单一呈现入口**：`present_files` 是所有"把成果给用户"动作的唯一入口，避免重复调用与样式碎片化。
- **错误隔离**：钩子异常时返回空串，不污染主流程。
- **原生 DriFox**：提示词与工具均按 DriFox 概念撰写（workdir、ToolResult、registry、agent_name 等）。

## 版本

1.0.1 — 修复：plan 模式阻断时效（tool_name PascalCase 归一化）+ UI 产物面板加载（FluentIcon 非法枚举）+ _state plan 辅助函数。
1.0.0 — 初版：BuildSystemPrompt 注入 + present_files 工具。

## 许可证

GPL-3.0-or-later。