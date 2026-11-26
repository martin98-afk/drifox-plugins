# 花叔艺术动画

用代码画画，把一支片子从镜头表做到成片，中间有三道硬门禁。

迁移自 [alchaincyf/huashu-art-motion](https://github.com/alchaincyf/huashu-art-motion)（7.7k★，MIT，v1.3.1），正文为上游中文原文。

## 它补的是什么

本仓原有的视频技能（`hyperframes`、`code-video-showcase`、`anything2explainer`）都是「怎么渲」，缺「怎么拍、怎么验」。这个插件补的正是后者：

| 能力 | 具体是什么 |
|---|---|
| 36 种实做风格 + 16 种研究配方 | 梵高、像素、版画等既有风格的代码实现，外加跨场景提炼方法 |
| 9 种解说动画语法 | 8 种可按口播参数渲片段，单片段最多撑 8 秒 |
| 镜头表模板 | 每行一镜：时间段 / 画面里的物 / 它在做什么 / 镜头 / 屏上字 / 做法 |
| 分镜 lint | `scripts/storyboard_lint.py`，查屏上数字与口播是否一致，红灯不许开写 |
| 逐帧质检 | `scripts/qa.py`，抽帧比对「六种做坏方式」 |
| 红灯不交付 | `scripts/deliver.py`，红灯不复制成片；绿灯写交付说明 |

另有导演级的镜头规则：镜头是标点不是修饰、看得清就不动、过渡用缓的重音才用快的、有来有回、整片不能只有一种节拍。

## 两条档位

上游按模型能力分流，插件里保留原样：

- **开阔档**：强模型，全文适用，库自己组合、渲染器自己写。
- **轨道档**：其它情况，只走一条固定路径（镜头表 → lint → 逐镜 → 拼接 → qa → 交付），只读该路径点名的文件。

## 依赖

不需要 node。需要：

```bash
# uv（已装在 ~/.local/bin/uv，不在 GUI PATH 里，调用时用绝对路径或先加 PATH）
~/.local/bin/uv --version
# playwright（uv 会自动装）
~/.local/bin/uv run --with playwright python -c "print('ok')"
# ffmpeg（拼接与质检要用，当前机器未安装）
/opt/homebrew/bin/brew install ffmpeg
```

首帧渲染走 playwright 的 Chromium，`uv run --with playwright` 会拉依赖；如果 Chromium 没下载，先跑一次 `uv run --with playwright playwright install chromium`。

## 用法

- `用艺术动画做一支 60 秒的短片，主题是…`
- `把这个动画拆解并复刻成同风格`
- `照镜头表做第 3 镜`
- `检查这支片子的镜头运动有没有全是 zoom in`

## 与上游的差异

- 裁掉 `assets/`（49.9MB 演示 GIF 与总览图）与 `tests/`：前者是样片展示，不影响出片；样片在上游仓库的 `assets/showcase/` 目录里，需要时从上游取。
- 保留 `scripts/engine`（24MB，含渲染引擎与中文字体 woff）：字体是渲染必需，裁掉会缺字。
- 未改任何正文与脚本。

## 图标

图标符号取自 [Lucide](https://lucide.dev) 的 `palette`，ISC 许可，见 `LICENSE-lucide.txt`。

## 许可

MIT，见 `LICENSE`。