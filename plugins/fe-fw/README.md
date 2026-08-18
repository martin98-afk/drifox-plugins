# fe-fw 插件 — DriFox 官方插件

**银翼圣焰** — 火焰纹章 万缕千丝（Fire Emblem: Fortune's Weave）灵感深色主题。火焰橙红主调、命运女神紫点缀、银白救世主文字色，附带专属聊天列表背景图（Leda 立绘）。

## 功能

| 特性 | 说明 |
|------|------|
| 🔥🟣 **双色调主题** | 火焰橙红（`#E04A2C`）+ 命运女神紫（`#9B7FE0`）双色组合，区别于同色系主题（rdr2 荒漠暖金） |
| ⚪ **银白文字** | 救世主伊修玛尔「银白羽翼铠甲」意象 — `#F0F2F8` 冷银白主文字色 |
| 🖼 **专属背景** | 聊天列表背景图 `fe-fw_bg.png`（14% 透明度）— Leda「Musician Out for Revenge」立绘 |
| 🎨 **全量 token** | 覆盖基础色/卡片/用户-AI 卡片/输入框/时间线/上下文圆环/分支标签等全部语义色 |
| 🔮 **输入卡 platinum 发光** | 聚焦时激活冷峻紫调 halo（聚焦 55/26、失焦 0），契合银翼圣焰主题 |
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

- **主调**：`accent: #E04A2C`（火焰橙红）、`accent_warm: #9B7FE0`（命运女神紫 — 非 rdr2 的暖金）
- **文本**：`text_primary: #F0F2F8`（救世主银白）、`text_secondary: rgba(240,242,248,0.72)`
- **卡片**：`card_bg: rgba(26,16,38,232)`（紫黑底）、`content_bg: #1A0F26`
- **用户卡**：紫蓝雾面（`rgba(48,44,76,150)`）
- **AI 卡**：火焰红雾面（`rgba(80,36,24,160)`）
- **聚焦边框**：`#9B7FE0`（命运紫）— 与 rdr2 的火焰红焦点区分
- **背景**：`fe-fw_bg.png`（Leda 立绘），透明度 0.14

## 设计灵感

- **火焰纹章**：1981 年起 Intelligent Systems 开发的任天堂 SRPG 系列，「Fire Emblem」纹章是系列标志
- **万缕千丝**（Fortune's Weave）：系列第 18 部正统续作，2026.9.17 NS2 独占，舞台为众神统治下的鞑古扎帝国，命运交织是核心叙事母题
- **救世主伊修玛尔**：银白羽翼铠甲、生于禁断之地、与命运女神芙托娜回溯时间改写悲剧结局 — 银白主文字色 + 命运紫聚焦正是这两位角色的视觉化
- **角色 Leda**：「Musician Out for Revenge」，比维拉琴奏者，复仇动机与皇家火焰气质兼具，立绘色调契合本主题的火焰橙红主调

## 参考

- 主题规范：[`docs/themes.md`](../../docs/themes.md)
- 插件 manifest 规范：[`docs/plugin-manifest.md`](../../docs/plugin-manifest.md)
- 主题加载：[app/utils/theme_manager.py](../../../../D:/work/DriFox/app/utils/theme_manager.py)