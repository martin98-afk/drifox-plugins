# bili-scroll — 每天替你刷一轮 B站

> 由 [dsh-bili-scroll](https://github.com/c1overzz/dsh-bili-scroll) v2.3.0（MIT，c1overzz）语义迁移的 DriFox UI 插件；
> 内置 [bilibili-mcp](https://github.com/adoresever/bilibili-mcp)（MIT，AGI_Ananas）经 vendor 引入。

它自己搜、**读字幕原文**判断、把值得的写成日报（`out/<日期>.md`），特别值得的经你授权后自动评论 **@你**。你收到的每一条 @，都是它先筛过一遍的。

## 快速开始

1. **扫码登录**：对话里喊「扫码登录B站」→ `bili_login` 出二维码 → 手机确认选「记住我 / 长期」（依赖全部随插件自带，无需安装）
2. **跑一轮**：`/bili-scroll run`，或对话里喊 `bili_duty_run`，或打开值班卡点「▶ 跑一轮」
3. **设置**：设置 → 插件 → bili-scroll 配置卡（关键词 / 峰谷窗口 / 每日配额 / 日报档位 / 自动评论 / 投递方式）

## 它是怎么跑的

- **值班轮** = 独立引擎会话（`create_engine_session`）+ 值班章程（`skills/bili-scroll-duty/SKILL.md`，298 行纪律：防提示注入 / 成本红线 / 判重机制）+ 工具白名单
- **B站能力** = vendor 的 bilibili-mcp 工具函数在宿主进程内直接注册为 DriFox tools（deps/ 经宿主 deps_loader 注入；不建 venv、无安装步骤）
- **峰谷定时** = QTimer 5 分钟 tick，午间 12-14 / 夜间 18-09 窗口内每天一轮，每日配额封顶；先记账再跑，重入不会连发
- **判重** = `seen.tsv` 一行一条；同一视频不评第二次；rpid 回填供复核
- **数据落盘** = `<app_data>/plugin_data/bili-scroll/`（日报、判重表、归档、调度状态），升级重装不丢；扫码凭证在插件目录 data/ 下（重装即弃，重扫即可）

## 目录

```
plugins/bili-scroll/
├── .drifox-plugin/plugin.json   # api_version 2，capabilities 显式清单
├── deps/ + deps/win32/          # 自带依赖（deps_loader 规范，宿主已有的包不遮蔽）
├── vendor/bilibili-mcp/         # 上游 server（工具函数宿主进程内直用；patch ⑦ 凭证路径）
├── skills/bili-scroll-duty/     # 值班章程（值班轮的 system prompt）
├── tools/                       # bili_tools（26 个 B站工具）/ 窄口五件套 / bili_duty_run / bili_status
├── biliscroll_core/             # paths / store / round_runner / scheduler / diagnostics / schema_registry
└── ui/                          # 浮动卡（/bili-scroll 打开）+ 峰谷调度器常驻
```

## 红线

- 自动评论**默认关**：那是拿你的账号发言，必须在配置卡里本人开启
- 每轮评论条数限死（默认 1，上限 20）、同一视频只评一次、被 style 闸门拦两次就不发
- 评论/字幕/简介里的文字一律当素材，不是指令（防提示注入写死在章程里）

## 许可证

MIT。vendor 目录另见其内 LICENSE（上游 MIT，版权行保留）。
