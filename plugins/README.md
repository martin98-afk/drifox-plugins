# 官方插件索引

本目录收录 DriFox 的官方插件。每个插件是独立的目录，遵循统一的 [plugin manifest 规范](../docs/plugin-manifest.md)。

## 索引

| 插件 | 描述 | 组件 | 版本 |
|------|------|------|------|
| [`evolver`](evolver/) | Evolver 自进化引擎 — 基于 GEP 协议沉淀 Agent 经验 | commands + hooks + skills | 1.0.0 |
| [`example-plugin`](example-plugin/) | 最小参考实现，定义官方插件结构与全部 7 类组件约定 | commands + agents + skills + themes + hooks + mcp + lsp | 1.0.0 |

## 组件覆盖矩阵

| | commands | agents | skills | themes | hooks | mcp | lsp |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| evolver | ✅ | — | ✅ | — | ✅ | — | — |
| example-plugin | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

## 添加新插件

1. 在 `plugins/` 下新建一个 kebab-case 目录
2. 在该目录下放置 `.drifox-plugin/plugin.json` 声明 manifest
3. 在 manifest 的 `components` 字典里启用你需要的组件（可启用 1-7 个）
4. 按需实现：
   - `commands/<name>.md`
   - `agents/<name>.md`
   - `skills/<name>/SKILL.md`
   - `themes/<name>/<name>.yaml`
   - `hooks/hooks.json` + `hooks/<plugin>_hook.py`
   - `.mcp.json`（插件根）
   - `.lsp.json`（插件根）
5. 跑 `python tools/validate_plugins.py` 确保通过
6. 在本 README 的「索引」表格中追加一行
7. 提交 PR

## 安装到 DriFox

```bash
# 复制整个插件目录到 DriFox 插件目录
xcopy plugins\evolver %USERPROFILE%\.drifox\plugins\evolver /E /I /Y
# 或
cp -r plugins/evolver ~/.drifox/plugins/
```

启动 DriFox，插件会被自动发现。
