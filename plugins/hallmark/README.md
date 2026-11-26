# Hallmark 反模板设计

让 AI 生成的网页看起来是有人设计的，不是模型默认吐出来的。

迁移自 [Nutlope/hallmark](https://github.com/Nutlope/hallmark)（61k★，MIT，上游 commit `04977e1`），技能正文译写为中文，`references/` 与 `scripts/` 保留上游英文原文。

## 它治什么

模型在没有约束时会收敛到同一套默认：紫蓝渐变、卡里套卡、emoji 当图标、eyebrow 小标签、三栏「数字+图标+说明」、编造的客户 logo 墙、居中堆叠的 hero。Hallmark 用三层机制压住它：

1. **底线（Floor，16 条）**：不可协商，任何场景生效，包括颜色与字体必须走 token、禁止 `transition: all`、hero 在 1280×800 不滚动可见、一屏约 80 词、永不编造数字与 logo。
2. **发牌（deal）**：从 20 套主题里抽三张给你选，从 21 种页面形态里抽一种构图，避开项目日志里用过的组合。同一个 prompt 做两次，得到两个不同的页面。
3. **清扫（sweep）**：`sloplint` 自动检查 + 闸门人工过 + 独立上下文完成评审。

## 用法

装好后直接描述你要的页面，技能按 description 命中：

- `做一个 <产品> 的落地页`
- `给 <产品> 做一个定价页，定制风格`
- `重设计 /path/to/page`（用户点名 `redesign` 时才是重设计）
- `审计 /path/to/page`（出一份报告，不改代码）

## 目录

```
skills/hallmark/
├── SKILL.md            中文正文：底线 16 条、流程 7 步、四问、主题发牌
├── references/         27 个参考文件 + 21 种形态 + 20 套主题（英文原文）
│   ├── gates.md        闸门定义（Floor / Reflex / Finish 三级）
│   ├── craft.md        字体、动效、表面手艺
│   ├── anatomy.md      各品类的真实站点结构
│   └── themes/         主题定义与参考图
└── scripts/            Node 脚本，零第三方依赖
    ├── sloplint.mjs    检查器（231KB，含 render 档）
    ├── theme.mjs       发牌 / 脚手架 / 图库检索
    └── capture.mjs     抓真实产品截图
```

## 环境要求

- 核心提示词层（底线、流程、闸门、形态、主题）不依赖任何运行时。
- `scripts/` 只依赖 Node 内置模块，有 Node 就能跑 `sloplint` 与主题发牌；没有 Node 时降级为手工挑主题、人工过闸，并在交付说明里注明未运行 sloplint。
- 上游的 Together AI 构图步骤需要 `TOGETHER_API_KEY`，没有就跳过。

## 许可

上游 MIT，见 `skills/hallmark/LICENSE`。

## 图标

图标用上游 [Nutlope/hallmark](https://github.com/Nutlope/hallmark) 的 `site/favicon.svg`：米白底 + 近黑字形 + 品牌橙 `#FC4C02`；深色版把底与字形反色，橙色保留。
