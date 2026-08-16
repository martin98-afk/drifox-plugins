# dsh-super-injector — 运行时上下文注入插件（DriFox 重写版）

**来源**：[yjh051108/dsh-routing-suite](https://github.com/yjh051108/dsh-routing-suite) 的
[dsh-super-injector](https://github.com/yjh051108/dsh-super-injector) 组件（v0.3.3，MIT 授权迁移）。

## 功能概述

- **会话审计观测**：Hook 在会话生命周期关键点（SessionStart / PostToolUse / PostAssistantMessage / Stop）记录审计日志、轻量异常检测与统计收尾，状态落盘 `memory/` 目录。
- **插件状态查询**：`dsh_plugin_status` 列出用户级与项目级插件（name/version/components）。
- **插件自检**：`dsh_plugin_self_test` 校验插件目录结构与 manifest 完整性。
- **能力声明**：`dsh_injector_info` 返回注入能力路径总览。

## 组件

| 目录 | 内容 |
|---|---|
| `hooks/` | 4 事件钩子（SessionStart/PostToolUse/PostAssistantMessage/Stop）+ 处理函数 |
| `tools/` | 3 工具（dsh_injector_info / dsh_plugin_status / dsh_plugin_self_test，全 danger=safe） |

## 与 dsh 原版差异声明

原版 dsh-super-injector 的 **system prompt 声明注入** 已通过 DriFox
**BuildSystemPrompt 事件**复刻：会话构建时把静态能力声明注入 system prompt 尾部（静态到头，
会话缓存稳定）。其余能力差异：
- 原 dev_* 工具全家桶（18 个）→ 精简为 3 个只读观测工具（信息/状态/自检）
- 原运行时热重载/进程内状态 → 由 DriFox 插件管理器（plugin-manager）承担，
  memory/ 目录 JSON 文件落盘（subprocess 无内存共享）

详见 dsh 侧原始文档：`D:/work/tmp/dsh-src/injector/README.md`（或上游仓库
[dsh-super-injector](https://github.com/yjh051108/dsh-super-injector)）。

## 许可证

MIT（原始项目 dsh-super-injector 已获作者授权迁移）。
