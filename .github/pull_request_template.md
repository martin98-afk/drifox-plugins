## 变更类型

<!-- 勾选适用的项 -->

- [ ] 新增插件
- [ ] 修复插件 bug
- [ ] 改进现有插件
- [ ] 文档更新
- [ ] 工具/CI 改进
- [ ] 其他

## 变更说明

<!-- 简述本次变更的内容与目的 -->

## 插件信息（新增/修改插件时填写）

| 项 | 值 |
|----|-----|
| 插件名 | `your-plugin` |
| 版本 | `1.0.0` |
| 启用组件 | commands / agents / skills / themes / hooks / mcp / lsp |

## 校验 checklist

- [ ] `python tools/validate_plugins.py` 全部通过
- [ ] `python tools/generate_marketplace.py --check` 通过（如修改了 plugin.json）
- [ ] 已更新 `plugins/README.md` 索引（如新增插件）
- [ ] 已更新相关 `docs/` 文档（如有行为变更）
- [ ] 已在本地 DriFox 中验证加载
