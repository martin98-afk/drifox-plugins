---
name: self-evolve
description: DriFox 自进化工作流 — 当用户要求开发新插件、优化/修复现有插件、给 DriFox 接入 MCP 服务器时，按标准自进化循环调用 evolution_* 工具集（scaffold/validate/inspect/mcp/journal）。触发关键词：自进化、开发插件、创建插件、优化插件、修复插件、改进插件、接入 MCP、连接 MCP、写个工具。
---

# self-evolve — DriFox 自进化工作流

DriFox 的工具/插件全部可热重载（user 根 `~/.drifox/plugins/` 保存即生效）。
配合本插件的 5 个 evolution_* 工具，实现「AI 自己给自己开发能力」。

## 工具速查

| 工具 | 用途 |
|------|------|
| `evolution_scaffold` | 需求 → 插件骨架（17 类组件模板） |
| `evolution_validate` | 插件结构校验（准入门槛） |
| `evolution_inspect` | 扫描已装插件/深查结构/TODO 定位 |
| `evolution_mcp` | 读写 .mcp.json 管理 MCP 服务器 |
| `evolution_journal` | 进化审计日志（每次动作必记） |
| `evolution_publish` | 发布到市场仓库（同步+marketplace+校验+commit，push 可选） |

## 标准工作流

### ① 开发新插件

```
1. evolution_scaffold name=<kebab> description=<一句话> components=[tools,...]
   → 生成骨架（含 TODO 标记）
2. read/edit 填充 TODO 实现（user 根直接改，热重载生效）
3. evolution_validate plugin_name=<name> → 全部 OK 才算完成
4. evolution_journal operation=log action=create plugin_name=<name> summary=...
```

### ② 优化/修复现有插件

```
1. evolution_inspect plugin_name=<name> → 摸清结构（目录树/组件/TODO）
2. read 目标实现文件 → 分析问题
3. edit 修改（user 根热重载；system 根需同步主程序仓库）
4. evolution_validate plugin_name=<name> → 复验
5. evolution_journal operation=log action=optimize|fix plugin_name=<name> summary=...
```

找不到工具实现路径时，用 `find_tool_path` 工具（tool-locator 插件）定位。

### ③ 接入 MCP 服务器

```
1. evolution_mcp operation=add plugin_name=<目标插件> server_name=<名称>
   command=<stdio命令> args=[...] env={...}     # 本地型
   或 url=<https://...> headers={...}           # 远程型
2. evolution_mcp operation=list → 确认配置
3. 提醒用户重启 DriFox（MCP 连接不热重载）
4. evolution_journal operation=log action=mcp plugin_name=<name> summary=...
```

### ⑤ 发布到市场（三模式）

```
自己用：无需发布 — 插件在 ~/.drifox/plugins 热加载即生效

分享给社区（标准流程）：
1. GitHub 上 Fork 官方仓库（github.com/martin98-afk/drifox-plugins 右上角 Fork）
2. evolution_publish plugin_name=<name> mode=fork \
     fork_remote=https://github.com/<你的账号>/drifox-plugins.git
   自动：同步仓库 → generate_marketplace → validate → feat/<name> 分支 → 推 fork → 给出 PR 链接
3. 打开 PR 链接提交审核 → maintainer 合并 → 上架

有官方仓库写权限（collaborator）：
   evolution_publish plugin_name=<name>              # 本地 commit（默认）
   evolution_publish plugin_name=<name> mode=direct  # 直推 origin/main
4. evolution_journal operation=log action=note plugin_name=<name> summary=...
```

### ⑥ 回滚

scaffold 的 force 覆盖会把旧版备份为 `<name>.bak.<ts>`。
回滚 = 把备份目录内容移回原位，然后 journal 记 `action=rollback`。
## 硬约束

- 插件名 kebab-case：`^[a-z][a-z0-9-]{1,63}$`
- 工具必须显式声明 `danger`（safe/dangerous），否则 registry 拒绝注册
- `tools/*.py` 必须暴露顶层 `register(registry)`
- impl 签名：`impl(tool_ctx, **kwargs) -> ToolResult`
- 每次进化动作结束**必须**记 journal（可追溯性是自进化的底线）
- 修改 `plugins/system/` 禁止——那是主程序内置
- hooks/mcp/lsp 变更不热重载，需重启 DriFox

## 何时用哪个工具（决策表）

| 用户说 | 动作 |
|--------|------|
| 「做个插件」「帮我开发 xx 功能」 | workflow ① |
| 「xx 插件坏了/慢了/要加功能」 | workflow ② |
| 「接个 MCP」「连 xx 服务」 | workflow ③ |
| 「看看装了哪些插件」 | evolution_inspect list_all=true |
| 「上次进化改了啥」 | evolution_journal operation=list |

## 版本纪律

- 新插件从 0.1.0 起
- 优化/修复后 bump：修 bug → patch；加功能 → minor
- scaffold 覆盖前强制用户确认（force 参数就是确认开关）
