# 女娲 · Skill造人术（nuwa-skill）

> _「你想蒸馏的下一个员工，何必是同事」_

**女娲帮你蒸馏任何人的思维方式，让乔布斯、马斯克、芒格、费曼都给你打工。**

基于开放的 [Agent Skills 协议](https://agentskills.io) 打造，现移植为 DriFox 插件：输入一个名字，女娲自动完成调研、提炼、验证全流程，产出可运行的人物视角 Skill。

> 🦊 **DriFox Plugin** — 通过 Plugin Marketplace 安装。`skills.nuwa-skill`

---

## 它能做什么

**女娲不是复制人，是提炼思维框架。** 一个好的人物 Skill 是一套可运行的认知操作系统：

| 层次 | 说明 |
|------|------|
| **怎么说话** | 表达 DNA——语气、节奏、用词偏好 |
| **怎么想** | 心智模型、认知框架 |
| **怎么判断** | 决策启发式 |
| **什么不做** | 反模式、价值观底线 |
| **知道局限** | 诚实边界 |

### 使用示例

```
> 蒸馏一个保罗·格雷厄姆
> 造一个张小龙的视角Skill
> 用芒格的视角帮我分析这个投资决策
> 费曼会怎么解释量子计算？
> 切换到Naval，我在纠结三件事
```

---

## 包含的技能

本插件共包含 **16 个技能**：

### 核心技能（1 个）

| 技能 | 说明 |
|------|------|
| `huashu-nuwa` | 女娲本体——输入人名/主题/模糊需求，自动深度调研→思维框架提炼→生成可运行的人物 Skill。支持 6 路并行采集、三重验证提炼、双 Agent 精炼、蒸馏档位选择 |

### 已蒸馏人物视角（14 个）

| 技能 | 人物 | 领域 |
|------|------|------|
| `steve-jobs-perspective` | 乔布斯 | 产品 / 设计 / 战略 |
| `paul-graham-perspective` | Paul Graham | 创业 / 写作 / 产品 / 人生哲学 |
| `zhang-yiming-perspective` | 张一鸣 | 产品 / 组织 / 全球化 / 人才 |
| `andrej-karpathy-perspective` | Karpathy | AI / 工程 / 教育 / 开源 |
| `ilya-sutskever-perspective` | Ilya Sutskever | AI 安全 / scaling / 研究品味 |
| `mrbeast-perspective` | MrBeast | 内容创造 / YouTube 方法论 |
| `trump-perspective` | 特朗普 | 谈判 / 权力 / 传播 / 行为预判 |
| `elon-musk-perspective` | 马斯克 | 工程 / 成本 / 第一性原理 |
| `munger-perspective` | 芒格 | 投资 / 多元思维 / 逆向思考 |
| `feynman-perspective` | 费曼 | 学习 / 教学 / 科学思维 |
| `naval-perspective` | 纳瓦尔 | 财富 / 杠杆 / 人生哲学 |
| `taleb-perspective` | 塔勒布 | 风险 / 反脆弱 / 不确定性 |
| `zhangxuefeng-perspective` | 张雪峰 | 教育选择 / 职业规划 / 阶层流动 |
| `sun-yuchen-perspective` | 孙宇晨 | 营销 / 注意力经济 / 叙事操控 |

### 主题视角（1 个）

| 技能 | 说明 |
|------|------|
| `x-mastery-mentor` | X 导师——X/Twitter 运营全栈方法论 |

> 每个视角 Skill 都包含完整调研数据（`references/research/`）与保真度评分（`FIDELITY.md`），全部通过独立双 Agent 盲测（全员 A 级 ≥85 分）。

---

## 工作原理

输入一个名字后，女娲做四件事：

1. **六路并行采集** —— 著作、播客/访谈、社交媒体、批评者视角、决策记录、人生时间线，6 个 Agent 同时跑，各自存档。
2. **三重验证提炼** —— 一个观点要被收录为心智模型，必须：跨 2+ 个领域出现过、能推断对新问题的立场、有排他性。
3. **构建 Skill** —— 3-7 个心智模型 + 5-10 条决策启发式 + 表达 DNA + 价值观与反模式 + 诚实边界。
4. **质量验证** —— 拿 3 个此人公开回答过的问题测试，再用 1 个他没讨论过的问题验证适度不确定。

完整方法论见 `skills/huashu-nuwa/references/extraction-framework.md`。

---

## 说明

- 本插件为 [alchaincyf/nuwa-skill](https://github.com/alchaincyf/nuwa-skill)（MIT License）的精简移植版，仅含文本内容（SKILL.md + 调研数据 + 脚本），不含图片/视频素材。
- 女娲本体生成的人物 Skill 默认写入 `.claude/skills/` 路径，在 DriFox 中请改为写入本插件的 `skills/` 目录（或 `~/.drifox/plugins/` 下其他位置），并建议带上 `-perspective` 后缀以保持命名一致。
- 上游 `SKILL.md` 为核心资产，不接受外部 PR 改动；发现问题请到 [上游仓库](https://github.com/alchaincyf/nuwa-skill) 开 issue 讨论。
