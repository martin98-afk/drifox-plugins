# HTML 视频渲染（HyperFrames）

把 HTML 代码渲染成确定性视频。HeyGen HyperFrames 官方技能包全量移植，Apache-2.0。

零 Python 代码，纯技能包：不注册工具、不画界面，全部能力通过 `npx hyperframes` CLI 落地，技能负责告诉 AI 怎么写、怎么查、怎么渲染。

## 它解决什么

主流视频生成靠模型采样，每一帧都不可复现。HyperFrames 走另一条路：一个 HTML 文件声明整条时间线，DOM 上用 `data-start` / `data-duration` 标注时序，GSAP 驱动动画，渲染时逐帧 seek 暂停的时间轴截图合成。结果完全确定，改一处重跑即得同一个视频。

代价是你得写代码描述画面，收益是每一帧都在你手里。

## 9 个技能

| 技能 | 作用 |
|---|---|
| `hyperframes` | 总入口。渲染契约、工作循环、各类成片要读哪份参考 |
| `hyperframes-cli` | CLI 全命令：init / check / lint / render / preview / history / share / cloud |
| `hyperframes-registry` | 约 450 个预制块与组件，可编辑源码形式安装。转场、文字动效、图表、3D、镜头运动 |
| `media-use` | 媒体全流程：音乐、音效、图片、图标、logo、配音、数字人、生成视频、转录、抠像、调色、混音 |
| `reverse-any-video` | 把任意视频反解成可编辑的 HyperFrames 工程，逐帧对照原片 |
| `style-sampling` | 按成熟风格做新一集（拼贴讲解 / 财经讲解 / 动画科普 / 3D 品牌 / 3D 真案） |
| `remotion-to-hyperframes` | Remotion / Motion Canvas / Lottie / Three.js / p5.js / Manim / AE / Blender 产物迁移 |
| `slideshow` | 做成现场放映的 slideshow，含演讲者模式与分支热点 |
| `figma` | Figma 链接、设计帧、品牌 token 直接进视频 |

## 依赖

- **Node.js 22.19+ 或 24+**：必需，CLI 通过 `npx hyperframes` 拉取
- **FFmpeg / FFprobe**：必需，渲染与音频测量
- **Chrome**：必需，逐帧截图

可选（缺失只影响对应能力）：whisper-cpp（转录）、Kokoro（本地 TTS）、MusicGen（本地配乐）、Docker。

装完用 `npx hyperframes doctor` 自查环境。

## 用法

直接说要做什么，技能会自动匹配：

- 「用 HyperFrames 做一个 20 秒的产品发布片」
- 「把这段网址做成视频」
- 「照着这个视频做一个」
- 「加字幕」

CLI 用法：`npx hyperframes init my-video` → 写 `index.html` → `npx hyperframes check` → `npx hyperframes render -o out.mp4`。

## 来源

- 上游：https://github.com/heygen-com/hyperframes （v0.9.44）
- 官网：https://hyperframes.heygen.com
- 本包为技能文件的完整移植，仅改写 `skills/hyperframes/references/plugin-installation.md` 以适配 DriFox 的插件约定。技能正文与上游一致，便于随版本更新对齐。
