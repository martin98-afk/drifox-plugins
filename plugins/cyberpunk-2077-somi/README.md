# 赛博朋克 2077 · Somi

Cyberpunk 2077 红灯室主题，深色单主题。

## 内容

| 组成 | 素材来源 |
|------|---------|
| 场景背景 `assets/bg.jpg` | Wallpaper Engine 创意工坊 `3244942566`（Song-So-Mi Cyberpunk-2077，作者 ecksoh）的 `materials/Cyberpunk-2077.tex`，从内嵌 PNG 提取，3962×1800 缩至 2560 宽 |
| 角色剪影 `assets/somi-deco.png` | 同项目的 `materials/Somi 2.tex`，内嵌 RGBA PNG，87% 透明区域，缩至 1600 宽 |
| 背景音乐 | 同项目 `sounds/` 下三首 Cyberpunk 2077 OST |

场景图与音乐由深色主题引用；角色剪影通过 `backgrounds.scene.foreground` 与背景共用同一矩形同一拉伸，还原壁纸原始构图。

## 主题能力演示

这套主题同时用到三块 `backgrounds`：

- `scene` — 主背景图 + `dim` 蒙版压暗，保证文字可读；`foreground` 叠同一画布的人物层
- `music` — 三首 OST 循环播放，`fade_ms: 420`

## 音乐行为

- 切到本主题自动播放，切走立即停止
- 应用失焦自动暂停，切回续播
- 音量由「设置 → 外观 → 主题音乐音量」控制，用户调过后恒以用户值为准

## 授权说明

素材来自 Wallpaper Engine 创意工坊订阅内容，版权归原作者与 CD Projekt RED 所有。本插件仅作个人主题演示，不作商业分发。若要公开发布到市场，建议替换为自有或明确可商用素材。
