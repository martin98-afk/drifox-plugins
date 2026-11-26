# Impeccable 设计手艺

把前端界面做到「有观点的手艺」，而不是模型默认输出。

迁移自 [pbakaus/impeccable](https://github.com/pbakaus/impeccable)（117k★，Apache-2.0，上游 commit `2fc5e14`），技能正文译写为中文，`reference/` 保留上游英文原文。

## 它给什么

一套设计总监级别的工作方式，分三层：

1. **四种界面模式**：Persuade（说服，落地页/定价）、Operate（操作，仪表盘/后台）、Read（阅读，文档/文章）、Experience（体验，作品集/画廊）。模式决定雄心该表现成大胆还是克制。
2. **24 个设计动作**：`critique` 启发式评审、`audit` 技术检查、`polish` 发布前收尾、`bolder`/`quieter` 调强度、`distill` 去复杂度、`harden` 补错误态与 i18n、`animate`/`colorize`/`typeset`/`layout`/`delight`/`overdrive` 做增强、`clarify`/`adapt`/`optimize` 修问题、`init`/`document`/`extract` 沉淀设计体系。
3. **50 个参考文件**：每个动作一份操作手册，外加 `craft-floor.md`（质量底线与绝对禁令）、`critique-rubric.md`（评分量规）、`foundations.md`（产品基础设施清单）。

## 用法

装好后直接描述诉求，技能按 description 命中：

- `评审一下这个页面的 UX`
- `这个界面太淡了，做大胆一点`
- `把这个仪表盘打磨到能发布`
- `给这个项目建一套设计体系`
- `图标和空状态都不对，收拾一下`

技能会先读项目里的 PRODUCT.md / DESIGN.md，再按对应动作的参考文件执行。

## 与上游的差异

本插件只移植提示词层，**不含** 上游的 Rust 引擎（`scripts/impeccable`）。上游用这个二进制做上下文加载、截图核对、命令 pin、编辑时检测钩子。因此：

| 上游 | 本移植版 |
|---|---|
| `impeccable context` 加载上下文 | 直接读 PRODUCT.md / DESIGN.md，缺了按 `reference/init.md` 补 |
| `impeccable shot` 截图验证 | 用用户提供的截图/录屏；没有就按清单逐条核对 |
| `pin` / `hooks` / `doctor` / `foundations` | 对应参考文件仍可读，手动执行；写项目配置的动作会明确说不支持 |

`reference/` 里出现的 `scripts/impeccable <verb>` 一律按「不可执行，仅作步骤说明」处理。

## 目录

```
skills/impeccable/
├── SKILL.md               中文正文：四模式、24 个动作的命令表、执行顺序、降级规则
├── reference/             50 个参考文件（英文原文）
│   ├── craft-floor.md     质量底线与绝对禁令，任何 UI 编辑前必读
│   ├── routing.md         无参数时的上下文菜单
│   ├── new-work*.md       新界面的构建 playbook
│   ├── critique*.md       评审与量规
│   └── ios.md / android.md 原生平台指引
├── scripts/
│   └── command-metadata.json  命令元数据（路由参考）
├── LICENSE                Apache-2.0
└── NOTICE.md              第三方内容署名
```

## 许可

Apache-2.0，见 `skills/impeccable/LICENSE`。`reference/ios.md` 与 `reference/android.md` 蒸馏自 ehmo 的 `platform-design-skills`（MIT），署名见 `skills/impeccable/NOTICE.md`。