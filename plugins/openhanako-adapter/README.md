# openhanako-adapter

openhanako（HanaAgent）能力适配插件：把其内置技能、智能体人格、日记、会话转技能、即梦 CLI、beautify HTML 美学移植到 DriFox。

## 组件

### 命令（用户 `/` 入口）
| 命令 | 说明 |
|---|---|
| `/diary` | 写今天的日记：collect 当天全部会话 → 第一人称日记 → 落盘 `OH-Works/日记/YYYY-MM-DD.md` |
| `/xing` | 会话转技能：把刚教完的事提炼成 SKILL.md 并安装（热重载生效） |

### 工具
| 工具 | 说明 |
|---|---|
| `jimeng` | 即梦 CLI 透传：submit 提交生图/生视频任务；query 轮询并下载成品 |

（/diary、/xing 不需要专用工具：命令 prompt 直接驱动模型，模型用 powershell/read/write 自主完成 IO）

### 智能体（人格底座）
`hanako`（温暖·文学，MOOD 块）、`butter`（共情·洞察，PULSE 块）、`ming`（克制·深刻，沉思块）、`kong`（极简·工具，无独白）——openhanako 四 yuan 底座原样移植。

### 技能
| 技能 | 说明 |
|---|---|
| `quiet-musing` | 深度推理协议（5 Phase），openhanako 原样移植 |
| `hana-html-beautify` | Hana HTML 美学纪律（暖纸底/青灰蓝强调/衬线克制/反 AI 味）全章节内联 |
| `agent-creator` | 科班式采访造 DriFox 子智能体人格（character-creator 方法论适配） |

（/diary /xing 的写作/提炼指导已内联在命令 prompt 里，不另设技能）

## 即梦 CLI 前置

```bash
curl -s https://jimeng.jianying.com/cli | bash
```
查找顺序：`DREAMINA_CLI_PATH` → `PATH` → `~/bin`、`%LOCALAPPDATA%/Programs/dreamina`。成品下载到 `<app_data>/plugins/openhanako-adapter/generated/`。

## 日记目录

`<app_data>/OH-Works/日记/YYYY-MM-DD.md`（与 openhanako 工作区输出目录约定对齐；同日重写旧版存 `.old.md`）。

## 来源

- 上游：[liliMozi/openhanako](https://github.com/liliMozi/openhanako)（Apache-2.0）
- 移植映射：`lib/diary/diary-writer.ts` → /diary 命令（模型自主执行）；`/xing` → /xing 命令（模型自主执行）；`lib/agents-templates/*.md` → agents/；`skills2set/quiet-musing` → skills/；`plugins/beautify` HTML 指南 → hana-html-beautify 技能；`plugins/jimeng-cli` → jimeng 工具
