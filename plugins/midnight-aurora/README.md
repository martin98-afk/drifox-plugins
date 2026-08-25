# midnight-aurora

> 午夜极光主题 — 深紫底色 + 青绿/粉橙双色 accent + 极光侧栏与场景图，给 DriFox 主窗口换上极地夜空氛围。

## 来源

主题定义源自上游 DriFox 应用内置主题 `plugins/system/themes/midnight_aurora/`（含 `midnight_aurora.yaml` + 侧栏/场景图）。本插件将其打包为独立官方插件，方便通过市场分发与版本管理。

## 安装

1. 启动 DriFox → 设置 → 插件市场
2. 搜索 `midnight-aurora` → 安装
3. 设置 → 外观 → 主题 → 选择 **午夜极光**

或手动：

```bash
cp -r plugins/midnight-aurora ~/.drifox/plugins/midnight-aurora
```

## 主题特性

- **mode**: `dark`
- **window 渐变**: `rgba(7,10,28,255)` → `rgba(20,13,43,255)`
- **侧栏背景图**: `sidebar_aurora.png`，不透明度 0.96
- **场景背景图**: `right_aurora.png`，不透明度 0.86，blur=5，dim=`rgba(4,5,18,0.34)`
- **accent**: `#65ddc0`（青绿）+ `#f28ab8`（粉橙）双色
- **输入卡发光预设**: `breath`
- **完整 token 集**: 覆盖全局 UI 基底 / 卡片语义色 / 语法高亮 / 标签 / 用户卡 / 助手卡 / 实时态 / 时间线 / 环形进度 / 分支标签 等

完整 token 列表见 [`themes/midnight_aurora/midnight_aurora.yaml`](./themes/midnight_aurora/midnight_aurora.yaml)。

## 目录结构

```
midnight-aurora/
├── .drifox-plugin/
│   └── plugin.json          # manifest（启用 themes 组件）
├── icon.svg                 # 浅色主题图标
├── icon_dark.svg            # 深色主题图标
├── README.md                # 本文件
└── themes/
    └── midnight_aurora/
        ├── midnight_aurora.yaml
        ├── sidebar_aurora.png
        └── right_aurora.png
```

## 校验

```bash
python tools/validate_plugins.py
```

应输出 `OK   midnight-aurora`。

## 许可证

MIT。