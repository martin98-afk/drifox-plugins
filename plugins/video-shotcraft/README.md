# Shotcraft 产品宣传片

把前端项目或网页做成电影感的产品宣传片：真实页面截图、镜头配方、节拍同步与音效设计。

迁移自 [Vincentwei1021/video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft)（22.6k★，Apache-2.0），正文为上游中英双语原文。

## 它补的是什么

本仓的 `anything2explainer` 也是 Remotion 路线，但偏「科普讲解」。这个插件补的是**镜头词汇库 + 音效设计**：

| 资产 | 是什么 |
|---|---|
| 124 张镜头配方卡 | 每张含 demo 实现源码与动态样片，可单独抽卡用在任意视频里 |
| Ink Press 模板 | 一支已验收的完整宣传片工程，按既有镜头结构替换截图/文案/品牌即可 |
| 音效选材 | `sfx-source.py search` 搜 Freesound 候选，`analyze` 测量，支持对齐与替换 |
| 节拍同步 | BGM 与画面节拍对齐的流程与参数 |
| 六阶段工作流 | 产品检查 → 模式选择 → 分镜 → 素材采集 → 实现 → 质检交付 |

## 三种创作模式

上游把整片制作分成三条互不合并的路线，插件保留原样：

1. **直接使用模板**：走 Ink Press，替换素材与文案，最快出货。
2. **自主自由创作**：Agent 自己定视觉方向、分镜、素材、音频，中途不停。
3. **共同创作**：分五个确认节点（产品简报 → 需求决策 → 视觉方向 → 镜头映射 → 最终分镜），逐段放行。

用户没选时，先做一次只读的产品检查，再给三种模式并说明推荐与取舍，不默认替用户选。

## 依赖

需要 node（v22.19+，本机为 v25.8.1，在 `/opt/homebrew/bin/node`）与 ffmpeg：

```bash
cd ~/.drifox/plugins/video-shotcraft/skills/video-shotcraft/template
npm install          # Remotion 4.0.484 + React 19.2.7
npx remotion render  # 出片
```

工作台的 dev server 用 `node workbench/scripts/open.mjs <成片工程目录>`（端口 5198）。ffmpeg 当前未安装，先 `brew install ffmpeg`。

## 目录

```
skills/video-shotcraft/
├── SKILL.md          上游正文（中英双语）：三种模式、工作流、交付标准
├── references/       制作手册：pipeline、分镜、音效、节拍、美术规则、终检
├── demos/            124 张镜头卡的 demo 源码与说明（9.6MB）
├── template/         Ink Press 完整 Remotion 工程（8MB）
├── workbench/        动效工作台
├── shot-polish/      单镜头打磨
├── videos/、publish/、jianying-export/   样片工程、发布脚本、剪映导出
└── LICENSE           Apache-2.0
```

## 与上游的差异

- 裁掉 `assets/`（30MB 宣传用图）、`gallery/`（2.4MB 动效预览图）与多语言 README：预览可在 [vincentwei1021.github.io/video-shotcraft](https://vincentwei1021.github.io/video-shotcraft/) 浏览，不影响出片。
- 保留 `demos/` 与 `template/`：前者是镜头卡的可运行实现，后者是整片工程，都是核心资产。
- 未改任何正文与脚本。

## 图标

图标用上游 `gallery/logo-mark-reverse.svg`（浅色画框 + 琥珀斜切，品牌色 `#D3923C`），加圆角底并缩放居中。

## 许可

Apache-2.0，见 `LICENSE`。