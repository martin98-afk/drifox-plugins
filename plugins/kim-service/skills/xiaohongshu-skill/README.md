# Xiaohongshu Skill

用于生成可直接验收的小红书 / Rednote 完整图文发布包：先研究内容机会，再确定营销与逐页视觉方向，生成封面 MVP，确认后批量完成正文、标题、封面和 6–8 页内页，并做发布前自检。

## 它适合谁

- 课程、咨询、服务、产品、个人 IP、本地商家和知识分享创作者。
- 不满足于“只给文案或提示词”，需要完整图文交付的人。
- 需要保留真实材料边界、平台风险和图片生成证据的人。

## 它和普通生成器有什么不同

- AI 自己研究读者场景、痛点词、同类供给和内容空缺，不把“流量从哪里来”反问给用户。
- 先形成营销决策板与逐页视觉导演表，再写图片 Brief。
- 图片路线优先使用宿主原生生图能力；提示词、SVG 或静态预览不能冒充已生成图片。
- 封面 MVP 通过后才批量出图，避免整套返工。
- 最终聊天给可复制发布版，完整工作台和验收证据放在归档文件中。

## 核心流程

```text
真实材料与边界
-> 内容机会研究
-> 营销决策与逐页视觉方向
-> 标题 / 封面字 / 图片 Brief
-> 封面 MVP
-> 用户确认或明确自动授权
-> 封面 + 6–8 页内页批量生成
-> 正文、标签、承接边界与发布前自检
```

## 包结构

- `SKILL.md`：入口与执行合同。
- `references/`：研究、营销、写作、视觉、平台风险与验收规则。
- `assets/`、`worksheets/`：工作台、决策板和真实材料收集表。
- `contracts/`、`evals/`、`scripts/`：可执行合同与回归门禁。
- `examples/`：正反例与页面方向回归样本。
- `docs/images/`：经授权公开的联系码、微信收款码和支付宝收款码。

## 安装

先进入本 Skill 目录；当前目录应能直接看到 `SKILL.md`。下面命令同时适用于本项目的 `skills/xiaohongshu-skill` 和 `Kim_Service/skills/xiaohongshu-skill`。

Codex 项目级安装：

```powershell
$skillRoot = (Resolve-Path ".").Path
if (-not (Test-Path (Join-Path $skillRoot "SKILL.md"))) { throw "请先进入 xiaohongshu-skill 目录" }
$projectRoot = (Resolve-Path (Join-Path $skillRoot "../..")).Path
$target = Join-Path $projectRoot ".codex/skills/xiaohongshu-skill"
if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
New-Item -ItemType Directory -Force -Path $target | Out-Null
Get-ChildItem -LiteralPath $skillRoot -Force | Copy-Item -Destination $target -Recurse -Force
```

Claude Code 项目级安装：

```powershell
$skillRoot = (Resolve-Path ".").Path
if (-not (Test-Path (Join-Path $skillRoot "SKILL.md"))) { throw "请先进入 xiaohongshu-skill 目录" }
$projectRoot = (Resolve-Path (Join-Path $skillRoot "../..")).Path
$target = Join-Path $projectRoot ".claude/skills/xiaohongshu-skill"
if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
New-Item -ItemType Directory -Force -Path $target | Out-Null
Get-ChildItem -LiteralPath $skillRoot -Force | Copy-Item -Destination $target -Recurse -Force
```

## 推荐触发句

- “帮我做一套完整的小红书图文发布包。”
- “根据这份课程材料做封面和 6–8 页内页。”
- “做一条适合发布的种草图文，先给我确认封面 MVP。”

单个标题、正文润色、评论回复、标签或单张绘画提示词不触发本 Skill。

## 交付形态

- 发布标题首选与至少 8 个备选。
- 可复制正文、标签和公开互动边界。
- 本轮新生成的封面与 6–8 页内页，或明确的阻塞证据。
- 完整工作台、逐页方向和校验记录的归档文件。

## 校验

在当前 Skill 目录运行：

```powershell
if (-not (Test-Path ".\SKILL.md")) { throw "请先进入 xiaohongshu-skill 目录" }
node scripts/check-rednote-note.mjs <output.md>
node scripts/check-rednote-chat-output.mjs <final-chat-output.md>
node scripts/check-chat-output-fixtures.mjs
node scripts/check-page-direction-fixtures.mjs
node scripts/check-narrative-route-fixtures.mjs
node scripts/check-visual-workspace-contract.mjs
```

脚本通过只证明结构合同；本轮图片是否真实生成，仍以宿主工具结果和新产物为准。

## 平台、营销与视觉边界

- 不伪造互动数据、用户反馈、联系方式或真实材料。
- 课程、咨询和服务类公开区避免高风险导流话术。
- 研究和营销路线必须标注用户材料、研究证据与 AI 假设，不能用固定爆款模板冒充研究。
- 真实照片、人物与商业素材必须遵守授权边界；缺真实素材时使用生成素材声明，不能冒充客户实拍。
- Image2 或宿主原生生图可用时优先使用；提示词、SVG、HTML 或静态预览不能冒充最终图片。
- 不把历史输出当成本轮生成证据。
- 联系码、微信收款码和支付宝收款码是本公开包经授权保留的必要资产；内部研究草稿、本机路径、验收会话和其他私有材料不得进入公开包。

## 联系方式

<p align="center">
  <img src="docs/images/contact-qr.png" width="720" alt="联系二维码">
</p>

## 支持项目

如果这个 Skill 帮你完成了图文制作，可以请作者喝杯咖啡：

<table align="center">
  <tr>
    <td align="center"><img src="docs/images/wechat-pay.jpg" width="260" alt="微信收款码"></td>
    <td align="center"><img src="docs/images/alipay.jpg" width="260" alt="支付宝收款码"></td>
  </tr>
</table>

## License

[MIT](LICENSE)
