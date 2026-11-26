# 文学改互动小说

把一本书、一出戏、一个故事，变成能在浏览器里点着玩的东西。

迁移自 [LindseyyZhang/lit-interactive-fiction](https://github.com/LindseyyZhang/lit-interactive-fiction)（MIT），正文为上游英文原文，`assets/game-template.html` 是 48KB 的单文件游戏引擎。

## 它和另外两个的区别

| | 产出 | 特点 |
|---|---|---|
| `lit-interactive-fiction` | 单文件 HTML，双击即玩 | 隐藏价值观轴 + 蝴蝶效应，结局是性格判定而不是输赢 |
| `interactive-fiction` | 对话里逐回合推进 | 每回合 5 个选项、存档、角色卡 |
| `novel-to-game` | 可运行的游戏工程 | 玩法与美术策划、构建、盲玩验收，可发小游戏平台 |

这个最轻：一个 HTML 文件，不依赖服务器，发给别人就能玩。

## 核心机制

- **有意义的选择**：不是「选 A 还是选 B 都能过」，选项改变隐藏的价值观轴。
- **蝴蝶效应**：前面的选择在后面显形。
- **结局即性格判定**：读完给你的是「你是哪种人」，不是分数或胜负。
- **原创化路径**：有版权的作品走内置改写，避免直接搬运原文。

## 用法

- `把《哈姆雷特》做成互动小说`
- `把这篇小说改成能点着玩的 HTML`
- `给这个互动小说加两条隐藏价值观轴`

## 目录

```
skills/lit-interactive-fiction/
├── SKILL.md                    正文（英文）
├── assets/game-template.html   单文件游戏模板（48KB）
└── references/
    ├── html-engine.md          HTML 引擎用法
    └── narrative-design.md     叙事设计
```

## 与上游的差异

- 裁掉 `examples/hamlet-en.html`（58KB 示例成品），需要时从上游取。
- 未改任何正文与模板。

## 图标

图标符号取自 [Lucide](https://lucide.dev) 的 `feather`，ISC 许可，见 `LICENSE-lucide.txt`。

## 许可

MIT，见 `LICENSE`。