# 平台支持

| 能力 | Claude Code | Codex | 其他 Agent Skills 宿主 |
|---|---|---|---|
| 读取 `SKILL.md` | 是 | 是 | 取决于宿主 |
| 三层文件格式 | 是 | 是 | 是，可手动使用 |
| 自动会话加载 | Hooks 配置后 | Hooks 配置并信任后 | 否 |
| 自动工具后提取 | Hooks 配置后 | Hooks 配置并信任后 | 否 |
| 自动压缩前保护 | Hooks 配置后 | Hooks 配置并信任后 | 否 |
| 手动 status/review | 是 | 是 | 是 |

## 不应推导的结论

- “兼容 Agent Skills”不代表“兼容所有宿主 Hooks”。
- 安装器写入配置不代表宿主已加载或信任。
- Python 单元测试通过不代表真实 Claude Code / Codex 会话已触发事件。
- Claude Code 的原生 auto-memory 与本包是不同系统；是否同时使用由用户决定。

平台能力变化时，应以当前宿主官方文档和一次真实会话验证为准，并把静态配置与运行结果分开报告。
