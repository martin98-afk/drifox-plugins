# rdr2 插件 — DriFox 官方插件

**荒野大镖客** — Red Dead Redemption 2 灵感深色主题。血红主调、荒漠暖金点缀，附带专属聊天列表背景图。

## 功能

| 特性 | 说明 |
|------|------|
| 🌄 **深色主题** | 血红主调（`#A12832`），荒漠暖金（`#D4883A`）点缀 |
| 🖼 **专属背景** | 聊天列表背景图 `rdr2_bg.jpg`（12% 透明度） |
| 🎨 **全量 token** | 覆盖基础色/卡片/用户-AI 卡片/输入框/时间线/上下文圆环/分支标签等全部语义色 |
| 🌓 **明暗自动识别** | 显式声明 `mode: dark`，深色模式切换不依赖亮度检测 |

## 安装

插件位于 `plugins/rdr2/`，DriFox 启动时自动发现。

```bash
# Windows
xcopy plugins\rdr2 %USERPROFILE%\.drifox\plugins\rdr2 /E /I /Y

# Linux / macOS
cp -r plugins/rdr2 ~/.drifox/plugins/
```

启动 DriFox 后切换主题：

```bash
/theme rdr2
```

或在 `~/.drifox/config.json` 中设为默认主题：

```json
{
  "ui": {
    "theme": "rdr2"
  }
}
```

## 目录结构

```
plugins/rdr2/
├── .drifox-plugin/
│   └── plugin.json          # manifest（components.themes=true）
├── __init__.py              # Python 包标记
├── themes/
│   └── rdr2/
│       ├── rdr2.yaml        # 主题定义（血红 + 荒漠暖金）
│       └── rdr2_bg.jpg      # 聊天列表背景图
├── icon.svg / icon_dark.svg # 插件图标（六角星徽章）
└── README.md                # 本文件
```

## 主题 token 速览

- **主调**：`accent: #A12832`（血红）、`accent_warm: #D4883A`（荒漠暖金）
- **文本**：`text_primary: #F0E6D3`、`text_secondary: rgba(240,230,211,0.70)`
- **卡片**：`card_bg: rgba(28,16,14,230)`、`content_bg: #1A0E0C`
- **用户卡**：冷蓝雾面（`rgba(38,50,72,150)`）
- **AI 卡**：暖金雾面（`rgba(70,40,28,150)`）
- **背景**：`rdr2_bg.jpg`，透明度 0.12

## 参考

- 主题规范：[`docs/themes.md`](../../docs/themes.md)
- 插件 manifest 规范：[`docs/plugin-manifest.md`](../../docs/plugin-manifest.md)
- 主题加载：[app/utils/theme_manager.py](../../../../D:/work/DriFox/app/utils/theme_manager.py)
