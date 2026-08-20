# 社区插件索引

本分支（community）是 DriFox 的**社区开发模板分支**，只保留 `example-plugin` 作为最小可运行模板。
社区插件由开发者 fork 本分支后开发，代码留在各自 fork；本仓库的 `marketplace.json` 只汇聚它们的**来源**
（不复制代码）。详见 `docs/community-cookbook.md` §10 与 `.github/workflows/sync-community.yml`。

## 模板插件

| 插件 | 描述 | 组件 | 版本 |
|------|------|------|------|
| [`example-plugin`](example-plugin/) | 最小参考实现，定义官方插件结构与全部 9 类组件约定 | 全部 9 类 | 1.0.0 |

## 其他插件在哪

社区插件不进本仓库（保持模板纯净、避免版权耦合）。在 plugin-marketplace 中看到来源后，去对应 fork 下载安装。
本仓库 CI（sync-community.yml）每周扫描所有 fork 并刷新 `marketplace.json`。

## 开发新插件

1. fork 本分支，在 `plugins/` 下新建 kebab-case 目录（**保留 example-plugin 作模板**）
2. 放置 `.drifox-plugin/plugin.json` 声明 manifest
3. 按需实现 `tools` / `commands` / `agents` / `skills` / `themes` / `hooks` / `mcp` / `lsp` / `ui`
4. 跑 `python tools/validate_plugins.py` 确保通过
5. 提交到你的 fork，等待本仓库 CI 汇聚来源

实战模式（来自 80+ 真实插件的精炼）见 [`docs/community-cookbook.md`](../docs/community-cookbook.md)。
