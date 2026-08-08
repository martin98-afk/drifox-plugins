# Slack GIF Creator

> 上游：Anthropic 官方 [slack-gif-creator](https://github.com/anthropics/skills/tree/main/skills/slack-gif-creator)（MIT）

创建优化适配 Slack 的动画 GIF：提供约束、校验工具与动画概念。当用户要求「做个 XX 的 GIF」时使用。

## 特性

- GIF 约束校验（尺寸/时长/帧率适配 Slack）
- 动画概念库 + 帧合成工具（pillow/imageio）
- 内置 easing/frame_composer/gif_builder 核心工具

## 依赖

\`pip install pillow imageio imageio-ffmpeg numpy\`（见 skills/slack-gif-creator/requirements.txt）

## 适配说明

与上游一致，零改动。

## 许可证

MIT（与上游一致）。
