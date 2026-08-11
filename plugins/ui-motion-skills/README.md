# ui-motion-skills — UI 动效设计技能集

将 Emil Kowalski（前 Vercel / Linear，[animations.dev](https://animations.dev) 作者）的 UI 动效与设计工程方法论注入 DriFox，让 AI 的动效品味达到一线产品水准。

源自 [emilkowalski/skills](https://github.com/emilkowalski/skills)（MIT License，28k+ stars）。

## 功能

| 技能 | 说明 | 触发方式 |
|------|------|---------|
| **emil-design-eng** | 核心哲学：UI 打磨、组件设计、动画决策、不可见细节 | 自动触发（设计/动效类任务） |
| **animate** | 从零构建动画：判断是否该动、用什么工具/属性/曲线/时长 | 自动触发（"加个动画/让组件活起来"） |
| **review-animations** | 严格审查动画代码，高标准把关，默认挑剔 | 显式调用 |
| **improve-animations** | 全库动画审计，产出优先级排序 + 可执行修复计划 | 显式调用（"改进动画/审计动效"） |
| **find-animation-opportunities** | 找出 UI 中该动而没动的地方，同时拒绝不该动的 | 显式调用（"哪里可以加动画"） |
| **animation-vocabulary** | 反向词汇表：把模糊描述变成精确动效术语 | 自动触发（"那个弹一下的效果叫什么"） |
| **apple-design** | Apple 界面设计与物理动效原则（转译为 Web） | 自动触发（手势/弹簧/毛玻璃/减少动效） |
| **pick-ui-library** | 从精选清单挑选合适 UI 库（数字输入/图表/拖拽/toast 等） | 显式调用 |
| **prototype** | 一次构建多个版本 UI，用切换器实时对比、挑选 | 显式调用 |
| **ask-sonner** | Sonner toast 库指南：安装/样式/主题/常见问题排查 | 自动触发（Sonner 相关任务） |

## 安装

插件位于 `plugins/ui-motion-skills/`，DriFox 启动时自动发现。无需额外依赖。

## 技能注入说明

- **自动触发**：AI 处理 UI/动效相关任务时，对应技能自动注入上下文。
- **显式调用**：`pick-ui-library` / `prototype` / `review-animations` / `improve-animations` / `find-animation-opportunities` 仅在你明确要求时运行，避免抢占普通任务上下文。

## 使用示例

```text
# 从零构建一个弹出菜单动画
→ 触发 animate

# 审查刚写的过渡动画
请用 review-animations 审查这段 CSS

# 全站动效体检
请用 improve-animations 审计当前项目的动画

# 想要 iOS 那种橡皮筋回弹
用 apple-design 的 spring 原则做这个拖动交互

# toast 不显示了
用 ask-sonner 排查
```

## 来源与许可

- 上游：https://github.com/emilkowalski/skills（MIT License）
- 本插件打包 10 个技能（含 `RECIPES.md` / `API.md` / `AUDIT.md` / `STANDARDS.md` / `PLAN-TEMPLATE.md` / `PICKER.md` 等辅助文档），内容保持与上游一致，未做修改。
