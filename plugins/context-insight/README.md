# context-insight — 上下文洞察

把 Agent 的上下文摊开：它现在携带什么、如何长起来、钱花在哪、工具/技能/命令都做了什么。

## 入口

| 入口 | 形态 | 说明 |
|------|------|------|
| **上下文洞察** | 左侧栏 → 全页覆盖卡 · 洞察 tab | 跨会话 KPI、7 日用量、16 周活跃热力图、计费组成、技能/工具/命令台账、可搜索的会话卡 |
| **会话上下文** | 全页覆盖卡 · 会话上下文 tab | 当前会话的概览 / 组成 / 趋势 / 事件 / 浏览 / 文件 / 命令 / 编队（含消息轨迹泳道图） |
| `/context` | 斜杠命令 | 打开全页并直接切到「会话上下文」tab |
| 偏好设置 | 设置 → 插件 → 上下文洞察偏好 | 默认范围、趋势粒度、自动刷新、系统提示前缀/后缀 |

## 数据口径

- 会话、消息、`token_usage`、`compaction_state`、`file_operations`、子智能体任务全部读宿主 `sessions.db`（只读）。
- 输入组成：系统提示 + 工具定义 + 前缀消息分类（用户 / 注入 / 技能 / 助手 / 推理 / 工具调用 / 工具结果）。
- 工具定义份额：活跃会话用引擎冻结的 tools schema；历史会话用「最后一次 API prompt_tokens − 内容估算」的差额桶。
- 展示为“≈”的步骤是本地估算；带 `token_usage` 的步骤以 API 值为准，并把分类等比锚定到该值。
- 成本按宿主 `models.dev` 缓存的价格估算，未知模型显示 `—` / 近似值。

## 结构

```
ui/
├── __init__.py      注册全页卡 / 右侧面板 / /context
├── insights.py      跨会话洞察页 + 会话上下文 tab 容器
├── panel.py         会话级 Context 面板（嵌入「会话上下文」tab）
├── trend.py         竖向逐请求趋势列表
├── cards.py         统计 / 组成 / 计时 / 事件 / 文件 / 命令卡
├── charts.py        QPainter 图表（环形/堆叠/柱状/热力/趋势/占用环）
├── fleet.py         当前 Agent / 团队成员 / 子智能体 / 消息轨迹泳道
├── lanechart.py     团队消息轨迹泳道图（QPainter，横向滚动）
├── teamcomms.py     团队邮箱聚合 / 快照落盘 / 回放
├── browser.py       逐请求 Context Browser
├── collector.py     QThread 增量扫描 + 单会话分析
├── analyzer.py      组成、趋势、事件、台账、计时
├── store.py         sessions.db 定位 / 解压 / extras 合并
├── pricing.py       models.dev 价格映射
├── theme.py / widgets.py / fmt.py
hooks/inject_prompt_affix.py   BuildSystemPrompt 前缀/后缀注入
```

## 能力池

插件不 import 任何 `app.*` 主程序模块，也不直读 `sessions.db`。全部宿主数据与动作走能力池：

```
session.history  会话列表 / 按 id 取全量记录
session.manage   打开历史会话
model.schema     工具 schema（Token 组成里的“工具定义”）
storage.data_dir 插件数据目录（索引/配置）
stream.subscribe 消息更新 / 流结束 / 会话切换
team.read        团队成员与任务状态
ui.notify        设置入口提示
ui.card.hide     打开会话后收起洞察页
```

## 消息轨迹泳道

「编队」tab 顶部的横向泳道图（复刻 dsh-context 的 pulse 时间线语义）：每个团队成员一条泳道，任务与回复邮件按时间沿轴展开，贝塞尔弧线连接发件人与收件人泳道。

- 数据源：宿主 TeamManager 邮箱（`team.read.get_mailbox_mails`，需宿主 0.7.3+ 白名单）。
- 快照回放：邮箱是「在线信箱」（成员离队即清），聚合结果按 mail_id 增量落到插件数据目录 `teamcomms/<run_id>.jsonl`（单 run 上限 2000 条），团队解散后历史会话仍可回放全程轨迹。
- 交互：hover 看摘要；点击事件点在条带下方展开详情；点击泳道头像筛选该成员相关消息；滚动默认锚到最新。

## 已知边界

- 消息轨迹的泳道名单在活跃团队下取成员表，回放场景从快照事件反推；同名多窗口成员合并为一条泳道。
- 缓存命中率只有活跃会话可读：宿主不把 `cache_read_tokens` 落库，历史会话显示 `—`。
- 工具定义份额对历史会话是当前工具集的近似，不是当时的 schema 快照。
- 系统提示前缀/后缀由 `BuildSystemPrompt` hook 以独立块追加在系统提示末尾（宿主机制决定无法真正插到 base 之前），语义是常驻附加指令。
