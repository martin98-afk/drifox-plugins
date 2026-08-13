# Meta Skill Creator

一个用于创建、重构和验收 Agent Skill 的元技能。它关注的不是生成更多文件，而是让 Skill 的目标明确、触发准确、输入输出清楚、执行步骤可操作、边界可检查，并能用真实任务验证。

## 它适合谁

- 想把重复工作流程沉淀成 Codex / Claude Code 可复用 Skill 的个人或团队。
- 已有 Skill 结构完整，但经常误触发、步骤含糊、结果不稳定的人。
- 需要为可视化、营销、研究或工具型 Skill 设计渐进加载和发布验收的人。

## 核心方法

1. 先写最小合同：目标、触发、输入、输出、步骤、边界和验证。
2. 先做最小证据扫查；领域陌生、事实会变化、涉及公开兼容或商业就绪时才升级为深度研究。
3. 把完整包当作能力库：视觉板、营销研究、多模态、交互式 MVP 和发布证明都由条件触发，不是固定模板。
4. 用目标 Skill 自己的脚本、触发正反例、真实任务和边界任务验证。
5. 只有准备公开分发、销售或声称优于基线时，才启用 clean-session、宿主证明和人工验收门禁。

## 包结构

```text
meta-skill-creator/
  SKILL.md
  README.md
  LICENSE
  CHANGELOG.md
  NOTICE
  references/
  assets/
  scripts/
  evals/
  examples/
  docs/images/
```

`SKILL.md` 是轻入口，其余文件按当前阶段渐进加载。目录多不等于每次都要读取或填写。无论本包单独使用，还是位于 `Kim_Service/skills/meta-skill-creator/`，下面的命令都从当前 Skill 目录运行。

## 安装

先进入本 Skill 目录，再把它安装到目标项目。将示例中的目标项目路径改成你的实际路径。

Codex 项目级安装：

```powershell
$skillRoot = (Get-Location).Path
$projectRoot = "D:\path\to\your-project"
$target = Join-Path $projectRoot ".codex/skills/meta-skill-creator"
New-Item -ItemType Directory -Force $target | Out-Null
Copy-Item -Recurse -Force (Join-Path $skillRoot '*') $target
```

Claude Code 项目级安装：

```powershell
$skillRoot = (Get-Location).Path
$projectRoot = "D:\path\to\your-project"
$target = Join-Path $projectRoot ".claude/skills/meta-skill-creator"
New-Item -ItemType Directory -Force $target | Out-Null
Copy-Item -Recurse -Force (Join-Path $skillRoot '*') $target
```

## 推荐触发句

- “把这个重复工作流程做成一个 Skill。”
- “重构这个 Skill，让目标、步骤和边界更清楚。”
- “检查这个 Skill 的触发范围和真实任务验收。”
- “准备公开这个 Skill，补齐发布门禁。”

## 自身校验

进入本 Skill 目录后直接运行：

```powershell
python scripts/check_meta_skill_package.py .
python scripts/check_closed_loop.py .
python scripts/test_acceptance_runs.py
```

这些命令只证明元技能包的结构和验证器回归。候选 Skill 是否好用，仍要运行候选自己的测试并保留真实任务结果；发布级声明还需要独立宿主与人工证据。

## 边界

- 不把一次性任务硬包装成 Skill。
- 不把所有能力模块套给每个候选。
- 不复制外部项目的命名、提示词、示例、视觉系统或商业话术。
- 不把内部研究笔记、验收会话、账号、密钥或本机路径放进公开包。

## 联系方式

<p align="center">
  <img src="docs/images/contact-qr.png" width="720" alt="联系二维码">
</p>

## 支持项目

如果这个项目帮你节省了时间，可以请作者喝杯咖啡：

<table align="center">
  <tr>
    <td align="center"><img src="docs/images/wechat-pay.jpg" width="260" alt="微信收款码"></td>
    <td align="center"><img src="docs/images/alipay.jpg" width="260" alt="支付宝收款码"></td>
  </tr>
</table>

## License

[MIT](LICENSE)
