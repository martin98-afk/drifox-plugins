# workbuddy 插件

把"专家全能模式"体验注入到 DriFox：安装即开启具备完整 agentic 能力的助手——自动加载工作流、强制以成果呈现收尾、按用户语言回复。

## 功能

- **BuildSystemPrompt 钩子**：在会话构建 system prompt 时注入 `prompts/expert-prompt.md`，让助手进入"专家全能模式"——具备规划、工具调用、子代理、强制成果呈现、最终回答规范等完整行为。
- **`present_files` 工具**：把任务产出的文件以结构化清单呈现给用户（路径、类型、大小、行数），是专家模式末尾的强制收尾步骤；同时驱动产物面板自动弹出。
- **Tab 式产物面板**：头部标签页列出所有已呈现的产物（可关闭/拖动排序），下方整区展示内容——Markdown 渲染、HTML 内嵌预览、文本、图片缩放、其余类型一键系统应用打开。新产物自动追加并聚焦。
- **Stop 钩子记忆提醒**：本轮发生过文件修改时，回复结束自动注入【记忆更新检查】提醒（续命一轮，最多一次），还原 WorkBuddy"停止时更新记忆"体验。
- **`wb_memory` 工具**：读取两层记忆全文 / 追加当日工作日志 / 项目长期笔记 / 用户级记忆，模型无需手工拼接记忆文件路径。

## 目录结构

```
workbuddy/
├── .drifox-plugin/
│   └── plugin.json
├── hooks/
│   ├── hooks.json                  # BuildSystemPrompt / PreToolUse / PostToolUse / Stop 事件映射
│   └── workbuddy_hook.py           # 提示词注入 + plan 阻断 + 写入计数 + 记忆提醒
├── prompts/
│   └── expert-prompt.md            # 专家模式系统提示词（hook 注入）
├── tools/
│   ├── wb_present.py               # present_files 工具实现
│   ├── wb_memory.py                # wb_memory 记忆读写工具实现
│   ├── icons/ icons_light/         # 深/浅主题工具图标
├── ui/
│   ├── artifact_panel.py           # Tab 式产物面板
│   └── theme.py                    # 主题样式
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

1.4.1 — 移除 wb_read_me 工具（read 工具已覆盖其能力，使用率低）。
1.4.0 — 迁移 WorkBuddy 内置腾讯技能 4 个：tencent-local-office-edit（本地 Office/WPS 实时编辑，经 editor_sdk MCP）、tencent-docs-routing（本地文档任务路由）、geo-map-compliance-guard（中国地图合规红线）、wb-finance-skill（金融场景总入口 + 60+ 分析框架 references）。未迁移：buddy-multimodal-generation / cloudstudio-deploy / ardot-* 等依赖 WorkBuddy 专有工具链的技能。
1.3.1 — Stop 记忆提醒修复：写入检测改磁盘标记文件通信（HookManager 按 function 缓存键独立 exec_module，模块级状态跨 hook 不共享导致提醒永不触发）；PostToolUse 显式 add_output_to_context=false。
1.3.0 — 修复 wb_plan 拒载（sys.modules 写入触发 PluginToolLoader AST 检查）+ _PopupBridge 后台线程构造 moveToThread 加固 + UI 质感重做（胶囊 tab/图标按钮/居中空态/markdown 排版增强）。
1.2.0 — 内核级还原：解包 WorkBuddy app.asar 对照原版提示词逐模块校对，补齐缺失的沟通风格（3.1）与主动可视化（6.2，Visualizer 适配为 ECharts/HTML 载体 + 主题设计规范 + 模型复杂度门控），记忆系统补检索选源策略与角色边界声明。
1.1.0 — 还原 WorkBuddy 体验：Stop 钩子记忆更新提醒（PostToolUse 写入检测 + completed 续命一轮）+ wb_memory 记忆读写工具 + 产物面板重构为 Tab 式（头部标签页 + 整区内容预览，增量同步不闪烁）+ 自动弹出链路加固（_state key 规范化、/artifacts 命令修复、provider 空缺 cwd 兜底）。
1.0.1 — 修复：plan 模式阻断时效（tool_name PascalCase 归一化）+ UI 产物面板加载（FluentIcon 非法枚举）+ _state plan 辅助函数。
1.0.0 — 初版：BuildSystemPrompt 注入 + present_files 工具。

## 许可证

GPL-3.0-or-later。