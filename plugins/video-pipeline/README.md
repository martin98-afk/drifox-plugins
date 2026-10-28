# video-pipeline

短视频生产与多平台发布流水线。19 个原子技能，从选题素材到成片投稿可独立调用，也可串成一条流水线。

## 迁移来源

- 上游仓库：https://github.com/439436269-ctrl/dsh-video-pipeline
- 上游 npm 包：`dsh-video-pipeline`
- 上游 license：MIT

## 技能清单

**生成**

| 技能 | 用途 |
|---|---|
| `ark-seedream-image` | 火山方舟 Seedream 文生图（按量后付费） |
| `ark-agent-plan-image` | 火山引擎 Agent Plan 专属生图/生视频通道 |
| `ark-seedance-video` | 火山方舟 Seedance 文生视频（create → poll → download） |
| `image-to-video` | 静态图转视频 |
| `dreamina-canvas-cli` | 即梦画布 CLI |

**后处理**

| 技能 | 用途 |
|---|---|
| `chinese-tts` | 中文配音读音校正（多音字表 + pinyin_fix 三模式）与 TTS 调用 |
| `video-compose` | 素材合成成片（ffmpeg） |
| `video-cover` | 封面生成 |
| `media-verify` | 成片校验（时长/分辨率/码率/音轨） |

**发布**

| 技能 | 用途 |
|---|---|
| `douyin-publish` | 抖音创作者中心上传发布 + 合集管理 |
| `bilibili-upload` | B 站投稿、biliup 凭据与合集管理 |
| `xiaohongshu-skills` | 小红书 CDP 发布、账号池与选题抓取 |
| `tencent-upload` | 腾讯视频号上传 |
| `quad-platform-publish` | 四平台发布（抖音/B站/小红书/视频号）编排 |
| `multi-platform-publish-orchestrator` | 多平台发布总编排 |

**项目特定**

| 技能 | 说明 |
|---|---|
| `video-pipeline` | 流水线总入口 |
| `tangshi-pipeline` / `tangshi-data-review` | 上游「唐诗 300 首短剧」项目的具体产线，含该项目的数据表与交付目录约定 |
| `feishu-bitable` | 飞书多维表格读写，绑定上游的 base token |

`tangshi-*` 与 `feishu-bitable` 是上游为具体项目写的，通用场景可直接删除，不影响其余 16 个技能。

## 运行时依赖

这些技能靠调用外部工具链干活，插件本身不含实现：

- **ffmpeg**：`video-compose` / `video-cover`
- **Node 18+**：抖音/B站合集管理用的 `.mjs` 脚本
- **Python 3.10+**：小红书、TTS、生图脚本
- **biliup**：B 站投稿凭据与上传
- **playwright / Chrome**：抖音与小红书的浏览器自动化路径
- **火山方舟 API Key**：`ARK_API_KEY` 环境变量

缺哪个，对应技能里的「排障」章节会给出报错对照。

## 与 dsh 原包的差异

- 上游 `lib/*.js` 只做一件事：把 `skills/` 目录注册成 dsh 的 skill provider（rank 600）。DriFox 的插件技能本身就是目录即生效，这层不需要，未迁移。
- 上游 `lib/placeholders.js` 的 `{{TOKEN}}` 运行时替换机制 DriFox 无对应物。已按上游的默认值表把 87 处占位符**静态替换**成可读值（如 `{{USER_HOME}}` → `~`、`{{FEISHU_BASE_APP}}` → `<飞书多维表格 base app_token>`），替换后无残留。
- 技能正文里的路径多为上游作者的 Windows 环境示例（反斜杠、`~\.tools\...`）。非 Windows 平台按自己的工具链路径调整，技能逻辑不依赖这些具体路径。
- `cordis.patch.yml` 的挂载逻辑未迁移（DriFox 无 cordis 运行时）。
