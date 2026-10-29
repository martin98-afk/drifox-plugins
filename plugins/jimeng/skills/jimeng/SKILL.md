---
name: jimeng
description: 即梦（Dreamina）生图/生视频技能 — 当用户要文生图、图生图、图片放大、文生视频、图生视频、首尾帧视频、多帧故事视频、多模态参考视频，或要查即梦额度、管理即梦会话、登录即梦账号时使用。常用词：即梦、Dreamina、dreamina、jimeng、AI 绘图、AI 生图、AI 生视频、seedance、文生图、图生图、图生视频、首尾帧、参考生视频。
---

# 即梦（Dreamina）生成

> 本技能适配 DriFox 的 `jimeng` 工具。工具已封装官方 `dreamina` CLI 的参数校验与成品落盘，
> **优先用工具，不要自己拼命令行**。CLI 直调只在排查问题时用。

## 触发场景

- 用户说「画一张…」「生成一张图」「按这段描述出图」
- 用户提供图片说「改成…」「把背景换掉」「放大这张」
- 用户说「做个视频」「让这张图动起来」「首尾帧过渡」
- 用户问「还剩多少额度」「我的即梦会话有哪些」
- 需要登录即梦才能继续时

## 前置：CLI 是否就绪

首次使用先调 `jimeng action=version` 确认可用。

未安装时按平台装：

| 平台 | 安装 |
|---|---|
| macOS / Linux | `curl -s https://jimeng.jianying.com/cli \| bash` |
| Windows | 官方脚本是 bash，PowerShell 跑不了。直接下载 exe 到 `%USERPROFILE%\bin\dreamina.exe`，再把该目录加进用户 PATH |

Windows 二进制地址：
`https://lf3-static.bytednsdoc.com/obj/eden-cn/psj_hupthlyk/ljhwZthlaukjlkulzlp/dreamina_cli_beta/dreamina_cli_windows_amd64.exe`

查找顺序：`DREAMINA_CLI_PATH` → PATH → `DREAMINA_INSTALL_DIR` → `~/bin`、`%LOCALAPPDATA%/Programs/dreamina`。

## 登录

全自动：遇到未登录报错直接调 `action=login`，工具会自动打开浏览器并阻塞等待授权完成（120s，超时再调 login/checklogin 续等），用户只需登录+点同意。无需向用户解释任何登录步骤，也不要让用户手动开浏览器或复制链接（仅当工具提示「未能自动调起浏览器」才降级为手动）。

## 命令选择

| 需求 | action | 必填 |
|---|---|---|
| 纯文字出图 | `text2image` | `prompt` `resolution` |
| 按图改图（1-10 张） | `image2image` | `images` `prompt` `resolution` |
| 单图放大 | `upscale` | `image` `resolution`(2k/4k/8k) |
| 纯文字出视频 | `text2video` | `prompt` `resolution` |
| 单图动起来 | `image2video` | `image` `prompt` `resolution` |
| 首帧到尾帧 | `frames2video` | `first` `last` `resolution` |
| 多图连贯故事 | `multiframe2video` | `images`(2-20) `resolution` |
| 图/视频/音频混合参考 | `multimodal2video` | 任一输入 + `resolution` |

`multiframe2video` 传 3 张以上图时，必须给 `N-1` 个 `transition_prompts` 描述相邻帧如何过渡；模型在该命令上固定不可选。`multimodal2video` 是原「全能参考」（旧名 ref2video）。

## 参数取值

**图片分辨率**：`1k` / `1.5k` / `2k` / `4k`，按模型不同
- 3.0 / 3.1 → 1k 或 2k
- 4.0 / 4.1 / 4.5 / 4.6 / 4.7 / 5.0 → 2k 或 4k
- 5.0Pro → 1.5k / 2k / 4k
- 默认模型 5.0

**视频分辨率**（必填）：`480p` / `720p` / `1080p` / `4k`，按模型不同
- seedance2.5 → 480p / 720p / 1080p，时长 4-30s，VIP 专属
- seedance2.0_vip → 720p / 1080p / 4k，时长 4-15s
- 其余 → 720p，时长 4-15s（seedance1.5pro 5-12s）
- 默认模型：text2video 是 seedance2.0fast，image2video / frames2video / multimodal2video 是 seedance2.0_vip

**宽高比**
- 图：`21:9` `16:9` `3:2` `4:3` `1:1` `3:4` `2:3` `9:16`（默认 16:9）
- 视频：`1:1` `3:4` `16:9` `4:3` `9:16` `21:9`
- `seedance2.5` 的图生视频/首尾帧**不接受** ratio（跟随首帧）
- 给了 `width`+`height` 就不能再给 `ratio`

**自定义尺寸**（仅图类）：`width` 与 `height` 必须成对，且与 `ratio` 互斥。各分辨率的单边与总像素上限：
- 1k：单边 512-2016，总像素 ≤ 1763584
- 1.5k：单边 972-2268，总像素 ≤ 2359296
- 2k：单边 768-3072，总像素 ≤ 4194304
- 4k：单边 1536-6240，总像素 ≤ 16777216

最终尺寸以后端对齐结果为准，`query` 返回的才是权威值。

## 异步：提交不等于完成

生成命令提交即返回，工具不阻塞等结果。

1. 拿到 `submit_id` 与 `gen_status`
2. `gen_status=querying` **只代表提交成功**，不是生成完成
3. 隔一会儿调 `jimeng action=query submit_id=...`
4. 只有 `success` 才算完成；`fail` 要把 `fail_reason` **主动**告诉用户
5. `query` 成功后文件会落盘，并自动出现在消息卡片的成果栏

不要凭一次 query 的 `querying` 就断言「失败了」。

## 模型选择

**不要凭本技能硬编码模型支持**。各命令的可用模型不同，且运行时可用的模型会变。

用户指定模型时，先看该 action 的 `resolution` 合法值表，或直接试提交看 CLI 报错。用户没指定就保持默认，不要为了「更好」擅自换。

用户表达速度/质量偏好（如「快点」「质量高一点」）时，才显式挑模型。

## 常见错误

| 报错 | 含义 | 处理 |
|---|---|---|
| `未检测到有效登录态` | 没登录 | 调 `action=login`，自动开浏览器等授权，无需用户手动操作 |
| `AigcComplianceConfirmationRequired` | 该模型首次使用需在即梦网页端完成一次生成 | 主动告诉用户去网页端用一次该模型，然后重试 |
| ratio / resolution 被拒 | 该模型不支持该取值 | 按上面的取值表调整，不要瞎试 |
| `未检测到 dreamina CLI` | 没装或不在 PATH | 按平台安装，或设 `DREAMINA_CLI_PATH` |

## 额度

生成消耗账号额度。`jimeng action=credit` 查余额。

- 批量生成前先查额度并告知用户预计消耗
- 用户没明确要求时不要一次提交多张（`generate_num` 保持默认 1）
- 每次付费生成都记下 action、参数、`submit_id` 与最终状态

## 会话

`jimeng action=session session_action=...`：
- `list` — 列出最近会话（ID / 名称 / 置顶 / 更新时间）
- `create` — 新建，可带 `session_name`
- `search` — 按名称查（区分大小写），用 `session_name`
- `rename` — 用 `session_id` + `session_name`
- `delete` — 用 `session_id`（软删除，历史回到默认会话；id 0 是默认会话，不可改名/删除）
