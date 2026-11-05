# context-usage-stats

对话上下文用量统计 — 浮动卡片展示最近对话的 token 用量、消息数量趋势与会话活跃度图表。

## 功能

- **最近 14 天会话活跃度**：按天统计新建会话数柱状图
- **最近 14 天消息量趋势**：按天统计消息总数折线图
- **最近 14 天 token 用量**：按天汇总 `context_usage`
- **总体统计**：总会话数、总消息数、平均消息数/会话、压缩率
- **当前会话信息**：消息数、估算 token 数
- **项目分布**：按项目维度统计会话数

## 使用

在对话中发送 `/context-usage-stats`，或从浮动卡片入口打开「用量统计」面板。
卡片以 `container="full"` 覆盖对话区，不抢占焦点。

## 实现说明

- 数据直接读取本地 SQLite（`.drifox/sessions.db`），路径查找顺序为
  开发环境项目目录 → 用户目录 `<home>/.drifox/sessions.db`
- 所有查询在后台线程执行，不阻塞 UI
- 卡片内绘制图表，颜色取自当前主题上下文，随明暗主题切换

## 目录结构

```
context-usage-stats/
├── .drifox-plugin/plugin.json   # 插件清单
├── ui/
│   ├── __init__.py              # register_ui 入口
│   ├── cards.py                 # 浮动卡片组件
│   ├── charts.py                # 柱状图 / 折线图 / 统计卡绘制
│   └── data.py                  # SQLite 数据读取（后台线程）
├── icon.png
└── icon_dark.png
```

## 许可

MIT
