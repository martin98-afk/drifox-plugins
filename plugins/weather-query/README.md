# weather-query — 天气查询工具

输入城市名（中英文均可），返回实时天气与未来 2 天预报。

## 功能

| 项 | 说明 |
|----|------|
| 数据源 | [wttr.in](https://wttr.in) 免费接口，**无需 API key** |
| 输出 | 气温/体感/天况/湿度/风速风向/能见度/UV + 未来 2 天高低温度 |
| 语言 | 天况自动映射中文（36 词条），未命中回退英文原文 |
| 依赖 | 纯 Python 标准库（urllib），零第三方依赖 |

## 用法

对话中直接说「查一下北京天气」，或 AI 调用 `weather_query` 工具：

```
weather_query(city="北京")
weather_query(city="Tokyo")
```

输出示例：

```
📍 北京 当前天气
────────────────────
🌡 气温：26°C（体感 28°C）
☁ 天况：附近零星降雨
💧 湿度：67%
🌬 风速：7 km/h ESE
👁 能见度：10 km  UV：0
📅 2026-08-23  附近零星降雨  23~34°C
📅 2026-08-24  附近雷暴  24~33°C

数据源：wttr.in
```

## 错误处理

- 城市未找到（HTTP 404）→ 提示检查拼写或换英文名
- 网络不可达 → 提示 wttr.in 服务状态
- 空参数 → 提示用法

## 目录结构

```
weather-query/
├── .drifox-plugin/plugin.json
├── icon.svg / icon_dark.svg       ← 插件图标（浅/深主题）
└── tools/
    ├── weather_query.py           ← 工具实现（register 入口）
    └── icons(±_light)/            ← 工具图标
```

## 许可

GPL-3.0-or-later
