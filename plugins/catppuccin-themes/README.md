# catppuccin-themes

Catppuccin 四套主题，翻译自[官方色板](https://github.com/catppuccin/palette)，映射 DriFox 全部 102 个颜色 token。

## 主题

| id | 名称 | 明暗 |
|---|---|---|
| `catppuccin-latte` | 卡布奇诺·拿铁 | 浅色 |
| `catppuccin-frappe` | 卡布奇诺·法布奇诺 | 深色 |
| `catppuccin-macchiato` | 卡布奇诺·玛奇朵 | 深色 |
| `catppuccin-mocha` | 卡布奇诺·摩卡 | 深色 |

## 切换

```
/theme catppuccin-mocha
```

## 映射说明

Catppuccin 的 26 个语义色按层级映射到 DriFox 的 token：

- `base` / `mantle` / `crust` → 内容区与窗口渐变底
- `surface0-2` → 卡片背景、边框、分割线
- `text` / `subtext0-1` / `overlay0-2` → 三级文字
- `mauve` → 主色调（accent / 选中态 / 发送按钮）
- `peach` → 互补暖色（assistant 卡强调、归档态）
- `sky` / `blue` → 用户卡强调、时间线、环形进度
- `green` / `yellow` / `red` → 语义状态色（成功/警告/错误）

原色值未做任何调整，仅做语义槽位分配。需要微调时直接改 yaml 里的 token 值。

## 与上游的差异

- 使用 `backgrounds:` 新 schema（`window` / `sidebar` / `scene` 三区域），不用已废弃的 `background.chat_list`。
- 未配置壁纸图片，只设纯色底。要加壁纸把图片放进主题目录，在 `backgrounds.scene.image` 写文件名。
- `input_glow_preset: breath`（DriFox 内置四档发光预设之一）。
