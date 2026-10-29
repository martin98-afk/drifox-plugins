# chrome-classics

> Chrome 主题商店头部主题的 DriFox 移植。四套主题，覆盖中性灰、纯黑、紫雾、森林日落四种调性。

## 主题

| id | 名称 | 明暗 | 上游主题 | 上游规模 |
|---|---|---|---|---|
| `slinky-grey` | 斯林基·中性灰 | 深色 | Slinky Elegant | 900K 用户 / ★4.5 |
| `amoled-black` | 真黑·AMOLED | 深色 | Into The Black Hole - True Amoled Black | 600K 用户 / ★4.6 |
| `shaded-purple` | 紫雾 | 深色 | Shaded Purple | 100K 用户 / ★4.7 |
| `forest-sunset` | 森林日落 | 深色 | Forest environment | 100K 用户 / ★4.4 |

## 切换

```
/theme slinky-grey
/theme amoled-black
/theme shaded-purple
/theme forest-sunset
```

## 各主题要点

### slinky-grey

全主题零彩色，只靠灰阶层次。原版是 `#1B1B1B` frame + `#1E1E1E` toolbar + `#050505` NTP 背景 + `#D2D5D5` 文字。移植时把 accent 直接压成中性灰 `#D2D5D5`，语法高亮也只保留极低饱和的色相，避免破坏中性观感。发光预设用 `platinum`（冷白，无暖色倾向）。

### amoled-black

真 AMOLED 纯黑，`content_bg` 和 window 底色都是 `#000000`。难点全在层次：卡片用 `rgba(13,13,13,235)`、边框用 `#242424`、hover 用 7% 白叠加，靠极窄灰阶和描边把卡片、输入框、分割线从纯黑里分离出来。光晕强度比其它主题低一档（alpha 110/55），否则纯黑上会糊成灰雾。

### shaded-purple

自带壁纸。`backgrounds.scene` 用原图 `scene.jpg`，opacity 0.30 + blur 3 + dim `rgba(30,20,44,0.62)`：原图是高明度紫粉雾面，不压暗压模糊的话文字读不清。`backgrounds.sidebar` 用居中竖裁的 `sidebar.jpg`（1:4，480×1920），opacity 0.92。

### forest-sunset

自带壁纸。原图 1920×1080 插画（星空青蓝天 → 橙金日落 → 深蓝河谷）。主色 `#3C9AAC`（天空青）、暖色 `#F0A44C`（日落金）、底色 `#0B1A26`（河谷深蓝）。`scene` opacity 0.48 + blur 2 + dim 0.62，保留山脊树影的可辨识度；`sidebar` 是居中竖裁 + 高斯模糊 0.6。

## 背景图说明

`shaded-purple` 和 `forest-sunset` 的 `scene.jpg` / `sidebar.jpg` 提取自对应 Chrome 主题包的 NTP 壁纸（`theme_ntp_background.png` / `background.png`），做了尺寸压缩与竖裁，无其它改动。上游壁纸版权归原作者所有，本插件随 DriFox 插件市场以 MIT 分发；二次分发壁纸素材前请自行确认授权。

`slinky-grey` 和 `amoled-black` 上游是纯色主题，本身没有壁纸，因此只用纯色背景层。

## 目录结构

```
chrome-classics/
├── .drifox-plugin/
│   └── plugin.json
├── __init__.py
├── icon.svg
├── icon_dark.svg
├── README.md
└── themes/
    ├── slinky-grey/
    │   └── slinky-grey.yaml
    ├── amoled-black/
    │   └── amoled-black.yaml
    ├── shaded-purple/
    │   ├── shaded-purple.yaml
    │   ├── scene.jpg
    │   └── sidebar.jpg
    └── forest-sunset/
        ├── forest-sunset.yaml
        ├── scene.jpg
        └── sidebar.jpg
```

## 校验

```bash
python tools/validate_plugins.py plugins/chrome-classics
```

## 许可证

MIT（主题 token 定义为原创；壁纸素材版权归上游作者）。
