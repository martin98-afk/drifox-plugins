# 小说改编游戏

丢一本小说进去，出来一个能玩的游戏。

迁移自 [zenstory-ai/novel-to-game](https://github.com/zenstory-ai/novel-to-game)（1258★，MIT，v0.9.0），正文为上游中文原文。

## 五个技能分工

| 技能 | 管什么 |
|---|---|
| `novel-to-game` | 总入口：定改编方向、阶段交接、验收记录 |
| `novel-game-analyze` | 通读全书，产出 `SOURCE_BIBLE.md`（人物、线索、可玩点） |
| `game-design` | 玩法与美术策划：概念方向、灰盒、视觉目标图 |
| `game-build` | 用本机工具搭出可运行的游戏 |
| `game-qa` | 新玩家盲玩验收，六项基础检查 |

## 三种模式

- `quick`（默认）：按推荐方案敲定方向，整条流程跑完。
- `director`：在概念方向、灰盒试玩、视觉目标图三个节点给候选与推荐，等你拍板。
- `resume`：读 `_progress.md` 与已生成文档，从最早未走完的交接点接着做。

另有两级标尺：`targetFinish`（灰盒 / 可玩原型 / 打磨过的垂直切片 / 展示级）决定制作完成度，`experienceProfile`（系统主导 / 叙事主导 / 混合）决定用哪套标准衡量体验。

## 支持的平台

网页、桌面、移动端、微信/抖音小游戏、TapTap 制造。

## 工作区

```
game-adaptations/{project}/
├── PRODUCT_BRIEF.md
├── analysis/SOURCE_BIBLE.md
├── concept/...
```

## 用法

- `把这本小说改成能玩的网页游戏`
- `用 director 模式做《…》的改编`
- `继续上次那个改编项目`（resume）
- `给我这个改编做个盲玩验收`

## 与上游的差异

- 只取 `skills/`（116KB，22 文件）。裁掉 `examples/`（148MB 样片）、`docs/`（设计文档）与 `scripts/`（仓库维护脚本）：三者都不被 SKILL.md 引用，不影响出活。
- 未改任何正文。

## 图标

图标符号取自 [Lucide](https://lucide.dev) 的 `gamepad-2`，ISC 许可，见 `LICENSE-lucide.txt`。

## 许可

MIT，见 `LICENSE`。