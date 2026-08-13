# laputa-fog 插件 — DriFox 官方插件

**浮岛·雾青** — 宫崎骏《天空之城》灵感浅色主题。灰蓝主调、琥珀暖金点缀、呼吸感光晕，附带专属聊天列表背景图。

## 功能

| 特性 | 说明 |
|------|------|
| 🌁 **浅色主题** | 灰蓝雾青主调（`#5B7E8E`），琥珀暖金（`#C49A5C`）点缀 |
| 🖼 **专属背景** | 聊天列表背景图 `laputa-fog_bg.jpg`（13% 透明度） |
| ✨ **呼吸感光晕** | `input_glow_preset: breath` — 输入框聚焦呼吸发光 |
| 🎨 **全量 token** | 覆盖基础色/卡片/语法高亮/标签/用户-AI 卡片/输入框/时间线/上下文圆环等全部语义色 |
| 🌓 **明暗自动识别** | 显式声明 `mode: light`，浅色模式切换不依赖亮度检测 |

## 安装

插件位于 `plugins/laputa-fog/`，DriFox 启动时自动发现。

```bash
# Windows
xcopy plugins\laputa-fog %USERPROFILE%\.drifox\plugins\laputa-fog /E /I /Y

# Linux / macOS
cp -r plugins/laputa-fog ~/.drifox/plugins/
```

启动 DriFox 后切换主题：

```bash
/theme laputa-fog
```

或在 `~/.drifox/config.json` 中设为默认主题：

```json
{
  "ui": {
    "theme": "laputa-fog"
  }
}
```

## 目录结构

```
plugins/laputa-fog/
├── .drifox-plugin/
│   └── plugin.json          # manifest（components.themes=true）
├── __init__.py              # Python 包标记
├── themes/
│   └── laputa-fog/
│       ├── laputa-fog.yaml      # 主题定义（灰蓝雾青 + 琥珀暖金）
│       └── laputa-fog_bg.jpg    # 聊天列表背景图
├── icon.svg / icon_dark.svg # 插件图标
└── README.md                # 本文件
```

## 主题 token 速览

- **主调**：`accent: #5B7E8E`（灰蓝）、`accent_warm: #C49A5C`（琥珀暖金）
- **文本**：`text_primary: #1F2D38`、`text_secondary: rgba(31,45,56,0.60)`
- **卡片**：`card_bg: rgba(233,238,242,238)`、`content_bg: #DDE5EC`
- **用户卡**：浅蓝雾面（`rgba(200,222,236,195)`）
- **AI 卡**：暖金雾面（`rgba(245,230,200,225)`）
- **背景**：`laputa-fog_bg.jpg`，透明度 0.13

## 参考

- 主题规范：[`docs/themes.md`](../../docs/themes.md)
- 插件 manifest 规范：[`docs/plugin-manifest.md`](../../docs/plugin-manifest.md)
- 主题加载：[app/utils/theme_manager.py](../../../../D:/work/DriFox/app/utils/theme_manager.py)
