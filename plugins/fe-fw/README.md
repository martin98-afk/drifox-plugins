# fe-fw 插件 — DriFox 官方插件

**纹章圣焰** — 火焰纹章 万缕千丝（Fire Emblem: Fortune's Weave）灵感深色主题。火焰橙红主调、皇室暖金点缀，附带专属聊天列表背景图（Leda 立绘）。

## 功能

| 特性 | 说明 |
|------|------|
| 🔥 **深色主题** | 火焰橙红主调（`#E04A2C`），皇室暖金（`#F0B848`）点缀 |
| 🖼 **专属背景** | 聊天列表背景图 `fe-fw_bg.png`（14% 透明度）— Leda「Musician Out for Revenge」立绘 |
| 🎨 **全量 token** | 覆盖基础色/卡片/用户-AI 卡片/输入框/时间线/上下文圆环/分支标签等全部语义色 |
| 🔆 **输入卡 ember 发光** | 聚焦时激活最强一档 halo 级发光（聚焦 70/30、失焦 18/20），契合火焰主题 |
| 🌓 **明暗自动识别** | 显式声明 `mode: dark`，深色模式切换不依赖亮度检测 |

## 安装

插件位于 `plugins/fe-fw/`，DriFox 启动时自动发现。

```bash
# Windows
xcopy plugins\fe-fw %USERPROFILE%\.drifox\plugins\fe-fw /E /I /Y

# Linux / macOS
cp -r plugins/fe-fw ~/.drifox/plugins/
```

启动 DriFox 后切换主题：

```bash
/theme fe-fw
```

或在 `~/.drifox/config.json` 中设为默认主题：

```json
{
  "ui": {
    "theme": "fe-fw"
  }
}
```

## 目录结构

```
plugins/fe-fw/
├── .drifox-plugin/
│   └── plugin.json          # manifest（components.themes=true）
├── __init__.py              # Python 包标记
├── themes/
│   └── fe-fw/
│       ├── fe-fw.yaml       # 主题定义（火焰橙红 + 皇室暖金）
│       └── fe-fw_bg.png     # 聊天列表背景图（Leda 立绘）
├── icon.png / icon_dark.png # 插件图标（官方主视觉：FIRE EMBLEM Fortune's Weave）
└── README.md                # 本文件
```

## 主题 token 速览

- **主调**：`accent: #E04A2C`（火焰橙红）、`accent_warm: #F0B848`（皇室暖金）
- **文本**：`text_primary: #F5EBD8`、`text_secondary: rgba(245,235,216,0.70)`
- **卡片**：`card_bg: rgba(36,14,12,232)`、`content_bg: #22100C`
- **用户卡**：冷蓝雾面（`rgba(38,50,72,150)`）
- **AI 卡**：暖金雾面（`rgba(80,44,24,150)`）
- **背景**：`fe-fw_bg.png`，透明度 0.14

## 设计灵感

- **火焰纹章**：1981 年起 Intelligent Systems 开发的任天堂 SRPG 系列，「Fire Emblem」纹章是系列标志
- **万缕千丝**（Fortune's Weave）：系列第 18 部正统续作，2026.9.17 NS2 独占，舞台为众神统治下的鞑古扎帝国，命运交织是核心叙事母题
- **角色 Leda**：「Musician Out for Revenge」，比维拉琴奏者，复仇动机与皇家火焰气质兼具，立绘色调契合本主题的火焰橙红主调

## 参考

- 主题规范：[`docs/themes.md`](../../docs/themes.md)
- 插件 manifest 规范：[`docs/plugin-manifest.md`](../../docs/plugin-manifest.md)
- 主题加载：[app/utils/theme_manager.py](../../../../D:/work/DriFox/app/utils/theme_manager.py)