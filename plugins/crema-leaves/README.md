# crema-leaves 插件 — DriFox 官方插件

**奶油树影** — 奶油黄浅色与暖褐深色两套主题，共享同一树影动态背景素材，叶隙光影在对话区缓慢流动（复刻 HanaAgent LeavesOverlay 视觉效果）。

## 功能

| 特性 | 说明 |
|------|------|
| 🌞 **浅色主题** | `crema-leaves-light` — 奶油黄主调（`#b8860b`），与系统静态主题 crema 同配色 |
| 🌙 **深色主题** | `crema-leaves-dark` — 暖褐暗底，亮金点缀（`#d9a12b`），`mode: dark` |
| 🃏 **共享素材** | 两套主题引用同一视频 `themes/assets/leaves-overlay.mp4`（约 2.3MB），安装体积只算一份 |
| 🎬 **动态背景** | yaml `backgrounds.overlay` 驱动，正放+倒放无缝循环；浅色 opacity 0.28 / 深色 0.24 |
| 🎨 **全量 token** | 覆盖基础色/卡片/语法高亮/标签/用户-AI 卡片/输入框/时间线/上下文圆环等全部语义色 |

> 树影遮罩为黑色压暗（帧亮度反相作 alpha），深色主题下是「暗上加暗」，对比天然弱于浅色，属机制特性。

## 安装

插件位于 `plugins/crema-leaves/`，DriFox 启动时自动发现。

```bash
# Windows
xcopy plugins\crema-leaves %USERPROFILE%\.drifox\plugins\crema-leaves /E /I /Y

# Linux / macOS
cp -r plugins/crema-leaves ~/.drifox/plugins/
```

启动 DriFox 后切换主题：

```bash
/theme crema-leaves-light
# 或
/theme crema-leaves-dark
```

## 目录结构

```
plugins/crema-leaves/
├── .drifox-plugin/
│   └── plugin.json              # manifest（components.themes=true）
├── __init__.py                  # Python 包标记
├── themes/
│   ├── leaves-overlay.mp4       # 共享树影视频（两套主题经 ../leaves-overlay.mp4 引用）
│   ├── crema-leaves-light/
│   │   └── crema-leaves-light.yaml
│   └── crema-leaves-dark/
│       └── crema-leaves-dark.yaml
├── icon.png / icon_dark.png     # 插件图标
└── README.md                    # 本文件
```

## 素材出处

`leaves-overlay.mp4` 来自 [HanaAgent](https://github.com/liliMozi/openhanako)（liliMozi/openhanako）的 LeavesOverlay 素材，Apache-2.0 许可。黑白树影、正放+倒放无缝剪辑。

## 参考

- 主题规范：[`docs/themes.md`](../../docs/themes.md)
- 插件 manifest 规范：[`docs/plugin-manifest.md`](../../docs/plugin-manifest.md)
